"""
Test script for 4-way intersection system.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from simulation.direction import Direction, Route, TurnType
from simulation.vehicle import Vehicle
from simulation.fourway_intersection import FourWayIntersection
from simulation.fourway_traffic_manager import FourWayTrafficManager


def test_directions():
    """Test direction and route logic."""
    print("Testing Directions and Routes...")
    
    # Test straight routes
    r1 = Route(Direction.NORTH, Direction.SOUTH)
    assert r1.turn_type == TurnType.STRAIGHT, "N→S should be straight"
    print(f"✓ {r1}")
    
    # Test left turns
    r2 = Route(Direction.NORTH, Direction.WEST)
    assert r2.turn_type == TurnType.LEFT, "N→W should be left"
    print(f"✓ {r2}")
    
    # Test right turns
    r3 = Route(Direction.NORTH, Direction.EAST)
    assert r3.turn_type == TurnType.RIGHT, "N→E should be right"
    print(f"✓ {r3}")
    
    print("✓ All direction tests passed!\n")


def test_conflicts():
    """Test route conflict detection."""
    print("Testing Route Conflicts...")
    
    # Conflicting: opposite straights
    r1 = Route(Direction.NORTH, Direction.SOUTH)
    r2 = Route(Direction.EAST, Direction.WEST)
    assert r1.conflicts_with(r2), "Opposite straights should conflict"
    print(f"✓ {r1} conflicts with {r2}")
    
    # Non-conflicting: same route
    r3 = Route(Direction.NORTH, Direction.SOUTH)
    r4 = Route(Direction.NORTH, Direction.SOUTH)
    assert not r3.conflicts_with(r4), "Same routes shouldn't conflict"
    print(f"✓ {r3} doesn't conflict with {r4}")
    
    # Conflicting: left turn vs oncoming straight
    r5 = Route(Direction.NORTH, Direction.WEST)  # left
    r6 = Route(Direction.SOUTH, Direction.NORTH)  # straight
    assert r5.conflicts_with(r6), "Left turn should conflict with oncoming straight"
    print(f"✓ {r5} conflicts with {r6}")
    
    print("✓ All conflict tests passed!\n")


def test_intersection():
    """Test 4-way intersection logic."""
    print("Testing 4-Way Intersection...")
    
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    print(f"✓ Created: {intersection}")
    
    # Create vehicles at correct positions for approach zone
    # NORTH vehicles move south (decreasing Y), so position > center_y + size/2
    route1 = Route(Direction.NORTH, Direction.SOUTH)
    v1 = Vehicle(1, route1, position=290.0, speed=15.0)  # 290 > 270 (center_y + size/2)
    
    # EAST vehicles move west (increasing X), so position < center_x - size/2
    route2 = Route(Direction.EAST, Direction.WEST)
    v2 = Vehicle(2, route2, position=200.0, speed=15.0)  # 200 < 230 (center_x - size/2)
    
    # Test approach detection
    assert intersection.is_in_approach_zone(v1), "V1 should be in approach zone"
    print(f"✓ V1 detected in approach zone")
    
    # Test entry
    can_enter = intersection.can_enter(v1)
    print(f"✓ V1 can enter: {can_enter}")
    
    # Request entry for v1
    intersection.request_entry(v1)
    assert v1.vehicle_id in intersection.vehicles_inside, "V1 should be inside"
    print(f"✓ V1 entered intersection")
    
    # Try to enter v2 (should conflict)
    can_enter_v2 = intersection.can_enter(v2)
    assert not can_enter_v2, "V2 should not be able to enter (conflicts with V1)"
    print(f"✓ V2 correctly blocked due to conflict")
    
    # Get state
    state = intersection.get_state()
    print(f"✓ Intersection state: occupancy={state['occupancy']}/{state['max_occupancy']}")
    
    print("✓ All intersection tests passed!\n")


def test_traffic_manager():
    """Test traffic manager."""
    print("Testing Traffic Manager...")
    
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    manager = FourWayTrafficManager(intersection, road_length=500.0)
    print(f"✓ Created: {manager}")
    
    # Spawn vehicles
    for i in range(5):
        v = manager.spawn_vehicle()
        print(f"✓ Spawned V{v.vehicle_id}: {v.route}")
    
    assert len(manager.vehicles) == 5, "Should have 5 vehicles"
    print(f"✓ Total vehicles: {len(manager.vehicles)}")
    
    # Update simulation
    manager.update(dt=1.0)
    print(f"✓ Simulation updated")
    
    # Get state
    state = manager.get_state()
    print(f"✓ Got state for {len(state)} vehicles")
    
    # Group by direction
    by_direction = manager.get_vehicles_by_direction()
    for direction, vehicles in by_direction.items():
        if vehicles:
            print(f"  {direction}: {len(vehicles)} vehicles")
    
    print("✓ All traffic manager tests passed!\n")


def main():
    """Run all tests."""
    print("=" * 60)
    print("4-WAY INTERSECTION SYSTEM TESTS")
    print("=" * 60 + "\n")
    
    try:
        test_directions()
        test_conflicts()
        test_intersection()
        test_traffic_manager()
        
        print("=" * 60)
        print("✓ ALL TESTS PASSED!")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
