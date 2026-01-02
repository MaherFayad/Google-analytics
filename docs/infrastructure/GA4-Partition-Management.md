# GA4 Analytics Events Partition Management

## Overview

The GA4 Analytics Events schema uses PostgreSQL table partitioning to handle large volumes of time-series event data efficiently. This document describes the partitioning strategy, maintenance procedures, and Python utilities for managing partitions.

## Architecture

### Table Structure

```
archon_ga4_events (Parent Table)
├── archon_ga4_events_2026_01 (Partition: Jan 2026)
├── archon_ga4_events_2026_02 (Partition: Feb 2026)
├── archon_ga4_events_2026_03 (Partition: Mar 2026)
└── ... (one partition per month)
```

### Partitioning Strategy

- **Partition Key**: `event_timestamp` (TIMESTAMPTZ)
- **Partition Interval**: Monthly (first day of month to first day of next month)
- **Retention Policy**: 24 months (configurable)
- **Future Planning**: 3 months ahead (configurable)

### Why Partitioning?

1. **Query Performance**: Date-range queries scan only relevant partitions
2. **Maintenance Efficiency**: Drop old data by removing partitions (instant vs. DELETE)
3. **Index Size**: Smaller per-partition indexes improve search speed
4. **Storage Management**: Easy to move old partitions to archive storage
5. **Parallel Operations**: PostgreSQL can scan partitions in parallel

## Schema Design

### Main Events Table

```sql
CREATE TABLE archon_ga4_events (
    id BIGSERIAL,
    tenant_id UUID NOT NULL,
    property_id TEXT NOT NULL,
    event_name TEXT NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL,
    page_path TEXT,
    page_title TEXT,
    user_pseudo_id TEXT,
    session_id TEXT,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    dimensions JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding_768 VECTOR(768),  -- pgvector for semantic search
    embedding_model TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (id, event_timestamp)
) PARTITION BY RANGE (event_timestamp);
```

### Daily Summaries Table

Pre-aggregated metrics for fast dashboard loads:

```sql
CREATE TABLE archon_ga4_daily_summaries (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    property_id TEXT NOT NULL,
    date DATE NOT NULL,
    total_sessions INT,
    total_page_views INT,
    unique_users INT,
    avg_session_duration_seconds FLOAT,
    bounce_rate FLOAT,
    conversion_rate FLOAT,
    total_conversions INT,
    top_pages JSONB,
    top_sources JSONB,
    device_breakdown JSONB,
    UNIQUE(tenant_id, property_id, date)
);
```

## Indexes

### Parent Table Indexes

Applied to all partitions automatically:

```sql
-- Tenant + time filtering (most common query pattern)
CREATE INDEX idx_ga4_events_tenant_time 
ON archon_ga4_events(tenant_id, event_timestamp DESC);

-- Property filtering
CREATE INDEX idx_ga4_events_property 
ON archon_ga4_events(property_id, event_timestamp DESC);

-- Event name filtering
CREATE INDEX idx_ga4_events_name 
ON archon_ga4_events(event_name, event_timestamp DESC);

-- JSONB indexes for metrics and dimensions
CREATE INDEX idx_ga4_events_metrics 
ON archon_ga4_events USING GIN (metrics jsonb_path_ops);

CREATE INDEX idx_ga4_events_dimensions 
ON archon_ga4_events USING GIN (dimensions jsonb_path_ops);
```

### Per-Partition Vector Indexes

Each partition gets its own pgvector index:

```sql
CREATE INDEX idx_ga4_events_2026_01_embedding 
ON archon_ga4_events_2026_01 
USING ivfflat (embedding_768 vector_cosine_ops) WITH (lists = 100);
```

**Note**: Vector indexes must be created per partition because pgvector doesn't support partitioned tables directly.

## Tenant Isolation (RLS)

Row Level Security ensures data isolation:

```sql
ALTER TABLE archon_ga4_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Tenant isolation for GA4 events"
  ON archon_ga4_events FOR ALL
  USING (tenant_id = (current_setting('app.current_tenant_id', true))::uuid);
```

**Query Pattern**:
```sql
-- Set tenant context before query
SET app.current_tenant_id = 'your-tenant-uuid';

-- All queries automatically filtered by tenant_id
SELECT * FROM archon_ga4_events 
WHERE event_timestamp > '2026-01-01';
```

## Maintenance Functions

### 1. Create Partition

```sql
-- Create partition for May 2026
SELECT create_ga4_events_partition('2026-05-01'::DATE);
```

### 2. Ensure Future Partitions Exist

```sql
-- Create partitions for current + next 3 months
SELECT * FROM ensure_ga4_partitions_exist(3);
```

Output:
```
partition_name              | status
----------------------------+--------------------------------------------------
archon_ga4_events_2026_01   | Partition archon_ga4_events_2026_01 already exists
archon_ga4_events_2026_02   | Successfully created partition archon_ga4_events_2026_02...
```

### 3. Drop Old Partitions

```sql
-- Drop partitions older than 24 months
SELECT * FROM drop_old_ga4_partitions(24);
```

### 4. Get Partition Statistics

```sql
SELECT * FROM get_ga4_partition_stats();
```

Output:
```
partition_name              | row_count | size_bytes | size_pretty | date_range_start | date_range_end
----------------------------+-----------+------------+-------------+------------------+----------------
archon_ga4_events_2026_01   | 1234567   | 524288000  | 500 MB      | 2026-01-01       | 2026-02-01
archon_ga4_events_2026_02   | 987654    | 419430400  | 400 MB      | 2026-02-01       | 2026-03-01
```

## Python API

### Basic Usage

```python
from sqlalchemy.ext.asyncio import AsyncSession
from server.services.ga4.partition_manager import GA4PartitionManager

# Initialize manager
manager = GA4PartitionManager(db_session)

# Create partition for specific date
result = await manager.create_partition(datetime(2026, 5, 1))
print(result)
# Output: "Successfully created partition archon_ga4_events_2026_05..."

# Ensure future partitions exist
partitions = await manager.ensure_partitions_exist(months_ahead=3)
for p in partitions:
    print(f"{p['partition_name']}: {p['status']}")

# Get partition statistics
stats = await manager.get_partition_stats()
for partition in stats:
    print(f"{partition.name}: {partition.row_count} rows, {partition.size_pretty}")

# Drop old partitions
dropped = await manager.drop_old_partitions(retention_months=24)
for p in dropped:
    print(f"Dropped: {p['partition_name']}")
```

### Scheduled Maintenance

Run this monthly via APScheduler or cron:

```python
from server.services.ga4.partition_manager import run_partition_maintenance

# Run full maintenance routine
results = await run_partition_maintenance(db_session)

print(f"Created: {len(results['created_partitions'])} partitions")
print(f"Dropped: {len(results['dropped_partitions'])} partitions")
print(f"Total events: {results['total_events_count']}")
```

### Integration with APScheduler

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from server.services.ga4.partition_manager import run_partition_maintenance

scheduler = AsyncIOScheduler()

# Run partition maintenance on 1st of every month at 2 AM
@scheduler.scheduled_job('cron', day=1, hour=2, minute=0)
async def scheduled_partition_maintenance():
    async with get_db_session() as session:
        results = await run_partition_maintenance(session)
        logger.info(f"Partition maintenance completed: {results}")

scheduler.start()
```

## Performance Considerations

### Query Optimization

**Good** - Partition pruning works:
```sql
-- Only scans January 2026 partition
SELECT * FROM archon_ga4_events 
WHERE event_timestamp BETWEEN '2026-01-01' AND '2026-01-31'
AND tenant_id = 'uuid';
```

**Bad** - Full table scan:
```sql
-- Scans ALL partitions (event_timestamp not filtered)
SELECT * FROM archon_ga4_events 
WHERE page_path = '/home';
```

### Index Usage

1. **Always filter by `tenant_id`** - Enables RLS and uses composite index
2. **Include `event_timestamp` range** - Enables partition pruning
3. **Use JSONB operators efficiently**:
   ```sql
   -- Fast: Uses GIN index
   WHERE metrics @> '{"sessions": 100}'
   
   -- Slow: No index
   WHERE metrics->>'sessions' = '100'
   ```

### Vector Search Optimization

Vector indexes are per-partition, so:

```sql
-- Good: Searches within specific partition
SELECT * FROM archon_ga4_events 
WHERE tenant_id = 'uuid'
AND event_timestamp BETWEEN '2026-01-01' AND '2026-01-31'
ORDER BY embedding_768 <=> '[0.1, 0.2, ...]' LIMIT 10;

-- Slower: Searches across all partitions
SELECT * FROM archon_ga4_events 
WHERE tenant_id = 'uuid'
ORDER BY embedding_768 <=> '[0.1, 0.2, ...]' LIMIT 10;
```

## Migration Procedure

### Initial Setup

1. Run schema migration:
   ```bash
   psql -U postgres -d your_database -f migrations/ga4_analytics_schema.sql
   ```

2. Run partition maintenance setup:
   ```bash
   psql -U postgres -d your_database -f migrations/ga4_partition_maintenance.sql
   ```

3. Verify partitions were created:
   ```sql
   SELECT * FROM get_ga4_partition_stats();
   ```

### Production Deployment

1. **Pre-deployment**: Create partitions for next month:
   ```sql
   SELECT ensure_ga4_partitions_exist(3);
   ```

2. **Deploy application code** with partition manager

3. **Set up cron job** for monthly maintenance:
   ```bash
   # /etc/cron.d/ga4-partition-maintenance
   0 2 1 * * psql -U postgres -d prod_db -c "SELECT * FROM ensure_ga4_partitions_exist(3);"
   ```

## Troubleshooting

### Partition Not Found Error

**Error**: `no partition of relation "archon_ga4_events" found for row`

**Solution**: Create missing partition:
```python
manager = GA4PartitionManager(db_session)
await manager.ensure_partitions_exist(months_ahead=6)
```

### Slow Vector Searches

**Symptom**: pgvector queries taking >1 second

**Diagnosis**:
```sql
-- Check if vector index exists on partition
\d archon_ga4_events_2026_01
```

**Solution**: Create missing vector index:
```sql
CREATE INDEX idx_ga4_events_2026_01_embedding 
ON archon_ga4_events_2026_01 
USING ivfflat (embedding_768 vector_cosine_ops) WITH (lists = 100);
```

### Disk Space Issues

**Symptom**: Partition sizes growing too large

**Solution**:
1. Check partition sizes:
   ```python
   stats = await manager.get_partition_stats()
   for p in stats:
       print(f"{p.name}: {p.size_pretty}")
   ```

2. Adjust retention policy:
   ```python
   # Drop partitions older than 12 months
   await manager.drop_old_partitions(retention_months=12)
   ```

3. Consider archiving to S3/cold storage before dropping

## Monitoring

### Key Metrics

1. **Partition Count**: Should be ~24-27 (24 months + 3 future)
2. **Per-Partition Size**: Target <1GB per partition for optimal performance
3. **Query Time**: P95 latency <100ms for date-range queries
4. **Index Size**: Vector indexes should be ~10-15% of partition size

### Alerting Thresholds

- **Alert** if partition count > 30 (possible maintenance failure)
- **Alert** if any partition > 2GB (consider more granular partitioning)
- **Alert** if query P95 > 500ms (index or partition issue)
- **Warn** if no future partitions exist (maintenance not running)

## References

- [PostgreSQL Table Partitioning Docs](https://www.postgresql.org/docs/current/ddl-partitioning.html)
- [pgvector Index Types](https://github.com/pgvector/pgvector#indexing)
- Task 18 (original implementation task)
- Task 11 (tenant isolation strategy)

