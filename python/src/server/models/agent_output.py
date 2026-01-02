"""
Pydantic output models for agent responses.

Implements Task 3.2: Pydantic Output Models

These models define the structured output format for AI agents:
- ChartData: Chart configurations for frontend (Recharts)
- MetricCard: Key metrics with change indicators
- Report: Complete report with answer, charts, and metrics

The models use Pydantic Field descriptions to guide LLMs on how to populate them.
"""

from typing import List, Dict, Any, Literal, Optional
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ChartDataPoint(BaseModel):
    """Single data point for charts."""
    
    x: str | float = Field(
        description="X-axis value (date string or numeric value)"
    )
    y: float = Field(
        description="Y-axis numeric value"
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {"x": "2025-01-01", "y": 1234.0},
                {"x": 1, "y": 5678.0}
            ]
        }


class ChartData(BaseModel):
    """
    Chart configuration for frontend visualization.
    
    Compatible with Recharts library.
    LLMs should generate this structure from analytics data.
    """
    
    title: str = Field(
        description="Chart title - should be descriptive and actionable",
        examples=["Sessions Over Time", "Conversion Rate by Device"]
    )
    
    type: Literal["line", "bar", "area", "pie"] = Field(
        description="Chart type - must be one of: line, bar, area, pie",
        examples=["line", "bar"]
    )
    
    data: List[Dict[str, Any]] = Field(
        description=(
            "Array of data points suitable for Recharts. "
            "Each object must have keys matching x_key and y_key. "
            "For multi-series charts, include additional y-value keys. "
            "Example: [{'date': '2025-01-01', 'sessions': 1234, 'conversions': 56}]"
        )
    )
    
    x_key: str = Field(
        description="Key name for X-axis in data array (e.g., 'date', 'device')",
        examples=["date", "device", "page"]
    )
    
    y_key: str = Field(
        description="Key name for Y-axis in data array (e.g., 'sessions', 'conversions')",
        examples=["sessions", "conversions", "revenue"]
    )
    
    y_keys: Optional[List[str]] = Field(
        default=None,
        description="Multiple Y-axis keys for multi-series charts (optional)"
    )
    
    x_label: Optional[str] = Field(
        default=None,
        description="X-axis label for display"
    )
    
    y_label: Optional[str] = Field(
        default=None,
        description="Y-axis label for display"
    )
    
    color: Optional[str] = Field(
        default=None,
        description="Chart color (hex code or color name)",
        examples=["#8884d8", "blue"]
    )
    
    @field_validator("data")
    @classmethod
    def validate_data_structure(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate data array is not empty and has consistent structure."""
        if not v:
            raise ValueError("Chart data array cannot be empty")
        
        # Check first item has required keys
        if not isinstance(v[0], dict):
            raise ValueError("Chart data must be array of objects")
        
        return v
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "title": "Sessions Over Time",
                    "type": "line",
                    "data": [
                        {"date": "2025-01-01", "sessions": 1234},
                        {"date": "2025-01-02", "sessions": 1456}
                    ],
                    "x_key": "date",
                    "y_key": "sessions"
                }
            ]
        }


class MetricCard(BaseModel):
    """
    Key metric card for dashboard display.
    
    Shows a single metric with optional change indicator.
    """
    
    label: str = Field(
        description="Metric label (e.g., 'Total Sessions', 'Conversion Rate')",
        examples=["Total Sessions", "Conversion Rate", "Revenue"]
    )
    
    value: str = Field(
        description=(
            "Formatted metric value. "
            "Include appropriate formatting (e.g., '12,450' for counts, "
            "'3.2%' for percentages, '$1,234.56' for currency)"
        ),
        examples=["12,450", "3.2%", "$1,234.56"]
    )
    
    change: Optional[str] = Field(
        default=None,
        description=(
            "Change indicator vs previous period. "
            "Format: '+21.7%' (positive), '-12.3%' (negative), or 'No change'. "
            "Include + or - sign to indicate direction."
        ),
        examples=["+21.7%", "-12.3%", "No change"]
    )
    
    trend: Optional[Literal["up", "down", "flat"]] = Field(
        default=None,
        description="Trend direction for visual indicator"
    )
    
    icon: Optional[str] = Field(
        default=None,
        description="Optional icon name for display",
        examples=["trending_up", "trending_down", "remove"]
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "label": "Total Sessions",
                    "value": "12,450",
                    "change": "+21.7%",
                    "trend": "up"
                }
            ]
        }


class SourceCitation(BaseModel):
    """
    Source citation for data provenance.
    
    Links report claims back to source GA4 data (Task P0-42).
    """
    
    metric_id: int = Field(
        description="ID of source ga4_metrics_raw record"
    )
    
    property_id: str = Field(
        description="GA4 property ID"
    )
    
    metric_date: str = Field(
        description="Date of metric (YYYY-MM-DD)"
    )
    
    raw_value: float | int = Field(
        description="Raw metric value from GA4"
    )
    
    metric_name: str = Field(
        description="Name of metric (e.g., 'sessions', 'conversions')",
        examples=["sessions", "conversions", "bounce_rate"]
    )


class Report(BaseModel):
    """
    Complete analytics report with answer, visualizations, and metrics.
    
    This is the primary output format for AI agents (Task 3.2).
    LLMs generate this structure in response to user queries.
    """
    
    answer: str = Field(
        description=(
            "Natural language answer to user's query. "
            "Should be clear, actionable, and evidence-based. "
            "Include specific numbers and cite data sources. "
            "Format with markdown for readability."
        ),
        examples=[
            "Mobile conversions increased 21.7% last week, driven by improved checkout flow. "
            "Desktop traffic remained stable at 7,000 sessions."
        ]
    )
    
    charts: List[ChartData] = Field(
        default_factory=list,
        description=(
            "Array of chart configurations for data visualization. "
            "Include 1-3 charts maximum to avoid overwhelming the user. "
            "Choose chart types appropriate for the data: "
            "- line: time-series trends, "
            "- bar: comparisons, "
            "- area: cumulative metrics, "
            "- pie: distributions"
        )
    )
    
    metrics: List[MetricCard] = Field(
        default_factory=list,
        description=(
            "Array of key metric cards (2-6 cards recommended). "
            "Highlight the most important metrics related to the query. "
            "Always include change indicators when comparing time periods."
        )
    )
    
    insights: List[str] = Field(
        default_factory=list,
        description=(
            "Key insights and recommendations (2-5 bullet points). "
            "Each insight should be actionable and specific. "
            "Example: 'Mobile bounce rate increased 8% - consider page load optimization'"
        )
    )
    
    citations: Optional[List[SourceCitation]] = Field(
        default=None,
        description=(
            "Source citations for data provenance (Task P0-42). "
            "Links numeric claims back to source GA4 metrics."
        )
    )
    
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Report metadata including query, persona, timestamp, etc. "
            "Used for tracking and analytics."
        )
    )
    
    @field_validator("charts")
    @classmethod
    def validate_charts_limit(cls, v: List[ChartData]) -> List[ChartData]:
        """Limit number of charts to avoid overwhelming UI."""
        if len(v) > 5:
            raise ValueError("Maximum 5 charts allowed per report")
        return v
    
    @field_validator("metrics")
    @classmethod
    def validate_metrics_limit(cls, v: List[MetricCard]) -> List[MetricCard]:
        """Limit number of metric cards."""
        if len(v) > 10:
            raise ValueError("Maximum 10 metric cards allowed per report")
        return v
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "answer": (
                        "Mobile conversions increased **21.7%** last week compared to the previous week, "
                        "driven by improved checkout flow on mobile devices. Desktop traffic remained "
                        "stable at 7,000 sessions with a 3.2% conversion rate.\n\n"
                        "Key highlights:\n"
                        "- Mobile sessions: 12,450 (+21.7%)\n"
                        "- Mobile conversions: 456 (+15.3%)\n"
                        "- Desktop conversions remained steady at 234"
                    ),
                    "charts": [
                        {
                            "title": "Sessions by Device (Last 7 Days)",
                            "type": "line",
                            "data": [
                                {"date": "2025-01-01", "mobile": 1100, "desktop": 700},
                                {"date": "2025-01-02", "mobile": 1200, "desktop": 710}
                            ],
                            "x_key": "date",
                            "y_key": "mobile",
                            "y_keys": ["mobile", "desktop"]
                        }
                    ],
                    "metrics": [
                        {
                            "label": "Total Sessions",
                            "value": "12,450",
                            "change": "+21.7%",
                            "trend": "up"
                        },
                        {
                            "label": "Conversion Rate",
                            "value": "3.2%",
                            "change": "+0.5pp",
                            "trend": "up"
                        }
                    ],
                    "insights": [
                        "Mobile traffic is the primary growth driver",
                        "Checkout flow improvements increased mobile conversions by 15%",
                        "Desktop performance is stable - focus optimization efforts on mobile"
                    ],
                    "metadata": {
                        "query": "Show me last week's mobile performance",
                        "persona": "product_owner",
                        "generated_at": "2025-01-02T13:00:00Z",
                        "property_id": "123456789"
                    }
                }
            ]
        }


class ReportStream(BaseModel):
    """
    Streaming report chunk for SSE (Task 4.2).
    
    Used to stream report generation progress to frontend.
    """
    
    type: Literal["status", "thought", "chart", "metric", "answer", "result", "error"] = Field(
        description="Event type for SSE streaming"
    )
    
    content: str | Dict[str, Any] = Field(
        description="Event content (string for status/thought, object for structured data)"
    )
    
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Event timestamp"
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "type": "status",
                    "content": "Fetching GA4 data...",
                    "timestamp": "2025-01-02T13:00:00Z"
                },
                {
                    "type": "result",
                    "content": {
                        "answer": "...",
                        "charts": [],
                        "metrics": []
                    },
                    "timestamp": "2025-01-02T13:00:05Z"
                }
            ]
        }

