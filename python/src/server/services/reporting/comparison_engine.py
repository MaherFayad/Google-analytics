"""
Historical Period Comparison Engine

Implements Task P0-15: Historical Period Comparison Engine [MEDIUM]

Features:
- Period-over-period comparison (week-over-week, month-over-month, etc.)
- Automatic date range calculation
- Percentage change and absolute difference calculation
- Support for multiple metrics
- Formatted output for ReportingAgent integration
"""

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Literal
from uuid import UUID
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..ga4.data_fetcher import GA4DataFetcher, GA4FetchError

logger = logging.getLogger(__name__)


# ========== Comparison Models ==========

class PeriodType(str):
    """Supported comparison period types."""
    
    WEEK_OVER_WEEK = "week_over_week"
    MONTH_OVER_MONTH = "month_over_month"
    YEAR_OVER_YEAR = "year_over_year"
    CUSTOM = "custom"


class ComparisonPeriod(BaseModel):
    """Date range for a comparison period."""
    
    start_date: date
    end_date: date
    label: str = Field(description="Human-readable label (e.g., 'Current Week')")
    
    @property
    def days(self) -> int:
        """Calculate number of days in the period."""
        return (self.end_date - self.start_date).days + 1


class MetricComparison(BaseModel):
    """Comparison result for a single metric."""
    
    metric_name: str
    current_value: float
    previous_value: float
    absolute_change: float
    percent_change: Optional[float] = None  # None if previous_value is 0
    trend: Literal["up", "down", "neutral"]
    formatted_current: str
    formatted_previous: str
    formatted_change: str


class PeriodComparisonResult(BaseModel):
    """Complete period comparison result."""
    
    current_period: ComparisonPeriod
    previous_period: ComparisonPeriod
    period_type: str
    metrics: List[MetricComparison]
    summary: str = Field(description="Human-readable summary")


# ========== Date Range Calculator ==========

class DateRangeCalculator:
    """Calculate current and previous date ranges for comparisons."""
    
    @staticmethod
    def calculate_week_over_week(
        reference_date: Optional[date] = None
    ) -> Tuple[ComparisonPeriod, ComparisonPeriod]:
        """
        Calculate week-over-week comparison periods.
        
        Args:
            reference_date: Reference date (defaults to yesterday)
            
        Returns:
            Tuple of (current_period, previous_period)
            
        Example:
            If reference_date is 2025-01-15 (Wednesday):
            - Current: 2025-01-09 to 2025-01-15 (Mon-Sun, 7 days)
            - Previous: 2025-01-02 to 2025-01-08 (Mon-Sun, 7 days)
        """
        if not reference_date:
            reference_date = date.today() - timedelta(days=1)
        
        # Find the most recent Sunday (end of current week)
        days_since_sunday = (reference_date.weekday() + 1) % 7
        current_end = reference_date - timedelta(days=days_since_sunday)
        current_start = current_end - timedelta(days=6)
        
        # Previous week
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=6)
        
        current = ComparisonPeriod(
            start_date=current_start,
            end_date=current_end,
            label="Current Week"
        )
        
        previous = ComparisonPeriod(
            start_date=previous_start,
            end_date=previous_end,
            label="Previous Week"
        )
        
        return current, previous
    
    @staticmethod
    def calculate_month_over_month(
        reference_date: Optional[date] = None
    ) -> Tuple[ComparisonPeriod, ComparisonPeriod]:
        """
        Calculate month-over-month comparison periods.
        
        Args:
            reference_date: Reference date (defaults to yesterday)
            
        Returns:
            Tuple of (current_period, previous_period)
            
        Example:
            If reference_date is 2025-01-15:
            - Current: 2025-01-01 to 2025-01-15
            - Previous: 2024-12-01 to 2024-12-15
        """
        if not reference_date:
            reference_date = date.today() - timedelta(days=1)
        
        # Current month from 1st to reference_date
        current_start = reference_date.replace(day=1)
        current_end = reference_date
        
        # Previous month, same day range
        # Calculate the first day of previous month
        if current_start.month == 1:
            previous_month_start = current_start.replace(year=current_start.year - 1, month=12, day=1)
        else:
            previous_month_start = current_start.replace(month=current_start.month - 1, day=1)
        
        # Try to match the same day, but handle month-end edge cases
        try:
            previous_end = previous_month_start.replace(day=reference_date.day)
        except ValueError:
            # If day doesn't exist in previous month (e.g., Jan 31 -> Feb 28), use last day
            import calendar
            last_day = calendar.monthrange(previous_month_start.year, previous_month_start.month)[1]
            previous_end = previous_month_start.replace(day=last_day)
        
        current = ComparisonPeriod(
            start_date=current_start,
            end_date=current_end,
            label=f"{current_start.strftime('%B %Y')}"
        )
        
        previous = ComparisonPeriod(
            start_date=previous_month_start,
            end_date=previous_end,
            label=f"{previous_month_start.strftime('%B %Y')}"
        )
        
        return current, previous
    
    @staticmethod
    def calculate_year_over_year(
        reference_date: Optional[date] = None
    ) -> Tuple[ComparisonPeriod, ComparisonPeriod]:
        """
        Calculate year-over-year comparison periods.
        
        Args:
            reference_date: Reference date (defaults to yesterday)
            
        Returns:
            Tuple of (current_period, previous_period)
        """
        if not reference_date:
            reference_date = date.today() - timedelta(days=1)
        
        # Current year from Jan 1 to reference_date
        current_start = reference_date.replace(month=1, day=1)
        current_end = reference_date
        
        # Previous year, same date range
        previous_start = current_start.replace(year=current_start.year - 1)
        previous_end = current_end.replace(year=current_end.year - 1)
        
        current = ComparisonPeriod(
            start_date=current_start,
            end_date=current_end,
            label=f"{current_start.year}"
        )
        
        previous = ComparisonPeriod(
            start_date=previous_start,
            end_date=previous_end,
            label=f"{previous_start.year}"
        )
        
        return current, previous
    
    @staticmethod
    def calculate_custom(
        current_start: date,
        current_end: date
    ) -> Tuple[ComparisonPeriod, ComparisonPeriod]:
        """
        Calculate custom period comparison.
        
        Previous period has same length, immediately before current period.
        
        Args:
            current_start: Start date of current period
            current_end: End date of current period
            
        Returns:
            Tuple of (current_period, previous_period)
        """
        period_length = (current_end - current_start).days + 1
        
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=period_length - 1)
        
        current = ComparisonPeriod(
            start_date=current_start,
            end_date=current_end,
            label="Current Period"
        )
        
        previous = ComparisonPeriod(
            start_date=previous_start,
            end_date=previous_end,
            label="Previous Period"
        )
        
        return current, previous


# ========== Comparison Engine ==========

class ComparisonEngine:
    """
    Historical period comparison engine for GA4 metrics.
    
    Implements Task P0-15: Fetch two date ranges, calculate changes,
    and provide formatted comparison data for visualization.
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize comparison engine.
        
        Args:
            session: Database session
        """
        self.session = session
        self.fetcher = GA4DataFetcher(session)
        self.calculator = DateRangeCalculator()
    
    async def compare_periods(
        self,
        user_id: UUID,
        tenant_id: UUID,
        property_id: str,
        period_type: str = PeriodType.WEEK_OVER_WEEK,
        current_start: Optional[date] = None,
        current_end: Optional[date] = None,
        reference_date: Optional[date] = None,
        metrics: Optional[List[str]] = None
    ) -> PeriodComparisonResult:
        """
        Compare metrics across two time periods.
        
        Args:
            user_id: User UUID
            tenant_id: Tenant UUID
            property_id: GA4 property ID
            period_type: Type of comparison (week_over_week, month_over_month, etc.)
            current_start: Custom current period start (for custom period_type)
            current_end: Custom current period end (for custom period_type)
            reference_date: Reference date for automatic period calculation
            metrics: List of metric names to compare (defaults to common metrics)
            
        Returns:
            PeriodComparisonResult with comparison data
            
        Raises:
            GA4FetchError: If data fetching fails
            ValueError: If invalid period_type or dates
            
        Example:
            ```python
            engine = ComparisonEngine(session)
            result = await engine.compare_periods(
                user_id=user_uuid,
                tenant_id=tenant_uuid,
                property_id="123456789",
                period_type="week_over_week"
            )
            print(result.summary)
            for metric in result.metrics:
                print(f"{metric.metric_name}: {metric.formatted_change}")
            ```
        """
        # Default metrics if not specified
        if not metrics:
            metrics = ["sessions", "screenPageViews", "bounceRate", "averageSessionDuration"]
        
        # Calculate date ranges
        if period_type == PeriodType.WEEK_OVER_WEEK:
            current, previous = self.calculator.calculate_week_over_week(reference_date)
        elif period_type == PeriodType.MONTH_OVER_MONTH:
            current, previous = self.calculator.calculate_month_over_month(reference_date)
        elif period_type == PeriodType.YEAR_OVER_YEAR:
            current, previous = self.calculator.calculate_year_over_year(reference_date)
        elif period_type == PeriodType.CUSTOM:
            if not current_start or not current_end:
                raise ValueError("Custom period requires current_start and current_end")
            current, previous = self.calculator.calculate_custom(current_start, current_end)
        else:
            raise ValueError(f"Invalid period_type: {period_type}")
        
        logger.info(
            f"Comparing periods: {period_type}",
            extra={
                "tenant_id": str(tenant_id),
                "current": f"{current.start_date} to {current.end_date}",
                "previous": f"{previous.start_date} to {previous.end_date}"
            }
        )
        
        # Fetch data for both periods
        try:
            current_data = await self.fetcher.fetch_daily_metrics(
                user_id=user_id,
                tenant_id=tenant_id,
                property_id=property_id,
                start_date=current.start_date,
                end_date=current.end_date
            )
            
            previous_data = await self.fetcher.fetch_daily_metrics(
                user_id=user_id,
                tenant_id=tenant_id,
                property_id=property_id,
                start_date=previous.start_date,
                end_date=previous.end_date
            )
        except Exception as e:
            logger.error(f"Failed to fetch comparison data: {e}", exc_info=True)
            raise GA4FetchError(f"Comparison data fetch failed: {e}") from e
        
        # Aggregate metrics for each period
        current_totals = self._aggregate_metrics(current_data, metrics)
        previous_totals = self._aggregate_metrics(previous_data, metrics)
        
        # Calculate comparisons
        comparisons = []
        for metric_name in metrics:
            current_val = current_totals.get(metric_name, 0.0)
            previous_val = previous_totals.get(metric_name, 0.0)
            
            comparison = self._calculate_metric_comparison(
                metric_name=metric_name,
                current_value=current_val,
                previous_value=previous_val
            )
            comparisons.append(comparison)
        
        # Generate summary
        summary = self._generate_summary(current, previous, comparisons)
        
        return PeriodComparisonResult(
            current_period=current,
            previous_period=previous,
            period_type=period_type,
            metrics=comparisons,
            summary=summary
        )
    
    def _aggregate_metrics(
        self,
        data: List[Dict[str, Any]],
        metric_names: List[str]
    ) -> Dict[str, float]:
        """
        Aggregate metrics from raw data.
        
        Args:
            data: List of metric records from database
            metric_names: List of metric names to aggregate
            
        Returns:
            Dictionary of metric_name -> total_value
        """
        totals = {metric: 0.0 for metric in metric_names}
        
        for record in data:
            metrics = record.get("metrics", {})
            for metric_name in metric_names:
                if metric_name in metrics:
                    totals[metric_name] += float(metrics[metric_name])
        
        return totals
    
    def _calculate_metric_comparison(
        self,
        metric_name: str,
        current_value: float,
        previous_value: float
    ) -> MetricComparison:
        """
        Calculate comparison metrics for a single metric.
        
        Args:
            metric_name: Name of the metric
            current_value: Current period value
            previous_value: Previous period value
            
        Returns:
            MetricComparison with calculated changes
        """
        absolute_change = current_value - previous_value
        
        # Calculate percentage change
        if previous_value == 0:
            percent_change = None  # Undefined
            trend = "up" if current_value > 0 else "neutral"
        else:
            percent_change = (absolute_change / previous_value) * 100
            
            # Determine trend
            if abs(percent_change) < 1.0:  # Less than 1% change
                trend = "neutral"
            elif percent_change > 0:
                trend = "up"
            else:
                trend = "down"
        
        # Format values
        formatted_current = self._format_metric_value(metric_name, current_value)
        formatted_previous = self._format_metric_value(metric_name, previous_value)
        
        if percent_change is None:
            formatted_change = f"+{formatted_current}" if current_value > 0 else "N/A"
        else:
            sign = "+" if percent_change >= 0 else ""
            formatted_change = f"{sign}{percent_change:.1f}%"
        
        return MetricComparison(
            metric_name=metric_name,
            current_value=current_value,
            previous_value=previous_value,
            absolute_change=absolute_change,
            percent_change=percent_change,
            trend=trend,
            formatted_current=formatted_current,
            formatted_previous=formatted_previous,
            formatted_change=formatted_change
        )
    
    def _format_metric_value(self, metric_name: str, value: float) -> str:
        """Format metric value based on metric type."""
        
        # Percentage metrics
        if "rate" in metric_name.lower() or "percentage" in metric_name.lower():
            return f"{value:.1f}%"
        
        # Duration metrics (in seconds)
        if "duration" in metric_name.lower() or "time" in metric_name.lower():
            if value < 60:
                return f"{value:.0f}s"
            elif value < 3600:
                return f"{value / 60:.1f}m"
            else:
                return f"{value / 3600:.1f}h"
        
        # Count metrics
        return f"{int(value):,}"
    
    def _generate_summary(
        self,
        current: ComparisonPeriod,
        previous: ComparisonPeriod,
        comparisons: List[MetricComparison]
    ) -> str:
        """
        Generate human-readable summary of comparison.
        
        Args:
            current: Current period
            previous: Previous period
            comparisons: List of metric comparisons
            
        Returns:
            Summary string
        """
        lines = [
            f"Comparing {current.label} ({current.start_date} to {current.end_date}) "
            f"with {previous.label} ({previous.start_date} to {previous.end_date}):",
            ""
        ]
        
        for comp in comparisons:
            emoji = "📈" if comp.trend == "up" else "📉" if comp.trend == "down" else "➡️"
            lines.append(
                f"{emoji} {comp.metric_name}: {comp.formatted_current} "
                f"(was {comp.formatted_previous}, {comp.formatted_change})"
            )
        
        return "\n".join(lines)

