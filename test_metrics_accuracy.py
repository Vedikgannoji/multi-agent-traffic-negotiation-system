"""
Test script to verify the passing accuracy metric fix.
This test ensures accuracy decreases when collisions occur.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from simulation.fourway_intersection import FourWayIntersection
from simulation.fourway_traffic_manager import FourWayTrafficManager

def test_passing_accuracy_with_collisions():
    """
    Test that passing accuracy correctly reflects collision rate.
    """
    print("="  * 60)
    print("Testing Passing Accuracy Metric")
    print("=" * 60)
    
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    manager = FourWayTrafficManager(intersection, road_length=500.0)
    
    # Scenario: Simulate metrics
    print("\n1. Initial state (no activity)")
    stats = manager.get_safety_stats()
    print(f"   Safe crossings: {stats['total_safe_crossings']}")
    print(f"   Collisions: {stats['total_collisions']}")
    print(f"   Accuracy: {stats['safety_accuracy_pct']}%")
    assert stats['safety_accuracy_pct'] == 100.0, "Should be 100% with no activity"
    print("   ✓ Correct: 100% with no activity")
    
    # Scenario: 10 safe crossings, 0 collisions
    print("\n2. Simulating 10 safe crossings, 0 collisions")
    intersection.total_safe_crossings = 10
    manager.total_collisions = 0
    stats = manager.get_safety_stats()
    print(f"   Safe crossings: {stats['total_safe_crossings']}")
    print(f"   Collisions: {stats['total_collisions']}")
    print(f"   Total attempts: {stats['total_crossing_attempts']}")
    print(f"   Accuracy: {stats['safety_accuracy_pct']}%")
    assert stats['total_crossing_attempts'] == 10, "Total attempts should be 10"
    assert stats['safety_accuracy_pct'] == 100.0, "Should be 100% with no collisions"
    print("   ✓ Correct: 100% (10/10)")
    
    # Scenario: 8 safe crossings, 2 collisions
    print("\n3. Simulating 8 safe crossings, 2 collisions")
    intersection.total_safe_crossings = 8
    manager.total_collisions = 2
    stats = manager.get_safety_stats()
    print(f"   Safe crossings: {stats['total_safe_crossings']}")
    print(f"   Collisions: {stats['total_collisions']}")
    print(f"   Total attempts: {stats['total_crossing_attempts']}")
    print(f"   Failed crossings: {stats['total_failed_crossings']}")
    print(f"   Accuracy: {stats['safety_accuracy_pct']}%")
    assert stats['total_crossing_attempts'] == 10, "Total attempts should be 10"
    assert stats['total_failed_crossings'] == 2, "Failed should equal collisions"
    assert stats['safety_accuracy_pct'] == 80.0, f"Should be 80% but got {stats['safety_accuracy_pct']}%"
    print("   ✓ Correct: 80% (8/10)")
    
    # Scenario: 5 safe crossings, 5 collisions
    print("\n4. Simulating 5 safe crossings, 5 collisions")
    intersection.total_safe_crossings = 5
    manager.total_collisions = 5
    stats = manager.get_safety_stats()
    print(f"   Safe crossings: {stats['total_safe_crossings']}")
    print(f"   Collisions: {stats['total_collisions']}")
    print(f"   Total attempts: {stats['total_crossing_attempts']}")
    print(f"   Accuracy: {stats['safety_accuracy_pct']}%")
    assert stats['total_crossing_attempts'] == 10, "Total attempts should be 10"
    assert stats['safety_accuracy_pct'] == 50.0, f"Should be 50% but got {stats['safety_accuracy_pct']}%"
    print("   ✓ Correct: 50% (5/10)")
    
    # Scenario: 0 safe crossings, 10 collisions (worst case)
    print("\n5. Simulating 0 safe crossings, 10 collisions (worst case)")
    intersection.total_safe_crossings = 0
    manager.total_collisions = 10
    stats = manager.get_safety_stats()
    print(f"   Safe crossings: {stats['total_safe_crossings']}")
    print(f"   Collisions: {stats['total_collisions']}")
    print(f"   Total attempts: {stats['total_crossing_attempts']}")
    print(f"   Accuracy: {stats['safety_accuracy_pct']}%")
    assert stats['total_crossing_attempts'] == 10, "Total attempts should be 10"
    assert stats['safety_accuracy_pct'] == 0.0, f"Should be 0% but got {stats['safety_accuracy_pct']}%"
    print("   ✓ Correct: 0% (0/10)")
    
    # Scenario: Large numbers
    print("\n6. Simulating large numbers: 95 safe, 5 collisions")
    intersection.total_safe_crossings = 95
    manager.total_collisions = 5
    stats = manager.get_safety_stats()
    print(f"   Safe crossings: {stats['total_safe_crossings']}")
    print(f"   Collisions: {stats['total_collisions']}")
    print(f"   Total attempts: {stats['total_crossing_attempts']}")
    print(f"   Accuracy: {stats['safety_accuracy_pct']}%")
    assert stats['total_crossing_attempts'] == 100, "Total attempts should be 100"
    assert stats['safety_accuracy_pct'] == 95.0, f"Should be 95% but got {stats['safety_accuracy_pct']}%"
    print("   ✓ Correct: 95% (95/100)")
    
    print("\n" + "=" * 60)
    print("✅ ALL ACCURACY TESTS PASSED!")
    print("=" * 60)
    print("\nMetric Fix Summary:")
    print("  Old formula: safe / total_crossings")
    print("  New formula: safe / (safe + collisions)")
    print("  Result: Accuracy now correctly decreases with collisions")

def test_hysteresis():
    """
    Test that state transition hysteresis works correctly.
    """
    print("\n" + "=" * 60)
    print("Testing State Transition Hysteresis")
    print("=" * 60)
    
    from simulation.vehicle import VehicleAgent, AgentState
    from simulation.direction import Route
    
    route = Route("north", "south")
    agent = VehicleAgent(vehicle_id=1, route=route, position=280.0)
    
    print("\n1. Vehicle approaching intersection (speed=10 m/s)")
    agent.current_speed = 10.0
    agent.update_agent_state(250.0, 250.0, 40.0, False, 0.1)
    print(f"   State: {agent.agent_state.value}")
    assert agent.agent_state == AgentState.NEGOTIATING, "Should be NEGOTIATING"
    print("   ✓ Correct")
    
    print("\n2. Vehicle slows to 0.5 m/s (at old threshold)")
    agent.current_speed = 0.5
    agent.update_agent_state(250.0, 250.0, 40.0, False, 0.1)
    print(f"   State: {agent.agent_state.value}")
    print(f"   (Old behavior would transition to WAITING)")
    assert agent.agent_state == AgentState.NEGOTIATING, "Should stay NEGOTIATING due to hysteresis"
    print("   ✓ Correct: Stays NEGOTIATING (hysteresis working)")
    
    print("\n3. Vehicle slows to 0.2 m/s (below WAITING threshold)")
    agent.current_speed = 0.2
    agent.update_agent_state(250.0, 250.0, 40.0, False, 0.1)
    print(f"   State: {agent.agent_state.value}")
    assert agent.agent_state == AgentState.WAITING, "Should enter WAITING"
    print("   ✓ Correct: Enters WAITING")
    
    print("\n4. Vehicle speeds up to 0.5 m/s (at old threshold)")
    agent.current_speed = 0.5
    agent.update_agent_state(250.0, 250.0, 40.0, False, 0.1)
    print(f"   State: {agent.agent_state.value}")
    print(f"   (Old behavior would transition to NEGOTIATING)")
    assert agent.agent_state == AgentState.WAITING, "Should stay WAITING due to hysteresis"
    print("   ✓ Correct: Stays WAITING (hysteresis working)")
    
    print("\n5. Vehicle speeds up to 0.8 m/s (above MOVING threshold)")
    agent.current_speed = 0.8
    agent.update_agent_state(250.0, 250.0, 40.0, False, 0.1)
    print(f"   State: {agent.agent_state.value}")
    assert agent.agent_state == AgentState.NEGOTIATING, "Should exit WAITING"
    print("   ✓ Correct: Exits WAITING")
    
    print("\n" + "=" * 60)
    print("✅ HYSTERESIS TESTS PASSED!")
    print("=" * 60)
    print("\nHysteresis Summary:")
    print("  Enter WAITING: speed < 0.3 m/s")
    print("  Exit WAITING:  speed > 0.7 m/s")
    print("  Dead zone: 0.3 - 0.7 m/s prevents oscillation")

def main():
    try:
        test_passing_accuracy_with_collisions()
        test_hysteresis()
        
        print("\n" + "=" * 60)
        print("✅ ALL STABILIZATION TESTS PASSED!")
        print("=" * 60)
        print("\nPhase 1 is now stabilized and ready for Phase 2!")
        
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
