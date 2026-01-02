"""
Anomaly Alerting System for Embedding Quality Issues.

Implements Task P0-5: Embedding Quality Assurance Pipeline

Features:
- Alert generation for quality issues
- Alert prioritization (warning, critical)
- Multi-channel alert delivery (logs, email, Slack)
- Alert rate limiting (prevent spam)
- Admin dashboard integration

Alert Triggers:
- Low quality batch (< 70% high quality embeddings)
- Semantic drift detected (similarity < 95%)
- High NaN/Inf rate (> 1%)
- Zero vector frequency (> 0.1%)
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from enum import Enum
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertChannel(str, Enum):
    """Alert delivery channels."""
    LOG = "log"
    EMAIL = "email"
    SLACK = "slack"
    PAGERDUTY = "pagerduty"


class EmbeddingQualityAlert(BaseModel):
    """Alert for embedding quality issues."""
    
    alert_id: str
    tenant_id: str
    level: AlertLevel
    title: str
    message: str
    details: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    channels: List[AlertChannel] = Field(default_factory=list)
    acknowledged: bool = False


class AnomalyAlertService:
    """
    Service for generating and managing embedding quality alerts.
    
    Implements Task P0-5: Admin alerting system
    
    Features:
    - Threshold-based alert generation
    - Rate limiting (max 1 alert per hour per type)
    - Multi-channel delivery
    - Alert history tracking
    
    Usage:
        alerter = AnomalyAlertService(redis_client)
        
        # Check batch quality and alert if needed
        if batch_stats["low_quality_percent"] > 30:
            await alerter.trigger_low_quality_alert(
                tenant_id="tenant-123",
                batch_stats=batch_stats
            )
    """
    
    ALERT_HISTORY_KEY = "embedding:alerts:"
    RATE_LIMIT_KEY = "embedding:alert_ratelimit:"
    RATE_LIMIT_WINDOW = 3600  # 1 hour
    
    def __init__(self, redis_client):
        """
        Initialize alert service.
        
        Args:
            redis_client: Redis client for alert history
        """
        self.redis = redis_client
        self._alert_history: List[EmbeddingQualityAlert] = []
        
        logger.info("Anomaly alert service initialized")
    
    async def trigger_low_quality_alert(
        self,
        tenant_id: str,
        batch_stats: Dict[str, Any]
    ):
        """
        Trigger alert for low quality batch.
        
        Args:
            tenant_id: Tenant ID
            batch_stats: Batch quality statistics
        """
        alert_type = "low_quality_batch"
        
        # Check rate limit
        if await self._is_rate_limited(tenant_id, alert_type):
            logger.debug(f"Alert rate limited: {alert_type} for tenant {tenant_id}")
            return
        
        # Determine severity
        low_quality_percent = batch_stats.get("low_quality_percent", 0)
        
        if low_quality_percent > 50:
            level = AlertLevel.CRITICAL
            channels = [AlertChannel.LOG, AlertChannel.EMAIL, AlertChannel.PAGERDUTY]
        elif low_quality_percent > 30:
            level = AlertLevel.WARNING
            channels = [AlertChannel.LOG, AlertChannel.SLACK]
        else:
            level = AlertLevel.INFO
            channels = [AlertChannel.LOG]
        
        # Create alert
        alert = EmbeddingQualityAlert(
            alert_id=f"{tenant_id}:{alert_type}:{datetime.utcnow().isoformat()}",
            tenant_id=tenant_id,
            level=level,
            title=f"Low Quality Embedding Batch Detected",
            message=(
                f"Embedding batch quality below threshold: "
                f"{low_quality_percent:.1f}% low quality embeddings "
                f"(expected < 30%)"
            ),
            details=batch_stats,
            channels=channels
        )
        
        # Deliver alert
        await self._deliver_alert(alert)
        
        # Record in history
        self._alert_history.append(alert)
        
        # Set rate limit
        await self._set_rate_limit(tenant_id, alert_type)
    
    async def trigger_drift_alert(
        self,
        tenant_id: str,
        drift_result: Dict[str, Any]
    ):
        """
        Trigger alert for semantic drift.
        
        Args:
            tenant_id: Tenant ID
            drift_result: Drift detection result
        """
        alert_type = "semantic_drift"
        
        # Check rate limit
        if await self._is_rate_limited(tenant_id, alert_type):
            logger.debug(f"Alert rate limited: {alert_type} for tenant {tenant_id}")
            return
        
        # Determine severity based on similarity
        similarity = drift_result.get("avg_similarity_to_baseline", 1.0)
        
        if similarity < 0.90:
            level = AlertLevel.CRITICAL
            channels = [AlertChannel.LOG, AlertChannel.EMAIL, AlertChannel.PAGERDUTY]
        elif similarity < 0.95:
            level = AlertLevel.WARNING
            channels = [AlertChannel.LOG, AlertChannel.SLACK]
        else:
            level = AlertLevel.INFO
            channels = [AlertChannel.LOG]
        
        # Create alert
        alert = EmbeddingQualityAlert(
            alert_id=f"{tenant_id}:{alert_type}:{datetime.utcnow().isoformat()}",
            tenant_id=tenant_id,
            level=level,
            title=f"Semantic Drift Detected",
            message=(
                f"Embedding model behavior has drifted: "
                f"{similarity:.2%} similarity to baseline "
                f"(expected >= 95%)"
            ),
            details=drift_result,
            channels=channels
        )
        
        # Deliver alert
        await self._deliver_alert(alert)
        
        # Record in history
        self._alert_history.append(alert)
        
        # Set rate limit
        await self._set_rate_limit(tenant_id, alert_type)
    
    async def trigger_high_error_rate_alert(
        self,
        tenant_id: str,
        error_stats: Dict[str, Any]
    ):
        """
        Trigger alert for high embedding error rate.
        
        Args:
            tenant_id: Tenant ID
            error_stats: Error statistics (NaN/Inf/zero vector counts)
        """
        alert_type = "high_error_rate"
        
        if await self._is_rate_limited(tenant_id, alert_type):
            return
        
        error_rate = error_stats.get("error_rate_percent", 0)
        
        # Create alert
        alert = EmbeddingQualityAlert(
            alert_id=f"{tenant_id}:{alert_type}:{datetime.utcnow().isoformat()}",
            tenant_id=tenant_id,
            level=AlertLevel.CRITICAL,
            title=f"High Embedding Error Rate",
            message=(
                f"Embedding generation error rate: {error_rate:.1f}% "
                f"(threshold: 1%)"
            ),
            details=error_stats,
            channels=[AlertChannel.LOG, AlertChannel.EMAIL]
        )
        
        await self._deliver_alert(alert)
        self._alert_history.append(alert)
        await self._set_rate_limit(tenant_id, alert_type)
    
    async def _deliver_alert(self, alert: EmbeddingQualityAlert):
        """
        Deliver alert through configured channels.
        
        Args:
            alert: Alert to deliver
        """
        for channel in alert.channels:
            if channel == AlertChannel.LOG:
                self._log_alert(alert)
            
            elif channel == AlertChannel.EMAIL:
                await self._send_email_alert(alert)
            
            elif channel == AlertChannel.SLACK:
                await self._send_slack_alert(alert)
            
            elif channel == AlertChannel.PAGERDUTY:
                await self._send_pagerduty_alert(alert)
    
    def _log_alert(self, alert: EmbeddingQualityAlert):
        """Log alert."""
        if alert.level == AlertLevel.CRITICAL:
            logger.critical(
                f"[ALERT] {alert.title}: {alert.message}",
                extra={"alert": alert.dict()}
            )
        elif alert.level == AlertLevel.WARNING:
            logger.warning(
                f"[ALERT] {alert.title}: {alert.message}",
                extra={"alert": alert.dict()}
            )
        else:
            logger.info(
                f"[ALERT] {alert.title}: {alert.message}",
                extra={"alert": alert.dict()}
            )
    
    async def _send_email_alert(self, alert: EmbeddingQualityAlert):
        """Send email alert (placeholder)."""
        # TODO: Integrate with email service (SendGrid, SES, etc.)
        logger.info(f"EMAIL alert: {alert.title} (placeholder)")
    
    async def _send_slack_alert(self, alert: EmbeddingQualityAlert):
        """Send Slack alert (placeholder)."""
        # TODO: Integrate with Slack API
        logger.info(f"SLACK alert: {alert.title} (placeholder)")
    
    async def _send_pagerduty_alert(self, alert: EmbeddingQualityAlert):
        """Send PagerDuty alert (placeholder)."""
        # TODO: Integrate with PagerDuty API
        logger.info(f"PAGERDUTY alert: {alert.title} (placeholder)")
    
    async def _is_rate_limited(self, tenant_id: str, alert_type: str) -> bool:
        """Check if alert type is rate limited."""
        key = f"{self.RATE_LIMIT_KEY}{tenant_id}:{alert_type}"
        exists = await self.redis.exists(key)
        return exists > 0
    
    async def _set_rate_limit(self, tenant_id: str, alert_type: str):
        """Set rate limit for alert type."""
        key = f"{self.RATE_LIMIT_KEY}{tenant_id}:{alert_type}"
        await self.redis.setex(key, self.RATE_LIMIT_WINDOW, "1")
    
    def get_alert_history(
        self,
        tenant_id: Optional[str] = None,
        level: Optional[AlertLevel] = None
    ) -> List[EmbeddingQualityAlert]:
        """
        Get alert history.
        
        Args:
            tenant_id: Filter by tenant
            level: Filter by alert level
        
        Returns:
            List of alerts
        """
        alerts = self._alert_history
        
        if tenant_id:
            alerts = [a for a in alerts if a.tenant_id == tenant_id]
        
        if level:
            alerts = [a for a in alerts if a.level == level]
        
        return alerts
    
    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity."""
        arr1 = np.array(vec1)
        arr2 = np.array(vec2)
        
        dot_product = np.dot(arr1, arr2)
        norm1 = np.linalg.norm(arr1)
        norm2 = np.linalg.norm(arr2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(max(0.0, min(1.0, dot_product / (norm1 * norm2))))

