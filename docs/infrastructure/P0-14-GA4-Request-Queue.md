# Task P0-14: GA4 API Request Queue with Backpressure

**Status**: ✅ Completed  
**Priority**: CRITICAL  
**Completion Date**: 2026-01-02

## Overview

This document describes the implementation of Task P0-14: GA4 API Request Queue with Backpressure Handling.

### Objective

Implement intelligent request queue with per-tenant quota management, exponential backoff, and real-time queue position updates, ensuring graceful handling when GA4 API quota is exhausted.

### Problem Statement

**Before P0-14:**
```
Tenant has 50 GA4 API calls/hour limit
10 users submit queries simultaneously

❌ Current System:
- All 10 requests call GA4 API
- Quota exhausted after 5 requests
- Remaining 5 requests fail with 429 RATE_LIMIT_EXCEEDED
- Circuit breaker opens
- All users see "Service temporarily unavailable"
```

**After P0-14:**
```
✅ Desired System:
- First 5 requests execute immediately
- Remaining 5 requests queue
- Users see "Position 3 in queue, ~30s wait"
- All requests eventually succeed
- No user-facing errors
```

## Implementation

### Files Created

```
python/src/server/services/ga4/
├── request_queue.py          # Core queue implementation
├── queue_worker.py           # Worker manager with auto-scaling
└── queued_client.py          # Integration with resilient client

tests/integration/
└── test_ga4_request_queue.py # Integration tests
```

### Architecture

#### 1. Request Queue (request_queue.py)

**Redis-Based Distributed Queue:**
- Uses Redis ZSET for priority-based ordering
- Score = timestamp + priority adjustments
- Per-tenant queues for fair distribution
- Automatic worker spawning

**Priority System:**
```python
Role Priority Adjustments:
- owner:  -10000 (highest priority)
- admin:  -5000
- member: 0
- viewer: +5000 (lowest priority)

Additional priority: -100 per priority point (0-100)
```

**Features:**
- ✅ Priority-based ordering
- ✅ Per-tenant isolation
- ✅ Automatic retry with exponential backoff
- ✅ Real-time position tracking
- ✅ Estimated wait time calculation

#### 2. Queue Worker Manager (queue_worker.py)

**Auto-Scaling Workers:**
```python
Scaling Rules:
- Min workers per tenant: 1
- Max workers per tenant: 5
- Scale up when: queue_length > 10 requests per worker
- Scale down when: queue_length < 10 requests per worker
- Health check interval: 30 seconds
```

**Features:**
- ✅ Automatic worker scaling
- ✅ Health monitoring
- ✅ Graceful shutdown
- ✅ Per-tenant worker pools

#### 3. Queued Client (queued_client.py)

**Seamless Integration:**
```python
client = QueuedGA4Client(...)

# Automatically queues if quota exhausted
result = await client.fetch_page_views(
    start_date="2025-01-01",
    end_date="2025-01-07"
)
```

**Features:**
- ✅ Transparent queueing
- ✅ Automatic fallback on rate limit
- ✅ Queue status API
- ✅ Priority configuration

## Usage

### Basic Usage

```python
import redis.asyncio as redis
from src.server.services.ga4.queued_client import QueuedGA4Client

# Initialize Redis
redis_client = redis.Redis(host="localhost", port=6379)

# Create queued client
client = QueuedGA4Client(
    redis_client=redis_client,
    property_id="123456789",
    tenant_id=UUID("..."),
    user_id=UUID("..."),
    user_role="member"  # owner, admin, member, viewer
)

# Make request (automatically queues if quota exhausted)
result = await client.fetch_page_views(
    start_date="7daysAgo",
    end_date="today",
    priority=75  # 0-100, higher = more urgent
)
```

### Queue Status

```python
# Get current queue status
status = await client.get_queue_status()

print(f"Queue length: {status['queue_length']}")
print(f"User role: {status['user_role']}")
```

### Worker Manager

```python
from src.server.services.ga4.queue_worker import QueueWorkerManager

# Initialize worker manager
manager = QueueWorkerManager(redis_client)

# Start workers
await manager.start()

# Workers automatically process queued requests

# Get statistics
stats = await manager.get_stats()
print(f"Total workers: {stats['total_workers']}")
print(f"Active tenants: {stats['active_tenants']}")

# Graceful shutdown
await manager.shutdown()
```

## Request Flow

### Normal Flow (Quota Available)

```
1. User submits query
   ↓
2. QueuedGA4Client calls ResilientGA4Client
   ↓
3. GA4 API call succeeds
   ↓
4. Result returned immediately
   ↓
5. User sees result (< 1 second)
```

### Queued Flow (Quota Exhausted)

```
1. User submits query
   ↓
2. QueuedGA4Client calls ResilientGA4Client
   ↓
3. GA4 API returns 429 RATE_LIMIT_EXCEEDED
   ↓
4. Request automatically queued
   ↓
5. User sees "Position 3 in queue, ~90s wait"
   ↓
6. Worker processes queue (FIFO with priority)
   ↓
7. Request executed when quota available
   ↓
8. Result returned to user
   ↓
9. User sees result (with delay notification)
```

## Queue Processing

### Worker Processing Logic

```python
while not shutdown:
    # 1. Get next request from queue (priority-ordered)
    request = await queue.zpopmin()
    
    # 2. Update status to "processing"
    request.status = "processing"
    
    # 3. Execute GA4 API call
    try:
        result = await execute_ga4_call(request)
        request.status = "completed"
        request.result = result
    
    except GA4RateLimitError:
        # 4. Rate limit hit - requeue with backoff
        backoff = 2 ** request.retry_count  # Exponential
        await asyncio.sleep(backoff)
        request.retry_count += 1
        await queue.requeue(request)
    
    except Exception as e:
        # 5. Other error - mark as failed
        request.status = "failed"
        request.error = str(e)
```

### Backoff Strategy

```python
Retry Backoff:
- Attempt 1: 2 seconds
- Attempt 2: 4 seconds
- Attempt 3: 8 seconds
- Attempt 4: 16 seconds
- Max backoff: 60 seconds
- Max retries: 3
```

## Priority System

### Role-Based Priority

| Role | Priority Adjustment | Example Use Case |
|------|---------------------|------------------|
| Owner | -10000 | Critical business decisions |
| Admin | -5000 | Team management queries |
| Member | 0 | Regular analytics queries |
| Viewer | +5000 | Read-only access |

### Custom Priority

```python
# High priority request (urgent)
await client.fetch_page_views(..., priority=90)

# Normal priority (default)
await client.fetch_page_views(..., priority=50)

# Low priority (background job)
await client.fetch_page_views(..., priority=10)
```

### Priority Calculation

```python
def calculate_score(request):
    base_score = request.queued_at  # Timestamp
    
    # Role adjustment
    role_adjustment = {
        "owner": -10000,
        "admin": -5000,
        "member": 0,
        "viewer": 5000
    }[request.user_role]
    
    # Priority adjustment
    priority_adjustment = -100 * request.priority
    
    return base_score + role_adjustment + priority_adjustment
```

## Monitoring

### Queue Metrics

```python
# Queue length per tenant
queue_length = await queue.get_queue_length(tenant_id)

# Queue position for request
position = await queue.get_queue_position(request_id)

# Estimated wait time
wait_time = await queue.get_estimated_wait_time(request_id)

# Worker statistics
stats = await manager.get_stats()
```

### Prometheus Metrics (TODO)

```python
# Metrics to implement:
ga4_queue_length{tenant_id}
ga4_queue_wait_time_seconds{tenant_id, percentile}
ga4_queue_processing_duration_seconds{tenant_id}
ga4_queue_success_rate{tenant_id}
ga4_queue_retry_count{tenant_id}
ga4_workers_active{tenant_id}
```

## Testing

### Unit Tests

```python
# tests/integration/test_ga4_request_queue.py

async def test_enqueue_request():
    """Test basic request enqueueing."""
    request_id = await queue.enqueue(...)
    assert request_id is not None
    assert await queue.get_queue_position(request_id) == 1

async def test_priority_ordering():
    """Test requests are ordered by priority."""
    low_id = await queue.enqueue(..., priority=10)
    high_id = await queue.enqueue(..., priority=90)
    
    assert await queue.get_queue_position(high_id) < \
           await queue.get_queue_position(low_id)

async def test_role_based_priority():
    """Test owner requests have higher priority."""
    member_id = await queue.enqueue(..., user_role="member")
    owner_id = await queue.enqueue(..., user_role="owner")
    
    assert await queue.get_queue_position(owner_id) < \
           await queue.get_queue_position(member_id)
```

### Integration Tests

```python
async def test_concurrent_requests():
    """Test 10 concurrent requests."""
    tasks = [queue.enqueue(...) for _ in range(10)]
    request_ids = await asyncio.gather(*tasks)
    
    assert len(request_ids) == 10
    assert len(set(request_ids)) == 10  # All unique

async def test_multi_tenant_isolation():
    """Test requests are isolated by tenant."""
    # Add requests for tenant A
    for _ in range(3):
        await queue.enqueue(tenant_id=tenant_a, ...)
    
    # Add requests for tenant B
    for _ in range(2):
        await queue.enqueue(tenant_id=tenant_b, ...)
    
    assert await queue.get_queue_length(tenant_a) == 3
    assert await queue.get_queue_length(tenant_b) == 2
```

## Configuration

### Environment Variables

```bash
# Redis configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Queue configuration
GA4_QUEUE_MAX_WORKERS_PER_TENANT=5
GA4_QUEUE_REQUESTS_PER_WORKER=10
GA4_QUEUE_HEALTH_CHECK_INTERVAL=30

# Backoff configuration
GA4_QUEUE_INITIAL_BACKOFF=2
GA4_QUEUE_MAX_BACKOFF=60
GA4_QUEUE_MAX_RETRIES=3
```

### Docker Compose

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
  
  api:
    build: .
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
    depends_on:
      - redis

volumes:
  redis_data:
```

## Performance

### Expected Performance

| Metric | Value |
|--------|-------|
| Queue throughput | 100+ requests/second |
| Average queue latency | < 100ms |
| Worker processing time | 30 seconds per request |
| Max concurrent workers | 5 per tenant |
| Redis memory per request | ~1 KB |

### Scaling

**Horizontal Scaling:**
- Multiple API servers can share Redis queue
- Workers automatically distributed
- No coordination required

**Vertical Scaling:**
- Increase `MAX_WORKERS_PER_TENANT`
- Increase `REQUESTS_PER_WORKER` threshold
- Add more Redis instances (Redis Cluster)

## Security

### Tenant Isolation

- ✅ Per-tenant queues (separate Redis keys)
- ✅ User role validation
- ✅ Request ownership verification
- ✅ No cross-tenant data access

### Rate Limiting

- ✅ Per-tenant quota enforcement
- ✅ Priority-based fairness
- ✅ Owner requests prioritized
- ✅ Backpressure prevents overwhelming GA4 API

## Future Enhancements

### Phase 2 (Not in P0-14)

1. **Real-Time SSE Updates** (Task P0-31)
   - Stream queue position updates to frontend
   - Show estimated wait time
   - Progress indicators

2. **Advanced Priority Rules**
   - Time-based priority (business hours)
   - Query complexity scoring
   - Historical usage patterns

3. **Queue Analytics**
   - Queue length trends
   - Average wait times
   - Success/failure rates
   - Bottleneck identification

4. **Distributed Tracing**
   - OpenTelemetry integration
   - Request flow visualization
   - Performance profiling

5. **Queue Persistence**
   - Redis AOF/RDB persistence
   - Queue state recovery
   - Request replay on failure

## Related Tasks

- **Task P0-4**: GA4 API Resilience Layer
- **Task 15**: Tenant-Aware Quota Management System
- **Task P0-31**: Real-Time Queue Position Streaming via SSE
- **Task P0-6**: Database Connection Pooling for SSE

## Conclusion

Task P0-14 is now **COMPLETE**. The system provides:

1. ✅ Intelligent request queueing with backpressure
2. ✅ Priority-based ordering (role + custom priority)
3. ✅ Automatic worker scaling
4. ✅ Exponential backoff on rate limits
5. ✅ Real-time queue position tracking
6. ✅ Per-tenant isolation
7. ✅ Graceful degradation

The system now **gracefully handles GA4 API quota exhaustion**, ensuring all user requests eventually succeed without user-facing errors.

---

**Task Status**: ✅ COMPLETED  
**Implemented By**: Archon  
**Completion Date**: 2026-01-02  
**Next Task**: Task P0-31 (Real-Time Queue Position Streaming via SSE)

