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
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from vehicle import VehicleAgent, VehicleState, AgentState
    from direction import Direction, Route
    from fourway_intersection import FourWayIntersection
    from communication import MessageBus

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

        # ── Simulation clock (deterministic, advances with dt) ────────────────
        self._sim_time: float = 0.0

        # ── Collision tracking ────────────────────────────────────────────────
        # Pairs that are currently overlapping (frozenset of two IDs).
        # A pair enters this set on first overlap and is counted once.
        self._active_collision_pairs: Set[FrozenSet[int]] = set()
        self.total_collisions: int = 0
        self._colliding_ids: Set[int] = set()

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
        # Use a monotonically advancing simulation clock instead of wall time.
        # This makes the arbiter deterministic and avoids timing-dependent races.
        self._sim_time += dt
        current_time = self._sim_time

        # ── V2V Communication Step ────────────────────────────────────────────
        # 1. Broadcasters: Each vehicle broadcasts its STATUS if interval is reached
        for vehicle in self.vehicles:
            if vehicle.state != VehicleState.COLLIDED:
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

        # 4. Clear message bus for the next tick
        self.message_bus.clear_processed()

        # 1. Tick collision freeze timers
        self._tick_collision_timers(dt)

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
                if vehicle.state != VehicleState.COLLIDED:
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

                # Skip if either is collided
                if (front.state == VehicleState.COLLIDED or
                        rear.state == VehicleState.COLLIDED):
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
        vid = vehicle.vehicle_id
        self._colliding_ids.discard(vid)

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

    def get_agent_state_counts(self) -> dict:
        """Return counts of agents in each state."""
        counts = {
            "approaching": 0,
            "negotiating": 0,
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
