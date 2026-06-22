"""
test_v2v_awareness.py - Unit tests for Phase 2 Stage 2 Vehicle Awareness Layer.
"""

import sys
import math
from pathlib import Path

# Add root folder to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from simulation.communication import MessageType, VehicleMessage
from simulation.vehicle import VehicleAgent, AgentState, VehicleState
from simulation.direction import Route, Direction
from simulation.fourway_intersection import FourWayIntersection
from simulation.fourway_traffic_manager import FourWayTrafficManager
from backend.main import app


def test_awareness_initialization():
    """Verify that new awareness properties are initialized to defaults."""
    route = Route("north", "south")
    v = VehicleAgent(vehicle_id=10, route=route, position=400.0)
    
    assert v.neighbor_count == 0
    assert v.closest_vehicle_id is None
    assert v.closest_vehicle_distance == float('inf')
    assert v.average_neighbor_speed == 0.0
    assert v.local_density == 0.0
    assert v.vehicles_ahead_count == 0
    assert v.vehicles_behind_count == 0
    
    assert v.get_closest_vehicle() is None
    summary = v.get_neighbor_summary()
    assert summary["neighbor_count"] == 0
    assert summary["closest_vehicle_id"] is None
    assert summary["closest_vehicle_distance"] == float('inf')


def test_update_awareness_computation():
    """Verify awareness metric computations based on known_agents data."""
    # Ego vehicle is North -> South (moving downward from 500, y decreasing)
    # Positions: 
    # Center is at (250, 250)
    # Ego is at position = 300.0 (300m along North path).
    # Its 2D coordinates: x = 250 - 12 = 238, y = 300
    ego_route = Route("north", "south")
    ego = VehicleAgent(vehicle_id=1, route=ego_route, position=300.0)
    
    # 1. Neighbor A: same corridor, traveling North -> South (moving downward)
    # Position: 280.0. 2D coordinates: (238, 280)
    # This is ahead of ego (since y=280 < y=300).
    # Distance = 20m. Speed = 10.0
    
    # 2. Neighbor B: same corridor, traveling South -> North (moving upward)
    # Position: 290.0 (traveling upward towards 500). 2D coordinates: (262, 290)
    # This is also ahead of ego along y-axis (since y=290 < y=300, and ego moves down towards 0).
    # Distance: dx = 24, dy = 10, dist = sqrt(24^2 + 10^2) = 26.0m. Speed = 15.0
    
    # 3. Neighbor C: same corridor, traveling North -> South (moving downward)
    # Position: 320.0. 2D coordinates: (238, 320)
    # This is behind ego (since y=320 > y=300).
    # Distance = 20m. Speed = 20.0
    
    # Let's populate known_agents
    ego.known_agents = {
        "2": {
            "position": 280.0,
            "speed": 10.0,
            "direction": "north",
            "destination": "south",
            "current_state": "moving"
        },
        "3": {
            "position": 290.0,
            "speed": 15.0,
            "direction": "south",
            "destination": "north",
            "current_state": "moving"
        },
        "4": {
            "position": 320.0,
            "speed": 20.0,
            "direction": "north",
            "destination": "south",
            "current_state": "moving"
        }
    }
    
    # Update awareness
    ego.update_awareness(center_x=250.0, center_y=250.0, lane_offset=12.0)
    
    # Verify neighbors
    assert ego.neighbor_count == 3
    
    # Check closest vehicle: Neighbor A (ID "2") at distance 20.0 (since Neighbor B distance is 26.0)
    assert ego.closest_vehicle_id == "2"
    assert math.isclose(ego.closest_vehicle_distance, 20.0)
    
    # Check average speed: (10 + 15 + 20) / 3 = 15.0
    assert math.isclose(ego.average_neighbor_speed, 15.0)
    
    # Check density: 3 / 150.0 = 0.02
    assert math.isclose(ego.local_density, 0.02)
    
    # Check ahead and behind counts:
    # Neighbor 2 (y=280) is ahead.
    # Neighbor 3 (y=290) is ahead.
    # Neighbor 4 (y=320) is behind.
    assert ego.vehicles_ahead_count == 2
    assert ego.vehicles_behind_count == 1
    
    # Verify helpers
    assert ego.get_closest_vehicle() == "2"
    summary = ego.get_neighbor_summary()
    assert summary["neighbor_count"] == 3
    assert summary["closest_vehicle_id"] == "2"
    assert math.isclose(summary["closest_vehicle_distance"], 20.0)
    assert summary["vehicles_ahead_count"] == 2
    assert summary["vehicles_behind_count"] == 1


def test_traffic_manager_integration():
    """Verify awareness metric updates and statistics aggregation inside FourWayTrafficManager."""
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    manager = FourWayTrafficManager(intersection, road_length=500.0)
    
    # Reset stats
    manager.total_messages_sent = 0
    manager.total_messages_received = 0
    
    # Spawn two vehicles close to each other
    v1 = manager.spawn_vehicle(source="north", destination="south")
    v1.position = 310.0
    v1._last_broadcast_time = -1.0
    
    v2 = manager.spawn_vehicle(source="north", destination="south")
    v2.position = 290.0
    v2._last_broadcast_time = -1.0
    
    # Tick simulation
    manager.update(dt=0.1)
    
    # They should see each other and update their awareness metrics
    assert v1.neighbor_count == 1
    assert v1.closest_vehicle_id == v2.agent_id
    assert math.isclose(v1.closest_vehicle_distance, 20.0)
    assert v1.vehicles_ahead_count == 1  # v2 is ahead of v1
    assert v1.vehicles_behind_count == 0
    
    # Check aggregated manager statistics
    v2v_stats = manager.get_v2v_stats()
    assert v2v_stats["total_messages_sent"] > 0
    assert v2v_stats["total_messages_received"] > 0
    assert v2v_stats["average_neighbors_per_vehicle"] == 1.0
    assert math.isclose(v2v_stats["average_local_density"], round(1 / 150.0, 4))
    assert math.isclose(v2v_stats["average_closest_vehicle_distance"], 20.0)
    
    # Check serialization
    state = manager.get_state()
    assert len(state) == 2
    v1_state = next(item for item in state if item["id"] == v1.vehicle_id)
    assert v1_state["neighbor_count"] == 1
    assert v1_state["closest_vehicle_id"] == v2.agent_id
    assert v1_state["closest_vehicle_distance"] == 20.0
    assert v1_state["vehicles_ahead_count"] == 1
    
    # Verify exit message accumulator
    # Force v2 to exit: exit north is pos < cy - rl = 0
    sent_before = v2.message_outbox.copy()
    recv_before = v2.message_inbox.copy()
    v2.position = -10.0
    
    # update ticks v2 exit
    manager.update(dt=0.1)
    
    # v2 should be gone from active vehicles
    assert v2 not in manager.vehicles
    # manager's accumulated stats should include v2's messages
    assert manager.total_messages_sent == len(sent_before) + 1
    assert manager.total_messages_received == len(recv_before) + 1


def test_backend_api_integration():
    """Verify that backend state payload contains the aggregated V2V statistics."""
    from backend.main import get_simulation_state, reset_simulation
    
    # Reset simulation
    reset_simulation()
    
    # Get simulation state
    state = get_simulation_state()
    assert "v2v" in state
    v2v = state["v2v"]
    assert "total_messages_sent" in v2v
    assert "total_messages_received" in v2v
    assert "average_neighbors_per_vehicle" in v2v
    assert "average_local_density" in v2v
    assert "average_closest_vehicle_distance" in v2v
    
    assert v2v["total_messages_sent"] == 0
    assert v2v["total_messages_received"] == 0
    
    # Check direct API stats return value
    from backend.main import get_v2v_stats
    direct_stats = get_v2v_stats()
    assert direct_stats["total_messages_sent"] == 0


if __name__ == "__main__":
    print("=" * 60)
    print("Phase 2 Stage 2: V2V Awareness Layer Tests")
    print("=" * 60)
    
    test_awareness_initialization()
    print("✓ test_awareness_initialization PASSED")
    
    test_update_awareness_computation()
    print("✓ test_update_awareness_computation PASSED")
    
    test_traffic_manager_integration()
    print("✓ test_traffic_manager_integration PASSED")
    
    test_backend_api_integration()
    print("✓ test_backend_api_integration PASSED")
    
    print("\n" + "=" * 60)
    print("✅ ALL V2V AWARENESS LAYER TESTS PASSED!")
    print("=" * 60)
