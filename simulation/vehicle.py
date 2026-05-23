"""
vehicle.py - Represents a single vehicle in the traffic simulation.
"""


class Vehicle:
    def __init__(self, vehicle_id: int, lane: int, position: float, speed: float):
        """
        vehicle_id : unique identifier
        lane       : current lane number (0-indexed)
        position   : distance along the road (meters)
        speed      : meters per second
        """
        self.vehicle_id = vehicle_id
        self.lane = lane
        self.position = position
        self.speed = speed

    def move(self, dt: float = 1.0):
        """Advance the vehicle forward by speed * dt meters."""
        self.position += self.speed * dt

    def change_lane(self, new_lane: int):
        """Move the vehicle to a different lane."""
        self.lane = new_lane

    def __repr__(self):
        return (
            f"Vehicle(id={self.vehicle_id}, lane={self.lane}, "
            f"pos={self.position:.1f}m, speed={self.speed}m/s)"
        )
