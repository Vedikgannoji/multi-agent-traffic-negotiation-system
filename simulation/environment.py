"""
environment.py - Main simulation loop.
Initialises the road, spawns vehicles, and runs the update cycle.
"""

import sys
import time
from pathlib import Path

# Support both standalone and package imports
try:
    from simulation.road import Road
    from simulation.traffic_manager import TrafficManager
except ImportError:
    # Running as standalone script
    sys.path.insert(0, str(Path(__file__).parent))
    from road import Road
    from traffic_manager import TrafficManager

# --- Configuration ---
NUM_LANES = 3
ROAD_LENGTH = 500.0      # meters
NUM_VEHICLES = 6
TICK_INTERVAL = 1.0      # seconds per simulation step
MAX_TICKS = 20           # stop after this many steps (0 = run forever)


def print_state(tick: int, state: list[dict]):
    """Pretty-print the current traffic state."""
    print(f"\n--- Tick {tick} ---")
    if not state:
        print("  (no vehicles on road)")
        return
    for v in state:
        bar = "=" * int(v["position"] / 10)  # simple ASCII position bar
        print(f"  V{v['id']:02d} | Lane {v['lane']} | {v['position']:6.1f}m | {v['speed']:5.1f}m/s | [{bar}]")


def run():
    """Entry point for the simulation."""
    road = Road(num_lanes=NUM_LANES, length=ROAD_LENGTH)
    manager = TrafficManager(road)

    print(f"Initialising simulation: {road}")

    # Spawn vehicles spread across the road so they don't all start at 0
    for i in range(NUM_VEHICLES):
        start_pos = i * (ROAD_LENGTH / NUM_VEHICLES)
        manager.spawn_vehicle(position=start_pos)

    print(f"Spawned {NUM_VEHICLES} vehicles.\n")

    tick = 0
    try:
        while True:
            tick += 1
            manager.update(dt=TICK_INTERVAL)
            print_state(tick, manager.get_state())

            if MAX_TICKS and tick >= MAX_TICKS:
                print("\nSimulation complete.")
                break

            time.sleep(TICK_INTERVAL)

    except KeyboardInterrupt:
        print("\nSimulation stopped by user.")


if __name__ == "__main__":
    run()
