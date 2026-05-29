# Simulation Controls - Quick Reference

## 🎛️ Control Panel Overview

Located on the right sidebar of the interface.

## Manual Spawning

| Button | Action | Shortcut API |
|--------|--------|--------------|
| ↓ North | Spawn from north | `POST /spawn/north` |
| ↑ South | Spawn from south | `POST /spawn/south` |
| ← East | Spawn from east | `POST /spawn/east` |
| → West | Spawn from west | `POST /spawn/west` |

**Note**: Requires 50m clearance. Max 30 vehicles.

## Vehicle Count

**Slider**: 0-30 vehicles

**Effect**: Adjusts target vehicle count dynamically

**API**: `POST /control/vehicle-count {"target_count": 10}`

## Simulation Speed

| Button | Speed | Use Case |
|--------|-------|----------|
| 1x | Normal | Default, realistic |
| 2x | Double | Faster testing |
| 4x | Quad | Stress testing |

**API**: `POST /control/speed {"speed": 2.0}`

## Pause/Resume

| Button | Action | State |
|--------|--------|-------|
| ⏸ Pause | Freeze simulation | Paused |
| ▶ Resume | Continue simulation | Running |

**API**: 
- `POST /control/pause`
- `POST /control/resume`

## Reset

**Button**: 🔄 Reset

**Effect**: 
- Removes all vehicles
- Clears reservations
- Resets intersection
- Continues running

**API**: `POST /control/reset`

## Statistics Display

| Metric | Description |
|--------|-------------|
| Vehicles | Current vehicle count |
| Reservations | Active reservations |
| Total Spawned | Lifetime vehicle count |
| Conflicts Prevented | Collisions avoided |

## Quick Testing Patterns

### Test Perpendicular Crossing
```
1. Reset
2. Spawn North
3. Spawn East (when North approaches)
4. Observe conflict detection
```

### Test Queue Behavior
```
1. Reset
2. Spawn North (3x rapidly)
3. Observe FIFO queueing
```

### Stress Test
```
1. Reset
2. Set count to 30
3. Set speed to 4x
4. Run for 5 minutes
```

### Debug Specific Scenario
```
1. Reset
2. Set count to 0
3. Manually spawn pattern
4. Pause to inspect
5. Resume to observe
```

## API Quick Commands

```bash
# Spawn vehicle
curl -X POST http://localhost:8000/spawn/north

# Set vehicle count
curl -X POST http://localhost:8000/control/vehicle-count \
  -H "Content-Type: application/json" \
  -d '{"target_count": 15}'

# Set speed
curl -X POST http://localhost:8000/control/speed \
  -H "Content-Type: application/json" \
  -d '{"speed": 2.0}'

# Pause
curl -X POST http://localhost:8000/control/pause

# Resume
curl -X POST http://localhost:8000/control/resume

# Reset
curl -X POST http://localhost:8000/control/reset

# Get status
curl http://localhost:8000/control/status
```

## Keyboard Shortcuts

*Note: Currently no keyboard shortcuts. Use mouse/API.*

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Spawn fails | Check vehicle count < 30 |
| Slow performance | Reduce vehicle count |
| Vehicles overlap | Check conflicts prevented counter |
| Reset doesn't work | Restart backend |

## Performance Targets

| Vehicles | Speed | Expected FPS | Expected CPU |
|----------|-------|--------------|--------------|
| 5 | 1x | 60 | <5% |
| 15 | 2x | 60 | <7% |
| 30 | 4x | 60 | <10% |

## Best Practices

✅ **DO**:
- Reset between tests
- Start with low vehicle count
- Use pause for inspection
- Monitor statistics
- Test at different speeds

❌ **DON'T**:
- Spawn too rapidly (wait for space)
- Set count > 30 (not supported)
- Expect instant spawn (needs 50m space)
- Run 4x speed for extended periods (stress test only)

## Common Workflows

**Quick Test**: Reset → Spawn pattern → Observe → Reset

**Stress Test**: Reset → Count 30 → Speed 4x → Run 5min

**Debug**: Reset → Count 0 → Manual spawn → Pause → Inspect

**Demo**: Reset → Count 10 → Speed 1x → Let run

---

**Full Documentation**: See `SIMULATION_CONTROLS.md`

**API Reference**: `http://localhost:8000/docs` (FastAPI auto-docs)
