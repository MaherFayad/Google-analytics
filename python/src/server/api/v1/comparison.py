"""
Period Comparison API Endpoints

Implements Task P0-15: Historical Period Comparison Engine

Provides REST endpoints for period-over-period metric comparisons.
"""

import logging
from datetime import date
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_session
from ...services.reporting.comparison_engine import (
    ComparisonEngine,
    PeriodType,
    PeriodComparisonResult,
)
from ...services.ga4.data_fetcher import GA4FetchError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/comparison", tags=["comparison"])


class ComparisonRequest(BaseModel):
    """Request model for period comparison."""
    
    user_id: str = Field(description="User UUID")
    tenant_id: str = Field(description="Tenant UUID")
    property_id: str = Field(description="GA4 property ID")
    period_type: str = Field(
        default=PeriodType.WEEK_OVER_WEEK,
        description="Type of comparison (week_over_week, month_over_month, year_over_year, custom)"
    )
    current_start: Optional[str] = Field(
        default=None,
        description="Custom period start date (YYYY-MM-DD, required for custom period_type)"
    )
    current_end: Optional[str] = Field(
        default=None,
        description="Custom period end date (YYYY-MM-DD, required for custom period_type)"
    )
    reference_date: Optional[str] = Field(
        default=None,
        description="Reference date for automatic period calculation (YYYY-MM-DD, defaults to yesterday)"
    )
    metrics: Optional[List[str]] = Field(
        default=None,
        description="List of metrics to compare (defaults to sessions, pageViews, bounceRate, avgSessionDuration)"
    )


@router.post(
    "/",
    response_model=PeriodComparisonResult,
    status_code=status.HTTP_200_OK,
    summary="Compare metrics across periods",
    description="""
    Task P0-15: Historical Period Comparison Engine
    
    Compare GA4 metrics across two time periods (current vs previous).
    
    Supported period types:
    - week_over_week: Compare current week with previous week
    - month_over_month: Compare current month with previous month  
    - year_over_year: Compare current year with previous year
    - custom: Compare custom date ranges
    
    Returns:
    - Metric values for both periods
    - Absolute and percentage changes
    - Trend indicators (up/down/neutral)
    - Human-readable summary
    
    Example queries:
    - "Show me last week's sessions compared to the previous week"
    - "Compare this month's conversions with last month"
    - "Year-over-year traffic analysis"
    """
)
async def compare_periods(
    request: ComparisonRequest,
    session: AsyncSession = Depends(get_session),
) -> PeriodComparisonResult:
    """
    Compare metrics across two periods.
    
    Args:
        request: Comparison request parameters
        session: Database session
        
    Returns:
        PeriodComparisonResult with comparison data
    """
    try:
        # Parse UUIDs
        try:
            user_uuid = UUID(request.user_id)
            tenant_uuid = UUID(request.tenant_id)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid UUID format: {e}"
            )
        
        # Parse dates
        current_start_date = None
        current_end_date = None
        reference_date_obj = None
        
        if request.current_start:
            try:
                current_start_date = date.fromisoformat(request.current_start)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid current_start date format: {request.current_start}"
                )
        
        if request.current_end:
            try:
                current_end_date = date.fromisoformat(request.current_end)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid current_end date format: {request.current_end}"
                )
        
        if request.reference_date:
            try:
                reference_date_obj = date.fromisoformat(request.reference_date)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid reference_date format: {request.reference_date}"
                )
        
        # Validate custom period
        if request.period_type == PeriodType.CUSTOM:
            if not current_start_date or not current_end_date:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Custom period requires both current_start and current_end"
                )
            if current_start_date > current_end_date:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="current_start must be before or equal to current_end"
                )
        
        logger.info(
            f"Processing comparison request",
            extra={
                "tenant_id": request.tenant_id,
                "property_id": request.property_id,
                "period_type": request.period_type
            }
        )
        
        # Execute comparison
        engine = ComparisonEngine(session)
        result = await engine.compare_periods(
            user_id=user_uuid,
            tenant_id=tenant_uuid,
            property_id=request.property_id,
            period_type=request.period_type,
            current_start=current_start_date,
            current_end=current_end_date,
            reference_date=reference_date_obj,
            metrics=request.metrics
        )
        
        logger.info(
            f"Comparison completed successfully",
            extra={
                "tenant_id": request.tenant_id,
                "metrics_count": len(result.metrics)
            }
        )
        
        return result
        
    except GA4FetchError as e:
        logger.error(f"GA4 fetch error during comparison: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch GA4 data: {str(e)}"
        )
    except ValueError as e:
        logger.error(f"Validation error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error during comparison: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Comparison failed: {str(e)}"
        )


@router.get(
    "/quick-summary",
    summary="Quick comparison summary",
    description="Get a quick week-over-week comparison summary"
)
async def quick_comparison(
    user_id: str = Query(..., description="User UUID"),
    tenant_id: str = Query(..., description="Tenant UUID"),
    property_id: str = Query(..., description="GA4 property ID"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Get a quick week-over-week comparison summary.
    
    Convenience endpoint for dashboards.
    
    Args:
        user_id: User UUID
        tenant_id: Tenant UUID
        property_id: GA4 property ID
        session: Database session
        
    Returns:
        Simplified comparison summary
    """
    request = ComparisonRequest(
        user_id=user_id,
        tenant_id=tenant_id,
        property_id=property_id,
        period_type=PeriodType.WEEK_OVER_WEEK,
        metrics=["sessions", "screenPageViews"]  # Just key metrics
    )
    
    result = await compare_periods(request, session)
    
    # Simplify response
    return {
        "period": f"{result.current_period.label} vs {result.previous_period.label}",
        "metrics": [
            {
                "name": m.metric_name,
                "change": m.formatted_change,
                "trend": m.trend
            }
            for m in result.metrics
        ],
        "summary": result.summary
    }

