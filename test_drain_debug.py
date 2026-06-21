"""Quick diagnostic to find what blocks DRAINING."""
import sys, os
if sys.platform == 'win32':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

sys.path.insert(0, '.')
from simulation.fourway_intersection import FourWayIntersection, PHASE_NS, PHASE_EW, PHASE_DIRS
from simulation.fourway_traffic_manager import FourWayTrafficManager
from simulation.direction import Direction
from simulation.vehicle import VehicleState

intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
manager = FourWayTrafficManager(intersection, road_length=500.0)

DT = 1.0 / 60.0
TARGET = 20
sim_time = 0.0
draining_start = None

for tick in range(60 * 60 * 5):  # 5 minutes
    while len(manager.vehicles) < TARGET:
        v = manager.spawn_vehicle()
        if v is None:
            break
    manager.update(DT)
    sim_time += DT

    hs = intersection._handover_state
    
    if hs == "DRAINING":
        if draining_start is None:
            draining_start = sim_time
        
        # Print every 1 second
        if tick % 60 == 0:
            draining_dirs = PHASE_DIRS.get(intersection._draining_from_phase, [])
            
            # Find blockers
            blockers = []
            for v in manager.vehicles:
                if v.state == VehicleState.COLLIDED:
                    continue
                if v.route.source not in draining_dirs:
                    continue
                in_int = intersection.is_in_intersection(v)
                between = intersection.is_between_stop_and_intersection(v)
                has_grant = v.vehicle_id in intersection.granted_vehicle_ids
                if in_int or between or has_grant:
                    blockers.append(f"id={v.vehicle_id} src={v.route.source} pos={v.position:.1f} spd={v.current_speed:.2f} in_int={in_int} between={between} grant={has_grant}")
            
            print(f"[{sim_time:.1f}s] DRAINING({sim_time - draining_start:.1f}s) grants={intersection.granted_vehicle_ids} blockers={len(blockers)}")
            for b in blockers:
                print(f"  {b}")
            
            if sim_time - draining_start > 30:
                print("\n30s of DRAINING without switch - something is wrong")
                break
    
    elif hs == "CLEARANCE":
        if tick % 60 == 0:
            print(f"[{sim_time:.1f}s] CLEARANCE timer={intersection._clearance_timer:.2f}")
        draining_start = None
    
    elif hs == "ACTIVE":
        if draining_start is not None:
            print(f"[{sim_time:.1f}s] SWITCH COMPLETE! Phase={intersection.current_phase}")
            draining_start = None

print(f"\nFinal: phase={intersection.current_phase} handover={intersection._handover_state}")
print(f"Collisions: {manager.total_collisions}")
