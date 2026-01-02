"""
Google Analytics 4 Data API tool for Pydantic-AI agents.

This replaces the CrewAI GoogleAnalyticsTool from Task 3.1 with a
Pydantic-AI compatible async function-based tool.

Key improvements over CrewAI version:
- Type-safe with Pydantic V2 models
- Async-first for non-blocking execution
- Integrated with FastAPI/Pydantic ecosystem
- Better error handling and retry logic
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field
from pydantic_ai import RunContext

logger = logging.getLogger(__name__)


class GA4ToolContext(BaseModel):
    """
    Context for GA4 tool execution.
    
    Passed to the tool via RunContext.deps to provide:
    - Authentication credentials
    - Tenant isolation
    - Configuration
    """
    
    tenant_id: str = Field(description="Tenant ID for multi-tenant isolation")
    user_id: str = Field(description="User ID for authentication")
    property_id: str = Field(description="GA4 property ID")
    access_token: str = Field(description="OAuth2 access token (from AuthService)")
    
    # Optional configuration
    api_base_url: str = Field(
        default="https://analyticsdata.googleapis.com/v1beta",
        description="GA4 Data API base URL"
    )
    timeout_seconds: int = Field(
        default=10,
        description="API request timeout"
    )


class GA4Dimension(BaseModel):
    """GA4 dimension for query."""
    name: str


class GA4Metric(BaseModel):
    """GA4 metric for query."""
    name: str


class GA4DateRange(BaseModel):
    """Date range for GA4 query."""
    start_date: str = Field(description="Start date (YYYY-MM-DD)")
    end_date: str = Field(description="End date (YYYY-MM-DD)")


async def fetch_ga4_data(
    ctx: RunContext[GA4ToolContext],
    dimensions: List[str],
    metrics: List[str],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch data from Google Analytics 4 Data API.
    
    This is a Pydantic-AI tool function that agents can call to retrieve GA4 data.
    
    Args:
        ctx: Run context with GA4ToolContext dependencies
        dimensions: List of dimension names (e.g., ["date", "deviceCategory"])
        metrics: List of metric names (e.g., ["sessions", "conversions"])
        start_date: Start date (YYYY-MM-DD), defaults to 7 days ago
        end_date: End date (YYYY-MM-DD), defaults to yesterday
        
    Returns:
        Dict containing GA4 API response with structure:
        {
            "dimensionHeaders": [...],
            "metricHeaders": [...],
            "rows": [
                {
                    "dimensionValues": [...],
                    "metricValues": [...]
                }
            ],
            "rowCount": int,
            "metadata": {...}
        }
        
    Raises:
        httpx.HTTPStatusError: If GA4 API returns error
        ValueError: If invalid parameters provided
        
    Example:
        ```python
        result = await fetch_ga4_data(
            ctx,
            dimensions=["date", "deviceCategory"],
            metrics=["sessions", "conversions"],
            start_date="2025-01-01",
            end_date="2025-01-07"
        )
        ```
    """
    # Get context
    ga4_ctx = ctx.deps
    
    # Default date range: last 7 days
    if not start_date:
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    logger.info(
        f"Fetching GA4 data for tenant {ga4_ctx.tenant_id}",
        extra={
            "property_id": ga4_ctx.property_id,
            "dimensions": dimensions,
            "metrics": metrics,
            "date_range": f"{start_date} to {end_date}"
        }
    )
    
    # Build GA4 API request
    request_body = {
        "dateRanges": [
            {
                "startDate": start_date,
                "endDate": end_date
            }
        ],
        "dimensions": [{"name": dim} for dim in dimensions],
        "metrics": [{"name": metric} for metric in metrics],
    }
    
    # Make API request
    url = f"{ga4_ctx.api_base_url}/properties/{ga4_ctx.property_id}:runReport"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                json=request_body,
                headers={
                    "Authorization": f"Bearer {ga4_ctx.access_token}",
                    "Content-Type": "application/json",
                },
                timeout=ga4_ctx.timeout_seconds,
            )
            
            response.raise_for_status()
            
            data = response.json()
            
            logger.info(
                f"Successfully fetched GA4 data: {data.get('rowCount', 0)} rows",
                extra={
                    "tenant_id": ga4_ctx.tenant_id,
                    "property_id": ga4_ctx.property_id,
                }
            )
            
            return data
            
        except httpx.HTTPStatusError as e:
            logger.error(
                f"GA4 API error: {e.response.status_code}",
                extra={
                    "response_body": e.response.text,
                    "tenant_id": ga4_ctx.tenant_id,
                }
            )
            raise
            
        except httpx.TimeoutException:
            logger.error(
                f"GA4 API timeout after {ga4_ctx.timeout_seconds}s",
                extra={"tenant_id": ga4_ctx.tenant_id}
            )
            raise
            
        except Exception as e:
            logger.error(
                f"Unexpected error fetching GA4 data: {e}",
                exc_info=True,
                extra={"tenant_id": ga4_ctx.tenant_id}
            )
            raise


async def get_ga4_property_info(
    ctx: RunContext[GA4ToolContext]
) -> Dict[str, Any]:
    """
    Get GA4 property metadata.
    
    Args:
        ctx: Run context with GA4ToolContext
        
    Returns:
        Property metadata including name, timezone, currency
    """
    ga4_ctx = ctx.deps
    
    url = f"{ga4_ctx.api_base_url}/properties/{ga4_ctx.property_id}/metadata"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {ga4_ctx.access_token}",
            },
            timeout=ga4_ctx.timeout_seconds,
        )
        
        response.raise_for_status()
        return response.json()

