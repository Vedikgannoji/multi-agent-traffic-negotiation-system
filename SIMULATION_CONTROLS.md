# Simulation Controls & Testing Guide

## Overview

The traffic simulation now includes a **comprehensive testing and control panel** that transforms it into a professional traffic engineering testing tool. This guide explains how to use the controls for debugging, stress testing, and validating intersection behavior.

## Control Panel Features

### 1. Manual Vehicle Spawning 🚗

**Purpose**: Instantly create vehicles from specific directions for targeted testing.

**Controls**:
- **↓ North** - Spawn vehicle from north
- **↑ South** - Spawn vehicle from south  
- **← East** - Spawn vehicle from east
- **→ West** - Spawn vehicle from west

**Behavior**:
- Creates vehicle immediately at spawn position
- Assigns random valid destination (not same as source)
- Randomized speed within configured limits (10-15 m/s)
- Respects 50m minimum spacing requirement
- Shows error if insufficient space

**Use Cases**:
```
Test perpendicular crossing:
1. Spawn North (goes South)
2. Immediately spawn East (goes West)
3. Observe conflict detection and queueing

Test opposite left turns:
1. Spawn North (random destination)
2. If it turns left, spawn South
3. Observe center conflict prevention

Test same-direction queueing:
1. Spawn North
2. Spawn North again
3. Spawn North again
4. Observe FIFO queue behavior
```

### 2. Vehicle Count Control 🔢

**Purpose**: Dynamically adjust traffic density for stress testing.

**Control**: Slider (0-30 vehicles)

**Behavior**:
- Updates target vehicle count in real-time
- Backend automatically spawns/maintains target count
- Respects spacing requirements (won't force spawn)
- Useful for testing congestion scenarios

**Testing Scenarios**:
```
Light traffic (1-4 vehicles):
- Test basic coordination
- Verify collision-free operation
- Observe individual vehicle behavior

Medium traffic (5-10 vehicles):
- Test queue management
- Verify FIFO ordering
- Observe waiting behavior

Heavy traffic (15-30 vehicles):
- Stress test intersection
- Test performance under load
- Verify no deadlocks
- Check conflicts prevented counter
```

### 3. Simulation Speed Control ⚡

**Purpose**: Scale simulation time for rapid testing or slow-motion debugging.

**Controls**:
- **1x** - Normal speed (real-time)
- **2x** - Double speed (faster testing)
- **4x** - Quadruple speed (stress testing)

**Behavior**:
- Scales simulation physics (vehicle movement, update timing)
- Frontend interpolation remains smooth (60fps)
- Backend updates faster/slower accordingly
- Useful for rapid iteration

**Use Cases**:
```
1x Speed (Normal):
- Default operation
- Realistic behavior observation
- Portfolio demonstrations

2x Speed (Fast):
- Faster testing iterations
- Quickly generate traffic scenarios
- Efficient debugging

4x Speed (Stress):
- Rapid stress testing
- Generate many conflicts quickly
- Performance validation
- High-throughput testing
```

**Technical Implementation**:
```python
# Backend scales update timing
manager.update(dt=1.0 * simulation_speed)
time.sleep(1.0 / simulation_speed)

# Frontend interpolation unaffected
# Still renders at 60fps smoothly
```

### 4. Pause/Resume ⏸▶

**Purpose**: Freeze simulation for inspection and debugging.

**Controls**:
- **⏸ Pause** - Freeze simulation
- **▶ Resume** - Continue simulation

**Behavior**:
- Pauses backend simulation loop
- Frontend remains responsive
- No state desynchronization
- Vehicles frozen in place
- Can inspect exact positions

**Use Cases**:
```
Debugging conflicts:
1. Observe vehicles approaching
2. Pause just before intersection
3. Inspect positions and states
4. Check reservation status
5. Resume to see resolution

Analyzing queues:
1. Let traffic build up
2. Pause simulation
3. Count waiting vehicles per direction
4. Verify FIFO ordering
5. Resume and observe flow

Taking screenshots:
1. Pause at interesting moment
2. Capture screenshot
3. Resume simulation
```

### 5. Reset Simulation 🔄

**Purpose**: Clear all state and start fresh.

**Control**: **🔄 Reset** button

**Behavior**:
- Removes all vehicles instantly
- Clears all reservations
- Resets intersection state
- Clears waiting queues
- Resets vehicle ID counter
- Simulation continues running (ready for new vehicles)

**Use Cases**:
```
Quick restart:
1. Test scenario completes
2. Click Reset
3. Immediately start new test

Clean slate:
1. Traffic becomes congested
2. Reset to clear
3. Start controlled test

Reproducible testing:
1. Reset simulation
2. Manually spawn specific pattern
3. Observe behavior
4. Reset and repeat
```

## Testing Workflows

### Workflow 1: Collision Detection Validation

**Objective**: Verify zero collisions under all scenarios

**Steps**:
1. Reset simulation
2. Set speed to 2x for faster testing
3. Set vehicle count to 15-20
4. Let simulation run for 2 minutes
5. Observe "Conflicts Prevented" counter
6. Verify counter increases (conflicts detected)
7. Verify zero visual overlaps (conflicts prevented)

**Expected Result**: Conflicts prevented > 0, zero collisions

### Workflow 2: Perpendicular Crossing Test

**Objective**: Test classic intersection conflict

**Steps**:
1. Reset simulation
2. Set speed to 1x (normal)
3. Spawn North (wait for it to approach intersection)
4. Spawn East (should conflict with North)
5. Observe: East waits at stop line
6. Observe: North crosses first
7. Observe: East proceeds after North clears

**Expected Result**: Proper queueing, no overlap

### Workflow 3: Opposite Left Turn Test

**Objective**: Test center collision prevention

**Steps**:
1. Reset simulation
2. Manually spawn vehicles until you get:
   - North turning left (to West)
   - South turning left (to East)
3. Observe: Second vehicle waits
4. Observe: First vehicle crosses center
5. Observe: Second vehicle proceeds after clearance

**Expected Result**: No center collision

### Workflow 4: Same-Direction Queue Test

**Objective**: Verify FIFO queueing

**Steps**:
1. Reset simulation
2. Spawn North (3 times rapidly)
3. Observe: Vehicles line up in order
4. Observe: 50m spacing maintained
5. Observe: First vehicle crosses first
6. Observe: Second vehicle follows
7. Observe: Third vehicle follows

**Expected Result**: Orderly FIFO queue

### Workflow 5: Stress Test

**Objective**: Validate performance under load

**Steps**:
1. Reset simulation
2. Set vehicle count to 30 (maximum)
3. Set speed to 4x (maximum)
4. Let run for 5 minutes
5. Monitor:
   - CPU usage (<10% expected)
   - Frame rate (60fps expected)
   - Conflicts prevented (should increase)
   - No crashes or freezes

**Expected Result**: Stable operation, smooth rendering

### Workflow 6: Congestion Recovery Test

**Objective**: Verify no deadlocks under congestion

**Steps**:
1. Reset simulation
2. Set vehicle count to 25
3. Set speed to 2x
4. Let traffic build up (all directions)
5. Observe: Vehicles queue at all stop lines
6. Observe: Intersection continues processing
7. Observe: No permanent deadlock
8. Observe: Queues eventually clear

**Expected Result**: Continuous flow, no deadlock

## API Endpoints

### Manual Spawning

```bash
# Spawn from North
curl -X POST http://localhost:8000/spawn/north

# Spawn from South with specific destination
curl -X POST http://localhost:8000/spawn/south \
  -H "Content-Type: application/json" \
  -d '{"destination": "east"}'

# Response
{
  "success": true,
  "vehicle": {
    "id": 5,
    "source": "north",
    "destination": "south",
    "turn_type": "straight",
    "position": 350.0,
    "speed": 12.3
  },
  "total_vehicles": 5
}
```

### Vehicle Count Control

```bash
# Set target count to 10
curl -X POST http://localhost:8000/control/vehicle-count \
  -H "Content-Type: application/json" \
  -d '{"target_count": 10}'

# Response
{
  "success": true,
  "target_count": 10,
  "max_count": 30,
  "current_count": 5
}
```

### Simulation Speed

```bash
# Set 2x speed
curl -X POST http://localhost:8000/control/speed \
  -H "Content-Type: application/json" \
  -d '{"speed": 2.0}'

# Response
{
  "success": true,
  "speed": 2.0,
  "description": "2.0x speed"
}
```

### Pause/Resume

```bash
# Pause
curl -X POST http://localhost:8000/control/pause

# Resume
curl -X POST http://localhost:8000/control/resume

# Response
{
  "success": true,
  "paused": true,
  "message": "Simulation paused"
}
```

### Reset

```bash
# Reset simulation
curl -X POST http://localhost:8000/control/reset

# Response
{
  "success": true,
  "message": "Simulation reset",
  "vehicles_removed": 0,
  "reservations_cleared": 15,
  "state": {
    "vehicles": 0,
    "active_reservations": 0,
    "target_count": 4
  }
}
```

### Control Status

```bash
# Get current control state
curl http://localhost:8000/control/status

# Response
{
  "running": true,
  "paused": false,
  "speed": 1.0,
  "target_vehicle_count": 4,
  "max_vehicle_count": 30,
  "current_vehicle_count": 5,
  "active_reservations": 1,
  "total_reservations": 47,
  "conflicts_prevented": 23
}
```

## Debugging Techniques

### Technique 1: Slow Motion Analysis

```
1. Set speed to 1x
2. Spawn specific conflict scenario
3. Watch vehicles approach in real-time
4. Observe exact moment of conflict detection
5. Verify proper waiting behavior
```

### Technique 2: Rapid Iteration

```
1. Set speed to 4x
2. Set vehicle count to 20
3. Let run for 30 seconds
4. Check conflicts prevented
5. Reset and repeat with different count
```

### Technique 3: Freeze Frame Inspection

```
1. Let traffic build up
2. Pause simulation
3. Open browser dev tools (F12)
4. Inspect vehicle positions in console
5. Verify spacing and states
6. Resume simulation
```

### Technique 4: Controlled Scenarios

```
1. Reset simulation
2. Set vehicle count to 0 (no auto-spawn)
3. Manually spawn specific pattern:
   - North, East (perpendicular)
   - North, South (opposite left)
   - North, North, North (queue)
4. Observe specific behavior
5. Reset and try different pattern
```

## Performance Monitoring

### Metrics to Watch

**Frontend (Browser Dev Tools)**:
- Frame rate: Should stay at 60fps
- Memory: Should stay under 150MB
- Network: ~1KB/s (polling)

**Backend (Terminal)**:
- CPU: Should stay under 10%
- Memory: Should stay under 100MB
- Response time: <10ms per request

**Simulation**:
- Conflicts prevented: Should increase over time
- Active reservations: Should fluctuate (0-2)
- Vehicle count: Should match target (±1)

### Stress Test Benchmarks

| Vehicle Count | Speed | Expected FPS | Expected CPU | Expected Conflicts/min |
|---------------|-------|--------------|--------------|------------------------|
| 5 | 1x | 60 | <5% | 5-10 |
| 10 | 1x | 60 | <5% | 10-20 |
| 20 | 2x | 60 | <8% | 40-60 |
| 30 | 4x | 60 | <10% | 100-150 |

## Troubleshooting

### Issue: Spawn button doesn't work

**Possible Causes**:
- Maximum vehicle count reached
- Insufficient space (50m required)
- Backend not running

**Solutions**:
1. Check current vehicle count
2. Reduce vehicle count or reset
3. Verify backend is running: `curl http://localhost:8000/`

### Issue: Simulation feels slow

**Possible Causes**:
- Speed set to 1x (normal)
- Too many vehicles (>25)
- Browser performance

**Solutions**:
1. Increase speed to 2x or 4x
2. Reduce vehicle count
3. Close other browser tabs
4. Check CPU usage

### Issue: Vehicles still overlap

**Possible Causes**:
- Visual interpolation lag
- Actual collision (bug)

**Solutions**:
1. Pause simulation and inspect
2. Check conflicts prevented counter (should increase)
3. If counter doesn't increase, report bug
4. Verify 50m following distance in code

### Issue: Reset doesn't work

**Possible Causes**:
- Backend error
- Network issue

**Solutions**:
1. Check browser console for errors
2. Verify backend is running
3. Try manual reset: `curl -X POST http://localhost:8000/control/reset`
4. Restart backend if needed

## Best Practices

### For Testing

1. **Start Simple**: Test with 1-2 vehicles first
2. **Increase Gradually**: Add complexity incrementally
3. **Use Reset Often**: Start fresh for each test
4. **Document Findings**: Note any unexpected behavior
5. **Vary Speed**: Test at different speeds

### For Debugging

1. **Pause Frequently**: Freeze to inspect state
2. **Use Manual Spawn**: Control exact scenarios
3. **Check Statistics**: Monitor conflicts prevented
4. **Slow Motion**: Use 1x speed for detailed observation
5. **Isolate Issues**: Test one scenario at a time

### For Stress Testing

1. **Max Everything**: 30 vehicles, 4x speed
2. **Run Extended**: Let run for 5+ minutes
3. **Monitor Performance**: Watch CPU, FPS, memory
4. **Check Stability**: Verify no crashes
5. **Validate Correctness**: Conflicts prevented should increase

## Advanced Usage

### Automated Testing Script

```bash
#!/bin/bash
# Automated stress test

echo "Starting stress test..."

# Reset
curl -X POST http://localhost:8000/control/reset

# Set high vehicle count
curl -X POST http://localhost:8000/control/vehicle-count \
  -H "Content-Type: application/json" \
  -d '{"target_count": 25}'

# Set high speed
curl -X POST http://localhost:8000/control/speed \
  -H "Content-Type: application/json" \
  -d '{"speed": 4.0}'

# Wait 5 minutes
sleep 300

# Get final stats
curl http://localhost:8000/control/status

echo "Stress test complete"
```

### Reproducible Test Sequence

```bash
# Test perpendicular crossing
curl -X POST http://localhost:8000/control/reset
sleep 1
curl -X POST http://localhost:8000/spawn/north
sleep 2
curl -X POST http://localhost:8000/spawn/east
# Observe conflict detection
```

## Summary

The simulation controls provide:

✅ **Manual Control** - Spawn vehicles on demand  
✅ **Dynamic Configuration** - Adjust count and speed  
✅ **Pause/Resume** - Freeze for inspection  
✅ **Quick Reset** - Start fresh instantly  
✅ **Real-time Statistics** - Monitor behavior  

This transforms the simulation into a **professional traffic engineering testing tool** suitable for:
- Collision detection validation
- Intersection algorithm debugging
- Performance stress testing
- Reproducible scenario testing
- Educational demonstrations

**Result**: Rapid, controlled, reproducible testing of traffic coordination algorithms.
