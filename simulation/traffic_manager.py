"""
traffic_manager.py - Manages all vehicles on the road.
Handles spawning, updating positions, and basic collision avoidance.
"""

import sys
import random
from pathlib import Path

# Support both standalone and package imports
try:
    from simulation.vehicle import Vehicle, VehicleState
    from simulation.road import Road
    from simulation.intersection import Intersection
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from vehicle import Vehicle, VehicleState
    from road import Road
    from intersection import Intersection

# Minimum gap (meters) required between two vehicles in the same lane
MIN_GAP = 10.0


class TrafficManager:
    def __init__(self, road: Road, intersection: Intersection = None):
        self.road = road
        self.vehicles: list[Vehicle] = []
        self.intersection = intersection
        self._next_id = 1  # auto-increment vehicle IDs

    # ------------------------------------------------------------------
    # Spawning
    # ------------------------------------------------------------------

    def spawn_vehicle(self, lane: int = None, position: float = 0.0, speed: float = None) -> Vehicle:
        """
        Create a new vehicle and add it to the simulation.
        Defaults to a random lane and a random speed between 10-30 m/s.
        """
        if lane is None:
            lane = random.randint(0, self.road.num_lanes - 1)
        if speed is None:
            speed = random.uniform(10.0, 30.0)

        vehicle = Vehicle(
            vehicle_id=self._next_id,
            lane=lane,
            position=position,
            speed=speed,
        )
        self._next_id += 1
        self.vehicles.append(vehicle)
        return vehicle

    # ------------------------------------------------------------------
    # Update loop
    # ------------------------------------------------------------------

    def update(self, dt: float = 1.0):
        """
        Advance the simulation by one time step (dt seconds).
        1. Update intersection logic for each vehicle.
        2. Move vehicles based on their state.
        3. Remove vehicles that have left the road.
        4. Resolve simple same-lane overlaps.
        """
        # Update intersection logic first
        if self.intersection:
            for vehicle in self.vehicles:
                action = self.intersection.update_vehicle(vehicle)
                
                # Apply action to vehicle
                if action == 'stop':
                    vehicle.slow_down(0.0)  # Stop
                elif action == 'slow':
                    vehicle.slow_down(5.0)  # Slow to 5 m/s
                elif action == 'cross':
                    vehicle.speed_up()  # Resume normal speed
                elif action == 'continue':
                    vehicle.speed_up()  # Resume normal speed
        
        # Move all vehicles
        for vehicle in self.vehicles:
            vehicle.move(dt)

        # Remove vehicles that drove off the end of the road
        self.vehicles = [v for v in self.vehicles if self.road.is_valid_position(v.position)]

        # Basic collision avoidance (still needed for same-lane vehicles)
        self._resolve_collisions()

    # ------------------------------------------------------------------
    # Collision avoidance (simple)
    # ------------------------------------------------------------------

    def _resolve_collisions(self):
        """
        Very basic overlap prevention: if two vehicles in the same lane
        are closer than MIN_GAP, slow the rear vehicle down slightly.
        """
        # Group vehicles by lane for efficient comparison
        by_lane: dict[int, list[Vehicle]] = {}
        for v in self.vehicles:
            by_lane.setdefault(v.lane, []).append(v)

        for lane_vehicles in by_lane.values():
            # Sort front-to-back (highest position first)
            lane_vehicles.sort(key=lambda v: v.position, reverse=True)

            for i in range(len(lane_vehicles) - 1):
                front = lane_vehicles[i]
                rear = lane_vehicles[i + 1]
                gap = front.position - rear.position

                if gap < MIN_GAP:
                    # Slow the rear vehicle to match the front vehicle's speed
                    rear.speed = max(front.speed * 0.9, 5.0)

    # ------------------------------------------------------------------
    # State reporting
    # ------------------------------------------------------------------

    def get_state(self) -> list[dict]:
        """Return a serialisable snapshot of all vehicles."""
        return [
            {
                "id": v.vehicle_id,
                "lane": v.lane,
                "position": round(v.position, 1),
                "speed": round(v.speed, 1),
                "state": v.state,
            }
            for v in sorted(self.vehicles, key=lambda v: v.position, reverse=True)
        ]

    def __repr__(self):
        return f"TrafficManager(vehicles={len(self.vehicles)}, road={self.road})"
