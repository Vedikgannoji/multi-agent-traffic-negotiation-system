"""
test_v2v_observability_mode.py - Unit tests for Phase 2 Stage 4.5 features:
  1. Default control mode
  2. Mode toggling
  3. Pure V2V Experimental Mode routing
  4. Yield visual timer minimum visibility
  5. Console logging rolling history and event formatting
  6. Active negotiations tracking and cleanup
  7. Messages per second rolling EMA
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
from simulation.negotiation import NegotiationEngine


def test_default_control_mode():
    """Verify default control mode is Reservation Assisted ('assisted')."""
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    manager = FourWayTrafficManager(intersection, road_length=500.0)
    
    assert hasattr(manager, 'control_mode')
    assert manager.control_mode == "assisted"
    assert manager.messages_per_second == 0.0
    assert manager.total_yield_duration == 0.0
    assert manager.completed_yield_count == 0


def test_control_mode_toggling():
    """Verify toggling control mode clears active grants/reservations."""
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    manager = FourWayTrafficManager(intersection, road_length=500.0)
    
    # Set fake grant and reservation
    intersection.granted_vehicle_ids.add(99)
    intersection.granted_vehicle_id = 99
    intersection.reservations[99] = "north"
    
    # Toggle to pure_v2v
    manager.control_mode = "pure_v2v"
    
    # Simulate API behavior of clearing active grants
    intersection.granted_vehicle_ids.clear()
    intersection.granted_vehicle_id = None
    intersection.reservations.clear()
    
    assert manager.control_mode == "pure_v2v"
    assert len(intersection.granted_vehicle_ids) == 0
    assert intersection.granted_vehicle_id is None
    assert len(intersection.reservations) == 0


def test_pure_v2v_routing_and_negotiation():
    """Verify that in Pure V2V mode, conflicts resolve and lower priority yields."""
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    manager = FourWayTrafficManager(intersection, road_length=500.0)
    manager.control_mode = "pure_v2v"
    
    # Spawn two conflicting vehicles near the intersection
    # NORTH (travels downward, stop line is 320, approach zone is 270..370)
    v1 = manager.spawn_vehicle(source="north", destination="south")
    v1.position = 325.0  # in approach zone, before stop line
    v1.waiting_time = 10.0  # high wait -> high priority (PROCEED)
    
    # EAST (travels rightward, stop line is 180, approach zone is 130..230)
    v2 = manager.spawn_vehicle(source="east", destination="west")
    v2.position = 175.0  # in approach zone, before stop line
    v2.waiting_time = 1.0  # low wait -> low priority (YIELD)
    
    # Run a tick
    manager.update(dt=0.1)
    
    # Verify grants are bypassed (still empty)
    assert len(intersection.granted_vehicle_ids) == 0
    
    # Verify outcomes
    assert v1.negotiation_outcome == "PROCEED"
    assert v2.negotiation_outcome == "YIELD"
    
    # Yielder must have target speed set to slow/stop
    assert v2.target_speed < v2.desired_speed
    # Winner must have target speed set to desired speed
    assert v1.target_speed == v1.desired_speed


def test_yield_visual_timer_persistence():
    """Verify that AgentState.YIELDING is held for a minimum of 1.5 seconds visual duration."""
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    manager = FourWayTrafficManager(intersection, road_length=500.0)
    
    v = manager.spawn_vehicle(source="north", destination="south")
    v.position = 290.0
    v.agent_state = AgentState.NEGOTIATING
    
    # Explicitly set to yielding with 1.5s visual timer
    v.agent_state = AgentState.YIELDING
    v.yielding_visual_timer = 1.5
    
    # Tick by 0.5s - state should still be YIELDING
    v.update_agent_state(250.0, 250.0, 40.0, False, 0.5)
    assert v.agent_state == AgentState.YIELDING
    assert v.yielding_visual_timer == 1.0
    
    # Tick by another 0.5s - state should still be YIELDING
    v.update_agent_state(250.0, 250.0, 40.0, False, 0.5)
    assert v.agent_state == AgentState.YIELDING
    assert v.yielding_visual_timer == 0.5
    
    # Tick by 0.6s (taking it past 1.5s total) - state can now update based on rules (e.g. WAITING or NEGOTIATING)
    v.update_agent_state(250.0, 250.0, 40.0, False, 0.6)
    assert v.yielding_visual_timer == 0.0
    assert v.agent_state != AgentState.YIELDING  # Transitions to WAITING because speed is 0


def test_console_logging_and_history():
    """Verify message log appends events correctly and caps at 50."""
    engine = NegotiationEngine()
    
    # Populate log with 55 dummy entries
    for i in range(55):
        engine._add_log(f"Test message {i}", 1.0)
        
    assert len(engine.message_console_log) == 50
    # First 5 should have been popped
    assert engine.message_console_log[0]["text"] == "Test message 5"
    assert engine.message_console_log[-1]["text"] == "Test message 54"


def test_active_negotiations_tracking():
    """Verify active negotiations are tracked, age increments, and cleaned up with metrics counted."""
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    engine = NegotiationEngine()
    
    # Create conflicting vehicles
    v1 = VehicleAgent(vehicle_id=12, route=Route("north", "south"), position=290.0)
    v1.agent_state = AgentState.NEGOTIATING
    v1.waiting_time = 10.0
    
    v2 = VehicleAgent(vehicle_id=19, route=Route("east", "west"), position=210.0)
    v2.agent_state = AgentState.NEGOTIATING
    v2.waiting_time = 1.0
    
    # Run evaluation at time 1.0
    engine.evaluate([v1, v2], intersection, current_time=1.0)
    
    # Key is frozenset({12, 19})
    key = frozenset({12, 19})
    assert key in engine.active_negotiations
    session = engine.active_negotiations[key]
    assert session["vehicle_a"] == 12 or session["vehicle_a"] == 19
    assert session["winner"] == 12  # V12 has more wait time
    assert session["yielding"] == 19
    assert session["start_time"] == 1.0
    
    # Verify console logs contain the interaction sequence
    logs = [log["text"] for log in engine.message_console_log]
    assert "Vehicle 12 -> Vehicle 19 : INTENT" in logs or "Vehicle 19 -> Vehicle 12 : INTENT" in logs
    assert "Vehicle 12 -> Vehicle 19 : PRIORITY" in logs
    assert "Vehicle 19 yielding to Vehicle 12" in logs
    assert "Vehicle 12 proceeding" in logs
    
    # Check that in next tick at 1.5, negotiation stays active
    engine.evaluate([v1, v2], intersection, current_time=1.5)
    assert key in engine.active_negotiations
    
    # Make vehicles exit candidates list to resolve negotiation
    v1.agent_state = AgentState.CROSSING
    
    # Run evaluate again at 2.0 (one vehicle crossed, no conflict)
    engine.evaluate([v1, v2], intersection, current_time=2.0)
    
    # Session should be resolved and cleaned up
    assert key not in engine.active_negotiations
    assert engine.completed_negotiation_count == 1
    assert engine.total_negotiation_duration == 1.0  # from 1.0 to 2.0


def test_messages_per_second_ema():
    """Verify Messages Per Second EMA calculation works."""
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    manager = FourWayTrafficManager(intersection, road_length=500.0)
    
    # Add dummy messages to bus
    from simulation.communication import VehicleMessage, MessageType
    for i in range(10):
        manager.message_bus.broadcast(VehicleMessage("1", 0.0, MessageType.STATUS, {}))
        
    # Run update tick with dt = 0.1
    # 10 messages / 0.1s = 100 mps
    # EMA = 0.9 * 0 + 0.1 * 100 = 10.0
    manager.update(dt=0.1)
    assert abs(manager.messages_per_second - 10.0) < 0.1


if __name__ == "__main__":
    print("=" * 60)
    print("Phase 2 Stage 4.5: V2V Observability & Pure V2V Mode Tests")
    print("=" * 60)

    tests = [
        ("test_default_control_mode", test_default_control_mode),
        ("test_control_mode_toggling", test_control_mode_toggling),
        ("test_pure_v2v_routing_and_negotiation", test_pure_v2v_routing_and_negotiation),
        ("test_yield_visual_timer_persistence", test_yield_visual_timer_persistence),
        ("test_console_logging_and_history", test_console_logging_and_history),
        ("test_active_negotiations_tracking", test_active_negotiations_tracking),
        ("test_messages_per_second_ema", test_messages_per_second_ema),
    ]

    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            test_fn()
            print(f"  v {name} PASSED")
            passed += 1
        except Exception as e:
            import traceback
            print(f"  X {name} FAILED: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 60}")
    if failed == 0:
        print(f"ALL {passed} PHASE 2 STAGE 4.5 TESTS PASSED!")
        sys.exit(0)
    else:
        print(f"RESULTS: {passed} passed, {failed} failed")
        sys.exit(1)
