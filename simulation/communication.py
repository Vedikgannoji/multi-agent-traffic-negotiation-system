"""
communication.py - Placeholder for future V2V / V2X communication logic.

V2V  = Vehicle-to-Vehicle
V2X  = Vehicle-to-Everything (infrastructure, pedestrians, cloud, etc.)

These methods are stubs only. No actual communication happens yet.
They will be wired up in a later phase of the project.
"""


class CommunicationModule:
    def broadcast_position(self, vehicle_id: int, position: float, lane: int):
        """
        [STUB] Broadcast a vehicle's current position to nearby vehicles.
        Future: send over a simulated wireless channel (e.g. DSRC / C-V2X).
        """
        pass

    def receive_messages(self, vehicle_id: int) -> list:
        """
        [STUB] Retrieve messages addressed to a specific vehicle.
        Future: return a list of position/intent messages from neighbours.
        """
        return []

    def send_infrastructure_update(self, data: dict):
        """
        [STUB] Send traffic data to road-side infrastructure (V2X).
        Future: push state to traffic lights, toll systems, cloud backend.
        """
        pass

    def request_route(self, vehicle_id: int, destination: str) -> list:
        """
        [STUB] Request an optimal route from a central traffic server.
        Future: return a list of waypoints based on live traffic data.
        """
        return []
