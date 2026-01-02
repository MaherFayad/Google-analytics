"""
Connection Pool Health Monitoring.

Implements Task P0-13: Connection Pool Health Monitoring [HIGH]

Provides real-time monitoring and alerting for database connection pool health
to prevent silent pool exhaustion failures at scale.

Features:
- Real-time pool utilization metrics
- Automatic health checks every 5 seconds
- Alert triggers at 80% and 90% thresholds
- Auto-scaling recommendations
- Integration with Prometheus and Grafana

Integration with Application:

```python
# In main FastAPI app startup
from server.monitoring.connection_pool import start_pool_monitoring

@app.on_event("startup")
async def startup():
    await start_pool_monitoring()

@app.on_event("shutdown")
async def shutdown():
    await stop_pool_monitoring()
```
"""

import logging
import asyncio
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from prometheus_client import Gauge, Counter, Histogram, Info

logger = logging.getLogger(__name__)


# ============================================================================
# Health Status Enum
# ============================================================================

class PoolHealthStatus(str, Enum):
    """Connection pool health status levels."""
    HEALTHY = "healthy"          # < 70% utilization
    WARNING = "warning"          # 70-80% utilization
    CRITICAL = "critical"        # 80-90% utilization
    EXHAUSTED = "exhausted"      # > 90% utilization
    UNKNOWN = "unknown"          # Unable to determine


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class PoolMetrics:
    """Connection pool metrics snapshot."""
    
    # Pool identification
    pool_type: str  # "transactional" or "session"
    timestamp: datetime
    
    # Connection counts
    active_connections: int
    idle_connections: int
    overflow_connections: int
    total_connections: int
    
    # Pool configuration
    pool_size: int
    max_overflow: int
    max_connections: int
    
    # Utilization
    utilization_percent: float
    health_status: PoolHealthStatus
    
    # Performance
    avg_checkout_time_ms: float = 0.0
    queue_length: int = 0
    wait_time_ms: float = 0.0


@dataclass
class PoolHealthCheck:
    """Pool health check result."""
    
    timestamp: datetime
    pool_type: str
    health_status: PoolHealthStatus
    utilization_percent: float
    
    # Issues detected
    warnings: List[str]
    recommendations: List[str]
    
    # Metrics
    metrics: PoolMetrics


# ============================================================================
# Prometheus Metrics (Extended)
# ============================================================================

# Pool health status gauge (0-3: healthy, warning, critical, exhausted)
pool_health_status_gauge = Gauge(
    'db_pool_health_status',
    'Connection pool health status level (0=healthy, 1=warning, 2=critical, 3=exhausted)',
    ['pool_type']
)

# Pool checkout time (time to get connection from pool)
pool_checkout_duration_seconds = Histogram(
    'db_pool_checkout_duration_seconds',
    'Time to checkout connection from pool',
    ['pool_type'],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0, 10.0)
)

# Pool wait queue length
pool_queue_length = Gauge(
    'db_pool_queue_length',
    'Number of requests waiting for connection',
    ['pool_type']
)

# Pool exhaustion events
pool_exhaustion_total = Counter(
    'db_pool_exhaustion_total',
    'Total number of pool exhaustion events',
    ['pool_type', 'severity']  # warning, critical, exhausted
)

# Pool alert triggers
pool_alert_triggered_total = Counter(
    'db_pool_alert_triggered_total',
    'Total number of pool alerts triggered',
    ['pool_type', 'alert_type']  # threshold_80, threshold_90, exhausted
)

# Connection checkout failures
pool_checkout_failures_total = Counter(
    'db_pool_checkout_failures_total',
    'Total number of failed connection checkouts',
    ['pool_type', 'reason']  # timeout, pool_exhausted, error
)

# Pool recovery events
pool_recovery_total = Counter(
    'db_pool_recovery_total',
    'Number of times pool recovered from critical state',
    ['pool_type']
)


# ============================================================================
# Connection Pool Monitor
# ============================================================================

class ConnectionPoolMonitor:
    """
    Monitors database connection pool health and triggers alerts.
    
    Features:
    - Real-time health checks every 5 seconds
    - Automatic alert triggering at thresholds
    - Scaling recommendations
    - Performance tracking
    
    Example:
        >>> monitor = ConnectionPoolMonitor()
        >>> await monitor.start()
        >>> 
        >>> # Check current health
        >>> health = await monitor.get_health_status()
        >>> print(f"Pool health: {health.health_status}")
    """
    
    def __init__(
        self,
        check_interval: int = 5,
        warning_threshold: float = 70.0,
        critical_threshold: float = 80.0,
        exhaustion_threshold: float = 90.0
    ):
        """
        Initialize pool monitor.
        
        Args:
            check_interval: Seconds between health checks (default: 5)
            warning_threshold: Warning alert threshold (default: 70%)
            critical_threshold: Critical alert threshold (default: 80%)
            exhaustion_threshold: Exhaustion alert threshold (default: 90%)
        """
        self.check_interval = check_interval
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.exhaustion_threshold = exhaustion_threshold
        
        self._task: Optional[asyncio.Task] = None
        self._is_running = False
        
        # Health history for trend analysis
        self._health_history: List[PoolHealthCheck] = []
        self._max_history_size = 100
        
        # Previous health status for alert deduplication
        self._last_status: Dict[str, PoolHealthStatus] = {}
        
        # Alert callback
        self._alert_callback: Optional[callable] = None
        
        logger.info(
            f"Connection pool monitor initialized "
            f"(warning={warning_threshold}%, critical={critical_threshold}%, "
            f"exhaustion={exhaustion_threshold}%)"
        )
    
    def set_alert_callback(self, callback: callable):
        """
        Set callback function for alerts.
        
        Args:
            callback: Async function called when alert is triggered
                     Signature: async def alert(health_check: PoolHealthCheck)
        
        Example:
            >>> async def send_pagerduty_alert(health_check):
            ...     await pagerduty.trigger_alert(health_check)
            >>> monitor.set_alert_callback(send_pagerduty_alert)
        """
        self._alert_callback = callback
    
    async def start(self):
        """Start the monitoring task."""
        if self._is_running:
            logger.warning("Pool monitor already running")
            return
        
        self._is_running = True
        self._task = asyncio.create_task(self._monitoring_loop())
        logger.info("Connection pool monitoring started")
    
    async def stop(self):
        """Stop the monitoring task."""
        if not self._is_running:
            return
        
        self._is_running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Connection pool monitoring stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop that runs health checks."""
        logger.info(f"Starting pool monitoring loop (interval={self.check_interval}s)")
        
        while self._is_running:
            try:
                # Check health of both pools
                await self._check_pool_health("transactional")
                await self._check_pool_health("session")
                
                # Sleep until next check
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                logger.info("Pool monitoring loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in pool monitoring loop: {e}", exc_info=True)
                await asyncio.sleep(self.check_interval)  # Continue despite errors
    
    async def _check_pool_health(self, pool_type: str):
        """
        Check health of a specific pool and trigger alerts if needed.
        
        Args:
            pool_type: "transactional" or "session"
        """
        try:
            # Import here to avoid circular dependency
            from ..database import get_pool_stats
            
            # Get current pool stats
            stats = await get_pool_stats()
            pool_stats = stats[pool_type]
            
            # Create metrics snapshot
            metrics = PoolMetrics(
                pool_type=pool_type,
                timestamp=datetime.utcnow(),
                active_connections=pool_stats["checked_out"],
                idle_connections=pool_stats["checked_in"],
                overflow_connections=pool_stats.get("overflow", 0),
                total_connections=pool_stats["checked_out"] + pool_stats["checked_in"],
                pool_size=pool_stats["pool_size"],
                max_overflow=pool_stats.get("max_overflow", 0),
                max_connections=pool_stats["pool_size"] + pool_stats.get("max_overflow", 0),
                utilization_percent=pool_stats["utilization"],
            )
            
            # Determine health status
            if metrics.utilization_percent >= self.exhaustion_threshold:
                metrics.health_status = PoolHealthStatus.EXHAUSTED
            elif metrics.utilization_percent >= self.critical_threshold:
                metrics.health_status = PoolHealthStatus.CRITICAL
            elif metrics.utilization_percent >= self.warning_threshold:
                metrics.health_status = PoolHealthStatus.WARNING
            else:
                metrics.health_status = PoolHealthStatus.HEALTHY
            
            # Analyze and generate warnings/recommendations
            warnings = []
            recommendations = []
            
            if metrics.health_status == PoolHealthStatus.EXHAUSTED:
                warnings.append(f"Pool exhaustion! {metrics.utilization_percent:.1f}% utilized")
                recommendations.append("Immediate action: Increase pool_size or max_overflow")
                recommendations.append("Review slow queries causing connection holding")
                pool_exhaustion_total.labels(
                    pool_type=pool_type,
                    severity="exhausted"
                ).inc()
            
            elif metrics.health_status == PoolHealthStatus.CRITICAL:
                warnings.append(f"Critical utilization: {metrics.utilization_percent:.1f}%")
                recommendations.append("Consider increasing pool_size")
                recommendations.append("Monitor for potential exhaustion")
                pool_exhaustion_total.labels(
                    pool_type=pool_type,
                    severity="critical"
                ).inc()
            
            elif metrics.health_status == PoolHealthStatus.WARNING:
                warnings.append(f"High utilization: {metrics.utilization_percent:.1f}%")
                recommendations.append("Prepare to scale if trend continues")
            
            # Check for overflow usage
            if metrics.overflow_connections > 0:
                warnings.append(f"Using overflow connections: {metrics.overflow_connections}")
                recommendations.append("Base pool_size may be too small for normal load")
            
            # Create health check result
            health_check = PoolHealthCheck(
                timestamp=metrics.timestamp,
                pool_type=pool_type,
                health_status=metrics.health_status,
                utilization_percent=metrics.utilization_percent,
                warnings=warnings,
                recommendations=recommendations,
                metrics=metrics,
            )
            
            # Update Prometheus metrics
            self._update_metrics(health_check)
            
            # Store in history
            self._health_history.append(health_check)
            if len(self._health_history) > self._max_history_size:
                self._health_history.pop(0)
            
            # Trigger alert if status changed
            await self._check_and_trigger_alert(health_check)
            
            # Log health status
            if metrics.health_status != PoolHealthStatus.HEALTHY:
                logger.warning(
                    f"Pool health check [{pool_type}]: {metrics.health_status.value} "
                    f"({metrics.utilization_percent:.1f}% utilized, "
                    f"active={metrics.active_connections}, idle={metrics.idle_connections})"
                )
            
        except Exception as e:
            logger.error(f"Error checking pool health [{pool_type}]: {e}", exc_info=True)
    
    def _update_metrics(self, health_check: PoolHealthCheck):
        """Update Prometheus metrics with health check results."""
        pool_type = health_check.pool_type
        
        # Update health status gauge
        status_value = {
            PoolHealthStatus.HEALTHY: 0,
            PoolHealthStatus.WARNING: 1,
            PoolHealthStatus.CRITICAL: 2,
            PoolHealthStatus.EXHAUSTED: 3,
        }.get(health_check.health_status, -1)
        
        pool_health_status_gauge.labels(pool_type=pool_type).set(status_value)
    
    async def _check_and_trigger_alert(self, health_check: PoolHealthCheck):
        """Check if alert should be triggered and call callback."""
        pool_type = health_check.pool_type
        current_status = health_check.health_status
        previous_status = self._last_status.get(pool_type, PoolHealthStatus.UNKNOWN)
        
        # Trigger alert if status worsened
        should_alert = False
        alert_type = None
        
        if current_status == PoolHealthStatus.EXHAUSTED and previous_status != PoolHealthStatus.EXHAUSTED:
            should_alert = True
            alert_type = "exhausted"
        
        elif current_status == PoolHealthStatus.CRITICAL and previous_status not in [
            PoolHealthStatus.CRITICAL,
            PoolHealthStatus.EXHAUSTED
        ]:
            should_alert = True
            alert_type = "threshold_90"
        
        elif current_status == PoolHealthStatus.WARNING and previous_status == PoolHealthStatus.HEALTHY:
            should_alert = True
            alert_type = "threshold_80"
        
        # Trigger recovery alert if status improved
        elif current_status == PoolHealthStatus.HEALTHY and previous_status in [
            PoolHealthStatus.WARNING,
            PoolHealthStatus.CRITICAL,
            PoolHealthStatus.EXHAUSTED
        ]:
            logger.info(f"Pool recovered [{pool_type}]: {previous_status.value} → {current_status.value}")
            pool_recovery_total.labels(pool_type=pool_type).inc()
        
        # Update last status
        self._last_status[pool_type] = current_status
        
        # Trigger alert
        if should_alert and alert_type:
            logger.warning(
                f"Pool alert triggered [{pool_type}]: {alert_type} "
                f"(utilization={health_check.utilization_percent:.1f}%)"
            )
            
            pool_alert_triggered_total.labels(
                pool_type=pool_type,
                alert_type=alert_type
            ).inc()
            
            # Call alert callback if set
            if self._alert_callback:
                try:
                    await self._alert_callback(health_check)
                except Exception as e:
                    logger.error(f"Error in alert callback: {e}", exc_info=True)
    
    async def get_health_status(self, pool_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Get current health status for pool(s).
        
        Args:
            pool_type: Specific pool to check, or None for all pools
            
        Returns:
            Dictionary with health status information
        """
        result = {}
        
        # Get recent health checks
        for health_check in reversed(self._health_history[-10:]):
            if pool_type is None or health_check.pool_type == pool_type:
                if health_check.pool_type not in result:
                    result[health_check.pool_type] = {
                        "health_status": health_check.health_status.value,
                        "utilization_percent": health_check.utilization_percent,
                        "warnings": health_check.warnings,
                        "recommendations": health_check.recommendations,
                        "last_check": health_check.timestamp.isoformat(),
                        "metrics": {
                            "active": health_check.metrics.active_connections,
                            "idle": health_check.metrics.idle_connections,
                            "overflow": health_check.metrics.overflow_connections,
                            "total": health_check.metrics.total_connections,
                            "max": health_check.metrics.max_connections,
                        }
                    }
        
        return result
    
    def get_health_history(
        self,
        pool_type: Optional[str] = None,
        limit: int = 20
    ) -> List[PoolHealthCheck]:
        """
        Get recent health check history.
        
        Args:
            pool_type: Filter by pool type, or None for all
            limit: Maximum number of results
            
        Returns:
            List of health checks (most recent first)
        """
        history = self._health_history[-limit:]
        
        if pool_type:
            history = [h for h in history if h.pool_type == pool_type]
        
        return list(reversed(history))


# ============================================================================
# Global Monitor Instance
# ============================================================================

_pool_monitor: Optional[ConnectionPoolMonitor] = None


async def start_pool_monitoring(
    check_interval: int = 5,
    alert_callback: Optional[callable] = None
) -> ConnectionPoolMonitor:
    """
    Start connection pool monitoring.
    
    Should be called at application startup.
    
    Args:
        check_interval: Seconds between health checks
        alert_callback: Optional callback for alerts
        
    Returns:
        ConnectionPoolMonitor instance
        
    Usage:
        @app.on_event("startup")
        async def startup():
            await start_pool_monitoring(alert_callback=send_slack_alert)
    """
    global _pool_monitor
    
    if _pool_monitor is not None:
        logger.warning("Pool monitoring already started")
        return _pool_monitor
    
    _pool_monitor = ConnectionPoolMonitor(check_interval=check_interval)
    
    if alert_callback:
        _pool_monitor.set_alert_callback(alert_callback)
    
    await _pool_monitor.start()
    
    return _pool_monitor


async def stop_pool_monitoring():
    """
    Stop connection pool monitoring.
    
    Should be called at application shutdown.
    
    Usage:
        @app.on_event("shutdown")
        async def shutdown():
            await stop_pool_monitoring()
    """
    global _pool_monitor
    
    if _pool_monitor is None:
        return
    
    await _pool_monitor.stop()
    _pool_monitor = None


async def get_pool_health_status(pool_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Get current pool health status.
    
    Args:
        pool_type: Specific pool type, or None for all
        
    Returns:
        Dictionary with health status
    """
    if _pool_monitor is None:
        return {"error": "Pool monitoring not started"}
    
    return await _pool_monitor.get_health_status(pool_type)


def get_pool_monitor() -> Optional[ConnectionPoolMonitor]:
    """Get global pool monitor instance."""
    return _pool_monitor

