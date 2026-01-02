"""
Reporting Services Module

Provides reporting, comparison, and analytics services.
"""

from .comparison_engine import (
    ComparisonEngine,
    DateRangeCalculator,
    PeriodType,
    ComparisonPeriod,
    MetricComparison,
    PeriodComparisonResult,
)

__all__ = [
    "ComparisonEngine",
    "DateRangeCalculator",
    "PeriodType",
    "ComparisonPeriod",
    "MetricComparison",
    "PeriodComparisonResult",
]

