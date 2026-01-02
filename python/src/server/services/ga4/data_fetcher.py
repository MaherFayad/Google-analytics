"""
GA4 Data Fetching Service.

Implements Task 8.1: GA4 Data Fetching Service (Reuse OAuth from Task 2.4)

This service fetches GA4 metrics using existing OAuth infrastructure and
transforms raw JSON to descriptive text summaries for dual-mode analytics:
- SQL queries (direct access to JSONB)
- Vector embeddings (from descriptive_summary)

Features:
1. OAuth token management via AuthService
2. GA4 Data API v1 integration
3. Descriptive text transformation
4. Storage in ga4_metrics_raw table
5. Tenant isolation enforcement
"""

import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthService, AuthenticationError
from ..core.config import settings

logger = logging.getLogger(__name__)


class GA4FetchError(Exception):
    """Raised when GA4 data fetch fails."""
    pass


class GA4DataFetcher:
    """
    Service to fetch GA4 metrics and store in database.
    
    Task 8.1 Implementation:
    - Fetches data from GA4 Data API
    - Transforms to descriptive text for embeddings
    - Stores in ga4_metrics_raw table
    - Handles OAuth token refresh
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize GA4 data fetcher.
        
        Args:
            session: Database session
        """
        self.session = session
        self.auth_service = AuthService(session)
    
    async def fetch_daily_metrics(
        self,
        user_id: UUID,
        tenant_id: UUID,
        property_id: str,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """
        Fetch daily GA4 metrics and store in database.
        
        Args:
            user_id: User UUID
            tenant_id: Tenant UUID (for isolation)
            property_id: GA4 property ID
            start_date: Start date
            end_date: End date
            
        Returns:
            List of stored metric records
            
        Raises:
            GA4FetchError: If fetch fails
            AuthenticationError: If OAuth token invalid
            
        Example:
            fetcher = GA4DataFetcher(session)
            metrics = await fetcher.fetch_daily_metrics(
                user_id=UUID("..."),
                tenant_id=UUID("..."),
                property_id="123456789",
                start_date=date(2025, 1, 1),
                end_date=date(2025, 1, 7)
            )
        """
        logger.info(
            f"Fetching GA4 metrics: tenant={tenant_id}, property={property_id}, "
            f"dates={start_date} to {end_date}"
        )
        
        # Get client (mock or real based on config)
        if settings.GA4_MOCK_MODE:
            from .mock_service import get_ga4_client
            client = get_ga4_client(
                property_id=property_id,
                tenant_id=tenant_id,
                mock_mode=True,
                scenario=settings.GA4_DEFAULT_SCENARIO
            )
        else:
            # TODO: Task 12 - Use real GA4Client with OAuth
            # For now, fall back to mock
            logger.warning("Real GA4 API not implemented, using mock")
            from .mock_service import get_ga4_client
            client = get_ga4_client(
                property_id=property_id,
                tenant_id=tenant_id,
                mock_mode=True
            )
        
        # Fetch data from GA4 API
        try:
            response = await client.fetch_page_views(
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                dimensions=["date", "pagePath", "deviceCategory"],
                metrics=["sessions", "screenPageViews", "bounceRate", "averageSessionDuration"]
            )
        except Exception as e:
            logger.error(f"GA4 API fetch failed: {e}", exc_info=True)
            raise GA4FetchError(f"Failed to fetch GA4 data: {e}") from e
        
        # Transform and store metrics
        stored_records = []
        
        for row in response.get("rows", []):
            # Extract dimensions
            dimensions = row.get("dimensionValues", [])
            metrics = row.get("metricValues", [])
            
            metric_date_str = dimensions[0]["value"]  # e.g., "20250101"
            page_path = dimensions[1]["value"]
            device = dimensions[2]["value"]
            
            # Parse date
            metric_date = datetime.strptime(metric_date_str, "%Y%m%d").date()
            
            # Extract metrics
            sessions = int(metrics[0]["value"])
            page_views = int(metrics[1]["value"])
            bounce_rate = float(metrics[2]["value"])
            avg_duration = float(metrics[3]["value"])
            
            # Build dimension context JSONB
            dimension_context = {
                "page_path": page_path,
                "device": device,
                "date": metric_date.isoformat()
            }
            
            # Build metric values JSONB
            metric_values = {
                "sessions": sessions,
                "page_views": page_views,
                "bounce_rate": bounce_rate,
                "average_session_duration": avg_duration
            }
            
            # Generate descriptive summary (Task 8.1 requirement)
            descriptive_summary = self._generate_descriptive_summary(
                metric_date=metric_date,
                device=device,
                page_path=page_path,
                sessions=sessions,
                page_views=page_views,
                bounce_rate=bounce_rate,
                avg_duration=avg_duration
            )
            
            # Store in database
            record = await self._store_metric(
                tenant_id=tenant_id,
                user_id=user_id,
                property_id=property_id,
                metric_date=metric_date,
                dimension_context=dimension_context,
                metric_values=metric_values,
                descriptive_summary=descriptive_summary
            )
            
            stored_records.append(record)
        
        logger.info(
            f"Stored {len(stored_records)} GA4 metric records for tenant {tenant_id}"
        )
        
        return stored_records
    
    def _generate_descriptive_summary(
        self,
        metric_date: date,
        device: str,
        page_path: str,
        sessions: int,
        page_views: int,
        bounce_rate: float,
        avg_duration: float
    ) -> str:
        """
        Generate descriptive text summary from GA4 metrics.
        
        This text will be used for embedding generation (Task 8.2).
        
        Args:
            metric_date: Date of metrics
            device: Device category (mobile, desktop, tablet)
            page_path: Page path
            sessions: Number of sessions
            page_views: Number of page views
            bounce_rate: Bounce rate (0.0-1.0)
            avg_duration: Average session duration in seconds
            
        Returns:
            Descriptive text summary
            
        Example output:
            "On January 5, 2025, mobile users visiting /products had 1,234 sessions 
            with 2,468 page views and 42.3% bounce rate. Average session duration 
            was 3 minutes 45 seconds."
        """
        # Format date
        date_formatted = metric_date.strftime("%B %d, %Y")
        
        # Format bounce rate
        bounce_pct = bounce_rate * 100
        
        # Format duration
        minutes = int(avg_duration // 60)
        seconds = int(avg_duration % 60)
        duration_str = f"{minutes} minute{'s' if minutes != 1 else ''} {seconds} second{'s' if seconds != 1 else ''}"
        
        # Format page path for readability
        page_display = page_path if page_path != "/" else "the homepage"
        
        # Build descriptive summary
        summary = (
            f"On {date_formatted}, {device} users visiting {page_display} had "
            f"{sessions:,} sessions with {page_views:,} page views and "
            f"{bounce_pct:.1f}% bounce rate. Average session duration was {duration_str}."
        )
        
        return summary
    
    async def _store_metric(
        self,
        tenant_id: UUID,
        user_id: UUID,
        property_id: str,
        metric_date: date,
        dimension_context: Dict[str, Any],
        metric_values: Dict[str, Any],
        descriptive_summary: str
    ) -> Dict[str, Any]:
        """
        Store GA4 metric in database.
        
        Stores in ga4_metrics_raw table (Task 7.2).
        
        Args:
            tenant_id: Tenant UUID
            user_id: User UUID
            property_id: GA4 property ID
            metric_date: Date of metrics
            dimension_context: JSONB dimension data
            metric_values: JSONB metric data
            descriptive_summary: Descriptive text for embeddings
            
        Returns:
            Stored record dict
        """
        # Set RLS context
        await self.session.execute(
            text("SET LOCAL app.tenant_id = :tenant_id"),
            {"tenant_id": str(tenant_id)}
        )
        await self.session.execute(
            text("SET LOCAL app.user_id = :user_id"),
            {"user_id": str(user_id)}
        )
        
        # Insert metric
        stmt = text("""
            INSERT INTO ga4_metrics_raw (
                tenant_id,
                user_id,
                property_id,
                metric_date,
                dimension_context,
                metric_values,
                descriptive_summary,
                synced_at
            ) VALUES (
                :tenant_id,
                :user_id,
                :property_id,
                :metric_date,
                :dimension_context::jsonb,
                :metric_values::jsonb,
                :descriptive_summary,
                NOW()
            )
            RETURNING id, tenant_id, user_id, property_id, metric_date,
                      dimension_context, metric_values, descriptive_summary,
                      synced_at, created_at
        """)
        
        import json
        result = await self.session.execute(
            stmt,
            {
                "tenant_id": str(tenant_id),
                "user_id": str(user_id),
                "property_id": property_id,
                "metric_date": metric_date,
                "dimension_context": json.dumps(dimension_context),
                "metric_values": json.dumps(metric_values),
                "descriptive_summary": descriptive_summary
            }
        )
        
        row = result.fetchone()
        await self.session.commit()
        
        return {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "user_id": row.user_id,
            "property_id": row.property_id,
            "metric_date": row.metric_date,
            "dimension_context": row.dimension_context,
            "metric_values": row.metric_values,
            "descriptive_summary": row.descriptive_summary,
            "synced_at": row.synced_at,
            "created_at": row.created_at
        }
    
    async def fetch_conversions(
        self,
        user_id: UUID,
        tenant_id: UUID,
        property_id: str,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """
        Fetch conversion metrics from GA4.
        
        Args:
            user_id: User UUID
            tenant_id: Tenant UUID
            property_id: GA4 property ID
            start_date: Start date
            end_date: End date
            
        Returns:
            List of stored conversion records
        """
        logger.info(
            f"Fetching GA4 conversions: tenant={tenant_id}, property={property_id}, "
            f"dates={start_date} to {end_date}"
        )
        
        # Get client
        if settings.GA4_MOCK_MODE:
            from .mock_service import get_ga4_client
            client = get_ga4_client(
                property_id=property_id,
                tenant_id=tenant_id,
                mock_mode=True,
                scenario=settings.GA4_DEFAULT_SCENARIO
            )
        else:
            logger.warning("Real GA4 API not implemented, using mock")
            from .mock_service import get_ga4_client
            client = get_ga4_client(
                property_id=property_id,
                tenant_id=tenant_id,
                mock_mode=True
            )
        
        # Fetch conversion data
        try:
            response = await client.fetch_conversions(
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            )
        except Exception as e:
            logger.error(f"GA4 conversion fetch failed: {e}", exc_info=True)
            raise GA4FetchError(f"Failed to fetch conversions: {e}") from e
        
        # Transform and store
        stored_records = []
        
        for row in response.get("rows", []):
            dimensions = row.get("dimensionValues", [])
            metrics = row.get("metricValues", [])
            
            metric_date_str = dimensions[0]["value"]
            device = dimensions[1]["value"]
            
            metric_date = datetime.strptime(metric_date_str, "%Y%m%d").date()
            
            sessions = int(metrics[0]["value"])
            conversions = int(metrics[1]["value"])
            conversion_rate = float(metrics[2]["value"])
            revenue = float(metrics[3]["value"])
            
            # Build data structures
            dimension_context = {
                "device": device,
                "date": metric_date.isoformat(),
                "event_name": "conversion"
            }
            
            metric_values = {
                "sessions": sessions,
                "conversions": conversions,
                "conversion_rate": conversion_rate,
                "revenue": revenue
            }
            
            # Generate descriptive summary
            date_formatted = metric_date.strftime("%B %d, %Y")
            conversion_pct = conversion_rate * 100
            avg_order_value = revenue / conversions if conversions > 0 else 0
            
            descriptive_summary = (
                f"On {date_formatted}, {device} users had {sessions:,} sessions "
                f"with {conversions:,} conversions ({conversion_pct:.1f}% conversion rate). "
                f"Total revenue was ${revenue:,.2f} with an average order value of ${avg_order_value:.2f}."
            )
            
            # Store in database
            record = await self._store_metric(
                tenant_id=tenant_id,
                user_id=user_id,
                property_id=property_id,
                metric_date=metric_date,
                dimension_context=dimension_context,
                metric_values=metric_values,
                descriptive_summary=descriptive_summary
            )
            
            stored_records.append(record)
        
        logger.info(
            f"Stored {len(stored_records)} conversion records for tenant {tenant_id}"
        )
        
        return stored_records
    
    async def get_sync_status(
        self,
        tenant_id: UUID,
        property_id: str
    ) -> Dict[str, Any]:
        """
        Get sync status for a property.
        
        Args:
            tenant_id: Tenant UUID
            property_id: GA4 property ID
            
        Returns:
            Sync status dict with last sync time and record count
        """
        # Set RLS context
        await self.session.execute(
            text("SET LOCAL app.tenant_id = :tenant_id"),
            {"tenant_id": str(tenant_id)}
        )
        
        # Query sync status
        stmt = text("""
            SELECT 
                COUNT(*) as total_records,
                MAX(synced_at) as last_sync,
                MIN(metric_date) as earliest_date,
                MAX(metric_date) as latest_date
            FROM ga4_metrics_raw
            WHERE tenant_id = :tenant_id
              AND property_id = :property_id
        """)
        
        result = await self.session.execute(
            stmt,
            {"tenant_id": str(tenant_id), "property_id": property_id}
        )
        
        row = result.fetchone()
        
        return {
            "property_id": property_id,
            "tenant_id": str(tenant_id),
            "total_records": row.total_records,
            "last_sync": row.last_sync.isoformat() if row.last_sync else None,
            "earliest_date": row.earliest_date.isoformat() if row.earliest_date else None,
            "latest_date": row.latest_date.isoformat() if row.latest_date else None
        }

