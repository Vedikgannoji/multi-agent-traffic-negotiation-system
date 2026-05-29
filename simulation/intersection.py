"""
intersection.py - Manages intersection logic and vehicle coordination.
Implements first-come-first-serve access with collision avoidance.
"""

import sys
from pathlib import Path
from collections import deque

# Support both standalone and package imports
try:
    from simulation.vehicle import Vehicle, VehicleState
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from vehicle import Vehicle, VehicleState


class Intersection:
    """
    Manages a single intersection zone where roads cross.
    Coordinates vehicle access using first-come-first-serve.
    """
    
    def __init__(self, center_position: float, size: float = 30.0, max_occupancy: int = 2):
        """
        center_position : position along the road where intersection is located (meters)
        size           : width of the intersection zone (meters)
        max_occupancy  : maximum vehicles allowed inside simultaneously
        """
        self.center = center_position
        self.size = size
        self.start = center_position - size / 2
        self.end = center_position + size / 2
        self.max_occupancy = max_occupancy
        
        # Track vehicles in different zones
        self.vehicles_inside: list[Vehicle] = []
        self.waiting_queue: deque[Vehicle] = deque()
        
        # Safety parameters
        self.approach_distance = 50.0  # distance before intersection to start checking
        self.stop_distance = 5.0       # distance before intersection to stop
    
    def is_in_approach_zone(self, position: float) -> bool:
        """Check if vehicle is approaching the intersection."""
        return self.start - self.approach_distance <= position < self.start
    
    def is_in_intersection(self, position: float) -> bool:
        """Check if vehicle is inside the intersection."""
        return self.start <= position <= self.end
    
    def is_past_intersection(self, position: float) -> bool:
        """Check if vehicle has cleared the intersection."""
        return position > self.end
    
    def can_enter(self) -> bool:
        """Check if intersection has capacity for another vehicle."""
        return len(self.vehicles_inside) < self.max_occupancy
    
    def request_entry(self, vehicle: Vehicle) -> bool:
        """
        Vehicle requests to enter intersection.
        Returns True if allowed, False if must wait.
        """
        if self.can_enter():
            self.vehicles_inside.append(vehicle)
            vehicle.set_state(VehicleState.CROSSING)
            return True
        else:
            if vehicle not in self.waiting_queue:
                self.waiting_queue.append(vehicle)
            vehicle.set_state(VehicleState.WAITING)
            return False
    
    def update_vehicle(self, vehicle: Vehicle) -> str:
        """
        Update vehicle state based on its position relative to intersection.
        Returns the action the vehicle should take: 'stop', 'slow', 'cross', 'continue'
        """
        pos = vehicle.position
        
        # Vehicle has cleared the intersection
        if self.is_past_intersection(pos):
            if vehicle in self.vehicles_inside:
                self.vehicles_inside.remove(vehicle)
            if vehicle in self.waiting_queue:
                self.waiting_queue.remove(vehicle)
            vehicle.set_state(VehicleState.MOVING)
            return 'continue'
        
        # Vehicle is inside the intersection
        if self.is_in_intersection(pos):
            if vehicle not in self.vehicles_inside:
                # Vehicle entered without permission (shouldn't happen)
                self.vehicles_inside.append(vehicle)
            vehicle.set_state(VehicleState.CROSSING)
            return 'cross'
        
        # Vehicle is approaching the intersection
        if self.is_in_approach_zone(pos):
            distance_to_intersection = self.start - pos
            
            # Very close - must stop if can't enter
            if distance_to_intersection <= self.stop_distance:
                if self.request_entry(vehicle):
                    return 'cross'
                else:
                    return 'stop'
            
            # Approaching - slow down if intersection is busy
            else:
                if not self.can_enter():
                    vehicle.set_state(VehicleState.WAITING)
                    return 'slow'
                else:
                    return 'continue'
        
        # Vehicle is before approach zone - normal driving
        vehicle.set_state(VehicleState.MOVING)
        return 'continue'
    
    def get_state(self) -> dict:
        """Return serializable intersection state."""
        return {
            "center": self.center,
            "start": self.start,
            "end": self.end,
            "size": self.size,
            "vehicles_inside": [v.vehicle_id for v in self.vehicles_inside],
            "waiting_count": len(self.waiting_queue),
            "occupancy": len(self.vehicles_inside),
            "max_occupancy": self.max_occupancy
        }
    
    def __repr__(self):
        return (
            f"Intersection(center={self.center}m, "
            f"occupancy={len(self.vehicles_inside)}/{self.max_occupancy})"
        )
