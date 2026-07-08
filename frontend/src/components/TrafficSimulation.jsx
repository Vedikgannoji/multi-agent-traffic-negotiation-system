import { useState, useEffect, useRef } from 'react';
import './TrafficSimulation.css';

const POLL_INTERVAL = 100; // Interpolation period reference

// ─── Interpolation engine with visual state persistence ──────────────────────
class VehicleInterpolator {
  constructor() { 
    this.vehicles = new Map(); 
  }

  updateTargets(backendVehicles, timestamp) {
    const currentIds = new Set(backendVehicles.map(v => v.id));

    backendVehicles.forEach(vehicle => {
      const now = timestamp;
      if (this.vehicles.has(vehicle.id)) {
        const ex = this.vehicles.get(vehicle.id);
        ex.prevPosition    = ex.currentPosition;
        ex.targetPosition  = vehicle.position;
        ex.prevAgentState  = ex.currentAgentState;
        
        // Track state timestamps for visual holding
        ex.backendAgentState = vehicle.agent_state;
        if (vehicle.agent_state === 'negotiating') {
          ex.lastNegotiatingTime = now;
        } else if (vehicle.agent_state === 'yielding') {
          ex.lastYieldingTime = now;
        }

        ex.targetAgentState = vehicle.agent_state;
        ex.lastUpdate      = now;
        ex.source          = vehicle.source;
        ex.destination     = vehicle.destination;
        ex.turn_type       = vehicle.turn_type;
        ex.speed           = vehicle.speed;
        ex.colliding       = vehicle.colliding ?? false;

        // V2V variables
        ex.conflict_group = vehicle.conflict_group;
        ex.reservation_state = vehicle.reservation_state;
        ex.eta = vehicle.eta;
        ex.reserved_time_window = vehicle.reserved_time_window;
        ex.negotiating_with = vehicle.negotiating_with;
        ex.reason_for_yield = vehicle.reason_for_yield;
      } else {
        this.vehicles.set(vehicle.id, {
          id: vehicle.id,
          prevPosition:      vehicle.position,
          currentPosition:   vehicle.position,
          targetPosition:    vehicle.position,
          prevAgentState:    vehicle.agent_state,
          currentAgentState: vehicle.agent_state,
          targetAgentState:  vehicle.agent_state,
          backendAgentState: vehicle.agent_state,
          lastNegotiatingTime: vehicle.agent_state === 'negotiating' ? now : 0,
          lastYieldingTime: vehicle.agent_state === 'yielding' ? now : 0,
          source:            vehicle.source,
          destination:       vehicle.destination,
          turn_type:         vehicle.turn_type,
          speed:             vehicle.speed,
          colliding:         vehicle.colliding ?? false,
          lastUpdate:        now,
          conflict_group:    vehicle.conflict_group,
          reservation_state: vehicle.reservation_state,
          eta:               vehicle.eta,
          reserved_time_window: vehicle.reserved_time_window,
          negotiating_with:  vehicle.negotiating_with,
          reason_for_yield:  vehicle.reason_for_yield,
        });
      }
    });

    for (const [id] of this.vehicles) {
      if (!currentIds.has(id)) this.vehicles.delete(id);
    }
  }

  interpolate(currentTime) {
    const out = [];
    const now = currentTime;
    for (const [, v] of this.vehicles) {
      const t = Math.min((now - v.lastUpdate) / POLL_INTERVAL, 1.0);
      v.currentPosition = v.prevPosition + (v.targetPosition - v.prevPosition) * t;
      
      // Determine displays state with a 1.5 second (1500ms) visual hold for negotiating and yielding
      let displayState = v.backendAgentState;
      if (displayState !== 'negotiating' && displayState !== 'yielding') {
        if (v.lastYieldingTime && now - v.lastYieldingTime < 1500) {
          displayState = 'yielding';
        } else if (v.lastNegotiatingTime && now - v.lastNegotiatingTime < 1500) {
          displayState = 'negotiating';
        }
      }
      
      v.currentAgentState = displayState;
      out.push({ 
        id: v.id, 
        position: v.currentPosition, 
        agent_state: v.currentAgentState,
        source: v.source, 
        destination: v.destination,
        turn_type: v.turn_type, 
        speed: v.speed,
        colliding: v.colliding ?? false,
        conflict_group: v.conflict_group,
        reservation_state: v.reservation_state,
        eta: v.eta,
        reserved_time_window: v.reserved_time_window,
        negotiating_with: v.negotiating_with,
        reason_for_yield: v.reason_for_yield
      });
    }
    return out;
  }
}

// ─── Main component ──────────────────────────────────────────────────────────
export default function TrafficSimulation({ backendVehicles, intersectionState, roadInfo, isConnected, conflictEdges = [] }) {
  const [vehicles, setVehicles] = useState([]);
  const interpolatorRef = useRef(new VehicleInterpolator());
  const animationFrameRef = useRef(null);

  // Update target coordinates whenever new backend vehicles arrive
  useEffect(() => {
    if (backendVehicles) {
      interpolatorRef.current.updateTargets(backendVehicles, Date.now());
    }
  }, [backendVehicles]);

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
          <p>Please launch the uvicorn API server to continue.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="sim-root">
      <div className="sim-canvas-wrap">
        {intersectionState && (
          <IntersectionSVG
            vehicles={vehicles}
            intersection={intersectionState}
            roadInfo={roadInfo}
            conflictEdges={conflictEdges}
          />
        )}
      </div>
    </div>
  );
}

// ─── SVG canvas ──────────────────────────────────────────────────────────────
function IntersectionSVG({ vehicles, intersection, roadInfo, conflictEdges = [] }) {
  const { center_x: cx, center_y: cy, size } = intersection;
  const [hoveredId, setHoveredId] = useState(null);
  const roadWidth = 54;
  const halfSize  = size / 2;
  const stopOff   = 16;
  const dash      = '8 6';

  const isBusy = (intersection.occupancy || 0) >= (intersection.max_occupancy || 2);

  const getCoordinates = (v) => {
    let x, y;
    if (v.source === 'north') { x = cx - 13; y = v.position; }
    else if (v.source === 'south') { x = cx + 13; y = v.position; }
    else if (v.source === 'east')  { x = v.position; y = cy - 13; }
    else                           { x = v.position; y = cy + 13; }
    return { x, y };
  };

  const vehicleMap = new Map(vehicles.map(v => [v.id, v]));

  return (
    <svg viewBox="0 0 500 500" className="sim-svg" preserveAspectRatio="xMidYMid meet">
      {/* Background slate representing landscape */}
      <rect width="500" height="500" fill="#f1f5f9" rx="8" />

      {/* Roads (slate gray) */}
      <rect x={cx - roadWidth/2} y={0}              width={roadWidth} height={500} fill="#e2e8f0" />
      <rect x={0}                y={cy - roadWidth/2} width={500}      height={roadWidth} fill="#e2e8f0" />

      {/* Lane divider markings (dashed white) */}
      <g stroke="#ffffff" strokeWidth="1.5" opacity="0.8">
        <line x1={cx} y1={0}            x2={cx} y2={cy - halfSize} strokeDasharray={dash}/>
        <line x1={cx} y1={cy + halfSize} x2={cx} y2={500}          strokeDasharray={dash}/>
        <line x1={0}            y1={cy} x2={cx - halfSize} y2={cy} strokeDasharray={dash}/>
        <line x1={cx + halfSize} y1={cy} x2={500}          y2={cy} strokeDasharray={dash}/>
      </g>

      {/* Stop lines (soft crimson/red) */}
      <g stroke="#f43f5e" strokeWidth="2.5" opacity="0.9">
        <line x1={cx - roadWidth/2} y1={cy - halfSize - stopOff} x2={cx + roadWidth/2} y2={cy - halfSize - stopOff}/>
        <line x1={cx - roadWidth/2} y1={cy + halfSize + stopOff} x2={cx + roadWidth/2} y2={cy + halfSize + stopOff}/>
        <line x1={cx - halfSize - stopOff} y1={cy - roadWidth/2} x2={cx - halfSize - stopOff} y2={cy + roadWidth/2}/>
        <line x1={cx + halfSize + stopOff} y1={cy - roadWidth/2} x2={cx + halfSize + stopOff} y2={cy + roadWidth/2}/>
      </g>

      {/* Intersection reservation boundary (thin blue dashed border) */}
      <rect
        x={cx - halfSize} y={cy - halfSize} width={size} height={size}
        fill={isBusy ? 'rgba(244, 63, 94, 0.05)' : 'rgba(37, 99, 235, 0.02)'}
        stroke={isBusy ? '#f43f5e' : '#3b82f6'}
        strokeWidth="1.5" strokeDasharray="4,4"
      />

      {/* V2V Conflict Edges (Decentralized Coordination Graph Overlay) */}
      {conflictEdges.map(([id1, id2], idx) => {
        const v1 = vehicleMap.get(id1);
        const v2 = vehicleMap.get(id2);
        if (!v1 || !v2) return null;
        const p1 = getCoordinates(v1);
        const p2 = getCoordinates(v2);
        return (
          <line
            key={`edge-${idx}`}
            x1={p1.x}
            y1={p1.y}
            x2={p2.x}
            y2={p2.y}
            stroke="#ef4444"
            strokeWidth="2"
            strokeDasharray="4,3"
            opacity="0.85"
          />
        );
      })}

      {/* Vehicles */}
      {vehicles.map(v => (
        <CarShape
          key={v.id}
          vehicle={v}
          cx={cx}
          cy={cy}
          onMouseEnter={() => setHoveredId(v.id)}
          onMouseLeave={() => setHoveredId(null)}
        />
      ))}

      {/* Direction labels (minimal styling) */}
      <g fill="#94a3b8" fontSize="10" fontWeight="700" letterSpacing="0.8">
        <text x={cx} y={20}  textAnchor="middle">NORTH</text>
        <text x={cx} y={490} textAnchor="middle">SOUTH</text>
        <text x={22} y={cy + 3.5} textAnchor="middle">WEST</text>
        <text x={478} y={cy + 3.5} textAnchor="middle">EAST</text>
      </g>

      {/* HUD Telemetry Tooltip Card */}
      {hoveredId !== null && vehicleMap.has(hoveredId) && (() => {
        const v = vehicleMap.get(hoveredId);
        const p = getCoordinates(v);
        
        // Dynamic positioning to prevent card clipping outside SVG viewbox
        const tx = Math.max(15, Math.min(290, p.x + (v.source === 'east' || v.source === 'west' ? -80 : 20)));
        const ty = Math.max(15, Math.min(350, p.y - 100));

        const lines = [
          `Vehicle V${v.id} (${v.source.toUpperCase()} → ${v.destination.toUpperCase()})`,
          `──────────────────────────────`,
          `State: ${(v.agent_state || "NONE").toUpperCase()}`,
          `Speed: ${v.speed ? v.speed.toFixed(1) + ' m/s' : '0.0 m/s'}`,
          `ETA: ${v.eta !== undefined ? v.eta.toFixed(2) + 's' : 'N/A'}`,
          `Reservation: ${v.reservation_state || 'NONE'}`,
          v.reservation_state === 'CONFIRMED' && v.reserved_time_window
            ? `Window: [${v.reserved_time_window[0].toFixed(2)}s, ${v.reserved_time_window[1].toFixed(2)}s]`
            : `Window: N/A`,
          `Conflict Group: [${(v.conflict_group || []).map(id => 'V' + id).join(', ')}]`,
          `Negotiating: [${(v.negotiating_with || []).map(id => 'V' + id).join(', ')}]`,
          v.reason_for_yield ? `Yield Reason: ${v.reason_for_yield}` : null
        ].filter(Boolean);

        const cardWidth = 195;
        const cardHeight = lines.length * 15 + 12;

        return (
          <g transform={`translate(${tx}, ${ty})`}>
            <rect
              width={cardWidth}
              height={cardHeight}
              rx="6"
              fill="#0f172a"
              opacity="0.94"
              stroke="#3b82f6"
              strokeWidth="1.5"
              style={{ filter: 'drop-shadow(0 4px 6px rgba(0,0,0,0.3))' }}
            />
            {lines.map((line, i) => {
              let fill = "#e2e8f0";
              let weight = "normal";
              if (i === 0) {
                fill = "#60a5fa";
                weight = "bold";
              } else if (line.startsWith("State:")) {
                if (v.agent_state === 'yielding') fill = "#c084fc";
                else if (v.agent_state === 'negotiating') fill = "#fbbf24";
                else if (v.agent_state === 'crossing') fill = "#34d399";
                else if (v.agent_state === 'waiting') fill = "#f97316";
              } else if (line.startsWith("Yield Reason:")) {
                fill = "#f87171";
              } else if (line.startsWith("Reservation: CONFIRMED")) {
                fill = "#34d399";
              }
              return (
                <text
                  key={i}
                  x="10"
                  y={18 + i * 15}
                  fill={fill}
                  fontSize="9"
                  fontWeight={weight}
                  fontFamily="monospace, Courier New"
                >
                  {line}
                </text>
              );
            })}
          </g>
        );
      })()}
    </svg>
  );
}

// ─── Car shape ────────────────────────────────────────────────────────────────
function CarShape({ vehicle, cx, cy, onMouseEnter, onMouseLeave }) {
  const { source, position, agent_state, colliding } = vehicle;

  let x, y, rotation;
  if      (source === 'north') { x = cx - 13; y = position; rotation = 180; }
  else if (source === 'south') { x = cx + 13; y = position; rotation = 0;   }
  else if (source === 'east')  { x = position; y = cy - 13; rotation = 90;  }
  else                         { x = position; y = cy + 13; rotation = 270; }

  // Harmonized Light-theme Colors
  const stateColors = {
    approaching: '#3b82f6',  // blue
    negotiating: '#f59e0b',  // amber
    yielding:    '#8b5cf6',  // violet
    waiting:     '#f97316',  // orange
    crossing:    '#10b981',  // emerald green
    exited:      '#94a3b8',  // gray-slate
    collided:    '#ef4444',  // red
  };

  const color = colliding ? '#ef4444' : (stateColors[agent_state] || '#64748b');
  const strokeColor = '#ffffff';

  return (
    <g
      transform={`translate(${x},${y}) rotate(${rotation})`}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      style={{ cursor: 'pointer' }}
    >
      {/* Sleek Minimalist Car Rect */}
      <rect 
        x="-7" 
        y="-14" 
        width="14" 
        height="28" 
        rx="4" 
        fill={color}
        stroke={strokeColor} 
        strokeWidth="1.2"
        style={{ filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.15))' }}
      />
      {/* Front windshield */}
      <rect x="-5" y="-9" width="10" height="4" rx="1" fill="rgba(255, 255, 255, 0.45)"/>
      {/* Rear windshield */}
      <rect x="-5" y="5"  width="10" height="3" rx="1" fill="rgba(255, 255, 255, 0.4)"/>
      
      {/* Headlights */}
      <circle cx="-3.5" cy="-12.5" r="1.2" fill="#fffef0" />
      <circle cx="3.5"  cy="-12.5" r="1.2" fill="#fffef0" />

      {/* State label: NEGOT or YIELD with clean capsules */}
      {(agent_state === 'negotiating' || agent_state === 'yielding') && (
        <g transform={`rotate(${-rotation}) translate(0, -22)`}>
          <rect 
            x="-16" 
            y="-6" 
            width="32" 
            height="12" 
            rx="4" 
            fill={agent_state === 'yielding' ? '#8b5cf6' : '#f59e0b'} 
            stroke="#ffffff" 
            strokeWidth="1" 
            style={{ filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.12))' }} 
          />
          <text x="0" y="2.5" textAnchor="middle" fontSize="7.5" fontWeight="800" fill="#ffffff">
            {agent_state === 'yielding' ? 'YIELD' : 'NEGOT'}
          </text>
        </g>
      )}
    </g>
  );
}
