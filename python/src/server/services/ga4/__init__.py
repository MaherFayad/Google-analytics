"""
GA4 (Google Analytics 4) service modules.

This package contains services for interacting with Google Analytics 4 API:
- mock_service: Mock GA4 API for local development (Task P0-10)
- data_fetcher: GA4 data fetching and storage (Task 8.1)
- ga4_client: Production GA4 API client (Task 12)
- resilient_client: Resilience layer with retries (Task P0-4)
- quota_manager: Per-tenant quota management (Task 15)
"""

from .mock_service import GA4MockService, get_ga4_client
from .data_fetcher import GA4DataFetcher, GA4FetchError
from .ga4_client import (
    GA4Client,
    GA4Credentials,
    GA4ReportRequest,
    GA4ReportResponse,
    GA4ReportRow,
    create_ga4_client,
)

__all__ = [
    "GA4MockService",
    "get_ga4_client",
    "GA4DataFetcher",
    "GA4FetchError",
    "GA4Client",
    "GA4Credentials",
    "GA4ReportRequest",
    "GA4ReportResponse",
    "GA4ReportRow",
    "create_ga4_client",
]

