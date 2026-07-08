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

        # V2V Conflict-Aware confirmed reservations and live debug edges
        self.confirmed_reservations: dict = {}
        self.conflict_edges: list = []

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
        self.confirmed_reservations.clear()
        self.conflict_edges.clear()

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
                yielder.reservation_state = "NONE"

            duration = current_time - lock_info["lock_time"]
            self._add_log(
                f"Vehicle {yielder_id} yield lock RELEASED "
                f"(winner {winner_id} cleared, {duration:.1f}s)",
                current_time
            )
            print(f"[V2V-UNLOCK] Veh {yielder_id} released — "
                  f"winner Veh {winner_id} cleared ({duration:.1f}s)")

    def release_confirmed_reservations(self, vehicles: list, intersection,
                                       current_time: float):
        """
        Release V2V reservations whose vehicle has crossed and cleared the intersection.
        """
        if not self.confirmed_reservations:
            return

        vehicle_by_id = {v.vehicle_id: v for v in vehicles}
        to_release = []

        for winner_id, res_info in self.confirmed_reservations.items():
            winner = vehicle_by_id.get(winner_id)
            should_release = False

            if winner is None:
                should_release = True
            elif winner.agent_state == AgentState.COLLIDED:
                should_release = True
            elif winner.has_exited_intersection:
                should_release = True
            elif intersection.is_fully_clear(winner):
                should_release = True
            elif current_time > res_info["exit_time"] + 5.0:  # Timeout safety net
                if not intersection.is_in_intersection(winner):
                    should_release = True

            if should_release:
                to_release.append(winner_id)

        for winner_id in to_release:
            self.confirmed_reservations.pop(winner_id, None)
            winner = vehicle_by_id.get(winner_id)
            if winner is not None:
                winner.reservation_state = "NONE"
                winner.reservation_entry_time = 0.0
                winner.reservation_exit_time = 0.0
                winner.negotiation_outcome = None
                winner.negotiation_partner_id = None

    # ══════════════════════════════════════════════════════════════════════════
    # MAIN ENTRY POINT
    # ══════════════════════════════════════════════════════════════════════════

    def evaluate(self, vehicles: list, intersection, message_bus=None,
                 current_time: float = 0.0):
        """
        Conflict-Aware Local V2V Negotiation:
        Only vehicles with intersecting trajectories negotiate.
        Connected components of the conflict graph define the conflict groups.
        """
        # ── 1. Release expired yield locks & reservations ─────────────────────
        self.release_yield_locks(vehicles, intersection, current_time)
        self.release_confirmed_reservations(vehicles, intersection, current_time)

        # ── 2. Reset transient states of candidates ───────────────────────────
        for v in vehicles:
            if v.agent_state in (AgentState.CROSSING, AgentState.EXITED, AgentState.COLLIDED):
                continue
            # Non-candidates are reset to NONE reservation if they are not confirmed
            if v.reservation_state != "CONFIRMED":
                v.reservation_state = "NONE"
                v.negotiation_outcome = None
                v.negotiation_partner_id = None
                v.reason_for_yield = ""
                v.conflict_group = []
                v.negotiating_with = []

        # ── 3. Identify candidate vehicles ────────────────────────────────────
        candidates = self._get_candidates(vehicles, intersection)
        
        # Build lookups
        candidate_ids = {v.vehicle_id for v in candidates}
        vehicle_by_id = {v.vehicle_id: v for v in vehicles}

        # Clear visual debug conflict edges list
        self.conflict_edges = []

        if len(candidates) == 0:
            # Clean up active negotiations that are no longer active
            for pair_key in list(self.active_negotiations.keys()):
                record = self.active_negotiations.pop(pair_key)
                duration = current_time - record["start_time"]
                self.total_negotiation_duration += duration
                self.completed_negotiation_count += 1
            return

        # ── 4. Estimate entry/exit times and calculate priorities ──────────────
        for v in candidates:
            v.negotiation_priority = self._calculate_priority(v, intersection)
            dist_to_stop = intersection.get_distance_to_stop_line(v)
            ref_speed = max(v.current_speed, v.desired_speed, 1.0)
            
            # Estimate windows
            if dist_to_stop <= 0.0 or intersection.is_in_intersection(v) or intersection.is_between_stop_and_intersection(v):
                v.estimated_entry_time = current_time
                v.estimated_exit_time = current_time + (intersection.size + 30.0) / ref_speed
            else:
                v.estimated_entry_time = current_time + dist_to_stop / ref_speed
                v.estimated_exit_time = v.estimated_entry_time + (intersection.size + 30.0) / ref_speed

        # ── 4b. Identify "obstacle" vehicles (CROSSING/EXITED but still in intersection) ──
        #    These are NOT candidates (they can't yield), but approaching
        #    candidates whose routes conflict with them must yield.
        obstacles = []
        for v in vehicles:
            if v.agent_state in (AgentState.CROSSING, AgentState.EXITED):
                if intersection.is_in_intersection(v):
                    obstacles.append(v)

        obstacle_ids = {o.vehicle_id for o in obstacles}

        # ── 5. Build conflict graph adjacency list & connected components ─────
        adj = {v.vehicle_id: [] for v in candidates}
        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                v1 = candidates[i]
                v2 = candidates[j]
                if v1.route.conflicts_with(v2.route):
                    adj[v1.vehicle_id].append(v2.vehicle_id)
                    adj[v2.vehicle_id].append(v1.vehicle_id)
                    self.conflict_edges.append([v1.vehicle_id, v2.vehicle_id])

        # Also record which candidates conflict with which obstacles
        candidate_obstacle_map = {}  # candidate_id -> list of obstacle vehicle_ids
        for c in candidates:
            conflicting_obs = []
            for o in obstacles:
                if c.route.conflicts_with(o.route):
                    conflicting_obs.append(o.vehicle_id)
            if conflicting_obs:
                candidate_obstacle_map[c.vehicle_id] = conflicting_obs

        visited = set()
        components = []
        for v in candidates:
            vid = v.vehicle_id
            if vid not in visited:
                comp = set()
                stack = [vid]
                while stack:
                    curr = stack.pop()
                    if curr not in comp:
                        comp.add(curr)
                        visited.add(curr)
                        for neighbor in adj[curr]:
                            if neighbor not in visited:
                                stack.append(neighbor)
                components.append(comp)

        current_resolved_pairs = set()

        # ── 6. Process each Connected Component (Conflict Group) ──────────────
        for comp in components:
            if len(comp) == 1:
                # Bypass: alone in its conflict group among candidates
                vid = next(iter(comp))
                v = vehicle_by_id[vid]

                # BUT: check if this candidate conflicts with any obstacle
                obs_conflicts = candidate_obstacle_map.get(vid, [])
                if obs_conflicts:
                    # Must yield to the crossing/exited vehicle still in intersection
                    blocker_id = obs_conflicts[0]
                    v.negotiation_outcome = "YIELD"
                    v.negotiation_partner_id = str(blocker_id)
                    v.reason_for_yield = f"Obstacle: V{blocker_id} still in intersection"
                    v.conflict_group = [vid]
                    v.negotiating_with = []
                    # Establish yield lock
                    if not v.v2v_yield_locked:
                        v.v2v_yield_locked = True
                        v.v2v_yield_partner_id = blocker_id
                        self.yield_locks[v.vehicle_id] = {
                            "winner_id": blocker_id,
                            "lock_time": current_time,
                        }
                        v.yield_hysteresis_timer = 0.4
                        self.yield_decisions += 1
                        print(f"[V2V-LOCK] Veh {v.vehicle_id} YIELD-LOCKED (obstacle Veh {blocker_id} in intersection)")
                    continue

                v.reservation_state = "CONFIRMED"
                v.reservation_entry_time = v.estimated_entry_time
                v.reservation_exit_time = v.estimated_exit_time
                self.confirmed_reservations[v.vehicle_id] = {
                    "entry_time": v.reservation_entry_time,
                    "exit_time": v.reservation_exit_time,
                    "route": v.route,
                    "lock_time": current_time
                }
                v.negotiation_outcome = None
                v.negotiation_partner_id = None
                v.conflict_group = [v.vehicle_id]
                v.negotiating_with = []
                v.reason_for_yield = ""
                if v.v2v_yield_locked:
                    v.v2v_yield_locked = False
                    v.v2v_yield_partner_id = None
                    self.yield_locks.pop(v.vehicle_id, None)
            else:
                # Local V2V negotiation inside the conflict group
                group_vehicles = [vehicle_by_id[vid] for vid in comp]
                
                # Fill local V2V awareness telemetry
                for v in group_vehicles:
                    v.conflict_group = sorted(list(comp))
                    v.negotiating_with = sorted([vid for vid in comp if vid != v.vehicle_id])

                # Priority sorting: confirmed first, then deterministic priority score
                def priority_key(veh):
                    is_confirmed = 0 if veh.reservation_state == "CONFIRMED" else 1
                    entry_t = veh.reservation_entry_time if veh.reservation_state == "CONFIRMED" else 0.0
                    return (is_confirmed, entry_t, -veh.negotiation_priority, veh.vehicle_id)

                group_vehicles.sort(key=priority_key)

                # Pairwise conflict resolution and reservation check
                for idx, v in enumerate(group_vehicles):
                    safety_gap = 1.5  # seconds
                    conflicting_winner = None

                    if v.reservation_state == "CONFIRMED":
                        # Existing confirmed reservation is locked and stable
                        v.negotiation_outcome = "PROCEED"
                        if v.v2v_yield_locked:
                            v.v2v_yield_locked = False
                            v.v2v_yield_partner_id = None
                            self.yield_locks.pop(v.vehicle_id, None)
                        continue

                    # Reset outcome for unconfirmed vehicles
                    v.negotiation_outcome = None
                    v.negotiation_partner_id = None
                    v.reason_for_yield = ""

                    # Check yield hysteresis first
                    has_hysteresis = False
                    if v.yield_hysteresis_timer > 0.0 and (v.v2v_yield_partner_id in candidate_ids or v.v2v_yield_partner_id in obstacle_ids):
                        partner_id = v.v2v_yield_partner_id
                        partner = vehicle_by_id[partner_id]
                        # Only keep yielding if partner conflicts and is still approaching/crossing
                        if v.route.conflicts_with(partner.route):
                            has_hysteresis = True
                            conflicting_winner = partner_id

                    has_overlap = has_hysteresis
                    if has_hysteresis:
                        v.reason_for_yield = f"Yield hysteresis active for partner V{conflicting_winner}"
                    else:
                        for other_id, res_info in self.confirmed_reservations.items():
                            if other_id == v.vehicle_id:
                                continue
                            if v.route.conflicts_with(res_info["route"]):
                                other_v = vehicle_by_id.get(other_id)
                                other_exit_t = res_info["exit_time"]
                                if other_v is not None and not intersection.is_fully_clear(other_v):
                                    other_exit_t = max(other_exit_t, current_time)
                                
                                overlap = not (v.estimated_exit_time + safety_gap < res_info["entry_time"] or
                                               other_exit_t + safety_gap < v.estimated_entry_time)
                                if overlap:
                                    has_overlap = True
                                    conflicting_winner = other_id
                                    break

                        # Also check against obstacles (crossing/exited vehicles in intersection)
                        if not has_overlap:
                            obs_conflicts = candidate_obstacle_map.get(v.vehicle_id, [])
                            if obs_conflicts:
                                has_overlap = True
                                conflicting_winner = obs_conflicts[0]
                                v.reason_for_yield = f"Obstacle: V{conflicting_winner} still in intersection"

                    if not has_overlap:
                        # Confirm reservation!
                        v.reservation_state = "CONFIRMED"
                        v.reservation_entry_time = v.estimated_entry_time
                        v.reservation_exit_time = v.estimated_exit_time
                        self.confirmed_reservations[v.vehicle_id] = {
                            "entry_time": v.reservation_entry_time,
                            "exit_time": v.reservation_exit_time,
                            "route": v.route,
                            "lock_time": current_time
                        }
                        v.negotiation_outcome = "PROCEED"
                        
                        # Find the highest priority conflicting vehicle in the group to list as partner
                        partner_id = None
                        for other in group_vehicles:
                            if other.vehicle_id != v.vehicle_id and v.route.conflicts_with(other.route):
                                partner_id = other.vehicle_id
                                break
                        v.negotiation_partner_id = str(partner_id) if partner_id is not None else None
                        v.reason_for_yield = ""
                        if v.v2v_yield_locked:
                            v.v2v_yield_locked = False
                            v.v2v_yield_partner_id = None
                            self.yield_locks.pop(v.vehicle_id, None)
                    else:
                        # Must yield!
                        v.negotiation_outcome = "YIELD"
                        v.negotiation_partner_id = str(conflicting_winner)
                        if not v.reason_for_yield:
                            v.reason_for_yield = f"Overlapping occupancy interval with confirmed V{conflicting_winner}"
                        
                        # Wait/delay times (Step 11 safety verification)
                        res_info = self.confirmed_reservations.get(conflicting_winner)
                        if res_info:
                            shift = (res_info["exit_time"] + safety_gap) - v.estimated_entry_time
                            if shift > 0:
                                v.estimated_entry_time += shift
                                v.estimated_exit_time += shift

                        # Establish yield lock
                        if not v.v2v_yield_locked:
                            v.v2v_yield_locked = True
                            v.v2v_yield_partner_id = conflicting_winner
                            self.yield_locks[v.vehicle_id] = {
                                "winner_id": conflicting_winner,
                                "lock_time": current_time,
                            }
                            v.yield_hysteresis_timer = 0.4
                            self.yield_decisions += 1
                            print(f"[V2V-LOCK] Veh {v.vehicle_id} YIELD-LOCKED (yielding to Veh {conflicting_winner})")

                # Track active negotiation sessions and logs for conflicting pairs in this group
                for v in group_vehicles:
                    for other in group_vehicles:
                        if v.vehicle_id < other.vehicle_id and v.route.conflicts_with(other.route):
                            # Determine winner and yielding based on outcomes
                            winner_id, loser_id = None, None
                            if v.negotiation_outcome == "PROCEED" and other.negotiation_outcome == "YIELD":
                                winner_id, loser_id = v.vehicle_id, other.vehicle_id
                            elif other.negotiation_outcome == "PROCEED" and v.negotiation_outcome == "YIELD":
                                winner_id, loser_id = other.vehicle_id, v.vehicle_id
                            
                            if winner_id is not None:
                                self.negotiations_initiated += 1
                                self.successful_negotiations += 1
                                pair_key = frozenset({winner_id, loser_id})
                                current_resolved_pairs.add(pair_key)

                                if pair_key not in self.active_negotiations:
                                    self.active_negotiations[pair_key] = {
                                        "vehicle_a": winner_id,
                                        "vehicle_b": loser_id,
                                        "start_time": current_time,
                                        "logged_intent": True,
                                        "logged_priority": True,
                                        "logged_yield": True,
                                        "logged_proceed": True,
                                        "winner": winner_id,
                                        "yielding": loser_id,
                                        "priority_a": vehicle_by_id[winner_id].negotiation_priority,
                                        "priority_b": vehicle_by_id[loser_id].negotiation_priority
                                    }
                                    # Log INTENT messages
                                    self._add_log(f"Vehicle {winner_id} -> Vehicle {loser_id} : INTENT", current_time)
                                    self._add_log(f"Vehicle {loser_id} -> Vehicle {winner_id} : INTENT", current_time)
                                    # Log PRIORITY messages
                                    self._add_log(f"Vehicle {winner_id} -> Vehicle {loser_id} : PRIORITY", current_time)
                                    self._add_log(f"Vehicle {loser_id} -> Vehicle {winner_id} : PRIORITY", current_time)
                                    # Log yielding/proceeding outcome
                                    self._add_log(f"Vehicle {loser_id} yielding to Vehicle {winner_id}", current_time)
                                    self._add_log(f"Vehicle {winner_id} proceeding", current_time)

        # ── 7. Update FSM transitions to YIELDING ──────────────────────────────
        for v in candidates:
            if v.negotiation_outcome == "YIELD":
                if v.agent_state in (AgentState.NEGOTIATING, AgentState.APPROACHING, AgentState.WAITING):
                    # Use vehicle FSM method
                    v._transition_to(AgentState.YIELDING)
                    v.yielding_visual_timer = 1.5

        # ── 8. Broadcast V2V messages ─────────────────────────────────────────
        if message_bus is not None:
            self._broadcast_outcomes(candidates, message_bus, current_time)

        # ── 9. Clean up negotiations that are no longer active ────────────────
        for pair_key in list(self.active_negotiations.keys()):
            if pair_key not in current_resolved_pairs:
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
