"""
direction.py - Defines directions and routes for 4-way intersection.
Includes comprehensive conflict matrix for path-based collision detection.
"""


class Direction:
    """Cardinal directions for the 4-way intersection."""
    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"
    
    @staticmethod
    def all():
        return [Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST]
    
    @staticmethod
    def opposite(direction: str) -> str:
        """Get the opposite direction."""
        opposites = {
            Direction.NORTH: Direction.SOUTH,
            Direction.SOUTH: Direction.NORTH,
            Direction.EAST: Direction.WEST,
            Direction.WEST: Direction.EAST
        }
        return opposites.get(direction, direction)


class TurnType:
    """Types of turns a vehicle can make."""
    STRAIGHT = "straight"
    LEFT = "left"
    RIGHT = "right"
    
    @staticmethod
    def all():
        return [TurnType.STRAIGHT, TurnType.LEFT, TurnType.RIGHT]


class Route:
    """Represents a vehicle's path through the intersection."""
    
    def __init__(self, source: str, destination: str):
        """
        source: Direction vehicle is coming from (NORTH/SOUTH/EAST/WEST)
        destination: Direction vehicle is going to
        """
        self.source = source
        self.destination = destination
        self.turn_type = self._calculate_turn_type()
    
    def _calculate_turn_type(self) -> str:
        """Determine if this route is straight, left, or right turn."""
        # Straight: opposite directions
        if self.destination == Direction.opposite(self.source):
            return TurnType.STRAIGHT
        
        # Define left and right turns for each source direction
        left_turns = {
            Direction.NORTH: Direction.WEST,
            Direction.SOUTH: Direction.EAST,
            Direction.EAST: Direction.NORTH,
            Direction.WEST: Direction.SOUTH
        }
        
        right_turns = {
            Direction.NORTH: Direction.EAST,
            Direction.SOUTH: Direction.WEST,
            Direction.EAST: Direction.SOUTH,
            Direction.WEST: Direction.NORTH
        }
        
        if self.destination == left_turns.get(self.source):
            return TurnType.LEFT
        elif self.destination == right_turns.get(self.source):
            return TurnType.RIGHT
        
        return TurnType.STRAIGHT  # fallback
    
    def conflicts_with(self, other: 'Route') -> bool:
        """
        COMPREHENSIVE CONFLICT DETECTION
        Check if this route conflicts with another route using a complete conflict matrix.
        Two routes conflict if their paths would intersect in the intersection.
        
        This is the authoritative conflict detection - all edge cases covered.
        """
        # Same route = no conflict (identical path)
        if self.source == other.source and self.destination == other.destination:
            return False
        
        # Use comprehensive conflict matrix
        return RouteConflictMatrix.has_conflict(self, other)
    
    def __repr__(self):
        return f"Route({self.source}→{self.destination}, {self.turn_type})"
    
    def __eq__(self, other):
        return (self.source == other.source and 
                self.destination == other.destination)
    
    def __hash__(self):
        return hash((self.source, self.destination))


class RouteConflictMatrix:
    """
    COMPREHENSIVE ROUTE CONFLICT MATRIX
    
    Defines all possible conflicts between routes in a 4-way intersection.
    This is the authoritative source for conflict detection.
    
    Conflict Rules:
    1. STRAIGHT vs STRAIGHT: Conflict if perpendicular (crossing paths)
    2. STRAIGHT vs LEFT: Conflict if left turn crosses straight path
    3. STRAIGHT vs RIGHT: Generally no conflict (right stays outer)
    4. LEFT vs LEFT: Conflict if paths cross
    5. LEFT vs RIGHT: Conflict if paths intersect
    6. RIGHT vs RIGHT: Generally no conflict (both stay outer)
    
    Special Cases:
    - Same source: No conflict (vehicles queue, don't cross)
    - Opposite source going same direction: Conflict (head-on in intersection)
    - Adjacent sources: Depends on turn types
    """
    
    # Pre-computed conflict matrix for all 144 possible route combinations (12x12)
    # Format: (source1, dest1, source2, dest2) -> conflicts
    _conflict_cache = {}
    
    @classmethod
    def has_conflict(cls, route1: Route, route2: Route) -> bool:
        """
        Check if two routes conflict using comprehensive logic.
        Returns True if vehicles following these routes would collide.
        """
        # Cache key for performance
        cache_key = (route1.source, route1.destination, route2.source, route2.destination)
        
        if cache_key in cls._conflict_cache:
            return cls._conflict_cache[cache_key]
        
        # Compute conflict
        conflict = cls._compute_conflict(route1, route2)
        
        # Cache result (and symmetric result)
        cls._conflict_cache[cache_key] = conflict
        reverse_key = (route2.source, route2.destination, route1.source, route1.destination)
        cls._conflict_cache[reverse_key] = conflict
        
        return conflict
    
    @classmethod
    def _compute_conflict(cls, route1: Route, route2: Route) -> bool:
        """Compute whether two routes conflict."""
        
        # RULE 1: Same source direction = no conflict (vehicles queue)
        if route1.source == route2.source:
            return False
        
        # RULE 1.5: Same destination but different sources = conflict (merging)
        if route1.destination == route2.destination:
            return True
        
        # RULE 1.8: Perpendicular corridors conflict in 1D physics
        if cls._are_perpendicular(route1.source, route2.source):
            return True
        
        # RULE 2: Opposite sources going to same destination = conflict (head-on)
        if (route1.source == Direction.opposite(route2.source) and 
            route1.destination == route2.destination):
            return True
        
        # RULE 3: STRAIGHT vs STRAIGHT
        if route1.turn_type == TurnType.STRAIGHT and route2.turn_type == TurnType.STRAIGHT:
            # Conflict if perpendicular (crossing paths)
            if cls._are_perpendicular(route1.source, route2.source):
                return True
            # No conflict if parallel (same axis)
            return False
        
        # RULE 4: STRAIGHT vs LEFT
        if route1.turn_type == TurnType.STRAIGHT and route2.turn_type == TurnType.LEFT:
            return cls._straight_left_conflict(route1, route2)
        if route1.turn_type == TurnType.LEFT and route2.turn_type == TurnType.STRAIGHT:
            return cls._straight_left_conflict(route2, route1)
        
        # RULE 5: STRAIGHT vs RIGHT
        if route1.turn_type == TurnType.STRAIGHT and route2.turn_type == TurnType.RIGHT:
            return cls._straight_right_conflict(route1, route2)
        if route1.turn_type == TurnType.RIGHT and route2.turn_type == TurnType.STRAIGHT:
            return cls._straight_right_conflict(route2, route1)
        
        # RULE 6: LEFT vs LEFT
        if route1.turn_type == TurnType.LEFT and route2.turn_type == TurnType.LEFT:
            return cls._left_left_conflict(route1, route2)
        
        # RULE 7: LEFT vs RIGHT
        if route1.turn_type == TurnType.LEFT and route2.turn_type == TurnType.RIGHT:
            return cls._left_right_conflict(route1, route2)
        if route1.turn_type == TurnType.RIGHT and route2.turn_type == TurnType.LEFT:
            return cls._left_right_conflict(route2, route1)
        
        # RULE 8: RIGHT vs RIGHT
        if route1.turn_type == TurnType.RIGHT and route2.turn_type == TurnType.RIGHT:
            # Right turns generally don't conflict (stay in outer lanes)
            # Exception: if one is turning into the other's source lane
            if route1.destination == route2.source:
                return True
            if route2.destination == route1.source:
                return True
            # Adjacent right turns are safe (both stay outer)
            return False
        
        # Default: no conflict
        return False
    
    @staticmethod
    def _are_perpendicular(dir1: str, dir2: str) -> bool:
        """Check if two directions are perpendicular."""
        ns = {Direction.NORTH, Direction.SOUTH}
        ew = {Direction.EAST, Direction.WEST}
        return (dir1 in ns and dir2 in ew) or (dir1 in ew and dir2 in ns)
    
    @staticmethod
    def _straight_left_conflict(straight: Route, left: Route) -> bool:
        """Check if a straight route conflicts with a left turn."""
        # Left turn crosses straight path if:
        # 1. They're perpendicular AND
        # 2. Left turn crosses the straight vehicle's path
        
        # If straight is coming from opposite of left's destination, they conflict
        if straight.source == Direction.opposite(left.destination):
            return True
        
        # If left is coming from opposite of straight's source, they conflict
        if left.source == Direction.opposite(straight.source):
            return True
        
        # If they're adjacent and left turn crosses straight path
        if RouteConflictMatrix._are_perpendicular(straight.source, left.source):
            # Left turn will cross the straight path
            return True
        
        return False
    
    @staticmethod
    def _straight_right_conflict(straight: Route, right: Route) -> bool:
        """Check if a straight route conflicts with a right turn."""
        # Right turns generally don't conflict with straight (stay outer)
        # Exception: if right turn destination is where straight is coming from
        if right.destination == straight.source:
            return True
        
        # Exception: if straight destination is where right is coming from
        if straight.destination == right.source:
            return True
        
        return False
    
    @staticmethod
    def _left_left_conflict(left1: Route, left2: Route) -> bool:
        """Check if two left turns conflict."""
        # Opposite left turns always conflict (cross in center)
        if left1.source == Direction.opposite(left2.source):
            return True
        
        # Adjacent left turns conflict if they cross paths
        if left1.destination == left2.source or left2.destination == left1.source:
            return True
        
        return False
    
    @staticmethod
    def _left_right_conflict(left: Route, right: Route) -> bool:
        """Check if a left turn conflicts with a right turn."""
        # Left turn conflicts with right if paths intersect
        
        # If left is turning into right's destination lane
        if left.destination == right.destination:
            return True
        
        # If right is turning into left's path
        if right.destination == left.source:
            return True
        
        # If they're coming from opposite directions
        if left.source == Direction.opposite(right.source):
            return True
        
        return False
