"""
Prometheus Metrics for Comprehensive System Monitoring

Implements:
- Task P0-13: pgBouncer Connection Pool Health Monitoring
- Task P0-7: Monitoring & Alerting Infrastructure

Exposes metrics for:
- Connection pool utilization
- GA4 API health and quota
- Vector search performance
- SSE connection tracking
- HTTP request metrics
- System health

Metrics are updated periodically and exported at /metrics endpoint.
"""

import logging
import asyncio
import time
from typing import Optional, Dict, Any
from functools import wraps

from prometheus_client import Gauge, Counter, Histogram, Info, Summary

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
# GA4 API Metrics
# ============================================================================

# GA4 API call counter
ga4_api_calls_total = Counter(
    'ga4_api_calls_total',
    'Total number of GA4 API calls',
    ['tenant_id', 'endpoint', 'status']  # status: 'success', 'error', 'rate_limited'
)

# GA4 API latency
ga4_api_latency_seconds = Histogram(
    'ga4_api_latency_seconds',
    'GA4 API request latency in seconds',
    ['endpoint'],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)
)

# GA4 quota usage ratio (0.0 to 1.0)
ga4_quota_usage_ratio = Gauge(
    'ga4_quota_usage_ratio',
    'GA4 API quota usage ratio (requests used / total quota)',
    ['tenant_id', 'property_id']
)

# GA4 quota remaining
ga4_quota_remaining = Gauge(
    'ga4_quota_remaining_requests',
    'Remaining GA4 API quota requests',
    ['tenant_id', 'property_id']
)

# GA4 API errors by type
ga4_api_errors_total = Counter(
    'ga4_api_errors_total',
    'Total GA4 API errors by type',
    ['tenant_id', 'error_type']  # error_type: 'timeout', 'auth', 'rate_limit', 'server_error'
)

# GA4 cache hit rate
ga4_cache_hit_rate = Gauge(
    'ga4_cache_hit_rate',
    'GA4 response cache hit rate (0.0 to 1.0)',
    ['tenant_id']
)


# ============================================================================
# Vector Search Metrics
# ============================================================================

# Vector search latency
vector_search_latency_seconds = Histogram(
    'vector_search_latency_seconds',
    'Vector search query latency in seconds',
    ['tenant_id', 'search_type'],  # search_type: 'exact', 'approximate', 'hybrid'
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
)

# Vector search result count
vector_search_results_count = Histogram(
    'vector_search_results_count',
    'Number of results returned per vector search',
    ['tenant_id'],
    buckets=(1, 5, 10, 25, 50, 100, 250, 500)
)

# Vector search cache hit rate
vector_search_cache_hit_rate = Gauge(
    'vector_search_cache_hit_rate',
    'Vector search cache hit rate (0.0 to 1.0)',
    ['tenant_id']
)

# Vector embedding generation time
vector_embedding_duration_seconds = Histogram(
    'vector_embedding_duration_seconds',
    'Time to generate embeddings in seconds',
    ['model'],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

# Vector embedding batch size
vector_embedding_batch_size = Histogram(
    'vector_embedding_batch_size',
    'Number of texts in embedding batch',
    buckets=(1, 5, 10, 25, 50, 100)
)


# ============================================================================
# SSE Connection Metrics
# ============================================================================

# Active SSE connections
sse_active_connections = Gauge(
    'sse_active_connections',
    'Number of active SSE connections',
    ['tenant_id', 'endpoint']
)

# SSE connection duration
sse_connection_duration_seconds = Histogram(
    'sse_connection_duration_seconds',
    'Duration of SSE connections in seconds',
    ['tenant_id', 'endpoint'],
    buckets=(1, 5, 10, 30, 60, 300, 600, 1800, 3600)
)

# SSE events sent
sse_events_sent_total = Counter(
    'sse_events_sent_total',
    'Total SSE events sent to clients',
    ['tenant_id', 'event_type']  # event_type: 'status', 'result', 'error'
)

# SSE errors
sse_errors_total = Counter(
    'sse_errors_total',
    'Total SSE connection errors',
    ['tenant_id', 'error_type']  # error_type: 'disconnect', 'timeout', 'client_abort'
)


# ============================================================================
# HTTP Request Metrics
# ============================================================================

# HTTP request counter
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

# HTTP request latency
http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

# HTTP request size
http_request_size_bytes = Summary(
    'http_request_size_bytes',
    'HTTP request size in bytes',
    ['method', 'endpoint']
)

# HTTP response size
http_response_size_bytes = Summary(
    'http_response_size_bytes',
    'HTTP response size in bytes',
    ['method', 'endpoint']
)


# ============================================================================
# System Health Metrics
# ============================================================================

# System uptime
system_uptime_seconds = Gauge(
    'system_uptime_seconds',
    'System uptime in seconds'
)

# Active tenants
active_tenants_count = Gauge(
    'active_tenants_count',
    'Number of active tenants (with requests in last 5 minutes)'
)

# Memory usage
system_memory_usage_bytes = Gauge(
    'system_memory_usage_bytes',
    'System memory usage in bytes',
    ['type']  # type: 'rss', 'vms', 'shared'
)

# CPU usage
system_cpu_usage_percent = Gauge(
    'system_cpu_usage_percent',
    'System CPU usage percentage (0.0 to 100.0)'
)

# Background task queue size
background_task_queue_size = Gauge(
    'background_task_queue_size',
    'Number of pending background tasks',
    ['task_type']  # task_type: 'embedding', 'analytics', 'cleanup'
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
            # Update all metrics
            await update_pool_metrics()
            await update_system_metrics()
            
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
# GA4 API Metric Helpers
# ============================================================================

def track_ga4_api_call(endpoint: str, tenant_id: str):
    """
    Context manager to track GA4 API call metrics.
    
    Usage:
        with track_ga4_api_call("runReport", tenant_id):
            response = await ga4_client.run_report()
    """
    return ga4_api_latency_seconds.labels(endpoint=endpoint).time()


def record_ga4_api_success(endpoint: str, tenant_id: str):
    """Record successful GA4 API call."""
    ga4_api_calls_total.labels(
        tenant_id=tenant_id,
        endpoint=endpoint,
        status="success"
    ).inc()


def record_ga4_api_error(endpoint: str, tenant_id: str, error_type: str):
    """Record failed GA4 API call."""
    ga4_api_calls_total.labels(
        tenant_id=tenant_id,
        endpoint=endpoint,
        status="error"
    ).inc()
    ga4_api_errors_total.labels(
        tenant_id=tenant_id,
        error_type=error_type
    ).inc()


def record_ga4_quota(tenant_id: str, property_id: str, used: int, total: int):
    """Update GA4 quota metrics."""
    ga4_quota_usage_ratio.labels(
        tenant_id=tenant_id,
        property_id=property_id
    ).set(used / total if total > 0 else 0)
    
    ga4_quota_remaining.labels(
        tenant_id=tenant_id,
        property_id=property_id
    ).set(total - used)


# ============================================================================
# Vector Search Metric Helpers
# ============================================================================

def track_vector_search(tenant_id: str, search_type: str = "exact"):
    """
    Context manager to track vector search metrics.
    
    Usage:
        with track_vector_search(tenant_id, "hybrid"):
            results = await vector_search(query)
    """
    return vector_search_latency_seconds.labels(
        tenant_id=tenant_id,
        search_type=search_type
    ).time()


def record_vector_search_results(tenant_id: str, count: int):
    """Record vector search result count."""
    vector_search_results_count.labels(tenant_id=tenant_id).observe(count)


def track_embedding_generation(model: str):
    """
    Context manager to track embedding generation time.
    
    Usage:
        with track_embedding_generation("text-embedding-3-small"):
            embeddings = await generate_embeddings(texts)
    """
    return vector_embedding_duration_seconds.labels(model=model).time()


def record_embedding_batch(size: int):
    """Record embedding batch size."""
    vector_embedding_batch_size.observe(size)


# ============================================================================
# SSE Connection Metric Helpers
# ============================================================================

_sse_connection_start_times: Dict[str, float] = {}


def track_sse_connection_start(connection_id: str, tenant_id: str, endpoint: str):
    """Track SSE connection start."""
    sse_active_connections.labels(
        tenant_id=tenant_id,
        endpoint=endpoint
    ).inc()
    _sse_connection_start_times[connection_id] = time.time()


def track_sse_connection_end(connection_id: str, tenant_id: str, endpoint: str):
    """Track SSE connection end."""
    sse_active_connections.labels(
        tenant_id=tenant_id,
        endpoint=endpoint
    ).dec()
    
    # Record connection duration
    if connection_id in _sse_connection_start_times:
        duration = time.time() - _sse_connection_start_times[connection_id]
        sse_connection_duration_seconds.labels(
            tenant_id=tenant_id,
            endpoint=endpoint
        ).observe(duration)
        del _sse_connection_start_times[connection_id]


def record_sse_event(tenant_id: str, event_type: str):
    """Record SSE event sent."""
    sse_events_sent_total.labels(
        tenant_id=tenant_id,
        event_type=event_type
    ).inc()


def record_sse_error(tenant_id: str, error_type: str):
    """Record SSE connection error."""
    sse_errors_total.labels(
        tenant_id=tenant_id,
        error_type=error_type
    ).inc()


# ============================================================================
# HTTP Request Metric Helpers
# ============================================================================

def track_http_request(method: str, endpoint: str):
    """
    Decorator to track HTTP request metrics.
    
    Usage:
        @track_http_request("GET", "/api/v1/analytics")
        async def get_analytics():
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            with http_request_duration_seconds.labels(
                method=method,
                endpoint=endpoint
            ).time():
                result = await func(*args, **kwargs)
            return result
        return wrapper
    return decorator


def record_http_request(method: str, endpoint: str, status_code: int):
    """Record HTTP request completion."""
    http_requests_total.labels(
        method=method,
        endpoint=endpoint,
        status_code=str(status_code)
    ).inc()


def record_http_request_size(method: str, endpoint: str, size: int):
    """Record HTTP request size."""
    http_request_size_bytes.labels(
        method=method,
        endpoint=endpoint
    ).observe(size)


def record_http_response_size(method: str, endpoint: str, size: int):
    """Record HTTP response size."""
    http_response_size_bytes.labels(
        method=method,
        endpoint=endpoint
    ).observe(size)


# ============================================================================
# System Health Metric Helpers
# ============================================================================

async def update_system_metrics():
    """Update system-level metrics."""
    try:
        import psutil
        
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=0.1)
        system_cpu_usage_percent.set(cpu_percent)
        
        # Memory usage
        memory = psutil.Process().memory_info()
        system_memory_usage_bytes.labels(type="rss").set(memory.rss)
        system_memory_usage_bytes.labels(type="vms").set(memory.vms)
        
        # Uptime
        process = psutil.Process()
        uptime = time.time() - process.create_time()
        system_uptime_seconds.set(uptime)
        
    except ImportError:
        logger.warning("psutil not installed, skipping system metrics")
    except Exception as e:
        logger.error(f"Error updating system metrics: {e}", exc_info=True)


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

ga4_metrics = {
    "api_calls": ga4_api_calls_total,
    "latency": ga4_api_latency_seconds,
    "quota_usage": ga4_quota_usage_ratio,
    "quota_remaining": ga4_quota_remaining,
    "errors": ga4_api_errors_total,
    "cache_hit_rate": ga4_cache_hit_rate,
}

vector_search_metrics = {
    "latency": vector_search_latency_seconds,
    "results_count": vector_search_results_count,
    "cache_hit_rate": vector_search_cache_hit_rate,
    "embedding_duration": vector_embedding_duration_seconds,
    "embedding_batch_size": vector_embedding_batch_size,
}

sse_metrics = {
    "active_connections": sse_active_connections,
    "connection_duration": sse_connection_duration_seconds,
    "events_sent": sse_events_sent_total,
    "errors": sse_errors_total,
}

http_metrics = {
    "requests_total": http_requests_total,
    "request_duration": http_request_duration_seconds,
    "request_size": http_request_size_bytes,
    "response_size": http_response_size_bytes,
}

system_metrics = {
    "uptime": system_uptime_seconds,
    "active_tenants": active_tenants_count,
    "memory_usage": system_memory_usage_bytes,
    "cpu_usage": system_cpu_usage_percent,
    "background_tasks": background_task_queue_size,
}

all_metrics = {
    "connection_pool": connection_pool_metrics,
    "ga4": ga4_metrics,
    "vector_search": vector_search_metrics,
    "sse": sse_metrics,
    "http": http_metrics,
    "system": system_metrics,
}

