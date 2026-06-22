"""
Backend API for 4-way intersection traffic simulation.
Runs the simulation with strict coordination and reduced vehicle count.
Includes comprehensive testing and control endpoints.
"""

import sys
import threading
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add parent directory to path so we can import simulation modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.fourway_intersection import FourWayIntersection
from simulation.fourway_traffic_manager import FourWayTrafficManager
from simulation.direction import Direction

# --- Global simulation state ---
intersection = FourWayIntersection(center_x=250.0, center_y=250.0, size=40.0)
manager = FourWayTrafficManager(intersection, road_length=500.0)
simulation_lock = threading.Lock()
simulation_running = False
simulation_paused = False

# Configuration - reduced for better visibility and control
TARGET_VEHICLE_COUNT = 4  # Default target
MAX_VEHICLE_COUNT = 30    # Maximum allowed (for stress testing)

# Simulation speed control (1x, 2x, 4x)
simulation_speed = 1.0  # Default 1x speed

# --- FastAPI app ---
app = FastAPI(title="4-Way Intersection Traffic Simulation API with Testing Controls")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request/Response Models ---
class SpawnRequest(BaseModel):
    """Request model for manual vehicle spawning."""
    destination: Optional[str] = None  # Optional specific destination


class VehicleCountRequest(BaseModel):
    """Request model for updating vehicle count limits."""
    target_count: int
    max_count: Optional[int] = None


class SimulationSpeedRequest(BaseModel):
    """Request model for simulation speed control."""
    speed: float  # 1.0 = normal, 2.0 = 2x, 4.0 = 4x


# --- Simulation thread ---
def simulation_loop():
    """
    Background simulation loop.
    Ticks at a target frequency of 60 Hz.
    Dynamically tracks real elapsed time (real_dt) between ticks and scales it by
    simulation_speed to ensure precise simulation movement speed even with Windows
    scheduler/timer sleeping latency.
    """
    global simulation_running, simulation_paused, TARGET_VEHICLE_COUNT

    TICK_HZ   = 60          # target tick rate - increased from 10 Hz for smooth movement
    TICK_SEC  = 1.0 / TICK_HZ

    # Spawn initial vehicles with small gaps between them
    spawned  = 0
    attempts = 0
    while spawned < TARGET_VEHICLE_COUNT and attempts < 40:
        with simulation_lock:
            v = manager.spawn_vehicle()
            if v:
                spawned += 1
        attempts += 1
        time.sleep(0.15)

    print(f"[OK] Spawned {spawned} initial vehicles")

    last_tick_time = time.monotonic()
    while simulation_running:
        tick_start = time.monotonic()
        real_dt = tick_start - last_tick_time
        last_tick_time = tick_start

        # Cap real_dt at a safe maximum (e.g. 0.1s) to prevent huge jumps if thread is suspended
        real_dt = min(real_dt, 0.1)

        if not simulation_paused:
            with simulation_lock:
                # dt = real elapsed time × speed multiplier
                manager.update(dt=real_dt * simulation_speed)

                # Auto-spawn to maintain target count (one attempt per tick)
                if len(manager.vehicles) < TARGET_VEHICLE_COUNT:
                    v = manager.spawn_vehicle()
                    if v:
                        pass  # spawned silently

        # Sleep for the remainder of the tick
        elapsed = time.monotonic() - tick_start
        sleep_for = max(0.0, TICK_SEC - elapsed)
        if sleep_for > 0:
            time.sleep(sleep_for)


@app.on_event("startup")
def startup_event():
    """Start the simulation when the server starts."""
    global simulation_running
    simulation_running = True
    thread = threading.Thread(target=simulation_loop, daemon=True)
    thread.start()
    print("[OK] 4-Way Intersection simulation started (PATH-BASED RESERVATION)")
    print(f"[OK] Intersection at ({intersection.center_x}, {intersection.center_y})")
    print(f"[OK] Target vehicles: {TARGET_VEHICLE_COUNT}, Max: {MAX_VEHICLE_COUNT}")
    print(f"[OK] Reservation system: Comprehensive conflict detection")
    print(f"[OK] Zero-collision guarantee through trajectory reservation")


@app.on_event("shutdown")
def shutdown_event():
    """Stop the simulation when the server shuts down."""
    global simulation_running
    simulation_running = False
    print("[OK] Simulation thread stopped")


# --- API Endpoints ---

@app.get("/")
def home():
    return {
        "message": "4-Way Intersection Traffic Simulation Running",
        "type": "fourway",
        "mode": "path_based_reservation",
        "target_vehicles": TARGET_VEHICLE_COUNT,
        "max_vehicles": MAX_VEHICLE_COUNT,
        "features": [
            "Path-based trajectory reservation",
            "Comprehensive conflict matrix",
            "Reservation lifecycle management",
            "Zero-collision guarantee"
        ],
        "endpoints": {
            "/traffic/state": "Get current traffic state",
            "/traffic/info": "Get road configuration",
            "/intersection/state": "Get intersection state"
        }
    }


@app.get("/simulation/state")
def get_simulation_state():
    """Return consolidated simulation state in a single payload to minimize network request overhead."""
    with simulation_lock:
        vehicles_state = manager.get_state()
        intersection_state = intersection.get_state()
        safety_stats = manager.get_safety_stats()
        agent_state_counts = manager.get_agent_state_counts()
        control_status = {
            "running":               simulation_running,
            "paused":                simulation_paused,
            "speed":                 simulation_speed,
            "target_vehicle_count":  TARGET_VEHICLE_COUNT,
            "max_vehicle_count":     MAX_VEHICLE_COUNT,
            "current_vehicle_count": len(manager.vehicles),
            "total_spawned":         manager.total_spawned,
        }
    
    return {
        "vehicles": vehicles_state,
        "intersection": intersection_state,
        "safety": safety_stats,
        "agent_states": agent_state_counts,
        "control": control_status,
        "timestamp": time.time()
    }


@app.get("/traffic/state")
def get_traffic_state():
    """Return current positions of all vehicles."""
    with simulation_lock:
        state = manager.get_state()
    
    return {
        "vehicles": state,
        "timestamp": time.time()
    }


@app.get("/traffic/info")
def get_traffic_info():
    """Return road configuration."""
    with simulation_lock:
        by_direction = manager.get_vehicles_by_direction()
    
    return {
        "type": "fourway",
        "mode": "path_based_reservation",
        "road_length": manager.road_length,
        "num_vehicles": len(manager.vehicles),
        "target_vehicles": TARGET_VEHICLE_COUNT,
        "max_vehicles": MAX_VEHICLE_COUNT,
        "vehicles_by_direction": {
            direction: len(vehicles)
            for direction, vehicles in by_direction.items()
        },
        "intersection_center": {
            "x": intersection.center_x,
            "y": intersection.center_y
        }
    }


@app.get("/intersection/state")
def get_intersection_state():
    """Return intersection state."""
    with simulation_lock:
        state = intersection.get_state()
    
    return state


# ========================================
# TESTING & CONTROL ENDPOINTS
# ========================================

@app.post("/spawn/{direction}")
def spawn_vehicle_manual(direction: str, request: Optional[SpawnRequest] = None):
    """
    Manually spawn a vehicle from a specific direction.
    
    Args:
        direction: north, south, east, or west
        request: Optional destination specification
    
    Returns:
        Spawned vehicle information
    """
    # Validate direction
    direction = direction.lower()
    if direction not in Direction.all():
        raise HTTPException(status_code=400, detail=f"Invalid direction: {direction}")
    
    # Check vehicle limit
    with simulation_lock:
        if len(manager.vehicles) >= MAX_VEHICLE_COUNT:
            raise HTTPException(
                status_code=400, 
                detail=f"Maximum vehicle count reached ({MAX_VEHICLE_COUNT})"
            )
        
        # Get destination from request or random
        destination = None
        if request and request.destination:
            destination = request.destination.lower()
            if destination not in Direction.all():
                raise HTTPException(status_code=400, detail=f"Invalid destination: {destination}")
            if destination == direction:
                raise HTTPException(status_code=400, detail="Destination cannot be same as source")
        
        # Spawn vehicle
        vehicle = manager.spawn_vehicle(source=direction, destination=destination)

        if not vehicle:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot spawn from {direction} — spawn point occupied, try again shortly"
            )
        
        return {
            "success": True,
            "vehicle": {
                "id": vehicle.vehicle_id,
                "source": vehicle.route.source,
                "destination": vehicle.route.destination,
                "turn_type": vehicle.route.turn_type,
                "position": vehicle.position,
                "speed": vehicle.speed
            },
            "total_vehicles": len(manager.vehicles)
        }


@app.post("/control/vehicle-count")
def update_vehicle_count(request: VehicleCountRequest):
    """
    Update target and maximum vehicle counts.
    
    Args:
        request: Vehicle count configuration
    
    Returns:
        Updated configuration
    """
    global TARGET_VEHICLE_COUNT, MAX_VEHICLE_COUNT
    
    # Validate
    if request.target_count < 0 or request.target_count > 30:
        raise HTTPException(status_code=400, detail="Target count must be between 0 and 30")
    
    if request.max_count and (request.max_count < request.target_count or request.max_count > 30):
        raise HTTPException(status_code=400, detail="Max count must be >= target and <= 30")
    
    with simulation_lock:
        TARGET_VEHICLE_COUNT = request.target_count
        if request.max_count:
            MAX_VEHICLE_COUNT = request.max_count
        
        return {
            "success": True,
            "target_count": TARGET_VEHICLE_COUNT,
            "max_count": MAX_VEHICLE_COUNT,
            "current_count": len(manager.vehicles)
        }


@app.post("/control/speed")
def update_simulation_speed(request: SimulationSpeedRequest):
    """
    Update simulation speed multiplier.
    
    Args:
        request: Speed configuration (1.0 = normal, 2.0 = 2x, 4.0 = 4x)
    
    Returns:
        Updated speed configuration
    """
    global simulation_speed
    
    # Validate
    if request.speed <= 0 or request.speed > 16.0:
        raise HTTPException(status_code=400, detail="Speed must be between 0.1 and 16.0")
    
    simulation_speed = request.speed
    
    return {
        "success": True,
        "speed": simulation_speed,
        "description": f"{simulation_speed}x speed"
    }


@app.post("/control/pause")
def pause_simulation():
    """
    Pause the simulation.
    
    Returns:
        Pause status
    """
    global simulation_paused
    
    simulation_paused = True
    
    return {
        "success": True,
        "paused": simulation_paused,
        "message": "Simulation paused"
    }


@app.post("/control/resume")
def resume_simulation():
    """
    Resume the simulation.
    
    Returns:
        Resume status
    """
    global simulation_paused
    
    simulation_paused = False
    
    return {
        "success": True,
        "paused": simulation_paused,
        "message": "Simulation resumed"
    }


@app.post("/control/reset")
def reset_simulation():
    """Reset simulation: remove all vehicles and clear all state including collision metrics."""
    with simulation_lock:
        manager.vehicles.clear()
        manager._next_id      = 1
        manager.total_spawned = 0
        manager.total_removed = 0

        # Reset collision tracking
        manager.total_collisions = 0
        manager._active_collision_pairs.clear()
        manager._colliding_ids.clear()

        # Reset intersection state (phase-based arbiter)
        intersection.granted_vehicle_id        = None
        intersection.granted_vehicle_ids.clear()
        intersection.grant_times.clear()
        intersection._grant_corridor.clear()
        intersection.current_phase             = "IDLE"
        intersection.phase_elapsed             = 0.0
        intersection.total_reservations        = 0
        intersection.total_conflicts_prevented = 0
        intersection.deadlock_recoveries       = 0
        intersection.total_crossings_completed = 0
        intersection.total_safe_crossings      = 0
        intersection.vehicles_inside.clear()
        intersection.committed_vehicles.clear()
        intersection.active_reservations.clear()
        intersection.reservations.clear()

        # Reset handover state machine
        intersection._handover_state       = "ACTIVE"
        intersection._clearance_timer      = 0.0
        intersection._pending_phase        = None
        intersection._draining_for_switch  = False

        for direction in Direction.all():
            intersection.queues[direction].clear()

        return {
            "success": True,
            "message": "Simulation reset — all state cleared",
        }


@app.get("/safety/stats")
def get_safety_stats():
    """Return real-time collision and safety accuracy metrics."""
    with simulation_lock:
        return manager.get_safety_stats()


@app.get("/agents/state-counts")
def get_agent_state_counts():
    """Return counts of agents in each state (Phase 1)."""
    with simulation_lock:
        return manager.get_agent_state_counts()


@app.get("/control/status")
def get_control_status():
    """Return current simulation control state including accurate spawn counts."""
    with simulation_lock:
        return {
            "running":               simulation_running,
            "paused":                simulation_paused,
            "speed":                 simulation_speed,
            "target_vehicle_count":  TARGET_VEHICLE_COUNT,
            "max_vehicle_count":     MAX_VEHICLE_COUNT,
            "current_vehicle_count": len(manager.vehicles),
            "total_spawned":         manager.total_spawned,
        }