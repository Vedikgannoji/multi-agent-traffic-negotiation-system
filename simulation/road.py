"""
road.py - Defines the road structure for the simulation.
"""


class Road:
    def __init__(self, num_lanes: int = 3, length: float = 500.0):
        """
        num_lanes : total number of lanes side by side
        length    : road length in meters
        """
        self.num_lanes = num_lanes
        self.length = length

    def is_valid_lane(self, lane: int) -> bool:
        """Return True if the lane number exists on this road."""
        return 0 <= lane < self.num_lanes

    def is_valid_position(self, position: float) -> bool:
        """Return True if the position is within road bounds."""
        return 0.0 <= position <= self.length

    def __repr__(self):
        return f"Road(lanes={self.num_lanes}, length={self.length}m)"
