# Graceful SSE Connection Shutdown

**Implements:** Task P0-20: Graceful SSE Connection Shutdown [MEDIUM]

## Overview

This feature ensures zero-downtime deployments by gracefully handling active SSE (Server-Sent Events) connections during server restarts, particularly in Kubernetes rolling deployments.

## Problem Solved

### Before (Pain Point)
```
Production Deployment:
1. kubectl rollout restart deployment/api-server
2. SIGTERM sent to pod
3. 1000 active SSE connections streaming reports
4. Pod has 30 seconds to shut down

Current System:
- All 1000 connections dropped immediately ❌
- Users see "Connection lost" error
- Reports in progress lost
- Poor user experience during deployments
```

### After (Solution)
```
Desired System:
- New connections rejected with 503 Service Unavailable ✅
- Existing connections: Send final SSE message "Server restarting, reconnect in 30s"
- Wait up to 20 seconds for in-flight requests to complete
- Frontend automatically reconnects
- Zero-downtime deployments achieved
```

## Architecture

### Components

1. **SSEConnectionManager** (`python/src/server/core/connection_manager.py`)
   - Tracks active SSE connections
   - Coordinates graceful shutdown
   - Notifies clients before restart
   - Enforces grace period

2. **Signal Handlers** (`python/src/server/main.py`)
   - Listens for SIGTERM/SIGINT signals
   - Triggers graceful shutdown process
   - Integrated with FastAPI lifespan

3. **SSE Endpoint** (`python/src/server/api/v1/analytics.py`)
   - Registers connections with manager
   - Checks for shutdown events during streaming
   - Rejects new connections during shutdown

### Connection Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│  NORMAL OPERATION                                            │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Client Request → Check if shutting down                     │
│       ↓ (No)                                                  │
│  Register connection (generates unique ID)                   │
│       ↓                                                       │
│  Create event queue for this connection                      │
│       ↓                                                       │
│  Stream SSE events (status, result, complete)                │
│       ↓                                                       │
│  Unregister connection on completion                         │
│                                                               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  SHUTDOWN SEQUENCE                                           │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  SIGTERM/SIGINT received                                     │
│       ↓                                                       │
│  Mark as shutting down (reject new connections)             │
│       ↓                                                       │
│  Send shutdown event to all active connections              │
│       ↓                                                       │
│  Wait up to 20 seconds for connections to close             │
│       │                                                       │
│       ├─ Connections close gracefully → Success ✅          │
│       │                                                       │
│       └─ Grace period expires → Force close remaining ⚠️    │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Configuration

### Environment Variables

```bash
# Grace period for SSE connection shutdown (seconds)
SHUTDOWN_GRACE_PERIOD=20
```

**Default:** 20 seconds

**Considerations:**
- Kubernetes default termination grace period: 30 seconds
- Recommended: Set SHUTDOWN_GRACE_PERIOD < Kubernetes terminationGracePeriodSeconds
- Example: If Kubernetes terminationGracePeriodSeconds=30, use SHUTDOWN_GRACE_PERIOD=20

## SSE Event Format

### Shutdown Event

When server begins shutdown, all active connections receive:

```
event: shutdown
data: {"type":"shutdown","message":"Server restarting, please reconnect in 30s","timestamp":"2025-01-02T13:00:00.000Z","reconnect_delay":30}
```

**Fields:**
- `type`: Always "shutdown"
- `message`: Human-readable shutdown message
- `timestamp`: ISO 8601 timestamp
- `reconnect_delay`: Suggested delay before reconnecting (seconds)

### Client Handling

Frontend should handle shutdown events:

```typescript
const eventSource = new EventSource('/api/v1/analytics/stream');

eventSource.addEventListener('shutdown', (event) => {
  const data = JSON.parse(event.data);
  
  // Notify user
  console.log(data.message); // "Server restarting, please reconnect in 30s"
  
  // Close connection
  eventSource.close();
  
  // Auto-reconnect after delay
  setTimeout(() => {
    reconnect();
  }, data.reconnect_delay * 1000);
});
```

## Deployment

### Kubernetes Configuration

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ga4-analytics-api
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 30  # Must be > SHUTDOWN_GRACE_PERIOD
      containers:
      - name: api
        env:
        - name: SHUTDOWN_GRACE_PERIOD
          value: "20"
```

### Rolling Update Strategy

```yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0  # Zero-downtime
```

## Monitoring

### Metrics

Track these metrics to monitor graceful shutdown:

```python
# Active SSE connections
sse_active_connections{pod="ga4-api-xyz"} 45

# Shutdown duration
sse_shutdown_duration_seconds{pod="ga4-api-xyz"} 12.5

# Force closed connections (should be 0 in ideal case)
sse_force_closed_connections_total{pod="ga4-api-xyz"} 0
```

### Logs

Shutdown process logs:

```
INFO  - Received SIGTERM signal, initiating graceful shutdown...
INFO  - Active SSE connections: 45
INFO  - Notifying 45 active connections of shutdown
INFO  - Waiting for 45 connections to close (0.5s elapsed)
INFO  - Waiting for 12 connections to close (5.2s elapsed)
INFO  - Graceful shutdown complete
```

## Testing

### Unit Tests

```bash
pytest tests/integration/test_graceful_shutdown.py -v
```

### Load Test

Simulate production deployment with 1000 concurrent connections:

```bash
python tests/load/test_graceful_shutdown_load.py
```

**Success Criteria:**
- 100% of connections receive shutdown notification
- 95%+ connections close within grace period
- 0% connections dropped without notification
- < 5% connections force closed

## Troubleshooting

### Issue: Connections force closed after grace period

**Symptom:** Logs show "Force closing N remaining connections"

**Causes:**
1. Frontend not handling shutdown events
2. Long-running queries exceed grace period
3. Network latency delays closure

**Solutions:**
- Implement frontend shutdown handler
- Increase SHUTDOWN_GRACE_PERIOD (if Kubernetes allows)
- Optimize query execution time

### Issue: New connections accepted during shutdown

**Symptom:** Connections registered after SIGTERM received

**Causes:**
1. Race condition in shutdown check
2. Connection manager not initialized

**Solutions:**
- Verify connection manager initialized in lifespan
- Check shutdown flag before registration
- Add integration test

## Future Enhancements

1. **Task P0-34:** Auto-reconnect with exponential backoff
2. **Task P0-31:** Real-time queue position streaming
3. Progressive shutdown (drain connections gradually)
4. Connection priority (VIP users drain last)

## References

- Task P0-20: Graceful SSE Connection Shutdown
- FastAPI Lifespan Events: https://fastapi.tiangolo.com/advanced/events/
- Kubernetes Termination: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination

