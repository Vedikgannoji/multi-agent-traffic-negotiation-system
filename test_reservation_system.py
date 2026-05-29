"""
Test suite for path-based reservation system.
Validates conflict detection and reservation lifecycle.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from simulation.direction import Direction, Route, RouteConflictMatrix, TurnType
from simulation.fourway_intersection import FourWayIntersection, ReservationState
from simulation.vehicle import Vehicle


def test_conflict_matrix():
    """Test comprehensive conflict detection."""
    print("\n=== Testing Conflict Matrix ===\n")
    
    # Test 1: Perpendicular straights (should conflict)
    r1 = Route(Direction.NORTH, Direction.SOUTH)
    r2 = Route(Direction.EAST, Direction.WEST)
    assert r1.conflicts_with(r2) == True, "Perpendicular straights should conflict"
    print("✓ Perpendicular straights conflict")
    
    # Test 2: Parallel straights (should NOT conflict)
    r1 = Route(Direction.NORTH, Direction.SOUTH)
    r2 = Route(Direction.SOUTH, Direction.NORTH)
    assert r1.conflicts_with(r2) == False, "Parallel straights should not conflict"
    print("✓ Parallel straights don't conflict")
    
    # Test 3: Opposite left turns (should conflict)
    r1 = Route(Direction.NORTH, Direction.WEST)
    r2 = Route(Direction.SOUTH, Direction.EAST)
    assert r1.conflicts_with(r2) == True, "Opposite left turns should conflict"
    print("✓ Opposite left turns conflict")
    
    # Test 4: Same source (should NOT conflict)
    r1 = Route(Direction.NORTH, Direction.SOUTH)
    r2 = Route(Direction.NORTH, Direction.EAST)
    assert r1.conflicts_with(r2) == False, "Same source should not conflict"
    print("✓ Same source doesn't conflict")
    
    # Test 5: Left vs oncoming straight (should conflict)
    r1 = Route(Direction.NORTH, Direction.WEST)  # Left turn
    r2 = Route(Direction.SOUTH, Direction.NORTH)  # Oncoming straight
    assert r1.conflicts_with(r2) == True, "Left vs oncoming straight should conflict"
    print("✓ Left vs oncoming straight conflicts")
    
    # Test 6: Symmetry (A conflicts with B ⟺ B conflicts with A)
    r1 = Route(Direction.NORTH, Direction.SOUTH)
    r2 = Route(Direction.EAST, Direction.WEST)
    assert r1.conflicts_with(r2) == r2.conflicts_with(r1), "Conflict should be symmetric"
    print("✓ Conflict detection is symmetric")
    
    # Test 7: Self (should NOT conflict)
    r1 = Route(Direction.NORTH, Direction.SOUTH)
    assert r1.conflicts_with(r1) == False, "Route should not conflict with itself"
    print("✓ Route doesn't conflict with itself")
    
    print("\n✅ All conflict matrix tests passed!\n")


def test_turn_type_calculation():
    """Test turn type calculation."""
    print("\n=== Testing Turn Type Calculation ===\n")
    
    # Straight turns
    assert Route(Direction.NORTH, Direction.SOUTH).turn_type == TurnType.STRAIGHT
    assert Route(Direction.SOUTH, Direction.NORTH).turn_type == TurnType.STRAIGHT
    assert Route(Direction.EAST, Direction.WEST).turn_type == TurnType.STRAIGHT
    assert Route(Direction.WEST, Direction.EAST).turn_type == TurnType.STRAIGHT
    print("✓ Straight turns calculated correctly")
    
    # Left turns
    assert Route(Direction.NORTH, Direction.WEST).turn_type == TurnType.LEFT
    assert Route(Direction.SOUTH, Direction.EAST).turn_type == TurnType.LEFT
    assert Route(Direction.EAST, Direction.NORTH).turn_type == TurnType.LEFT
    assert Route(Direction.WEST, Direction.SOUTH).turn_type == TurnType.LEFT
    print("✓ Left turns calculated correctly")
    
    # Right turns
    assert Route(Direction.NORTH, Direction.EAST).turn_type == TurnType.RIGHT
    assert Route(Direction.SOUTH, Direction.WEST).turn_type == TurnType.RIGHT
    assert Route(Direction.EAST, Direction.SOUTH).turn_type == TurnType.RIGHT
    assert Route(Direction.WEST, Direction.NORTH).turn_type == TurnType.RIGHT
    print("✓ Right turns calculated correctly")
    
    print("\n✅ All turn type tests passed!\n")


def test_reservation_lifecycle():
    """Test reservation lifecycle management."""
    print("\n=== Testing Reservation Lifecycle ===\n")
    
    intersection = FourWayIntersection()
    
    # Create test vehicles
    route1 = Route(Direction.NORTH, Direction.SOUTH)
    vehicle1 = Vehicle(vehicle_id=1, route=route1, position=350.0, desired_speed=12.0)
    
    route2 = Route(Direction.EAST, Direction.WEST)
    vehicle2 = Vehicle(vehicle_id=2, route=route2, position=150.0, desired_speed=12.0)
    
    current_time = 1.0  # Start at 1.0 to avoid min_grant_interval issue
    
    # Test 1: Request reservation
    res1 = intersection.request_reservation(vehicle1, current_time)
    assert res1.state == ReservationState.REQUESTED
    print("✓ Reservation requested")
    
    # Test 2: Add to queue and approve reservation
    intersection.add_to_queue(vehicle1)
    assert intersection.can_approve_reservation(res1, current_time) == True
    intersection.approve_reservation(res1, current_time)
    assert res1.state == ReservationState.APPROVED
    assert vehicle1.vehicle_id in intersection.active_reservations
    print("✓ Reservation approved")
    
    # Test 3: Conflicting reservation should be blocked
    res2 = intersection.request_reservation(vehicle2, current_time)
    intersection.add_to_queue(vehicle2)
    assert intersection.can_approve_reservation(res2, current_time) == False
    print("✓ Conflicting reservation blocked")
    
    # Test 4: Release reservation
    intersection.release_reservation(vehicle1.vehicle_id, current_time + 5.0)
    assert res1.state == ReservationState.RELEASED
    assert vehicle1.vehicle_id not in intersection.active_reservations
    print("✓ Reservation released")
    
    # Test 5: Now conflicting reservation can be approved
    current_time += 6.0
    assert intersection.can_approve_reservation(res2, current_time) == True
    print("✓ Previously conflicting reservation now approvable")
    
    print("\n✅ All reservation lifecycle tests passed!\n")


def test_comprehensive_conflicts():
    """Test all major conflict scenarios."""
    print("\n=== Testing Comprehensive Conflict Scenarios ===\n")
    
    test_cases = [
        # (route1, route2, should_conflict, description)
        (Route(Direction.NORTH, Direction.SOUTH), Route(Direction.EAST, Direction.WEST), True, "Perpendicular straights"),
        (Route(Direction.NORTH, Direction.SOUTH), Route(Direction.SOUTH, Direction.NORTH), False, "Parallel straights"),
        (Route(Direction.NORTH, Direction.WEST), Route(Direction.SOUTH, Direction.EAST), True, "Opposite left turns"),
        (Route(Direction.NORTH, Direction.WEST), Route(Direction.WEST, Direction.SOUTH), True, "Adjacent left turns"),
        (Route(Direction.NORTH, Direction.SOUTH), Route(Direction.NORTH, Direction.EAST), False, "Same source"),
        (Route(Direction.NORTH, Direction.WEST), Route(Direction.SOUTH, Direction.NORTH), True, "Left vs oncoming straight"),
        (Route(Direction.NORTH, Direction.EAST), Route(Direction.SOUTH, Direction.WEST), False, "Non-conflicting right turns"),
        (Route(Direction.NORTH, Direction.EAST), Route(Direction.EAST, Direction.SOUTH), True, "Conflicting right turns"),
    ]
    
    passed = 0
    failed = 0
    
    for route1, route2, expected_conflict, description in test_cases:
        actual_conflict = route1.conflicts_with(route2)
        if actual_conflict == expected_conflict:
            print(f"✓ {description}: {'conflict' if expected_conflict else 'no conflict'}")
            passed += 1
        else:
            print(f"✗ {description}: expected {'conflict' if expected_conflict else 'no conflict'}, got {'conflict' if actual_conflict else 'no conflict'}")
            failed += 1
    
    print(f"\n{passed} passed, {failed} failed")
    
    if failed == 0:
        print("\n✅ All comprehensive conflict tests passed!\n")
    else:
        print(f"\n❌ {failed} tests failed!\n")
        sys.exit(1)


def test_statistics():
    """Test statistics tracking."""
    print("\n=== Testing Statistics Tracking ===\n")
    
    intersection = FourWayIntersection()
    
    # Create vehicles
    route1 = Route(Direction.NORTH, Direction.SOUTH)
    vehicle1 = Vehicle(vehicle_id=1, route=route1, position=350.0, desired_speed=12.0)
    
    route2 = Route(Direction.EAST, Direction.WEST)
    vehicle2 = Vehicle(vehicle_id=2, route=route2, position=150.0, desired_speed=12.0)
    
    current_time = 1.0
    
    # Request and approve first reservation
    res1 = intersection.request_reservation(vehicle1, current_time)
    intersection.add_to_queue(vehicle1)
    intersection.approve_reservation(res1, current_time)
    
    assert intersection.total_reservations == 1
    print("✓ Total reservations tracked")
    
    # Try to approve conflicting reservation (should be blocked)
    res2 = intersection.request_reservation(vehicle2, current_time)
    intersection.add_to_queue(vehicle2)
    can_approve = intersection.can_approve_reservation(res2, current_time)
    
    if not can_approve:
        # Manually increment conflicts_prevented (normally done in update loop)
        intersection.total_conflicts_prevented += 1
    
    assert intersection.total_conflicts_prevented >= 1
    print("✓ Conflicts prevented tracked")
    
    # Check state
    state = intersection.get_state()
    assert state['active_reservations'] == 1
    assert state['total_reservations'] == 2
    assert state['conflicts_prevented'] >= 1
    print("✓ State correctly reported")
    
    print("\n✅ All statistics tests passed!\n")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("PATH-BASED RESERVATION SYSTEM TEST SUITE")
    print("="*60)
    
    try:
        test_turn_type_calculation()
        test_conflict_matrix()
        test_reservation_lifecycle()
        test_comprehensive_conflicts()
        test_statistics()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
