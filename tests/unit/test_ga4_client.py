"""
Unit tests for GA4 Client (Task 12).

Tests the production GA4 Data API client with mocked Google Analytics API.
"""

import pytest
from datetime import date
from uuid import uuid4
from unittest.mock import Mock, patch, MagicMock

from google.analytics.data_v1beta.types import (
    RunReportResponse,
    Row,
    DimensionValue,
    MetricValue,
)

from server.services.ga4.ga4_client import (
    GA4Client,
    GA4Credentials,
    GA4ReportRequest,
    GA4ReportResponse,
    create_ga4_client,
)
from server.services.ga4.exceptions import (
    GA4AuthenticationError,
    GA4RateLimitError,
    GA4QuotaExceededError,
    GA4InvalidPropertyError,
)


@pytest.fixture
def ga4_credentials():
    """Mock GA4 OAuth2 credentials."""
    return GA4Credentials(
        access_token="mock_access_token",
        refresh_token="mock_refresh_token",
        client_id="mock_client_id.apps.googleusercontent.com",
        client_secret="mock_client_secret",
    )


@pytest.fixture
def tenant_id():
    """Mock tenant UUID."""
    return uuid4()


@pytest.fixture
def mock_quota_manager():
    """Mock quota manager."""
    manager = Mock()
    manager.acquire_quota = Mock(return_value=None)
    return manager


@pytest.fixture
def ga4_client(ga4_credentials, tenant_id, mock_quota_manager):
    """Create GA4 client with mocked API."""
    with patch('server.services.ga4.ga4_client.BetaAnalyticsDataClient'):
        client = GA4Client(
            credentials=ga4_credentials,
            property_id="123456789",
            tenant_id=tenant_id,
            quota_manager=mock_quota_manager,
        )
        return client


class TestGA4Credentials:
    """Test GA4Credentials model."""
    
    def test_credentials_initialization(self, ga4_credentials):
        """Test credentials can be initialized."""
        assert ga4_credentials.access_token == "mock_access_token"
        assert ga4_credentials.refresh_token == "mock_refresh_token"
        assert ga4_credentials.client_id == "mock_client_id.apps.googleusercontent.com"
    
    def test_to_google_credentials(self, ga4_credentials):
        """Test conversion to google-auth Credentials."""
        google_creds = ga4_credentials.to_google_credentials()
        assert google_creds.token == "mock_access_token"
        assert google_creds.refresh_token == "mock_refresh_token"


class TestGA4ReportRequest:
    """Test GA4ReportRequest model."""
    
    def test_valid_request(self):
        """Test valid report request."""
        request = GA4ReportRequest(
            property_id="123456789",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 7),
            dimensions=["date", "deviceCategory"],
            metrics=["sessions", "conversions"],
        )
        assert request.property_id == "123456789"
        assert len(request.dimensions) == 2
        assert len(request.metrics) == 2
    
    def test_request_requires_dimensions(self):
        """Test that at least one dimension is required."""
        with pytest.raises(ValueError, match="At least one dimension is required"):
            GA4ReportRequest(
                property_id="123456789",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 7),
                dimensions=[],
                metrics=["sessions"],
            )
    
    def test_request_requires_metrics(self):
        """Test that at least one metric is required."""
        with pytest.raises(ValueError, match="At least one metric is required"):
            GA4ReportRequest(
                property_id="123456789",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 7),
                dimensions=["date"],
                metrics=[],
            )
    
    def test_request_limit_validation(self):
        """Test limit must be within valid range."""
        # Valid limit
        request = GA4ReportRequest(
            property_id="123456789",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 7),
            dimensions=["date"],
            metrics=["sessions"],
            limit=5000,
        )
        assert request.limit == 5000
        
        # Invalid limit (too high)
        with pytest.raises(ValueError):
            GA4ReportRequest(
                property_id="123456789",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 7),
                dimensions=["date"],
                metrics=["sessions"],
                limit=200000,  # > 100000
            )


class TestGA4Client:
    """Test GA4Client functionality."""
    
    def test_client_initialization(self, ga4_credentials, tenant_id):
        """Test GA4 client can be initialized."""
        with patch('server.services.ga4.ga4_client.BetaAnalyticsDataClient'):
            client = GA4Client(
                credentials=ga4_credentials,
                property_id="123456789",
                tenant_id=tenant_id,
            )
            assert client.property_id == "properties/123456789"
            assert client.tenant_id == tenant_id
    
    @pytest.mark.asyncio
    async def test_run_report_success(self, ga4_client):
        """Test successful report execution."""
        # Mock GA4 API response
        mock_response = RunReportResponse(
            rows=[
                Row(
                    dimension_values=[
                        DimensionValue(value="2026-01-01"),
                        DimensionValue(value="mobile"),
                    ],
                    metric_values=[
                        MetricValue(value="1234"),
                        MetricValue(value="56"),
                    ],
                ),
                Row(
                    dimension_values=[
                        DimensionValue(value="2026-01-01"),
                        DimensionValue(value="desktop"),
                    ],
                    metric_values=[
                        MetricValue(value="5678"),
                        MetricValue(value="89"),
                    ],
                ),
            ]
        )
        
        ga4_client.client.run_report = Mock(return_value=mock_response)
        
        # Create request
        request = GA4ReportRequest(
            property_id="123456789",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 7),
            dimensions=["date", "deviceCategory"],
            metrics=["sessions", "conversions"],
        )
        
        # Execute report
        response = await ga4_client.run_report(request)
        
        # Verify response
        assert isinstance(response, GA4ReportResponse)
        assert response.row_count == 2
        assert len(response.rows) == 2
        
        # Verify first row
        assert response.rows[0].dimensions["date"] == "2026-01-01"
        assert response.rows[0].dimensions["deviceCategory"] == "mobile"
        assert response.rows[0].metrics["sessions"] == 1234.0
        assert response.rows[0].metrics["conversions"] == 56.0
    
    @pytest.mark.asyncio
    async def test_run_report_with_quota_check(self, ga4_client, mock_quota_manager):
        """Test report execution checks quota."""
        # Mock successful response
        mock_response = RunReportResponse(rows=[])
        ga4_client.client.run_report = Mock(return_value=mock_response)
        
        request = GA4ReportRequest(
            property_id="123456789",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 7),
            dimensions=["date"],
            metrics=["sessions"],
        )
        
        await ga4_client.run_report(request)
        
        # Verify quota was checked
        mock_quota_manager.acquire_quota.assert_called_once_with(requests=1)
    
    @pytest.mark.asyncio
    async def test_run_report_quota_exceeded(self, ga4_client, mock_quota_manager):
        """Test report execution fails when quota exceeded."""
        # Mock quota exceeded
        mock_quota_manager.acquire_quota.side_effect = Exception("Quota exceeded")
        
        request = GA4ReportRequest(
            property_id="123456789",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 7),
            dimensions=["date"],
            metrics=["sessions"],
        )
        
        with pytest.raises(GA4QuotaExceededError):
            await ga4_client.run_report(request)
    
    @pytest.mark.asyncio
    async def test_run_report_rate_limit_error(self, ga4_client):
        """Test handling of rate limit errors."""
        # Mock rate limit error
        ga4_client.client.run_report = Mock(
            side_effect=Exception("429 rate limit exceeded")
        )
        
        request = GA4ReportRequest(
            property_id="123456789",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 7),
            dimensions=["date"],
            metrics=["sessions"],
        )
        
        with pytest.raises(GA4RateLimitError):
            await ga4_client.run_report(request)
    
    @pytest.mark.asyncio
    async def test_run_report_invalid_property(self, ga4_client):
        """Test handling of invalid property ID."""
        # Mock invalid property error
        ga4_client.client.run_report = Mock(
            side_effect=Exception("property not found")
        )
        
        request = GA4ReportRequest(
            property_id="999999999",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 7),
            dimensions=["date"],
            metrics=["sessions"],
        )
        
        with pytest.raises(GA4InvalidPropertyError):
            await ga4_client.run_report(request)
    
    @pytest.mark.asyncio
    async def test_fetch_page_views(self, ga4_client):
        """Test convenience method for fetching page views."""
        # Mock response
        mock_response = RunReportResponse(rows=[])
        ga4_client.client.run_report = Mock(return_value=mock_response)
        
        response = await ga4_client.fetch_page_views(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 7),
        )
        
        assert isinstance(response, GA4ReportResponse)
        ga4_client.client.run_report.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_fetch_conversions(self, ga4_client):
        """Test convenience method for fetching conversions."""
        # Mock response
        mock_response = RunReportResponse(rows=[])
        ga4_client.client.run_report = Mock(return_value=mock_response)
        
        response = await ga4_client.fetch_conversions(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 7),
        )
        
        assert isinstance(response, GA4ReportResponse)
        ga4_client.client.run_report.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_fetch_traffic_sources(self, ga4_client):
        """Test convenience method for fetching traffic sources."""
        # Mock response
        mock_response = RunReportResponse(rows=[])
        ga4_client.client.run_report = Mock(return_value=mock_response)
        
        response = await ga4_client.fetch_traffic_sources(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 7),
        )
        
        assert isinstance(response, GA4ReportResponse)
        ga4_client.client.run_report.assert_called_once()


class TestCreateGA4Client:
    """Test factory function for creating GA4 client."""
    
    def test_create_client_from_dict(self, tenant_id):
        """Test creating client from credentials dictionary."""
        credentials_dict = {
            "access_token": "mock_access_token",
            "refresh_token": "mock_refresh_token",
            "client_id": "mock_client_id.apps.googleusercontent.com",
            "client_secret": "mock_client_secret",
        }
        
        with patch('server.services.ga4.ga4_client.BetaAnalyticsDataClient'):
            client = create_ga4_client(
                credentials=credentials_dict,
                property_id="123456789",
                tenant_id=tenant_id,
            )
            
            assert isinstance(client, GA4Client)
            assert client.property_id == "properties/123456789"
            assert client.tenant_id == tenant_id

