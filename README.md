# Multi-Agent Traffic Simulation System

A modular AI traffic simulation with live visualization.

## Architecture

```
multi-agent-traffic-system/
├── simulation/          # Core simulation engine (Python)
│   ├── vehicle.py       # Vehicle logic
│   ├── road.py          # Road structure
│   ├── traffic_manager.py  # Traffic management
│   ├── environment.py   # Standalone simulation runner
│   └── communication.py # V2V/V2X stubs
├── backend/             # FastAPI REST API
│   └── main.py          # Exposes simulation state
└── frontend/            # React visualization
    └── src/
        └── components/
            └── TrafficVisualization.jsx
```

## Features

- **Multi-lane traffic simulation** with collision avoidance
- **Real-time visualization** with smooth animations
- **REST API** for accessing simulation state
- **Modular architecture** ready for ML/RL extensions

## Quick Start

### 1. Install Dependencies

**Backend:**
```bash
pip install fastapi uvicorn
```

**Frontend:**
```bash
cd frontend
npm install
```

### 2. Run Backend

From project root:
```bash
uvicorn backend.main:app --reload
```

Backend runs at `http://localhost:8000`

API endpoints:
- `GET /` - API info
- `GET /traffic/state` - Current vehicle positions
- `GET /traffic/info` - Road configuration

### 3. Run Frontend

In a new terminal:
```bash
cd frontend
npm run dev
```

Frontend runs at `http://localhost:5173`

### 4. View Live Simulation

Open `http://localhost:5173` in your browser. You'll see:
- 3-lane road with moving vehicles
- Real-time position updates (500ms polling)
- Vehicle details (ID, lane, position, speed)

## Standalone Simulation

Run the simulation without the API:
```bash
python simulation/environment.py
```

## How It Works

### Backend
- Runs simulation in a background thread
- Updates vehicle positions every second
- Spawns new vehicles when old ones leave the road
- Thread-safe state access via locks

### Frontend
- Polls `/traffic/state` every 500ms
- Renders vehicles as positioned elements
- CSS transitions create smooth movement
- Responsive grid layout for vehicle details

### Simulation Logic
- Vehicles move at random speeds (10-30 m/s)
- Simple collision avoidance: rear vehicle slows when gap < 10m
- Vehicles respawn at road start to maintain traffic flow

## Next Steps

- [ ] WebSocket support for real-time updates
- [ ] Reinforcement learning for vehicle behavior
- [ ] Lane changing logic
- [ ] Traffic light integration
- [ ] V2V communication implementation
- [ ] Performance metrics dashboard
