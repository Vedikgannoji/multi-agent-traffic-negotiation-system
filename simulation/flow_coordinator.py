"""
flow_coordinator.py - Adaptive Flow-Aware Cooperative Negotiation (Phase 2.1).

Provides a fully decentralized flow coordination layer that allows compatible
vehicles to temporarily cooperate as a traffic flow.

Architecture:
  1. Flow Leader Election — After a negotiation winner gets PROCEED, promote
     that vehicle to flow leader and broadcast FLOW_ACTIVE.
  2. Follower Detection — Scan same-corridor vehicles behind the leader that
     are compatible, not in conflict, and at safe following distance.
  3. Adaptive Flow Window — Dynamically decide when to release the flow based
     on queue pressure, fairness, flow size, and remaining compatible followers.
  4. Fairness Guard — If any opposing vehicle has waited > 2× the corridor
     average, the flow is voluntarily released immediately.
  5. Flow Release — Leader broadcasts FLOW_RELEASED, all flow state is cleared,
     normal negotiation resumes on the next tick.

Integration:
  Runs AFTER the NegotiationEngine.evaluate() call, in the same tick.
  Never creates/removes yield locks — only the NegotiationEngine does.
  Never overrides existing YIELD outcomes — strictly additive.

Pure V2V Mode Only:
  Flow coordination is only active when control_mode == "pure_v2v".
"""

import sys
from pathlib import Path

try:
    from simulation.vehicle import VehicleAgent, AgentState
    from simulation.communication import VehicleMessage, MessageType
    from simulation.direction import Direction
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from vehicle import VehicleAgent, AgentState
    from communication import VehicleMessage, MessageType
    from direction import Direction


# ── Configuration ─────────────────────────────────────────────────────────────
MAX_FLOW_SIZE = 8           # Absolute safety cap on flow size
MIN_FOLLOWING_DIST = 20.0   # Minimum following distance for flow follower
MAX_FOLLOWING_DIST = 120.0  # Maximum distance from leader to still join flow
FLOW_ELIGIBLE_RANGE = 100.0 # Max distance from intersection to be flow-eligible
CONTINUE_THRESHOLD = 0.35   # Score threshold to continue flow

# Adaptive window weights (must sum to 1.0)
W_QUEUE_BALANCE = 0.30
W_FAIRNESS      = 0.35
W_SIZE_SCORE    = 0.20
W_MOMENTUM      = 0.15

# Fairness constants
FAIRNESS_WAIT_MULTIPLIER = 2.0   # Release if opponent waits > 2× corridor avg
FAIRNESS_MIN_DENOMINATOR = 5.0   # Floor for fairness denominator (seconds)

# ── Corridor helpers ──────────────────────────────────────────────────────────

def _corridor_key(source: str) -> str:
    """Return the corridor key for a direction (NS or EW)."""
    if source in (Direction.NORTH, Direction.SOUTH):
        return "NS"
    return "EW"


def _corridor_directions(corridor_key: str) -> list:
    """Return the directions belonging to a corridor."""
    if corridor_key == "NS":
        return [Direction.NORTH, Direction.SOUTH]
    return [Direction.EAST, Direction.WEST]


def _opposite_corridor_directions(corridor_key: str) -> list:
    """Return directions from the opposing corridor."""
    if corridor_key == "NS":
        return [Direction.EAST, Direction.WEST]
    return [Direction.NORTH, Direction.SOUTH]


def _is_compatible_follower(leader: VehicleAgent, candidate: VehicleAgent,
                            intersection) -> bool:
    """
    Check if a candidate vehicle is compatible to follow the leader:
      - Same corridor (NS vs EW)
      - Same direction of travel
      - Not yield-locked
      - Not in a terminal state
      - Not already a leader/follower of another flow
      - Within eligible distance of intersection
      - Behind the leader in the queue
    """
    # Same direction
    if candidate.route.source != leader.route.source:
        return False

    # Not locked or in terminal state
    if candidate.v2v_yield_locked:
        return False
    if candidate.agent_state in (AgentState.CROSSING, AgentState.EXITED,
                                  AgentState.COLLIDED):
        return False
    if getattr(candidate, 'has_exited_intersection', False):
        return False

    # Not already in a flow
    if candidate.flow_role is not None:
        return False

    # Must be in approach zone or close to intersection
    cx, cy = intersection.center_x, intersection.center_y
    if candidate.route.source in (Direction.NORTH, Direction.SOUTH):
        dist = abs(candidate.position - cy)
    else:
        dist = abs(candidate.position - cx)
    if dist > FLOW_ELIGIBLE_RANGE:
        return False

    # Must be behind the leader (farther from intersection)
    if leader.route.source in (Direction.NORTH, Direction.SOUTH):
        leader_dist = abs(leader.position - cy)
        cand_dist = abs(candidate.position - cy)
    else:
        leader_dist = abs(leader.position - cx)
        cand_dist = abs(candidate.position - cx)

    if cand_dist <= leader_dist:
        return False  # Not behind the leader

    # Following distance check
    separation = cand_dist - leader_dist
    if separation < MIN_FOLLOWING_DIST or separation > MAX_FOLLOWING_DIST:
        return False

    return True


class FlowCoordinator:
    """
    Adaptive Flow-Aware Cooperative Negotiation coordinator.

    Called once per simulation tick, immediately after the NegotiationEngine.
    Manages flow leader election, follower acceptance, adaptive window
    scoring, and flow release.

    Fully decentralized — all decisions emerge from V2V message exchange.
    """

    def __init__(self):
        # Active flow state
        self.active_flow = None  # dict: leader_id, corridor, followers, start_time, ...

        # Event log for dashboard (ring buffer)
        self.flow_event_log: list = []

        # Cumulative metrics
        self.total_flows_started: int = 0
        self.total_flows_released: int = 0
        self.total_flow_continuations: int = 0
        self.total_flow_vehicles: int = 0
        self.total_flow_duration: float = 0.0
        self._completed_flow_count: int = 0

    def reset(self):
        """Reset all flow coordination state."""
        self.active_flow = None
        self.flow_event_log.clear()
        self.total_flows_started = 0
        self.total_flows_released = 0
        self.total_flow_continuations = 0
        self.total_flow_vehicles = 0
        self.total_flow_duration = 0.0
        self._completed_flow_count = 0

    def _add_event(self, vehicle_id: int, event: str, timestamp: float,
                   detail: str = ""):
        """Add a flow event to the live log (ring buffer of 50)."""
        self.flow_event_log.append({
            "timestamp": round(timestamp, 2),
            "vehicle_id": vehicle_id,
            "event": event,
            "detail": detail
        })
        if len(self.flow_event_log) > 50:
            self.flow_event_log.pop(0)

    # ══════════════════════════════════════════════════════════════════════════
    # MAIN ENTRY POINT
    # ══════════════════════════════════════════════════════════════════════════

    def evaluate(self, vehicles: list, intersection, negotiation_engine,
                 message_bus, current_time: float):
        """
        Run one tick of flow coordination (called after negotiation).

        Steps:
          1. Clean up stale flows (leader exited/collided).
          2. If no active flow, attempt to elect a new flow leader.
          3. If active flow, evaluate adaptive window (continue or release).
          4. If continuing, attempt to accept new followers.
          5. Broadcast appropriate V2V messages.
        """
        # Build vehicle lookup
        veh_by_id = {v.vehicle_id: v for v in vehicles}

        # ── 1. Clean up stale flows ───────────────────────────────────────────
        if self.active_flow is not None:
            leader = veh_by_id.get(self.active_flow["leader_id"])
            should_cleanup = False

            if leader is None:
                should_cleanup = True
            elif leader.agent_state in (AgentState.COLLIDED, AgentState.EXITED):
                should_cleanup = True
            elif leader.has_exited_intersection:
                should_cleanup = True
            elif leader.v2v_yield_locked:
                # Safety: leader got yield-locked — release flow immediately
                should_cleanup = True

            if should_cleanup:
                self._release_flow(vehicles, veh_by_id, message_bus,
                                   current_time, reason="leader_unavailable")
                # After cleanup, fall through to try electing a new leader

        # ── 2. No active flow — try to elect a leader ─────────────────────────
        if self.active_flow is None:
            self._try_elect_leader(vehicles, intersection, negotiation_engine,
                                   message_bus, current_time)
            return

        # ── 3. Adaptive window: should we continue or release? ────────────────
        if not self._should_continue_flow(vehicles, intersection, current_time):
            self._release_flow(vehicles, veh_by_id, message_bus,
                               current_time, reason="adaptive_release")
            return

        # ── 4. Accept new followers ───────────────────────────────────────────
        self._accept_followers(vehicles, veh_by_id, intersection,
                               message_bus, current_time)

        # ── 5. Clean up followers that have crossed/exited ────────────────────
        self._prune_completed_followers(vehicles, veh_by_id, current_time)

    # ══════════════════════════════════════════════════════════════════════════
    # LEADER ELECTION
    # ══════════════════════════════════════════════════════════════════════════

    def _try_elect_leader(self, vehicles: list, intersection,
                          negotiation_engine, message_bus,
                          current_time: float):
        """
        Elect a flow leader from vehicles that won negotiation (PROCEED).

        Criteria:
          - Has negotiation_outcome == "PROCEED"
          - Not yield-locked
          - Not already in a flow
          - In approach zone or negotiation zone
          - Has at least one compatible follower available
        """
        # Find PROCEED winners
        candidates = []
        for v in vehicles:
            if v.negotiation_outcome != "PROCEED":
                continue
            if v.v2v_yield_locked:
                continue
            if v.flow_role is not None:
                continue
            if v.agent_state in (AgentState.CROSSING, AgentState.EXITED,
                                  AgentState.COLLIDED):
                continue
            if v.has_exited_intersection:
                continue
            candidates.append(v)

        if not candidates:
            return

        # Pick the candidate with highest negotiation priority
        candidates.sort(key=lambda v: v.negotiation_priority, reverse=True)
        leader = candidates[0]

        # Check if there are compatible followers available
        corridor = _corridor_key(leader.route.source)
        has_followers = any(
            _is_compatible_follower(leader, v, intersection)
            for v in vehicles if v.vehicle_id != leader.vehicle_id
        )

        if not has_followers:
            return  # No point starting a flow with no followers

        # ── Elect this vehicle as flow leader ──────────────────────────────────
        leader.flow_role = "leader"
        leader.flow_leader_id = leader.vehicle_id
        leader.flow_corridor = corridor
        leader.flow_follower_ids = []
        leader.flow_join_time = current_time

        self.active_flow = {
            "leader_id": leader.vehicle_id,
            "corridor": corridor,
            "direction": leader.route.source,
            "followers": [],
            "start_time": current_time,
            "vehicles_through": 0,
        }

        self.total_flows_started += 1
        self.total_flow_vehicles += 1  # Count the leader

        # Broadcast FLOW_ACTIVE
        flow_msg = VehicleMessage(
            sender_id=leader.agent_id,
            timestamp=current_time,
            message_type=MessageType.FLOW_ACTIVE,
            payload={
                "corridor": corridor,
                "direction": leader.route.source,
                "leader_id": leader.vehicle_id,
            }
        )
        message_bus.broadcast(flow_msg)

        self._add_event(leader.vehicle_id, "FLOW_STARTED", current_time,
                        f"Corridor: {corridor}, Dir: {leader.route.source}")
        print(f"[FLOW] Vehicle {leader.vehicle_id} elected as flow leader "
              f"(corridor={corridor}, dir={leader.route.source})")

    # ══════════════════════════════════════════════════════════════════════════
    # FOLLOWER ACCEPTANCE
    # ══════════════════════════════════════════════════════════════════════════

    def _accept_followers(self, vehicles: list, veh_by_id: dict,
                          intersection, message_bus, current_time: float):
        """
        Scan for compatible followers and accept them into the active flow.
        """
        flow = self.active_flow
        if flow is None:
            return

        leader = veh_by_id.get(flow["leader_id"])
        if leader is None:
            return

        current_size = len(flow["followers"]) + 1  # +1 for leader
        if current_size >= MAX_FLOW_SIZE:
            return  # Safety cap reached

        for v in vehicles:
            if v.vehicle_id == leader.vehicle_id:
                continue
            if v.vehicle_id in flow["followers"]:
                continue
            if current_size >= MAX_FLOW_SIZE:
                break

            if _is_compatible_follower(leader, v, intersection):
                # Accept follower
                v.flow_role = "follower"
                v.flow_leader_id = leader.vehicle_id
                v.flow_corridor = flow["corridor"]
                v.flow_join_time = current_time

                flow["followers"].append(v.vehicle_id)
                leader.flow_follower_ids.append(v.vehicle_id)
                current_size += 1

                self.total_flow_continuations += 1
                self.total_flow_vehicles += 1

                # Broadcast FOLLOW_REQUEST (from follower)
                req_msg = VehicleMessage(
                    sender_id=v.agent_id,
                    timestamp=current_time,
                    message_type=MessageType.FOLLOW_REQUEST,
                    payload={
                        "leader_id": leader.vehicle_id,
                        "corridor": flow["corridor"],
                    }
                )
                message_bus.broadcast(req_msg)

                # Broadcast FOLLOW_ACCEPTED (from leader)
                acc_msg = VehicleMessage(
                    sender_id=leader.agent_id,
                    timestamp=current_time,
                    message_type=MessageType.FOLLOW_ACCEPTED,
                    payload={
                        "follower_id": v.vehicle_id,
                        "corridor": flow["corridor"],
                        "flow_size": current_size,
                    }
                )
                message_bus.broadcast(acc_msg)

                self._add_event(v.vehicle_id, "FOLLOW_REQUEST", current_time,
                                f"Leader: {leader.vehicle_id}")
                self._add_event(leader.vehicle_id, "FOLLOW_APPROVED",
                                current_time,
                                f"Follower: {v.vehicle_id}, Size: {current_size}")
                print(f"[FLOW] Vehicle {v.vehicle_id} joined flow "
                      f"(leader={leader.vehicle_id}, size={current_size})")

    # ══════════════════════════════════════════════════════════════════════════
    # PRUNE COMPLETED FOLLOWERS
    # ══════════════════════════════════════════════════════════════════════════

    def _prune_completed_followers(self, vehicles: list, veh_by_id: dict,
                                    current_time: float):
        """Remove followers that have crossed or exited from the active flow."""
        flow = self.active_flow
        if flow is None:
            return

        remaining = []
        for fid in flow["followers"]:
            follower = veh_by_id.get(fid)
            if follower is None:
                flow["vehicles_through"] += 1
                continue
            if follower.agent_state in (AgentState.EXITED, AgentState.COLLIDED):
                flow["vehicles_through"] += 1
                self._clear_vehicle_flow_state(follower)
                continue
            if follower.has_exited_intersection:
                flow["vehicles_through"] += 1
                self._clear_vehicle_flow_state(follower)
                continue
            remaining.append(fid)

        flow["followers"] = remaining

        # Update leader's follower list
        leader = veh_by_id.get(flow["leader_id"])
        if leader is not None:
            leader.flow_follower_ids = list(remaining)

    # ══════════════════════════════════════════════════════════════════════════
    # ADAPTIVE FLOW WINDOW
    # ══════════════════════════════════════════════════════════════════════════

    def _should_continue_flow(self, vehicles: list, intersection,
                               current_time: float) -> bool:
        """
        Dynamically decide whether to continue or release the active flow.

        Uses four factors:
          1. Queue balance — opposing queue pressure
          2. Fairness — max wait of opposing vehicles vs. corridor average
          3. Diminishing returns — flow size approaching cap
          4. Momentum — remaining compatible followers

        Returns True if the flow should continue, False if it should release.
        """
        flow = self.active_flow
        if flow is None:
            return False

        flow_duration = current_time - flow["start_time"]
        flow_size = len(flow["followers"]) + 1  # +1 for leader

        # ── Factor 1: Queue pressure from opposing directions ─────────────────
        own_dirs = _corridor_directions(flow["corridor"])
        opp_dirs = _opposite_corridor_directions(flow["corridor"])

        own_queue = sum(len(intersection.queues.get(d, [])) for d in own_dirs)
        opp_queue = sum(len(intersection.queues.get(d, [])) for d in opp_dirs)
        total_queue = own_queue + opp_queue

        if total_queue > 0:
            queue_balance = 1.0 - (opp_queue / total_queue)
        else:
            queue_balance = 1.0  # No opposition

        # ── Factor 2: Fairness — max wait of opposing vehicles ────────────────
        opp_waits = [v.waiting_time for v in vehicles
                     if v.route.source in opp_dirs
                     and v.waiting_time > 0
                     and v.agent_state not in (AgentState.CROSSING,
                                                AgentState.EXITED,
                                                AgentState.COLLIDED)]
        own_waits = [v.waiting_time for v in vehicles
                     if v.route.source in own_dirs
                     and v.waiting_time > 0
                     and v.agent_state not in (AgentState.CROSSING,
                                                AgentState.EXITED,
                                                AgentState.COLLIDED)]

        opp_max_wait = max(opp_waits) if opp_waits else 0.0
        own_avg_wait = (sum(own_waits) / len(own_waits)) if own_waits else 0.0

        # Immediate fairness release: starvation guard
        if opp_max_wait > FAIRNESS_WAIT_MULTIPLIER * max(own_avg_wait,
                                                          FAIRNESS_MIN_DENOMINATOR):
            print(f"[FLOW] Fairness guard triggered — opposing max wait "
                  f"{opp_max_wait:.1f}s > {FAIRNESS_WAIT_MULTIPLIER}× "
                  f"corridor avg {own_avg_wait:.1f}s")
            return False

        fairness_denom = max(own_avg_wait * FAIRNESS_WAIT_MULTIPLIER,
                              FAIRNESS_MIN_DENOMINATOR)
        fairness = 1.0 - min(opp_max_wait / fairness_denom, 1.0)

        # ── Factor 3: Diminishing returns on flow size ────────────────────────
        size_score = 1.0 - min(flow_size / MAX_FLOW_SIZE, 1.0)

        # ── Factor 4: Remaining compatible followers ──────────────────────────
        # Check if there are still eligible vehicles that could join
        leader_id = flow["leader_id"]
        veh_by_id = {v.vehicle_id: v for v in vehicles}
        leader = veh_by_id.get(leader_id)

        if leader is not None:
            remaining = sum(
                1 for v in vehicles
                if v.vehicle_id != leader_id
                and v.vehicle_id not in flow["followers"]
                and _is_compatible_follower(leader, v, intersection)
            )
        else:
            remaining = 0

        momentum = min(remaining / 3.0, 1.0)

        # ── Weighted combination ──────────────────────────────────────────────
        score = (W_QUEUE_BALANCE * queue_balance +
                 W_FAIRNESS * fairness +
                 W_SIZE_SCORE * size_score +
                 W_MOMENTUM * momentum)

        should_continue = score > CONTINUE_THRESHOLD

        # Also release if no followers remain AND leader has crossed
        if (not flow["followers"] and leader is not None and
                (leader.has_exited_intersection or
                 leader.agent_state in (AgentState.CROSSING, AgentState.EXITED))):
            should_continue = False

        return should_continue

    # ══════════════════════════════════════════════════════════════════════════
    # FLOW RELEASE
    # ══════════════════════════════════════════════════════════════════════════

    def _release_flow(self, vehicles: list, veh_by_id: dict,
                      message_bus, current_time: float,
                      reason: str = ""):
        """Release the active flow and clear all flow state on vehicles."""
        flow = self.active_flow
        if flow is None:
            return

        leader_id = flow["leader_id"]
        duration = current_time - flow["start_time"]
        flow_size = len(flow["followers"]) + 1

        # Clear all vehicle flow states
        leader = veh_by_id.get(leader_id)
        if leader is not None:
            # Broadcast FLOW_RELEASED
            rel_msg = VehicleMessage(
                sender_id=leader.agent_id,
                timestamp=current_time,
                message_type=MessageType.FLOW_RELEASED,
                payload={
                    "corridor": flow["corridor"],
                    "flow_size": flow_size,
                    "duration": round(duration, 2),
                    "reason": reason,
                }
            )
            message_bus.broadcast(rel_msg)
            self._clear_vehicle_flow_state(leader)

        for fid in flow["followers"]:
            follower = veh_by_id.get(fid)
            if follower is not None:
                self._clear_vehicle_flow_state(follower)

        # Update metrics
        self.total_flows_released += 1
        self.total_flow_duration += duration
        self._completed_flow_count += 1

        self._add_event(leader_id, "FLOW_RELEASED", current_time,
                        f"Size: {flow_size}, Duration: {duration:.1f}s, "
                        f"Reason: {reason}")
        print(f"[FLOW] Flow released (leader={leader_id}, size={flow_size}, "
              f"duration={duration:.1f}s, reason={reason})")

        self.active_flow = None

    @staticmethod
    def _clear_vehicle_flow_state(vehicle: VehicleAgent):
        """Clear all flow-related state on a vehicle."""
        vehicle.flow_role = None
        vehicle.flow_leader_id = None
        vehicle.flow_corridor = None
        vehicle.flow_follower_ids = []
        vehicle.flow_join_time = None

    # ══════════════════════════════════════════════════════════════════════════
    # STATE & METRICS FOR API / DASHBOARD
    # ══════════════════════════════════════════════════════════════════════════

    def get_flow_state(self) -> dict:
        """Return current active flow state for API/dashboard."""
        if self.active_flow is None:
            return {
                "active": False,
                "corridor": None,
                "direction": None,
                "leader_id": None,
                "follower_count": 0,
                "follower_ids": [],
                "duration": 0.0,
                "vehicles_through": 0,
            }
        flow = self.active_flow
        return {
            "active": True,
            "corridor": flow["corridor"],
            "direction": flow["direction"],
            "leader_id": flow["leader_id"],
            "follower_count": len(flow["followers"]),
            "follower_ids": list(flow["followers"]),
            "duration": 0.0,  # Will be computed by caller with current_time
            "vehicles_through": flow["vehicles_through"],
        }

    def get_flow_metrics(self) -> dict:
        """Return aggregate flow metrics for dashboard."""
        avg_size = 0.0
        avg_duration = 0.0
        if self._completed_flow_count > 0:
            avg_size = self.total_flow_vehicles / self._completed_flow_count
            avg_duration = self.total_flow_duration / self._completed_flow_count

        return {
            "total_flows_started": self.total_flows_started,
            "total_flows_released": self.total_flows_released,
            "total_flow_continuations": self.total_flow_continuations,
            "total_flow_vehicles": self.total_flow_vehicles,
            "avg_flow_size": round(avg_size, 2),
            "avg_flow_duration": round(avg_duration, 2),
            "active_flow": self.active_flow is not None,
        }

    def get_queue_lengths(self, intersection) -> dict:
        """Return per-direction queue lengths for dashboard."""
        return {
            d: len(intersection.queues.get(d, []))
            for d in Direction.all()
        }
