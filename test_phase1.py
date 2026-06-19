"""
Phase 1 Test Script
Tests the VehicleAgent state machine implementation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from simulation.vehicle import VehicleAgent, AgentState, VehicleState
from simulation.direction import Route, Direction
from simulation.fourway_intersection import FourWayIntersection
from simulation.fourway_traffic_manager import FourWayTrafficManager

def test_agent_state_enum():
    """Test that AgentState enum is properly defined."""
    print("Testing AgentState enum...")
    assert AgentState.APPROACHING.value == "approaching"
    assert AgentState.NEGOTIATING.value == "negotiating"
    assert AgentState.WAITING.value == "waiting"
    assert AgentState.CROSSING.value == "crossing"
    assert AgentState.EXITED.value == "exited"
    assert AgentState.COLLIDED.value == "collided"
    print("✓ AgentState enum OK")

def test_vehicle_agent_creation():
    """Test VehicleAgent creation with new properties."""
    print("\nTesting VehicleAgent creation...")
    route = Route("north", "south")
    agent = VehicleAgent(
        vehicle_id=1,
        route=route,
        position=100.0,
        desired_speed=15.0,
        max_speed=25.0
    )
    
    assert agent.vehicle_id == 1
    assert agent.position == 100.0
    assert agent.agent_state == AgentState.APPROACHING
    assert agent.waiting_time == 0.0
    assert agent.priority == 0.5
    print(f"✓ Created agent: {agent}")

def test_state_machine_transitions():
    """Test state machine transitions."""
    print("\nTesting state machine transitions...")
    
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    route = Route("north", "south")
    agent = VehicleAgent(vehicle_id=1, route=route, position=400.0)
    
    # Test 1: Far from intersection -> APPROACHING
    agent.current_speed = 15.0
    agent.update_agent_state(
        intersection_center_x=250.0,
        intersection_center_y=250.0,
        intersection_size=40.0,
        is_inside_intersection=False,
        dt=0.1
    )
    assert agent.agent_state == AgentState.APPROACHING
    print(f"✓ Far from intersection: {agent.agent_state.value}")
    
    # Test 2: Near intersection, moving -> NEGOTIATING
    agent.position = 280.0  # 30m from center
    agent.current_speed = 10.0
    agent.update_agent_state(250.0, 250.0, 40.0, False, 0.1)
    assert agent.agent_state == AgentState.NEGOTIATING
    print(f"✓ Near intersection, moving: {agent.agent_state.value}")
    
    # Test 3: Near intersection, stopped -> WAITING
    agent.current_speed = 0.0
    agent.update_agent_state(250.0, 250.0, 40.0, False, 0.1)
    assert agent.agent_state == AgentState.WAITING
    assert agent.waiting_time > 0.0
    print(f"✓ Near intersection, stopped: {agent.agent_state.value}, waiting={agent.waiting_time:.2f}s")
    
    # Test 4: Inside intersection -> CROSSING
    agent.current_speed = 8.0
    agent.update_agent_state(250.0, 250.0, 40.0, True, 0.1)
    assert agent.agent_state == AgentState.CROSSING
    assert agent.waiting_time == 0.0  # Reset when crossing
    print(f"✓ Inside intersection: {agent.agent_state.value}")
    
    # Test 5: COLLIDED is terminal
    agent.agent_state = AgentState.COLLIDED
    agent.state = VehicleState.COLLIDED
    agent.update_agent_state(250.0, 250.0, 40.0, False, 0.1)
    assert agent.agent_state == AgentState.COLLIDED
    print(f"✓ COLLIDED is terminal: {agent.agent_state.value}")

def test_traffic_manager_integration():
    """Test traffic manager with VehicleAgent."""
    print("\nTesting traffic manager integration...")
    
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    manager = FourWayTrafficManager(intersection, road_length=500.0)
    
    # Spawn vehicles
    v1 = manager.spawn_vehicle(source="north", destination="south")
    v2 = manager.spawn_vehicle(source="south", destination="north")
    
    assert v1 is not None
    assert v2 is not None
    assert len(manager.vehicles) == 2
    print(f"✓ Spawned 2 vehicles")
    
    # Test state counts
    state_counts = manager.get_agent_state_counts()
    assert "approaching" in state_counts
    assert "negotiating" in state_counts
    assert "waiting" in state_counts
    assert "crossing" in state_counts
    assert state_counts["approaching"] == 2  # Both just spawned
    print(f"✓ Agent state counts: {state_counts}")
    
    # Run a few simulation steps
    for _ in range(10):
        manager.update(dt=0.1)
    
    # Check that vehicles are moving and states are updating
    state_counts = manager.get_agent_state_counts()
    print(f"✓ After 10 steps: {state_counts}")
    
    # Test state serialization
    state = manager.get_state()
    assert len(state) > 0
    for vehicle_data in state:
        assert "agent_state" in vehicle_data
        assert "waiting_time" in vehicle_data
        assert "priority" in vehicle_data
        print(f"✓ Vehicle {vehicle_data['id']}: state={vehicle_data['agent_state']}, waiting={vehicle_data['waiting_time']:.2f}s")

def test_backward_compatibility():
    """Test backward compatibility with legacy code."""
    print("\nTesting backward compatibility...")
    
    from simulation.vehicle import Vehicle  # Should be alias for VehicleAgent
    
    route = Route("east", "west")
    vehicle = Vehicle(vehicle_id=99, route=route, position=50.0)
    
    assert isinstance(vehicle, VehicleAgent)
    assert vehicle.vehicle_id == 99
    print("✓ Vehicle alias works")
    
    # Test legacy state property
    vehicle.state = VehicleState.MOVING
    assert vehicle.state == VehicleState.MOVING
    print("✓ Legacy state property works")

def main():
    print("=" * 60)
    print("Phase 1: VehicleAgent State Machine Tests")
    print("=" * 60)
    
    try:
        test_agent_state_enum()
        test_vehicle_agent_creation()
        test_state_machine_transitions()
        test_traffic_manager_integration()
        test_backward_compatibility()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED - Phase 1 Implementation Complete!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Start backend: uvicorn backend.main:app --reload")
        print("2. Start frontend: cd frontend && npm run dev")
        print("3. Verify visual color-coding and dashboard")
        
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
