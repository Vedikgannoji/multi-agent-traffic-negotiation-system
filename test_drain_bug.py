import sys
import time
from simulation.fourway_intersection import FourWayIntersection
from simulation.fourway_traffic_manager import FourWayTrafficManager
from simulation.direction import Direction, Route

intersection = FourWayIntersection()
manager = FourWayTrafficManager(intersection)

for t in range(39600):
    if t % 60 == 0:
        if len(manager.vehicles) < 20:
            manager.spawn_vehicle(Direction.random_start(), Direction.random_end(Direction.NORTH))
            
    manager.update(1/60.0)
    
    if intersection._handover_state == 'CLEARANCE':
        if not hasattr(manager, 'clearance_ticks'):
            manager.clearance_ticks = 0
        manager.clearance_ticks += 1
        if manager.clearance_ticks > 600:
            print("\nSTUCK IN CLEARANCE!")
            draining_dirs = intersection.PHASE_DIRS.get(intersection._draining_from_phase, intersection._active_dirs())
            print(f"vehicles_inside: {intersection.vehicles_inside}")
            print(f"clearance_timer: {intersection._clearance_timer}")
            for v in manager.vehicles:
                if v.route.source in draining_dirs:
                    print(f"v{v.vehicle_id}: pos={v.position:.2f}, speed={v.current_speed:.2f}, grant={v.vehicle_id in intersection.granted_vehicle_ids}")
                    print(f"   between: {intersection.is_between_stop_and_intersection(v)}, in: {intersection.is_in_intersection(v)}, clear: {intersection.is_fully_clear(v)}")
            sys.exit(1)
    else:
        manager.clearance_ticks = 0
