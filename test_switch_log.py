import sys
import os
from simulation.fourway_intersection import FourWayIntersection
from simulation.fourway_traffic_manager import FourWayTrafficManager
from simulation.direction import Direction, Route

if os.path.exists("switch_log.txt"):
    os.remove("switch_log.txt")

intersection = FourWayIntersection()
manager = FourWayTrafficManager(intersection)

# Run for 30 simulated seconds (1800 ticks)
for t in range(1800):
    if t % 60 == 0:
        if len(manager.vehicles) < 20:
            manager.spawn_vehicle(Direction.NORTH, Direction.SOUTH)
            manager.spawn_vehicle(Direction.SOUTH, Direction.NORTH)
            manager.spawn_vehicle(Direction.EAST, Direction.WEST)
            manager.spawn_vehicle(Direction.WEST, Direction.EAST)
            
    manager.update(1/60.0)
    
    if os.path.exists("switch_log.txt"):
        print(f"\nCaught switch requested at tick {t} (time {t/60.0:.2f}s)")
        sys.exit(0)
