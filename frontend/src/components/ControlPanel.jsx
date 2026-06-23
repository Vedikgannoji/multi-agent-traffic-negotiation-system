import { useState, useEffect } from 'react';
import './ControlPanel.css';

export default function ControlPanel({ simulationState, isConnected, onControlAction }) {
  const control = simulationState?.control || null;
  const controlMode = control?.control_mode || "assisted";
  const speed = control?.speed || 1.0;
  const paused = control?.paused || false;
  
  // Local state for immediate slider tracking
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
        <div className="cp-offline-message">
          Awaiting simulation connection...
        </div>
      </aside>
    );
  }

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

  const setControlMode = (mode) => {
    onControlAction('/control/mode', 'POST', { mode });
  };

  const triggerSpawn = (direction) => {
    onControlAction(`/spawn/${direction}`, 'POST');
  };

  return (
    <aside className="cp">
      {/* Header */}
      <div className="cp-header">
        <span className="cp-title">Simulation Settings</span>
        <span className={`cp-pill ${paused ? 'cp-pill--paused' : 'cp-pill--running'}`}>
          {paused ? 'Paused' : 'Active'}
        </span>
      </div>

      {/* Play / Pause / Reset */}
      <section className="cp-section">
        <p className="cp-label">Simulation State</p>
        <div className="cp-row">
          <button
            className={`cp-btn cp-btn--primary ${paused ? 'cp-btn--resume' : 'cp-btn--pause'}`}
            onClick={togglePause}
          >
            {paused ? '▶ Resume' : '⏸ Pause'}
          </button>
          <button className="cp-btn cp-btn--secondary" onClick={reset}>
            ↺ Reset
          </button>
        </div>
      </section>

      {/* Simulation Speed */}
      <section className="cp-section">
        <p className="cp-label">Speed Multiplier</p>
        <div className="cp-grid-speed">
          {[1, 2, 4, 8, 16].map(s => (
            <button
              key={s}
              className={`cp-btn-speed ${speed === s ? 'cp-btn-speed--active' : ''}`}
              onClick={() => setSimSpeed(s)}
            >
              {s}x
            </button>
          ))}
        </div>
      </section>

      {/* Control Mode */}
      <section className="cp-section">
        <p className="cp-label">Operating Mode</p>
        <div className="cp-column-mode">
          <button
            className={`cp-btn-mode ${controlMode === 'assisted' ? 'cp-btn-mode--active' : ''}`}
            onClick={() => setControlMode('assisted')}
          >
            Reservation Mode
          </button>
          <button
            className={`cp-btn-mode ${controlMode === 'pure_v2v' ? 'cp-btn-mode--active' : ''}`}
            onClick={() => setControlMode('pure_v2v')}
          >
            Pure V2V Mode (Exp)
          </button>
        </div>
      </section>

      {/* Target Vehicle Density */}
      <section className="cp-section">
        <div className="cp-label-row">
          <p className="cp-label">Target Vehicle Density</p>
          <span className="cp-count">{sliderTarget}</span>
        </div>
        <input
          type="range"
          min="0"
          max="20"
          value={sliderTarget}
          className="cp-slider"
          onChange={e => setSliderTarget(+e.target.value)}
          onMouseUp={() => updateCount(sliderTarget)}
          onTouchEnd={() => updateCount(sliderTarget)}
        />
        <div className="cp-slider-ends">
          <span>0</span>
          <span>20</span>
        </div>
      </section>

      {/* Manual Vehicle Spawning */}
      <section className="cp-section cp-section--last">
        <p className="cp-label">Manual Spawn Agent</p>
        <div className="cp-grid-spawn">
          <button className="cp-btn cp-btn--spawn" onClick={() => triggerSpawn('north')}>
            ↑ North
          </button>
          <button className="cp-btn cp-btn--spawn" onClick={() => triggerSpawn('south')}>
            ↓ South
          </button>
          <button className="cp-btn cp-btn--spawn" onClick={() => triggerSpawn('east')}>
            → East
          </button>
          <button className="cp-btn cp-btn--spawn" onClick={() => triggerSpawn('west')}>
            ← West
          </button>
        </div>
      </section>
    </aside>
  );
}
