import { useState, useEffect, useCallback } from 'react';
import './App.css';
import TrafficSimulation from './components/TrafficSimulation';
import ControlPanel from './components/ControlPanel';

const API_URL = 'http://localhost:8000';
const POLL_INTERVAL = 100;

export default function App() {
  const [simulationState, setSimulationState] = useState(null);
  const [roadInfo, setRoadInfo]               = useState(null);
  const [isConnected, setIsConnected]         = useState(false);

  const fetchState = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/simulation/state`);
      if (!res.ok) throw new Error('API error');
      const data = await res.json();
      setSimulationState(data);
      setIsConnected(true);
    } catch (_) {
      setIsConnected(false);
    }
  }, []);

  // Fetch initial road configuration once
  useEffect(() => {
    fetch(`${API_URL}/traffic/info`)
      .then(r => {
        if (!r.ok) throw new Error();
        return r.json();
      })
      .then(d => {
        setRoadInfo(d);
        setIsConnected(true);
      })
      .catch(() => setIsConnected(false));
  }, []);

  // Set up high-frequency polling loop
  useEffect(() => {
    if (!isConnected) {
      // If disconnected, poll less frequently to prevent spamming
      const id = setInterval(fetchState, 1000);
      return () => clearInterval(id);
    }
    fetchState();
    const id = setInterval(fetchState, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [isConnected, fetchState]);

  // Unified callback to execute a control action and immediately pull fresh state
  const handleControlAction = useCallback(async (actionPath, method = 'POST', body = null) => {
    try {
      const options = { method };
      if (body) {
        options.headers = { 'Content-Type': 'application/json' };
        options.body = JSON.stringify(body);
      }
      await fetch(`${API_URL}${actionPath}`, options);
      // Immediately pull state to keep UI ultra-responsive
      await fetchState();
    } catch (_) {}
  }, [fetchState]);

  return (
    <div className="app">
      <div className="app-sim">
        <TrafficSimulation 
          backendVehicles={simulationState?.vehicles || []}
          intersectionState={simulationState?.intersection || null}
          roadInfo={roadInfo}
          isConnected={isConnected}
        />
      </div>
      <div className="app-panel">
        <ControlPanel 
          simulationState={simulationState}
          isConnected={isConnected}
          onControlAction={handleControlAction}
        />
      </div>
    </div>
  );
}
