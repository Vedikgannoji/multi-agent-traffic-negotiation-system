"""
Quick test to verify intersection system works correctly.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from simulation.intersection import Intersection
from simulation.vehicle import Vehicle, VehicleState

def test_intersection():
    # Create intersection
    intersection = Intersection(center_position=250.0, size=30.0, max_occupancy=2)
    print(f'✓ Created: {intersection}')

    # Create test vehicles
    v1 = Vehicle(1, 0, 200.0, 20.0)  # Approaching
    v2 = Vehicle(2, 1, 245.0, 15.0)  # Inside
    v3 = Vehicle(3, 2, 190.0, 25.0)  # Far away

    # Test vehicle 1 (approaching)
    action1 = intersection.update_vehicle(v1)
    print(f'✓ V1 (pos={v1.position}m): action={action1}, state={v1.state}')

    # Test vehicle 2 (inside)
    action2 = intersection.update_vehicle(v2)
    print(f'✓ V2 (pos={v2.position}m): action={action2}, state={v2.state}')

    # Test vehicle 3 (far)
    action3 = intersection.update_vehicle(v3)
    print(f'✓ V3 (pos={v3.position}m): action={action3}, state={v3.state}')

    # Check intersection state
    state = intersection.get_state()
    print(f'✓ Intersection occupancy: {state["occupancy"]}/{state["max_occupancy"]}')
    print(f'✓ Vehicles inside: {state["vehicles_inside"]}')
    
    # Verify states
    assert v1.state == VehicleState.MOVING, "V1 should be moving (far from intersection)"
    assert v2.state == VehicleState.CROSSING, "V2 should be crossing (inside intersection)"
    assert v3.state == VehicleState.MOVING, "V3 should be moving (far from intersection)"
    
    print('\n✓ All tests passed!')

if __name__ == "__main__":
    test_intersection()
