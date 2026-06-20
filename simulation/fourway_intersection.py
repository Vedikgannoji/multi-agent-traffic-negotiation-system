"""
fourway_intersection.py - Ownership-window intersection arbiter.

Architecture: PHASE-BASED OWNERSHIP WINDOWS
  The intersection is controlled by a single rotating arbiter.
  At any moment exactly one phase owns the intersection:
    PHASE_NS  – north/south vehicles may cross
    PHASE_EW  – east/west vehicles may cross
    PHASE_IDLE – no vehicles present, arbiter is idle

  Within the active phase the arbiter grants crossing permission to
  vehicles one at a time (lead vehicle first).  Vehicles in the
  inactive phase MUST stop and queue.  This eliminates all circular
  waiting and mutual-yield deadlocks by construction.

  Phase rotation rules:
    1. Rotate when the active queue is empty AND no vehicle is crossing.
    2. Rotate when the phase timeout expires (max_phase_duration).
    3. If the new phase also has no queue, rotate again immediately.

  Crossing statistics are counted the instant a vehicle fully exits
  the intersection zone – NOT when it despawns.
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

# Minimum time a phase stays active even if queue drains (seconds).
MIN_PHASE_DURATION = 1.0

# Maximum time a phase stays active before forced rotation (seconds).
# A single crossing takes ~8s, so allow 2 crossings per phase max.
MAX_PHASE_DURATION = 10.0

# How far ahead of the intersection a vehicle must be to be considered
# "in the approach zone" and eligible for a grant.
APPROACH_DISTANCE = 100.0   # metres

# Stop-line offset: vehicles stop this far before the intersection boundary.
# Must be >= v²/(2*decel) for max speed: 18²/(2*4) = 40.5m → use 50m for safety.
STOP_DISTANCE = 50.0        # metres

# Clearance: vehicle must travel this far past the intersection boundary
# before its reservation is released and the crossing is counted.
CLEARANCE_DISTANCE = 30.0   # metres


class FourWayIntersection:
    """
    Ownership-window intersection arbiter.

    Single source of truth for:
      - which phase currently owns the intersection
      - which vehicle (if any) holds the active crossing grant
      - per-direction waiting queues
      - crossing statistics
    """

    def __init__(self, center_x: float = 250.0, center_y: float = 250.0,
                 size: float = 40.0):
        self.center_x = center_x
        self.center_y = center_y
        self.size     = size

        # Intersection boundary
        self.x_min = center_x - size / 2
        self.x_max = center_x + size / 2
        self.y_min = center_y - size / 2
        self.y_max = center_y + size / 2

        # ── Phase state ────────────────────────────────────────────────────────
        self.current_phase: str        = PHASE_IDLE
        self.phase_start_time: float   = 0.0
        self.phase_elapsed: float      = 0.0

        # ── Grant state ────────────────────────────────────────────────────────
        # TASK A: Support multiple simultaneous grants within same phase
        # (e.g., both NORTH and SOUTH vehicles can cross together in NS phase)
        self.granted_vehicle_ids: Set[int] = set()  # Multiple vehicles can have grants
        self.grant_times: Dict[int, float] = {}     # Track when each grant was issued
        
        # Legacy compatibility - keep single grant ID field for API
        self.granted_vehicle_id: Optional[int] = None
        self.granted_at: float                 = 0.0

        # ── Per-direction queues ───────────────────────────────────────────────
        # Ordered by arrival time (FIFO).  Only vehicles in the active phase
        # are eligible to receive a grant.
        self.queues: Dict[str, deque] = {
            Direction.NORTH: deque(),
            Direction.SOUTH: deque(),
            Direction.EAST:  deque(),
            Direction.WEST:  deque(),
        }

        # Set of vehicle IDs currently inside the intersection zone.
        self.vehicles_inside: Set[int] = set()

        # ── Statistics ─────────────────────────────────────────────────────────
        self.total_crossings_completed: int = 0
        self.total_safe_crossings:      int = 0
        self.total_reservations:        int = 0   # kept for API compat
        self.total_conflicts_prevented: int = 0   # kept for API compat
        self.deadlock_recoveries:       int = 0

        # Legacy compat (used by backend reset)
        self.active_reservations: Set[int] = set()
        self.reservations:        Dict     = {}
        self.waiting_queues                = self.queues   # alias

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
        else:  # WEST
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

    def _has_vehicle_crossing(self) -> bool:
        """Check if any vehicle currently has a grant."""
        return len(self.granted_vehicle_ids) > 0

    def _select_phase_for(self, all_vehicles: List[Vehicle]) -> str:
        """Choose the best phase given current vehicle positions."""
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
        # Prefer the axis with more waiting vehicles; tie → NS first
        return PHASE_NS if ns_count >= ew_count else PHASE_EW

    def _opposite_phase(self) -> str:
        if self.current_phase == PHASE_NS:
            return PHASE_EW
        elif self.current_phase == PHASE_EW:
            return PHASE_NS
        return PHASE_NS   # from IDLE, start with NS

    def tick_phase(self, all_vehicles: List[Vehicle], dt: float,
                   current_time: float):
        """
        Called once per update cycle.  Advances the phase timer and rotates
        the phase when appropriate.  Also issues or refreshes the crossing
        grant for the lead vehicle in the active phase.
        
        TASK B FIX: Only rotate phase when intersection is completely empty.
        """
        self.phase_elapsed += dt

        active_dirs = self._active_dirs()
        queue_empty = self._queue_size(active_dirs) == 0
        no_crossing = not self._has_vehicle_crossing()

        # TASK B CRITICAL: Count vehicles physically inside intersection
        vehicles_inside_count = len(self.vehicles_inside)
        intersection_empty = vehicles_inside_count == 0

        # Check if the OTHER axis has vehicles waiting
        opposite_dirs = PHASE_DIRS[self._opposite_phase()] if self.current_phase != PHASE_IDLE else []
        opposite_waiting = self._queue_size(opposite_dirs) > 0

        timed_out   = self.phase_elapsed >= MAX_PHASE_DURATION
        min_elapsed = self.phase_elapsed >= MIN_PHASE_DURATION

        # TASK B: Rotate ONLY when intersection is completely empty
        should_rotate = (
            intersection_empty and
            no_crossing and
            (
                (queue_empty and min_elapsed) or
                timed_out or
                (queue_empty and opposite_waiting)
            )
        )

        if should_rotate or self.current_phase == PHASE_IDLE:
            # Log corridor switch events
            if self.current_phase != PHASE_IDLE and vehicles_inside_count == 0:
                print(f"[PHASE SWITCH] Time {current_time:.2f}: {self.current_phase} → rotation. Vehicles inside: {vehicles_inside_count}")
            self._rotate_phase(all_vehicles, current_time)

        # TASK A: Try to issue grants continuously (can issue multiple simultaneously)
        self._issue_grant(current_time)

    def _rotate_phase(self, all_vehicles: List[Vehicle], current_time: float):
        """
        Switch to the next phase.  Clears any stale queue entries.
        
        TASK B: Log phase rotation events with occupancy count.
        """
        new_phase = self._select_phase_for(all_vehicles)
        
        vehicles_inside_count = len(self.vehicles_inside)

        if new_phase == PHASE_IDLE:
            # Nothing approaching – stay idle but keep checking
            if self.current_phase != PHASE_IDLE:
                print(f"[CORRIDOR REVOKED] Time {current_time:.2f}: {self.current_phase} → IDLE. Vehicles inside: {vehicles_inside_count}")
                self.current_phase  = PHASE_IDLE
                self.phase_elapsed  = 0.0
                self.phase_start_time = current_time
            return

        # If we were idle or the new phase differs, switch
        if new_phase != self.current_phase or self.current_phase == PHASE_IDLE:
            old_phase = self.current_phase
            self.current_phase    = new_phase
            self.phase_elapsed    = 0.0
            self.phase_start_time = current_time
            
            print(f"[CORRIDOR GRANTED] Time {current_time:.2f}: {old_phase} → {new_phase}. Vehicles inside: {vehicles_inside_count}")

            # Purge stale queue entries for the newly active directions
            # (vehicles that left the approach zone while waiting)
            for d in PHASE_DIRS[new_phase]:
                live = [v for v in self.queues[d]
                        if v in all_vehicles and
                        self.is_in_approach_zone(v) and
                        v.state != VehicleState.COLLIDED]
                self.queues[d] = deque(live)

    def _issue_grant(self, current_time: float):
        """
        Grant crossing permission to vehicles in the active phase.
        
        TASK A FIX: Allow opposite straight movements simultaneously.
        - Within NS phase: both NORTH and SOUTH can have grants at once
        - Within EW phase: both EAST and WEST can have grants at once
        
        TASK B FIX: Only grant if intersection is completely empty of conflicting traffic.
        """
        active_dirs = self._active_dirs()
        
        # TASK B: Safety check - intersection must be empty before first grant
        if len(self.vehicles_inside) > 0:
            # Don't grant if ANY vehicle is still physically inside
            return
        
        # Try to issue grants to each direction in the active phase
        for d in active_dirs:
            q = self.queues[d]
            if not q:
                continue
                
            lead = q[0]
            
            # Skip invalid vehicles
            if lead.state == VehicleState.COLLIDED:
                q.popleft()
                continue
            if not self.is_in_approach_zone(lead):
                q.popleft()
                continue
            
            # Check if this vehicle already has a grant
            if lead.vehicle_id in self.granted_vehicle_ids:
                continue

            # Grant to this vehicle
            self.granted_vehicle_ids.add(lead.vehicle_id)
            self.grant_times[lead.vehicle_id] = current_time
            self.total_reservations += 1
            q.popleft()
            
            # Update legacy field for API compatibility
            if self.granted_vehicle_id is None:
                self.granted_vehicle_id = lead.vehicle_id
                self.granted_at = current_time
            
            print(f"[GRANT] Time {current_time:.2f}: Vehicle {lead.vehicle_id} from {d} granted. Active grants: {len(self.granted_vehicle_ids)}, Vehicles inside: {len(self.vehicles_inside)}")

    def _revoke_grant(self, vehicle_id: int):
        """Revoke grant for a specific vehicle."""
        self.granted_vehicle_ids.discard(vehicle_id)
        if vehicle_id in self.grant_times:
            del self.grant_times[vehicle_id]
        
        # Update legacy field
        if self.granted_vehicle_id == vehicle_id:
            # Set to another active grant if any
            if self.granted_vehicle_ids:
                self.granted_vehicle_id = next(iter(self.granted_vehicle_ids))
            else:
                self.granted_vehicle_id = None

    # ══════════════════════════════════════════════════════════════════════════
    # QUEUE MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════════

    def _enqueue(self, vehicle: Vehicle):
        """Add vehicle to its direction queue if not already present."""
        q = self.queues[vehicle.route.source]
        if vehicle not in q:
            q.append(vehicle)

    def _dequeue(self, vehicle: Vehicle):
        """Remove vehicle from its direction queue."""
        q = self.queues[vehicle.route.source]
        if vehicle in q:
            q.remove(vehicle)

    # ══════════════════════════════════════════════════════════════════════════
    # DEADLOCK RECOVERY (safety net – should rarely fire)
    # ══════════════════════════════════════════════════════════════════════════

    def _force_recovery(self, all_vehicles: List[Vehicle], current_time: float):
        """
        Hard reset: clear grant, clear queues, force-rotate phase, re-enqueue
        all approach-zone vehicles, issue a fresh grant.
        """
        self.deadlock_recoveries += 1
        self.granted_vehicle_ids.clear()
        self.grant_times.clear()
        self.granted_vehicle_id = None

        # Clear all queues
        for d in Direction.all():
            self.queues[d].clear()

        # Re-enqueue every non-collided approach-zone vehicle
        for v in all_vehicles:
            if v.state != VehicleState.COLLIDED and self.is_in_approach_zone(v):
                self._enqueue(v)

        # Force phase rotation
        self.current_phase  = PHASE_IDLE
        self.phase_elapsed  = MAX_PHASE_DURATION   # triggers immediate rotation
        self._rotate_phase(all_vehicles, current_time)
        self._issue_grant(current_time)

    # ══════════════════════════════════════════════════════════════════════════
    # MAIN PER-VEHICLE UPDATE
    # ══════════════════════════════════════════════════════════════════════════

    def update_vehicle(self, vehicle: Vehicle, current_time: float) -> str:
        """
        Authoritative per-vehicle command.

        Returns one of: 'continue', 'slow', 'stop', 'enter', 'cross'

        Lifecycle:
          BEFORE APPROACH  → 'continue'  (normal driving)
          APPROACH, no grant → enqueue, 'slow'/'stop'
          APPROACH, granted  → 'continue' (proceed to stop line)
          AT STOP LINE, granted → 'enter'
          INSIDE INTERSECTION → 'cross'  (grant locked until clear)
          FULLY CLEAR → count crossing, release grant, 'continue'
        
        TASK A: Support multiple simultaneous grants within same phase.
        TASK B: Track vehicles inside intersection for corridor handoff safety.
        """
        vid = vehicle.vehicle_id

        # ── 1. Fully cleared ──────────────────────────────────────────────────
        if self.is_fully_clear(vehicle):
            if not vehicle.has_exited_intersection:
                vehicle.has_exited_intersection = True
                self.total_crossings_completed += 1
                if vehicle.state != VehicleState.COLLIDED and not vehicle.in_collision:
                    self.total_safe_crossings += 1

            # TASK B: Remove from vehicles_inside when fully cleared
            was_inside = vid in self.vehicles_inside
            self.vehicles_inside.discard(vid)
            
            if was_inside:
                print(f"[CLEARED] Time {current_time:.2f}: Vehicle {vid} cleared. Vehicles inside: {len(self.vehicles_inside)}")

            # Release grant IMMEDIATELY so next vehicle can be issued one
            if vid in self.granted_vehicle_ids:
                self._revoke_grant(vid)
                # Immediately try to issue the next grant
                self._issue_grant(current_time)

            self._dequeue(vehicle)
            vehicle.set_state(VehicleState.MOVING)
            return 'continue'

        # ── 2. Inside intersection ────────────────────────────────────────────
        if self.is_in_intersection(vehicle):
            was_inside = vid in self.vehicles_inside
            self.vehicles_inside.add(vid)
            
            if not was_inside:
                print(f"[ENTERED] Time {current_time:.2f}: Vehicle {vid} entered. Vehicles inside: {len(self.vehicles_inside)}")
            
            vehicle.set_state(VehicleState.CROSSING)
            # Lock the grant to this vehicle while it's inside.
            if vid not in self.granted_vehicle_ids:
                self.granted_vehicle_ids.add(vid)
                if self.granted_vehicle_id is None:
                    self.granted_vehicle_id = vid
            return 'cross'

        # ── 3. Approach zone ──────────────────────────────────────────────────
        if self.is_in_approach_zone(vehicle):
            direction    = vehicle.route.source
            has_grant    = (vid in self.granted_vehicle_ids)
            in_active    = (direction in self._active_dirs())
            dist_to_stop = self.get_distance_to_stop_line(vehicle)

            if has_grant:
                # This vehicle owns the crossing right — proceed confidently
                if dist_to_stop <= 2.0:
                    vehicle.set_state(VehicleState.CROSSING)
                    return 'enter'
                else:
                    vehicle.set_state(VehicleState.MOVING)
                    return 'continue'

            elif in_active:
                # Active phase but no grant yet — queue and slow/stop
                self._enqueue(vehicle)
                vehicle.set_state(VehicleState.WAITING)
                return 'stop' if dist_to_stop <= 10.0 else 'slow'

            else:
                # Inactive phase — must stop before stop line, no exceptions
                self._enqueue(vehicle)
                vehicle.set_state(VehicleState.WAITING)
                return 'stop'

        # ── 4. Before approach zone ───────────────────────────────────────────
        vehicle.set_state(VehicleState.MOVING)
        return 'continue'

    # ══════════════════════════════════════════════════════════════════════════
    # CALLED BY TRAFFIC MANAGER EACH TICK
    # ══════════════════════════════════════════════════════════════════════════

    def run_arbiter(self, all_vehicles: List[Vehicle], dt: float,
                    current_time: float):
        """
        Master arbiter tick.  Call this ONCE per simulation update, before
        calling update_vehicle() for individual vehicles.
        """
        live_ids = {v.vehicle_id for v in all_vehicles}

        # 1. Purge dead vehicles from queues
        for d in Direction.all():
            self.queues[d] = deque(
                v for v in self.queues[d] if v.vehicle_id in live_ids
            )

        # 2. Purge grants if holder left the simulation
        dead_grants = [vid for vid in self.granted_vehicle_ids if vid not in live_ids]
        for vid in dead_grants:
            self._revoke_grant(vid)

        # 3. Sync vehicles_inside — only vehicles physically inside right now
        self.vehicles_inside = {
            v.vehicle_id for v in all_vehicles
            if self.is_in_intersection(v) and v.state != VehicleState.COLLIDED
        }

        # 4. Phase tick + grant issuance
        self.tick_phase(all_vehicles, dt, current_time)

        # 5. Deadlock safety-net
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
                self.phase_elapsed > MAX_PHASE_DURATION + 3.0):
            self._force_recovery(all_vehicles, current_time)

        # Keep legacy active_reservations in sync for API compat
        self.active_reservations = self.granted_vehicle_ids.copy()

    # ══════════════════════════════════════════════════════════════════════════
    # STATE SERIALISATION (frontend / API)
    # ══════════════════════════════════════════════════════════════════════════

    def get_state(self) -> dict:
        waiting_counts = {d: len(self.queues[d]) for d in Direction.all()}
        vehicles_inside_count = len(self.vehicles_inside)
        active_grants_count = len(self.granted_vehicle_ids)
        
        return {
            "center_x":            self.center_x,
            "center_y":            self.center_y,
            "size":                self.size,
            # Phase info
            "current_phase":       self.current_phase,
            "phase_elapsed":       round(self.phase_elapsed, 2),
            "active_directions":   self._active_dirs(),
            # Grant info (TASK A: expose multiple grants)
            "granted_vehicle_id":  self.granted_vehicle_id,  # Legacy single grant
            "granted_vehicle_ids": list(self.granted_vehicle_ids),  # All active grants
            "active_reservations": len(self.active_reservations),
            "active_grants_count": active_grants_count,
            # Queues
            "waiting_counts":      waiting_counts,
            # Stats
            "total_reservations":  self.total_reservations,
            "conflicts_prevented": self.total_conflicts_prevented,
            "deadlock_recoveries": self.deadlock_recoveries,
            "total_crossings":     self.total_crossings_completed,
            "safe_crossings":      self.total_safe_crossings,
            # TASK B: Expose vehicles inside count for debugging corridor handoff
            "vehicles_inside_count": vehicles_inside_count,
            # Legacy frontend fields
            "occupancy":           active_grants_count,
            "max_occupancy":       2,  # Can have 2 simultaneous (opposite straights)
            "vehicles_inside":     list(self.vehicles_inside),
            "reservation_details": [
                {"vehicle_id": vid, "state": "crossing"}
                for vid in self.granted_vehicle_ids
            ],
        }

    def __repr__(self):
        return (
            f"FourWayIntersection(phase={self.current_phase}, "
            f"grants={len(self.granted_vehicle_ids)}, "
            f"queues={sum(len(q) for q in self.queues.values())})"
        )
