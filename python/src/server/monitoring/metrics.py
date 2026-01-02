"""
Prometheus Metrics for pgBouncer Connection Pools

Implements Task P0-13: pgBouncer Connection Pool Health Monitoring

Exposes metrics for:
- Connection pool utilization
- Active/idle connections
- Waiting clients
- Pool overflow usage

Metrics are updated every 5 seconds and exported at /metrics endpoint.
"""

import logging
import asyncio
from typing import Optional

from prometheus_client import Gauge, Counter, Histogram, Info

from ..database import get_pool_stats

logger = logging.getLogger(__name__)


# ============================================================================
# Connection Pool Metrics
# ============================================================================

# Pool utilization (0.0 to 1.0)
connection_pool_utilization = Gauge(
    'connection_pool_utilization_ratio',
    'Connection pool utilization ratio (0.0 to 1.0)',
    ['pool_type']  # 'transactional' or 'session'
)

# Active connections (checked out from pool)
connection_pool_active = Gauge(
    'connection_pool_active_connections',
    'Number of active connections (checked out)',
    ['pool_type']
)

# Idle connections (available in pool)
connection_pool_idle = Gauge(
    'connection_pool_idle_connections',
    'Number of idle connections (available)',
    ['pool_type']
)

# Overflow connections (beyond pool_size)
connection_pool_overflow = Gauge(
    'connection_pool_overflow_connections',
    'Number of overflow connections in use',
    ['pool_type']
)

# Pool size configuration
connection_pool_size = Gauge(
    'connection_pool_size_total',
    'Total connection pool size (pool_size + max_overflow)',
    ['pool_type']
)

# Pool configuration info
connection_pool_info = Info(
    'connection_pool',
    'Connection pool configuration and metadata'
)


# ============================================================================
# Database Query Metrics
# ============================================================================

# Query execution time
database_query_duration_seconds = Histogram(
    'database_query_duration_seconds',
    'Database query execution time in seconds',
    ['operation', 'pool_type'],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

# Total queries executed
database_queries_total = Counter(
    'database_queries_total',
    'Total number of database queries executed',
    ['operation', 'pool_type', 'status']  # status: 'success' or 'error'
)

# Database errors
database_errors_total = Counter(
    'database_errors_total',
    'Total number of database errors',
    ['error_type', 'pool_type']
)


# ============================================================================
# Metrics Collection Task
# ============================================================================

_metrics_task: Optional[asyncio.Task] = None


async def update_pool_metrics() -> None:
    """
    Update Prometheus metrics with current pool statistics.
    
    Called periodically by the metrics collector task.
    """
    try:
        stats = await get_pool_stats()
        
        # Update transactional pool metrics
        trans_stats = stats["transactional"]
        connection_pool_utilization.labels(pool_type="transactional").set(
            trans_stats["utilization"] / 100  # Convert percentage to ratio
        )
        connection_pool_active.labels(pool_type="transactional").set(
            trans_stats["checked_out"]
        )
        connection_pool_idle.labels(pool_type="transactional").set(
            trans_stats["checked_in"]
        )
        connection_pool_overflow.labels(pool_type="transactional").set(
            trans_stats.get("overflow", 0)
        )
        connection_pool_size.labels(pool_type="transactional").set(
            trans_stats["pool_size"] + trans_stats.get("max_overflow", 0)
        )
        
        # Update session pool metrics
        session_stats = stats["session"]
        connection_pool_utilization.labels(pool_type="session").set(
            session_stats["utilization"] / 100  # Convert percentage to ratio
        )
        connection_pool_active.labels(pool_type="session").set(
            session_stats["checked_out"]
        )
        connection_pool_idle.labels(pool_type="session").set(
            session_stats["checked_in"]
        )
        connection_pool_overflow.labels(pool_type="session").set(
            session_stats.get("overflow", 0)
        )
        connection_pool_size.labels(pool_type="session").set(
            session_stats["pool_size"] + session_stats.get("max_overflow", 0)
        )
        
        # Update pool info (configuration metadata)
        connection_pool_info.info({
            'transactional_pool_size': str(trans_stats["pool_size"]),
            'transactional_max_overflow': str(trans_stats.get("max_overflow", 0)),
            'session_pool_size': str(session_stats["pool_size"]),
            'session_max_overflow': str(session_stats.get("max_overflow", 0)),
            'pgbouncer_transactional_port': '6432',
            'pgbouncer_session_port': '6433',
        })
        
    except Exception as e:
        logger.error(f"Error updating pool metrics: {e}", exc_info=True)


async def metrics_collector_task() -> None:
    """
    Background task that periodically updates Prometheus metrics.
    
    Runs every 5 seconds to keep metrics fresh.
    """
    logger.info("Starting metrics collector task (5s interval)")
    
    while True:
        try:
            await update_pool_metrics()
            await asyncio.sleep(5)  # Update every 5 seconds
        except asyncio.CancelledError:
            logger.info("Metrics collector task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in metrics collector task: {e}", exc_info=True)
            await asyncio.sleep(5)  # Continue despite errors


def start_metrics_collector() -> asyncio.Task:
    """
    Start the background metrics collector task.
    
    Should be called at application startup.
    
    Returns:
        asyncio.Task: The running collector task
        
    Usage:
        @app.on_event("startup")
        async def startup():
            start_metrics_collector()
    """
    global _metrics_task
    
    if _metrics_task is not None:
        logger.warning("Metrics collector already running")
        return _metrics_task
    
    _metrics_task = asyncio.create_task(metrics_collector_task())
    logger.info("Metrics collector task started")
    
    return _metrics_task


async def stop_metrics_collector() -> None:
    """
    Stop the background metrics collector task.
    
    Should be called at application shutdown.
    
    Usage:
        @app.on_event("shutdown")
        async def shutdown():
            await stop_metrics_collector()
    """
    global _metrics_task
    
    if _metrics_task is None:
        return
    
    _metrics_task.cancel()
    
    try:
        await _metrics_task
    except asyncio.CancelledError:
        pass
    
    _metrics_task = None
    logger.info("Metrics collector task stopped")


# ============================================================================
# Metric Helper Functions
# ============================================================================

def track_query(operation: str, pool_type: str = "transactional"):
    """
    Context manager to track database query metrics.
    
    Usage:
        with track_query("fetch_analytics", pool_type="transactional"):
            result = await session.execute(query)
    """
    return database_query_duration_seconds.labels(
        operation=operation,
        pool_type=pool_type
    ).time()


def record_query_success(operation: str, pool_type: str = "transactional"):
    """Record successful query execution."""
    database_queries_total.labels(
        operation=operation,
        pool_type=pool_type,
        status="success"
    ).inc()


def record_query_error(operation: str, pool_type: str = "transactional"):
    """Record failed query execution."""
    database_queries_total.labels(
        operation=operation,
        pool_type=pool_type,
        status="error"
    ).inc()


def record_database_error(error_type: str, pool_type: str = "transactional"):
    """Record database error."""
    database_errors_total.labels(
        error_type=error_type,
        pool_type=pool_type
    ).inc()


# ============================================================================
# Export metrics for FastAPI /metrics endpoint
# ============================================================================

connection_pool_metrics = {
    "utilization": connection_pool_utilization,
    "active": connection_pool_active,
    "idle": connection_pool_idle,
    "overflow": connection_pool_overflow,
    "size": connection_pool_size,
    "info": connection_pool_info,
}

