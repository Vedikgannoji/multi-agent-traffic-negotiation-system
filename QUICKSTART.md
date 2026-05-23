# Quick Start Guide

## Prerequisites

1. **Python 3.8+** with pip
2. **Node.js 16+** with npm
3. Install Python dependencies:
   ```bash
   pip install fastapi uvicorn
   ```
4. Install frontend dependencies:
   ```bash
   cd frontend
   npm install
   cd ..
   ```

## Running the Full System

### Option 1: Manual (Recommended for Development)

**Terminal 1 - Backend:**
```bash
uvicorn backend.main:app --reload
```
Backend runs at `http://localhost:8000`

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```
Frontend runs at `http://localhost:5173`

**Open browser:** Navigate to `http://localhost:5173`

### Option 2: Using Batch Scripts (Windows)

**Terminal 1:**
```bash
start_backend.bat
```

**Terminal 2:**
```bash
cd frontend
start_frontend.bat
```

## Testing Individual Components

### Test Standalone Simulation
```bash
python simulation/environment.py
```
Runs console-only simulation for 20 ticks.

### Test Backend API
```bash
uvicorn backend.main:app --reload
```
Then visit:
- `http://localhost:8000` - API info
- `http://localhost:8000/traffic/state` - Live vehicle data
- `http://localhost:8000/traffic/info` - Road config

### Test Frontend (Mock Mode)
If backend isn't running, frontend shows connection error with instructions.

## What You'll See

### Backend Console
```
✓ Simulation thread started
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### Frontend Browser
- **Header:** Live stats (lanes, road length, vehicle count)
- **Road View:** 3 lanes with animated car emojis moving left to right
- **Vehicle List:** Grid showing each vehicle's details

### How It Works
1. Backend spawns 8 vehicles at startup
2. Simulation updates every 1 second
3. Frontend polls `/traffic/state` every 500ms
4. CSS transitions smooth out the movement
5. Vehicles respawn when they exit the road

## Troubleshooting

**"Backend Not Connected" error:**
- Make sure backend is running on port 8000
- Check for CORS errors in browser console
- Verify `http://localhost:8000/traffic/state` returns JSON

**Import errors:**
- Run commands from project root directory
- Ensure `simulation/__init__.py` exists
- Check Python path includes project root

**Port already in use:**
- Backend: Change port with `uvicorn backend.main:app --port 8001`
- Frontend: Vite will auto-increment to 5174, 5175, etc.

## Next Steps

1. Modify `backend/main.py` to change simulation parameters
2. Edit `frontend/src/components/TrafficVisualization.jsx` for UI changes
3. Adjust `POLL_INTERVAL` in frontend for faster/slower updates
4. Add more vehicles by changing spawn count in `backend/main.py`
