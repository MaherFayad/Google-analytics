"""
Alert Trigger Logic.

Implements Task P0-13: Connection Pool Health Monitoring Alert System

Provides alert triggers for various monitoring systems:
- Slack notifications
- PagerDuty incident creation
- Email alerts
- Webhook notifications

Integration:

```python
from server.monitoring.connection_pool import start_pool_monitoring
from server.monitoring.alerts import send_alert

async def alert_handler(health_check):
    await send_alert(health_check, channels=["slack", "pagerduty"])

await start_pool_monitoring(alert_callback=alert_handler)
```
"""

import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


# ============================================================================
# Alert Severity Levels
# ============================================================================

class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ============================================================================
# Alert Channels
# ============================================================================

class AlertChannel(str, Enum):
    """Supported alert channels."""
    SLACK = "slack"
    PAGERDUTY = "pagerduty"
    EMAIL = "email"
    WEBHOOK = "webhook"
    LOG = "log"


# ============================================================================
# Alert Configuration
# ============================================================================

class AlertConfig:
    """Alert configuration settings."""
    
    # Slack
    SLACK_WEBHOOK_URL: Optional[str] = None
    SLACK_CHANNEL: str = "#alerts"
    
    # PagerDuty
    PAGERDUTY_API_KEY: Optional[str] = None
    PAGERDUTY_SERVICE_ID: Optional[str] = None
    
    # Email
    EMAIL_SMTP_HOST: Optional[str] = None
    EMAIL_SMTP_PORT: int = 587
    EMAIL_FROM: Optional[str] = None
    EMAIL_TO: List[str] = []
    
    # Webhook
    WEBHOOK_URL: Optional[str] = None
    WEBHOOK_AUTH_TOKEN: Optional[str] = None
    
    # Alert settings
    ENABLE_ALERTS: bool = True
    ALERT_COOLDOWN_SECONDS: int = 300  # 5 minutes
    
    @classmethod
    def from_env(cls):
        """Load configuration from environment variables."""
        import os
        
        cls.SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
        cls.SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "#alerts")
        
        cls.PAGERDUTY_API_KEY = os.getenv("PAGERDUTY_API_KEY")
        cls.PAGERDUTY_SERVICE_ID = os.getenv("PAGERDUTY_SERVICE_ID")
        
        cls.EMAIL_SMTP_HOST = os.getenv("EMAIL_SMTP_HOST")
        cls.EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
        cls.EMAIL_FROM = os.getenv("EMAIL_FROM")
        email_to = os.getenv("EMAIL_TO", "")
        cls.EMAIL_TO = [e.strip() for e in email_to.split(",") if e.strip()]
        
        cls.WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL")
        cls.WEBHOOK_AUTH_TOKEN = os.getenv("ALERT_WEBHOOK_AUTH_TOKEN")
        
        cls.ENABLE_ALERTS = os.getenv("ENABLE_ALERTS", "true").lower() == "true"


# Load configuration on module import
AlertConfig.from_env()


# ============================================================================
# Alert Cooldown Tracker
# ============================================================================

_alert_cooldowns: Dict[str, datetime] = {}


def should_send_alert(alert_key: str) -> bool:
    """
    Check if alert should be sent based on cooldown period.
    
    Args:
        alert_key: Unique key for alert (e.g., "pool_exhausted_transactional")
        
    Returns:
        True if alert should be sent
    """
    from datetime import timedelta
    
    now = datetime.utcnow()
    last_sent = _alert_cooldowns.get(alert_key)
    
    if last_sent is None:
        return True
    
    cooldown = timedelta(seconds=AlertConfig.ALERT_COOLDOWN_SECONDS)
    return now - last_sent >= cooldown


def mark_alert_sent(alert_key: str):
    """Mark alert as sent to start cooldown period."""
    _alert_cooldowns[alert_key] = datetime.utcnow()


# ============================================================================
# Main Alert Function
# ============================================================================

async def send_alert(
    health_check,  # PoolHealthCheck from connection_pool.py
    channels: Optional[List[str]] = None,
    severity: Optional[AlertSeverity] = None
) -> Dict[str, bool]:
    """
    Send alert to configured channels.
    
    Args:
        health_check: PoolHealthCheck object with details
        channels: List of channels to send to (default: all configured)
        severity: Override severity level
        
    Returns:
        Dictionary with success status per channel
        
    Example:
        >>> async def alert_handler(health_check):
        ...     result = await send_alert(
        ...         health_check,
        ...         channels=["slack", "pagerduty"]
        ...     )
        ...     print(f"Sent to: {result}")
    """
    if not AlertConfig.ENABLE_ALERTS:
        logger.debug("Alerts disabled, skipping")
        return {}
    
    # Check cooldown
    alert_key = f"pool_{health_check.health_status.value}_{health_check.pool_type}"
    if not should_send_alert(alert_key):
        logger.debug(f"Alert {alert_key} in cooldown period, skipping")
        return {}
    
    # Determine severity
    if severity is None:
        severity = _determine_severity(health_check)
    
    # Build alert message
    alert_data = _build_alert_data(health_check, severity)
    
    # Send to channels
    results = {}
    channels = channels or ["log", "slack", "pagerduty"]
    
    for channel in channels:
        try:
            if channel == AlertChannel.SLACK:
                results[channel] = await _send_slack_alert(alert_data)
            elif channel == AlertChannel.PAGERDUTY:
                results[channel] = await _send_pagerduty_alert(alert_data)
            elif channel == AlertChannel.EMAIL:
                results[channel] = await _send_email_alert(alert_data)
            elif channel == AlertChannel.WEBHOOK:
                results[channel] = await _send_webhook_alert(alert_data)
            elif channel == AlertChannel.LOG:
                results[channel] = _send_log_alert(alert_data)
            else:
                logger.warning(f"Unknown alert channel: {channel}")
                results[channel] = False
        
        except Exception as e:
            logger.error(f"Error sending alert to {channel}: {e}", exc_info=True)
            results[channel] = False
    
    # Mark as sent if any channel succeeded
    if any(results.values()):
        mark_alert_sent(alert_key)
    
    return results


def _determine_severity(health_check) -> AlertSeverity:
    """Determine alert severity from health check."""
    from .connection_pool import PoolHealthStatus
    
    status_to_severity = {
        PoolHealthStatus.EXHAUSTED: AlertSeverity.CRITICAL,
        PoolHealthStatus.CRITICAL: AlertSeverity.ERROR,
        PoolHealthStatus.WARNING: AlertSeverity.WARNING,
        PoolHealthStatus.HEALTHY: AlertSeverity.INFO,
    }
    
    return status_to_severity.get(health_check.health_status, AlertSeverity.WARNING)


def _build_alert_data(health_check, severity: AlertSeverity) -> Dict[str, Any]:
    """Build alert data structure."""
    return {
        "timestamp": health_check.timestamp.isoformat(),
        "severity": severity.value,
        "pool_type": health_check.pool_type,
        "health_status": health_check.health_status.value,
        "utilization_percent": health_check.utilization_percent,
        "warnings": health_check.warnings,
        "recommendations": health_check.recommendations,
        "metrics": {
            "active_connections": health_check.metrics.active_connections,
            "idle_connections": health_check.metrics.idle_connections,
            "overflow_connections": health_check.metrics.overflow_connections,
            "total_connections": health_check.metrics.total_connections,
            "max_connections": health_check.metrics.max_connections,
            "pool_size": health_check.metrics.pool_size,
            "max_overflow": health_check.metrics.max_overflow,
        }
    }


# ============================================================================
# Slack Alerts
# ============================================================================

async def _send_slack_alert(alert_data: Dict[str, Any]) -> bool:
    """Send alert to Slack."""
    if not AlertConfig.SLACK_WEBHOOK_URL:
        logger.debug("Slack webhook URL not configured")
        return False
    
    # Build Slack message
    severity_emoji = {
        AlertSeverity.INFO: ":information_source:",
        AlertSeverity.WARNING: ":warning:",
        AlertSeverity.ERROR: ":x:",
        AlertSeverity.CRITICAL: ":rotating_light:",
    }
    
    emoji = severity_emoji.get(AlertSeverity(alert_data["severity"]), ":warning:")
    
    message = {
        "channel": AlertConfig.SLACK_CHANNEL,
        "username": "Connection Pool Monitor",
        "icon_emoji": ":database:",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Connection Pool Alert: {alert_data['health_status'].upper()}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Pool Type:*\n{alert_data['pool_type']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Utilization:*\n{alert_data['utilization_percent']:.1f}%"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Active:*\n{alert_data['metrics']['active_connections']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Idle:*\n{alert_data['metrics']['idle_connections']}"
                    }
                ]
            }
        ]
    }
    
    # Add warnings
    if alert_data["warnings"]:
        message["blocks"].append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Warnings:*\n" + "\n".join(f"• {w}" for w in alert_data["warnings"])
            }
        })
    
    # Add recommendations
    if alert_data["recommendations"]:
        message["blocks"].append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Recommendations:*\n" + "\n".join(f"• {r}" for r in alert_data["recommendations"])
            }
        })
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                AlertConfig.SLACK_WEBHOOK_URL,
                json=message,
                timeout=10.0
            )
            
            if response.status_code == 200:
                logger.info("Slack alert sent successfully")
                return True
            else:
                logger.error(f"Slack alert failed: {response.status_code} {response.text}")
                return False
    
    except Exception as e:
        logger.error(f"Error sending Slack alert: {e}", exc_info=True)
        return False


# ============================================================================
# PagerDuty Alerts
# ============================================================================

async def _send_pagerduty_alert(alert_data: Dict[str, Any]) -> bool:
    """Send alert to PagerDuty."""
    if not AlertConfig.PAGERDUTY_API_KEY or not AlertConfig.PAGERDUTY_SERVICE_ID:
        logger.debug("PagerDuty credentials not configured")
        return False
    
    # Build PagerDuty event
    event = {
        "routing_key": AlertConfig.PAGERDUTY_SERVICE_ID,
        "event_action": "trigger",
        "dedup_key": f"pool_{alert_data['pool_type']}_{alert_data['health_status']}",
        "payload": {
            "summary": (
                f"Connection Pool {alert_data['health_status'].upper()}: "
                f"{alert_data['pool_type']} pool at {alert_data['utilization_percent']:.1f}%"
            ),
            "severity": alert_data["severity"],
            "source": "connection-pool-monitor",
            "timestamp": alert_data["timestamp"],
            "custom_details": alert_data
        }
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://events.pagerduty.com/v2/enqueue",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Token token={AlertConfig.PAGERDUTY_API_KEY}"
                },
                json=event,
                timeout=10.0
            )
            
            if response.status_code in [200, 202]:
                logger.info("PagerDuty alert sent successfully")
                return True
            else:
                logger.error(f"PagerDuty alert failed: {response.status_code} {response.text}")
                return False
    
    except Exception as e:
        logger.error(f"Error sending PagerDuty alert: {e}", exc_info=True)
        return False


# ============================================================================
# Email Alerts
# ============================================================================

async def _send_email_alert(alert_data: Dict[str, Any]) -> bool:
    """Send alert via email."""
    if not AlertConfig.EMAIL_SMTP_HOST or not AlertConfig.EMAIL_TO:
        logger.debug("Email configuration not complete")
        return False
    
    try:
        import aiosmtplib
        from email.message import EmailMessage
        
        # Build email
        msg = EmailMessage()
        msg["Subject"] = (
            f"[{alert_data['severity'].upper()}] Connection Pool Alert: "
            f"{alert_data['pool_type']} {alert_data['health_status']}"
        )
        msg["From"] = AlertConfig.EMAIL_FROM
        msg["To"] = ", ".join(AlertConfig.EMAIL_TO)
        
        body = f"""
Connection Pool Health Alert

Pool Type: {alert_data['pool_type']}
Health Status: {alert_data['health_status'].upper()}
Utilization: {alert_data['utilization_percent']:.1f}%
Timestamp: {alert_data['timestamp']}

Metrics:
- Active Connections: {alert_data['metrics']['active_connections']}
- Idle Connections: {alert_data['metrics']['idle_connections']}
- Overflow Connections: {alert_data['metrics']['overflow_connections']}
- Total / Max: {alert_data['metrics']['total_connections']} / {alert_data['metrics']['max_connections']}

Warnings:
{chr(10).join(f'- {w}' for w in alert_data['warnings'])}

Recommendations:
{chr(10).join(f'- {r}' for r in alert_data['recommendations'])}
"""
        
        msg.set_content(body)
        
        # Send email
        await aiosmtplib.send(
            msg,
            hostname=AlertConfig.EMAIL_SMTP_HOST,
            port=AlertConfig.EMAIL_SMTP_PORT,
            start_tls=True
        )
        
        logger.info(f"Email alert sent to {AlertConfig.EMAIL_TO}")
        return True
    
    except ImportError:
        logger.warning("aiosmtplib not installed, cannot send email alerts")
        return False
    except Exception as e:
        logger.error(f"Error sending email alert: {e}", exc_info=True)
        return False


# ============================================================================
# Webhook Alerts
# ============================================================================

async def _send_webhook_alert(alert_data: Dict[str, Any]) -> bool:
    """Send alert to custom webhook."""
    if not AlertConfig.WEBHOOK_URL:
        logger.debug("Webhook URL not configured")
        return False
    
    try:
        headers = {"Content-Type": "application/json"}
        if AlertConfig.WEBHOOK_AUTH_TOKEN:
            headers["Authorization"] = f"Bearer {AlertConfig.WEBHOOK_AUTH_TOKEN}"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                AlertConfig.WEBHOOK_URL,
                headers=headers,
                json=alert_data,
                timeout=10.0
            )
            
            if response.status_code in [200, 201, 202]:
                logger.info("Webhook alert sent successfully")
                return True
            else:
                logger.error(f"Webhook alert failed: {response.status_code} {response.text}")
                return False
    
    except Exception as e:
        logger.error(f"Error sending webhook alert: {e}", exc_info=True)
        return False


# ============================================================================
# Log Alerts
# ============================================================================

def _send_log_alert(alert_data: Dict[str, Any]) -> bool:
    """Log alert to application logs."""
    severity = AlertSeverity(alert_data["severity"])
    
    message = (
        f"POOL ALERT [{alert_data['pool_type']}]: {alert_data['health_status']} "
        f"({alert_data['utilization_percent']:.1f}% utilized) - "
        f"Active: {alert_data['metrics']['active_connections']}, "
        f"Idle: {alert_data['metrics']['idle_connections']}"
    )
    
    if severity == AlertSeverity.CRITICAL:
        logger.critical(message)
    elif severity == AlertSeverity.ERROR:
        logger.error(message)
    elif severity == AlertSeverity.WARNING:
        logger.warning(message)
    else:
        logger.info(message)
    
    # Log warnings and recommendations
    for warning in alert_data["warnings"]:
        logger.warning(f"  Warning: {warning}")
    
    for rec in alert_data["recommendations"]:
        logger.info(f"  Recommendation: {rec}")
    
    return True

