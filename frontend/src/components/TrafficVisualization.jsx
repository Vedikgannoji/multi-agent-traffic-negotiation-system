import { useState, useEffect } from 'react';
import './TrafficVisualization.css';

const API_URL = 'http://localhost:8000';
const POLL_INTERVAL = 500; // milliseconds

export default function TrafficVisualization() {
  const [trafficState, setTrafficState] = useState({ vehicles: [] });
  const [roadInfo, setRoadInfo] = useState(null);
  const [intersectionState, setIntersectionState] = useState(null);
  const [isConnected, setIsConnected] = useState(false);

  // Fetch road configuration once on mount
  useEffect(() => {
    fetch(`${API_URL}/traffic/info`)
      .then(res => res.json())
      .then(data => {
        setRoadInfo(data);
        setIsConnected(true);
      })
      .catch(err => {
        console.error('Failed to connect to backend:', err);
        setIsConnected(false);
      });
  }, []);

  // Poll traffic state and intersection state periodically
  useEffect(() => {
    const interval = setInterval(() => {
      // Fetch traffic state
      fetch(`${API_URL}/traffic/state`)
        .then(res => res.json())
        .then(data => {
          setTrafficState(data);
          setIsConnected(true);
        })
        .catch(err => {
          console.error('Failed to fetch traffic state:', err);
          setIsConnected(false);
        });

      // Fetch intersection state
      fetch(`${API_URL}/intersection/state`)
        .then(res => res.json())
        .then(data => {
          setIntersectionState(data);
        })
        .catch(err => {
          console.error('Failed to fetch intersection state:', err);
        });
    }, POLL_INTERVAL);

    return () => clearInterval(interval);
  }, []);

  if (!isConnected || !roadInfo) {
    return (
      <div className="error-state">
        <h2>⚠️ Backend Not Connected</h2>
        <p>Make sure the backend is running:</p>
        <code>uvicorn backend.main:app --reload</code>
      </div>
    );
  }

  return (
    <div className="traffic-container">
      <header className="traffic-header">
        <h1>🚦 4-Way Intersection Traffic Simulation</h1>
        <div className="stats">
          <span>Total Vehicles: {trafficState.vehicles.length}</span>
          {intersectionState && (
            <span>In Intersection: {intersectionState.occupancy}/{intersectionState.max_occupancy}</span>
          )}
          {roadInfo.vehicles_by_direction && (
            <>
              <span>North: {roadInfo.vehicles_by_direction.north || 0}</span>
              <span>South: {roadInfo.vehicles_by_direction.south || 0}</span>
              <span>East: {roadInfo.vehicles_by_direction.east || 0}</span>
              <span>West: {roadInfo.vehicles_by_direction.west || 0}</span>
            </>
          )}
        </div>
      </header>

      <div className="fourway-container">
        <FourWayIntersectionView
          vehicles={trafficState.vehicles}
          intersectionState={intersectionState}
          roadInfo={roadInfo}
        />
      </div>

      <div className="info-panels">
        <VehicleList vehicles={trafficState.vehicles} />
        {intersectionState && <IntersectionInfo state={intersectionState} />}
      </div>
    </div>
  );
}

function FourWayIntersectionView({ vehicles, intersectionState, roadInfo }) {
  if (!intersectionState || !roadInfo) return null;

  const centerX = intersectionState.center_x;
  const centerY = intersectionState.center_y;
  const size = intersectionState.size;
  const roadLength = roadInfo.road_length;

  // Group vehicles by direction
  const vehiclesByDirection = {
    north: vehicles.filter(v => v.source === 'north'),
    south: vehicles.filter(v => v.source === 'south'),
    east: vehicles.filter(v => v.source === 'east'),
    west: vehicles.filter(v => v.source === 'west')
  };

  return (
    <div className="fourway-view">
      <svg viewBox="0 0 500 500" className="intersection-svg">
        {/* Roads */}
        <Road direction="north" centerX={centerX} centerY={centerY} size={size} roadLength={roadLength} />
        <Road direction="south" centerX={centerX} centerY={centerY} size={size} roadLength={roadLength} />
        <Road direction="east" centerX={centerX} centerY={centerY} size={size} roadLength={roadLength} />
        <Road direction="west" centerX={centerX} centerY={centerY} size={size} roadLength={roadLength} />

        {/* Intersection zone */}
        <rect
          x={centerX - size / 2}
          y={centerY - size / 2}
          width={size}
          height={size}
          className={`intersection-box ${intersectionState.occupancy >= intersectionState.max_occupancy ? 'busy' : 'available'}`}
        />

        {/* Vehicles */}
        {Object.entries(vehiclesByDirection).map(([direction, dirVehicles]) =>
          dirVehicles.map(vehicle => (
            <VehicleSVG
              key={vehicle.id}
              vehicle={vehicle}
              centerX={centerX}
              centerY={centerY}
              roadLength={roadLength}
            />
          ))
        )}
      </svg>

      {/* Direction labels */}
      <div className="direction-labels">
        <div className="label-north">NORTH</div>
        <div className="label-south">SOUTH</div>
        <div className="label-east">EAST</div>
        <div className="label-west">WEST</div>
      </div>
    </div>
  );
}

function Road({ direction, centerX, centerY, size, roadLength }) {
  const roadWidth = 60;
  const halfSize = size / 2;

  if (direction === 'north') {
    return (
      <rect
        x={centerX - roadWidth / 2}
        y={centerY - roadLength / 2}
        width={roadWidth}
        height={roadLength / 2 - halfSize}
        className="road-segment"
      />
    );
  } else if (direction === 'south') {
    return (
      <rect
        x={centerX - roadWidth / 2}
        y={centerY + halfSize}
        width={roadWidth}
        height={roadLength / 2 - halfSize}
        className="road-segment"
      />
    );
  } else if (direction === 'east') {
    return (
      <rect
        x={centerX - roadLength / 2}
        y={centerY - roadWidth / 2}
        width={roadLength / 2 - halfSize}
        height={roadWidth}
        className="road-segment"
      />
    );
  } else if (direction === 'west') {
    return (
      <rect
        x={centerX + halfSize}
        y={centerY - roadWidth / 2}
        width={roadLength / 2 - halfSize}
        height={roadWidth}
        className="road-segment"
      />
    );
  }
  return null;
}

function VehicleSVG({ vehicle, centerX, centerY, roadLength }) {
  const { source, position, state, turn_type } = vehicle;

  // Calculate vehicle position on screen
  let x, y, rotation;

  if (source === 'north') {
    x = centerX;
    y = position;
    rotation = 180; // pointing down
  } else if (source === 'south') {
    x = centerX;
    y = position;
    rotation = 0; // pointing up
  } else if (source === 'east') {
    x = position;
    y = centerY;
    rotation = 90; // pointing right
  } else if (source === 'west') {
    x = position;
    y = centerY;
    rotation = 270; // pointing left
  }

  // Determine color based on state
  const displayState = vehicle.agent_state || state;
  let color;
  if (displayState === 'moving' || displayState === 'approaching') {
    color = '#3b82f6'; // blue
  } else if (displayState === 'negotiating') {
    color = '#fbbf24'; // yellow
  } else if (displayState === 'waiting') {
    color = '#f97316'; // orange
  } else if (displayState === 'crossing') {
    color = '#10b981'; // green
  } else {
    color = '#6b7280'; // gray
  }

  return (
    <g transform={`translate(${x}, ${y}) rotate(${rotation})`}>
      <circle r="6" fill={color} className="vehicle-circle" />
      <text
        y="4"
        textAnchor="middle"
        fontSize="10"
        fill="white"
        fontWeight="bold"
        transform={`rotate(${-rotation})`}
      >
        {turn_type === 'left' ? '←' : turn_type === 'right' ? '→' : '↑'}
      </text>
    </g>
  );
}

function VehicleList({ vehicles }) {
  // Group vehicles by state
  const byState = vehicles.reduce((acc, v) => {
    let state = v.agent_state || v.state || 'moving';
    if (state === 'approaching') state = 'moving';
    acc[state] = (acc[state] || 0) + 1;
    return acc;
  }, {});

  // Group by turn type
  const byTurn = vehicles.reduce((acc, v) => {
    const turn = v.turn_type || 'straight';
    acc[turn] = (acc[turn] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="vehicle-list">
      <h3>Vehicle Details</h3>

      <div className="state-summary">
        <div className="state-badge state-moving">
          Moving: {byState.moving || 0}
        </div>
        <div className="state-badge state-negotiating">
          Negotiating: {byState.negotiating || 0}
        </div>
        <div className="state-badge state-waiting">
          Waiting: {byState.waiting || 0}
        </div>
        <div className="state-badge state-crossing">
          Crossing: {byState.crossing || 0}
        </div>
      </div>

      <div className="turn-summary">
        <div className="turn-badge">↑ Straight: {byTurn.straight || 0}</div>
        <div className="turn-badge">← Left: {byTurn.left || 0}</div>
        <div className="turn-badge">→ Right: {byTurn.right || 0}</div>
      </div>

      <div className="vehicle-grid">
        {vehicles.slice(0, 20).map(v => {
          let displayState = v.agent_state || v.state || 'moving';
          if (displayState === 'approaching') displayState = 'moving';
          return (
            <div key={v.id} className={`vehicle-card state-${displayState}`}>
              <span className="vehicle-id">V{v.id}</span>
              <span>{v.source} → {v.destination}</span>
              <span>{v.turn_type}</span>
              <span>{v.position.toFixed(0)}m</span>
              <span>{v.speed.toFixed(1)}m/s</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function IntersectionInfo({ state }) {
  const utilizationPercent = (state.occupancy / state.max_occupancy) * 100;

  return (
    <div className="intersection-info">
      <h3>🚦 Intersection Status</h3>

      <div className="info-row">
        <span>Location:</span>
        <span>({state.center_x}, {state.center_y})</span>
      </div>

      <div className="info-row">
        <span>Size:</span>
        <span>{state.size}m × {state.size}m</span>
      </div>

      <div className="info-row">
        <span>Occupancy:</span>
        <span>{state.occupancy} / {state.max_occupancy}</span>
      </div>

      <div className="utilization-bar">
        <div
          className="utilization-fill"
          style={{ width: `${utilizationPercent}%` }}
        ></div>
      </div>

      <h4>Waiting Queues:</h4>
      {Object.entries(state.waiting_counts || {}).map(([direction, count]) => (
        <div key={direction} className="info-row">
          <span>{direction.toUpperCase()}:</span>
          <span>{count} vehicles</span>
        </div>
      ))}

      {state.vehicles_inside && state.vehicles_inside.length > 0 && (
        <>
          <h4>Inside Intersection:</h4>
          {state.vehicles_inside.map(v => (
            <div key={v.id} className="info-row">
              <span>V{v.id}:</span>
              <span>{v.route} ({v.turn_type})</span>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
