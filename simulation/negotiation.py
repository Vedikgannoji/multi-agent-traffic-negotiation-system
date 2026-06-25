"""
negotiation.py - V2V Negotiation Layer (Phase 2 Stage 4).

Provides cooperative decision making between vehicles approaching the
intersection from conflicting corridors.

Architecture:
  1. Conflict Detection — identify cross-corridor vehicle pairs near the
     intersection that would conflict if both proceeded simultaneously.
  2. Priority Calculation — deterministic score based on waiting time,
     distance to intersection, and queue position. Fully explainable.
  3. Conflict Resolution — higher priority → PROCEED, lower → YIELD.
  4. Yield Locking — YIELD decisions persist (event-driven) until the
     winning vehicle physically clears the intersection.
  5. Outcome Broadcasting — send PRIORITY/YIELD/PROCEED V2V messages.

Pure V2V Mode:
  When the traffic manager is in pure_v2v mode, the negotiation engine
  is the SOLE authority for intersection access control. Yield locks
  directly control vehicle motion — a locked vehicle MUST stop.
"""

import sys
import math
from pathlib import Path

try:
    from simulation.vehicle import VehicleAgent, AgentState
    from simulation.communication import VehicleMessage, MessageType
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from vehicle import VehicleAgent, AgentState
    from communication import VehicleMessage, MessageType


# ── Configuration ─────────────────────────────────────────────────────────────
NEGOTIATION_RANGE = 100.0      # Only negotiate with vehicles within this distance
                                # of the intersection center (metres)
CONFLICT_RANGE    = 120.0      # Maximum distance between two vehicles to be
                                # considered a conflicting pair (metres)

# Priority weights (must sum to 1.0)
WEIGHT_WAIT_TIME  = 0.40       # Longer wait → higher priority
WEIGHT_DISTANCE   = 0.35       # Closer to intersection → higher priority
WEIGHT_QUEUE_POS  = 0.25       # Earlier in queue → higher priority

# Normalisation constants
MAX_WAIT_TIME     = 30.0       # seconds — cap for normalisation
MAX_DISTANCE      = 100.0      # metres — max meaningful distance
MAX_QUEUE_POS     = 10         # queue depth cap for normalisation


class NegotiationEngine:
    """
    Cooperative negotiation layer for V2V-enabled autonomous vehicles.

    Called once per simulation tick. Evaluates cross-corridor conflicts,
    computes deterministic priority scores, and assigns YIELD/PROCEED
    outcomes.

    In Pure V2V mode, yield locks directly control vehicle motion.
    Yield locks are EVENT-DRIVEN: once assigned, they persist until
    the winning vehicle physically clears the intersection.
    """

    def __init__(self):
        # Cumulative statistics
        self.negotiations_initiated: int = 0
        self.successful_negotiations: int = 0
        self.yield_decisions: int = 0

        # Observability and metrics
        self.active_negotiations: dict = {}
        self.message_console_log: list = []
        self.total_negotiation_duration: float = 0.0
        self.completed_negotiation_count: int = 0

        # ── Yield Locks (event-driven persistence) ────────────────────────────
        # Maps yielding_vehicle_id → {
        #   "winner_id": int,          # vehicle that won the negotiation
        #   "lock_time": float,        # simulation time when lock was acquired
        # }
        # A locked vehicle MUST remain stopped. The lock is released only when
        # the winner has physically cleared the intersection.
        self.yield_locks: dict = {}

    def reset(self):
        """Reset all negotiation statistics."""
        self.negotiations_initiated = 0
        self.successful_negotiations = 0
        self.yield_decisions = 0
        self.active_negotiations.clear()
        self.message_console_log.clear()
        self.total_negotiation_duration = 0.0
        self.completed_negotiation_count = 0
        self.yield_locks.clear()

    def _add_log(self, text: str, timestamp: float):
        self.message_console_log.append({
            "timestamp": round(timestamp, 2),
            "text": text
        })
        if len(self.message_console_log) > 50:
            self.message_console_log.pop(0)

    # ══════════════════════════════════════════════════════════════════════════
    # YIELD LOCK MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════════

    def release_yield_locks(self, vehicles: list, intersection,
                            current_time: float):
        """
        Release yield locks for vehicles whose winning partner has cleared
        the intersection.

        A lock is released when the winner:
          - Has exited the intersection (has_exited_intersection == True), OR
          - Is no longer in the simulation (removed), OR
          - Has collided (terminal state)

        This is the ONLY way a yield lock gets released.
        """
        if not self.yield_locks:
            return

        # Build lookup of all active vehicles by ID
        vehicle_by_id = {v.vehicle_id: v for v in vehicles}

        locks_to_release = []
        for yielder_id, lock_info in self.yield_locks.items():
            winner_id = lock_info["winner_id"]
            winner = vehicle_by_id.get(winner_id)

            should_release = False

            if winner is None:
                # Winner was removed from simulation — release
                should_release = True
            elif winner.agent_state == AgentState.COLLIDED:
                # Winner collided — release
                should_release = True
            elif winner.has_exited_intersection:
                # Winner has fully crossed and exited — release
                should_release = True
            elif intersection.is_fully_clear(winner):
                # Winner has cleared the intersection zone — release
                should_release = True

            if should_release:
                locks_to_release.append(yielder_id)

        for yielder_id in locks_to_release:
            lock_info = self.yield_locks.pop(yielder_id)
            winner_id = lock_info["winner_id"]

            # Clear the lock on the vehicle object
            yielder = vehicle_by_id.get(yielder_id)
            if yielder is not None:
                yielder.v2v_yield_locked = False
                yielder.v2v_yield_partner_id = None
                yielder.negotiation_outcome = None
                yielder.negotiation_partner_id = None

            duration = current_time - lock_info["lock_time"]
            self._add_log(
                f"Vehicle {yielder_id} yield lock RELEASED "
                f"(winner {winner_id} cleared, {duration:.1f}s)",
                current_time
            )
            print(f"[V2V-UNLOCK] Veh {yielder_id} released — "
                  f"winner Veh {winner_id} cleared ({duration:.1f}s)")

    # ══════════════════════════════════════════════════════════════════════════
    # MAIN ENTRY POINT
    # ══════════════════════════════════════════════════════════════════════════

    def evaluate(self, vehicles: list, intersection, message_bus=None,
                 current_time: float = 0.0):
        """
        Run one tick of negotiation evaluation.

        Steps:
          1. Release expired yield locks (winner cleared).
          2. Clear previous-tick outcomes for UNLOCKED vehicles only.
          3. Identify candidate vehicles.
          4. Detect cross-corridor conflict pairs (skip locked pairs).
          5. Calculate priority for each candidate.
          6. Resolve each conflict: higher priority → PROCEED, lower → YIELD.
          7. Apply outcomes and create yield locks.
          8. Broadcast V2V messages.
        """
        # ── 1. Release expired yield locks ─────────────────────────────────────
        self.release_yield_locks(vehicles, intersection, current_time)

        # ── 2. Clear previous outcomes for UNLOCKED vehicles only ──────────────
        # Locked vehicles keep their YIELD outcome until released.
        for v in vehicles:
            if v.agent_state in (AgentState.CROSSING, AgentState.EXITED,
                                  AgentState.COLLIDED):
                continue
            if v.v2v_yield_locked:
                continue  # DO NOT clear — lock persists
            v.negotiation_outcome = None
            v.negotiation_partner_id = None

        # ── 3. Identify candidates ────────────────────────────────────────────
        candidates = self._get_candidates(vehicles, intersection)

        current_resolved_pairs = set()

        if len(candidates) < 2:
            # Not enough vehicles to negotiate — compute priorities anyway
            for v in candidates:
                v.negotiation_priority = self._calculate_priority(
                    v, intersection
                )
            
            # Clean up active negotiations that are no longer active
            for pair_key in list(self.active_negotiations.keys()):
                record = self.active_negotiations.pop(pair_key)
                duration = current_time - record["start_time"]
                self.total_negotiation_duration += duration
                self.completed_negotiation_count += 1
            return

        # ── 4. Calculate priorities ───────────────────────────────────────────
        for v in candidates:
            v.negotiation_priority = self._calculate_priority(v, intersection)

        # ── 5. Detect conflicts (skip locked pairs) ───────────────────────────
        conflicts = self._detect_conflicts(candidates, intersection)

        # ── 6. Resolve each conflict ──────────────────────────────────────────
        # We evaluate all conflict pairs. If any conflict results in a vehicle
        # needing to YIELD, its outcome is set to YIELD. This correctly propagates
        # yield chains (e.g. A yields to B, B yields to C).
        current_lock_graph = {yielder_id: info["winner_id"] for yielder_id, info in self.yield_locks.items()}

        def has_path(start_id: int, end_id: int) -> bool:
            visited = set()
            curr = start_id
            while curr in current_lock_graph:
                if curr in visited:
                    break
                visited.add(curr)
                curr = current_lock_graph[curr]
                if curr == end_id:
                    return True
            return False

        for va, vb in conflicts:
            self.negotiations_initiated += 1

            # Higher priority gets PROCEED, lower gets YIELD
            if va.negotiation_priority >= vb.negotiation_priority:
                winner, loser = va, vb
            else:
                winner, loser = vb, va

            # Tie-breaking: if priorities are identical, use vehicle ID
            if abs(va.negotiation_priority - vb.negotiation_priority) < 0.001:
                if va.vehicle_id < vb.vehicle_id:
                    winner, loser = va, vb
                else:
                    winner, loser = vb, va

            # Check if making loser yield to winner creates a cycle
            if has_path(winner.vehicle_id, loser.vehicle_id):
                # Swap them to avoid cycle!
                print(f"[V2V-DEADLOCK-PREVENTION] Swapping winner/loser for pair ({va.vehicle_id}, {vb.vehicle_id}) to prevent cycle: {winner.vehicle_id} is already yielding/locked to {loser.vehicle_id}")
                winner, loser = loser, winner

            # Loser must yield to winner (overwrite only if not already yielding)
            if loser.negotiation_outcome != "YIELD":
                loser.negotiation_outcome = "YIELD"
                loser.negotiation_partner_id = str(winner.vehicle_id)
                self.yield_decisions += 1
                current_lock_graph[loser.vehicle_id] = winner.vehicle_id

            # Winner can proceed, but only if they don't have an overriding YIELD outcome
            if winner.negotiation_outcome != "YIELD":
                winner.negotiation_outcome = "PROCEED"
                winner.negotiation_partner_id = str(loser.vehicle_id)

            self.successful_negotiations += 1

            # Track active negotiation session
            pair_key = frozenset({winner.vehicle_id, loser.vehicle_id})
            current_resolved_pairs.add(pair_key)

            if pair_key not in self.active_negotiations:
                # Initiate new negotiation session tracking and logging
                self.active_negotiations[pair_key] = {
                    "vehicle_a": winner.vehicle_id,
                    "vehicle_b": loser.vehicle_id,
                    "start_time": current_time,
                    "logged_intent": True,
                    "logged_priority": True,
                    "logged_yield": True,
                    "logged_proceed": True,
                    "winner": winner.vehicle_id,
                    "yielding": loser.vehicle_id,
                    "priority_a": winner.negotiation_priority,
                    "priority_b": loser.negotiation_priority
                }
                # Log INTENT messages
                self._add_log(f"Vehicle {winner.vehicle_id} -> Vehicle {loser.vehicle_id} : INTENT", current_time)
                self._add_log(f"Vehicle {loser.vehicle_id} -> Vehicle {winner.vehicle_id} : INTENT", current_time)
                # Log PRIORITY messages
                self._add_log(f"Vehicle {winner.vehicle_id} -> Vehicle {loser.vehicle_id} : PRIORITY", current_time)
                self._add_log(f"Vehicle {loser.vehicle_id} -> Vehicle {winner.vehicle_id} : PRIORITY", current_time)
                # Log yielding/proceeding outcome
                self._add_log(f"Vehicle {loser.vehicle_id} yielding to Vehicle {winner.vehicle_id}", current_time)
                self._add_log(f"Vehicle {winner.vehicle_id} proceeding", current_time)
            else:
                # Update existing negotiation info
                record = self.active_negotiations[pair_key]
                record["winner"] = winner.vehicle_id
                record["yielding"] = loser.vehicle_id
                # Track winner/loser priorities specifically:
                if winner.vehicle_id == record["vehicle_a"]:
                    record["priority_a"] = winner.negotiation_priority
                    record["priority_b"] = loser.negotiation_priority
                else:
                    record["priority_a"] = loser.negotiation_priority
                    record["priority_b"] = winner.negotiation_priority

        # ── 7. Apply outcomes: create yield locks & update agent state ─────────
        for v in candidates:
            if v.negotiation_outcome == "YIELD":
                # Create yield lock if not already locked
                if not v.v2v_yield_locked:
                    v.v2v_yield_locked = True
                    v.v2v_yield_partner_id = int(v.negotiation_partner_id)
                    self.yield_locks[v.vehicle_id] = {
                        "winner_id": int(v.negotiation_partner_id),
                        "lock_time": current_time,
                    }
                    print(f"[V2V-LOCK] Veh {v.vehicle_id} YIELD-LOCKED "
                          f"(yielding to Veh {v.negotiation_partner_id}, "
                          f"priority={v.negotiation_priority:.4f})")

                # Set agent state to YIELDING
                if v.agent_state in (AgentState.NEGOTIATING,
                                      AgentState.APPROACHING,
                                      AgentState.WAITING):
                    v.agent_state = AgentState.YIELDING
                    v.yielding_visual_timer = 1.5

        # ── 8. Broadcast V2V messages ─────────────────────────────────────────
        if message_bus is not None:
            self._broadcast_outcomes(candidates, message_bus, current_time)

        # ── 9. Clean up negotiations that are no longer active ────────────────
        for pair_key in list(self.active_negotiations.keys()):
            if pair_key not in current_resolved_pairs:
                # Check if either vehicle in this pair still has a yield lock
                has_active_lock = False
                for vid in pair_key:
                    if vid in self.yield_locks:
                        has_active_lock = True
                        break
                if not has_active_lock:
                    record = self.active_negotiations.pop(pair_key)
                    duration = current_time - record["start_time"]
                    self.total_negotiation_duration += duration
                    self.completed_negotiation_count += 1

    # ══════════════════════════════════════════════════════════════════════════
    # CANDIDATE SELECTION
    # ══════════════════════════════════════════════════════════════════════════

    def _get_candidates(self, vehicles: list, intersection) -> list:
        """
        Return vehicles eligible for negotiation:
          - Within NEGOTIATION_RANGE of intersection center
          - Not already crossing, exited, or collided
          - Not holding a grant (reservation system already decided)
          - Not already crossed/cleared/moving away
        """
        cx = intersection.center_x
        cy = intersection.center_y
        candidates = []

        for v in vehicles:
            # Skip terminal or committed states, and already crossed states
            if v.agent_state in (AgentState.CROSSING, AgentState.EXITED,
                                  AgentState.COLLIDED):
                continue

            # Skip vehicles that have cleared the intersection
            if getattr(v, "has_exited_intersection", False):
                continue

            # Skip vehicles that are physically past the center of the intersection
            if hasattr(v, "is_past_intersection") and v.is_past_intersection(cx, cy):
                continue

            # Skip vehicles with active grants
            if v.vehicle_id in intersection.granted_vehicle_ids:
                continue

            # Distance check
            if v.route.source in ("north", "south"):
                dist = abs(v.position - cy)
            else:
                dist = abs(v.position - cx)

            if dist <= NEGOTIATION_RANGE:
                candidates.append(v)

        return candidates

    # ══════════════════════════════════════════════════════════════════════════
    # CONFLICT DETECTION
    # ══════════════════════════════════════════════════════════════════════════

    def _detect_conflicts(self, candidates: list, intersection) -> list:
        """
        Detect pairs of vehicles from conflicting corridors (NS vs EW).
        Same-corridor vehicles do not conflict at a 4-way intersection.

        Skips pairs where either vehicle already has a yield lock (already
        resolved — no re-negotiation until the lock is released).

        Returns: list of (vehicle_a, vehicle_b) tuples.
        """
        ns_dirs = {"north", "south"}
        conflicts = []

        n = len(candidates)
        for i in range(n):
            for j in range(i + 1, n):
                va = candidates[i]
                vb = candidates[j]

                # Skip only if BOTH vehicles are already yield-locked
                if va.v2v_yield_locked and vb.v2v_yield_locked:
                    continue

                # Only cross-corridor pairs conflict
                a_ns = va.route.source in ns_dirs
                b_ns = vb.route.source in ns_dirs
                if a_ns == b_ns:
                    continue  # Same corridor — no conflict

                # Distance check between the two vehicles
                va_x, va_y = va.get_2d_position(
                    intersection.center_x, intersection.center_y
                )
                vb_x, vb_y = vb.get_2d_position(
                    intersection.center_x, intersection.center_y
                )
                dist = math.sqrt((va_x - vb_x) ** 2 + (va_y - vb_y) ** 2)

                if dist <= CONFLICT_RANGE:
                    conflicts.append((va, vb))

        return conflicts

    # ══════════════════════════════════════════════════════════════════════════
    # PRIORITY CALCULATION
    # ══════════════════════════════════════════════════════════════════════════

    def _calculate_priority(self, vehicle: VehicleAgent,
                            intersection) -> float:
        """
        Deterministic priority score in [0.0, 1.0].

        Factors:
          - Wait time (40%): longer wait → higher priority
          - Distance (35%): closer to intersection → higher priority
          - Queue position (25%): earlier in queue → higher priority

        All factors are normalised to [0, 1] before weighting.
        """
        # ── Wait time component ───────────────────────────────────────────────
        wait_norm = min(vehicle.waiting_time / MAX_WAIT_TIME, 1.0)

        # ── Distance component ────────────────────────────────────────────────
        cx = intersection.center_x
        cy = intersection.center_y
        if vehicle.route.source in ("north", "south"):
            raw_dist = abs(vehicle.position - cy)
        else:
            raw_dist = abs(vehicle.position - cx)
        dist_norm = 1.0 - min(raw_dist / MAX_DISTANCE, 1.0)  # invert: closer = higher

        # ── Queue position component ──────────────────────────────────────────
        direction = vehicle.route.source
        queue = intersection.queues.get(direction)
        if queue and vehicle in queue:
            # Index 0 = front of queue = highest priority
            idx = list(queue).index(vehicle)
            queue_norm = 1.0 - min(idx / MAX_QUEUE_POS, 1.0)
        else:
            queue_norm = 0.5  # Not in queue — neutral

        # ── Weighted sum ──────────────────────────────────────────────────────
        priority = (WEIGHT_WAIT_TIME * wait_norm +
                    WEIGHT_DISTANCE  * dist_norm +
                    WEIGHT_QUEUE_POS * queue_norm)

        return round(priority, 4)

    # ══════════════════════════════════════════════════════════════════════════
    # V2V MESSAGE BROADCASTING
    # ══════════════════════════════════════════════════════════════════════════

    def _broadcast_outcomes(self, candidates: list, message_bus,
                            current_time: float):
        """Broadcast PRIORITY, YIELD, and PROCEED messages for resolved vehicles."""
        for v in candidates:
            if v.negotiation_outcome is None:
                continue

            # Send priority announcement
            priority_msg = VehicleMessage(
                sender_id=v.agent_id,
                timestamp=current_time,
                message_type=MessageType.PRIORITY,
                payload={
                    "priority_score": v.negotiation_priority,
                    "outcome": v.negotiation_outcome,
                    "partner_id": v.negotiation_partner_id
                }
            )
            message_bus.broadcast(priority_msg)

            # Send specific outcome message
            if v.negotiation_outcome == "YIELD":
                outcome_msg = VehicleMessage(
                    sender_id=v.agent_id,
                    timestamp=current_time,
                    message_type=MessageType.YIELD,
                    payload={
                        "yielding_to": v.negotiation_partner_id,
                        "priority_score": v.negotiation_priority
                    }
                )
                message_bus.broadcast(outcome_msg)
            elif v.negotiation_outcome == "PROCEED":
                outcome_msg = VehicleMessage(
                    sender_id=v.agent_id,
                    timestamp=current_time,
                    message_type=MessageType.PROCEED,
                    payload={
                        "proceeding_over": v.negotiation_partner_id,
                        "priority_score": v.negotiation_priority
                    }
                )
                message_bus.broadcast(outcome_msg)

    # ══════════════════════════════════════════════════════════════════════════
    # STATISTICS
    # ══════════════════════════════════════════════════════════════════════════

    def get_stats(self) -> dict:
        """Return negotiation statistics."""
        return {
            "negotiations_initiated": self.negotiations_initiated,
            "successful_negotiations": self.successful_negotiations,
            "yield_decisions": self.yield_decisions,
        }
