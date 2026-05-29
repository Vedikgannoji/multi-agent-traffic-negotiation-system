"""
vehicle.py - Represents a single vehicle with realistic physics.
"""

import sys
from pathlib import Path

try:
    from simulation.direction import Route
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from direction import Route


class VehicleState:
    MOVING   = "moving"
    WAITING  = "waiting"
    CROSSING = "crossing"
    COLLIDED = "collided"   # terminal state — vehicle is frozen after a crash


class Vehicle:
    # Physics constants
    MAX_ACCELERATION      = 2.5   # m/s²
    MAX_DECELERATION      = 4.0   # m/s²
    EMERGENCY_DECELERATION = 6.0  # m/s²
    MIN_SPEED             = 0.0   # m/s

    def __init__(self, vehicle_id: int, route: Route, position: float = 0.0,
                 desired_speed: float = None, max_speed: float = 25.0):
        self.vehicle_id   = vehicle_id
        self.route        = route
        self.position     = position
        self.max_speed    = max_speed

        import random
        self.desired_speed  = desired_speed if desired_speed is not None else random.uniform(12.0, 22.0)
        self.current_speed  = 0.0
        self.target_speed   = self.desired_speed

        self.state                    = VehicleState.MOVING
        self.has_entered_intersection = False
        self.has_exited_intersection  = False
        self.in_collision             = False   # True while overlapping another vehicle
        self.is_emergency_braking     = False

        # Collision freeze timer: set to a positive value when collision is detected.
        # Vehicle stays frozen (speed=0, state=COLLIDED) until timer reaches 0,
        # then it is removed from the simulation.
        self.collision_freeze_timer: float = 0.0

    @property
    def speed(self) -> float:
        return self.current_speed

    @speed.setter
    def speed(self, value: float):
        self.current_speed = max(0.0, min(value, self.max_speed))

    def set_target_speed(self, target: float, emergency: bool = False):
        self.target_speed = max(0.0, min(target, self.max_speed))
        self.is_emergency_braking = emergency and target < self.current_speed

    def accelerate_to_desired(self):
        self.set_target_speed(self.desired_speed, emergency=False)

    def slow_to_speed(self, target_speed: float, emergency: bool = False):
        self.set_target_speed(target_speed, emergency=emergency)

    def stop(self, emergency: bool = False):
        self.set_target_speed(0.0, emergency=emergency)

    def set_state(self, state: str):
        # Never override COLLIDED state from outside the collision system
        if self.state == VehicleState.COLLIDED:
            return
        self.state = state

    # Legacy compatibility
    def move(self, dt: float = 1.0):       pass
    def slow_down(self, t: float):         self.slow_to_speed(t)
    def speed_up(self):                    self.accelerate_to_desired()
    def update_physics(self, dt: float):   pass  # movement handled by manager

    def __repr__(self):
        return (f"Vehicle(id={self.vehicle_id}, route={self.route}, "
                f"pos={self.position:.1f}m, spd={self.current_speed:.1f}m/s, "
                f"state={self.state})")
