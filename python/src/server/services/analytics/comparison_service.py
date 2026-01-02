"""
Comparison Service for Analytics.

Implements Task P0-15: Historical Period Comparison Engine [MEDIUM]

Provides simplified interface to comparison engine for API endpoints.
Handles common use cases like week-over-week, month-over-month comparisons.

Example:
    ```python
    from server.services.analytics.comparison_service import ComparisonService
    
    service = ComparisonService(db_session)
    
    # Week-over-week comparison
    result = await service.compare_week_over_week(
        tenant_id=tenant_uuid,
        user_id=user_uuid,
        property_id="123456789"
    )
    
    print(f"Sessions: {result['metrics']['sessions']['change']}")
    ```
"""

import logging
from datetime import date
from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..reporting.comparison_engine import (
    ComparisonEngine,
    PeriodType,
    PeriodComparisonResult
)

logger = logging.getLogger(__name__)


class ComparisonService:
    """
    Service layer for period-over-period comparisons.
    
    Provides simplified API for common comparison operations.
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize comparison service."""
        self.session = session
        self.engine = ComparisonEngine(session)
    
    async def compare_week_over_week(
        self,
        tenant_id: UUID,
        user_id: UUID,
        property_id: str,
        reference_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Compare current week with previous week.
        
        Args:
            tenant_id: Tenant UUID
            user_id: User UUID
            property_id: GA4 property ID
            reference_date: Optional reference date (defaults to yesterday)
            
        Returns:
            Formatted comparison result dictionary
        """
        result = await self.engine.compare_periods(
            user_id=user_id,
            tenant_id=tenant_id,
            property_id=property_id,
            period_type=PeriodType.WEEK_OVER_WEEK,
            reference_date=reference_date
        )
        
        return self._format_result(result)
    
    async def compare_month_over_month(
        self,
        tenant_id: UUID,
        user_id: UUID,
        property_id: str,
        reference_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Compare current month with previous month.
        
        Args:
            tenant_id: Tenant UUID
            user_id: User UUID
            property_id: GA4 property ID
            reference_date: Optional reference date (defaults to yesterday)
            
        Returns:
            Formatted comparison result dictionary
        """
        result = await self.engine.compare_periods(
            user_id=user_id,
            tenant_id=tenant_id,
            property_id=property_id,
            period_type=PeriodType.MONTH_OVER_MONTH,
            reference_date=reference_date
        )
        
        return self._format_result(result)
    
    async def compare_year_over_year(
        self,
        tenant_id: UUID,
        user_id: UUID,
        property_id: str,
        reference_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Compare current year with previous year.
        
        Args:
            tenant_id: Tenant UUID
            user_id: User UUID
            property_id: GA4 property ID
            reference_date: Optional reference date (defaults to yesterday)
            
        Returns:
            Formatted comparison result dictionary
        """
        result = await self.engine.compare_periods(
            user_id=user_id,
            tenant_id=tenant_id,
            property_id=property_id,
            period_type=PeriodType.YEAR_OVER_YEAR,
            reference_date=reference_date
        )
        
        return self._format_result(result)
    
    async def compare_custom_period(
        self,
        tenant_id: UUID,
        user_id: UUID,
        property_id: str,
        current_start: date,
        current_end: date,
        metrics: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Compare custom period with previous period of same length.
        
        Args:
            tenant_id: Tenant UUID
            user_id: User UUID
            property_id: GA4 property ID
            current_start: Start date of current period
            current_end: End date of current period
            metrics: Optional list of metrics to compare
            
        Returns:
            Formatted comparison result dictionary
        """
        result = await self.engine.compare_periods(
            user_id=user_id,
            tenant_id=tenant_id,
            property_id=property_id,
            period_type=PeriodType.CUSTOM,
            current_start=current_start,
            current_end=current_end,
            metrics=metrics
        )
        
        return self._format_result(result)
    
    def _format_result(self, result: PeriodComparisonResult) -> Dict[str, Any]:
        """
        Format comparison result for API response.
        
        Args:
            result: PeriodComparisonResult from engine
            
        Returns:
            Dictionary with formatted comparison data
        """
        metrics_dict = {}
        
        for metric_comp in result.metrics:
            metrics_dict[metric_comp.metric_name] = {
                "current": metric_comp.current_value,
                "previous": metric_comp.previous_value,
                "change": metric_comp.absolute_change,
                "percent_change": metric_comp.percent_change,
                "trend": metric_comp.trend,
                "formatted": {
                    "current": metric_comp.formatted_current,
                    "previous": metric_comp.formatted_previous,
                    "change": metric_comp.formatted_change
                }
            }
        
        return {
            "period_type": result.period_type,
            "current_period": {
                "label": result.current_period.label,
                "start_date": result.current_period.start_date.isoformat(),
                "end_date": result.current_period.end_date.isoformat(),
                "days": result.current_period.days
            },
            "previous_period": {
                "label": result.previous_period.label,
                "start_date": result.previous_period.start_date.isoformat(),
                "end_date": result.previous_period.end_date.isoformat(),
                "days": result.previous_period.days
            },
            "metrics": metrics_dict,
            "summary": result.summary
        }
    
    async def get_comparison_chart_data(
        self,
        tenant_id: UUID,
        user_id: UUID,
        property_id: str,
        period_type: str = "week_over_week",
        reference_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Get formatted data for comparison charts.
        
        Args:
            tenant_id: Tenant UUID
            user_id: User UUID
            property_id: GA4 property ID
            period_type: Type of comparison
            reference_date: Optional reference date
            
        Returns:
            Chart-ready comparison data
        """
        # Get comparison result
        if period_type == "week_over_week":
            result_dict = await self.compare_week_over_week(
                tenant_id, user_id, property_id, reference_date
            )
        elif period_type == "month_over_month":
            result_dict = await self.compare_month_over_month(
                tenant_id, user_id, property_id, reference_date
            )
        elif period_type == "year_over_year":
            result_dict = await self.compare_year_over_year(
                tenant_id, user_id, property_id, reference_date
            )
        else:
            raise ValueError(f"Invalid period_type: {period_type}")
        
        # Format for chart
        chart_data = []
        for metric_name, metric_data in result_dict["metrics"].items():
            chart_data.append({
                "metric": metric_name,
                "current": metric_data["current"],
                "previous": metric_data["previous"],
                "change_percent": metric_data["percent_change"]
            })
        
        return {
            "type": "comparison",
            "period_type": period_type,
            "current_period": result_dict["current_period"]["label"],
            "previous_period": result_dict["previous_period"]["label"],
            "chart_data": chart_data,
            "summary": result_dict["summary"]
        }


