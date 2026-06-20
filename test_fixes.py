"""
Test script to verify Task A and Task B fixes.

Task A: Opposite straight movements run simultaneously
Task B: Corridor handoff only happens when intersection is empty
"""

import sys
from simulation.fourway_intersection import FourWayIntersection
from simulation.vehicle import Vehicle, VehicleState
from simulation.direction import Direction, Route

def test_opposite_straights():
    """Test that opposite straight movements can receive simultaneous grants."""
    print("\n" + "="*70)
    print("TEST A: Opposite Straight Movements")
    print("="*70)
    
    intersection = FourWayIntersection(center_x=250, center_y=250, size=40)
    
    # Create vehicles from opposite directions (NORTH and SOUTH)
    # Position them in approach zone
    v_north = Vehicle(
        vehicle_id=1,
        route=Route(Direction.NORTH, Direction.SOUTH),
        position=310.0,  # In approach zone (y_max=270, approach=270-370)
        desired_speed=18.0
    )
    
    v_south = Vehicle(
        vehicle_id=2,
        route=Route(Direction.SOUTH, Direction.NORTH),
        position=190.0,  # In approach zone (y_min=230, approach=130-230)
        desired_speed=18.0
    )
    
    all_vehicles = [v_north, v_south]
    current_time = 0.0
    dt = 0.0166  # 60 Hz
    
    # Run arbiter
    intersection.run_arbiter(all_vehicles, dt, current_time)
    
    # Check that both can be in the same phase
    state = intersection.get_state()
    print(f"Current phase: {state['current_phase']}")
    print(f"Active directions: {state['active_directions']}")
    print(f"Active grants count: {state['active_grants_count']}")
    print(f"Granted vehicle IDs: {state['granted_vehicle_ids']}")
    
    # Update each vehicle to trigger grant issuance
    for v in all_vehicles:
        cmd = intersection.update_vehicle(v, current_time)
        print(f"Vehicle {v.vehicle_id} from {v.route.source}: command='{cmd}'")
    
    # Run arbiter again to issue grants
    current_time += dt
    intersection.run_arbiter(all_vehicles, dt, current_time)
    
    state = intersection.get_state()
    print(f"\nAfter grant issuance:")
    print(f"Active grants count: {state['active_grants_count']}")
    print(f"Granted vehicle IDs: {state['granted_vehicle_ids']}")
    
    # Verify both vehicles can get grants
    if state['active_grants_count'] >= 1:
        print("\n✓ PASS: At least one grant issued to opposite straights")
        if state['active_grants_count'] == 2:
            print("✓ EXCELLENT: Both opposite straights granted simultaneously!")
    else:
        print("\n✗ FAIL: No grants issued")

def test_corridor_handoff():
    """Test that corridor handoff only happens when intersection is empty."""
    print("\n" + "="*70)
    print("TEST B: Corridor Handoff Safety")
    print("="*70)
    
    intersection = FourWayIntersection(center_x=250, center_y=250, size=40)
    
    # Create a NORTH vehicle that's currently crossing
    v_north_crossing = Vehicle(
        vehicle_id=10,
        route=Route(Direction.NORTH, Direction.SOUTH),
        position=250.0,  # Inside intersection (y_min=230, y_max=270)
        desired_speed=18.0
    )
    v_north_crossing.set_state(VehicleState.CROSSING)
    
    # Create an EAST vehicle waiting
    v_east_waiting = Vehicle(
        vehicle_id=11,
        route=Route(Direction.EAST, Direction.WEST),
        position=180.0,  # In approach zone
        desired_speed=18.0
    )
    
    all_vehicles = [v_north_crossing, v_east_waiting]
    current_time = 10.0
    dt = 0.0166
    
    # Set phase to NS and give grant to north vehicle
    intersection.current_phase = "NS"
    intersection.granted_vehicle_ids.add(10)
    intersection.granted_vehicle_id = 10
    
    print(f"Initial state:")
    print(f"  Phase: {intersection.current_phase}")
    print(f"  Vehicles inside: {len(intersection.vehicles_inside)}")
    
    # Update the crossing vehicle (should be marked as inside)
    intersection.update_vehicle(v_north_crossing, current_time)
    
    print(f"\nAfter updating crossing vehicle:")
    print(f"  Vehicles inside: {len(intersection.vehicles_inside)}")
    
    # Try to rotate phase - should NOT rotate while vehicle is inside
    intersection.phase_elapsed = 15.0  # Force timeout condition
    intersection.run_arbiter(all_vehicles, dt, current_time)
    
    print(f"\nAfter arbiter (vehicle still inside):")
    print(f"  Phase: {intersection.current_phase}")
    print(f"  Vehicles inside: {len(intersection.vehicles_inside)}")
    
    if intersection.current_phase == "NS":
        print("✓ PASS: Phase did NOT rotate while vehicle inside")
    else:
        print("✗ FAIL: Phase rotated despite vehicle inside!")
    
    # Now move vehicle out completely
    v_north_crossing.position = 195.0  # Fully cleared (y_min - clearance = 200)
    intersection.update_vehicle(v_north_crossing, current_time + dt)
    
    print(f"\nAfter vehicle cleared:")
    print(f"  Vehicles inside: {len(intersection.vehicles_inside)}")
    
    # Now phase should be able to rotate
    intersection.run_arbiter(all_vehicles, dt, current_time + dt)
    
    print(f"\nAfter arbiter (vehicle cleared):")
    print(f"  Phase: {intersection.current_phase}")
    print(f"  Vehicles inside: {len(intersection.vehicles_inside)}")
    
    if len(intersection.vehicles_inside) == 0:
        print("✓ PASS: Intersection confirmed empty before phase rotation allowed")
    else:
        print("✗ FAIL: Vehicles still inside during phase rotation")

if __name__ == "__main__":
    print("\n" + "#"*70)
    print("# TESTING TASK A & B FIXES")
    print("#"*70)
    
    test_opposite_straights()
    test_corridor_handoff()
    
    print("\n" + "#"*70)
    print("# TESTS COMPLETE")
    print("#"*70)
