"""
GA4 API Quota Manager.

Implements Task 15: Tenant-Aware Quota Management System [P1 - HIGH]

Per-tenant GA4 API quota tracking and enforcement with:
- Hourly and daily quota windows
- Graceful degradation when limits reached
- Admin monitoring and analytics
- Automatic quota reset

Google Analytics Data API Limits (as of 2024):
- 50 requests per hour per property
- 200 requests per day per property
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from uuid import UUID
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from .exceptions import GA4QuotaExceededError, GA4RateLimitError

logger = logging.getLogger(__name__)


class QuotaUsage(BaseModel):
    """Quota usage information for a specific window."""
    
    requests_made: int = Field(..., ge=0)
    requests_limit: int = Field(..., gt=0)
    requests_remaining: int = Field(..., ge=0)
    window_start: datetime
    window_end: datetime
    utilization_percent: float = Field(..., ge=0.0, le=100.0)
    
    @property
    def is_exhausted(self) -> bool:
        """Check if quota is exhausted."""
        return self.requests_remaining <= 0
    
    @property
    def is_near_limit(self, threshold: float = 0.8) -> bool:
        """Check if quota utilization is near limit (default: 80%)."""
        return self.utilization_percent >= (threshold * 100)


class GA4QuotaManager:
    """
    Per-tenant GA4 API quota tracking and enforcement.
    
    Features:
    - Hourly and daily quota tracking
    - Automatic quota window management
    - Request logging for audit
    - Graceful degradation with informative errors
    
    Default Limits (Google Analytics Data API):
    - HOURLY_LIMIT: 50 requests per hour
    - DAILY_LIMIT: 200 requests per day
    
    Example:
        >>> manager = GA4QuotaManager(
        ...     db_session=session,
        ...     tenant_id=UUID("..."),
        ...     property_id="123456789"
        ... )
        >>> # Check if quota available
        >>> await manager.acquire_quota(requests=1)
        >>> # Get current usage
        >>> usage = await manager.get_quota_usage(window_type="hourly")
        >>> print(f"Used: {usage.requests_made}/{usage.requests_limit}")
    """
    
    # Default quota limits (can be overridden per tenant)
    HOURLY_LIMIT = 50
    DAILY_LIMIT = 200
    
    def __init__(
        self,
        db_session: AsyncSession,
        tenant_id: UUID,
        property_id: str,
        hourly_limit: Optional[int] = None,
        daily_limit: Optional[int] = None,
    ):
        """
        Initialize quota manager.
        
        Args:
            db_session: Database session
            tenant_id: Tenant UUID
            property_id: GA4 property ID
            hourly_limit: Optional custom hourly limit (default: 50)
            daily_limit: Optional custom daily limit (default: 200)
        """
        self.db = db_session
        self.tenant_id = tenant_id
        self.property_id = property_id
        self.hourly_limit = hourly_limit or self.HOURLY_LIMIT
        self.daily_limit = daily_limit or self.DAILY_LIMIT
        self._lock = asyncio.Lock()
    
    async def acquire_quota(self, requests: int = 1) -> None:
        """
        Acquire quota tokens for GA4 API calls.
        
        This method checks both hourly and daily quotas and increments
        usage counters if quota is available.
        
        Args:
            requests: Number of requests to acquire quota for (default: 1)
            
        Raises:
            GA4RateLimitError: If hourly limit reached (includes reset time)
            GA4QuotaExceededError: If daily limit reached
            
        Example:
            >>> try:
            ...     await manager.acquire_quota(requests=1)
            ...     # Make GA4 API call
            ... except GA4RateLimitError as e:
            ...     print(f"Rate limited. Retry after {e.retry_after} seconds")
            ... except GA4QuotaExceededError:
            ...     print("Daily quota exhausted. Try again tomorrow")
        """
        async with self._lock:
            # Check hourly quota
            hourly_usage = await self.get_quota_usage(window_type="hourly")
            if hourly_usage.requests_remaining < requests:
                seconds_until_reset = int((hourly_usage.window_end - datetime.utcnow()).total_seconds())
                logger.warning(
                    f"Hourly quota exceeded for tenant {self.tenant_id}, property {self.property_id}. "
                    f"Reset in {seconds_until_reset} seconds"
                )
                raise GA4RateLimitError(
                    f"Hourly quota limit reached ({hourly_usage.requests_made}/{hourly_usage.requests_limit}). "
                    f"Resets at {hourly_usage.window_end.isoformat()}",
                    retry_after=seconds_until_reset
                )
            
            # Check daily quota
            daily_usage = await self.get_quota_usage(window_type="daily")
            if daily_usage.requests_remaining < requests:
                logger.error(
                    f"Daily quota exceeded for tenant {self.tenant_id}, property {self.property_id}"
                )
                raise GA4QuotaExceededError(
                    f"Daily quota limit reached ({daily_usage.requests_made}/{daily_usage.requests_limit}). "
                    f"Resets at {daily_usage.window_end.isoformat()}"
                )
            
            # Increment quota usage
            await self._increment_usage(requests=requests, window_type="hourly")
            await self._increment_usage(requests=requests, window_type="daily")
            
            logger.info(
                f"Quota acquired: tenant={self.tenant_id}, property={self.property_id}, "
                f"requests={requests}, hourly={hourly_usage.requests_made + requests}/{hourly_usage.requests_limit}, "
                f"daily={daily_usage.requests_made + requests}/{daily_usage.requests_limit}"
            )
    
    async def get_quota_usage(self, window_type: str = "hourly") -> QuotaUsage:
        """
        Get current quota usage for a specific window.
        
        Args:
            window_type: Type of quota window ("hourly" or "daily")
            
        Returns:
            QuotaUsage object with current usage information
            
        Example:
            >>> hourly = await manager.get_quota_usage("hourly")
            >>> print(f"Hourly: {hourly.requests_made}/{hourly.requests_limit}")
            >>> daily = await manager.get_quota_usage("daily")
            >>> print(f"Daily: {daily.requests_made}/{daily.requests_limit}")
        """
        result = await self.db.execute(
            text("""
                SELECT * FROM get_current_quota_usage(
                    :tenant_id,
                    :property_id,
                    :window_type
                )
            """),
            {
                "tenant_id": self.tenant_id,
                "property_id": self.property_id,
                "window_type": window_type,
            }
        )
        
        row = result.fetchone()
        if not row:
            # Return default empty usage
            now = datetime.utcnow()
            if window_type == "hourly":
                window_start = now.replace(minute=0, second=0, microsecond=0)
                window_end = window_start + timedelta(hours=1)
                limit = self.hourly_limit
            else:  # daily
                window_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                window_end = window_start + timedelta(days=1)
                limit = self.daily_limit
            
            return QuotaUsage(
                requests_made=0,
                requests_limit=limit,
                requests_remaining=limit,
                window_start=window_start,
                window_end=window_end,
                utilization_percent=0.0,
            )
        
        return QuotaUsage(
            requests_made=row[0],
            requests_limit=row[1],
            requests_remaining=row[2],
            window_start=row[3],
            window_end=row[4],
            utilization_percent=row[5],
        )
    
    async def _increment_usage(self, requests: int, window_type: str) -> None:
        """
        Increment quota usage counter.
        
        Args:
            requests: Number of requests to add
            window_type: Type of quota window ("hourly" or "daily")
        """
        now = datetime.utcnow()
        
        # Calculate window boundaries
        if window_type == "hourly":
            window_start = now.replace(minute=0, second=0, microsecond=0)
            window_end = window_start + timedelta(hours=1)
            limit = self.hourly_limit
        else:  # daily
            window_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            window_end = window_start + timedelta(days=1)
            limit = self.daily_limit
        
        # Upsert quota usage record
        await self.db.execute(
            text("""
                INSERT INTO ga4_api_quota_usage (
                    tenant_id,
                    property_id,
                    quota_window_start,
                    quota_window_end,
                    window_type,
                    requests_made,
                    requests_limit,
                    last_request_at
                )
                VALUES (
                    :tenant_id,
                    :property_id,
                    :window_start,
                    :window_end,
                    :window_type,
                    :requests,
                    :limit,
                    :now
                )
                ON CONFLICT (tenant_id, property_id, quota_window_start, window_type)
                DO UPDATE SET
                    requests_made = ga4_api_quota_usage.requests_made + :requests,
                    last_request_at = :now,
                    updated_at = :now
            """),
            {
                "tenant_id": self.tenant_id,
                "property_id": self.property_id,
                "window_start": window_start,
                "window_end": window_end,
                "window_type": window_type,
                "requests": requests,
                "limit": limit,
                "now": now,
            }
        )
        
        await self.db.commit()
    
    async def log_request(
        self,
        request_type: str,
        status: str,
        dimensions: Optional[list] = None,
        metrics: Optional[list] = None,
        date_range: Optional[Dict[str, str]] = None,
        response_time_ms: Optional[int] = None,
        error_message: Optional[str] = None,
        user_id: Optional[UUID] = None,
    ) -> None:
        """
        Log GA4 API request for audit and monitoring.
        
        Args:
            request_type: Type of GA4 API request (e.g., "runReport")
            status: Request status ("success", "error", "rate_limited", "quota_exceeded")
            dimensions: List of dimensions requested
            metrics: List of metrics requested
            date_range: Date range for the request
            response_time_ms: Response time in milliseconds
            error_message: Error message if request failed
            user_id: Optional user ID who made the request
            
        Example:
            >>> await manager.log_request(
            ...     request_type="runReport",
            ...     status="success",
            ...     dimensions=["date", "deviceCategory"],
            ...     metrics=["sessions", "conversions"],
            ...     date_range={"start": "2026-01-01", "end": "2026-01-07"},
            ...     response_time_ms=234
            ... )
        """
        await self.db.execute(
            text("""
                INSERT INTO ga4_api_request_log (
                    tenant_id,
                    property_id,
                    user_id,
                    request_type,
                    dimensions,
                    metrics,
                    date_range,
                    status,
                    response_time_ms,
                    error_message
                )
                VALUES (
                    :tenant_id,
                    :property_id,
                    :user_id,
                    :request_type,
                    :dimensions,
                    :metrics,
                    :date_range,
                    :status,
                    :response_time_ms,
                    :error_message
                )
            """),
            {
                "tenant_id": self.tenant_id,
                "property_id": self.property_id,
                "user_id": user_id,
                "request_type": request_type,
                "dimensions": dimensions or [],
                "metrics": metrics or [],
                "date_range": date_range,
                "status": status,
                "response_time_ms": response_time_ms,
                "error_message": error_message,
            }
        )
        
        await self.db.commit()
    
    async def get_usage_stats(
        self,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get quota usage statistics for the past N days.
        
        Args:
            days: Number of days to include in stats (default: 7)
            
        Returns:
            Dictionary with usage statistics
            
        Example:
            >>> stats = await manager.get_usage_stats(days=7)
            >>> print(f"Total requests: {stats['total_requests']}")
            >>> print(f"Average daily: {stats['avg_daily_requests']}")
        """
        result = await self.db.execute(
            text("""
                SELECT 
                    COUNT(*) as total_requests,
                    COUNT(DISTINCT DATE(requested_at)) as active_days,
                    AVG(response_time_ms) as avg_response_time_ms,
                    MAX(response_time_ms) as max_response_time_ms,
                    COUNT(*) FILTER (WHERE status = 'success') as successful_requests,
                    COUNT(*) FILTER (WHERE status = 'error') as failed_requests,
                    COUNT(*) FILTER (WHERE status = 'rate_limited') as rate_limited_requests,
                    COUNT(*) FILTER (WHERE status = 'quota_exceeded') as quota_exceeded_requests
                FROM ga4_api_request_log
                WHERE tenant_id = :tenant_id
                AND property_id = :property_id
                AND requested_at >= NOW() - INTERVAL ':days days'
            """),
            {
                "tenant_id": self.tenant_id,
                "property_id": self.property_id,
                "days": days,
            }
        )
        
        row = result.fetchone()
        if not row:
            return {
                "total_requests": 0,
                "active_days": 0,
                "avg_daily_requests": 0,
                "avg_response_time_ms": 0,
                "max_response_time_ms": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "rate_limited_requests": 0,
                "quota_exceeded_requests": 0,
                "success_rate": 0.0,
            }
        
        total_requests = row[0]
        active_days = row[1]
        
        return {
            "total_requests": total_requests,
            "active_days": active_days,
            "avg_daily_requests": total_requests / active_days if active_days > 0 else 0,
            "avg_response_time_ms": row[2] or 0,
            "max_response_time_ms": row[3] or 0,
            "successful_requests": row[4],
            "failed_requests": row[5],
            "rate_limited_requests": row[6],
            "quota_exceeded_requests": row[7],
            "success_rate": (row[4] / total_requests * 100) if total_requests > 0 else 0.0,
        }


# Convenience function for cleanup job
async def cleanup_old_quota_records(
    db_session: AsyncSession,
    retention_days: int = 30
) -> int:
    """
    Cleanup old quota records.
    
    Should be called periodically (e.g., daily via cron job).
    
    Args:
        db_session: Database session
        retention_days: Number of days to retain records (default: 30)
        
    Returns:
        Number of records deleted
    """
    result = await db_session.execute(
        text("SELECT cleanup_old_quota_records(:retention_days)"),
        {"retention_days": retention_days}
    )
    
    deleted_count = result.scalar_one()
    await db_session.commit()
    
    logger.info(f"Cleaned up {deleted_count} old quota records (retention: {retention_days} days)")
    return deleted_count

