"""
Mock GA4 Data API service for local development and testing.

Implements Task P0-10: GA4 API Mock Service for Development

This service enables:
1. Local development without GA4 credentials
2. Fast iteration (no API calls)
3. Predictable test data
4. Scenario-based testing
5. No quota consumption

Usage:
    from server.services.ga4 import get_ga4_client
    
    # Automatically returns mock in dev mode
    client = get_ga4_client(mock_mode=True)
    response = await client.fetch_page_views(start_date="2025-01-01", end_date="2025-01-07")
"""

import logging
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class GA4MockService:
    """
    Mock GA4 Data API for local development and testing.
    
    Generates realistic GA4 analytics data without requiring actual API credentials.
    Supports multiple scenarios for comprehensive testing.
    """
    
    # Pre-defined test scenarios
    SCENARIOS = {
        "steady_growth": {
            "description": "Steady traffic growth over time",
            "base_sessions": 10000,
            "growth_rate": 0.05,  # 5% week-over-week
            "conversion_rate": 0.03,  # 3%
            "bounce_rate": 0.42
        },
        "conversion_drop": {
            "description": "Sudden conversion rate drop (testing alerts)",
            "base_sessions": 15000,
            "growth_rate": 0.02,
            "conversion_rate": 0.015,  # Dropped from 3% to 1.5%
            "bounce_rate": 0.52  # Increased from 42% to 52%
        },
        "traffic_spike": {
            "description": "Viral content causing traffic spike",
            "base_sessions": 50000,  # 5x normal
            "growth_rate": 0.0,
            "conversion_rate": 0.025,  # Slightly lower due to new visitors
            "bounce_rate": 0.48
        },
        "seasonal_low": {
            "description": "Off-season low traffic period",
            "base_sessions": 5000,
            "growth_rate": -0.03,  # Declining 3% per week
            "conversion_rate": 0.035,  # Higher quality traffic
            "bounce_rate": 0.38
        },
        "high_performance": {
            "description": "Best-case performance metrics",
            "base_sessions": 25000,
            "growth_rate": 0.10,  # 10% growth
            "conversion_rate": 0.05,  # 5% conversion
            "bounce_rate": 0.30  # Low bounce rate
        }
    }
    
    # Device distribution (realistic mix)
    DEVICE_TYPES = {
        "mobile": 0.55,
        "desktop": 0.35,
        "tablet": 0.10
    }
    
    # Common page paths
    PAGE_PATHS = [
        "/",
        "/products",
        "/pricing",
        "/blog",
        "/about",
        "/contact",
        "/checkout",
        "/account",
        "/features",
        "/documentation"
    ]
    
    # Event names
    EVENT_NAMES = [
        "page_view",
        "session_start",
        "first_visit",
        "user_engagement",
        "scroll",
        "click",
        "form_submit",
        "purchase",
        "add_to_cart",
        "view_item"
    ]
    
    def __init__(
        self,
        property_id: str,
        tenant_id: UUID,
        scenario: str = "steady_growth"
    ):
        """
        Initialize mock GA4 service.
        
        Args:
            property_id: GA4 property ID (not used, but kept for interface compatibility)
            tenant_id: Tenant UUID for multi-tenant isolation
            scenario: Test scenario name (see SCENARIOS dict)
        """
        self.property_id = property_id
        self.tenant_id = tenant_id
        self.scenario = self.SCENARIOS.get(scenario, self.SCENARIOS["steady_growth"])
        self.scenario_name = scenario
        
        logger.info(
            f"GA4MockService initialized: tenant={tenant_id}, "
            f"scenario={scenario}, property={property_id}"
        )
    
    async def fetch_page_views(
        self,
        start_date: str,
        end_date: str,
        dimensions: Optional[List[str]] = None,
        metrics: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Fetch page view metrics (mock implementation).
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            dimensions: List of dimensions (e.g., ["date", "pagePath", "deviceCategory"])
            metrics: List of metrics (e.g., ["sessions", "screenPageViews", "bounceRate"])
            
        Returns:
            Mock GA4 API response with realistic data
        """
        logger.debug(
            f"Mock GA4 fetch_page_views: {start_date} to {end_date}, "
            f"scenario={self.scenario_name}"
        )
        
        # Parse dates
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        days = (end - start).days + 1
        
        # Default dimensions and metrics
        dimensions = dimensions or ["date", "pagePath", "deviceCategory"]
        metrics = metrics or ["sessions", "screenPageViews", "bounceRate", "averageSessionDuration"]
        
        # Generate daily data
        rows = []
        current_date = start
        
        for day_offset in range(days):
            current_date = start + timedelta(days=day_offset)
            date_str = current_date.strftime("%Y%m%d")
            
            # Apply growth rate over time
            growth_factor = (1 + self.scenario["growth_rate"]) ** day_offset
            base_sessions = int(self.scenario["base_sessions"] * growth_factor)
            
            # Generate data for each page path and device combination
            for page_path in random.sample(self.PAGE_PATHS, k=min(5, len(self.PAGE_PATHS))):
                for device, device_weight in self.DEVICE_TYPES.items():
                    # Calculate metrics with realistic variation
                    sessions = int(base_sessions * device_weight * random.uniform(0.8, 1.2) / 5)
                    page_views = int(sessions * random.uniform(1.2, 2.5))
                    bounce_rate = self.scenario["bounce_rate"] * random.uniform(0.9, 1.1)
                    avg_session_duration = random.uniform(120, 300)  # 2-5 minutes
                    
                    rows.append({
                        "dimensionValues": [
                            {"value": date_str},
                            {"value": page_path},
                            {"value": device}
                        ],
                        "metricValues": [
                            {"value": str(sessions)},
                            {"value": str(page_views)},
                            {"value": f"{bounce_rate:.4f}"},
                            {"value": f"{avg_session_duration:.2f}"}
                        ]
                    })
        
        # Format response to match GA4 API structure
        response = {
            "dimensionHeaders": [
                {"name": dim} for dim in dimensions
            ],
            "metricHeaders": [
                {"name": metric, "type": "TYPE_INTEGER" if metric in ["sessions", "screenPageViews"] else "TYPE_FLOAT"}
                for metric in metrics
            ],
            "rows": rows,
            "rowCount": len(rows),
            "metadata": {
                "dataLossFromOtherRow": False,
                "samplingMetadatas": [],
                "schemaRestrictionResponse": {"activeMetricRestrictions": []},
                "currencyCode": "USD",
                "timeZone": "America/New_York"
            },
            "kind": "analyticsData#runReport"
        }
        
        logger.info(
            f"Mock GA4 generated {len(rows)} rows for {days} days, "
            f"scenario={self.scenario_name}"
        )
        
        return response
    
    async def fetch_events(
        self,
        start_date: str,
        end_date: str,
        event_names: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Fetch event metrics (mock implementation).
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            event_names: List of event names to filter (optional)
            
        Returns:
            Mock GA4 API response with event data
        """
        logger.debug(
            f"Mock GA4 fetch_events: {start_date} to {end_date}, "
            f"events={event_names or 'all'}"
        )
        
        # Parse dates
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        days = (end - start).days + 1
        
        # Filter or use all events
        events_to_generate = event_names or self.EVENT_NAMES
        
        # Generate event data
        rows = []
        current_date = start
        
        for day_offset in range(days):
            current_date = start + timedelta(days=day_offset)
            date_str = current_date.strftime("%Y%m%d")
            
            growth_factor = (1 + self.scenario["growth_rate"]) ** day_offset
            base_events = int(self.scenario["base_sessions"] * growth_factor * 3)  # 3 events per session avg
            
            for event_name in events_to_generate:
                event_count = int(base_events * random.uniform(0.1, 0.3))
                event_value = event_count * random.uniform(0.5, 2.0) if event_name == "purchase" else 0
                
                rows.append({
                    "dimensionValues": [
                        {"value": date_str},
                        {"value": event_name}
                    ],
                    "metricValues": [
                        {"value": str(event_count)},
                        {"value": f"{event_value:.2f}"}
                    ]
                })
        
        response = {
            "dimensionHeaders": [
                {"name": "date"},
                {"name": "eventName"}
            ],
            "metricHeaders": [
                {"name": "eventCount", "type": "TYPE_INTEGER"},
                {"name": "eventValue", "type": "TYPE_FLOAT"}
            ],
            "rows": rows,
            "rowCount": len(rows),
            "metadata": {
                "dataLossFromOtherRow": False,
                "currencyCode": "USD",
                "timeZone": "America/New_York"
            },
            "kind": "analyticsData#runReport"
        }
        
        logger.info(
            f"Mock GA4 generated {len(rows)} event rows for {days} days"
        )
        
        return response
    
    async def fetch_conversions(
        self,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """
        Fetch conversion metrics (mock implementation).
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            Mock GA4 API response with conversion data
        """
        logger.debug(
            f"Mock GA4 fetch_conversions: {start_date} to {end_date}, "
            f"scenario={self.scenario_name}"
        )
        
        # Parse dates
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        days = (end - start).days + 1
        
        # Generate conversion data
        rows = []
        
        for day_offset in range(days):
            current_date = start + timedelta(days=day_offset)
            date_str = current_date.strftime("%Y%m%d")
            
            growth_factor = (1 + self.scenario["growth_rate"]) ** day_offset
            base_sessions = int(self.scenario["base_sessions"] * growth_factor)
            
            for device, device_weight in self.DEVICE_TYPES.items():
                sessions = int(base_sessions * device_weight)
                conversions = int(sessions * self.scenario["conversion_rate"] * random.uniform(0.9, 1.1))
                conversion_rate = conversions / sessions if sessions > 0 else 0
                revenue = conversions * random.uniform(50, 150)  # $50-$150 per conversion
                
                rows.append({
                    "dimensionValues": [
                        {"value": date_str},
                        {"value": device}
                    ],
                    "metricValues": [
                        {"value": str(sessions)},
                        {"value": str(conversions)},
                        {"value": f"{conversion_rate:.4f}"},
                        {"value": f"{revenue:.2f}"}
                    ]
                })
        
        response = {
            "dimensionHeaders": [
                {"name": "date"},
                {"name": "deviceCategory"}
            ],
            "metricHeaders": [
                {"name": "sessions", "type": "TYPE_INTEGER"},
                {"name": "conversions", "type": "TYPE_INTEGER"},
                {"name": "conversionRate", "type": "TYPE_FLOAT"},
                {"name": "totalRevenue", "type": "TYPE_CURRENCY"}
            ],
            "rows": rows,
            "rowCount": len(rows),
            "metadata": {
                "dataLossFromOtherRow": False,
                "currencyCode": "USD",
                "timeZone": "America/New_York"
            },
            "kind": "analyticsData#runReport"
        }
        
        logger.info(
            f"Mock GA4 generated {len(rows)} conversion rows, "
            f"scenario={self.scenario_name}, conversion_rate={self.scenario['conversion_rate']:.1%}"
        )
        
        return response


def get_ga4_client(
    property_id: str,
    tenant_id: UUID,
    mock_mode: bool = False,
    scenario: str = "steady_growth",
    credentials: Optional[Dict[str, Any]] = None
) -> GA4MockService:
    """
    Factory function to get GA4 client (mock or real).
    
    Task P0-10: Returns mock service for local development.
    Task 12: Will return real GA4Client when implemented.
    
    Args:
        property_id: GA4 property ID
        tenant_id: Tenant UUID
        mock_mode: If True, return mock service
        scenario: Test scenario for mock service
        credentials: OAuth credentials (for real client)
        
    Returns:
        GA4MockService (or GA4Client when Task 12 is implemented)
        
    Usage:
        # Local development with mock
        client = get_ga4_client(
            property_id="123456789",
            tenant_id=UUID("..."),
            mock_mode=True,
            scenario="conversion_drop"
        )
        
        # Production with real API
        client = get_ga4_client(
            property_id="123456789",
            tenant_id=UUID("..."),
            mock_mode=False,
            credentials={...}
        )
    """
    if mock_mode:
        logger.info(f"Creating GA4MockService for tenant {tenant_id}, scenario={scenario}")
        return GA4MockService(
            property_id=property_id,
            tenant_id=tenant_id,
            scenario=scenario
        )
    else:
        # TODO: Task 12 - Return real GA4Client
        logger.warning(
            "Real GA4Client not yet implemented (Task 12). "
            "Falling back to mock service."
        )
        return GA4MockService(
            property_id=property_id,
            tenant_id=tenant_id,
            scenario=scenario
        )

