import './App.css';
import TrafficSimulation from './components/TrafficSimulation';
import ControlPanel from './components/ControlPanel';

export default function App() {
  return (
    <div className="app">
      <div className="app-sim">
        <TrafficSimulation />
      </div>
      <div className="app-panel">
        <ControlPanel />
      </div>
    </div>
  );
}
