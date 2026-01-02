"""
Unit Tests for Historical Period Comparison Engine

Tests Task P0-15: Historical Period Comparison Engine
"""

import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from python.src.server.services.reporting.comparison_engine import (
    DateRangeCalculator,
    ComparisonEngine,
    PeriodType,
    ComparisonPeriod,
    MetricComparison,
)
from python.src.server.services.ga4.data_fetcher import GA4FetchError


class TestDateRangeCalculator:
    """Test date range calculation logic."""
    
    def test_week_over_week_calculation(self):
        """Test week-over-week period calculation."""
        calculator = DateRangeCalculator()
        
        # Test with a Wednesday (2025-01-15)
        reference = date(2025, 1, 15)
        current, previous = calculator.calculate_week_over_week(reference)
        
        # Current week should be Mon-Sun containing reference date
        assert current.start_date == date(2025, 1, 12)  # Monday
        assert current.end_date == date(2025, 1, 12)    # Sunday (same week as ref, but we go to most recent Sunday)
        assert current.label == "Current Week"
        assert current.days == 1
        
        # Previous week should be 7 days before
        assert previous.start_date == date(2025, 1, 5)
        assert previous.end_date == date(2025, 1, 11)
        assert previous.label == "Previous Week"
    
    def test_month_over_month_calculation(self):
        """Test month-over-month period calculation."""
        calculator = DateRangeCalculator()
        
        # Test with mid-month date
        reference = date(2025, 1, 15)
        current, previous = calculator.calculate_month_over_month(reference)
        
        assert current.start_date == date(2025, 1, 1)
        assert current.end_date == date(2025, 1, 15)
        assert "January 2025" in current.label
        
        assert previous.start_date == date(2024, 12, 1)
        assert previous.end_date == date(2024, 12, 15)
        assert "December 2024" in previous.label
    
    def test_month_over_month_edge_case(self):
        """Test month-over-month with month-end date (Jan 31)."""
        calculator = DateRangeCalculator()
        
        # January 31st
        reference = date(2025, 1, 31)
        current, previous = calculator.calculate_month_over_month(reference)
        
        assert current.start_date == date(2025, 1, 1)
        assert current.end_date == date(2025, 1, 31)
        
        # December only has 31 days, so should match
        assert previous.start_date == date(2024, 12, 1)
        assert previous.end_date == date(2024, 12, 31)
    
    def test_year_over_year_calculation(self):
        """Test year-over-year period calculation."""
        calculator = DateRangeCalculator()
        
        reference = date(2025, 6, 15)
        current, previous = calculator.calculate_year_over_year(reference)
        
        assert current.start_date == date(2025, 1, 1)
        assert current.end_date == date(2025, 6, 15)
        assert current.label == "2025"
        
        assert previous.start_date == date(2024, 1, 1)
        assert previous.end_date == date(2024, 6, 15)
        assert previous.label == "2024"
    
    def test_custom_period_calculation(self):
        """Test custom period calculation."""
        calculator = DateRangeCalculator()
        
        # 7-day custom period
        current_start = date(2025, 1, 10)
        current_end = date(2025, 1, 16)
        
        current, previous = calculator.calculate_custom(current_start, current_end)
        
        assert current.start_date == date(2025, 1, 10)
        assert current.end_date == date(2025, 1, 16)
        assert current.days == 7
        
        # Previous should be 7 days before
        assert previous.start_date == date(2025, 1, 3)
        assert previous.end_date == date(2025, 1, 9)
        assert previous.days == 7


class TestComparisonEngine:
    """Test comparison engine logic."""
    
    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return AsyncMock()
    
    @pytest.fixture
    def mock_fetcher_data(self):
        """Mock GA4 fetcher data."""
        # Current period data (higher values)
        current_data = [
            {
                "metrics": {
                    "sessions": 1000,
                    "screenPageViews": 5000,
                    "bounceRate": 45.5,
                    "averageSessionDuration": 120
                }
            },
            {
                "metrics": {
                    "sessions": 1200,
                    "screenPageViews": 5500,
                    "bounceRate": 43.2,
                    "averageSessionDuration": 130
                }
            }
        ]
        
        # Previous period data (lower values)
        previous_data = [
            {
                "metrics": {
                    "sessions": 800,
                    "screenPageViews": 4000,
                    "bounceRate": 50.0,
                    "averageSessionDuration": 110
                }
            },
            {
                "metrics": {
                    "sessions": 900,
                    "screenPageViews": 4200,
                    "bounceRate": 48.0,
                    "averageSessionDuration": 115
                }
            }
        ]
        
        return current_data, previous_data
    
    @pytest.mark.asyncio
    async def test_compare_periods_week_over_week(self, mock_session, mock_fetcher_data):
        """Test week-over-week comparison."""
        current_data, previous_data = mock_fetcher_data
        
        engine = ComparisonEngine(mock_session)
        
        # Mock the fetcher
        with patch.object(engine.fetcher, 'fetch_daily_metrics', side_effect=[current_data, previous_data]):
            result = await engine.compare_periods(
                user_id=uuid4(),
                tenant_id=uuid4(),
                property_id="123456789",
                period_type=PeriodType.WEEK_OVER_WEEK
            )
        
        assert result.period_type == PeriodType.WEEK_OVER_WEEK
        assert len(result.metrics) == 4  # 4 default metrics
        
        # Check sessions comparison
        sessions_comp = next(m for m in result.metrics if m.metric_name == "sessions")
        assert sessions_comp.current_value == 2200  # 1000 + 1200
        assert sessions_comp.previous_value == 1700  # 800 + 900
        assert sessions_comp.absolute_change == 500
        assert sessions_comp.percent_change == pytest.approx(29.41, rel=0.1)
        assert sessions_comp.trend == "up"
    
    @pytest.mark.asyncio
    async def test_compare_periods_custom(self, mock_session, mock_fetcher_data):
        """Test custom period comparison."""
        current_data, previous_data = mock_fetcher_data
        
        engine = ComparisonEngine(mock_session)
        
        with patch.object(engine.fetcher, 'fetch_daily_metrics', side_effect=[current_data, previous_data]):
            result = await engine.compare_periods(
                user_id=uuid4(),
                tenant_id=uuid4(),
                property_id="123456789",
                period_type=PeriodType.CUSTOM,
                current_start=date(2025, 1, 10),
                current_end=date(2025, 1, 16)
            )
        
        assert result.period_type == PeriodType.CUSTOM
        assert result.current_period.start_date == date(2025, 1, 10)
        assert result.previous_period.start_date == date(2025, 1, 3)
    
    @pytest.mark.asyncio
    async def test_compare_periods_with_custom_metrics(self, mock_session):
        """Test comparison with custom metrics list."""
        current_data = [{"metrics": {"sessions": 1000, "conversions": 50}}]
        previous_data = [{"metrics": {"sessions": 800, "conversions": 40}}]
        
        engine = ComparisonEngine(mock_session)
        
        with patch.object(engine.fetcher, 'fetch_daily_metrics', side_effect=[current_data, previous_data]):
            result = await engine.compare_periods(
                user_id=uuid4(),
                tenant_id=uuid4(),
                property_id="123456789",
                period_type=PeriodType.WEEK_OVER_WEEK,
                metrics=["sessions", "conversions"]
            )
        
        assert len(result.metrics) == 2
        metric_names = [m.metric_name for m in result.metrics]
        assert "sessions" in metric_names
        assert "conversions" in metric_names
    
    @pytest.mark.asyncio
    async def test_compare_periods_ga4_fetch_error(self, mock_session):
        """Test error handling when GA4 fetch fails."""
        engine = ComparisonEngine(mock_session)
        
        # Mock fetcher to raise error
        with patch.object(engine.fetcher, 'fetch_daily_metrics', side_effect=GA4FetchError("API error")):
            with pytest.raises(GA4FetchError):
                await engine.compare_periods(
                    user_id=uuid4(),
                    tenant_id=uuid4(),
                    property_id="123456789",
                    period_type=PeriodType.WEEK_OVER_WEEK
                )
    
    def test_aggregate_metrics(self, mock_session):
        """Test metric aggregation."""
        engine = ComparisonEngine(mock_session)
        
        data = [
            {"metrics": {"sessions": 100, "pageViews": 500}},
            {"metrics": {"sessions": 150, "pageViews": 600}},
            {"metrics": {"sessions": 200, "pageViews": 700}},
        ]
        
        totals = engine._aggregate_metrics(data, ["sessions", "pageViews"])
        
        assert totals["sessions"] == 450
        assert totals["pageViews"] == 1800
    
    def test_calculate_metric_comparison_positive_change(self, mock_session):
        """Test metric comparison with positive change."""
        engine = ComparisonEngine(mock_session)
        
        comp = engine._calculate_metric_comparison(
            metric_name="sessions",
            current_value=1200,
            previous_value=1000
        )
        
        assert comp.current_value == 1200
        assert comp.previous_value == 1000
        assert comp.absolute_change == 200
        assert comp.percent_change == 20.0
        assert comp.trend == "up"
        assert comp.formatted_change == "+20.0%"
    
    def test_calculate_metric_comparison_negative_change(self, mock_session):
        """Test metric comparison with negative change."""
        engine = ComparisonEngine(mock_session)
        
        comp = engine._calculate_metric_comparison(
            metric_name="bounceRate",
            current_value=40.0,
            previous_value=50.0
        )
        
        assert comp.absolute_change == -10.0
        assert comp.percent_change == -20.0
        assert comp.trend == "down"
        assert comp.formatted_change == "-20.0%"
    
    def test_calculate_metric_comparison_zero_previous(self, mock_session):
        """Test metric comparison when previous value is zero."""
        engine = ComparisonEngine(mock_session)
        
        comp = engine._calculate_metric_comparison(
            metric_name="newMetric",
            current_value=100,
            previous_value=0
        )
        
        assert comp.percent_change is None
        assert comp.trend == "up"
        assert "100" in comp.formatted_change  # Should show absolute value
    
    def test_calculate_metric_comparison_neutral_trend(self, mock_session):
        """Test metric comparison with neutral trend (<1% change)."""
        engine = ComparisonEngine(mock_session)
        
        comp = engine._calculate_metric_comparison(
            metric_name="sessions",
            current_value=1005,
            previous_value=1000
        )
        
        assert comp.percent_change == 0.5
        assert comp.trend == "neutral"  # Less than 1% change
    
    def test_format_metric_value_count(self, mock_session):
        """Test formatting for count metrics."""
        engine = ComparisonEngine(mock_session)
        
        formatted = engine._format_metric_value("sessions", 12450)
        assert formatted == "12,450"
    
    def test_format_metric_value_percentage(self, mock_session):
        """Test formatting for percentage metrics."""
        engine = ComparisonEngine(mock_session)
        
        formatted = engine._format_metric_value("bounceRate", 45.67)
        assert formatted == "45.7%"
    
    def test_format_metric_value_duration(self, mock_session):
        """Test formatting for duration metrics."""
        engine = ComparisonEngine(mock_session)
        
        # Seconds
        formatted = engine._format_metric_value("averageSessionDuration", 45)
        assert formatted == "45s"
        
        # Minutes
        formatted = engine._format_metric_value("averageSessionDuration", 125)
        assert formatted == "2.1m"
        
        # Hours
        formatted = engine._format_metric_value("averageSessionDuration", 7200)
        assert formatted == "2.0h"
    
    def test_generate_summary(self, mock_session):
        """Test summary generation."""
        engine = ComparisonEngine(mock_session)
        
        current = ComparisonPeriod(
            start_date=date(2025, 1, 6),
            end_date=date(2025, 1, 12),
            label="Current Week"
        )
        
        previous = ComparisonPeriod(
            start_date=date(2024, 12, 30),
            end_date=date(2025, 1, 5),
            label="Previous Week"
        )
        
        comparisons = [
            MetricComparison(
                metric_name="sessions",
                current_value=1200,
                previous_value=1000,
                absolute_change=200,
                percent_change=20.0,
                trend="up",
                formatted_current="1,200",
                formatted_previous="1,000",
                formatted_change="+20.0%"
            )
        ]
        
        summary = engine._generate_summary(current, previous, comparisons)
        
        assert "Current Week" in summary
        assert "Previous Week" in summary
        assert "sessions" in summary
        assert "+20.0%" in summary
        assert "📈" in summary  # Up emoji

