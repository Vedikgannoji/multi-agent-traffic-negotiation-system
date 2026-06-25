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
    Phase 2 Stage 4: Includes YIELDING for cooperative negotiation.
    """
    APPROACHING = "approaching"  # Moving toward intersection
    NEGOTIATING = "negotiating"  # At intersection zone, evaluating conflicts
    YIELDING    = "yielding"     # Yielding to higher-priority vehicle
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

        # V2V Awareness properties
        self.neighbor_count = 0
        self.closest_vehicle_id = None
        self.closest_vehicle_distance = float('inf')
        self.average_neighbor_speed = 0.0
        self.local_density = 0.0
        self.vehicles_ahead_count = 0
        self.vehicles_behind_count = 0

        # V2V Intent Sharing properties
        self.has_grant = False
        self.nearby_approaching_agents = 0
        self.nearby_waiting_agents = 0
        self.nearby_crossing_agents = 0
        self.nearby_yielding_agents = 0
        self.nearby_negotiating_agents = 0

        # Negotiation Layer properties (Phase 2 Stage 4)
        self.negotiation_priority = 0.0
        self.negotiation_outcome = None  # "PROCEED", "YIELD", or None
        self.negotiation_partner_id = None
        self.yielding_visual_timer = 0.0
        self.yielding_duration = 0.0

        # V2V Yield Lock — set by NegotiationEngine, enforced by traffic manager
        # When True, this vehicle MUST remain stopped until the lock is released.
        self.v2v_yield_locked = False
        self.v2v_yield_partner_id = None  # ID of the vehicle we are yielding to

    @property
    def speed(self) -> float:
        return self.current_speed

    @speed.setter
    def speed(self, value: float):
        self.current_speed = max(0.0, min(value, self.max_speed))

    def is_past_intersection(self, center_x: float, center_y: float) -> bool:
        """Check if vehicle is past the intersection center in its direction of travel."""
        src = self.route.source
        if src == "north":
            # North travels downward (decreasing position)
            return self.position < center_y
        elif src == "south":
            # South travels upward (increasing position)
            return self.position > center_y
        elif src == "east":
            # East travels rightward (increasing position)
            return self.position > center_x
        elif src == "west":
            # West travels leftward (decreasing position)
            return self.position < center_x
        return False

    def _transition_to(self, new_state: AgentState):
        """
        Transition agent to a new state while auditing and enforcing FSM constraints.
        """
        # If transitioning to the same state, do nothing
        if self.agent_state == new_state:
            return

        # COLLIDED is terminal; no transition out allowed
        if self.agent_state == AgentState.COLLIDED:
            return
        
        # EXITED is terminal; no transition out allowed
        if self.agent_state == AgentState.EXITED:
            return

        # Disallow: CROSSING -> NEGOTIATING
        if self.agent_state == AgentState.CROSSING and new_state == AgentState.NEGOTIATING:
            print(f"[FSM-AUDIT] Denied illegal transition: CROSSING -> NEGOTIATING (Veh {self.vehicle_id})")
            return

        # Disallow: CROSSING -> YIELDING
        if self.agent_state == AgentState.CROSSING and new_state == AgentState.YIELDING:
            print(f"[FSM-AUDIT] Denied illegal transition: CROSSING -> YIELDING (Veh {self.vehicle_id})")
            return


        print(f"[FSM-AUDIT] Veh {self.vehicle_id}: {self.agent_state.value.upper()} -> {new_state.value.upper()}")
        self.agent_state = new_state

    def update_agent_state(self, intersection_center_x: float, intersection_center_y: float,
                          intersection_size: float, is_inside_intersection: bool, dt: float):
        """
        Update the agent state machine based on arbitration commands.
        """
        if self.agent_state == AgentState.COLLIDED or self.state == VehicleState.COLLIDED:
            return
        
        if self.agent_state == AgentState.EXITED:
            return

        # ── V2V Yield Lock: absolute override ─────────────────────────────────
        # When the negotiation engine has locked this vehicle into yielding,
        # the state machine MUST NOT override it. The vehicle stays YIELDING
        # until the lock is released (winner clears the intersection).
        if self.v2v_yield_locked:
            self._transition_to(AgentState.YIELDING)
            self.waiting_time += dt
            self.yielding_duration += dt
            return

        # Decrement visual timer
        if hasattr(self, 'yielding_visual_timer') and self.yielding_visual_timer > 0.0:
            self.yielding_visual_timer = max(0.0, self.yielding_visual_timer - dt)

        # If visual timer is active, hold YIELDING state (unless crossing/collided/exited)
        if hasattr(self, 'yielding_visual_timer') and self.yielding_visual_timer > 0.0:
            if not is_inside_intersection and self.state != VehicleState.CROSSING and not self.has_exited_intersection:
                self._transition_to(AgentState.YIELDING)
                if self.current_speed < self.SPEED_THRESHOLD_WAITING:
                    self.state = VehicleState.WAITING
                    self.waiting_time += dt
                else:
                    self.state = VehicleState.MOVING
                    self.waiting_time = 0.0
                if self.agent_state == AgentState.YIELDING:
                    self.yielding_duration += dt
                return

        # If the vehicle has fully clear/exited the intersection, it goes to EXITED
        if self.has_exited_intersection or self.is_past_intersection(intersection_center_x, intersection_center_y):
            self._transition_to(AgentState.EXITED)
            self.yielding_visual_timer = 0.0
            self.waiting_time = 0.0
            return

        if self.state == VehicleState.CROSSING or is_inside_intersection:
            self._transition_to(AgentState.CROSSING)
            self.waiting_time = 0.0
            return

        if self.state == VehicleState.WAITING:
            self._transition_to(AgentState.WAITING)
            self.waiting_time += dt
            return

        # Normal moving behavior before/approaching the intersection
        if self.route.source in ('north', 'south'):
            distance_to_center = abs(self.position - intersection_center_y)
        else:
            distance_to_center = abs(self.position - intersection_center_x)

        if distance_to_center < self.NEGOTIATION_ZONE_DISTANCE:
            # Near intersection - use hysteresis to prevent oscillation
            if self.agent_state == AgentState.WAITING:
                # Already waiting - need higher speed to exit waiting state
                if self.current_speed > self.SPEED_THRESHOLD_MOVING:
                    self._transition_to(AgentState.NEGOTIATING)
                    self.waiting_time = 0.0
                else:
                    # Stay waiting, accumulate time
                    self.waiting_time += dt
            else:
                # Not waiting - check if should enter waiting
                if self.current_speed < self.SPEED_THRESHOLD_WAITING:
                    self._transition_to(AgentState.WAITING)
                    self.waiting_time += dt
                else:
                    # Moving normally in negotiation zone
                    self._transition_to(AgentState.NEGOTIATING)
                    self.waiting_time = 0.0
        else:
            # Far from intersection -> APPROACHING
            self._transition_to(AgentState.APPROACHING)
            self.waiting_time = 0.0

        if self.agent_state == AgentState.YIELDING:
            self.yielding_duration += dt

    def set_agent_state(self, state: AgentState):
        """Manually set agent state (used for special cases like collision/exit)."""
        self._transition_to(state)
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
            intent = "unknown"
            if self.agent_state == AgentState.APPROACHING:
                intent = "approaching"
            elif self.agent_state == AgentState.WAITING:
                intent = "waiting"
            elif self.agent_state == AgentState.CROSSING:
                intent = "crossing"
            elif self.agent_state == AgentState.NEGOTIATING:
                intent = "negotiating"
            elif self.agent_state == AgentState.YIELDING:
                intent = "yielding"

            corridor = "NS" if self.route.source in ("north", "south") else "EW"

            payload = {
                "position": self.position,
                "speed": self.current_speed,
                "direction": self.route.source,
                "destination": self.route.destination,
                "current_state": self.agent_state.value,
                "intent": intent,
                "corridor": corridor,
                "has_grant": self.has_grant,
                "negotiation_priority": self.negotiation_priority,
                "negotiation_outcome": self.negotiation_outcome
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

    def update_awareness(self, center_x: float = 250.0, center_y: float = 250.0, lane_offset: float = 12.0):
        """Update awareness properties based on current known_agents."""
        import math
        
        self.neighbor_count = len(self.known_agents)
        
        if not self.known_agents:
            self.closest_vehicle_id = None
            self.closest_vehicle_distance = float('inf')
            self.average_neighbor_speed = 0.0
            self.local_density = 0.0
            self.vehicles_ahead_count = 0
            self.vehicles_behind_count = 0
            self.nearby_approaching_agents = 0
            self.nearby_waiting_agents = 0
            self.nearby_crossing_agents = 0
            self.nearby_yielding_agents = 0
            self.nearby_negotiating_agents = 0
            return

        my_x, my_y = self.get_2d_position(center_x, center_y, lane_offset)
        
        closest_id = None
        min_dist = float('inf')
        total_speed = 0.0
        ahead_count = 0
        behind_count = 0
        
        approaching_agents = 0
        waiting_agents = 0
        crossing_agents = 0
        yielding_agents = 0
        negotiating_agents = 0

        my_dir = self.route.source
        is_ns = my_dir in ("north", "south")
        
        for aid, info in self.known_agents.items():
            other_dir = info.get("direction")
            other_pos = info.get("position")
            other_speed = info.get("speed", 0.0)
            other_intent = info.get("intent", "unknown")
            
            total_speed += other_speed
            
            if other_intent == "approaching":
                approaching_agents += 1
            elif other_intent == "waiting":
                waiting_agents += 1
            elif other_intent == "crossing":
                crossing_agents += 1
            elif other_intent == "yielding":
                yielding_agents += 1
            elif other_intent == "negotiating":
                negotiating_agents += 1

            # 2D coordinates for distance
            other_x, other_y = self.calculate_2d_position(other_dir, other_pos, center_x, center_y, lane_offset)
            dist = math.sqrt((my_x - other_x) ** 2 + (my_y - other_y) ** 2)
            
            if dist < min_dist:
                min_dist = dist
                closest_id = aid
                
            # Corridor check
            other_is_ns = other_dir in ("north", "south")
            if is_ns == other_is_ns:
                # Same travel corridor
                if my_dir == "north":
                    if other_y < my_y:
                        ahead_count += 1
                    elif other_y > my_y:
                        behind_count += 1
                elif my_dir == "south":
                    if other_y > my_y:
                        ahead_count += 1
                    elif other_y < my_y:
                        behind_count += 1
                elif my_dir == "east":
                    if other_x > my_x:
                        ahead_count += 1
                    elif other_x < my_x:
                        behind_count += 1
                elif my_dir == "west":
                    if other_x < my_x:
                        ahead_count += 1
                    elif other_x > my_x:
                        behind_count += 1
                        
        self.closest_vehicle_id = closest_id
        self.closest_vehicle_distance = min_dist
        self.average_neighbor_speed = total_speed / self.neighbor_count
        self.local_density = self.neighbor_count / 150.0
        self.vehicles_ahead_count = ahead_count
        self.vehicles_behind_count = behind_count
        
        self.nearby_approaching_agents = approaching_agents
        self.nearby_waiting_agents = waiting_agents
        self.nearby_crossing_agents = crossing_agents
        self.nearby_yielding_agents = yielding_agents
        self.nearby_negotiating_agents = negotiating_agents

    def get_closest_vehicle(self) -> str:
        """Return the vehicle ID of the closest vehicle in communication range."""
        return self.closest_vehicle_id

    def get_neighbor_summary(self) -> dict:
        """Return a dictionary summary of all neighbor-related awareness metrics."""
        return {
            "neighbor_count": self.neighbor_count,
            "closest_vehicle_id": self.closest_vehicle_id,
            "closest_vehicle_distance": self.closest_vehicle_distance,
            "average_neighbor_speed": self.average_neighbor_speed,
            "local_density": self.local_density,
            "vehicles_ahead_count": self.vehicles_ahead_count,
            "vehicles_behind_count": self.vehicles_behind_count
        }

    def get_intent_summary(self) -> dict:
        """Return summary of neighbor intents."""
        return {
            "approaching_agents": self.nearby_approaching_agents,
            "waiting_agents": self.nearby_waiting_agents,
            "crossing_agents": self.nearby_crossing_agents,
            "yielding_agents": self.nearby_yielding_agents,
            "negotiating_agents": self.nearby_negotiating_agents
        }

    def __repr__(self):
        return (f"VehicleAgent(id={self.vehicle_id}, route={self.route}, "
                f"pos={self.position:.1f}m, spd={self.current_speed:.1f}m/s, "
                f"agent_state={self.agent_state.value}, waiting={self.waiting_time:.1f}s)")


# Alias for backward compatibility
Vehicle = VehicleAgent
