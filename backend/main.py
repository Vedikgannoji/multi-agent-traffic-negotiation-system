"""
Backend API for traffic simulation.
Runs the simulation in a background thread and exposes state via REST endpoints.
"""

import sys
import threading
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add parent directory to path so we can import simulation modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.road import Road
from simulation.traffic_manager import TrafficManager

# --- Global simulation state ---
road = Road(num_lanes=3, length=500.0)
manager = TrafficManager(road)
simulation_lock = threading.Lock()
simulation_running = False

# --- FastAPI app ---
app = FastAPI(title="Traffic Simulation API")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Simulation thread ---
def simulation_loop():
    """Background thread that continuously updates the simulation."""
    global simulation_running
    
    # Spawn initial vehicles
    for i in range(8):
        start_pos = i * 60.0
        manager.spawn_vehicle(position=start_pos)
    
    while simulation_running:
        with simulation_lock:
            manager.update(dt=1.0)
            
            # Respawn vehicles that left the road to keep traffic flowing
            if len(manager.vehicles) < 8:
                manager.spawn_vehicle(position=0.0)
        
        time.sleep(1.0)  # Update every second


@app.on_event("startup")
def startup_event():
    """Start the simulation when the server starts."""
    global simulation_running
    simulation_running = True
    thread = threading.Thread(target=simulation_loop, daemon=True)
    thread.start()
    print("✓ Simulation thread started")


@app.on_event("shutdown")
def shutdown_event():
    """Stop the simulation when the server shuts down."""
    global simulation_running
    simulation_running = False
    print("✓ Simulation thread stopped")


# --- API Endpoints ---

@app.get("/")
def home():
    return {
        "message": "Traffic Simulation Backend Running",
        "endpoints": {
            "/traffic/state": "Get current traffic state",
            "/traffic/info": "Get road configuration"
        }
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
    return {
        "num_lanes": road.num_lanes,
        "road_length": road.length,
        "num_vehicles": len(manager.vehicles)
    }