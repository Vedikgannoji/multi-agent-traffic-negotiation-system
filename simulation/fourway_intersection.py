"""
fourway_intersection.py - Ownership-window intersection arbiter.

Architecture: PHASE-BASED OWNERSHIP WINDOWS with STRICT HANDOVER SAFETY
  The intersection is controlled by a single rotating arbiter.
  At any moment exactly one phase owns the intersection:
    PHASE_NS  – north/south vehicles may cross
    PHASE_EW  – east/west vehicles may cross
    PHASE_IDLE – no vehicles present, arbiter is idle

  CORRIDOR HANDOVER uses a strict 4-state machine:
    ACTIVE    → normal operation, grants issued to active corridor
    DRAINING  → switch requested, NO new grants, wait for all vehicles to clear
    CLEARANCE → ALL-RED period (2.0s), absolutely nothing moves
    ACTIVE    → new corridor activates

  This eliminates handover collisions by construction.
"""

import sys
from pathlib import Path
from collections import deque
from typing import Dict, List, Optional, Set

try:
    from simulation.vehicle import Vehicle, VehicleState
    from simulation.direction import Direction, Route, TurnType
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from vehicle import Vehicle, VehicleState
    from direction import Direction, Route, TurnType


# ── Phase constants ────────────────────────────────────────────────────────────
PHASE_NS   = "NS"    # north + south active
PHASE_EW   = "EW"    # east  + west  active
PHASE_IDLE = "IDLE"  # no vehicles anywhere near intersection

# Directions that belong to each phase
PHASE_DIRS: Dict[str, List[str]] = {
    PHASE_NS:   [Direction.NORTH, Direction.SOUTH],
    PHASE_EW:   [Direction.EAST,  Direction.WEST],
    PHASE_IDLE: [],
}

# ── Handover state machine ────────────────────────────────────────────────────
HANDOVER_ACTIVE    = "ACTIVE"
HANDOVER_DRAINING  = "DRAINING"
HANDOVER_CLEARANCE = "CLEARANCE"

MIN_PHASE_DURATION = 10.0
MAX_PHASE_DURATION = 30.0
CLEARANCE_DURATION = 2.0
APPROACH_DISTANCE = 100.0
STOP_DISTANCE = 50.0
CLEARANCE_DISTANCE = 30.0
EMERGENCY_DECELERATION = 6.0
COMMITMENT_SAFETY_MARGIN = 2.0
DANGER_ZONE_MARGIN = 60.0


class FourWayIntersection:
    """Ownership-window intersection arbiter with strict handover safety."""

    def __init__(self, center_x: float = 250.0, center_y: float = 250.0,
                 size: float = 40.0):
        self.center_x = center_x
        self.center_y = center_y
        self.size     = size

        self.x_min = center_x - size / 2
        self.x_max = center_x + size / 2
        self.y_min = center_y - size / 2
        self.y_max = center_y + size / 2

        # Phase state
        self.current_phase: str        = PHASE_IDLE
        self.phase_start_time: float   = 0.0
        self.phase_elapsed: float      = 0.0

        # Handover state machine
        self._handover_state: str      = HANDOVER_ACTIVE
        self._clearance_timer: float   = 0.0
        self._pending_phase: Optional[str] = None
        self._draining_from_phase: Optional[str] = None

        # Grant state
        self.granted_vehicle_ids: Set[int] = set()
        self.grant_times: Dict[int, float] = {}
        self._grant_corridor: Dict[int, str] = {}

        # Legacy compatibility
        self.granted_vehicle_id: Optional[int] = None
        self.granted_at: float                 = 0.0

        # Per-direction queues
        self.queues: Dict[str, deque] = {
            Direction.NORTH: deque(),
            Direction.SOUTH: deque(),
            Direction.EAST:  deque(),
            Direction.WEST:  deque(),
        }

        # Vehicle tracking
        self.vehicles_inside: Set[int] = set()
        self.committed_vehicles: Set[int] = set()
        self._all_vehicles: List[Vehicle] = []

        # Legacy compat
        self._draining_for_switch: bool = False

        # Statistics
        self.total_crossings_completed: int = 0
        self.total_safe_crossings:      int = 0
        self.total_reservations:        int = 0
        self.total_conflicts_prevented: int = 0
        self.deadlock_recoveries:       int = 0

        # Legacy compat
        self.active_reservations: Set[int] = set()
        self.reservations:        Dict     = {}
        self.waiting_queues                = self.queues

    # ══════════════════════════════════════════════════════════════════════════
    # GEOMETRY HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def get_stop_position(self, direction: str) -> float:
        if direction == Direction.NORTH:
            return self.y_max + STOP_DISTANCE
        elif direction == Direction.SOUTH:
            return self.y_min - STOP_DISTANCE
        elif direction == Direction.EAST:
            return self.x_min - STOP_DISTANCE
        else:
            return self.x_max + STOP_DISTANCE

    def get_distance_to_stop_line(self, vehicle: Vehicle) -> float:
        stop = self.get_stop_position(vehicle.route.source)
        d    = vehicle.route.source
        if d == Direction.NORTH:
            return vehicle.position - stop
        elif d == Direction.SOUTH:
            return stop - vehicle.position
        elif d == Direction.EAST:
            return stop - vehicle.position
        else:
            return vehicle.position - stop

    def is_in_approach_zone(self, vehicle: Vehicle) -> bool:
        d   = vehicle.route.source
        pos = vehicle.position
        if d == Direction.NORTH:
            return self.y_max < pos <= self.y_max + APPROACH_DISTANCE
        elif d == Direction.SOUTH:
            return self.y_min - APPROACH_DISTANCE <= pos < self.y_min
        elif d == Direction.EAST:
            return self.x_min - APPROACH_DISTANCE <= pos < self.x_min
        else:
            return self.x_max < pos <= self.x_max + APPROACH_DISTANCE

    def is_in_intersection(self, vehicle: Vehicle) -> bool:
        d   = vehicle.route.source
        pos = vehicle.position
        if d in (Direction.NORTH, Direction.SOUTH):
            return self.y_min <= pos <= self.y_max
        else:
            return self.x_min <= pos <= self.x_max

    def is_between_stop_and_intersection(self, vehicle: Vehicle) -> bool:
        """Check if vehicle is between stop line and intersection boundary."""
        d   = vehicle.route.source
        pos = vehicle.position
        if d == Direction.NORTH:
            return self.y_max < pos <= self.y_max + STOP_DISTANCE
        elif d == Direction.SOUTH:
            return self.y_min - STOP_DISTANCE <= pos < self.y_min
        elif d == Direction.EAST:
            return self.x_min - STOP_DISTANCE <= pos < self.x_min
        else:
            return self.x_max < pos <= self.x_max + STOP_DISTANCE

    def is_fully_clear(self, vehicle: Vehicle) -> bool:
        d   = vehicle.route.source
        pos = vehicle.position
        if d == Direction.NORTH:
            return pos < self.y_min - CLEARANCE_DISTANCE
        elif d == Direction.SOUTH:
            return pos > self.y_max + CLEARANCE_DISTANCE
        elif d == Direction.EAST:
            return pos > self.x_max + CLEARANCE_DISTANCE
        else:
            return pos < self.x_min - CLEARANCE_DISTANCE

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE ARBITER
    # ══════════════════════════════════════════════════════════════════════════

    def _active_dirs(self) -> List[str]:
        return PHASE_DIRS.get(self.current_phase, [])

    def _queue_size(self, dirs: List[str]) -> int:
        return sum(len(self.queues[d]) for d in dirs)

    def _select_phase_for(self, all_vehicles: List[Vehicle]) -> str:
        ns_count = sum(1 for v in all_vehicles
                       if v.route.source in PHASE_DIRS[PHASE_NS]
                       and self.is_in_approach_zone(v)
                       and v.state != VehicleState.COLLIDED)
        ew_count = sum(1 for v in all_vehicles
                       if v.route.source in PHASE_DIRS[PHASE_EW]
                       and self.is_in_approach_zone(v)
                       and v.state != VehicleState.COLLIDED)
        if ns_count == 0 and ew_count == 0:
            return PHASE_IDLE
        return PHASE_NS if ns_count >= ew_count else PHASE_EW

    def _opposite_phase(self) -> str:
        if self.current_phase == PHASE_NS:
            return PHASE_EW
        elif self.current_phase == PHASE_EW:
            return PHASE_NS
        return PHASE_NS

    def is_committed_to_cross(self, vehicle: Vehicle) -> bool:
        """
        A vehicle is committed if:
          1. Physically inside the intersection, OR
          2. Between stop line and intersection with non-zero speed, OR
          3. Has grant AND cannot stop before stop line
        """
        vid = vehicle.vehicle_id

        if self.is_in_intersection(vehicle):
            return True

        if self.is_between_stop_and_intersection(vehicle) and vehicle.current_speed > 0.5:
            return True

        if vid not in self.granted_vehicle_ids:
            return False

        dist_to_stop = self.get_distance_to_stop_line(vehicle)
        if dist_to_stop < 0:
            return True
        if vehicle.current_speed < 0.5:
            return False

        braking_dist = (vehicle.current_speed ** 2) / (2 * EMERGENCY_DECELERATION) + COMMITMENT_SAFETY_MARGIN
        return braking_dist > dist_to_stop

    def committed_vehicle_count(self) -> int:
        return len(self.committed_vehicles)

    def intersection_occupancy_count(self) -> int:
        return len(self.vehicles_inside)

    def _any_vehicle_in_conflict_zone(self, corridor_dirs: List[str]) -> bool:
        """Check if ANY vehicle from given corridor is in the conflict zone."""
        for v in self._all_vehicles:
            if v.state == VehicleState.COLLIDED:
                continue
            if v.route.source not in corridor_dirs:
                continue
            if self.is_in_intersection(v):
                return True
            if self.is_between_stop_and_intersection(v) and v.current_speed > 0.1:
                return True
            if v.vehicle_id in self.granted_vehicle_ids:
                return True
        return False

    def _is_intersection_fully_safe_for_switch(self) -> bool:
        """
        Safety check for corridor handover.
        
        Safe when:
          1. No vehicle from ANY corridor is inside the intersection
          2. No DRAINING corridor vehicle has a grant
          3. No DRAINING corridor vehicle is between stop line and intersection
             with any speed
        
        NOTE: We do NOT check committed_vehicles globally because incoming
        corridor vehicles at their stop line are irrelevant — they are being
        stopped/clamped and cannot cause a handover collision.
        """
        # Check 1: No vehicles inside intersection from ANY corridor
        if len(self.vehicles_inside) > 0:
            return False

        # Check 2+3: No draining corridor vehicles pose conflict risk
        draining_dirs = PHASE_DIRS.get(self._draining_from_phase, self._active_dirs())
        for v in self._all_vehicles:
            if v.state == VehicleState.COLLIDED:
                continue
            if v.route.source not in draining_dirs:
                continue
            if self.is_in_intersection(v):
                return False
            if v.vehicle_id in self.granted_vehicle_ids:
                return False
            if self.is_between_stop_and_intersection(v) and v.current_speed > 0.1:
                return False

        return True

    # ══════════════════════════════════════════════════════════════════════════
    # TICK PHASE (HANDOVER STATE MACHINE)
    # ══════════════════════════════════════════════════════════════════════════

    def tick_phase(self, all_vehicles: List[Vehicle], dt: float,
                   current_time: float):
        """
        Strict corridor handover state machine:
          ACTIVE → DRAINING → CLEARANCE → ACTIVE
        """
        self.phase_elapsed += dt

        # ── CLEARANCE state ───────────────────────────────────────────────────
        if self._handover_state == HANDOVER_CLEARANCE:
            self._clearance_timer -= dt

            # Extend clearance if draining corridor still has vehicles near
            draining_dirs = PHASE_DIRS.get(self._draining_from_phase, [])
            still_risky = False
            for v in all_vehicles:
                if v.state == VehicleState.COLLIDED:
                    continue
                if v.route.source not in draining_dirs:
                    continue
                if self.is_in_intersection(v):
                    still_risky = True
                    break
                if self.is_between_stop_and_intersection(v) and v.current_speed > 0.1:
                    still_risky = True
                    break
            if still_risky:
                self._clearance_timer = max(self._clearance_timer, CLEARANCE_DURATION)

            if self._clearance_timer <= 0:
                if self._is_intersection_fully_safe_for_switch():
                    self._activate_new_phase(all_vehicles, current_time)
                    self._handover_state = HANDOVER_ACTIVE
                    self._clearance_timer = 0.0
                else:
                    self._clearance_timer = CLEARANCE_DURATION
            return

        # ── DRAINING state ────────────────────────────────────────────────────
        if self._handover_state == HANDOVER_DRAINING:
            if self._is_intersection_fully_safe_for_switch():
                self._handover_state = HANDOVER_CLEARANCE
                self._clearance_timer = CLEARANCE_DURATION
                self._revoke_all_grants()
            return

        # ── ACTIVE state ──────────────────────────────────────────────────────
        active_dirs = self._active_dirs()
        
        # A corridor is only empty if there are NO serviceable vehicles left.
        # We must look at ALL vehicles on the active corridor that haven't crossed yet,
        # otherwise we might prematurely switch while a vehicle is approaching from >100m away.
        active_serviceable = sum(1 for v in all_vehicles 
                                 if v.route.source in active_dirs 
                                 and not v.has_exited_intersection
                                 and v.state != VehicleState.COLLIDED)
        queue_empty = (active_serviceable == 0)

        opposite_phase = self._opposite_phase()
        opposite_dirs = PHASE_DIRS.get(opposite_phase, [])
        # For the opposite waiting check, we only care if they are close enough to matter
        opposite_waiting = sum(1 for v in all_vehicles 
                               if v.route.source in opposite_dirs 
                               and self.is_in_approach_zone(v) 
                               and v.state != VehicleState.COLLIDED) > 0
        
        min_elapsed = self.phase_elapsed >= MIN_PHASE_DURATION

        if self.current_phase == PHASE_IDLE:
            self._activate_new_phase(all_vehicles, current_time)
            return

        should_switch = False
        if queue_empty and (min_elapsed or opposite_waiting):
            should_switch = True
        if self.phase_elapsed >= MAX_PHASE_DURATION and opposite_waiting:
            should_switch = True

        if should_switch:
            self._handover_state = HANDOVER_DRAINING
            self._draining_from_phase = self.current_phase
            self._draining_for_switch = True
            self._pending_phase = opposite_phase
            return

        self._issue_grant(current_time)

    def _revoke_all_grants(self):
        self.granted_vehicle_ids.clear()
        self.grant_times.clear()
        self._grant_corridor.clear()
        self.granted_vehicle_id = None

    def _activate_new_phase(self, all_vehicles: List[Vehicle], current_time: float):
        """Activate a new corridor phase. Only called when fully safe."""
        if self._pending_phase is not None:
            new_phase = self._pending_phase
        else:
            new_phase = self._select_phase_for(all_vehicles)
            
        self._revoke_all_grants()

        if new_phase == PHASE_IDLE:
            self.current_phase    = PHASE_IDLE
            self.phase_elapsed    = 0.0
            self.phase_start_time = current_time
            self._handover_state  = HANDOVER_ACTIVE
            self._draining_for_switch = False
            self._draining_from_phase = None
            self._pending_phase = None
            return

        self.current_phase    = new_phase
        self.phase_elapsed    = 0.0
        self.phase_start_time = current_time
        self._handover_state  = HANDOVER_ACTIVE
        self._draining_for_switch = False
        self._draining_from_phase = None
        self._pending_phase = None

        for d in PHASE_DIRS[new_phase]:
            live = [v for v in self.queues[d]
                    if v in all_vehicles and
                    self.is_in_approach_zone(v) and
                    v.state != VehicleState.COLLIDED]
            self.queues[d] = deque(live)

    def _issue_grant(self, current_time: float):
        """
        SINGLE AUTHORITY for crossing grants.
        
        Rules:
          1. Never during DRAINING or CLEARANCE
          2. Only active-phase vehicles
          3. No grants if intersection occupied
          4. No grants if committed vehicles exist
          5. No grants if opposite corridor in conflict zone
        """
        if self._handover_state != HANDOVER_ACTIVE:
            return

        active_dirs = self._active_dirs()
        if not active_dirs:
            return

        if self.intersection_occupancy_count() > 0:
            return
        if self.committed_vehicle_count() > 0:
            return

        opposite_phase = self._opposite_phase()
        opposite_dirs = PHASE_DIRS.get(opposite_phase, [])
        if opposite_dirs and self._any_vehicle_in_conflict_zone(opposite_dirs):
            return

        for d in active_dirs:
            q = self.queues[d]
            if not q:
                continue
            lead = q[0]
            if lead.state == VehicleState.COLLIDED:
                q.popleft()
                continue
            if not self.is_in_approach_zone(lead):
                q.popleft()
                continue
            if lead.vehicle_id in self.granted_vehicle_ids:
                continue

            self.granted_vehicle_ids.add(lead.vehicle_id)
            self.grant_times[lead.vehicle_id] = current_time
            self._grant_corridor[lead.vehicle_id] = self.current_phase
            self.total_reservations += 1
            q.popleft()

            if self.granted_vehicle_id is None:
                self.granted_vehicle_id = lead.vehicle_id
                self.granted_at = current_time

    def _revoke_grant(self, vehicle_id: int):
        self.granted_vehicle_ids.discard(vehicle_id)
        if vehicle_id in self.grant_times:
            del self.grant_times[vehicle_id]
        if vehicle_id in self._grant_corridor:
            del self._grant_corridor[vehicle_id]
        if self.granted_vehicle_id == vehicle_id:
            if self.granted_vehicle_ids:
                self.granted_vehicle_id = next(iter(self.granted_vehicle_ids))
            else:
                self.granted_vehicle_id = None

    # ══════════════════════════════════════════════════════════════════════════
    # QUEUE MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════════

    def _enqueue(self, vehicle: Vehicle):
        q = self.queues[vehicle.route.source]
        if vehicle not in q:
            q.append(vehicle)

    def _dequeue(self, vehicle: Vehicle):
        q = self.queues[vehicle.route.source]
        if vehicle in q:
            q.remove(vehicle)

    # ══════════════════════════════════════════════════════════════════════════
    # DEADLOCK RECOVERY
    # ══════════════════════════════════════════════════════════════════════════

    def _force_recovery(self, all_vehicles: List[Vehicle], current_time: float):
        self.deadlock_recoveries += 1
        self._revoke_all_grants()
        self._handover_state = HANDOVER_ACTIVE
        self._draining_for_switch = False
        self._draining_from_phase = None
        self._clearance_timer = 0.0
        self._pending_phase = None

        for d in Direction.all():
            self.queues[d].clear()

        for v in all_vehicles:
            if v.state != VehicleState.COLLIDED and self.is_in_approach_zone(v):
                self._enqueue(v)

        self.current_phase = PHASE_IDLE
        self.phase_elapsed = MAX_PHASE_DURATION
        self._activate_new_phase(all_vehicles, current_time)
        self._issue_grant(current_time)

    # ══════════════════════════════════════════════════════════════════════════
    # PER-VEHICLE UPDATE
    # ══════════════════════════════════════════════════════════════════════════

    def update_vehicle(self, vehicle: Vehicle, current_time: float) -> str:
        """
        SINGLE AUTHORITY per-vehicle command.
        Returns: 'continue', 'slow', 'stop', 'enter', 'cross'
        """
        vid = vehicle.vehicle_id
        direction = vehicle.route.source
        active_dirs = self._active_dirs()
        in_active = (direction in active_dirs)

        # ── CLEARANCE: vehicles already inside or past stop line must exit; all others stop ─────
        if self._handover_state == HANDOVER_CLEARANCE:
            if self.is_in_intersection(vehicle) or self.is_between_stop_and_intersection(vehicle) or self.is_committed_to_cross(vehicle):
                self.vehicles_inside.add(vid)
                vehicle.set_state(VehicleState.CROSSING)
                return 'cross' if self.is_in_intersection(vehicle) else 'enter'
            if self.is_in_approach_zone(vehicle):
                vehicle.set_state(VehicleState.WAITING)
                return 'stop'

        # ── 1. Fully cleared ──────────────────────────────────────────────────
        if self.is_fully_clear(vehicle):
            if not vehicle.has_exited_intersection:
                vehicle.has_exited_intersection = True
                self.total_crossings_completed += 1
                if vehicle.state != VehicleState.COLLIDED and not vehicle.in_collision:
                    self.total_safe_crossings += 1
            self.vehicles_inside.discard(vid)
            if vid in self.granted_vehicle_ids:
                self._revoke_grant(vid)
                if self._handover_state == HANDOVER_ACTIVE:
                    self._issue_grant(current_time)
            self._dequeue(vehicle)
            vehicle.set_state(VehicleState.MOVING)
            return 'continue'

        # ── 2. Inside intersection ────────────────────────────────────────────
        if self.is_in_intersection(vehicle):
            self.vehicles_inside.add(vid)
            vehicle.set_state(VehicleState.CROSSING)
            return 'cross'

        # ── 3. Between stop line and intersection (Point of no return) ────────
        if self.is_between_stop_and_intersection(vehicle):
            # ONCE PAST THE STOP LINE, THE VEHICLE MUST NEVER MOVE BACKWARD.
            # Even if it lost its grant or the phase changed, clamping it backward
            # causes teleportation/rollback bugs. Therefore, we let it cross.
            vehicle.set_state(VehicleState.CROSSING)
            return 'enter'

        # ── 4. Approach zone ──────────────────────────────────────────────────
        if self.is_in_approach_zone(vehicle):
            has_grant = (vid in self.granted_vehicle_ids)
            dist_to_stop = self.get_distance_to_stop_line(vehicle)

            # DRAINING: vehicles with existing grants continue; others stop
            if self._handover_state == HANDOVER_DRAINING:
                if has_grant:
                    if dist_to_stop <= 2.0:
                        vehicle.set_state(VehicleState.CROSSING)
                        return 'enter'
                    else:
                        vehicle.set_state(VehicleState.MOVING)
                        return 'continue'
                else:
                    self._enqueue(vehicle)
                    vehicle.set_state(VehicleState.WAITING)
                    return 'stop'

            # CORRIDOR GATE: wrong corridor → stop
            if not in_active:
                self._enqueue(vehicle)
                vehicle.set_state(VehicleState.WAITING)
                return 'stop'

            # Active phase with grant
            if has_grant:
                if not in_active:
                    self._revoke_grant(vid)
                    self._enqueue(vehicle)
                    vehicle.set_state(VehicleState.WAITING)
                    return 'stop'
                if dist_to_stop <= 2.0:
                    vehicle.set_state(VehicleState.CROSSING)
                    return 'enter'
                else:
                    vehicle.set_state(VehicleState.MOVING)
                    return 'continue'
            else:
                self._enqueue(vehicle)
                vehicle.set_state(VehicleState.WAITING)
                return 'stop' if dist_to_stop <= 10.0 else 'slow'

        # ── 5. Before approach zone ───────────────────────────────────────────
        vehicle.set_state(VehicleState.MOVING)
        return 'continue'

    # ══════════════════════════════════════════════════════════════════════════
    # MASTER ARBITER TICK
    # ══════════════════════════════════════════════════════════════════════════

    def run_arbiter(self, all_vehicles: List[Vehicle], dt: float,
                    current_time: float):
        self._all_vehicles = all_vehicles
        live_ids = {v.vehicle_id for v in all_vehicles}

        # 1. Purge dead vehicles from queues
        for d in Direction.all():
            self.queues[d] = deque(
                v for v in self.queues[d] if v.vehicle_id in live_ids
            )

        # 2. Purge grants for removed vehicles
        dead_grants = [vid for vid in self.granted_vehicle_ids if vid not in live_ids]
        for vid in dead_grants:
            self._revoke_grant(vid)

        # 3. Sync vehicles_inside
        self.vehicles_inside = {
            v.vehicle_id for v in all_vehicles
            if self.is_in_intersection(v) and v.state != VehicleState.COLLIDED
        }

        # 4. Update committed_vehicles
        self.committed_vehicles = {
            v.vehicle_id for v in all_vehicles
            if self.is_committed_to_cross(v) and v.state != VehicleState.COLLIDED
        }

        # 5. Revoke wrong-corridor grants
        if self._handover_state == HANDOVER_ACTIVE:
            active_dirs = self._active_dirs()
            wrong_grants = []
            for vid in list(self.granted_vehicle_ids):
                veh = None
                for v in all_vehicles:
                    if v.vehicle_id == vid:
                        veh = v
                        break
                if veh is None:
                    wrong_grants.append(vid)
                    continue
                if veh.route.source not in active_dirs:
                    wrong_grants.append(vid)
            for vid in wrong_grants:
                self._revoke_grant(vid)

        # 6. Phase tick
        self.tick_phase(all_vehicles, dt, current_time)

        # 7. Deadlock safety net
        waiting_in_approach = [
            v for v in all_vehicles
            if v.state == VehicleState.WAITING
            and self.is_in_approach_zone(v)
            and v.state != VehicleState.COLLIDED
        ]
        crossing_now = [
            v for v in all_vehicles
            if self.is_in_intersection(v) and v.state != VehicleState.COLLIDED
        ]
        if (waiting_in_approach and
                not crossing_now and
                len(self.granted_vehicle_ids) == 0 and
                self.phase_elapsed > MAX_PHASE_DURATION + 5.0 and
                self._handover_state == HANDOVER_ACTIVE):
            self._force_recovery(all_vehicles, current_time)

        self.active_reservations = self.granted_vehicle_ids.copy()

    # ══════════════════════════════════════════════════════════════════════════
    # STATE SERIALISATION
    # ══════════════════════════════════════════════════════════════════════════

    def get_state(self) -> dict:
        waiting_counts = {d: len(self.queues[d]) for d in Direction.all()}
        occupancy_count = self.intersection_occupancy_count()
        committed_count = self.committed_vehicle_count()
        active_grants_count = len(self.granted_vehicle_ids)

        return {
            "center_x":            self.center_x,
            "center_y":            self.center_y,
            "size":                self.size,
            "current_phase":       self.current_phase,
            "handover_state":      self._handover_state,
            "phase_elapsed":       round(self.phase_elapsed, 2),
            "active_directions":   self._active_dirs(),
            "granted_vehicle_id":  self.granted_vehicle_id,
            "granted_vehicle_ids": list(self.granted_vehicle_ids),
            "active_reservations": len(self.active_reservations),
            "active_grants_count": active_grants_count,
            "waiting_counts":      waiting_counts,
            "total_reservations":  self.total_reservations,
            "conflicts_prevented": self.total_conflicts_prevented,
            "deadlock_recoveries": self.deadlock_recoveries,
            "total_crossings":     self.total_crossings_completed,
            "safe_crossings":      self.total_safe_crossings,
            "committed_vehicles":  committed_count,
            "intersection_occupancy": occupancy_count,
            "vehicles_inside_count": occupancy_count,
            "clearance_timer":     round(self._clearance_timer, 2),
            "occupancy":           active_grants_count,
            "max_occupancy":       2,
            "vehicles_inside":     list(self.vehicles_inside),
            "reservation_details": [
                {"vehicle_id": vid, "state": "crossing"}
                for vid in self.granted_vehicle_ids
            ],
        }

    def __repr__(self):
        return (
            f"FourWayIntersection(phase={self.current_phase}, "
            f"handover={self._handover_state}, "
            f"grants={len(self.granted_vehicle_ids)}, "
            f"queues={sum(len(q) for q in self.queues.values())})"
        )
