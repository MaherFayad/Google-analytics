# pgBouncer Hybrid Pool Strategy

## Overview

This directory implements **Task P0-32: Hybrid pgBouncer Pool Strategy** to support both high-concurrency SSE streaming and long-running embedding transactions.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Application Layer                            │
│  ┌────────────────────────────┐  ┌─────────────────────────┐   │
│  │   SSE Endpoints (1000)     │  │  Embedding Workers (20) │   │
│  │  - Short transactions      │  │  - Long transactions    │   │
│  │  - High concurrency        │  │  - Session variables    │   │
│  └────────────────────────────┘  └─────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                    ↓                           ↓
┌─────────────────────────────────────────────────────────────────┐
│                   Connection Pooling Layer                       │
│  ┌────────────────────────────┐  ┌─────────────────────────┐   │
│  │ pgBouncer Transactional    │  │ pgBouncer Session       │   │
│  │ Port: 6432                 │  │ Port: 6433              │   │
│  │ Mode: transaction          │  │ Mode: session           │   │
│  │ Pool: 25 connections       │  │ Pool: 10 connections    │   │
│  └────────────────────────────┘  └─────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                    ↓                           ↓
┌─────────────────────────────────────────────────────────────────┐
│                      PostgreSQL Database                         │
│  Max Connections: 100                                            │
│  Actual Usage: 25 (transactional) + 10 (session) = 35           │
└─────────────────────────────────────────────────────────────────┘
```

## Why Hybrid Strategy?

### Problem

**Transaction Mode** (releases connection after each SQL statement):
- ✅ Great for SSE: 1000 clients → 25 DB connections (40x multiplexing)
- ❌ Breaks embedding workers: 10-30 second transactions get interrupted
- ❌ Session variables (RLS `SET app.tenant_id`) are lost

**Session Mode** (holds connection for entire session):
- ✅ Perfect for embedding workers: Long transactions complete successfully
- ✅ Session variables persist across queries
- ❌ No connection multiplexing: 1000 clients → 1000 DB connections (exhaustion!)

### Solution

**Use both modes simultaneously:**
- SSE endpoints → pgBouncer:6432 (transaction mode) → High concurrency
- Embedding workers → pgBouncer:6433 (session mode) → Long transactions

## Configuration Files

### 1. `pgbouncer_transactional.ini` (Port 6432)

**Purpose:** SSE streaming endpoints with high concurrency

**Key Settings:**
```ini
pool_mode = transaction       # Release connection after each SQL statement
max_client_conn = 1000       # Support 1000 concurrent SSE connections
default_pool_size = 25       # Only need 25 actual DB connections
```

**Use Cases:**
- SSE analytics streaming
- REST API endpoints
- Real-time notifications
- Quick database queries

**Connection Lifecycle:**
```
Client connects → Gets connection from pool
Query 1: SELECT ... → Connection returned to pool
Query 2: SELECT ... → Gets connection again (may be different)
Query 3: SELECT ... → Connection returned to pool
Client disconnects
```

### 2. `pgbouncer_session.ini` (Port 6433)

**Purpose:** Long-running embedding generation jobs

**Key Settings:**
```ini
pool_mode = session          # Hold connection for entire session
max_client_conn = 100        # Support up to 100 workers
default_pool_size = 10       # 10 dedicated connections
```

**Use Cases:**
- Embedding generation (10-30 seconds)
- Batch processing jobs
- Operations requiring session variables (`SET app.tenant_id`)
- Operations with temporary tables

**Connection Lifecycle:**
```
Worker connects → Gets dedicated connection
SET app.tenant_id = 'uuid'  → Session variable set
BEGIN transaction           → Long transaction starts
... 10-30 seconds of work ... → Connection held
COMMIT transaction          → Transaction completes
Worker disconnects          → Connection returns to pool
```

## Database Routing (Python)

The `database.py` file provides automatic routing:

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.server.database import get_session_transactional, get_session_long

# SSE endpoint (uses transactional pool)
@app.get("/analytics/stream")
async def stream(session: AsyncSession = Depends(get_session_transactional)):
    # Connection automatically routed to pgBouncer:6432
    result = await session.execute("SELECT ...")
    return result

# Embedding worker (uses session pool)
@app.post("/embeddings/generate")
async def generate(session: AsyncSession = Depends(get_session_long)):
    # Connection automatically routed to pgBouncer:6433
    await session.execute("SET app.tenant_id = '...'")
    # Session variable persists!
    result = await session.execute("INSERT INTO embeddings ...")
    return result
```

## Performance Characteristics

### Transactional Mode (Port 6432)

| Metric | Value | Notes |
|--------|-------|-------|
| Max concurrent clients | 1000 | SSE connections |
| DB connections used | 25 | Connection multiplexing |
| Multiplexing ratio | 40:1 | 1000 → 25 |
| Avg query duration | <100ms | Short queries |
| Connection reuse | High | Released after each query |

### Session Mode (Port 6433)

| Metric | Value | Notes |
|--------|-------|-------|
| Max concurrent clients | 100 | Embedding workers |
| DB connections used | 10 | 1:1 ratio per worker |
| Multiplexing ratio | 1:1 | No multiplexing |
| Avg transaction duration | 10-30s | Long transactions |
| Connection reuse | Low | Held for entire session |

## Docker Compose Setup

Both pgBouncer instances run as separate containers:

```yaml
services:
  pgbouncer-transactional:
    image: edoburu/pgbouncer:latest
    environment:
      POOL_MODE: transaction
      MAX_CLIENT_CONN: 1000
      DEFAULT_POOL_SIZE: 25
    ports:
      - "6432:5432"

  pgbouncer-session:
    image: edoburu/pgbouncer:latest
    environment:
      POOL_MODE: session
      MAX_CLIENT_CONN: 100
      DEFAULT_POOL_SIZE: 10
    ports:
      - "6433:5432"
```

## Monitoring

Connection pool stats available via API:

```bash
curl http://localhost:8000/health/db
```

Response:
```json
{
  "transactional": {
    "size": 25,
    "checked_out": 18,
    "utilization": 72.0
  },
  "session": {
    "size": 10,
    "checked_out": 3,
    "utilization": 30.0
  }
}
```

### Key Metrics to Monitor

1. **Utilization:** Should stay < 80% under normal load
2. **Overflow:** Indicates burst capacity being used
3. **Wait time:** High wait time indicates pool exhaustion

### Alerting Thresholds

- ⚠️ Warning: Utilization > 75%
- 🔥 Critical: Utilization > 90%
- 💀 Emergency: Overflow maxed out + wait time > 5s

## Troubleshooting

### Problem: Embedding jobs fail mid-transaction

**Symptoms:**
- Error: "connection closed unexpectedly"
- Partial data inserted
- Transaction rollback

**Cause:** Using transactional pgBouncer for long transactions

**Solution:**
```python
# Wrong - uses transactional pool
session: AsyncSession = Depends(get_session)

# Correct - uses session pool
session: AsyncSession = Depends(get_session_long)
```

### Problem: SSE connections causing connection exhaustion

**Symptoms:**
- Error: "connection pool exhausted"
- New SSE connections rejected
- High DB connection count

**Cause:** Using session pgBouncer for SSE endpoints

**Solution:**
```python
# Wrong - uses session pool (no multiplexing)
session: AsyncSession = Depends(get_session_long)

# Correct - uses transactional pool (40x multiplexing)
session: AsyncSession = Depends(get_session_transactional)
```

### Problem: RLS session variables not persisting

**Symptoms:**
- `app.tenant_id` is NULL in second query
- RLS policies not filtering data
- Cross-tenant data leakage

**Cause:** Using transactional mode (variables reset after each query)

**Solution:**
```python
# Use session mode for operations requiring session variables
async with get_session_long() as session:
    await session.execute("SET app.tenant_id = 'uuid'")
    # Variable persists for all subsequent queries
    result = await session.execute("SELECT ...")
```

## Load Testing

Test hybrid strategy under realistic load:

```bash
# Terminal 1: 1000 concurrent SSE connections (transactional)
for i in {1..1000}; do
  curl -N http://localhost:8000/analytics/stream &
done

# Terminal 2: 20 concurrent embedding jobs (session)
for i in {1..20}; do
  curl -X POST http://localhost:8000/embeddings/generate &
done

# Terminal 3: Monitor pool stats
watch -n 1 'curl -s http://localhost:8000/health/db | jq'
```

**Expected Results:**
- ✅ Transactional pool: 72% utilization (18/25 connections)
- ✅ Session pool: 30% utilization (3/10 connections)
- ✅ No connection timeout errors
- ✅ No connection pool exhaustion

## Best Practices

### When to Use Transactional Mode (Port 6432)

✅ Use for:
- SSE streaming endpoints
- REST API endpoints
- Read-only queries
- Quick writes (<100ms)
- High-concurrency operations

❌ Don't use for:
- Long transactions (>1 second)
- Operations requiring session variables
- Batch processing
- Temporary tables

### When to Use Session Mode (Port 6433)

✅ Use for:
- Embedding generation (10-30 seconds)
- Batch processing jobs
- Operations with `SET` session variables
- Operations with temporary tables
- Long-running reports

❌ Don't use for:
- SSE streaming (causes connection exhaustion)
- High-concurrency operations (no multiplexing)
- Quick queries (wastes dedicated connection)

## Related Documentation

- [Task P0-6: Database Connection Pooling](../docs/infrastructure/P0-06-connection-pooling.md)
- [Task P0-32: Hybrid Strategy](../docs/infrastructure/P0-32-hybrid-pgbouncer.md)
- [Task P0-13: Pool Monitoring](../docs/observability/P0-13-pool-monitoring.md)
- [database.py Implementation](../python/src/server/database.py)

## References

- [pgBouncer Documentation](https://www.pgbouncer.org/config.html)
- [pgBouncer Pool Modes](https://www.pgbouncer.org/features.html)
- [Connection Pooling Best Practices](https://wiki.postgresql.org/wiki/Number_Of_Database_Connections)

