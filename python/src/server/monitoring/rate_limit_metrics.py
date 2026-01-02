"""
Rate Limit Queue Health Metrics.

Implements Task P0-14: Queue health metrics for monitoring

Provides Prometheus metrics for:
- Queue size and depth
- Wait times and throughput
- Retry statistics
- Backoff distribution

Integration with Grafana for real-time monitoring.
"""

import logging
from prometheus_client import Gauge, Counter, Histogram, Info

logger = logging.getLogger(__name__)


# ============================================================================
# Queue Size Metrics
# ============================================================================

rate_limit_queue_depth = Gauge(
    'ga4_rate_limit_queue_depth_total',
    'Total number of requests across all tenants in rate limit queue'
)

rate_limit_queue_by_priority = Gauge(
    'ga4_rate_limit_queue_by_priority',
    'Number of queued requests by priority level',
    ['priority']  # CRITICAL, HIGH, NORMAL, LOW
)

rate_limit_queue_oldest_wait_seconds = Gauge(
    'ga4_rate_limit_queue_oldest_wait_seconds',
    'Age of oldest request in queue',
    ['tenant_id']
)


# ============================================================================
# Throughput Metrics
# ============================================================================

rate_limit_requests_processed_total = Counter(
    'ga4_rate_limit_requests_processed_total',
    'Total requests processed from rate limit queue',
    ['tenant_id', 'status']  # success, failure, timeout
)

rate_limit_queue_throughput = Gauge(
    'ga4_rate_limit_queue_throughput_per_minute',
    'Requests processed per minute from rate limit queue',
    ['tenant_id']
)


# ============================================================================
# Wait Time Metrics
# ============================================================================

rate_limit_queue_wait_time_histogram = Histogram(
    'ga4_rate_limit_queue_wait_time_histogram_seconds',
    'Distribution of queue wait times',
    ['tenant_id', 'priority'],
    buckets=(1, 5, 10, 20, 30, 60, 120, 300, 600, 1800)
)

rate_limit_queue_avg_wait_seconds = Gauge(
    'ga4_rate_limit_queue_avg_wait_seconds',
    'Average wait time in queue',
    ['tenant_id']
)


# ============================================================================
# Retry and Backoff Metrics
# ============================================================================

rate_limit_retry_attempts_total = Counter(
    'ga4_rate_limit_retry_attempts_total',
    'Total number of retry attempts',
    ['tenant_id', 'attempt']  # attempt: 1, 2, 3, ...
)

rate_limit_backoff_current_seconds = Gauge(
    'ga4_rate_limit_backoff_current_seconds',
    'Current backoff time for tenant',
    ['tenant_id']
)

rate_limit_consecutive_429s = Gauge(
    'ga4_rate_limit_consecutive_429s',
    'Number of consecutive 429 responses',
    ['tenant_id']
)


# ============================================================================
# Health Status Metrics
# ============================================================================

rate_limit_queue_health_status = Gauge(
    'ga4_rate_limit_queue_health_status',
    'Queue health status (0=healthy, 1=warning, 2=critical, 3=failing)',
    ['tenant_id']
)

rate_limit_queue_capacity_ratio = Gauge(
    'ga4_rate_limit_queue_capacity_ratio',
    'Queue utilization ratio (0.0 to 1.0)',
    ['tenant_id']
)


# ============================================================================
# Metric Helper Functions
# ============================================================================

def record_queue_metrics(queue_stats: dict):
    """
    Update queue metrics from queue statistics.
    
    Args:
        queue_stats: Dictionary with queue statistics
    """
    # Overall depth
    rate_limit_queue_depth.set(queue_stats.get("total_queued", 0))
    
    # By priority
    by_priority = queue_stats.get("by_priority", {})
    for priority, count in by_priority.items():
        rate_limit_queue_by_priority.labels(priority=priority).set(count)
    
    # Wait times
    avg_wait = queue_stats.get("average_wait_seconds", 0.0)
    oldest_wait = queue_stats.get("oldest_wait_seconds", 0.0)
    
    for tenant_id, count in queue_stats.get("by_tenant", {}).items():
        rate_limit_queue_avg_wait_seconds.labels(tenant_id=tenant_id).set(avg_wait)
        rate_limit_queue_oldest_wait_seconds.labels(tenant_id=tenant_id).set(oldest_wait)


def record_request_processed(tenant_id: str, status: str, wait_time: float, priority: str):
    """
    Record a processed request.
    
    Args:
        tenant_id: Tenant ID
        status: success/failure/timeout
        wait_time: Time spent in queue (seconds)
        priority: Request priority
    """
    rate_limit_requests_processed_total.labels(
        tenant_id=tenant_id,
        status=status
    ).inc()
    
    rate_limit_queue_wait_time_histogram.labels(
        tenant_id=tenant_id,
        priority=priority
    ).observe(wait_time)


def record_retry_attempt(tenant_id: str, attempt: int):
    """
    Record a retry attempt.
    
    Args:
        tenant_id: Tenant ID
        attempt: Retry attempt number (1, 2, 3, ...)
    """
    rate_limit_retry_attempts_total.labels(
        tenant_id=tenant_id,
        attempt=str(attempt)
    ).inc()


def update_rate_limit_state(tenant_id: str, state_info: dict):
    """
    Update rate limit state metrics.
    
    Args:
        tenant_id: Tenant ID
        state_info: State information dictionary
    """
    # Backoff time
    backoff = state_info.get("current_backoff_seconds", 0.0)
    rate_limit_backoff_current_seconds.labels(tenant_id=tenant_id).set(backoff)
    
    # Consecutive 429s
    consecutive = state_info.get("consecutive_429s", 0)
    rate_limit_consecutive_429s.labels(tenant_id=tenant_id).set(consecutive)
    
    # Health status
    if state_info.get("is_rate_limited", False):
        if consecutive >= 5:
            health_status = 3  # Failing
        elif consecutive >= 3:
            health_status = 2  # Critical
        elif consecutive >= 1:
            health_status = 1  # Warning
        else:
            health_status = 0  # Healthy
    else:
        health_status = 0  # Healthy
    
    rate_limit_queue_health_status.labels(tenant_id=tenant_id).set(health_status)


def update_queue_capacity(tenant_id: str, current_size: int, max_size: int):
    """
    Update queue capacity metrics.
    
    Args:
        tenant_id: Tenant ID
        current_size: Current queue size
        max_size: Maximum queue size
    """
    ratio = current_size / max_size if max_size > 0 else 0.0
    rate_limit_queue_capacity_ratio.labels(tenant_id=tenant_id).set(ratio)


# ============================================================================
# Health Check Function
# ============================================================================

def check_queue_health(queue_stats: dict) -> dict:
    """
    Assess queue health and return status.
    
    Args:
        queue_stats: Queue statistics dictionary
        
    Returns:
        Health assessment dictionary
    """
    total_queued = queue_stats.get("total_queued", 0)
    oldest_wait = queue_stats.get("oldest_wait_seconds", 0.0)
    
    # Determine health status
    if total_queued == 0:
        status = "healthy"
        level = 0
    elif oldest_wait > 300:  # 5 minutes
        status = "critical"
        level = 2
    elif oldest_wait > 120:  # 2 minutes
        status = "warning"
        level = 1
    else:
        status = "healthy"
        level = 0
    
    # Check for starvation (requests waiting too long)
    starvation_risk = oldest_wait > 600  # 10 minutes
    
    return {
        "status": status,
        "level": level,
        "total_queued": total_queued,
        "oldest_wait_seconds": oldest_wait,
        "starvation_risk": starvation_risk,
        "recommendation": _get_recommendation(status, oldest_wait, total_queued)
    }


def _get_recommendation(status: str, oldest_wait: float, total_queued: int) -> str:
    """Get recommendation based on health status."""
    if status == "critical":
        return (
            f"CRITICAL: {total_queued} requests queued, oldest waiting {oldest_wait:.0f}s. "
            "Consider increasing rate limits or scaling workers."
        )
    elif status == "warning":
        return (
            f"WARNING: Queue building up ({total_queued} requests). "
            "Monitor closely for potential issues."
        )
    else:
        return "Queue is healthy."

