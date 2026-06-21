"""
test_handover_safety.py - Headless stress test for corridor handover safety.
"""

import sys
import os
import time
from pathlib import Path

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))

from simulation.fourway_intersection import FourWayIntersection, PHASE_NS, PHASE_EW
from simulation.fourway_traffic_manager import FourWayTrafficManager
from simulation.direction import Direction


def run_stress_test():
    print("=" * 70)
    print("  CORRIDOR HANDOVER SAFETY STRESS TEST")
    print("  Target: 20 vehicles, 10+ min simulated time, 0 collisions")
    print("=" * 70)

    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    manager = FourWayTrafficManager(intersection, road_length=500.0)

    TARGET_VEHICLES = 20
    DT = 1.0 / 60.0  # 60 Hz
    SIM_DURATION = 660.0  # 11 minutes of simulated time

    # Tracking
    phases_seen = set()
    ns_crossings = 0
    ew_crossings = 0
    corridor_switches = 0
    prev_phase = None
    last_crossing_time = 0.0
    max_drought = 0.0
    ns_parallel = False
    ew_parallel = False

    sim_time = 0.0
    tick_count = 0
    wall_start = time.monotonic()

    print(f"\nRunning {SIM_DURATION}s of simulated time at {1/DT:.0f} Hz...")
    print(f"Total ticks: {int(SIM_DURATION / DT):,}")
    print()

    while sim_time < SIM_DURATION:
        # Auto-spawn to maintain target count
        while len(manager.vehicles) < TARGET_VEHICLES:
            v = manager.spawn_vehicle()
            if v is None:
                break

        # Update simulation
        manager.update(DT)
        sim_time += DT
        tick_count += 1

        # Track phases
        current_phase = intersection.current_phase
        phases_seen.add(current_phase)

        if prev_phase is not None and current_phase != prev_phase:
            if prev_phase in (PHASE_NS, PHASE_EW) and current_phase in (PHASE_NS, PHASE_EW):
                corridor_switches += 1
        prev_phase = current_phase

        # Track crossings by direction
        for v in manager.vehicles:
            if v.has_exited_intersection and not getattr(v, '_counted_for_test', False):
                v._counted_for_test = True
                last_crossing_time = sim_time
                src = v.route.source
                if src in (Direction.NORTH, Direction.SOUTH):
                    ns_crossings += 1
                else:
                    ew_crossings += 1

        # Check for parallel operation
        inside_dirs = set()
        for v in manager.vehicles:
            if intersection.is_in_intersection(v):
                inside_dirs.add(v.route.source)
        if Direction.NORTH in inside_dirs and Direction.SOUTH in inside_dirs:
            ns_parallel = True
        if Direction.EAST in inside_dirs and Direction.WEST in inside_dirs:
            ew_parallel = True

        # Track crossing drought
        drought = sim_time - last_crossing_time if last_crossing_time > 0 else 0
        if drought > max_drought:
            max_drought = drought

        # Early abort on collision - print diagnostic info
        if manager.total_collisions > 0:
            print(f"\n[FAIL] COLLISION DETECTED at sim_time={sim_time:.2f}s (tick {tick_count})")
            print(f"   Phase: {current_phase}, Handover: {intersection._handover_state}")
            print(f"   Vehicles inside: {intersection.vehicles_inside}")
            print(f"   Grants: {intersection.granted_vehicle_ids}")
            print(f"   Committed: {intersection.committed_vehicles}")
            # Print details of colliding vehicles
            for v in manager.vehicles:
                if v.in_collision:
                    print(f"   COLLIDED: id={v.vehicle_id} src={v.route.source} "
                          f"dst={v.route.destination} pos={v.position:.1f} "
                          f"spd={v.current_speed:.1f} state={v.state}")
            # Print all vehicles near intersection
            print("   All vehicles near intersection:")
            for v in manager.vehicles:
                if intersection.is_in_intersection(v) or intersection.is_in_approach_zone(v):
                    in_int = intersection.is_in_intersection(v)
                    has_grant = v.vehicle_id in intersection.granted_vehicle_ids
                    print(f"     id={v.vehicle_id:3d} src={v.route.source:5s} "
                          f"pos={v.position:7.1f} spd={v.current_speed:5.1f} "
                          f"{'INSIDE' if in_int else 'APPROACH':8s} "
                          f"{'GRANT' if has_grant else '     ':5s} "
                          f"state={v.state}")
            break



        # Progress report every 60s of sim time
        if tick_count % (60 * 60) == 0:
            elapsed_wall = time.monotonic() - wall_start
            total_crossings = intersection.total_safe_crossings
            print(f"  [{sim_time:6.1f}s] vehicles={len(manager.vehicles):2d}  "
                  f"crossings={total_crossings:4d}  collisions={manager.total_collisions}  "
                  f"switches={corridor_switches}  phase={current_phase}  "
                  f"handover={intersection._handover_state}  "
                  f"wall={elapsed_wall:.1f}s")

    # Results
    wall_elapsed = time.monotonic() - wall_start
    total_crossings = intersection.total_safe_crossings
    collisions = manager.total_collisions
    deadlocks = intersection.deadlock_recoveries

    print()
    print("=" * 70)
    print("  RESULTS")
    print("=" * 70)
    print(f"  Simulated time:     {sim_time:.1f}s ({sim_time/60:.1f} min)")
    print(f"  Wall time:          {wall_elapsed:.1f}s ({wall_elapsed/60:.1f} min)")
    print(f"  Total ticks:        {tick_count:,}")
    print(f"  Total spawned:      {manager.total_spawned}")
    print(f"  Total crossings:    {total_crossings}")
    print(f"  NS crossings:       {ns_crossings}")
    print(f"  EW crossings:       {ew_crossings}")
    print()
    print(f"  Collisions:         {collisions}")
    print(f"  Failed crossings:   {collisions}")
    print(f"  Corridor switches:  {corridor_switches}")
    print(f"  Deadlock recoveries:{deadlocks}")
    print(f"  Max crossing drought:{max_drought:.1f}s")
    print(f"  NS/SN parallel:     {'YES' if ns_parallel else 'NO'}")
    print(f"  EW/WE parallel:     {'YES' if ew_parallel else 'NO'}")
    print()

    # Pass/Fail
    all_pass = True

    def check(condition, label):
        nonlocal all_pass
        status = "[PASS]" if condition else "[FAIL]"
        if not condition:
            all_pass = False
        print(f"  {status}: {label}")

    check(collisions == 0, f"Zero collisions (got {collisions})")
    check(corridor_switches > 0, f"Corridor switching occurred ({corridor_switches} switches)")
    check(total_crossings > 0, f"Vehicles crossed successfully ({total_crossings} crossings)")
    check(ns_crossings > 0, f"NS corridor had crossings ({ns_crossings})")
    check(ew_crossings > 0, f"EW corridor had crossings ({ew_crossings})")
    check(ns_parallel, "NS/SN parallel operation observed")
    check(ew_parallel, "EW/WE parallel operation observed")
    check(max_drought < 30.0, f"No deadlock (max drought {max_drought:.1f}s < 30s)")

    print()
    if all_pass:
        print("  [PASS] ALL TESTS PASSED - Handover safety verified!")
    else:
        print("  [FAIL] SOME TESTS FAILED - See above for details")
    print("=" * 70)

    return all_pass


if __name__ == "__main__":
    success = run_stress_test()
    sys.exit(0 if success else 1)
