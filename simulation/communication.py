"""
communication.py - V2V communication layer.
Provides MessageType enum, VehicleMessage model, and in-memory MessageBus.
"""

from enum import Enum


class MessageType(Enum):
    """Supported V2V message types."""
    HELLO = "HELLO"
    STATUS = "STATUS"
    INTENT = "INTENT"
    PRIORITY = "PRIORITY"
    YIELD = "YIELD"
    PROCEED = "PROCEED"
    GRANT = "GRANT"


class VehicleMessage:
    """Represents a V2V message between vehicle agents."""
    def __init__(self, sender_id: str, timestamp: float, message_type: MessageType, payload: dict):
        self.sender_id = sender_id
        self.timestamp = timestamp
        self.message_type = message_type
        self.payload = payload if payload is not None else {}

    def __repr__(self):
        return f"VehicleMessage(sender={self.sender_id}, type={self.message_type.value}, time={self.timestamp:.2f})"


class MessageBus:
    """In-memory message bus for vehicle agent communication."""
    def __init__(self):
        self.messages = []

    def broadcast(self, message: VehicleMessage):
        """Broadcast a message onto the bus."""
        self.messages.append(message)

    def receive(self, agent_id: str) -> list:
        """Receive all messages currently on the bus, except those sent by the caller."""
        return [msg for msg in self.messages if msg.sender_id != agent_id]

    def clear_processed(self):
        """Clear all messages from the bus."""
        self.messages.clear()


# Keep stub class for backward compatibility if imported elsewhere
class CommunicationModule:
    def broadcast_position(self, vehicle_id: int, position: float, lane: int):
        pass

    def receive_messages(self, vehicle_id: int) -> list:
        return []

    def send_infrastructure_update(self, data: dict):
        pass

    def request_route(self, vehicle_id: int, destination: str) -> list:
        return []
