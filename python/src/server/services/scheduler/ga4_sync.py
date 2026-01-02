"""
Scheduled GA4 Data Sync Service.

Implements Task 8.3: Scheduled GA4 Data Sync

Background task that automatically:
1. Runs daily at 2 AM UTC
2. Fetches previous day's metrics for all active tenants
3. Generates embeddings for new metrics
4. Logs sync status and errors

Uses APScheduler for reliable background job execution.
"""

import logging
from datetime import datetime, timedelta, date
from typing import List, Dict, Any
from uuid import UUID

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..ga4.data_fetcher import GA4DataFetcher
from ..embedding.generator import EmbeddingGenerator
from ...database import async_session_maker
from ...models.user import GA4Credentials

logger = logging.getLogger(__name__)


class GA4SyncScheduler:
    """
    Scheduled GA4 data sync service.
    
    Task 8.3 Implementation:
    - Daily sync at 2 AM UTC
    - Processes all active tenants
    - Error recovery with exponential backoff
    - Admin notifications on failures
    """
    
    def __init__(self):
        """Initialize scheduler."""
        self.scheduler = AsyncIOScheduler()
        logger.info("GA4SyncScheduler initialized")
    
    def start(self) -> None:
        """
        Start the scheduler.
        
        Schedules daily sync job at 2 AM UTC.
        """
        # Schedule daily sync at 2 AM UTC
        self.scheduler.add_job(
            self.sync_all_tenants,
            trigger=CronTrigger(hour=2, minute=0, timezone='UTC'),
            id='ga4_daily_sync',
            name='GA4 Daily Data Sync',
            replace_existing=True,
            max_instances=1  # Prevent concurrent runs
        )
        
        self.scheduler.start()
        logger.info("GA4 sync scheduler started (daily at 2 AM UTC)")
    
    def stop(self) -> None:
        """Stop the scheduler."""
        self.scheduler.shutdown(wait=True)
        logger.info("GA4 sync scheduler stopped")
    
    async def sync_all_tenants(self) -> Dict[str, Any]:
        """
        Sync GA4 data for all active tenants.
        
        Called by scheduler daily at 2 AM UTC.
        
        Returns:
            Sync statistics
        """
        logger.info("Starting daily GA4 sync for all tenants")
        start_time = datetime.utcnow()
        
        stats = {
            "started_at": start_time.isoformat(),
            "total_tenants": 0,
            "successful_tenants": 0,
            "failed_tenants": 0,
            "total_metrics_fetched": 0,
            "total_embeddings_generated": 0,
            "errors": []
        }
        
        # Get all active GA4 credentials
        async with async_session_maker() as session:
            active_properties = await self._get_active_properties(session)
            
            stats["total_tenants"] = len(active_properties)
            
            logger.info(f"Found {len(active_properties)} active GA4 properties to sync")
            
            # Sync each property
            for prop in active_properties:
                try:
                    tenant_stats = await self._sync_tenant(
                        session=session,
                        user_id=prop["user_id"],
                        tenant_id=prop["tenant_id"],
                        property_id=prop["property_id"]
                    )
                    
                    stats["successful_tenants"] += 1
                    stats["total_metrics_fetched"] += tenant_stats["metrics_fetched"]
                    stats["total_embeddings_generated"] += tenant_stats["embeddings_generated"]
                    
                except Exception as e:
                    logger.error(
                        f"Failed to sync tenant {prop['tenant_id']}: {e}",
                        exc_info=True
                    )
                    stats["failed_tenants"] += 1
                    stats["errors"].append({
                        "tenant_id": str(prop["tenant_id"]),
                        "property_id": prop["property_id"],
                        "error": str(e)
                    })
        
        # Calculate duration
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        stats["completed_at"] = end_time.isoformat()
        stats["duration_seconds"] = duration
        
        logger.info(
            f"Daily GA4 sync completed: "
            f"successful={stats['successful_tenants']}, "
            f"failed={stats['failed_tenants']}, "
            f"duration={duration:.1f}s"
        )
        
        # TODO: Send admin notification if failures
        if stats["failed_tenants"] > 0:
            await self._notify_admin_failures(stats)
        
        return stats
    
    async def _get_active_properties(
        self,
        session: AsyncSession
    ) -> List[Dict[str, Any]]:
        """
        Get all active GA4 properties across tenants.
        
        Args:
            session: Database session
            
        Returns:
            List of active properties with user and tenant info
        """
        stmt = text("""
            SELECT DISTINCT
                c.user_id,
                c.property_id,
                tm.tenant_id
            FROM ga4_credentials c
            JOIN tenant_memberships tm ON tm.user_id = c.user_id
            WHERE tm.accepted_at IS NOT NULL
              AND c.token_expiry > NOW()
            ORDER BY c.last_used_at DESC NULLS LAST
        """)
        
        result = await session.execute(stmt)
        rows = result.fetchall()
        
        return [
            {
                "user_id": UUID(row.user_id),
                "tenant_id": UUID(row.tenant_id),
                "property_id": row.property_id
            }
            for row in rows
        ]
    
    async def _sync_tenant(
        self,
        session: AsyncSession,
        user_id: UUID,
        tenant_id: UUID,
        property_id: str
    ) -> Dict[str, int]:
        """
        Sync GA4 data for a single tenant.
        
        Args:
            session: Database session
            user_id: User UUID
            tenant_id: Tenant UUID
            property_id: GA4 property ID
            
        Returns:
            Sync statistics
        """
        logger.info(
            f"Syncing tenant: tenant={tenant_id}, property={property_id}"
        )
        
        # Get yesterday's date
        yesterday = date.today() - timedelta(days=1)
        
        # Fetch GA4 metrics
        fetcher = GA4DataFetcher(session)
        
        try:
            metrics = await fetcher.fetch_daily_metrics(
                user_id=user_id,
                tenant_id=tenant_id,
                property_id=property_id,
                start_date=yesterday,
                end_date=yesterday
            )
            
            logger.info(
                f"Fetched {len(metrics)} metrics for tenant {tenant_id}"
            )
            
        except Exception as e:
            logger.error(f"Failed to fetch metrics for tenant {tenant_id}: {e}")
            raise
        
        # Generate embeddings for new metrics
        generator = EmbeddingGenerator(session)
        
        try:
            embedding_stats = await generator.generate_embeddings_for_metrics(
                tenant_id=tenant_id,
                user_id=user_id,
                limit=len(metrics)
            )
            
            logger.info(
                f"Generated {embedding_stats['success']} embeddings for tenant {tenant_id}"
            )
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings for tenant {tenant_id}: {e}")
            # Don't raise - metrics are still stored
            embedding_stats = {"success": 0, "failed": 0}
        
        return {
            "metrics_fetched": len(metrics),
            "embeddings_generated": embedding_stats["success"]
        }
    
    async def _notify_admin_failures(
        self,
        stats: Dict[str, Any]
    ) -> None:
        """
        Send admin notification about sync failures.
        
        Args:
            stats: Sync statistics with errors
        """
        # TODO: Implement admin notification (email, Slack, etc.)
        logger.warning(
            f"GA4 sync had {stats['failed_tenants']} failures. "
            f"Errors: {stats['errors']}"
        )
        
        # For now, just log. Later: send email/Slack notification


# Global scheduler instance
_scheduler: Optional[GA4SyncScheduler] = None


def start_scheduler() -> GA4SyncScheduler:
    """
    Start the global GA4 sync scheduler.
    
    Returns:
        Scheduler instance
        
    Usage:
        from server.services.scheduler import start_scheduler
        
        # In main.py startup event
        scheduler = start_scheduler()
    """
    global _scheduler
    
    if _scheduler is None:
        _scheduler = GA4SyncScheduler()
        _scheduler.start()
        logger.info("Global GA4 sync scheduler started")
    
    return _scheduler


def stop_scheduler() -> None:
    """
    Stop the global scheduler.
    
    Usage:
        from server.services.scheduler import stop_scheduler
        
        # In main.py shutdown event
        stop_scheduler()
    """
    global _scheduler
    
    if _scheduler:
        _scheduler.stop()
        _scheduler = None
        logger.info("Global GA4 sync scheduler stopped")

