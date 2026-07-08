"""
fourway_traffic_manager.py - Traffic management with direction-aware movement,
strict following distance, and persistent collision handling.
"""

import sys
import random
import time
from pathlib import Path
from typing import Set, FrozenSet, Dict, Tuple

try:
    from simulation.vehicle import VehicleAgent, VehicleState, AgentState
    from simulation.direction import Direction, Route
    from simulation.fourway_intersection import FourWayIntersection
    from simulation.communication import MessageBus
    from simulation.negotiation import NegotiationEngine
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from vehicle import VehicleAgent, VehicleState, AgentState
    from direction import Direction, Route
    from fourway_intersection import FourWayIntersection
    from communication import MessageBus
    from negotiation import NegotiationEngine

# ── Vehicle dimensions (simulation metres, matching SVG pixels 1:1) ──────────
# SVG car rect: width=12, height=24.  Position is the centre of the car.
VEHICLE_W = 12.0   # full width  (perpendicular to travel)
VEHICLE_L = 24.0   # full length (along travel axis)

# Lane offsets in SVG: North/South ±12 px from road centre, East/West ±12 px
LANE_OFFSET = 12.0

# ── Collision detection ───────────────────────────────────────────────────────
# Use slightly smaller boxes than the full car to avoid false positives from
# vehicles that are merely adjacent in the same lane.
COLL_HALF_W = VEHICLE_W / 2 * 0.85   # ~5.1 m
COLL_HALF_L = VEHICLE_L / 2 * 0.85   # ~10.2 m

# Only check collisions when both vehicles are inside (or very near) the
# intersection zone.  This prevents false positives from same-lane queueing.
COLLISION_ZONE_MARGIN = 20.0   # metres beyond intersection boundary

# How long a collided vehicle stays frozen before being removed (seconds)
COLLISION_FREEZE_DURATION = 2.5

# ── Spawn / following constants ───────────────────────────────────────────────
SPAWN_CLEAR_WINDOW = 35.0   # metres — only check this close to spawn point

# Safe following distances (centre-to-centre).
# VEHICLE_L = 24 m, so minimum safe gap = 24 + buffer.
FOLLOW_MIN_GAP    = VEHICLE_L + 8.0    # 32 m — absolute minimum (emergency brake)
FOLLOW_SAFE_GAP   = VEHICLE_L + 20.0   # 44 m — comfortable following
FOLLOW_CAUTION_GAP = VEHICLE_L + 35.0  # 59 m — start easing off

MIN_DESIRED_SPEED  = 10.0   # m/s
MAX_DESIRED_SPEED  = 18.0   # m/s
ABSOLUTE_MAX_SPEED = 22.0   # m/s


class FourWayTrafficManager:
    """
    Manages all vehicles with:
    - Direction-aware movement
    - Strict following distance (no bumper stacking)
    - Persistent collision state (COLLIDED vehicles freeze then are removed)
    - Accurate crossing / safety metrics
    """

    def __init__(self, intersection: FourWayIntersection, road_length: float = 500.0):
        self.intersection = intersection
        self.road_length  = road_length
        self.vehicles: list[VehicleAgent] = []
        self._next_id = 1
        self.message_bus  = MessageBus()
        self.negotiation_engine = NegotiationEngine()

        cx = intersection.center_x
        cy = intersection.center_y
        rl = road_length / 2

        self.spawn_positions = {
            Direction.NORTH: cy + rl,
            Direction.SOUTH: cy - rl,
            Direction.EAST:  cx - rl,
            Direction.WEST:  cx + rl,
        }

        self.exit_thresholds = {
            Direction.NORTH: cy - rl,
            Direction.SOUTH: cy + rl,
            Direction.EAST:  cx + rl,
            Direction.WEST:  cx - rl,
        }

        # ── Counters ──────────────────────────────────────────────────────────
        self.total_spawned  = 0
        self.total_removed  = 0

        # ── V2V Statistics ────────────────────────────────────────────────────
        self.total_messages_sent = 0
        self.total_messages_received = 0

        # ── Simulation clock (deterministic, advances with dt) ────────────────
        self._sim_time: float = 0.0

        # ── Collision tracking ────────────────────────────────────────────────
        # Pairs that are currently overlapping (frozenset of two IDs).
        # A pair enters this set on first overlap and is counted once.
        self._active_collision_pairs: Set[FrozenSet[int]] = set()
        self.total_collisions: int = 0
        self._colliding_ids: Set[int] = set()

        # ── Control Mode and Extra Observability Metrics ────────────────────────
        self.control_mode = "assisted"  # "assisted" or "pure_v2v"
        self.messages_per_second = 0.0
        self.total_yield_duration = 0.0
        self.completed_yield_count = 0

    # ── Spawn helpers ─────────────────────────────────────────────────────────

    def can_spawn_at_direction(self, direction: str) -> bool:
        spawn_pos = self.spawn_positions[direction]
        for v in self.vehicles:
            if v.route.source != direction:
                continue
            if abs(v.position - spawn_pos) < SPAWN_CLEAR_WINDOW:
                return False
        return True

    def spawn_vehicle(self, source: str = None, destination: str = None,
                      desired_speed: float = None) -> 'VehicleAgent | None':
        if source is None:
            available = [d for d in Direction.all() if self.can_spawn_at_direction(d)]
            if not available:
                return None
            source = random.choice(available)
        else:
            if not self.can_spawn_at_direction(source):
                return None

        if destination is None:
            destination = random.choice([d for d in Direction.all() if d != source])

        if desired_speed is None:
            desired_speed = random.uniform(MIN_DESIRED_SPEED, MAX_DESIRED_SPEED)

        vehicle = VehicleAgent(
            vehicle_id    = self._next_id,
            route         = Route(source, destination),
            position      = self.spawn_positions[source],
            desired_speed = desired_speed,
            max_speed     = ABSOLUTE_MAX_SPEED,
        )
        self._next_id      += 1
        self.vehicles.append(vehicle)
        self.total_spawned += 1
        return vehicle

    # ── Main update ───────────────────────────────────────────────────────────

    def update(self, dt: float):
        # Record previous agent states to detect transitions out of YIELDING
        prev_states = {v.vehicle_id: v.agent_state for v in self.vehicles}

        # Use a monotonically advancing simulation clock instead of wall time.
        # This makes the arbiter deterministic and avoids timing-dependent races.
        self._sim_time += dt
        current_time = self._sim_time

        # ── V2V Communication Step ────────────────────────────────────────────
        # 1. Broadcasters: Each vehicle broadcasts its STATUS if interval is reached
        for vehicle in self.vehicles:
            if vehicle.state != VehicleState.COLLIDED:
                vehicle.has_grant = vehicle.vehicle_id in self.intersection.granted_vehicle_ids
                vehicle.broadcast_status(self.message_bus, current_time, interval=0.1)

        # 2. Receivers: Each vehicle receives messages and updates known_agents
        for vehicle in self.vehicles:
            if vehicle.state != VehicleState.COLLIDED:
                vehicle.receive_messages(
                    self.message_bus,
                    center_x=self.intersection.center_x,
                    center_y=self.intersection.center_y,
                    range_threshold=150.0
                )

        # 3. Prune exited or out-of-range vehicles from known_agents
        active_agents = {v.agent_id: v for v in self.vehicles}
        for vehicle in self.vehicles:
            if vehicle.state != VehicleState.COLLIDED:
                my_x, my_y = vehicle.get_2d_position(self.intersection.center_x, self.intersection.center_y)
                pruned_known = {}
                for aid, info in vehicle.known_agents.items():
                    if aid in active_agents:
                        sender = active_agents[aid]
                        sender_x, sender_y = sender.get_2d_position(self.intersection.center_x, self.intersection.center_y)
                        import math
                        dist = math.sqrt((my_x - sender_x) ** 2 + (my_y - sender_y) ** 2)
                        if dist <= 150.0:
                            pruned_known[aid] = info
                vehicle.known_agents = pruned_known

        # 3.5. Update vehicle awareness layer properties
        for vehicle in self.vehicles:
            if vehicle.state != VehicleState.COLLIDED:
                vehicle.update_awareness(
                    center_x=self.intersection.center_x,
                    center_y=self.intersection.center_y,
                    lane_offset=LANE_OFFSET
                )

        # 3.6. Negotiation Layer — cooperative decision making
        #      Runs AFTER awareness (needs neighbor data) and BEFORE the
        #      reservation arbiter (advisory only, does not affect grants).
        self.negotiation_engine.evaluate(
            self.vehicles,
            self.intersection,
            message_bus=self.message_bus,
            current_time=current_time
        )

        # 4. Calculate Messages Per Second before clearing message bus
        msgs_this_tick = len(self.message_bus.messages)
        tick_mps = msgs_this_tick / dt if dt > 0 else 0.0
        self.messages_per_second = 0.9 * self.messages_per_second + 0.1 * tick_mps

        # 4.5 Clear message bus for the next tick
        self.message_bus.clear_processed()

        # 1. Tick collision freeze timers
        self._tick_collision_timers(dt)

        if self.control_mode == "pure_v2v":
            # ══════════════════════════════════════════════════════════════════
            # PURE V2V MODE — Negotiation outcomes are the SOLE authority
            # for intersection access. No grants, no phases.
            # ══════════════════════════════════════════════════════════════════
            self.intersection.granted_vehicle_ids.clear()
            self.intersection.granted_vehicle_id = None

            # Sync vehicles_inside for yield lock release checks
            self.intersection.vehicles_inside = {
                v.vehicle_id for v in self.vehicles
                if self.intersection.is_in_intersection(v)
                and v.state != VehicleState.COLLIDED
            }

            for vehicle in self.vehicles:
                if vehicle.state == VehicleState.COLLIDED:
                    continue

                vid = vehicle.vehicle_id
                is_yield_locked = vehicle.v2v_yield_locked

                # ── Fully cleared the intersection ────────────────────────
                if self.intersection.is_fully_clear(vehicle):
                    if not vehicle.has_exited_intersection:
                        vehicle.has_exited_intersection = True
                        self.intersection.total_crossings_completed += 1
                        if not vehicle.in_collision:
                            self.intersection.total_safe_crossings += 1
                    self.intersection.vehicles_inside.discard(vid)
                    self.intersection._dequeue(vehicle)
                    # Release any stale yield lock (safety)
                    if is_yield_locked:
                        vehicle.v2v_yield_locked = False
                        vehicle.v2v_yield_partner_id = None
                        self.negotiation_engine.yield_locks.pop(vid, None)
                    vehicle.set_state(VehicleState.MOVING)
                    vehicle.accelerate_to_desired()

                # ── Inside intersection — MUST continue crossing ──────────
                elif self.intersection.is_in_intersection(vehicle):
                    self.intersection.vehicles_inside.add(vid)
                    vehicle.set_state(VehicleState.CROSSING)
                    vehicle.accelerate_to_desired()

                # ── Between stop line and intersection (point of no return) ─
                elif self.intersection.is_between_stop_and_intersection(vehicle):
                    vehicle.set_state(VehicleState.CROSSING)
                    vehicle.accelerate_to_desired()

                # ── Approach zone — THIS is where yield enforcement matters ─
                elif self.intersection.is_in_approach_zone(vehicle):
                    if is_yield_locked or vehicle.negotiation_outcome == "YIELD":
                        # YIELD: physically stop this vehicle
                        self.intersection._enqueue(vehicle)
                        vehicle.set_state(VehicleState.WAITING)
                        vehicle.stop(emergency=True)
                        # IMMEDIATE speed zeroing — don't wait for deceleration
                        vehicle.current_speed = 0.0
                        vehicle.target_speed = 0.0
                    else:
                        # PROCEED or no conflict — drive through
                        self.intersection._dequeue(vehicle)
                        vehicle.set_state(VehicleState.MOVING)
                        vehicle.accelerate_to_desired()

                # ── Before approach zone — normal driving ─────────────────
                else:
                    vehicle.set_state(VehicleState.MOVING)
                    vehicle.accelerate_to_desired()

            # ── Debug output (throttled to ~1 per second) ─────────────────
            if not hasattr(self, '_v2v_debug_timer'):
                self._v2v_debug_timer = 0.0
            self._v2v_debug_timer += dt
            if self._v2v_debug_timer >= 1.0:
                self._v2v_debug_timer = 0.0
                locked_vehicles = [v for v in self.vehicles
                                   if v.v2v_yield_locked and v.state != VehicleState.COLLIDED]
                proceeding_vehicles = [v for v in self.vehicles
                                       if v.negotiation_outcome == "PROCEED"
                                       and v.state != VehicleState.COLLIDED]
                if locked_vehicles or proceeding_vehicles:
                    print(f"[V2V-DEBUG] t={current_time:.1f} | "
                          f"locks={len(self.negotiation_engine.yield_locks)} | "
                          f"active_neg={len(self.negotiation_engine.active_negotiations)}")
                    for v in locked_vehicles:
                        stop_pos = self.intersection.get_stop_position(v.route.source)
                        print(f"  YIELD  Veh {v.vehicle_id}: spd={v.current_speed:.1f} "
                              f"pos={v.position:.1f} stop={stop_pos:.1f} "
                              f"locked={v.v2v_yield_locked} "
                              f"partner={v.v2v_yield_partner_id}")
                    for v in proceeding_vehicles:
                        in_int = self.intersection.is_in_intersection(v)
                        print(f"  PROCEED Veh {v.vehicle_id}: spd={v.current_speed:.1f} "
                              f"pos={v.position:.1f} "
                              f"in_intersection={in_int}")
        else:
            # Reservation Assisted (Default):
            # 2. Run the phase arbiter FIRST — it decides who gets the grant
            #    and rotates phases. Must happen before per-vehicle updates.
            self.intersection.run_arbiter(self.vehicles, dt, current_time)

            # 3. Per-vehicle intersection commands — skip COLLIDED vehicles
            for vehicle in self.vehicles:
                if vehicle.state == VehicleState.COLLIDED:
                    continue
                action = self.intersection.update_vehicle(vehicle, current_time)
                if action == 'stop':
                    vehicle.stop(emergency=True)   # emergency brake for inactive-phase vehicles
                elif action == 'slow':
                    vehicle.slow_to_speed(4.0)
                elif action in ('enter', 'cross', 'continue'):
                    vehicle.accelerate_to_desired()

        # 4. Car-following — skip COLLIDED vehicles
        self._enforce_following_distance()

        # 5. Update agent state machine for each vehicle
        for vehicle in self.vehicles:
            if vehicle.state != VehicleState.COLLIDED:
                is_inside = self.intersection.is_in_intersection(vehicle)
                vehicle.update_agent_state(
                    intersection_center_x=self.intersection.center_x,
                    intersection_center_y=self.intersection.center_y,
                    intersection_size=self.intersection.size,
                    is_inside_intersection=is_inside,
                    dt=dt
                )

        # 6. Physics sub-steps - reduced substep size for smoother motion at 60 Hz
        SUB_STEP = 0.0166  # ~1/60 second, matching the new tick rate
        steps    = max(1, round(dt / SUB_STEP))
        sub_dt   = dt / steps
        for _ in range(steps):
            for vehicle in self.vehicles:
                if vehicle.state == VehicleState.COLLIDED:
                    continue
                # Yield-locked vehicles must have ZERO movement — skip physics entirely
                if vehicle.v2v_yield_locked and self.control_mode == "pure_v2v":
                    continue
                self._move_vehicle(vehicle, sub_dt)

        # 6.5. HARD POSITION CLAMP — last line of defense against handover collisions.
        # Vehicles from the inactive corridor without grants are physically clamped
        # at the stop line. They CANNOT advance past it regardless of momentum.
        active_dirs = self.intersection._active_dirs()
        for vehicle in self.vehicles:
            if vehicle.state == VehicleState.COLLIDED:
                continue
            vid = vehicle.vehicle_id
            direction = vehicle.route.source
            has_grant = vid in self.intersection.granted_vehicle_ids

            # Clamp vehicles WITHOUT grants:
            #  - CLEARANCE: all non-granted vehicles clamped
            #  - DRAINING: all non-granted vehicles clamped (even draining corridor)
            #  - ACTIVE: only inactive corridor non-granted vehicles clamped
            should_clamp = False
            if self.intersection._handover_state == "CLEARANCE":
                if not has_grant:
                    should_clamp = True
            elif self.intersection._handover_state == "DRAINING":
                if not has_grant:
                    should_clamp = True
            elif direction not in active_dirs and not has_grant:
                should_clamp = True

            if self.control_mode == "pure_v2v":
                # In pure V2V mode, the reservation system's phase/grant logic
                # is disabled. Instead, clamp yield-LOCKED vehicles at the stop line.
                # Non-locked vehicles drive freely based on negotiation outcomes.
                should_clamp = vehicle.v2v_yield_locked

            # Exclude vehicles that have already crossed, are currently inside,
            # are between the stop line and intersection (already passed stop line),
            # or are otherwise committed to crossing.
            if (vehicle.has_exited_intersection or 
                self.intersection.is_in_intersection(vehicle) or
                self.intersection.is_between_stop_and_intersection(vehicle) or
                self.intersection.is_committed_to_cross(vehicle)):
                should_clamp = False

            if should_clamp:
                stop_pos = self.intersection.get_stop_position(direction)
                # Clamp position: vehicle cannot advance past stop line
                if direction == Direction.NORTH:
                    # North travels downward (decreasing y); stop_pos is above intersection
                    if vehicle.position < stop_pos:
                        vehicle.position = stop_pos
                        vehicle.current_speed = 0.0
                        vehicle.target_speed = 0.0
                elif direction == Direction.SOUTH:
                    # South travels upward (increasing y); stop_pos is below intersection
                    if vehicle.position > stop_pos:
                        vehicle.position = stop_pos
                        vehicle.current_speed = 0.0
                        vehicle.target_speed = 0.0
                elif direction == Direction.EAST:
                    # East travels rightward (increasing x); stop_pos is left of intersection
                    if vehicle.position > stop_pos:
                        vehicle.position = stop_pos
                        vehicle.current_speed = 0.0
                        vehicle.target_speed = 0.0
                else:  # WEST
                    # West travels leftward (decreasing x); stop_pos is right of intersection
                    if vehicle.position < stop_pos:
                        vehicle.position = stop_pos
                        vehicle.current_speed = 0.0
                        vehicle.target_speed = 0.0

        # 7. Collision detection (intersection zone only)
        self._detect_collisions()

        # 8. Remove vehicles that have exited or finished their collision freeze
        to_remove = [v for v in self.vehicles
                     if self._has_exited(v) or
                     (v.state == VehicleState.COLLIDED and v.collision_freeze_timer <= 0)]
        for v in to_remove:
            self._on_vehicle_exit(v)
        remove_ids = {v.vehicle_id for v in to_remove}
        before = len(self.vehicles)
        self.vehicles = [v for v in self.vehicles if v.vehicle_id not in remove_ids]
        self.total_removed += before - len(self.vehicles)

        # 9. Clean up stale collision pairs
        live_ids = {v.vehicle_id for v in self.vehicles}
        stale = {p for p in self._active_collision_pairs if not p.issubset(live_ids)}
        for pair in stale:
            self._active_collision_pairs.discard(pair)
            for vid in pair:
                if vid not in live_ids:
                    self._colliding_ids.discard(vid)

        # Track transitions out of YIELDING for active vehicles
        for vehicle in self.vehicles:
            prev = prev_states.get(vehicle.vehicle_id)
            if prev == AgentState.YIELDING and vehicle.agent_state != AgentState.YIELDING:
                self.total_yield_duration += vehicle.yielding_duration
                self.completed_yield_count += 1
                vehicle.yielding_duration = 0.0

    # ── Collision freeze timer ────────────────────────────────────────────────

    def _tick_collision_timers(self, dt: float):
        """Count down freeze timers for COLLIDED vehicles."""
        for v in self.vehicles:
            if v.state == VehicleState.COLLIDED and v.collision_freeze_timer > 0:
                v.collision_freeze_timer = max(0.0, v.collision_freeze_timer - dt)

    # ── Movement ──────────────────────────────────────────────────────────────

    def _move_vehicle(self, vehicle: VehicleAgent, dt: float):
        self._update_speed(vehicle, dt)
        delta = vehicle.current_speed * dt
        if vehicle.route.source in (Direction.NORTH, Direction.WEST):
            vehicle.position -= delta
        else:
            vehicle.position += delta

    @staticmethod
    def _update_speed(vehicle: VehicleAgent, dt: float):
        diff = vehicle.target_speed - vehicle.current_speed
        if abs(diff) < 0.05:
            vehicle.current_speed = vehicle.target_speed
            return
        if diff > 0:
            change = VehicleAgent.MAX_ACCELERATION * dt
            vehicle.current_speed = min(vehicle.current_speed + change, vehicle.target_speed)
        else:
            rate   = VehicleAgent.EMERGENCY_DECELERATION if vehicle.is_emergency_braking else VehicleAgent.MAX_DECELERATION
            change = rate * dt
            vehicle.current_speed = max(vehicle.current_speed - change, vehicle.target_speed)
        vehicle.current_speed = max(0.0, min(vehicle.current_speed, vehicle.max_speed))

    # ── Following distance ────────────────────────────────────────────────────

    def _enforce_following_distance(self):
        """
        Strict car-following: vehicles maintain at least FOLLOW_MIN_GAP
        centre-to-centre distance.  Uses proportional speed reduction so
        braking is smooth, not abrupt.
        
        Includes hysteresis to prevent rapid oscillation between states.
        """
        by_dir = self.get_vehicles_by_direction()

        for direction, vehicles in by_dir.items():
            if len(vehicles) < 2:
                continue

            # Sort front-to-back (index 0 = furthest ahead)
            reverse = direction in (Direction.SOUTH, Direction.EAST)
            vehicles.sort(key=lambda v: v.position, reverse=reverse)

            for i in range(len(vehicles) - 1):
                front = vehicles[i]
                rear  = vehicles[i + 1]

                # Skip if rear is collided (no control)
                if rear.state == VehicleState.COLLIDED:
                    continue

                dist = abs(front.position - rear.position)

                # Add hysteresis: if already braking, use slightly larger thresholds
                # to prevent rapid oscillation
                is_braking = rear.target_speed < rear.desired_speed * 0.9
                hysteresis = 2.0 if is_braking else 0.0

                if dist < FOLLOW_MIN_GAP:
                    # Emergency stop — too close
                    rear.stop(emergency=True)
                elif dist < FOLLOW_SAFE_GAP + hysteresis:
                    # Match front speed, scaled by how close we are
                    ratio = (dist - FOLLOW_MIN_GAP) / (FOLLOW_SAFE_GAP - FOLLOW_MIN_GAP)
                    ratio = max(0.0, min(1.0, ratio))
                    safe_speed = front.current_speed * (0.5 + 0.4 * ratio)
                    safe_speed = min(safe_speed, rear.desired_speed * 0.7)
                    if safe_speed < rear.target_speed:
                        rear.set_target_speed(safe_speed)
                elif dist < FOLLOW_CAUTION_GAP + hysteresis:
                    # Ease off slightly, but do not exceed intersection's target speed
                    ratio = (dist - FOLLOW_SAFE_GAP) / (FOLLOW_CAUTION_GAP - FOLLOW_SAFE_GAP)
                    ratio = max(0.0, min(1.0, ratio))
                    safe_speed = rear.desired_speed * (0.8 + 0.15 * ratio)
                    # Only reduce speed, never increase beyond what intersection set
                    if safe_speed < rear.target_speed:
                        rear.set_target_speed(safe_speed)

    # ── Collision detection ───────────────────────────────────────────────────

    def _get_aabb(self, vehicle: VehicleAgent) -> Tuple[float, float, float, float]:
        """
        Compute AABB for a vehicle in simulation-space coordinates.
        Uses slightly-shrunk boxes (COLL_HALF_W / COLL_HALF_L) to avoid
        false positives from vehicles that are merely adjacent.
        """
        cx  = self.intersection.center_x
        cy  = self.intersection.center_y
        src = vehicle.route.source
        pos = vehicle.position

        if src == Direction.NORTH:
            cx_v, cy_v = cx - LANE_OFFSET, pos
            return (cx_v - COLL_HALF_W, cy_v - COLL_HALF_L,
                    cx_v + COLL_HALF_W, cy_v + COLL_HALF_L)
        elif src == Direction.SOUTH:
            cx_v, cy_v = cx + LANE_OFFSET, pos
            return (cx_v - COLL_HALF_W, cy_v - COLL_HALF_L,
                    cx_v + COLL_HALF_W, cy_v + COLL_HALF_L)
        elif src == Direction.EAST:
            cx_v, cy_v = pos, cy - LANE_OFFSET
            return (cx_v - COLL_HALF_L, cy_v - COLL_HALF_W,
                    cx_v + COLL_HALF_L, cy_v + COLL_HALF_W)
        else:  # WEST
            cx_v, cy_v = pos, cy + LANE_OFFSET
            return (cx_v - COLL_HALF_L, cy_v - COLL_HALF_W,
                    cx_v + COLL_HALF_L, cy_v + COLL_HALF_W)

    def _is_near_intersection(self, vehicle: VehicleAgent) -> bool:
        """
        Return True only when the vehicle is inside or very close to the
        intersection zone.  Collision detection is restricted to this area
        to prevent false positives from same-lane queueing.
        """
        cx  = self.intersection.center_x
        cy  = self.intersection.center_y
        sz  = self.intersection.size / 2 + COLLISION_ZONE_MARGIN
        pos = vehicle.position
        src = vehicle.route.source

        if src in (Direction.NORTH, Direction.SOUTH):
            return abs(pos - cy) <= sz
        else:
            return abs(pos - cx) <= sz

    @staticmethod
    def _are_cross_corridor(va: VehicleAgent, vb: VehicleAgent) -> bool:
        """Check if two vehicles are from perpendicular corridors (NS vs EW)."""
        ns_dirs = {Direction.NORTH, Direction.SOUTH}
        ew_dirs = {Direction.EAST, Direction.WEST}
        a_ns = va.route.source in ns_dirs
        b_ns = vb.route.source in ns_dirs
        return a_ns != b_ns  # One is NS, other is EW

    @staticmethod
    def _aabb_overlap(a: Tuple[float, float, float, float],
                      b: Tuple[float, float, float, float]) -> bool:
        return (a[0] < b[2] and a[2] > b[0] and
                a[1] < b[3] and a[3] > b[1])

    def _detect_collisions(self):
        """
        AABB collision detection restricted to the intersection zone.
        
        CROSS-CORRIDOR SAFETY: For vehicles from perpendicular corridors
        (NS vs EW), both must be physically inside the intersection for
        a collision to be flagged. This prevents false positives from
        vehicles correctly stopped just outside the boundary whose AABBs
        slightly overlap due to lane offset geometry.
        """
        # Only consider vehicles near the intersection
        candidates = [v for v in self.vehicles if self._is_near_intersection(v)]
        n = len(candidates)

        if n < 2:
            return

        boxes = {v.vehicle_id: self._get_aabb(v) for v in candidates}
        currently_overlapping: Set[FrozenSet[int]] = set()

        for i in range(n):
            for j in range(i + 1, n):
                va   = candidates[i]
                vb   = candidates[j]

                # Skip pairs where both are already in COLLIDED state
                if (va.state == VehicleState.COLLIDED and
                        vb.state == VehicleState.COLLIDED):
                    continue

                # CROSS-CORRIDOR FILTER: For perpendicular corridor pairs,
                # only flag collision when BOTH are inside the intersection.
                # A vehicle stopped just outside the boundary is safe even if
                # its AABB barely overlaps with a crossing vehicle's AABB.
                if self._are_cross_corridor(va, vb):
                    a_inside = self.intersection.is_in_intersection(va)
                    b_inside = self.intersection.is_in_intersection(vb)
                    if not (a_inside and b_inside):
                        continue

                pair = frozenset((va.vehicle_id, vb.vehicle_id))

                if self._aabb_overlap(boxes[va.vehicle_id], boxes[vb.vehicle_id]):
                    currently_overlapping.add(pair)

                    if pair not in self._active_collision_pairs:
                        # ── New collision event ──────────────────────────────
                        self._active_collision_pairs.add(pair)
                        self.total_collisions += 1

                        # ── Capture detailed collision diagnostics ───────────
                        import json
                        diag_file = "collision_diagnostics.txt"
                        
                        diag_info = {
                            "timestamp_sim": round(self._sim_time, 2),
                            "timestamp_real": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                            "vehicle_a": {
                                "id": va.vehicle_id,
                                "source": va.route.source,
                                "destination": va.route.destination,
                                "position": round(va.position, 2),
                                "speed": round(va.current_speed, 2),
                                "agent_state": va.agent_state.value if hasattr(va.agent_state, 'value') else str(va.agent_state),
                                "priority_score": round(va.negotiation_priority, 4),
                                "yield_locked": va.v2v_yield_locked,
                                "yield_partner": va.v2v_yield_partner_id,
                                "negotiation_outcome": va.negotiation_outcome,
                                "has_grant": va.vehicle_id in self.intersection.granted_vehicle_ids
                            },
                            "vehicle_b": {
                                "id": vb.vehicle_id,
                                "source": vb.route.source,
                                "destination": vb.route.destination,
                                "position": round(vb.position, 2),
                                "speed": round(vb.current_speed, 2),
                                "agent_state": vb.agent_state.value if hasattr(vb.agent_state, 'value') else str(vb.agent_state),
                                "priority_score": round(vb.negotiation_priority, 4),
                                "yield_locked": vb.v2v_yield_locked,
                                "yield_partner": vb.v2v_yield_partner_id,
                                "negotiation_outcome": vb.negotiation_outcome,
                                "has_grant": vb.vehicle_id in self.intersection.granted_vehicle_ids
                            },
                            "active_negotiations": [
                                {
                                    "vehicle_a": data["vehicle_a"],
                                    "vehicle_b": data["vehicle_b"],
                                    "winner": data.get("winner"),
                                    "yielding": data.get("yielding"),
                                    "priority_a": round(data["priority_a"], 2),
                                    "priority_b": round(data["priority_b"], 2),
                                    "age": round(self._sim_time - data["start_time"], 2)
                                }
                                for data in self.negotiation_engine.active_negotiations.values()
                            ],
                            "yield_locks": {
                                str(yid): {
                                    "winner_id": lock["winner_id"],
                                    "lock_time_sim": round(lock["lock_time"], 2)
                                }
                                for yid, lock in self.negotiation_engine.yield_locks.items()
                            }
                        }

                        report_lines = [
                            "=" * 80,
                            f"COLLISION DIAGNOSTIC EVENT - SIM TIME: {diag_info['timestamp_sim']}s - REAL TIME: {diag_info['timestamp_real']}",
                            "=" * 80,
                            f"Vehicle A: ID={diag_info['vehicle_a']['id']}, Dir={diag_info['vehicle_a']['source']}->{diag_info['vehicle_a']['destination']}",
                            f"  State={diag_info['vehicle_a']['agent_state']}, Position={diag_info['vehicle_a']['position']}m, Speed={diag_info['vehicle_a']['speed']}m/s",
                            f"  Priority={diag_info['vehicle_a']['priority_score']}, Yield Locked={diag_info['vehicle_a']['yield_locked']} (partner={diag_info['vehicle_a']['yield_partner']})",
                            f"  Outcome={diag_info['vehicle_a']['negotiation_outcome']}, Has Grant={diag_info['vehicle_a']['has_grant']}",
                            f"Vehicle B: ID={diag_info['vehicle_b']['id']}, Dir={diag_info['vehicle_b']['source']}->{diag_info['vehicle_b']['destination']}",
                            f"  State={diag_info['vehicle_b']['agent_state']}, Position={diag_info['vehicle_b']['position']}m, Speed={diag_info['vehicle_b']['speed']}m/s",
                            f"  Priority={diag_info['vehicle_b']['priority_score']}, Yield Locked={diag_info['vehicle_b']['yield_locked']} (partner={diag_info['vehicle_b']['yield_partner']})",
                            f"  Outcome={diag_info['vehicle_b']['negotiation_outcome']}, Has Grant={diag_info['vehicle_b']['has_grant']}",
                            f"Active Negotiations: {json.dumps(diag_info['active_negotiations'])}",
                            f"Active Yield Locks: {json.dumps(diag_info['yield_locks'])}",
                            "=" * 80,
                            ""
                        ]
                        report_text = "\n".join(report_lines)
                        print(report_text)
                        
                        try:
                            with open(diag_file, "a") as f:
                                f.write(report_text)
                        except Exception as ex:
                            print(f"[ERROR] Failed to write collision diagnostics: {ex}")

                        for v in (va, vb):
                            v.in_collision            = True
                            v.state                   = VehicleState.COLLIDED
                            v.agent_state             = AgentState.COLLIDED
                            v.current_speed           = 0.0
                            v.target_speed            = 0.0
                            v.collision_freeze_timer  = COLLISION_FREEZE_DURATION
                            self._colliding_ids.add(v.vehicle_id)

        # Remove pairs that are no longer overlapping
        separated = self._active_collision_pairs - currently_overlapping
        for pair in separated:
            self._active_collision_pairs.discard(pair)


    # ── Exit detection ────────────────────────────────────────────────────────

    def _on_vehicle_exit(self, vehicle: VehicleAgent):
        """Clean up vehicle data when it exits."""
        # Ensure the vehicle is transitioned to EXITED agent state
        vehicle.set_agent_state(AgentState.EXITED)
        
        vid = vehicle.vehicle_id
        self._colliding_ids.discard(vid)
        # Accumulate message metrics
        self.total_messages_sent += len(vehicle.message_outbox)
        self.total_messages_received += len(vehicle.message_inbox)
        
        # Accumulate yielding duration if exited while/after yielding
        if hasattr(vehicle, 'yielding_duration') and vehicle.yielding_duration > 0.0:
            self.total_yield_duration += vehicle.yielding_duration
            self.completed_yield_count += 1

        # Clean up V2V reservation
        self.negotiation_engine.confirmed_reservations.pop(vid, None)
        # Clean up yield locks: remove this vehicle's own lock
        self.negotiation_engine.yield_locks.pop(vid, None)
        # Also release any vehicle that was yielding TO this one (winner exited)
        locks_to_release = [yid for yid, info in self.negotiation_engine.yield_locks.items()
                            if info["winner_id"] == vid]
        for yid in locks_to_release:
            self.negotiation_engine.yield_locks.pop(yid, None)
            # Find and unlock the yielding vehicle
            for v in self.vehicles:
                if v.vehicle_id == yid:
                    v.v2v_yield_locked = False
                    v.v2v_yield_partner_id = None
                    v.negotiation_outcome = None
                    v.negotiation_partner_id = None
                    break

    def _has_exited(self, vehicle: VehicleAgent) -> bool:
        # COLLIDED vehicles are removed by their freeze timer, not by exit threshold
        if vehicle.state == VehicleState.COLLIDED:
            return False
        direction = vehicle.route.source
        pos       = vehicle.position
        threshold = self.exit_thresholds[direction]
        if direction == Direction.NORTH:
            return pos < threshold
        elif direction == Direction.SOUTH:
            return pos > threshold
        elif direction == Direction.EAST:
            return pos > threshold
        else:
            return pos < threshold

    # ── State serialisation ───────────────────────────────────────────────────

    def get_state(self) -> list[dict]:
        colliding = self._colliding_ids
        return [
            {
                "id":          v.vehicle_id,
                "source":      v.route.source,
                "destination": v.route.destination,
                "turn_type":   v.route.turn_type,
                "position":    round(v.position, 2),
                "speed":       round(v.current_speed, 2),
                "state":       v.state,  # Legacy state for compatibility
                "agent_state": v.agent_state.value,  # New agent state
                "waiting_time": round(v.waiting_time, 2),
                "priority":    round(v.priority, 2),
                "colliding":   v.vehicle_id in colliding,
                "neighbor_count": v.neighbor_count,
                "closest_vehicle_id": v.closest_vehicle_id,
                "closest_vehicle_distance": round(v.closest_vehicle_distance, 2) if v.closest_vehicle_distance != float('inf') else None,
                "average_neighbor_speed": round(v.average_neighbor_speed, 2),
                "local_density": round(v.local_density, 4),
                "vehicles_ahead_count": v.vehicles_ahead_count,
                "vehicles_behind_count": v.vehicles_behind_count,
                "nearby_approaching_agents": v.nearby_approaching_agents,
                "nearby_waiting_agents": v.nearby_waiting_agents,
                "nearby_crossing_agents": v.nearby_crossing_agents,
                "nearby_yielding_agents": v.nearby_yielding_agents,
                "nearby_negotiating_agents": v.nearby_negotiating_agents,
                "negotiation_priority": round(v.negotiation_priority, 4),
                "negotiation_outcome": v.negotiation_outcome,
                "v2v_yield_locked": v.v2v_yield_locked,
                "v2v_yield_partner_id": v.v2v_yield_partner_id,
                "conflict_group": getattr(v, "conflict_group", []),
                "reservation_state": getattr(v, "reservation_state", "NONE"),
                "eta": round(getattr(v, "estimated_entry_time", 0.0), 2),
                "reserved_time_window": [round(getattr(v, "reservation_entry_time", 0.0), 2), round(getattr(v, "reservation_exit_time", 0.0), 2)] if getattr(v, "reservation_state", "NONE") == "CONFIRMED" else None,
                "negotiating_with": getattr(v, "negotiating_with", []),
                "reason_for_yield": getattr(v, "reason_for_yield", ""),
            }
            for v in self.vehicles
        ]

    def get_safety_stats(self) -> dict:
        # Get accurate crossing counts from intersection
        safe_crossings = self.intersection.total_safe_crossings
        collisions = max(0, self.total_collisions)
        
        # Total attempts = successful crossings + collisions
        # This gives us the true pass/fail rate
        total_attempts = safe_crossings + collisions
        
        # Calculate passing accuracy: safe crossings as percentage of all attempts
        if total_attempts > 0:
            accuracy = round((safe_crossings / total_attempts) * 100.0, 1)
        else:
            accuracy = 100.0  # No attempts yet = perfect score
        
        accuracy = max(0.0, min(100.0, accuracy))

        return {
            "total_collisions":        collisions,
            "total_crossing_attempts": total_attempts,
            "total_safe_crossings":    safe_crossings,
            "total_failed_crossings":  collisions,  # Failed = collisions
            "safety_accuracy_pct":     accuracy,
            "currently_colliding":     len(self._active_collision_pairs),
            "deadlock_recoveries":     self.intersection.deadlock_recoveries,
        }

    def get_v2v_stats(self) -> dict:
        """Calculate and return aggregated V2V awareness metrics."""
        active_vehicles = self.vehicles
        num_active = len(active_vehicles)
        
        total_sent = self.total_messages_sent + sum(len(v.message_outbox) for v in active_vehicles)
        total_received = self.total_messages_received + sum(len(v.message_inbox) for v in active_vehicles)
        
        avg_neighbors = 0.0
        avg_density = 0.0
        avg_closest_dist = 0.0
        
        if num_active > 0:
            avg_neighbors = sum(v.neighbor_count for v in active_vehicles) / num_active
            avg_density = sum(v.local_density for v in active_vehicles) / num_active
            
            valid_dists = [v.closest_vehicle_distance for v in active_vehicles if v.neighbor_count > 0]
            if valid_dists:
                avg_closest_dist = sum(valid_dists) / len(valid_dists)
                
        # Neighbor-observation aggregates (summed observations across all active vehicles)
        obs_approaching = sum(v.nearby_approaching_agents for v in active_vehicles)
        obs_waiting = sum(v.nearby_waiting_agents for v in active_vehicles)
        obs_crossing = sum(v.nearby_crossing_agents for v in active_vehicles)
        obs_yielding = sum(v.nearby_yielding_agents for v in active_vehicles)

        # Actual vehicle counts by intent
        actual_approaching = sum(1 for v in active_vehicles if v.agent_state == AgentState.APPROACHING)
        actual_waiting = sum(1 for v in active_vehicles if v.agent_state == AgentState.WAITING)
        actual_crossing = sum(1 for v in active_vehicles if v.agent_state == AgentState.CROSSING)
        actual_negotiating = sum(1 for v in active_vehicles if v.agent_state == AgentState.NEGOTIATING)
        actual_yielding = sum(1 for v in active_vehicles if v.agent_state == AgentState.YIELDING)

        # Calculate durations for metrics
        avg_neg_dur = 0.0
        if self.negotiation_engine.completed_negotiation_count > 0:
            avg_neg_dur = self.negotiation_engine.total_negotiation_duration / self.negotiation_engine.completed_negotiation_count
            
        avg_yield_dur = 0.0
        if self.completed_yield_count > 0:
            avg_yield_dur = self.total_yield_duration / self.completed_yield_count

        return {
            "total_messages_sent": total_sent,
            "total_messages_received": total_received,
            "average_neighbors_per_vehicle": round(avg_neighbors, 2),
            "average_local_density": round(avg_density, 4),
            "average_closest_vehicle_distance": round(avg_closest_dist, 2),
            "total_approaching_agents": actual_approaching,
            "total_waiting_agents": actual_waiting,
            "total_crossing_agents": actual_crossing,
            "total_negotiating_agents": actual_negotiating,
            "total_yielding_agents": actual_yielding,
            "obs_approaching_agents": obs_approaching,
            "obs_waiting_agents": obs_waiting,
            "obs_crossing_agents": obs_crossing,
            "obs_yielding_agents": obs_yielding,
            "negotiations_initiated": self.negotiation_engine.negotiations_initiated,
            "successful_negotiations": self.negotiation_engine.successful_negotiations,
            "yield_decisions": self.negotiation_engine.yield_decisions,
            "active_negotiations": len(self.negotiation_engine.active_negotiations),
            "average_negotiation_duration": round(avg_neg_dur, 2),
            "average_yield_duration": round(avg_yield_dur, 2),
            "messages_per_second": round(self.messages_per_second, 1),
        }

    def get_agent_state_counts(self) -> dict:
        """Return counts of agents in each state."""
        counts = {
            "approaching": 0,
            "negotiating": 0,
            "yielding": 0,
            "waiting": 0,
            "crossing": 0,
            "exited": 0,
            "collided": 0,
        }
        for v in self.vehicles:
            counts[v.agent_state.value] += 1
        return counts

    def get_vehicles_by_direction(self) -> dict:
        by_dir = {d: [] for d in Direction.all()}
        for v in self.vehicles:
            by_dir[v.route.source].append(v)
        return by_dir

    def get_statistics(self) -> dict:
        return {
            "total_spawned":    self.total_spawned,
            "total_removed":    self.total_removed,
            "current_vehicles": len(self.vehicles),
        }

    def __repr__(self):
        return f"FourWayTrafficManager(vehicles={len(self.vehicles)})"
