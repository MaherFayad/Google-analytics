"""
Chart Data Schemas for Backend → Frontend Contract.

Implements Task P0-21: Chart Data Schema Specification & Validation

Provides strongly-typed Pydantic schemas for chart data that:
1. Prevent LLM hallucinations (e.g., strings instead of numbers)
2. Enforce compile-time type safety
3. Enable runtime validation before sending to frontend
4. Support TypeScript type generation from OpenAPI spec (Task P0-35)

Usage:
    # In ReportingAgent
    chart = LineChartConfig(
        title="Sessions Over Time",
        x_label="Date",
        y_label="Sessions",
        data=[
            ChartDataPoint(x="2025-01-01", y=1234.0),
            ChartDataPoint(x="2025-01-02", y=1456.0),
        ]
    )
    
    # Pydantic validates:
    # ✓ y is float (not string "1234")
    # ✓ type is Literal["line", "bar", "pie", "area"]
    # ✓ data is List[ChartDataPoint] (not raw dict)
"""

from typing import Literal, List, Union
from pydantic import BaseModel, Field, field_validator, model_validator


class ChartDataPoint(BaseModel):
    """
    Single data point for chart visualization.
    
    Strictly validates that:
    - x is string (date/category) or numeric (for scatter plots)
    - y is ALWAYS float (prevents "1234" string bug)
    
    Example:
        ChartDataPoint(x="2025-01-01", y=1234.0)  # ✓ Valid
        ChartDataPoint(x="2025-01-01", y="1234")  # ✗ Validation error
    """
    
    x: Union[str, float] = Field(
        description="X-axis value (date string or numeric value)"
    )
    y: float = Field(
        description="Y-axis value (MUST be numeric, not string)"
    )
    
    @field_validator("y", mode="before")
    @classmethod
    def coerce_y_to_float(cls, v):
        """
        Coerce y to float (handles LLM returning strings).
        
        This prevents crashes when LLM generates:
            {"x": "2025-01-01", "y": "1234"}  // String!
        
        Instead of failing, we coerce to float.
        """
        if isinstance(v, str):
            try:
                return float(v.replace(",", ""))  # Handle "1,234"
            except ValueError:
                raise ValueError(f"Cannot convert y value '{v}' to float")
        return float(v)
    
    class Config:
        json_schema_extra = {
            "examples": [
                {"x": "2025-01-01", "y": 1234.0},
                {"x": 0, "y": 42.5},  # Scatter plot
            ]
        }


class BaseChartConfig(BaseModel):
    """
    Base configuration for all chart types.
    
    Provides common fields (title, labels, data) with validation.
    """
    
    title: str = Field(
        min_length=1,
        max_length=100,
        description="Chart title (1-100 characters)"
    )
    x_label: str = Field(
        default="",
        max_length=50,
        description="X-axis label"
    )
    y_label: str = Field(
        default="",
        max_length=50,
        description="Y-axis label"
    )
    data: List[ChartDataPoint] = Field(
        min_length=1,
        description="Chart data points (at least 1 required)"
    )
    
    @field_validator("data")
    @classmethod
    def validate_data_not_empty(cls, v: List[ChartDataPoint]) -> List[ChartDataPoint]:
        """Ensure data array is not empty."""
        if not v:
            raise ValueError("Chart data cannot be empty")
        return v


class LineChartConfig(BaseChartConfig):
    """
    Line chart configuration.
    
    Used for time-series data (sessions over time, conversions trend, etc.)
    
    Example:
        LineChartConfig(
            title="Sessions Over Time",
            x_label="Date",
            y_label="Sessions",
            data=[
                ChartDataPoint(x="2025-01-01", y=1234.0),
                ChartDataPoint(x="2025-01-02", y=1456.0),
            ]
        )
    """
    
    type: Literal["line"] = Field(
        default="line",
        description="Chart type (fixed as 'line')"
    )
    x_key: str = Field(
        default="x",
        description="Data key for X-axis (default: 'x')"
    )
    y_key: str = Field(
        default="y",
        description="Data key for Y-axis (default: 'y')"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "line",
                "title": "Sessions Over Time",
                "x_label": "Date",
                "y_label": "Sessions",
                "data": [
                    {"x": "2025-01-01", "y": 1234.0},
                    {"x": "2025-01-02", "y": 1456.0},
                    {"x": "2025-01-03", "y": 1389.0},
                ]
            }
        }


class BarChartConfig(BaseChartConfig):
    """
    Bar chart configuration.
    
    Used for categorical comparisons (mobile vs desktop, page rankings, etc.)
    
    Example:
        BarChartConfig(
            title="Traffic by Device",
            x_label="Device",
            y_label="Sessions",
            data=[
                ChartDataPoint(x="Mobile", y=5678.0),
                ChartDataPoint(x="Desktop", y=3456.0),
            ]
        )
    """
    
    type: Literal["bar"] = Field(
        default="bar",
        description="Chart type (fixed as 'bar')"
    )
    x_key: str = Field(default="x")
    y_key: str = Field(default="y")
    horizontal: bool = Field(
        default=False,
        description="Horizontal bar chart (default: vertical)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "bar",
                "title": "Traffic by Device",
                "x_label": "Device",
                "y_label": "Sessions",
                "horizontal": False,
                "data": [
                    {"x": "Mobile", "y": 5678.0},
                    {"x": "Desktop", "y": 3456.0},
                    {"x": "Tablet", "y": 789.0},
                ]
            }
        }


class PieChartConfig(BaseModel):
    """
    Pie chart configuration.
    
    Used for percentage breakdowns (traffic sources, device distribution, etc.)
    
    Note: Pie charts use (name, value) instead of (x, y).
    
    Example:
        PieChartConfig(
            title="Traffic Sources",
            data=[
                PieChartDataPoint(name="Organic", value=45.2),
                PieChartDataPoint(name="Direct", value=32.1),
                PieChartDataPoint(name="Referral", value=22.7),
            ]
        )
    """
    
    type: Literal["pie"] = Field(
        default="pie",
        description="Chart type (fixed as 'pie')"
    )
    title: str = Field(
        min_length=1,
        max_length=100,
        description="Chart title"
    )
    data: List["PieChartDataPoint"] = Field(
        min_length=1,
        description="Pie chart data (at least 1 slice required)"
    )
    
    @model_validator(mode="after")
    def validate_percentages_sum(self) -> "PieChartConfig":
        """
        Validate that pie chart percentages sum to ~100%.
        
        Allows 0.1% tolerance for rounding errors.
        """
        total = sum(point.value for point in self.data)
        if not (99.9 <= total <= 100.1):
            raise ValueError(
                f"Pie chart values must sum to ~100% (got {total:.1f}%)"
            )
        return self
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "pie",
                "title": "Traffic Sources",
                "data": [
                    {"name": "Organic", "value": 45.2},
                    {"name": "Direct", "value": 32.1},
                    {"name": "Referral", "value": 22.7},
                ]
            }
        }


class PieChartDataPoint(BaseModel):
    """Data point for pie chart (name, value pairs)."""
    
    name: str = Field(
        description="Slice label (e.g., 'Organic Search')"
    )
    value: float = Field(
        ge=0.0,
        le=100.0,
        description="Percentage value (0-100)"
    )
    
    @field_validator("value", mode="before")
    @classmethod
    def coerce_value_to_float(cls, v):
        """Coerce value to float (handles LLM returning strings)."""
        if isinstance(v, str):
            try:
                return float(v.replace("%", "").replace(",", ""))
            except ValueError:
                raise ValueError(f"Cannot convert pie value '{v}' to float")
        return float(v)


class AreaChartConfig(BaseChartConfig):
    """
    Area chart configuration.
    
    Used for cumulative metrics (stacked traffic sources over time, etc.)
    
    Example:
        AreaChartConfig(
            title="Traffic Sources Over Time",
            x_label="Date",
            y_label="Sessions",
            data=[
                ChartDataPoint(x="2025-01-01", y=1234.0),
                ChartDataPoint(x="2025-01-02", y=1456.0),
            ]
        )
    """
    
    type: Literal["area"] = Field(
        default="area",
        description="Chart type (fixed as 'area')"
    )
    x_key: str = Field(default="x")
    y_key: str = Field(default="y")
    stacked: bool = Field(
        default=False,
        description="Stacked area chart (default: overlapping)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "area",
                "title": "Sessions Over Time",
                "x_label": "Date",
                "y_label": "Sessions",
                "stacked": False,
                "data": [
                    {"x": "2025-01-01", "y": 1234.0},
                    {"x": "2025-01-02", "y": 1456.0},
                ]
            }
        }


# Union type for all chart configurations
ChartConfig = Union[
    LineChartConfig,
    BarChartConfig,
    PieChartConfig,
    AreaChartConfig,
]


class MetricCard(BaseModel):
    """
    Metric card for dashboard display.
    
    Displays a single KPI with optional trend indicator.
    
    Example:
        MetricCard(
            label="Sessions",
            value="12,450",
            change="+21.7%",
            trend="up"
        )
    """
    
    label: str = Field(
        min_length=1,
        max_length=50,
        description="Metric name (e.g., 'Sessions', 'Conversions')"
    )
    value: str = Field(
        min_length=1,
        max_length=20,
        description="Formatted metric value (e.g., '12,450', '42.3%')"
    )
    change: str | None = Field(
        default=None,
        max_length=20,
        description="Period-over-period change (e.g., '+21.7%', '-5.2%')"
    )
    trend: Literal["up", "down", "neutral"] | None = Field(
        default=None,
        description="Trend direction indicator"
    )
    
    @model_validator(mode="after")
    def infer_trend_from_change(self) -> "MetricCard":
        """
        Auto-infer trend from change if not explicitly set.
        
        Examples:
            "+21.7%" → trend="up"
            "-5.2%" → trend="down"
            "0.0%" → trend="neutral"
        """
        if self.change and not self.trend:
            if self.change.startswith("+"):
                self.trend = "up"
            elif self.change.startswith("-"):
                self.trend = "down"
            else:
                self.trend = "neutral"
        return self
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "label": "Sessions",
                    "value": "12,450",
                    "change": "+21.7%",
                    "trend": "up"
                },
                {
                    "label": "Bounce Rate",
                    "value": "42.3%",
                    "change": "-2.8pp",
                    "trend": "down"  # Down is good for bounce rate!
                },
            ]
        }


def validate_chart_data(chart_config: dict) -> ChartConfig:
    """
    Validate chart data dictionary and return typed ChartConfig.
    
    Use this function to validate LLM-generated chart data before
    sending to frontend.
    
    Args:
        chart_config: Raw dictionary from LLM
        
    Returns:
        Validated ChartConfig (LineChartConfig, BarChartConfig, etc.)
        
    Raises:
        ValidationError: If chart data is invalid
        
    Example:
        # LLM generates raw dict
        raw_chart = {
            "type": "line",
            "title": "Sessions",
            "data": [{"x": "2025-01-01", "y": "1234"}]  # y is string!
        }
        
        # Validate and coerce
        validated = validate_chart_data(raw_chart)  # ✓ y coerced to float
        assert isinstance(validated, LineChartConfig)
        assert validated.data[0].y == 1234.0  # Now a float
    """
    chart_type = chart_config.get("type")
    
    if chart_type == "line":
        return LineChartConfig(**chart_config)
    elif chart_type == "bar":
        return BarChartConfig(**chart_config)
    elif chart_type == "pie":
        return PieChartConfig(**chart_config)
    elif chart_type == "area":
        return AreaChartConfig(**chart_config)
    else:
        raise ValueError(
            f"Unknown chart type: {chart_type}. "
            f"Must be one of: line, bar, pie, area"
        )



