"""
Unit tests for GA4 tool.

Tests the Pydantic-AI GA4 tool functionality.
"""

import pytest
from unittest.mock import AsyncMock, patch
from pydantic_ai import RunContext

from src.agents.tools.ga4_tool import (
    fetch_ga4_data,
    GA4ToolContext,
)


@pytest.fixture
def ga4_context():
    """Create test GA4 context."""
    return GA4ToolContext(
        tenant_id="test-tenant-123",
        user_id="user-456",
        property_id="123456789",
        access_token="test-token",
    )


@pytest.fixture
def mock_run_context(ga4_context):
    """Create mock RunContext."""
    ctx = AsyncMock(spec=RunContext)
    ctx.deps = ga4_context
    return ctx


class TestGA4Tool:
    """Test suite for GA4 tool."""
    
    @pytest.mark.asyncio
    async def test_fetch_ga4_data_success(self, mock_run_context):
        """Test successful GA4 data fetch."""
        mock_response = {
            "dimensionHeaders": [{"name": "date"}],
            "metricHeaders": [{"name": "sessions"}],
            "rows": [
                {
                    "dimensionValues": [{"value": "2025-01-01"}],
                    "metricValues": [{"value": "1234"}]
                }
            ],
            "rowCount": 1
        }
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response_obj = AsyncMock()
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = AsyncMock()
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response_obj
            )
            
            result = await fetch_ga4_data(
                mock_run_context,
                dimensions=["date"],
                metrics=["sessions"],
                start_date="2025-01-01",
                end_date="2025-01-07"
            )
            
            assert result == mock_response
            assert result["rowCount"] == 1
            assert len(result["rows"]) == 1
    
    @pytest.mark.asyncio
    async def test_fetch_ga4_data_with_defaults(self, mock_run_context):
        """Test GA4 data fetch with default date range."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response_obj = AsyncMock()
            mock_response_obj.json.return_value = {"rowCount": 0, "rows": []}
            mock_response_obj.raise_for_status = AsyncMock()
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response_obj
            )
            
            result = await fetch_ga4_data(
                mock_run_context,
                dimensions=["date"],
                metrics=["sessions"]
            )
            
            assert "rowCount" in result
    
    @pytest.mark.asyncio
    async def test_fetch_ga4_data_api_error(self, mock_run_context):
        """Test GA4 API error handling."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response_obj = AsyncMock()
            mock_response_obj.raise_for_status.side_effect = Exception("API Error")
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response_obj
            )
            
            with pytest.raises(Exception, match="API Error"):
                await fetch_ga4_data(
                    mock_run_context,
                    dimensions=["date"],
                    metrics=["sessions"]
                )
    
    def test_ga4_tool_context_validation(self):
        """Test GA4ToolContext validation."""
        # Valid context
        ctx = GA4ToolContext(
            tenant_id="tenant-123",
            user_id="user-456",
            property_id="prop-789",
            access_token="token"
        )
        
        assert ctx.tenant_id == "tenant-123"
        assert ctx.timeout_seconds == 10  # default
        
        # Custom timeout
        ctx2 = GA4ToolContext(
            tenant_id="tenant-123",
            user_id="user-456",
            property_id="prop-789",
            access_token="token",
            timeout_seconds=30
        )
        
        assert ctx2.timeout_seconds == 30

