import { useState, useEffect } from 'react';
import './TrafficVisualization.css';

const API_URL = 'http://localhost:8000';
const POLL_INTERVAL = 500; // milliseconds

export default function TrafficVisualization() {
  const [trafficState, setTrafficState] = useState({ vehicles: [] });
  const [roadInfo, setRoadInfo] = useState({ num_lanes: 3, road_length: 500 });
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

  // Poll traffic state periodically
  useEffect(() => {
    const interval = setInterval(() => {
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
    }, POLL_INTERVAL);

    return () => clearInterval(interval);
  }, []);

  if (!isConnected) {
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
        <h1>🚗 Live Traffic Simulation</h1>
        <div className="stats">
          <span>Lanes: {roadInfo.num_lanes}</span>
          <span>Road Length: {roadInfo.road_length}m</span>
          <span>Vehicles: {trafficState.vehicles.length}</span>
        </div>
      </header>

      <div className="road-container">
        <Road 
          numLanes={roadInfo.num_lanes} 
          roadLength={roadInfo.road_length}
          vehicles={trafficState.vehicles}
        />
      </div>

      <VehicleList vehicles={trafficState.vehicles} />
    </div>
  );
}

function Road({ numLanes, roadLength, vehicles }) {
  return (
    <div className="road">
      {Array.from({ length: numLanes }).map((_, laneIndex) => (
        <Lane 
          key={laneIndex} 
          laneNumber={laneIndex}
          roadLength={roadLength}
          vehicles={vehicles.filter(v => v.lane === laneIndex)}
        />
      ))}
    </div>
  );
}

function Lane({ laneNumber, roadLength, vehicles }) {
  return (
    <div className="lane">
      <div className="lane-label">Lane {laneNumber}</div>
      <div className="lane-track">
        {vehicles.map(vehicle => (
          <Vehicle 
            key={vehicle.id}
            vehicle={vehicle}
            roadLength={roadLength}
          />
        ))}
      </div>
    </div>
  );
}

function Vehicle({ vehicle, roadLength }) {
  // Calculate position as percentage of road length
  const positionPercent = (vehicle.position / roadLength) * 100;
  
  return (
    <div 
      className="vehicle"
      style={{ left: `${positionPercent}%` }}
      title={`V${vehicle.id}: ${vehicle.speed}m/s`}
    >
      🚗
    </div>
  );
}

function VehicleList({ vehicles }) {
  return (
    <div className="vehicle-list">
      <h3>Vehicle Details</h3>
      <div className="vehicle-grid">
        {vehicles.map(v => (
          <div key={v.id} className="vehicle-card">
            <span className="vehicle-id">V{v.id}</span>
            <span>Lane {v.lane}</span>
            <span>{v.position.toFixed(1)}m</span>
            <span>{v.speed.toFixed(1)}m/s</span>
          </div>
        ))}
      </div>
    </div>
  );
}
