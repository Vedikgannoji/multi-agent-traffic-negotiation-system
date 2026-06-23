import { useState, useEffect, useCallback, useRef } from 'react';
import './App.css';
import TrafficSimulation from './components/TrafficSimulation';
import ControlPanel from './components/ControlPanel';
import { LineChart, BarChart, ProgressRing } from './components/Charts';

const API_URL = 'http://localhost:8000';
const POLL_INTERVAL = 100;

export default function App() {
  const [simulationState, setSimulationState] = useState(null);
  const [roadInfo, setRoadInfo] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [currentTab, setCurrentTab] = useState('traffic');
  const [history, setHistory] = useState([]);
  
  const tickCounterRef = useRef(0);
  const consoleEndRef = useRef(null);

  const fetchState = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/simulation/state`);
      if (!res.ok) throw new Error('API error');
      const data = await res.json();
      setSimulationState(data);
      setIsConnected(true);

      // Accumulate history every 1.0 second (10 polling ticks)
      tickCounterRef.current += 1;
      if (tickCounterRef.current >= 10) {
        tickCounterRef.current = 0;
        
        setHistory(prevHistory => {
          const prevItem = prevHistory[prevHistory.length - 1];
          const currentSafeCrossings = data.safety?.total_safe_crossings ?? 0;
          const currentNegotiations = data.v2v?.negotiations_initiated ?? 0;
          const currentYields = data.v2v?.yield_decisions ?? 0;

          const deltaSafeCrossings = prevItem ? Math.max(0, currentSafeCrossings - prevItem._rawSafeCrossings) : 0;
          const deltaNegotiations = prevItem ? Math.max(0, currentNegotiations - prevItem._rawNegotiations) : 0;
          const deltaYields = prevItem ? Math.max(0, currentYields - prevItem._rawYields) : 0;

          const newItem = {
            timestamp: data.timestamp,
            throughput: deltaSafeCrossings,
            negotiations: deltaNegotiations,
            yields: deltaYields,
            messagesPerSecond: data.v2v?.messages_per_second ?? 0,
            safetyAccuracy: data.safety?.safety_accuracy_pct ?? 100,
            approaching: data.agent_states?.approaching ?? 0,
            waiting: data.agent_states?.waiting ?? 0,
            crossing: data.agent_states?.crossing ?? 0,
            negotiating: data.agent_states?.negotiating ?? 0,
            yielding: data.agent_states?.yielding ?? 0,
            _rawSafeCrossings: currentSafeCrossings,
            _rawNegotiations: currentNegotiations,
            _rawYields: currentYields
          };

          const newHistory = [...prevHistory, newItem];
          return newHistory.length > 40 ? newHistory.slice(newHistory.length - 40) : newHistory;
        });
      }
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

  // High-frequency polling loop
  useEffect(() => {
    if (!isConnected) {
      const id = setInterval(fetchState, 1000);
      return () => clearInterval(id);
    }
    fetchState();
    const id = setInterval(fetchState, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [isConnected, fetchState]);

  // Handle manual mode changes to update active tab validity
  const control = simulationState?.control || null;
  const controlMode = control?.control_mode || "assisted";

  useEffect(() => {
    const validTabs = controlMode === 'pure_v2v' 
      ? ['traffic', 'safety', 'v2v', 'intent', 'negotiation', 'live_feed']
      : ['traffic', 'safety'];
    
    if (!validTabs.includes(currentTab)) {
      setCurrentTab('traffic');
    }
  }, [controlMode, currentTab]);

  // Console automatic scrolling when on live feed tab
  useEffect(() => {
    if (currentTab === 'live_feed' && consoleEndRef.current) {
      consoleEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [currentTab, simulationState?.v2v_log]);

  // Unified callback to execute control actions and immediately pull state
  const handleControlAction = useCallback(async (actionPath, method = 'POST', body = null) => {
    try {
      const options = { method };
      if (body) {
        options.headers = { 'Content-Type': 'application/json' };
        options.body = JSON.stringify(body);
      }
      await fetch(`${API_URL}${actionPath}`, options);
      await fetchState();
    } catch (_) {}
  }, [fetchState]);

  // Helper to parse console log text and return color-coded CSS class
  const getConsoleLogClass = (text) => {
    const lower = text.toLowerCase();
    if (lower.includes('yielding') || lower.includes('yield')) return 'console-text yield';
    if (lower.includes('intent:')) return 'console-text intent';
    if (lower.includes('priority')) return 'console-text priority';
    if (lower.includes('proceeding') || lower.includes('proceed')) return 'console-text proceed';
    return 'console-text';
  };

  // ─── Extract Simulation Data ───────────────────────────────────────────────
  const vehicles = simulationState?.vehicles || [];
  const safety = simulationState?.safety || { total_collisions: 0, total_safe_crossings: 0, total_failed_crossings: 0, safety_accuracy_pct: 100 };
  const v2v = simulationState?.v2v || {};
  const activeNegotiations = simulationState?.active_negotiations || [];
  const v2vLog = simulationState?.v2v_log || [];

  // Density count metrics
  const totalVehicles = vehicles.length;
  const waitingCount = vehicles.filter(v => v.agent_state === 'waiting').length;
  const crossingCount = vehicles.filter(v => v.agent_state === 'crossing').length;
  const movingCount = totalVehicles - waitingCount;
  
  const totalWaitTime = vehicles.reduce((sum, v) => sum + (v.waiting_time || 0), 0);
  const avgWaitTime = totalVehicles > 0 ? (totalWaitTime / totalVehicles).toFixed(1) : "0.0";

  return (
    <div className="app-container">
      {/* ─── Top Application Header ─── */}
      <header className="app-header">
        <div className="app-title-group">
          <h1 className="app-title">Autonomous Multi-Agent Intersection Coordinator</h1>
          <p className="app-subtitle">Cooperative Research & Observability Platform</p>
        </div>
        <div className="app-meta-group">
          <span className={`app-mode-badge ${controlMode === 'pure_v2v' ? 'app-mode-badge--v2v' : ''}`}>
            {controlMode === 'pure_v2v' ? 'Pure V2V Experimental Mode' : 'Reservation Assisted Mode'}
          </span>
          <div className="app-status">
            <span className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`} />
            <span>{isConnected ? 'Sim Connected' : 'Sim Offline'}</span>
          </div>
        </div>
      </header>

      {/* ─── Main Content Workspace ─── */}
      <main className="app-main">
        {/* Center Row: Canvas (Left) & Input Controls (Right) */}
        <div className="app-center">
          <div className="canvas-card">
            <TrafficSimulation 
              backendVehicles={vehicles}
              intersectionState={simulationState?.intersection || null}
              roadInfo={roadInfo}
              isConnected={isConnected}
            />
          </div>
          <div className="controls-card">
            <ControlPanel 
              simulationState={simulationState}
              isConnected={isConnected}
              onControlAction={handleControlAction}
            />
          </div>
        </div>

        {/* Bottom Row: Tab-based Analytics Workspace */}
        <div className="app-bottom">
          <nav className="tabs-header">
            <button 
              className={`tab-btn ${currentTab === 'traffic' ? 'tab-btn--active' : ''}`}
              onClick={() => setCurrentTab('traffic')}
            >
              📊 Traffic flow
            </button>
            <button 
              className={`tab-btn ${currentTab === 'safety' ? 'tab-btn--active' : ''}`}
              onClick={() => setCurrentTab('safety')}
            >
              🛡 Safety Analysis
            </button>
            {controlMode === 'pure_v2v' && (
              <>
                <button 
                  className={`tab-btn ${currentTab === 'v2v' ? 'tab-btn--active' : ''}`}
                  onClick={() => setCurrentTab('v2v')}
                >
                  ⚡ V2V Comms
                </button>
                <button 
                  className={`tab-btn ${currentTab === 'intent' ? 'tab-btn--active' : ''}`}
                  onClick={() => setCurrentTab('intent')}
                >
                  🎯 Intent States
                </button>
                <button 
                  className={`tab-btn ${currentTab === 'negotiation' ? 'tab-btn--active' : ''}`}
                  onClick={() => setCurrentTab('negotiation')}
                >
                  🤝 Cooperation
                </button>
                <button 
                  className={`tab-btn ${currentTab === 'live_feed' ? 'tab-btn--active' : ''}`}
                  onClick={() => setCurrentTab('live_feed')}
                >
                  📟 Live Feed
                </button>
              </>
            )}
          </nav>

          <div className="tab-content">
            {/* 1. TRAFFIC TAB */}
            {currentTab === 'traffic' && (
              <div className="tab-pane">
                <div className="metrics-row">
                  <div className="metric-card">
                    <span className="metric-card-label">Active Vehicles</span>
                    <span className="metric-card-value">{totalVehicles}</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Moving</span>
                    <span className="metric-card-value">{movingCount}</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Waiting</span>
                    <span className="metric-card-value">{waitingCount}</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Crossing</span>
                    <span className="metric-card-value">{crossingCount}</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Total Spawned</span>
                    <span className="metric-card-value">{control?.total_spawned ?? 0}</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Avg Wait Time</span>
                    <span className="metric-card-value">
                      {avgWaitTime}<span className="metric-card-unit">s</span>
                    </span>
                  </div>
                </div>
                <div className="charts-grid">
                  <div className="chart-card">
                    <span className="chart-card-title">Throughput Delta Rate (Vehicles/s)</span>
                    <LineChart data={history.map(h => h.throughput)} stroke="#2563eb" fill="rgba(37, 99, 235, 0.06)" />
                  </div>
                  <div className="chart-card">
                    <span className="chart-card-title">Vehicle Agent State Distribution</span>
                    <BarChart 
                      data={[
                        { label: 'Approach', value: vehicles.filter(v => v.agent_state === 'approaching').length },
                        { label: 'Waiting', value: vehicles.filter(v => v.agent_state === 'waiting').length },
                        { label: 'Crossing', value: vehicles.filter(v => v.agent_state === 'crossing').length },
                        { label: 'Negotiating', value: vehicles.filter(v => v.agent_state === 'negotiating').length },
                        { label: 'Yielding', value: vehicles.filter(v => v.agent_state === 'yielding').length }
                      ]} 
                      color="#2563eb" 
                    />
                  </div>
                </div>
              </div>
            )}

            {/* 2. SAFETY TAB */}
            {currentTab === 'safety' && (
              <div className="tab-pane">
                <div className="metrics-row">
                  <div className="metric-card">
                    <span className="metric-card-label">Collisions</span>
                    <span className="metric-card-value" style={{ color: safety.total_collisions > 0 ? '#ef4444' : '#10b981' }}>
                      {safety.total_collisions}
                    </span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Safe Crossings</span>
                    <span className="metric-card-value">{safety.total_safe_crossings}</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Failed Crossings</span>
                    <span className="metric-card-value" style={{ color: safety.total_failed_crossings > 0 ? '#ef4444' : '#64748b' }}>
                      {safety.total_failed_crossings}
                    </span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Passing Accuracy</span>
                    <span className="metric-card-value">
                      {safety.safety_accuracy_pct}%
                    </span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Deadlocks Recovered</span>
                    <span className="metric-card-value">{safety.deadlock_recoveries ?? 0}</span>
                  </div>
                </div>
                <div className="charts-grid">
                  <div className="chart-card">
                    <span className="chart-card-title">Safety Passing Accuracy Trend (%)</span>
                    <LineChart data={history.map(h => h.safetyAccuracy)} minVal={0} maxVal={100} stroke="#10b981" fill="rgba(16, 185, 129, 0.05)" />
                  </div>
                  <div className="chart-card">
                    <span className="chart-card-title">Crossings vs Collisions</span>
                    <BarChart 
                      data={[
                        { label: 'Safe Crossings', value: safety.total_safe_crossings },
                        { label: 'Collisions', value: safety.total_collisions }
                      ]} 
                      color="#ef4444" 
                    />
                  </div>
                </div>
              </div>
            )}

            {/* 3. V2V TAB (Only visible in V2V mode) */}
            {currentTab === 'v2v' && controlMode === 'pure_v2v' && (
              <div className="tab-pane">
                <div className="metrics-row">
                  <div className="metric-card">
                    <span className="metric-card-label">Messages Sent</span>
                    <span className="metric-card-value">{v2v.total_messages_sent ?? 0}</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Messages Received</span>
                    <span className="metric-card-value">{v2v.total_messages_received ?? 0}</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Messages / Sec</span>
                    <span className="metric-card-value">{v2v.messages_per_second?.toFixed(1) ?? "0.0"}</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Avg Neighbors</span>
                    <span className="metric-card-value">{v2v.average_neighbors_per_vehicle ?? "0.0"}</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Local Density</span>
                    <span className="metric-card-value">{v2v.average_local_density?.toFixed(3) ?? "0.000"}</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Avg Closest Dist</span>
                    <span className="metric-card-value">
                      {v2v.average_closest_vehicle_distance && v2v.average_closest_vehicle_distance > 0 
                        ? `${v2v.average_closest_vehicle_distance.toFixed(1)}m` 
                        : "N/A"}
                    </span>
                  </div>
                </div>
                <div className="charts-grid">
                  <div className="chart-card">
                    <span className="chart-card-title">Messages Per Second Over Time</span>
                    <LineChart data={history.map(h => h.messagesPerSecond)} stroke="#3b82f6" fill="rgba(59, 130, 246, 0.05)" />
                  </div>
                  <div className="chart-card">
                    <span className="chart-card-title">Local Vehicle Neighbor Distribution</span>
                    <BarChart 
                      data={(() => {
                        const counts = [0, 0, 0, 0];
                        vehicles.forEach(v => {
                          const count = v.neighbor_count ?? 0;
                          if (count >= 3) counts[3]++;
                          else counts[count]++;
                        });
                        return [
                          { label: '0 Neighbors', value: counts[0] },
                          { label: '1 Neighbor', value: counts[1] },
                          { label: '2 Neighbors', value: counts[2] },
                          { label: '3+ Neighbors', value: counts[3] }
                        ];
                      })()}
                      color="#3b82f6"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* 4. INTENT TAB (Only visible in V2V mode) */}
            {currentTab === 'intent' && controlMode === 'pure_v2v' && (
              <div className="tab-pane">
                <div className="metrics-row">
                  <div className="metric-card">
                    <span className="metric-card-label">Approaching Intent</span>
                    <span className="metric-card-value">{v2v.total_approaching_agents ?? 0}</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Waiting Intent</span>
                    <span className="metric-card-value">{v2v.total_waiting_agents ?? 0}</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Crossing Intent</span>
                    <span className="metric-card-value">{v2v.total_crossing_agents ?? 0}</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Negotiating Intent</span>
                    <span className="metric-card-value">{v2v.total_negotiating_agents ?? 0}</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Yielding Intent</span>
                    <span className="metric-card-value">{v2v.total_yielding_agents ?? 0}</span>
                  </div>
                </div>
                <div className="charts-grid">
                  <div className="chart-card">
                    <span className="chart-card-title">Intent State Distribution</span>
                    <BarChart 
                      data={[
                        { label: 'Approach', value: v2v.total_approaching_agents ?? 0 },
                        { label: 'Waiting', value: v2v.total_waiting_agents ?? 0 },
                        { label: 'Crossing', value: v2v.total_crossing_agents ?? 0 },
                        { label: 'Negotiating', value: v2v.total_negotiating_agents ?? 0 },
                        { label: 'Yielding', value: v2v.total_yielding_agents ?? 0 }
                      ]} 
                      color="#eab308" 
                    />
                  </div>
                  <div className="chart-card">
                    <span className="chart-card-title">Cooperative Coordination Level Trend (Active Negot + Yield)</span>
                    <LineChart data={history.map(h => h.negotiating + h.yielding)} stroke="#eab308" fill="rgba(234, 179, 8, 0.05)" />
                  </div>
                </div>
              </div>
            )}

            {/* 5. NEGOTIATION TAB (Only visible in V2V mode) */}
            {currentTab === 'negotiation' && controlMode === 'pure_v2v' && (
              <div className="tab-pane">
                <div className="metrics-row">
                  <div className="metric-card">
                    <span className="metric-card-label">Negotiations Initiated</span>
                    <span className="metric-card-value">{v2v.negotiations_initiated ?? 0}</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Successful Negotiations</span>
                    <span className="metric-card-value">{v2v.successful_negotiations ?? 0}</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Yield Decisions</span>
                    <span className="metric-card-value">{v2v.yield_decisions ?? 0}</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Active Negotiations</span>
                    <span className="metric-card-value">{v2v.active_negotiations ?? 0}</span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Avg Negotiation Dur</span>
                    <span className="metric-card-value">
                      {v2v.average_negotiation_duration?.toFixed(2) ?? "0.00"}<span className="metric-card-unit">s</span>
                    </span>
                  </div>
                  <div className="metric-card">
                    <span className="metric-card-label">Avg Yield Dur</span>
                    <span className="metric-card-value">
                      {v2v.average_yield_duration?.toFixed(2) ?? "0.00"}<span className="metric-card-unit">s</span>
                    </span>
                  </div>
                </div>
                <div className="charts-grid">
                  <div className="chart-card">
                    <span className="chart-card-title">Negotiation Resolution Rate over time</span>
                    <LineChart data={history.map(h => h.negotiations)} stroke="#8b5cf6" fill="rgba(139, 92, 246, 0.05)" />
                  </div>
                  <div className="chart-card">
                    <span className="chart-card-title">Negotiation Success Rate</span>
                    <div className="negotiation-ring-layout">
                      <ProgressRing 
                        percentage={v2v.negotiations_initiated > 0 ? (v2v.successful_negotiations / v2v.negotiations_initiated) * 100 : 100}
                        color="#8b5cf6"
                        size={120}
                        label="Resolved / Initiated"
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* 6. LIVE FEED TAB (Only visible in V2V mode) */}
            {currentTab === 'live_feed' && controlMode === 'pure_v2v' && (
              <div className="live-feed-split">
                {/* Left Panel: V2V Message Console */}
                <div className="console-panel">
                  <span className="panel-header-title console-header-title">📟 V2V Message Console Feed</span>
                  <div className="console-box">
                    {v2vLog.length === 0 ? (
                      <div className="active-neg-empty">No communications logged yet...</div>
                    ) : (
                      v2vLog.map((log, idx) => (
                        <div key={idx} className="console-row">
                          <span className="console-time">[{new Date(dataTimestampToDate(log.timestamp)).toLocaleTimeString()}]</span>
                          <span className={getConsoleLogClass(log.text)}>{log.text}</span>
                        </div>
                      ))
                    )}
                    <div ref={consoleEndRef} />
                  </div>
                </div>

                {/* Right Panel: Active Negotiation Monitor */}
                <div className="active-neg-panel">
                  <span className="panel-header-title">🤝 Active Negotiation Monitor</span>
                  <div className="active-neg-box">
                    {activeNegotiations.length === 0 ? (
                      <div className="active-neg-empty">No active negotiations in progress</div>
                    ) : (
                      activeNegotiations.map((neg, idx) => (
                        <div key={idx} className="neg-card">
                          <div className="neg-card-top">
                            <div className="neg-ids">
                              <span className="neg-vehicle-tag">Vehicle {neg.vehicle_a}</span>
                              <span style={{ color: '#94a3b8', fontSize: '0.75rem' }}>vs</span>
                              <span className="neg-vehicle-tag">Vehicle {neg.vehicle_b}</span>
                            </div>
                            <span className="neg-age">{neg.age.toFixed(1)}s active</span>
                          </div>
                          <div className="neg-card-row">
                            <span className="neg-label">Priority Scores:</span>
                            <span className="neg-val">{neg.priority_a.toFixed(2)} / {neg.priority_b.toFixed(2)}</span>
                          </div>
                          <div className="neg-card-row">
                            <span className="neg-label">Priority Winner:</span>
                            <span className="neg-val winner">Vehicle {neg.winner}</span>
                          </div>
                          <div className="neg-card-row">
                            <span className="neg-label">Yielding Agent:</span>
                            <span className="neg-val yielder">Vehicle {neg.yielding}</span>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

// Helper to format simulated epoch timestamp to local Javascript date
function dataTimestampToDate(sec) {
  // If simulated relative time, translate to virtual clock time or use relative seconds
  return Date.now();
}
