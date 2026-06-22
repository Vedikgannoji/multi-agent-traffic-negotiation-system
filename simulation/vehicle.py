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

        # V2V identity and communication fields
        self.agent_id = str(vehicle_id)
        self.known_agents = {}
        self.message_inbox = []
        self.message_outbox = []
        self._last_broadcast_time = -1.0

    @property
    def speed(self) -> float:
        return self.current_speed

    @speed.setter
    def speed(self, value: float):
        self.current_speed = max(0.0, min(value, self.max_speed))

    def update_agent_state(self, intersection_center_x: float, intersection_center_y: float,
                          intersection_size: float, is_inside_intersection: bool, dt: float):
        """
        Update the agent state machine based on arbitration commands.
        """
        if self.agent_state == AgentState.COLLIDED or self.state == VehicleState.COLLIDED:
            return
        
        if self.agent_state == AgentState.EXITED:
            return
            
        if self.route.source in ('north', 'south'):
            distance_to_center = abs(self.position - intersection_center_y)
        else:
            distance_to_center = abs(self.position - intersection_center_x)

        # The arbitration engine explicitly sets self.state to WAITING, MOVING, or CROSSING.
        # We must respect that arbitration decision for visualization and metrics.
        if self.state == VehicleState.WAITING:
            self.agent_state = AgentState.WAITING
            self.waiting_time += dt
        elif self.state == VehicleState.CROSSING or is_inside_intersection:
            self.agent_state = AgentState.CROSSING
            self.state = VehicleState.CROSSING
            self.waiting_time = 0.0
        else:
            # self.state == VehicleState.MOVING
            self.waiting_time = 0.0
            if distance_to_center < self.NEGOTIATION_ZONE_DISTANCE:
                self.agent_state = AgentState.NEGOTIATING
            else:
                self.agent_state = AgentState.APPROACHING

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

    def get_2d_position(self, center_x: float = 250.0, center_y: float = 250.0, lane_offset: float = 12.0) -> tuple:
        """Calculate 2D coordinates (x, y) based on 1D position along direction."""
        src = self.route.source
        pos = self.position
        if src == "north":
            return center_x - lane_offset, pos
        elif src == "south":
            return center_x + lane_offset, pos
        elif src == "east":
            return pos, center_y - lane_offset
        else:  # west
            return pos, center_y + lane_offset

    @staticmethod
    def calculate_2d_position(direction: str, position: float, center_x: float = 250.0, center_y: float = 250.0, lane_offset: float = 12.0) -> tuple:
        """Calculate 2D coordinates (x, y) for any arbitrary vehicle direction and position."""
        if direction == "north":
            return center_x - lane_offset, position
        elif direction == "south":
            return center_x + lane_offset, position
        elif direction == "east":
            return position, center_y - lane_offset
        else:  # west
            return position, center_y + lane_offset

    def broadcast_status(self, message_bus, current_time: float, force: bool = False, interval: float = 0.1):
        """Broadcast status message if interval has elapsed since last broadcast."""
        from simulation.communication import VehicleMessage, MessageType
        
        if force or (current_time - self._last_broadcast_time >= interval):
            payload = {
                "position": self.position,
                "speed": self.current_speed,
                "direction": self.route.source,
                "destination": self.route.destination,
                "current_state": self.agent_state.value
            }
            msg = VehicleMessage(
                sender_id=self.agent_id,
                timestamp=current_time,
                message_type=MessageType.STATUS,
                payload=payload
            )
            message_bus.broadcast(msg)
            self.message_outbox.append(msg)
            self._last_broadcast_time = current_time

    def receive_messages(self, message_bus, center_x: float = 250.0, center_y: float = 250.0, lane_offset: float = 12.0, range_threshold: float = 150.0):
        """Receive messages from the message bus and process STATUS messages within range."""
        from simulation.communication import MessageType
        
        messages = message_bus.receive(self.agent_id)
        my_x, my_y = self.get_2d_position(center_x, center_y, lane_offset)
        
        for msg in messages:
            self.message_inbox.append(msg)
            if msg.message_type == MessageType.STATUS:
                sender_dir = msg.payload.get("direction")
                sender_pos = msg.payload.get("position")
                if sender_dir is not None and sender_pos is not None:
                    sender_x, sender_y = self.calculate_2d_position(sender_dir, sender_pos, center_x, center_y, lane_offset)
                    import math
                    dist = math.sqrt((my_x - sender_x) ** 2 + (my_y - sender_y) ** 2)
                    if dist <= range_threshold:
                        self.known_agents[msg.sender_id] = msg.payload
                    else:
                        # Prune if too far
                        self.known_agents.pop(msg.sender_id, None)

    def __repr__(self):
        return (f"VehicleAgent(id={self.vehicle_id}, route={self.route}, "
                f"pos={self.position:.1f}m, spd={self.current_speed:.1f}m/s, "
                f"agent_state={self.agent_state.value}, waiting={self.waiting_time:.1f}s)")


# Alias for backward compatibility
Vehicle = VehicleAgent
