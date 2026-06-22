"""
test_v2v_foundation.py - Unit tests for Phase 2 Stage 1 V2V communication layer.
"""

import sys
import math
from pathlib import Path

# Add root folder to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from simulation.communication import MessageType, VehicleMessage, MessageBus
from simulation.vehicle import VehicleAgent, AgentState, VehicleState
from simulation.direction import Route, Direction
from simulation.fourway_intersection import FourWayIntersection
from simulation.fourway_traffic_manager import FourWayTrafficManager


def test_message_types():
    """Verify that all required message types exist in the Enum."""
    print("Testing MessageType enum...")
    assert hasattr(MessageType, "HELLO")
    assert hasattr(MessageType, "STATUS")
    assert hasattr(MessageType, "INTENT")
    assert hasattr(MessageType, "PRIORITY")
    assert hasattr(MessageType, "YIELD")
    assert hasattr(MessageType, "GRANT")
    
    assert MessageType.HELLO.value == "HELLO"
    assert MessageType.STATUS.value == "STATUS"
    print("✓ MessageType enum OK")


def test_vehicle_message_model():
    """Verify the VehicleMessage model fields and constructor."""
    print("\nTesting VehicleMessage model...")
    payload = {"position": 10.0, "speed": 12.5}
    msg = VehicleMessage(
        sender_id="vehicle_1",
        timestamp=1.25,
        message_type=MessageType.STATUS,
        payload=payload
    )
    
    assert msg.sender_id == "vehicle_1"
    assert msg.timestamp == 1.25
    assert msg.message_type == MessageType.STATUS
    assert msg.payload == payload
    print("✓ VehicleMessage model OK")


def test_message_bus():
    """Verify in-memory MessageBus broadcast, receive, and clear functionality."""
    print("\nTesting MessageBus...")
    bus = MessageBus()
    
    msg1 = VehicleMessage("veh_1", 0.1, MessageType.STATUS, {"val": 1})
    msg2 = VehicleMessage("veh_2", 0.1, MessageType.STATUS, {"val": 2})
    
    bus.broadcast(msg1)
    bus.broadcast(msg2)
    
    # Receiver veh_1 should not receive its own message
    recv_1 = bus.receive("veh_1")
    assert len(recv_1) == 1
    assert recv_1[0].sender_id == "veh_2"
    
    # Receiver veh_2 should not receive its own message
    recv_2 = bus.receive("veh_2")
    assert len(recv_2) == 1
    assert recv_2[0].sender_id == "veh_1"
    
    # Receiver other should receive all
    recv_other = bus.receive("veh_3")
    assert len(recv_other) == 2
    
    # Clear processed
    bus.clear_processed()
    assert len(bus.receive("veh_3")) == 0
    print("✓ MessageBus OK")


def test_vehicle_agent_identity_and_communication_fields():
    """Verify VehicleAgent identity and list properties."""
    print("\nTesting VehicleAgent communication fields...")
    route = Route("north", "south")
    agent = VehicleAgent(vehicle_id=42, route=route, position=100.0)
    
    assert agent.agent_id == "42"
    assert agent.known_agents == {}
    assert agent.message_inbox == []
    assert agent.message_outbox == []
    assert agent._last_broadcast_time == -1.0
    print("✓ VehicleAgent identity and V2V fields OK")


def test_status_broadcast_and_receipt_flow():
    """Verify that STATUS broadcasts are received and update known_agents if within range."""
    print("\nTesting STATUS broadcast and receipt flow...")
    
    # Setup intersection and manager
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    manager = FourWayTrafficManager(intersection, road_length=500.0)
    
    # Spawn vehicle A (North travels downward, starts at cy + rl = 250 + 250 = 500)
    # Spawn vehicle B (South travels upward, starts at cy - rl = 250 - 250 = 0)
    # A position = 400 (150m from center), B position = 100 (150m from center)
    # Distance between them: A is at (238, 400), B is at (262, 100).
    # dx = 24, dy = 300, dist = sqrt(24^2 + 300^2) = ~301m (> 150m V2V range)
    # They should NOT see each other.
    
    vA = manager.spawn_vehicle(source="north", destination="south")
    vB = manager.spawn_vehicle(source="south", destination="north")
    
    vA.position = 300.0  # 50m north of center -> (238, 300)
    vB.position = 200.0  # 50m south of center -> (262, 200)
    # dx = 24, dy = 100, dist = sqrt(24^2 + 100^2) = 102.8m (< 150m V2V range)
    # They should see each other!
    
    # Force broadcast time to be ready
    vA._last_broadcast_time = -1.0
    vB._last_broadcast_time = -1.0
    
    # Run one manager update tick
    manager.update(dt=0.0166)
    
    # Verify broadcast messages are sent
    assert len(vA.message_outbox) > 0
    assert len(vB.message_outbox) > 0
    assert vA.message_outbox[-1].message_type == MessageType.STATUS
    assert vB.message_outbox[-1].message_type == MessageType.STATUS
    
    # Verify messages are in inboxes
    assert len(vA.message_inbox) > 0
    assert len(vB.message_inbox) > 0
    
    # Verify they added each other to known_agents
    assert vB.agent_id in vA.known_agents
    assert vA.agent_id in vB.known_agents
    
    # Verify the payload stored
    payload_A_in_B = vB.known_agents[vA.agent_id]
    assert payload_A_in_B["position"] == 300.0
    assert payload_A_in_B["direction"] == "north"
    
    print("✓ STATUS broadcast & range-based receipt flow OK")


def test_out_of_range_and_exit_pruning():
    """Verify that vehicles are pruned when they move out of range or exit."""
    print("\nTesting out-of-range and exit pruning...")
    
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    manager = FourWayTrafficManager(intersection, road_length=500.0)
    
    vA = manager.spawn_vehicle(source="north", destination="south")
    vB = manager.spawn_vehicle(source="south", destination="north")
    
    vA.position = 255.0  # (238, 255)
    vB.position = 245.0  # (262, 245)
    # Distance is ~26m (<150m) -> should see each other
    
    vA._last_broadcast_time = -1.0
    vB._last_broadcast_time = -1.0
    
    manager.update(dt=0.0166)
    assert vB.agent_id in vA.known_agents
    
    # Move B out of range: B position = 50.0 -> (262, 50)
    # Distance: dy = 205m (> 150m)
    vB.position = 50.0
    
    # Run update tick: B should be pruned from A's known_agents
    manager.update(dt=0.0166)
    assert vB.agent_id not in vA.known_agents
    print("✓ Out of range pruning OK")
    
    # Restore proximity
    vB.position = 245.0
    vA._last_broadcast_time = -1.0
    vB._last_broadcast_time = -1.0
    manager.update(dt=0.0166)
    assert vB.agent_id in vA.known_agents
    
    # Let vB exit the simulation (e.g. exit_threshold for south-to-north is cy + rl = 500.0)
    # South-to-north exits when position > 500
    vB.position = 501.0
    manager.update(dt=0.0166)
    
    # vB should be removed from vehicles list
    assert vB not in manager.vehicles
    # vB should be pruned from A's known_agents
    assert vB.agent_id not in vA.known_agents
    print("✓ Exit pruning OK")


def main():
    print("=" * 60)
    print("Phase 2 Stage 1: V2V Communication Foundation Tests")
    print("=" * 60)
    
    try:
        test_message_types()
        test_vehicle_message_model()
        test_message_bus()
        test_vehicle_agent_identity_and_communication_fields()
        test_status_broadcast_and_receipt_flow()
        test_out_of_range_and_exit_pruning()
        
        print("\n" + "=" * 60)
        print("✅ ALL V2V FOUNDATION TESTS PASSED!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
