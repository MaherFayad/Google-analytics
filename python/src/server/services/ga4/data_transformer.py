"""
GA4 Data Transformation Pipeline.

Implements Task 14: GA4-Specific Data Transformation Pipeline

Transforms GA4 API responses into vectorizable natural language documents
while preserving raw metrics in JSONB metadata for dual-mode analytics.

Features:
1. Multiple transformation strategies (page views, events, conversions)
2. Aggregation for high-cardinality data
3. Natural language generation
4. JSONB metadata preservation
5. Tenant isolation
"""

import logging
from typing import List, Dict, Any, Literal
from datetime import datetime, date
from uuid import UUID

logger = logging.getLogger(__name__)


class GA4DataTransformer:
    """
    Transforms GA4 event data into vectorizable documents.
    
    Task 14 Implementation:
    - Converts GA4 JSON to natural language
    - Preserves raw metrics in JSONB
    - Aggregates high-cardinality data
    - Generates temporal metadata
    """
    
    TRANSFORMATION_VERSION = "v1.0.0"
    
    def __init__(self):
        """Initialize data transformer."""
        logger.info("GA4DataTransformer initialized")
    
    def transform_page_views_to_documents(
        self,
        ga4_response: Dict[str, Any],
        tenant_id: UUID,
        property_id: str
    ) -> List[Dict[str, Any]]:
        """
        Convert GA4 page views API response into vectorizable documents.
        
        Strategy:
        1. Group by page path
        2. Aggregate metrics (sessions, bounce rate, duration)
        3. Create natural language summary for embedding
        4. Preserve raw metrics in metadata JSONB
        
        Args:
            ga4_response: GA4 API response dict
            tenant_id: Tenant UUID
            property_id: GA4 property ID
            
        Returns:
            List of document dicts ready for embedding
            
        Example output:
            [
                {
                    "content": "The homepage (/) had 12,450 sessions...",
                    "metadata": {
                        "source": "ga4",
                        "type": "page_views",
                        "tenant_id": "...",
                        "property_id": "123456789",
                        "page_path": "/",
                        "metrics": {"page_views": 24500, "sessions": 12450}
                    }
                }
            ]
        """
        documents = []
        
        for row in ga4_response.get('rows', []):
            # Extract dimensions
            dimension_values = row.get('dimensionValues', [])
            metric_values = row.get('metricValues', [])
            
            # Parse based on dimension structure
            # Common structure: [date, pagePath, deviceCategory]
            if len(dimension_values) >= 2:
                page_path = dimension_values[1]['value']
                
                # Get device if available
                device = dimension_values[2]['value'] if len(dimension_values) > 2 else "all devices"
                
                # Parse metrics
                page_views = int(metric_values[0]['value']) if len(metric_values) > 0 else 0
                sessions = int(metric_values[1]['value']) if len(metric_values) > 1 else 0
                bounce_rate = float(metric_values[2]['value']) if len(metric_values) > 2 else 0.0
                avg_duration = float(metric_values[3]['value']) if len(metric_values) > 3 else 0.0
                
                # Create natural language summary
                content = self._create_page_view_summary(
                    page_path=page_path,
                    device=device,
                    page_views=page_views,
                    sessions=sessions,
                    bounce_rate=bounce_rate,
                    avg_duration=avg_duration
                )
                
                # Build metadata
                metadata = {
                    "source": "ga4",
                    "type": "page_views",
                    "tenant_id": str(tenant_id),
                    "property_id": property_id,
                    "page_path": page_path,
                    "device": device,
                    "metrics": {
                        "page_views": page_views,
                        "sessions": sessions,
                        "bounce_rate": bounce_rate,
                        "avg_session_duration": avg_duration
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                    "transformation_version": self.TRANSFORMATION_VERSION
                }
                
                documents.append({
                    "content": content,
                    "metadata": metadata
                })
        
        logger.info(
            f"Transformed {len(documents)} page view documents "
            f"for tenant {tenant_id}"
        )
        
        return documents
    
    def transform_events_to_documents(
        self,
        ga4_response: Dict[str, Any],
        tenant_id: UUID,
        property_id: str
    ) -> List[Dict[str, Any]]:
        """
        Convert GA4 events API response into vectorizable documents.
        
        Args:
            ga4_response: GA4 API response dict
            tenant_id: Tenant UUID
            property_id: GA4 property ID
            
        Returns:
            List of document dicts
        """
        documents = []
        
        for row in ga4_response.get('rows', []):
            dimension_values = row.get('dimensionValues', [])
            metric_values = row.get('metricValues', [])
            
            # Extract event data
            event_date = dimension_values[0]['value'] if len(dimension_values) > 0 else None
            event_name = dimension_values[1]['value'] if len(dimension_values) > 1 else "unknown"
            
            event_count = int(metric_values[0]['value']) if len(metric_values) > 0 else 0
            event_value = float(metric_values[1]['value']) if len(metric_values) > 1 else 0.0
            
            # Create natural language summary
            content = self._create_event_summary(
                event_name=event_name,
                event_date=event_date,
                event_count=event_count,
                event_value=event_value
            )
            
            # Build metadata
            metadata = {
                "source": "ga4",
                "type": "events",
                "tenant_id": str(tenant_id),
                "property_id": property_id,
                "event_name": event_name,
                "event_date": event_date,
                "metrics": {
                    "event_count": event_count,
                    "event_value": event_value
                },
                "timestamp": datetime.utcnow().isoformat(),
                "transformation_version": self.TRANSFORMATION_VERSION
            }
            
            documents.append({
                "content": content,
                "metadata": metadata
            })
        
        logger.info(
            f"Transformed {len(documents)} event documents for tenant {tenant_id}"
        )
        
        return documents
    
    def transform_conversions_to_documents(
        self,
        ga4_response: Dict[str, Any],
        tenant_id: UUID,
        property_id: str
    ) -> List[Dict[str, Any]]:
        """
        Convert GA4 conversions API response into vectorizable documents.
        
        Args:
            ga4_response: GA4 API response dict
            tenant_id: Tenant UUID
            property_id: GA4 property ID
            
        Returns:
            List of document dicts
        """
        documents = []
        
        for row in ga4_response.get('rows', []):
            dimension_values = row.get('dimensionValues', [])
            metric_values = row.get('metricValues', [])
            
            # Extract conversion data
            conv_date = dimension_values[0]['value'] if len(dimension_values) > 0 else None
            device = dimension_values[1]['value'] if len(dimension_values) > 1 else "all devices"
            
            sessions = int(metric_values[0]['value']) if len(metric_values) > 0 else 0
            conversions = int(metric_values[1]['value']) if len(metric_values) > 1 else 0
            conversion_rate = float(metric_values[2]['value']) if len(metric_values) > 2 else 0.0
            revenue = float(metric_values[3]['value']) if len(metric_values) > 3 else 0.0
            
            # Create natural language summary
            content = self._create_conversion_summary(
                date=conv_date,
                device=device,
                sessions=sessions,
                conversions=conversions,
                conversion_rate=conversion_rate,
                revenue=revenue
            )
            
            # Build metadata
            metadata = {
                "source": "ga4",
                "type": "conversions",
                "tenant_id": str(tenant_id),
                "property_id": property_id,
                "device": device,
                "date": conv_date,
                "metrics": {
                    "sessions": sessions,
                    "conversions": conversions,
                    "conversion_rate": conversion_rate,
                    "revenue": revenue,
                    "avg_order_value": revenue / conversions if conversions > 0 else 0
                },
                "timestamp": datetime.utcnow().isoformat(),
                "transformation_version": self.TRANSFORMATION_VERSION
            }
            
            documents.append({
                "content": content,
                "metadata": metadata
            })
        
        logger.info(
            f"Transformed {len(documents)} conversion documents for tenant {tenant_id}"
        )
        
        return documents
    
    def _create_page_view_summary(
        self,
        page_path: str,
        device: str,
        page_views: int,
        sessions: int,
        bounce_rate: float,
        avg_duration: float
    ) -> str:
        """
        Create natural language summary for page views.
        
        Args:
            page_path: Page path
            device: Device category
            page_views: Number of page views
            sessions: Number of sessions
            bounce_rate: Bounce rate (0.0-1.0)
            avg_duration: Average session duration in seconds
            
        Returns:
            Natural language summary
        """
        # Format page path for readability
        page_display = page_path if page_path != "/" else "the homepage"
        
        # Format duration
        minutes = int(avg_duration // 60)
        seconds = int(avg_duration % 60)
        duration_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
        if seconds > 0:
            duration_str += f" {seconds} second{'s' if seconds != 1 else ''}"
        
        # Format bounce rate
        bounce_pct = bounce_rate * 100
        
        # Build summary
        summary = (
            f"{page_display} on {device} devices had {page_views:,} page views "
            f"from {sessions:,} sessions. The bounce rate was {bounce_pct:.1f}% "
            f"and average session duration was {duration_str}."
        )
        
        return summary
    
    def _create_event_summary(
        self,
        event_name: str,
        event_date: str,
        event_count: int,
        event_value: float
    ) -> str:
        """Create natural language summary for events."""
        # Parse date if possible
        try:
            if len(event_date) == 8:  # YYYYMMDD format
                date_obj = datetime.strptime(event_date, "%Y%m%d")
                date_display = date_obj.strftime("%B %d, %Y")
            else:
                date_display = event_date
        except:
            date_display = event_date
        
        summary = f"The event '{event_name}' occurred {event_count:,} times"
        
        if date_display:
            summary += f" on {date_display}"
        
        if event_value > 0:
            summary += f" with a total value of ${event_value:,.2f}"
        
        summary += "."
        
        return summary
    
    def _create_conversion_summary(
        self,
        date: str,
        device: str,
        sessions: int,
        conversions: int,
        conversion_rate: float,
        revenue: float
    ) -> str:
        """Create natural language summary for conversions."""
        # Parse date
        try:
            if len(date) == 8:  # YYYYMMDD format
                date_obj = datetime.strptime(date, "%Y%m%d")
                date_display = date_obj.strftime("%B %d, %Y")
            else:
                date_display = date
        except:
            date_display = date
        
        # Format conversion rate
        conv_pct = conversion_rate * 100
        
        # Calculate AOV
        avg_order_value = revenue / conversions if conversions > 0 else 0
        
        summary = (
            f"On {date_display}, {device} users had {sessions:,} sessions "
            f"with {conversions:,} conversions ({conv_pct:.1f}% conversion rate). "
            f"Total revenue was ${revenue:,.2f} with an average order value of ${avg_order_value:.2f}."
        )
        
        return summary
    
    def aggregate_by_page(
        self,
        documents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Aggregate documents by page path.
        
        Reduces high-cardinality data by grouping similar pages.
        
        Args:
            documents: List of document dicts
            
        Returns:
            Aggregated document list
        """
        # Group by page_path
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        
        for doc in documents:
            page_path = doc["metadata"].get("page_path", "/")
            
            if page_path not in grouped:
                grouped[page_path] = []
            
            grouped[page_path].append(doc)
        
        # Aggregate each group
        aggregated = []
        
        for page_path, docs in grouped.items():
            if len(docs) == 1:
                aggregated.append(docs[0])
            else:
                # Aggregate multiple documents for same page
                agg_doc = self._aggregate_page_documents(docs)
                aggregated.append(agg_doc)
        
        logger.info(
            f"Aggregated {len(documents)} documents into {len(aggregated)} "
            f"by page path"
        )
        
        return aggregated
    
    def _aggregate_page_documents(
        self,
        docs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Aggregate multiple documents for the same page.
        
        Args:
            docs: List of documents for same page
            
        Returns:
            Single aggregated document
        """
        # Sum metrics
        total_page_views = sum(
            doc["metadata"]["metrics"].get("page_views", 0)
            for doc in docs
        )
        total_sessions = sum(
            doc["metadata"]["metrics"].get("sessions", 0)
            for doc in docs
        )
        
        # Average bounce rate (weighted by sessions)
        weighted_bounce = sum(
            doc["metadata"]["metrics"].get("bounce_rate", 0) *
            doc["metadata"]["metrics"].get("sessions", 0)
            for doc in docs
        )
        avg_bounce_rate = weighted_bounce / total_sessions if total_sessions > 0 else 0.0
        
        # First doc metadata as base
        base_metadata = docs[0]["metadata"].copy()
        base_metadata["metrics"] = {
            "page_views": total_page_views,
            "sessions": total_sessions,
            "bounce_rate": avg_bounce_rate,
            "aggregated_from": len(docs)
        }
        
        # Create aggregated summary
        page_path = base_metadata["page_path"]
        page_display = page_path if page_path != "/" else "the homepage"
        
        content = (
            f"{page_display} had {total_page_views:,} page views "
            f"from {total_sessions:,} sessions across all devices. "
            f"The average bounce rate was {avg_bounce_rate * 100:.1f}%."
        )
        
        return {
            "content": content,
            "metadata": base_metadata
        }
    
    def set_transformation_version(self, version: str) -> None:
        """
        Set transformation version for audit tracking.
        
        Args:
            version: Version string (e.g., "v1.1.0")
        """
        self.TRANSFORMATION_VERSION = version
        logger.info(f"Transformation version set to {version}")

