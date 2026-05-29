import { useState, useEffect } from 'react';
import './ControlPanel.css';

const API_URL = 'http://localhost:8000';

export default function ControlPanel() {
  const [status,   setStatus]   = useState(null);
  const [vehicles, setVehicles] = useState([]);
  const [safety,   setSafety]   = useState(null);
  const [target,   setTarget]   = useState(4);
  const [speed,    setSpeed]    = useState(1.0);
  const [paused,   setPaused]   = useState(false);

  // ── Poll all three endpoints every second ─────────────────────────────────
  useEffect(() => {
    let cancelled = false;

    const tick = async () => {
      try {
        const [ctrl, traffic, safetyData] = await Promise.all([
          fetch(`${API_URL}/control/status`).then(r => r.json()),
          fetch(`${API_URL}/traffic/state`).then(r => r.json()),
          fetch(`${API_URL}/safety/stats`).then(r => r.json()),
        ]);
        if (cancelled) return;

        setStatus(ctrl);
        setVehicles(traffic.vehicles ?? []);
        setSafety(safetyData);
        setTarget(ctrl.target_vehicle_count);
        setSpeed(ctrl.speed);
        setPaused(ctrl.paused);
      } catch (_) {}
    };

    tick();
    const id = setInterval(tick, 1000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // ── Actions ───────────────────────────────────────────────────────────────

  const setSimSpeed = async (v) => {
    setSpeed(v);
    try {
      await fetch(`${API_URL}/control/speed`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ speed: v }),
      });
    } catch (_) {}
  };

  const togglePause = async () => {
    const next = !paused;
    setPaused(next);
    try {
      await fetch(`${API_URL}/control/${next ? 'pause' : 'resume'}`, { method: 'POST' });
    } catch (_) {}
  };

  const reset = async () => {
    try {
      await fetch(`${API_URL}/control/reset`, { method: 'POST' });
    } catch (_) {}
  };

  const updateCount = async (n) => {
    setTarget(n);
    try {
      await fetch(`${API_URL}/control/vehicle-count`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_count: n }),
      });
    } catch (_) {}
  };

  // ── Derived metrics ───────────────────────────────────────────────────────
  const byState = vehicles.reduce((acc, v) => {
    acc[v.state] = (acc[v.state] || 0) + 1;
    return acc;
  }, {});

  const totalVehicles  = vehicles.length;
  const totalSpawned   = status?.total_spawned    ?? 0;
  const maxVehicles    = status?.max_vehicle_count ?? 20;

  const collisions     = safety?.total_collisions       ?? 0;
  const safeCrossings  = safety?.total_safe_crossings   ?? 0;
  const failedCrossings = safety?.total_failed_crossings ?? 0;
  const safetyPct      = safety?.safety_accuracy_pct    ?? 100;

  const safetyColor = safetyPct >= 95 ? '#44ff88'
                    : safetyPct >= 80 ? '#ffb84a'
                    : '#ff4444';

  // ── Render ────────────────────────────────────────────────────────────────
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
        <div className="cp-row cp-row--3">
          {[1, 2, 4].map(s => (
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
          <span className="cp-count">{target}</span>
        </div>
        <input
          type="range" min="0" max="20" value={target}
          className="cp-slider"
          onChange={e => setTarget(+e.target.value)}
          onMouseUp={e => updateCount(+e.target.value)}
          onTouchEnd={e => updateCount(+e.target.value)}
        />
        <div className="cp-slider-ends"><span>0</span><span>20</span></div>
        <p className="cp-hint">{totalVehicles} / {maxVehicles} active</p>
      </section>

      {/* ── Section 3: Traffic Metrics ── */}
      <section className="cp-section">
        <p className="cp-label">Traffic</p>
        <div className="cp-metrics">
          <Metric label="Moving"        value={byState.moving   ?? 0} accent="#4a9eff" />
          <Metric label="Waiting"       value={byState.waiting  ?? 0} accent="#ffb84a" />
          <Metric label="Crossing"      value={byState.crossing ?? 0} accent="#44ff88" />
          <Metric label="Total Vehicles" value={totalVehicles}         accent="#ccc"    />
          <Metric label="Total Spawned" value={totalSpawned}           accent="#ccc"    />
        </div>
      </section>

      {/* ── Section 4: Safety Metrics ── */}
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
