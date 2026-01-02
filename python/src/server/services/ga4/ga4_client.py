"""
Google Analytics 4 Data API Client.

Implements Task 12: Google Analytics 4 API Client [P0 - CRITICAL]

Production-ready GA4 Data API v1 client with:
- OAuth2 authentication
- Quota management integration
- Error handling
- Type safety with Pydantic models

This client is wrapped by ResilientGA4Client (Task P0-4) for retry logic
and circuit breaker patterns.
"""

import logging
from datetime import date, datetime
from typing import Dict, List, Any, Optional
from uuid import UUID

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest,
    RunReportResponse,
    DateRange,
    Dimension,
    Metric,
    FilterExpression,
    Filter,
    FilterExpressionList,
)
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
from pydantic import BaseModel, Field, validator

from .exceptions import (
    GA4AuthenticationError,
    GA4APIError,
    GA4RateLimitError,
    GA4QuotaExceededError,
    GA4InvalidPropertyError,
)

logger = logging.getLogger(__name__)


class GA4Credentials(BaseModel):
    """OAuth2 credentials for GA4 API access."""
    
    access_token: str
    refresh_token: str
    token_uri: str = "https://oauth2.googleapis.com/token"
    client_id: str
    client_secret: str
    expiry: Optional[datetime] = None
    
    def to_google_credentials(self) -> Credentials:
        """Convert to google-auth Credentials object."""
        return Credentials(
            token=self.access_token,
            refresh_token=self.refresh_token,
            token_uri=self.token_uri,
            client_id=self.client_id,
            client_secret=self.client_secret,
        )


class GA4ReportRequest(BaseModel):
    """Request parameters for GA4 report."""
    
    property_id: str = Field(..., description="GA4 property ID (e.g., '123456789')")
    start_date: date = Field(..., description="Report start date")
    end_date: date = Field(..., description="Report end date")
    dimensions: List[str] = Field(default_factory=list, description="GA4 dimensions (e.g., 'date', 'deviceCategory')")
    metrics: List[str] = Field(default_factory=list, description="GA4 metrics (e.g., 'sessions', 'conversions')")
    limit: int = Field(default=10000, ge=1, le=100000, description="Maximum rows to return")
    offset: int = Field(default=0, ge=0, description="Pagination offset")
    
    @validator('dimensions')
    def validate_dimensions(cls, v):
        """Ensure at least one dimension is specified."""
        if not v:
            raise ValueError("At least one dimension is required")
        return v
    
    @validator('metrics')
    def validate_metrics(cls, v):
        """Ensure at least one metric is specified."""
        if not v:
            raise ValueError("At least one metric is required")
        return v


class GA4ReportRow(BaseModel):
    """Single row from GA4 report response."""
    
    dimensions: Dict[str, str] = Field(default_factory=dict)
    metrics: Dict[str, float] = Field(default_factory=dict)


class GA4ReportResponse(BaseModel):
    """Parsed GA4 report response."""
    
    rows: List[GA4ReportRow]
    row_count: int
    property_id: str
    date_range: Dict[str, str]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GA4Client:
    """
    Google Analytics 4 Data API v1 Client.
    
    Features:
    - OAuth2 authentication with automatic token refresh
    - Type-safe request/response models
    - Comprehensive error handling
    - Quota management integration (Task 15)
    - Tenant isolation support
    
    Example:
        >>> credentials = GA4Credentials(
        ...     access_token="...",
        ...     refresh_token="...",
        ...     client_id="...",
        ...     client_secret="..."
        ... )
        >>> client = GA4Client(
        ...     credentials=credentials,
        ...     property_id="123456789",
        ...     tenant_id=UUID("...")
        ... )
        >>> request = GA4ReportRequest(
        ...     property_id="123456789",
        ...     start_date=date(2026, 1, 1),
        ...     end_date=date(2026, 1, 7),
        ...     dimensions=["date", "deviceCategory"],
        ...     metrics=["sessions", "conversions"]
        ... )
        >>> response = await client.run_report(request)
        >>> print(f"Fetched {response.row_count} rows")
    """
    
    def __init__(
        self,
        credentials: GA4Credentials,
        property_id: str,
        tenant_id: UUID,
        quota_manager: Optional[Any] = None,
    ):
        """
        Initialize GA4 client.
        
        Args:
            credentials: OAuth2 credentials for GA4 API
            property_id: GA4 property ID (e.g., "123456789")
            tenant_id: Tenant UUID for quota tracking
            quota_manager: Optional quota manager instance (Task 15)
        """
        self.credentials = credentials
        self.property_id = f"properties/{property_id}"
        self.tenant_id = tenant_id
        self.quota_manager = quota_manager
        
        # Initialize Google Analytics Data API client
        try:
            google_creds = credentials.to_google_credentials()
            self.client = BetaAnalyticsDataClient(credentials=google_creds)
            logger.info(f"GA4 client initialized for property {property_id}, tenant {tenant_id}")
        except Exception as e:
            logger.error(f"Failed to initialize GA4 client: {e}")
            raise GA4AuthenticationError(f"Failed to initialize GA4 client: {e}")
    
    async def run_report(self, request: GA4ReportRequest) -> GA4ReportResponse:
        """
        Run a GA4 report request.
        
        Args:
            request: Report request parameters
            
        Returns:
            Parsed report response
            
        Raises:
            GA4AuthenticationError: If OAuth credentials are invalid
            GA4RateLimitError: If rate limit exceeded (429)
            GA4QuotaExceededError: If daily quota exhausted
            GA4InvalidPropertyError: If property ID is invalid
            GA4APIError: For other API errors
        """
        logger.info(
            f"Running GA4 report: property={request.property_id}, "
            f"dates={request.start_date} to {request.end_date}, "
            f"dimensions={request.dimensions}, metrics={request.metrics}"
        )
        
        # Check quota before making API call (Task 15 integration)
        if self.quota_manager:
            try:
                await self.quota_manager.acquire_quota(requests=1)
            except Exception as e:
                logger.warning(f"Quota check failed: {e}")
                raise GA4QuotaExceededError(str(e))
        
        # Build GA4 API request
        ga4_request = self._build_request(request)
        
        try:
            # Make API call
            response: RunReportResponse = self.client.run_report(ga4_request)
            
            # Parse response
            parsed_response = self._parse_response(response, request)
            
            logger.info(f"GA4 report completed: {parsed_response.row_count} rows fetched")
            return parsed_response
            
        except RefreshError as e:
            logger.error(f"OAuth token refresh failed: {e}")
            raise GA4AuthenticationError(f"OAuth token refresh failed: {e}")
            
        except Exception as e:
            error_message = str(e)
            
            # Parse error type from exception message
            if "429" in error_message or "rate limit" in error_message.lower():
                logger.warning(f"GA4 rate limit exceeded: {e}")
                raise GA4RateLimitError(str(e))
            
            elif "quota" in error_message.lower():
                logger.error(f"GA4 quota exceeded: {e}")
                raise GA4QuotaExceededError(str(e))
            
            elif "property" in error_message.lower() or "not found" in error_message.lower():
                logger.error(f"Invalid GA4 property: {e}")
                raise GA4InvalidPropertyError(f"Invalid property ID: {request.property_id}")
            
            elif "auth" in error_message.lower() or "permission" in error_message.lower():
                logger.error(f"GA4 authentication error: {e}")
                raise GA4AuthenticationError(str(e))
            
            else:
                logger.error(f"GA4 API error: {e}")
                raise GA4APIError(f"GA4 API error: {e}")
    
    def _build_request(self, request: GA4ReportRequest) -> RunReportRequest:
        """
        Build Google Analytics Data API request object.
        
        Args:
            request: Parsed request parameters
            
        Returns:
            GA4 API request object
        """
        return RunReportRequest(
            property=self.property_id,
            dimensions=[Dimension(name=dim) for dim in request.dimensions],
            metrics=[Metric(name=metric) for metric in request.metrics],
            date_ranges=[
                DateRange(
                    start_date=request.start_date.isoformat(),
                    end_date=request.end_date.isoformat()
                )
            ],
            limit=request.limit,
            offset=request.offset,
        )
    
    def _parse_response(
        self,
        response: RunReportResponse,
        request: GA4ReportRequest
    ) -> GA4ReportResponse:
        """
        Parse GA4 API response into structured format.
        
        Args:
            response: Raw GA4 API response
            request: Original request (for metadata)
            
        Returns:
            Parsed response with typed rows
        """
        rows = []
        
        for row in response.rows:
            # Parse dimensions
            dimensions = {}
            for i, dim in enumerate(request.dimensions):
                dimensions[dim] = row.dimension_values[i].value
            
            # Parse metrics
            metrics = {}
            for i, metric in enumerate(request.metrics):
                try:
                    metrics[metric] = float(row.metric_values[i].value)
                except (ValueError, IndexError):
                    metrics[metric] = 0.0
            
            rows.append(GA4ReportRow(dimensions=dimensions, metrics=metrics))
        
        return GA4ReportResponse(
            rows=rows,
            row_count=len(rows),
            property_id=request.property_id,
            date_range={
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
            },
            metadata={
                "dimensions": request.dimensions,
                "metrics": request.metrics,
                "tenant_id": str(self.tenant_id),
            }
        )
    
    async def fetch_page_views(
        self,
        start_date: date,
        end_date: date,
        dimensions: Optional[List[str]] = None,
        limit: int = 10000
    ) -> GA4ReportResponse:
        """
        Convenience method to fetch page views report.
        
        Args:
            start_date: Report start date
            end_date: Report end date
            dimensions: Optional custom dimensions (default: date, pagePath, pageTitle)
            limit: Maximum rows to return
            
        Returns:
            Report response with page view data
        """
        if dimensions is None:
            dimensions = ["date", "pagePath", "pageTitle"]
        
        request = GA4ReportRequest(
            property_id=self.property_id.replace("properties/", ""),
            start_date=start_date,
            end_date=end_date,
            dimensions=dimensions,
            metrics=["screenPageViews", "sessions", "bounceRate"],
            limit=limit
        )
        
        return await self.run_report(request)
    
    async def fetch_conversions(
        self,
        start_date: date,
        end_date: date,
        dimensions: Optional[List[str]] = None,
        limit: int = 10000
    ) -> GA4ReportResponse:
        """
        Convenience method to fetch conversions report.
        
        Args:
            start_date: Report start date
            end_date: Report end date
            dimensions: Optional custom dimensions (default: date, deviceCategory)
            limit: Maximum rows to return
            
        Returns:
            Report response with conversion data
        """
        if dimensions is None:
            dimensions = ["date", "deviceCategory"]
        
        request = GA4ReportRequest(
            property_id=self.property_id.replace("properties/", ""),
            start_date=start_date,
            end_date=end_date,
            dimensions=dimensions,
            metrics=["conversions", "sessions", "engagementRate"],
            limit=limit
        )
        
        return await self.run_report(request)
    
    async def fetch_traffic_sources(
        self,
        start_date: date,
        end_date: date,
        limit: int = 10000
    ) -> GA4ReportResponse:
        """
        Convenience method to fetch traffic sources report.
        
        Args:
            start_date: Report start date
            end_date: Report end date
            limit: Maximum rows to return
            
        Returns:
            Report response with traffic source data
        """
        request = GA4ReportRequest(
            property_id=self.property_id.replace("properties/", ""),
            start_date=start_date,
            end_date=end_date,
            dimensions=["date", "sessionSource", "sessionMedium"],
            metrics=["sessions", "newUsers", "engagementRate"],
            limit=limit
        )
        
        return await self.run_report(request)


# Factory function for creating GA4 client
def create_ga4_client(
    credentials: Dict[str, Any],
    property_id: str,
    tenant_id: UUID,
    quota_manager: Optional[Any] = None,
) -> GA4Client:
    """
    Factory function to create GA4 client from credentials dict.
    
    Args:
        credentials: Dictionary with OAuth2 credentials
        property_id: GA4 property ID
        tenant_id: Tenant UUID
        quota_manager: Optional quota manager instance
        
    Returns:
        Initialized GA4 client
        
    Example:
        >>> credentials = {
        ...     "access_token": "...",
        ...     "refresh_token": "...",
        ...     "client_id": "...",
        ...     "client_secret": "..."
        ... }
        >>> client = create_ga4_client(
        ...     credentials=credentials,
        ...     property_id="123456789",
        ...     tenant_id=UUID("...")
        ... )
    """
    ga4_creds = GA4Credentials(**credentials)
    return GA4Client(
        credentials=ga4_creds,
        property_id=property_id,
        tenant_id=tenant_id,
        quota_manager=quota_manager,
    )

