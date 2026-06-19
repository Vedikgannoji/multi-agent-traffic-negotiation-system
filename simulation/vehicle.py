"""
vehicle.py - Represents a single autonomous vehicle agent with state machine.
Phase 1: Stateful autonomous agents without negotiation or RL.
"""

import sys
from enum import Enum
from pathlib import Path

try:
    from simulation.direction import Route
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from direction import Route


class AgentState(Enum):
    """
    State machine for autonomous vehicle agents.
    Phase 1: Basic state transitions without negotiation.
    """
    APPROACHING = "approaching"  # Moving toward intersection
    NEGOTIATING = "negotiating"  # At intersection zone (placeholder for Phase 2)
    WAITING     = "waiting"      # Blocked, waiting to proceed
    CROSSING    = "crossing"     # Inside intersection
    EXITED      = "exited"       # Left the simulation
    COLLIDED    = "collided"     # Terminal state - frozen after crash


# Legacy state names for backward compatibility
class VehicleState:
    MOVING   = "moving"
    WAITING  = "waiting"
    CROSSING = "crossing"
    COLLIDED = "collided"


class VehicleAgent:
    """
    Autonomous vehicle agent with state machine.
    Phase 1: State transitions without negotiation or V2V communication.
    """
    # Physics constants
    MAX_ACCELERATION      = 2.5   # m/s²
    MAX_DECELERATION      = 4.0   # m/s²
    EMERGENCY_DECELERATION = 6.0  # m/s²
    MIN_SPEED             = 0.0   # m/s

    # Intersection zone threshold for state transitions (meters from center)
    NEGOTIATION_ZONE_DISTANCE = 60.0  # Enter NEGOTIATING when within this distance
    
    # Hysteresis thresholds to prevent state oscillation
    SPEED_THRESHOLD_WAITING = 0.3      # Enter WAITING when speed drops below this
    SPEED_THRESHOLD_MOVING = 0.7       # Exit WAITING when speed exceeds this

    def __init__(self, vehicle_id: int, route: Route, position: float = 0.0,
                 desired_speed: float = None, max_speed: float = 25.0):
        # Core identity
        self.vehicle_id   = vehicle_id
        self.route        = route
        
        # Physics
        self.position     = position
        self.max_speed    = max_speed

        import random
        self.desired_speed  = desired_speed if desired_speed is not None else random.uniform(12.0, 22.0)
        self.current_speed  = 0.0
        self.target_speed   = self.desired_speed

        # Agent state machine (Phase 1)
        self.agent_state              = AgentState.APPROACHING
        self.waiting_time             = 0.0  # Time spent waiting
        self.priority                 = 0.5  # Default priority (for future phases)
        
        # Legacy state for backward compatibility
        self.state                    = VehicleState.MOVING
        
        # Intersection tracking
        self.has_entered_intersection = False
        self.has_exited_intersection  = False
        self.in_collision             = False
        self.is_emergency_braking     = False

        # Collision handling
        self.collision_freeze_timer: float = 0.0

    @property
    def speed(self) -> float:
        return self.current_speed

    @speed.setter
    def speed(self, value: float):
        self.current_speed = max(0.0, min(value, self.max_speed))

    def update_agent_state(self, intersection_center_x: float, intersection_center_y: float,
                          intersection_size: float, is_inside_intersection: bool, dt: float):
        """
        Update the agent state machine based on position and conditions.
        Phase 1: Basic state transitions without negotiation logic.
        """
        # COLLIDED is terminal - never transition out
        if self.agent_state == AgentState.COLLIDED:
            return
        
        # EXITED is terminal
        if self.agent_state == AgentState.EXITED:
            return
        
        # Calculate distance to intersection center
        if self.route.source in ('north', 'south'):
            distance_to_center = abs(self.position - intersection_center_y)
        else:
            distance_to_center = abs(self.position - intersection_center_x)
        
        # State machine transitions with hysteresis
        if is_inside_intersection:
            # Inside intersection -> CROSSING
            self.agent_state = AgentState.CROSSING
            self.state = VehicleState.CROSSING
            self.waiting_time = 0.0
            
        elif distance_to_center < self.NEGOTIATION_ZONE_DISTANCE:
            # Near intersection - use hysteresis to prevent oscillation
            if self.agent_state == AgentState.WAITING:
                # Already waiting - need higher speed to exit waiting state
                if self.current_speed > self.SPEED_THRESHOLD_MOVING:
                    self.agent_state = AgentState.NEGOTIATING
                    self.state = VehicleState.MOVING
                    self.waiting_time = 0.0
                else:
                    # Stay waiting, accumulate time
                    self.waiting_time += dt
            else:
                # Not waiting - check if should enter waiting
                if self.current_speed < self.SPEED_THRESHOLD_WAITING:
                    self.agent_state = AgentState.WAITING
                    self.state = VehicleState.WAITING
                    self.waiting_time += dt
                else:
                    # Moving normally in negotiation zone
                    self.agent_state = AgentState.NEGOTIATING
                    self.state = VehicleState.MOVING
                    self.waiting_time = 0.0
            
        else:
            # Far from intersection -> APPROACHING
            self.agent_state = AgentState.APPROACHING
            self.state = VehicleState.MOVING  # Legacy state
            self.waiting_time = 0.0

    def set_agent_state(self, state: AgentState):
        """Manually set agent state (used for special cases like collision/exit)."""
        if self.agent_state == AgentState.COLLIDED:
            return  # Never override COLLIDED
        self.agent_state = state
        
        # Update legacy state for compatibility
        if state == AgentState.CROSSING:
            self.state = VehicleState.CROSSING
        elif state == AgentState.WAITING:
            self.state = VehicleState.WAITING
        elif state == AgentState.COLLIDED:
            self.state = VehicleState.COLLIDED
        else:
            self.state = VehicleState.MOVING

    def set_target_speed(self, target: float, emergency: bool = False):
        self.target_speed = max(0.0, min(target, self.max_speed))
        self.is_emergency_braking = emergency and target < self.current_speed

    def accelerate_to_desired(self):
        self.set_target_speed(self.desired_speed, emergency=False)

    def slow_to_speed(self, target_speed: float, emergency: bool = False):
        self.set_target_speed(target_speed, emergency=emergency)

    def stop(self, emergency: bool = False):
        self.set_target_speed(0.0, emergency=emergency)

    def set_state(self, state: str):
        """Legacy method for backward compatibility."""
        if self.state == VehicleState.COLLIDED:
            return
        self.state = state

    # Legacy compatibility methods
    def move(self, dt: float = 1.0):       pass
    def slow_down(self, t: float):         self.slow_to_speed(t)
    def speed_up(self):                    self.accelerate_to_desired()
    def update_physics(self, dt: float):   pass

    def __repr__(self):
        return (f"VehicleAgent(id={self.vehicle_id}, route={self.route}, "
                f"pos={self.position:.1f}m, spd={self.current_speed:.1f}m/s, "
                f"agent_state={self.agent_state.value}, waiting={self.waiting_time:.1f}s)")


# Alias for backward compatibility
Vehicle = VehicleAgent
