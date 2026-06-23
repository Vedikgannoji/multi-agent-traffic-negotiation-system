"""
test_v2v_negotiation.py - Unit tests for Phase 2 Stage 4 V2V Negotiation Layer.

Tests:
  1. YIELDING state exists in AgentState enum
  2. Conflict detection between cross-corridor vehicles
  3. No conflict for same-corridor vehicles
  4. Priority calculation is deterministic
  5. Negotiation resolution: higher priority → PROCEED, lower → YIELD
  6. YIELD outcome transitions agent to YIELDING state
  7. Grant holders skip negotiation
  8. Negotiation statistics increment correctly
  9. PROCEED message type exists
  10. Zero collisions maintained with negotiation active
  11. Existing V2V features preserved
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


def test_yielding_state_exists():
    """Verify AgentState.YIELDING exists and has the correct value."""
    assert hasattr(AgentState, 'YIELDING')
    assert AgentState.YIELDING.value == "yielding"

    # Verify it's distinct from NEGOTIATING
    assert AgentState.YIELDING != AgentState.NEGOTIATING
    assert AgentState.YIELDING.value != AgentState.NEGOTIATING.value


def test_proceed_message_type_exists():
    """Verify MessageType.PROCEED exists."""
    assert hasattr(MessageType, 'PROCEED')
    assert MessageType.PROCEED.value == "PROCEED"

    # Verify all required negotiation message types
    assert hasattr(MessageType, 'PRIORITY')
    assert hasattr(MessageType, 'YIELD')
    assert hasattr(MessageType, 'PROCEED')


def test_conflict_detection():
    """Two cross-corridor vehicles near intersection → conflict detected."""
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    engine = NegotiationEngine()

    # Create NS vehicle
    v1 = VehicleAgent(vehicle_id=1, route=Route("north", "south"), position=300.0)
    v1.agent_state = AgentState.NEGOTIATING

    # Create EW vehicle
    v2 = VehicleAgent(vehicle_id=2, route=Route("east", "west"), position=200.0)
    v2.agent_state = AgentState.NEGOTIATING

    candidates = engine._get_candidates([v1, v2], intersection)
    conflicts = engine._detect_conflicts(candidates, intersection)

    assert len(conflicts) == 1, f"Expected 1 conflict, got {len(conflicts)}"
    assert (v1 in conflicts[0] and v2 in conflicts[0]), "Conflict should contain both vehicles"


def test_no_conflict_same_corridor():
    """Two same-corridor vehicles → no conflict."""
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    engine = NegotiationEngine()

    # Both NS corridor
    v1 = VehicleAgent(vehicle_id=1, route=Route("north", "south"), position=300.0)
    v1.agent_state = AgentState.NEGOTIATING

    v2 = VehicleAgent(vehicle_id=2, route=Route("south", "north"), position=200.0)
    v2.agent_state = AgentState.NEGOTIATING

    candidates = engine._get_candidates([v1, v2], intersection)
    conflicts = engine._detect_conflicts(candidates, intersection)

    assert len(conflicts) == 0, f"Expected 0 conflicts for same corridor, got {len(conflicts)}"


def test_priority_calculation():
    """Priority calculation is deterministic and based on wait time, distance, queue position."""
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    engine = NegotiationEngine()

    # Vehicle with longer wait time should get higher priority
    v1 = VehicleAgent(vehicle_id=1, route=Route("north", "south"), position=290.0)
    v1.waiting_time = 10.0

    v2 = VehicleAgent(vehicle_id=2, route=Route("north", "south"), position=290.0)
    v2.waiting_time = 2.0

    p1 = engine._calculate_priority(v1, intersection)
    p2 = engine._calculate_priority(v2, intersection)

    assert p1 > p2, f"Vehicle with longer wait ({p1}) should have higher priority than ({p2})"

    # Determinism check: same inputs → same output
    p1_again = engine._calculate_priority(v1, intersection)
    assert p1 == p1_again, "Priority must be deterministic"

    # Vehicle closer to intersection should get higher priority (same wait time)
    v3 = VehicleAgent(vehicle_id=3, route=Route("north", "south"), position=260.0)
    v3.waiting_time = 5.0

    v4 = VehicleAgent(vehicle_id=4, route=Route("north", "south"), position=340.0)
    v4.waiting_time = 5.0

    p3 = engine._calculate_priority(v3, intersection)
    p4 = engine._calculate_priority(v4, intersection)

    assert p3 > p4, f"Closer vehicle ({p3}) should have higher priority than farther ({p4})"


def test_negotiation_resolution():
    """Higher priority gets PROCEED, lower gets YIELD."""
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    engine = NegotiationEngine()

    # NS vehicle with high wait → higher priority
    v1 = VehicleAgent(vehicle_id=1, route=Route("north", "south"), position=290.0)
    v1.agent_state = AgentState.NEGOTIATING
    v1.waiting_time = 15.0

    # EW vehicle with low wait → lower priority
    v2 = VehicleAgent(vehicle_id=2, route=Route("east", "west"), position=210.0)
    v2.agent_state = AgentState.NEGOTIATING
    v2.waiting_time = 1.0

    engine.evaluate([v1, v2], intersection)

    assert v1.negotiation_outcome == "PROCEED", f"High priority vehicle should PROCEED, got {v1.negotiation_outcome}"
    assert v2.negotiation_outcome == "YIELD", f"Low priority vehicle should YIELD, got {v2.negotiation_outcome}"

    assert v1.negotiation_partner_id == str(v2.vehicle_id)
    assert v2.negotiation_partner_id == str(v1.vehicle_id)


def test_yielding_agent_state():
    """YIELD outcome transitions agent to AgentState.YIELDING."""
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    engine = NegotiationEngine()

    v1 = VehicleAgent(vehicle_id=1, route=Route("north", "south"), position=290.0)
    v1.agent_state = AgentState.NEGOTIATING
    v1.waiting_time = 20.0  # High priority → PROCEED

    v2 = VehicleAgent(vehicle_id=2, route=Route("east", "west"), position=210.0)
    v2.agent_state = AgentState.NEGOTIATING
    v2.waiting_time = 0.0  # Low priority → YIELD

    engine.evaluate([v1, v2], intersection)

    assert v2.agent_state == AgentState.YIELDING, f"Yielding vehicle should be in YIELDING state, got {v2.agent_state}"
    # Winner should NOT be forced to YIELDING
    assert v1.agent_state != AgentState.YIELDING, "Proceeding vehicle should not be YIELDING"


def test_grant_holders_skip_negotiation():
    """Vehicles with active grants are not negotiated."""
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    engine = NegotiationEngine()

    v1 = VehicleAgent(vehicle_id=1, route=Route("north", "south"), position=290.0)
    v1.agent_state = AgentState.NEGOTIATING

    v2 = VehicleAgent(vehicle_id=2, route=Route("east", "west"), position=210.0)
    v2.agent_state = AgentState.NEGOTIATING

    # Give v1 a grant — it should be excluded from negotiation
    intersection.granted_vehicle_ids.add(v1.vehicle_id)

    engine.evaluate([v1, v2], intersection)

    assert v1.negotiation_outcome is None, "Grant holder should not get negotiation outcome"
    # v2 alone has no one to conflict with, so no outcome either
    assert v2.negotiation_outcome is None, "Single candidate should not get negotiation outcome"


def test_negotiation_stats():
    """Negotiation counters increment correctly."""
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    engine = NegotiationEngine()

    assert engine.negotiations_initiated == 0
    assert engine.successful_negotiations == 0
    assert engine.yield_decisions == 0

    v1 = VehicleAgent(vehicle_id=1, route=Route("north", "south"), position=290.0)
    v1.agent_state = AgentState.NEGOTIATING
    v1.waiting_time = 10.0

    v2 = VehicleAgent(vehicle_id=2, route=Route("east", "west"), position=210.0)
    v2.agent_state = AgentState.NEGOTIATING
    v2.waiting_time = 1.0

    engine.evaluate([v1, v2], intersection)

    assert engine.negotiations_initiated == 1, f"Expected 1 negotiation initiated, got {engine.negotiations_initiated}"
    assert engine.successful_negotiations == 1, f"Expected 1 successful negotiation, got {engine.successful_negotiations}"
    assert engine.yield_decisions == 1, f"Expected 1 yield decision, got {engine.yield_decisions}"

    # Reset check
    engine.reset()
    assert engine.negotiations_initiated == 0
    assert engine.successful_negotiations == 0
    assert engine.yield_decisions == 0


def test_v2v_message_broadcasting():
    """Negotiation broadcasts PRIORITY, YIELD, and PROCEED V2V messages."""
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    engine = NegotiationEngine()
    bus = MessageBus()

    v1 = VehicleAgent(vehicle_id=1, route=Route("north", "south"), position=290.0)
    v1.agent_state = AgentState.NEGOTIATING
    v1.waiting_time = 10.0

    v2 = VehicleAgent(vehicle_id=2, route=Route("east", "west"), position=210.0)
    v2.agent_state = AgentState.NEGOTIATING
    v2.waiting_time = 1.0

    engine.evaluate([v1, v2], intersection, message_bus=bus, current_time=1.0)

    # Should have broadcast messages
    assert len(bus.messages) > 0, "Expected negotiation messages on the bus"

    # Check message types
    msg_types = {m.message_type for m in bus.messages}
    assert MessageType.PRIORITY in msg_types, "Expected PRIORITY messages"
    assert MessageType.YIELD in msg_types, "Expected YIELD messages"
    assert MessageType.PROCEED in msg_types, "Expected PROCEED messages"


def test_zero_collisions_with_negotiation():
    """Run full simulation for 500 ticks and verify zero collisions."""
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    manager = FourWayTrafficManager(intersection, road_length=500.0)

    # Spawn initial vehicles
    for direction in ["north", "south", "east", "west"]:
        manager.spawn_vehicle(source=direction)

    # Run simulation
    dt = 0.05
    for tick in range(500):
        manager.update(dt=dt)

        # Auto-spawn to keep density up
        if len(manager.vehicles) < 8:
            manager.spawn_vehicle()

    stats = manager.get_safety_stats()
    assert stats["total_collisions"] == 0, f"Expected 0 collisions, got {stats['total_collisions']}"

    # Verify negotiation engine was active
    neg_stats = manager.negotiation_engine.get_stats()
    print(f"  Negotiations initiated: {neg_stats['negotiations_initiated']}")
    print(f"  Successful negotiations: {neg_stats['successful_negotiations']}")
    print(f"  Yield decisions: {neg_stats['yield_decisions']}")
    print(f"  Safe crossings: {stats['total_safe_crossings']}")


def test_existing_v2v_features_preserved():
    """Verify awareness and intent sharing still function with negotiation active."""
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    manager = FourWayTrafficManager(intersection, road_length=500.0)

    v1 = manager.spawn_vehicle(source="north", destination="south")
    v1.position = 310.0
    v1._last_broadcast_time = -1.0

    v2 = manager.spawn_vehicle(source="east", destination="west")
    v2.position = 200.0
    v2._last_broadcast_time = -1.0

    # Tick a few times
    for _ in range(5):
        manager.update(dt=0.1)

    # V2V stats should be populated
    v2v_stats = manager.get_v2v_stats()
    assert v2v_stats["total_messages_sent"] > 0, "V2V messages should still be sent"

    # Agent state counts should include the new yielding key
    state_counts = manager.get_agent_state_counts()
    assert "yielding" in state_counts, "State counts should include 'yielding'"
    assert "negotiating" in state_counts, "State counts should include 'negotiating'"

    # Serialization should include negotiation fields
    state = manager.get_state()
    if len(state) > 0:
        first = state[0]
        assert "negotiation_priority" in first, "get_state should include negotiation_priority"
        assert "negotiation_outcome" in first, "get_state should include negotiation_outcome"
        assert "nearby_negotiating_agents" in first, "get_state should include nearby_negotiating_agents"


def test_negotiation_engine_integration_stats():
    """Verify negotiation stats flow through the traffic manager's get_v2v_stats."""
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    manager = FourWayTrafficManager(intersection, road_length=500.0)

    # Spawn cross-corridor vehicles near the intersection
    v1 = manager.spawn_vehicle(source="north", destination="south")
    v1.position = 290.0  # Near intersection
    v1.waiting_time = 5.0
    v1._last_broadcast_time = -1.0

    v2 = manager.spawn_vehicle(source="east", destination="west")
    v2.position = 210.0  # Near intersection
    v2.waiting_time = 1.0
    v2._last_broadcast_time = -1.0

    # Run several ticks
    for _ in range(20):
        manager.update(dt=0.05)

    v2v_stats = manager.get_v2v_stats()

    # Negotiation stats should be in v2v_stats
    assert "negotiations_initiated" in v2v_stats, "v2v_stats should include negotiations_initiated"
    assert "successful_negotiations" in v2v_stats, "v2v_stats should include successful_negotiations"
    assert "yield_decisions" in v2v_stats, "v2v_stats should include yield_decisions"
    assert "total_negotiating_agents" in v2v_stats, "v2v_stats should include total_negotiating_agents"
    assert "total_yielding_agents" in v2v_stats, "v2v_stats should include total_yielding_agents"


def test_intent_broadcast_with_yielding():
    """Verify that YIELDING state broadcasts intent 'yielding' correctly."""
    route = Route("north", "south")
    v = VehicleAgent(vehicle_id=1, route=route, position=290.0)
    bus = MessageBus()

    # Test YIELDING intent
    v.agent_state = AgentState.YIELDING
    v.broadcast_status(bus, current_time=0.0, force=True)

    assert v.message_outbox[-1].payload["intent"] == "yielding"
    assert v.message_outbox[-1].payload["current_state"] == "yielding"

    # Test NEGOTIATING intent (should now be 'negotiating', not 'yielding')
    v.agent_state = AgentState.NEGOTIATING
    v.broadcast_status(bus, current_time=0.2, force=True)

    assert v.message_outbox[-1].payload["intent"] == "negotiating"
    assert v.message_outbox[-1].payload["current_state"] == "negotiating"


if __name__ == "__main__":
    print("=" * 60)
    print("Phase 2 Stage 4: V2V Negotiation Layer Tests")
    print("=" * 60)

    tests = [
        ("test_yielding_state_exists", test_yielding_state_exists),
        ("test_proceed_message_type_exists", test_proceed_message_type_exists),
        ("test_conflict_detection", test_conflict_detection),
        ("test_no_conflict_same_corridor", test_no_conflict_same_corridor),
        ("test_priority_calculation", test_priority_calculation),
        ("test_negotiation_resolution", test_negotiation_resolution),
        ("test_yielding_agent_state", test_yielding_agent_state),
        ("test_grant_holders_skip_negotiation", test_grant_holders_skip_negotiation),
        ("test_negotiation_stats", test_negotiation_stats),
        ("test_v2v_message_broadcasting", test_v2v_message_broadcasting),
        ("test_zero_collisions_with_negotiation", test_zero_collisions_with_negotiation),
        ("test_existing_v2v_features_preserved", test_existing_v2v_features_preserved),
        ("test_negotiation_engine_integration_stats", test_negotiation_engine_integration_stats),
        ("test_intent_broadcast_with_yielding", test_intent_broadcast_with_yielding),
    ]

    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            test_fn()
            print(f"  v {name} PASSED")
            passed += 1
        except Exception as e:
            print(f"  X {name} FAILED: {e}")
            failed += 1

    print(f"\n{'=' * 60}")
    if failed == 0:
        print(f"ALL {passed} NEGOTIATION LAYER TESTS PASSED!")
    else:
        print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
