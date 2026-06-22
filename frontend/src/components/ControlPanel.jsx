import { useState, useEffect } from 'react';
import './ControlPanel.css';

export default function ControlPanel({ simulationState, isConnected, onControlAction }) {
  const control = simulationState?.control || null;
  const vehicles = simulationState?.vehicles || [];
  const safety = simulationState?.safety || null;
  const agentStates = simulationState?.agent_states || null;

  // Local state for immediate slider tracking, synced to control.target_vehicle_count on update
  const [sliderTarget, setSliderTarget] = useState(4);

  useEffect(() => {
    if (control?.target_vehicle_count !== undefined) {
      setSliderTarget(control.target_vehicle_count);
    }
  }, [control?.target_vehicle_count]);

  if (!isConnected || !simulationState) {
    return (
      <aside className="cp cp--offline">
        <div className="cp-header">
          <span className="cp-title">Control Panel</span>
        </div>
        <div style={{ padding: '2rem 1rem', color: '#666', fontSize: '0.85rem', textAlign: 'center' }}>
          Awaiting simulation connection...
        </div>
      </aside>
    );
  }

  const speed = control?.speed || 1.0;
  const paused = control?.paused || false;

  // ── Actions ───────────────────────────────────────────────────────────────

  const setSimSpeed = (v) => {
    onControlAction('/control/speed', 'POST', { speed: v });
  };

  const togglePause = () => {
    onControlAction(`/control/${paused ? 'resume' : 'pause'}`, 'POST');
  };

  const reset = () => {
    onControlAction('/control/reset', 'POST');
  };

  const updateCount = (n) => {
    onControlAction('/control/vehicle-count', 'POST', { target_count: n });
  };

  // ── Derived metrics ───────────────────────────────────────────────────────
  const byState = vehicles.reduce((acc, v) => {
    acc[v.state] = (acc[v.state] || 0) + 1;
    return acc;
  }, {});

  const totalVehicles  = vehicles.length;
  const totalSpawned   = control?.total_spawned    ?? 0;
  const maxVehicles    = control?.max_vehicle_count ?? 20;

  const collisions     = safety?.total_collisions       ?? 0;
  const safeCrossings  = safety?.total_safe_crossings   ?? 0;
  const failedCrossings = safety?.total_failed_crossings ?? 0;
  const safetyPct      = safety?.safety_accuracy_pct    ?? 100;

  const approaching = agentStates?.approaching ?? 0;
  const negotiating = agentStates?.negotiating ?? 0;
  const waiting     = agentStates?.waiting ?? 0;
  const crossing    = agentStates?.crossing ?? 0;

  const safetyColor = safetyPct >= 95 ? '#44ff88'
                    : safetyPct >= 80 ? '#ffb84a'
                    : '#ff4444';

  const totalWaitTime = vehicles.reduce((sum, v) => sum + (v.waiting_time || 0), 0);
  const avgWaitTime = vehicles.length > 0 ? (totalWaitTime / vehicles.length).toFixed(1) : "0.0";

  return (
    <aside className="cp">

      {/* Header */}
      <div className="cp-header">
        <span className="cp-title">Control Panel</span>
        <span className={`cp-pill ${paused ? 'cp-pill--paused' : 'cp-pill--running'}`}>
          {paused ? '⏸ Paused' : '▶ Running'}
        </span>
      </div>

      {/* ── Section 1: Simulation Controls ── */}
      <section className="cp-section">
        <p className="cp-label">Simulation</p>
        <div className="cp-row">
          <button
            className={`cp-btn cp-btn--half ${paused ? 'cp-btn--green' : 'cp-btn--amber'}`}
            onClick={togglePause}
          >
            {paused ? '▶ Resume' : '⏸ Pause'}
          </button>
          <button className="cp-btn cp-btn--half cp-btn--red" onClick={reset}>
            ↺ Reset
          </button>
        </div>
        <div className="cp-row cp-row--5">
          {[1, 2, 4, 8, 16].map(s => (
            <button
              key={s}
              className={`cp-btn cp-btn--speed ${speed === s ? 'cp-btn--speed-active' : ''}`}
              onClick={() => setSimSpeed(s)}
            >
              {s}×
            </button>
          ))}
        </div>
      </section>

      {/* ── Section 2: Vehicle Density ── */}
      <section className="cp-section">
        <div className="cp-label-row">
          <p className="cp-label">Vehicle Density</p>
          <span className="cp-count">{sliderTarget}</span>
        </div>
        <input
          type="range" min="0" max="20" value={sliderTarget}
          className="cp-slider"
          onChange={e => setSliderTarget(+e.target.value)}
          onMouseUp={e => updateCount(sliderTarget)}
          onTouchEnd={e => updateCount(sliderTarget)}
        />
        <div className="cp-slider-ends"><span>0</span><span>20</span></div>
        <p className="cp-hint">{totalVehicles} / {maxVehicles} active</p>
      </section>

      {/* ── Section 3: Agent States (Phase 1) ── */}
      <section className="cp-section">
        <p className="cp-label">Agent States</p>
        <div className="cp-metrics">
          <Metric label="Approaching" value={approaching} accent="#4a9eff" />
          <Metric label="Negotiating" value={negotiating} accent="#fbbf24" />
          <Metric label="Waiting"     value={waiting}     accent="#f97316" />
          <Metric label="Crossing"    value={crossing}    accent="#44ff88" />
        </div>
      </section>

      {/* ── Section 4: Traffic Metrics ── */}
      <section className="cp-section">
        <p className="cp-label">Traffic</p>
        <div className="cp-metrics">
          <Metric label="Moving"        value={byState.moving   ?? 0} accent="#4a9eff" />
          <Metric label="Waiting"       value={byState.waiting  ?? 0} accent="#f97316" />
          <Metric label="Crossing"      value={byState.crossing ?? 0} accent="#44ff88" />
          <Metric label="Avg Wait (s)"  value={avgWaitTime}            accent="#f97316" />
          <Metric label="Total Vehicles" value={totalVehicles}         accent="#ccc"    />
          <Metric label="Total Spawned" value={totalSpawned}           accent="#ccc"    />
        </div>
      </section>

      {/* ── Section 5: Safety Metrics ── */}
      <section className="cp-section cp-section--last">
        <p className="cp-label">Safety</p>
        <div className="cp-metrics">
          <Metric
            label="Collisions"
            value={collisions}
            accent={collisions > 0 ? '#ff4444' : '#ccc'}
          />
          <Metric label="Safe Crossings"   value={safeCrossings}   accent="#44ff88" />
          <Metric label="Failed Crossings" value={failedCrossings} accent={failedCrossings > 0 ? '#ff6060' : '#ccc'} />
          <Metric
            label="Passing Accuracy"
            value={`${safetyPct}%`}
            accent={safetyColor}
          />
        </div>
      </section>

    </aside>
  );
}

function Metric({ label, value, accent }) {
  return (
    <div className="cp-metric">
      <span className="cp-metric-label">{label}</span>
      <span className="cp-metric-value" style={{ color: accent }}>{value}</span>
    </div>
  );
}
