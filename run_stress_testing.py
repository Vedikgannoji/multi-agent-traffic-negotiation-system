import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from simulation.fourway_intersection import FourWayIntersection
from simulation.fourway_traffic_manager import FourWayTrafficManager
from simulation.vehicle import VehicleState, AgentState

def run_simulation_run(density: int, speed: float, target_crossings: int = 300):
    print(f"Starting test run: Density={density}, SpeedMultiplier={speed}x, Target={target_crossings} crossings")
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    manager = FourWayTrafficManager(intersection, road_length=500.0)
    manager.control_mode = "pure_v2v"
    
    # Fixed dt corresponding to 60Hz ticks scaled by speed
    dt = 0.0166 * speed
    
    # Spawn initial vehicles
    spawned = 0
    attempts = 0
    while spawned < density and attempts < 100:
        v = manager.spawn_vehicle()
        if v:
            spawned += 1
        # Update simulator a bit to move vehicles forward so we can spawn more
        manager.update(0.1)
        attempts += 1
        
    print(f"Spawned {len(manager.vehicles)} initial vehicles")
    
    # Main simulation loop
    tick = 0
    while intersection.total_crossings_completed < target_crossings:
        # Auto-spawn to maintain density
        if len(manager.vehicles) < density:
            manager.spawn_vehicle()
            
        manager.update(dt)
        tick += 1
        
        # Safety break if simulation gets stuck (e.g., in a deadlock)
        if tick > 500000:
            print("WARNING: Reached maximum tick count safety limit.")
            break
            
    stats = manager.get_v2v_stats()
    safety = manager.get_safety_stats()
    
    run_result = {
        "density": density,
        "speed": speed,
        "total_crossings": intersection.total_crossings_completed,
        "safe_crossings": intersection.total_safe_crossings,
        "collisions": safety["total_collisions"],
        "negotiations_initiated": stats["negotiations_initiated"],
        "successful_negotiations": stats["successful_negotiations"],
        "yield_decisions": stats["yield_decisions"],
        "avg_negotiation_duration": stats["average_negotiation_duration"],
        "avg_yield_duration": stats["average_yield_duration"]
    }
    
    print(f"Finished test run: Crossings={run_result['total_crossings']}, Safe={run_result['safe_crossings']}, Collisions={run_result['collisions']}")
    print("-" * 50)
    return run_result

def main():
    results = []
    
    # Run a matrix of density and speed combinations
    test_matrix = [
        (5, 1.0),
        (5, 2.0),
        (10, 2.0),
        (10, 4.0),
        (15, 4.0),
        (15, 8.0),
        (20, 8.0)
    ]
    
    print("=" * 80)
    import os
    if os.path.exists("collision_diagnostics.txt"):
        try:
            os.remove("collision_diagnostics.txt")
        except:
            pass
            
    print("RUNNING V2V DECENTRALIZED SIMULATION STRESS TESTING")
    print("=" * 80)
    
    for density, speed in test_matrix:
        res = run_simulation_run(density, speed, target_crossings=300)
        results.append(res)
        
    # Write summary report to file
    summary_file = "stress_test_results.md"
    with open(summary_file, "w") as f:
        f.write("# Stress Test Results Summary\n\n")
        f.write("| Density | Speed | Total Crossings | Safe Crossings | Collisions | Negotiations | Yield Decisions |\n")
        f.write("|---------|-------|-----------------|----------------|------------|--------------|-----------------|\n")
        for r in results:
            f.write(f"| {r['density']} | {r['speed']}x | {r['total_crossings']} | {r['safe_crossings']} | {r['collisions']} | {r['negotiations_initiated']} | {r['yield_decisions']} |\n")
            
    print(f"\nSaved stress test summary to {summary_file}")
    
    # Check if we achieved target safety
    total_crossings = sum(r["total_crossings"] for r in results)
    total_collisions = sum(r["collisions"] for r in results)
    print(f"Total simulated crossings: {total_crossings}")
    print(f"Total collisions: {total_collisions}")
    if total_collisions == 0:
        print("SUCCESS: 0 collisions achieved!")
    else:
        print(f"Collision rate: {total_collisions / total_crossings:.4f} per crossing")

if __name__ == "__main__":
    main()
