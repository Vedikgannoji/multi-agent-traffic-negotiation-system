import { useState, useEffect, useRef } from 'react';
import './TrafficSimulation.css';

const API_URL = 'http://localhost:8000';
const POLL_INTERVAL = 1000;

// ─── Interpolation engine ────────────────────────────────────────────────────
class VehicleInterpolator {
  constructor() { this.vehicles = new Map(); }

  updateTargets(backendVehicles, timestamp) {
    const currentIds = new Set(backendVehicles.map(v => v.id));

    backendVehicles.forEach(vehicle => {
      if (this.vehicles.has(vehicle.id)) {
        const ex = this.vehicles.get(vehicle.id);
        ex.prevPosition    = ex.currentPosition;
        ex.targetPosition  = vehicle.position;
        ex.prevState       = ex.currentState;
        ex.targetState     = vehicle.state;
        ex.lastUpdate      = timestamp;
        ex.source          = vehicle.source;
        ex.destination     = vehicle.destination;
        ex.turn_type       = vehicle.turn_type;
        ex.speed           = vehicle.speed;
        ex.colliding       = vehicle.colliding ?? false;
      } else {
        this.vehicles.set(vehicle.id, {
          id: vehicle.id,
          prevPosition:   vehicle.position,
          currentPosition: vehicle.position,
          targetPosition: vehicle.position,
          prevState:      vehicle.state,
          currentState:   vehicle.state,
          targetState:    vehicle.state,
          source:         vehicle.source,
          destination:    vehicle.destination,
          turn_type:      vehicle.turn_type,
          speed:          vehicle.speed,
          colliding:      vehicle.colliding ?? false,
          lastUpdate:     timestamp,
        });
      }
    });

    for (const [id] of this.vehicles) {
      if (!currentIds.has(id)) this.vehicles.delete(id);
    }
  }

  interpolate(currentTime) {
    const out = [];
    for (const [, v] of this.vehicles) {
      const t      = Math.min((currentTime - v.lastUpdate) / POLL_INTERVAL, 1.0);
      const eased  = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      v.currentPosition = v.prevPosition + (v.targetPosition - v.prevPosition) * eased;
      v.currentState    = t > 0.5 ? v.targetState : v.prevState;
      out.push({ id: v.id, position: v.currentPosition, state: v.currentState,
                 source: v.source, destination: v.destination,
                 turn_type: v.turn_type, speed: v.speed,
                 colliding: v.colliding ?? false });
    }
    return out;
  }
}

// ─── Main component ──────────────────────────────────────────────────────────
export default function TrafficSimulation() {
  const [vehicles, setVehicles]             = useState([]);
  const [intersectionState, setIntersection] = useState(null);
  const [roadInfo, setRoadInfo]             = useState(null);
  const [isConnected, setIsConnected]       = useState(false);

  const interpolatorRef    = useRef(new VehicleInterpolator());
  const animationFrameRef  = useRef(null);

  // Initial connection
  useEffect(() => {
    fetch(`${API_URL}/traffic/info`)
      .then(r => r.json())
      .then(d => { setRoadInfo(d); setIsConnected(true); })
      .catch(() => setIsConnected(false));
  }, []);

  // Backend polling
  useEffect(() => {
    if (!isConnected) return;
    const poll = () => {
      const ts = Date.now();
      Promise.all([
        fetch(`${API_URL}/traffic/state`).then(r => r.json()),
        fetch(`${API_URL}/intersection/state`).then(r => r.json()),
      ]).then(([traffic, intersection]) => {
        setIntersection(intersection);
        interpolatorRef.current.updateTargets(traffic.vehicles, ts);
      }).catch(() => {});
    };
    poll();
    const id = setInterval(poll, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [isConnected]);

  // 60 fps render loop
  useEffect(() => {
    const loop = () => {
      setVehicles(interpolatorRef.current.interpolate(Date.now()));
      animationFrameRef.current = requestAnimationFrame(loop);
    };
    loop();
    return () => cancelAnimationFrame(animationFrameRef.current);
  }, []);

  if (!isConnected || !roadInfo) {
    return (
      <div className="sim-offline">
        <div className="sim-offline-box">
          <span className="sim-offline-icon">⚠</span>
          <h2>Backend Offline</h2>
          <p>Start the backend server:</p>
          <code>uvicorn backend.main:app --reload</code>
        </div>
      </div>
    );
  }

  return (
    <div className="sim-root">
      <SimHeader />
      <div className="sim-canvas-wrap">
        {intersectionState && (
          <IntersectionSVG
            vehicles={vehicles}
            intersection={intersectionState}
            roadInfo={roadInfo}
          />
        )}
      </div>
    </div>
  );
}

// ─── Header ──────────────────────────────────────────────────────────────────
function SimHeader() {
  return (
    <header className="sim-header">
      <div>
        <h1 className="sim-title">Autonomous Traffic Coordination</h1>
        <p className="sim-subtitle">Intelligent Intersection Management System</p>
      </div>
      <div className="sim-header-badge">Path-Based Reservation</div>
    </header>
  );
}

// ─── SVG canvas ──────────────────────────────────────────────────────────────
function IntersectionSVG({ vehicles, intersection, roadInfo }) {
  const { center_x: cx, center_y: cy, size } = intersection;
  const roadWidth = 50;
  const halfSize  = size / 2;
  const stopOff   = 15;
  const dash      = '10 8';

  const isBusy = (intersection.occupancy || 0) >= (intersection.max_occupancy || 2);

  return (
    <svg viewBox="0 0 500 500" className="sim-svg" preserveAspectRatio="xMidYMid meet">
      <defs>
        <filter id="glow">
          <feGaussianBlur stdDeviation="2" result="blur"/>
          <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <linearGradient id="roadGrad" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%"   stopColor="#2a2a2a"/>
          <stop offset="50%"  stopColor="#1a1a1a"/>
          <stop offset="100%" stopColor="#2a2a2a"/>
        </linearGradient>
      </defs>

      {/* Background */}
      <rect width="500" height="500" fill="#0a0a0a"/>

      {/* Roads */}
      <rect x={cx - roadWidth/2} y={0}              width={roadWidth} height={500} fill="url(#roadGrad)"/>
      <rect x={0}                y={cy - roadWidth/2} width={500}      height={roadWidth} fill="url(#roadGrad)"/>

      {/* Lane dividers */}
      <g stroke="#ffd700" strokeWidth="1" opacity="0.4">
        <line x1={cx} y1={0}            x2={cx} y2={cy - halfSize} strokeDasharray={dash}/>
        <line x1={cx} y1={cy + halfSize} x2={cx} y2={500}          strokeDasharray={dash}/>
        <line x1={0}            y1={cy} x2={cx - halfSize} y2={cy} strokeDasharray={dash}/>
        <line x1={cx + halfSize} y1={cy} x2={500}          y2={cy} strokeDasharray={dash}/>
      </g>

      {/* Stop lines */}
      <g stroke="#ff4444" strokeWidth="2" opacity="0.7">
        <line x1={cx - roadWidth/2} y1={cy - halfSize - stopOff} x2={cx + roadWidth/2} y2={cy - halfSize - stopOff}/>
        <line x1={cx - roadWidth/2} y1={cy + halfSize + stopOff} x2={cx + roadWidth/2} y2={cy + halfSize + stopOff}/>
        <line x1={cx - halfSize - stopOff} y1={cy - roadWidth/2} x2={cx - halfSize - stopOff} y2={cy + roadWidth/2}/>
        <line x1={cx + halfSize + stopOff} y1={cy - roadWidth/2} x2={cx + halfSize + stopOff} y2={cy + roadWidth/2}/>
      </g>

      {/* Intersection zone */}
      <rect
        x={cx - halfSize} y={cy - halfSize} width={size} height={size}
        fill={isBusy ? 'rgba(255,68,68,0.1)' : 'rgba(68,255,136,0.05)'}
        stroke={isBusy ? '#ff4444' : '#44ff88'}
        strokeWidth="1.5" strokeDasharray="5,5"
      />

      {/* Vehicles */}
      {vehicles.map(v => <CarShape key={v.id} vehicle={v} cx={cx} cy={cy}/>)}

      {/* Direction labels */}
      <g fill="#555" fontSize="11" fontWeight="600" letterSpacing="1">
        <text x={cx} y={22}  textAnchor="middle">NORTH</text>
        <text x={cx} y={488} textAnchor="middle">SOUTH</text>
        <text x={22} y={cy + 4} textAnchor="middle">WEST</text>
        <text x={478} y={cy + 4} textAnchor="middle">EAST</text>
      </g>
    </svg>
  );
}

// ─── Car shape ────────────────────────────────────────────────────────────────
function CarShape({ vehicle, cx, cy }) {
  const { source, position, state, colliding } = vehicle;

  let x, y, rotation;
  if      (source === 'north') { x = cx - 12; y = position; rotation = 180; }
  else if (source === 'south') { x = cx + 12; y = position; rotation = 0;   }
  else if (source === 'east')  { x = position; y = cy - 12; rotation = 90;  }
  else                         { x = position; y = cy + 12; rotation = 270; }

  // Collision overrides state colour with red flash
  const color = colliding
    ? '#ff3333'
    : ({ moving: '#4a9eff', waiting: '#ffb84a', crossing: '#44ff88' }[state] || '#888');

  const strokeColor = colliding ? '#ff8888' : 'rgba(255,255,255,0.4)';

  return (
    <g transform={`translate(${x},${y}) rotate(${rotation})`}
       className={colliding ? 'vehicle-colliding' : ''}>
      <rect x="-6" y="-12" width="12" height="24" rx="3" fill={color}
            stroke={strokeColor} strokeWidth={colliding ? 1.5 : 0.5}
            filter="url(#glow)"/>
      <rect x="-4" y="-8"  width="8"  height="6"  rx="1" fill="rgba(255,255,255,0.25)"/>
      <circle cx="-3" cy="-11" r="1" fill="#fff" opacity="0.7"/>
      <circle cx="3"  cy="-11" r="1" fill="#fff" opacity="0.7"/>
    </g>
  );
}
