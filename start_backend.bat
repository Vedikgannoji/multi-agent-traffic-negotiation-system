@echo off
echo Starting Traffic Simulation Backend...
echo.
echo Backend will run at http://localhost:8000
echo Press Ctrl+C to stop
echo.

uvicorn backend.main:app --reload

pause