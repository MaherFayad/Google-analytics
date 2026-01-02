"""
GA4 Partition Manager

Provides Python utilities for managing GA4 events table partitions.
Integrates with PostgreSQL partition functions for automated maintenance.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PartitionInfo:
    """Represents information about a table partition"""
    
    def __init__(
        self,
        name: str,
        row_count: int,
        size_bytes: int,
        size_pretty: str,
        date_range_start: datetime,
        date_range_end: datetime
    ):
        self.name = name
        self.row_count = row_count
        self.size_bytes = size_bytes
        self.size_pretty = size_pretty
        self.date_range_start = date_range_start
        self.date_range_end = date_range_end
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "name": self.name,
            "row_count": self.row_count,
            "size_bytes": self.size_bytes,
            "size_pretty": self.size_pretty,
            "date_range_start": self.date_range_start.isoformat() if self.date_range_start else None,
            "date_range_end": self.date_range_end.isoformat() if self.date_range_end else None,
        }


class GA4PartitionManager:
    """
    Manages GA4 events table partitions.
    
    Features:
    - Create new monthly partitions
    - Drop old partitions based on retention policy
    - Get partition statistics
    - Ensure future partitions exist
    """
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
    
    async def create_partition(self, partition_date: datetime) -> str:
        """
        Create a new monthly partition for the given date.
        
        Args:
            partition_date: Date within the month for which to create partition
            
        Returns:
            Status message indicating success or if partition already exists
            
        Example:
            >>> manager = GA4PartitionManager(db_session)
            >>> result = await manager.create_partition(datetime(2026, 5, 1))
            >>> print(result)
            'Successfully created partition archon_ga4_events_2026_05 for date range 2026-05-01 to 2026-06-01'
        """
        try:
            result = await self.db.execute(
                text("SELECT create_ga4_events_partition(:partition_date)"),
                {"partition_date": partition_date.date()}
            )
            message = result.scalar_one()
            logger.info(f"Partition creation: {message}")
            return message
        except Exception as e:
            logger.error(f"Failed to create partition for {partition_date}: {e}")
            raise
    
    async def ensure_partitions_exist(self, months_ahead: int = 3) -> List[Dict[str, str]]:
        """
        Ensure partitions exist for current month + N months ahead.
        
        Args:
            months_ahead: Number of future months to create partitions for
            
        Returns:
            List of dictionaries with partition names and status messages
            
        Example:
            >>> manager = GA4PartitionManager(db_session)
            >>> results = await manager.ensure_partitions_exist(3)
            >>> for result in results:
            ...     print(f"{result['partition_name']}: {result['status']}")
        """
        try:
            result = await self.db.execute(
                text("SELECT * FROM ensure_ga4_partitions_exist(:months_ahead)"),
                {"months_ahead": months_ahead}
            )
            rows = result.fetchall()
            
            partitions = [
                {"partition_name": row[0], "status": row[1]}
                for row in rows
            ]
            
            logger.info(f"Ensured {len(partitions)} partitions exist (current + {months_ahead} months ahead)")
            return partitions
        except Exception as e:
            logger.error(f"Failed to ensure partitions exist: {e}")
            raise
    
    async def drop_old_partitions(self, retention_months: int = 24) -> List[Dict[str, str]]:
        """
        Drop partitions older than the retention period.
        
        Args:
            retention_months: Number of months to retain data (default: 24 months)
            
        Returns:
            List of dictionaries with partition names and status messages
            
        Example:
            >>> manager = GA4PartitionManager(db_session)
            >>> dropped = await manager.drop_old_partitions(retention_months=12)
            >>> for partition in dropped:
            ...     print(f"Dropped: {partition['partition_name']}")
        """
        try:
            result = await self.db.execute(
                text("SELECT * FROM drop_old_ga4_partitions(:retention_months)"),
                {"retention_months": retention_months}
            )
            rows = result.fetchall()
            
            dropped = [
                {"partition_name": row[0], "status": row[1]}
                for row in rows
            ]
            
            logger.info(f"Partition cleanup: {len(dropped)} partitions processed")
            return dropped
        except Exception as e:
            logger.error(f"Failed to drop old partitions: {e}")
            raise
    
    async def get_partition_stats(self) -> List[PartitionInfo]:
        """
        Get statistics for all GA4 events partitions.
        
        Returns:
            List of PartitionInfo objects with row counts, sizes, and date ranges
            
        Example:
            >>> manager = GA4PartitionManager(db_session)
            >>> stats = await manager.get_partition_stats()
            >>> for partition in stats:
            ...     print(f"{partition.name}: {partition.row_count} rows, {partition.size_pretty}")
        """
        try:
            result = await self.db.execute(
                text("SELECT * FROM get_ga4_partition_stats()")
            )
            rows = result.fetchall()
            
            partitions = [
                PartitionInfo(
                    name=row[0],
                    row_count=row[1],
                    size_bytes=row[2],
                    size_pretty=row[3],
                    date_range_start=row[4],
                    date_range_end=row[5]
                )
                for row in rows
            ]
            
            logger.info(f"Retrieved statistics for {len(partitions)} partitions")
            return partitions
        except Exception as e:
            logger.error(f"Failed to get partition stats: {e}")
            raise
    
    async def get_total_events_count(self, tenant_id: Optional[str] = None) -> int:
        """
        Get total count of events across all partitions.
        
        Args:
            tenant_id: Optional tenant ID to filter by
            
        Returns:
            Total count of events
        """
        try:
            if tenant_id:
                result = await self.db.execute(
                    text("""
                        SELECT COUNT(*) FROM archon_ga4_events 
                        WHERE tenant_id = :tenant_id
                    """),
                    {"tenant_id": tenant_id}
                )
            else:
                result = await self.db.execute(
                    text("SELECT COUNT(*) FROM archon_ga4_events")
                )
            
            count = result.scalar_one()
            return count
        except Exception as e:
            logger.error(f"Failed to get total events count: {e}")
            raise
    
    async def get_partition_for_date(self, target_date: datetime) -> Optional[str]:
        """
        Get the partition name that should contain data for a given date.
        
        Args:
            target_date: Date to find partition for
            
        Returns:
            Partition name (e.g., 'archon_ga4_events_2026_01') or None if not found
        """
        partition_name = f"archon_ga4_events_{target_date.strftime('%Y_%m')}"
        
        try:
            result = await self.db.execute(
                text("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_class 
                        WHERE relname = :partition_name
                    )
                """),
                {"partition_name": partition_name}
            )
            exists = result.scalar_one()
            
            return partition_name if exists else None
        except Exception as e:
            logger.error(f"Failed to check partition existence: {e}")
            raise
    
    async def maintenance_routine(
        self,
        ensure_future_months: int = 3,
        retention_months: int = 24
    ) -> Dict[str, Any]:
        """
        Run full partition maintenance routine.
        
        This should be called periodically (e.g., monthly via cron job):
        1. Ensure future partitions exist
        2. Drop old partitions beyond retention period
        3. Get current statistics
        
        Args:
            ensure_future_months: Number of future months to prepare partitions for
            retention_months: Number of months to retain historical data
            
        Returns:
            Dictionary with maintenance results
            
        Example:
            >>> manager = GA4PartitionManager(db_session)
            >>> results = await manager.maintenance_routine()
            >>> print(f"Created: {len(results['created_partitions'])}")
            >>> print(f"Dropped: {len(results['dropped_partitions'])}")
        """
        logger.info(f"Starting partition maintenance routine")
        
        # Ensure future partitions
        created = await self.ensure_partitions_exist(ensure_future_months)
        
        # Drop old partitions
        dropped = await self.drop_old_partitions(retention_months)
        
        # Get current stats
        stats = await self.get_partition_stats()
        
        # Get total count
        total_events = await self.get_total_events_count()
        
        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "created_partitions": created,
            "dropped_partitions": dropped,
            "current_partitions": [p.to_dict() for p in stats],
            "total_events_count": total_events,
            "retention_policy_months": retention_months,
        }
        
        logger.info(
            f"Partition maintenance completed: "
            f"{len(created)} created, {len(dropped)} dropped, "
            f"{len(stats)} active partitions, {total_events} total events"
        )
        
        return results


# Convenience function for scheduled tasks
async def run_partition_maintenance(db_session: AsyncSession) -> Dict[str, Any]:
    """
    Convenience function to run partition maintenance.
    Can be called from APScheduler or other job schedulers.
    
    Args:
        db_session: SQLAlchemy async session
        
    Returns:
        Maintenance results dictionary
    """
    manager = GA4PartitionManager(db_session)
    return await manager.maintenance_routine()

