"""
Deadlock Audit Test - Tracks reservation lifecycle with detailed logging.

Audit Questions:
1. What condition grants the first vehicle?
2. What condition releases a reservation?
3. Can a reservation remain active after a vehicle leaves the intersection?
4. Can two vehicles mutually block each other forever?
5. Can a vehicle hold a reservation while not moving?
6. Can all queues become blocked because no route is selected as a winner?

Logging captures:
- Reservation granted (vehicle_id, route, reason)
- Reservation denied (vehicle_id, route, reason - overlap or no clearance)
- Reservation released (vehicle_id, route, reason - fully clear or collided)
- Active reservation count per tick
- Vehicles currently inside intersection
"""

import sys
import time
from pathlib import Path
from typing import Set

sys.path.insert(0, str(Path(__file__).parent))

from simulation.fourway_intersection import FourWayIntersection
from simulation.fourway_traffic_manager import FourWayTrafficManager
from simulation.direction import Direction
from simulation.vehicle import VehicleState

# ── Logging state ──────────────────────────────────────────────────────────
logs = []
deadlock_detected = False
deadlock_tick = 0

def log(message: str):
    """Log a message with timestamp."""
    global logs
    timestamp = len(logs)
    logs.append(f"[{timestamp}] {message}")
    print(f"[{timestamp}] {message}")

def audit_reservation_events(intersection: FourWayIntersection, vehicles: list, tick: int, dt: float):
    """
    Audit the reservation system by tracking state changes.
    This runs AFTER the manager.update() to capture the current state.
    """
    # NOTE: audit logs already captured in main loop, no need to duplicate here
    
    # Count vehicles in different states
    waiting_count = sum(1 for v in vehicles if v.state == VehicleState.WAITING)
    crossing_count = sum(1 for v in vehicles if v.state == VehicleState.CROSSING)
    moving_count = sum(1 for v in vehicles if v.state == VehicleState.MOVING)
    collided_count = sum(1 for v in vehicles if v.state == VehicleState.COLLIDED)
    
    # Queue sizes
    queue_status = {d: len(intersection.queues[d]) for d in Direction.all()}
    
    # Occupancy status
    occupancy_status = {d: intersection.path_occupancy[d] for d in Direction.all()}
    
    # Log tick summary
    log(f"TICK {tick}: " +
        f"vehicles=[moving:{moving_count} waiting:{waiting_count} crossing:{crossing_count} collided:{collided_count}] " +
        f"reservations={len(intersection.active_paths)} " +
        f"queues={queue_status} " +
        f"occupancy={occupancy_status}")
    
    # Log each active reservation
    for vid, path in intersection.active_paths.items():
        vehicle = next((v for v in vehicles if v.vehicle_id == vid), None)
        if vehicle:
            grant_time = intersection.grant_times.get(vid, -1)
            duration = tick - grant_time if grant_time >= 0 else -1
            status = f"[INSIDE]" if intersection.is_in_intersection(vehicle) else "[APPROACHING]"
            log(f"  ACTIVE_RES: vid={vid} {vehicle.route.source}->{vehicle.route.destination} " +
                f"speed={vehicle.current_speed:.1f} pos={vehicle.position:.1f} {status} duration={duration}ticks")
    
    # Log each queue
    for direction in Direction.all():
        queue = intersection.queues[direction]
        if queue:
            log(f"  QUEUE[{direction}]: {len(queue)} vehicles")
            for i, v in enumerate(queue):
                log(f"    [{i}] vid={v.vehicle_id} {v.route.source}->{v.route.destination} " +
                    f"speed={v.current_speed:.1f} pos={v.position:.1f}")

def detect_deadlock(intersection: FourWayIntersection, vehicles: list, tick: int) -> bool:
    """
    Detect deadlock condition:
    - Vehicles waiting in approach zones
    - Intersection empty (no vehicles crossing)
    - No active reservations
    - No vehicles moving toward intersection
    """
    global deadlock_detected, deadlock_tick
    
    if deadlock_detected:
        return True
    
    waiting_in_approach = [
        v for v in vehicles
        if v.state == VehicleState.WAITING
        and intersection.is_in_approach_zone(v)
        and v.state != VehicleState.COLLIDED
    ]
    
    has_active_reservations = len(intersection.active_paths) > 0
    vehicles_inside = len(intersection.vehicles_inside) > 0
    
    # Deadlock: vehicles waiting but nothing crossing, nothing reserved
    if waiting_in_approach and not vehicles_inside and not has_active_reservations:
        log(f"\n{'='*80}")
        log(f"DEADLOCK DETECTED AT TICK {tick}")
        log(f"{'='*80}")
        log(f"Waiting vehicles in approach: {len(waiting_in_approach)}")
        for v in waiting_in_approach:
            log(f"  - vid={v.vehicle_id} {v.route.source}->{v.route.destination} waiting_time={v.waiting_time:.2f}s")
        log(f"Active reservations: {len(intersection.active_paths)}")
        log(f"Vehicles inside: {len(intersection.vehicles_inside)}")
        log(f"Path occupancy: {intersection.path_occupancy}")
        log(f"Clearance timers: {intersection.path_clearance_time}")
        
        deadlock_detected = True
        deadlock_tick = tick
        return True
    
    return False

def run_audit():
    """Run the traffic simulation and audit for deadlock."""
    global logs, deadlock_detected
    
    log("="*80)
    log("DEADLOCK AUDIT TEST - Reservation Lifecycle Analysis")
    log("="*80)
    
    # Setup simulation
    intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
    manager = FourWayTrafficManager(intersection, road_length=500.0)
    
    # Spawn 4 initial vehicles
    log(f"Spawning initial vehicles...")
    spawned = 0
    for attempt in range(10):
        v = manager.spawn_vehicle()
        if v:
            spawned += 1
            log(f"  Spawned vehicle {v.vehicle_id}: {v.route.source}->{v.route.destination}")
        if spawned >= 4:
            break
        time.sleep(0.01)  # Small delay between spawns
    
    log(f"Initial spawn complete: {spawned} vehicles")
    log("")
    
    # Simulation parameters
    TICK_HZ = 60
    TICK_SEC = 1.0 / TICK_HZ
    MAX_TICKS = 3000  # ~50 seconds at 60 Hz
    
    # Run simulation
    tick = 0
    try:
        while tick < MAX_TICKS and not deadlock_detected:
            # Simulate one tick
            manager.update(dt=TICK_SEC)
            
            # Always capture reservation events (audit log from intersection)
            for audit_msg in intersection.audit_log:
                log(f"RES: {audit_msg}")
            intersection.audit_log.clear()
            
            # Audit summary every 20 ticks
            if tick % 20 == 0:  # Log every 20 ticks for better performance
                audit_reservation_events(intersection, manager.vehicles, tick, TICK_SEC)
            
            # Check for deadlock every tick
            if tick % 10 == 0:
                if detect_deadlock(intersection, manager.vehicles, tick):
                    break
            
            tick += 1
    
    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        log(traceback.format_exc())
    
    # Final report
    log("")
    log("="*80)
    log("FINAL STATE")
    log("="*80)
    log(f"Total ticks: {tick}")
    log(f"Total vehicles spawned: {manager.total_spawned}")
    log(f"Total vehicles removed: {manager.total_removed}")
    log(f"Vehicles alive: {len(manager.vehicles)}")
    log(f"Total crossings: {intersection.total_crossings_completed}")
    log(f"Safe crossings: {intersection.total_safe_crossings}")
    log(f"Total reservations issued: {intersection.total_reservations}")
    log(f"Conflicts prevented: {intersection.total_conflicts_prevented}")
    log(f"Deadlock recoveries: {intersection.deadlock_recoveries}")
    log("")
    
    if deadlock_detected:
        log(f"DEADLOCK CONFIRMED at tick {deadlock_tick} ({deadlock_tick/TICK_HZ:.2f}s)")
        log("Analysis needed:")
        log("  1. Which vehicles are stuck waiting?")
        log("  2. Which reservation should have been granted?")
        log("  3. Why was that reservation not granted?")
    else:
        log("No deadlock detected within simulation window")
    
    log("")
    
    # Write logs to file
    log_file = Path(__file__).parent / "deadlock_audit_log.txt"
    with open(log_file, "w") as f:
        f.write("\n".join(logs))
    log(f"Logs written to: {log_file}")
    
    return logs, deadlock_detected

if __name__ == "__main__":
    logs, deadlock = run_audit()
    if deadlock:
        print(f"\n✗ DEADLOCK DETECTED - Check deadlock_audit_log.txt for details")
    else:
        print(f"\n✓ No deadlock detected in simulation window")
