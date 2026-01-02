"""
Period Calculator Utility.

Implements Task P0-15: Date range calculation for period comparisons

Provides utility functions for calculating date ranges for various
comparison types (week-over-week, month-over-month, etc.)

Example:
    ```python
    from server.services.analytics.period_calculator import PeriodCalculator
    
    calc = PeriodCalculator()
    
    # Get current week and previous week
    current, previous = calc.get_week_over_week()
    print(f"Current: {current.start} to {current.end}")
    print(f"Previous: {previous.start} to {previous.end}")
    ```
"""

import calendar
from datetime import date, datetime, timedelta
from typing import Tuple, Optional
from dataclasses import dataclass


@dataclass
class DateRange:
    """Represents a date range with start and end dates."""
    
    start: date
    end: date
    label: str
    
    @property
    def days(self) -> int:
        """Calculate number of days in the range."""
        return (self.end - self.start).days + 1
    
    def __str__(self) -> str:
        """String representation."""
        return f"{self.label} ({self.start} to {self.end}, {self.days} days)"


class PeriodCalculator:
    """
    Utility for calculating date ranges for period comparisons.
    
    All methods return tuples of (current_period, previous_period).
    """
    
    @staticmethod
    def get_week_over_week(
        reference_date: Optional[date] = None
    ) -> Tuple[DateRange, DateRange]:
        """
        Calculate week-over-week date ranges.
        
        Week runs from Monday to Sunday.
        
        Args:
            reference_date: Reference date (defaults to yesterday)
            
        Returns:
            Tuple of (current_week, previous_week)
            
        Example:
            If reference_date is 2026-01-15 (Thursday):
            - Current: 2026-01-13 to 2026-01-19 (Mon-Sun)
            - Previous: 2026-01-06 to 2026-01-12 (Mon-Sun)
        """
        if reference_date is None:
            reference_date = date.today() - timedelta(days=1)
        
        # Find Monday of current week
        days_since_monday = reference_date.weekday()  # 0 = Monday, 6 = Sunday
        current_start = reference_date - timedelta(days=days_since_monday)
        current_end = current_start + timedelta(days=6)  # Sunday
        
        # Previous week
        previous_start = current_start - timedelta(days=7)
        previous_end = current_end - timedelta(days=7)
        
        current = DateRange(
            start=current_start,
            end=current_end,
            label="Current Week"
        )
        
        previous = DateRange(
            start=previous_start,
            end=previous_end,
            label="Previous Week"
        )
        
        return current, previous
    
    @staticmethod
    def get_month_over_month(
        reference_date: Optional[date] = None
    ) -> Tuple[DateRange, DateRange]:
        """
        Calculate month-over-month date ranges.
        
        Compares same day range in current month vs previous month.
        
        Args:
            reference_date: Reference date (defaults to yesterday)
            
        Returns:
            Tuple of (current_month, previous_month)
            
        Example:
            If reference_date is 2026-01-15:
            - Current: 2026-01-01 to 2026-01-15
            - Previous: 2025-12-01 to 2025-12-15
        """
        if reference_date is None:
            reference_date = date.today() - timedelta(days=1)
        
        # Current month from 1st to reference_date
        current_start = reference_date.replace(day=1)
        current_end = reference_date
        
        # Previous month
        if current_start.month == 1:
            previous_year = current_start.year - 1
            previous_month = 12
        else:
            previous_year = current_start.year
            previous_month = current_start.month - 1
        
        previous_start = date(previous_year, previous_month, 1)
        
        # Try to match same day, handle month-end edge cases
        try:
            previous_end = date(previous_year, previous_month, reference_date.day)
        except ValueError:
            # Day doesn't exist in previous month (e.g., Jan 31 -> Feb 28)
            last_day = calendar.monthrange(previous_year, previous_month)[1]
            previous_end = date(previous_year, previous_month, last_day)
        
        current = DateRange(
            start=current_start,
            end=current_end,
            label=current_start.strftime("%B %Y")
        )
        
        previous = DateRange(
            start=previous_start,
            end=previous_end,
            label=previous_start.strftime("%B %Y")
        )
        
        return current, previous
    
    @staticmethod
    def get_year_over_year(
        reference_date: Optional[date] = None
    ) -> Tuple[DateRange, DateRange]:
        """
        Calculate year-over-year date ranges.
        
        Compares same date range in current year vs previous year.
        
        Args:
            reference_date: Reference date (defaults to yesterday)
            
        Returns:
            Tuple of (current_year, previous_year)
            
        Example:
            If reference_date is 2026-01-15:
            - Current: 2026-01-01 to 2026-01-15
            - Previous: 2025-01-01 to 2025-01-15
        """
        if reference_date is None:
            reference_date = date.today() - timedelta(days=1)
        
        # Current year from Jan 1 to reference_date
        current_start = reference_date.replace(month=1, day=1)
        current_end = reference_date
        
        # Previous year, same date range
        previous_start = date(current_start.year - 1, 1, 1)
        previous_end = date(current_end.year - 1, current_end.month, current_end.day)
        
        current = DateRange(
            start=current_start,
            end=current_end,
            label=str(current_start.year)
        )
        
        previous = DateRange(
            start=previous_start,
            end=previous_end,
            label=str(previous_start.year)
        )
        
        return current, previous
    
    @staticmethod
    def get_custom_period(
        current_start: date,
        current_end: date
    ) -> Tuple[DateRange, DateRange]:
        """
        Calculate custom period comparison.
        
        Previous period has same length, immediately before current period.
        
        Args:
            current_start: Start date of current period
            current_end: End date of current period
            
        Returns:
            Tuple of (current_period, previous_period)
            
        Example:
            If current_start=2026-01-15, current_end=2026-01-21 (7 days):
            - Current: 2026-01-15 to 2026-01-21
            - Previous: 2026-01-08 to 2026-01-14 (7 days)
        """
        period_length = (current_end - current_start).days
        
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=period_length)
        
        current = DateRange(
            start=current_start,
            end=current_end,
            label="Current Period"
        )
        
        previous = DateRange(
            start=previous_start,
            end=previous_end,
            label="Previous Period"
        )
        
        return current, previous
    
    @staticmethod
    def get_last_n_days(
        days: int,
        end_date: Optional[date] = None
    ) -> DateRange:
        """
        Get date range for last N days.
        
        Args:
            days: Number of days
            end_date: End date (defaults to yesterday)
            
        Returns:
            DateRange for last N days
            
        Example:
            >>> calc.get_last_n_days(7)  # Last 7 days
            DateRange(start=..., end=..., label="Last 7 Days")
        """
        if end_date is None:
            end_date = date.today() - timedelta(days=1)
        
        start_date = end_date - timedelta(days=days - 1)
        
        return DateRange(
            start=start_date,
            end=end_date,
            label=f"Last {days} Days"
        )
    
    @staticmethod
    def get_last_complete_week() -> DateRange:
        """
        Get last complete week (Monday to Sunday).
        
        Returns:
            DateRange for last complete week
        """
        today = date.today()
        days_since_monday = today.weekday()
        
        # Last Sunday
        last_sunday = today - timedelta(days=days_since_monday + 1)
        
        # Previous Monday (7 days before Sunday)
        last_monday = last_sunday - timedelta(days=6)
        
        return DateRange(
            start=last_monday,
            end=last_sunday,
            label="Last Week"
        )
    
    @staticmethod
    def get_last_complete_month() -> DateRange:
        """
        Get last complete month.
        
        Returns:
            DateRange for last complete month
        """
        today = date.today()
        
        # First day of current month
        first_of_this_month = today.replace(day=1)
        
        # Last day of previous month
        last_of_prev_month = first_of_this_month - timedelta(days=1)
        
        # First day of previous month
        first_of_prev_month = last_of_prev_month.replace(day=1)
        
        return DateRange(
            start=first_of_prev_month,
            end=last_of_prev_month,
            label=first_of_prev_month.strftime("%B %Y")
        )

