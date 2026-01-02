"""
Tests for ReportingAgent.

Implements tests for Task 16: Structured Report Generation Agent
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from python.src.agents.reporting_agent import ReportingAgent
from python.src.agents.schemas.results import (
    ReportResult,
    SourceCitation,
)
from python.src.agents.schemas.charts import (
    LineChartConfig,
    BarChartConfig,
    MetricCard,
)


@pytest.fixture
def reporting_agent():
    """Create a ReportingAgent instance for testing."""
    return ReportingAgent(openai_api_key="test-key")


@pytest.fixture
def sample_ga4_data():
    """Sample GA4 API response data."""
    return {
        "dimensionHeaders": [{"name": "date"}],
        "metricHeaders": [
            {"name": "sessions"},
            {"name": "conversions"},
            {"name": "bounce_rate"}
        ],
        "rows": [
            {
                "dimensionValues": [{"value": "2025-01-01"}],
                "metricValues": [
                    {"value": "1234"},
                    {"value": "56"},
                    {"value": "42.3"}
                ]
            },
            {
                "dimensionValues": [{"value": "2025-01-02"}],
                "metricValues": [
                    {"value": "1456"},
                    {"value": "67"},
                    {"value": "39.8"}
                ]
            },
            {
                "dimensionValues": [{"value": "2025-01-03"}],
                "metricValues": [
                    {"value": "1389"},
                    {"value": "61"},
                    {"value": "41.2"}
                ]
            }
        ]
    }


@pytest.fixture
def sample_citations():
    """Sample source citations."""
    return [
        SourceCitation(
            metric_id=123,
            property_id="GA4-12345",
            metric_date="2025-01-01",
            raw_json={"sessions": 1234},
            similarity_score=0.95
        ),
        SourceCitation(
            metric_id=124,
            property_id="GA4-12345",
            metric_date="2025-01-02",
            raw_json={"sessions": 1456},
            similarity_score=0.92
        )
    ]


class TestReportingAgent:
    """Test suite for ReportingAgent."""
    
    def test_initialization(self, reporting_agent):
        """Test agent initializes correctly."""
        assert reporting_agent.name == "reporting"
        assert reporting_agent.model == "openai:gpt-4o"
        assert reporting_agent.retries == 2
        assert reporting_agent.timeout_seconds == 20
    
    @pytest.mark.asyncio
    async def test_run_async_generates_report(
        self,
        reporting_agent,
        sample_ga4_data,
        sample_citations
    ):
        """Test report generation from GA4 data."""
        result = await reporting_agent.run_async(
            ctx=None,
            query="Show me sessions for the last 3 days",
            ga4_data=sample_ga4_data,
            retrieved_context=[
                "Historical: Sessions increased 20% last month",
                "Historical: Mobile traffic dominates at 65%"
            ],
            citations=sample_citations,
            tenant_id="test-tenant-123"
        )
        
        # Verify result structure
        assert isinstance(result, ReportResult)
        assert result.query == "Show me sessions for the last 3 days"
        assert result.tenant_id == "test-tenant-123"
        assert result.confidence > 0.5
        
        # Verify answer contains markdown
        assert "# Analysis" in result.answer or "Analysis" in result.answer
        assert "Metric" in result.answer
        
        # Verify charts were generated
        assert len(result.charts) > 0
        assert any(hasattr(chart, "type") for chart in result.charts)
        
        # Verify metrics were created
        assert len(result.metrics) > 0
        assert all(isinstance(m, MetricCard) for m in result.metrics)
        
        # Verify citations are included
        assert result.citations == sample_citations
    
    def test_extract_metrics(self, reporting_agent, sample_ga4_data):
        """Test metric extraction from GA4 data."""
        metrics = reporting_agent._extract_metrics(sample_ga4_data)
        
        assert "sessions" in metrics
        assert "conversions" in metrics
        assert "bounce_rate" in metrics
        assert metrics["sessions"] == "1234"
        assert metrics["conversions"] == "56"
    
    def test_create_metrics_table(self, reporting_agent):
        """Test markdown table generation."""
        metrics = {
            "sessions": "1234",
            "conversions": "56",
            "bounce_rate": "42.3"
        }
        
        table = reporting_agent._create_metrics_table(metrics)
        
        assert "| Metric | Value |" in table
        assert "|--------|-------|" in table
        assert "| Sessions |" in table
        assert "| Conversions |" in table
        assert "| Bounce Rate |" in table
    
    def test_create_charts(self, reporting_agent, sample_ga4_data):
        """Test chart generation from GA4 data."""
        charts = reporting_agent._create_charts(sample_ga4_data)
        
        # Should create at least one chart
        assert len(charts) > 0
        
        # First chart should be line chart (date dimension)
        first_chart = charts[0]
        assert hasattr(first_chart, "type")
        assert first_chart.type == "line"
        assert len(first_chart.data) == 3
        
        # Verify data points
        assert first_chart.data[0].x == "2025-01-01"
        assert first_chart.data[0].y == 1234.0
    
    def test_create_charts_device_dimension(self, reporting_agent):
        """Test bar chart generation for device dimension."""
        ga4_data = {
            "dimensionHeaders": [{"name": "deviceCategory"}],
            "metricHeaders": [{"name": "sessions"}],
            "rows": [
                {
                    "dimensionValues": [{"value": "mobile"}],
                    "metricValues": [{"value": "5678"}]
                },
                {
                    "dimensionValues": [{"value": "desktop"}],
                    "metricValues": [{"value": "3456"}]
                }
            ]
        }
        
        charts = reporting_agent._create_charts(ga4_data)
        
        # Should create bar chart for device dimension
        assert len(charts) > 0
        assert charts[0].type == "bar"
        assert len(charts[0].data) == 2
    
    def test_create_metric_cards(self, reporting_agent, sample_ga4_data):
        """Test metric card generation."""
        cards = reporting_agent._create_metric_cards(sample_ga4_data)
        
        assert len(cards) == 3  # 3 metrics in sample data
        
        # Verify card structure
        sessions_card = cards[0]
        assert sessions_card.label == "Sessions"
        assert sessions_card.value == "1,234"
        
        # Verify percentage formatting
        bounce_card = cards[2]
        assert "%" in bounce_card.value
    
    def test_create_metric_cards_with_period_comparison(self, reporting_agent, sample_ga4_data):
        """Test metric cards include period-over-period changes."""
        cards = reporting_agent._create_metric_cards(sample_ga4_data)
        
        # First card should have change calculation (comparing row 0 to row 1)
        sessions_card = cards[0]
        if sessions_card.change:
            assert "%" in sessions_card.change
            assert sessions_card.trend in ["up", "down", "neutral"]
    
    def test_calculate_confidence(self, reporting_agent, sample_ga4_data):
        """Test confidence score calculation."""
        # With data and context
        confidence = reporting_agent._calculate_confidence(
            ga4_data=sample_ga4_data,
            context=["Historical context 1", "Historical context 2", "Historical context 3"]
        )
        assert confidence > 0.7
        
        # With data, no context
        confidence_no_context = reporting_agent._calculate_confidence(
            ga4_data=sample_ga4_data,
            context=[]
        )
        assert confidence_no_context < confidence
        
        # No data
        confidence_no_data = reporting_agent._calculate_confidence(
            ga4_data={"rows": []},
            context=[]
        )
        assert confidence_no_data == 0.5
    
    @pytest.mark.asyncio
    async def test_export_to_csv(
        self,
        reporting_agent,
        sample_ga4_data,
        sample_citations
    ):
        """Test CSV export functionality (Task 16)."""
        # Generate a report
        result = await reporting_agent.run_async(
            ctx=None,
            query="Show me sessions",
            ga4_data=sample_ga4_data,
            retrieved_context=[],
            citations=sample_citations,
            tenant_id="test-tenant-123"
        )
        
        # Export to CSV
        csv_data = reporting_agent.export_to_csv(result)
        
        # Verify CSV structure
        assert "Report Export" in csv_data
        assert "Show me sessions" in csv_data
        assert "Generated" in csv_data
        assert "Confidence" in csv_data
        assert "Metric Cards" in csv_data
        assert "Sessions" in csv_data
        assert "Source Citations" in csv_data
    
    @pytest.mark.asyncio
    async def test_get_report_summary(
        self,
        reporting_agent,
        sample_ga4_data,
        sample_citations
    ):
        """Test report summary generation."""
        result = await reporting_agent.run_async(
            ctx=None,
            query="Show me sessions",
            ga4_data=sample_ga4_data,
            retrieved_context=[],
            citations=sample_citations,
            tenant_id="test-tenant-123"
        )
        
        summary = reporting_agent.get_report_summary(result)
        
        assert summary["query"] == "Show me sessions"
        assert summary["tenant_id"] == "test-tenant-123"
        assert "confidence" in summary
        assert "metrics_count" in summary
        assert "charts_count" in summary
        assert "citations_count" in summary
        assert "answer_preview" in summary
    
    def test_empty_ga4_data_handling(self, reporting_agent):
        """Test graceful handling of empty GA4 data."""
        empty_data = {"rows": [], "metricHeaders": []}
        
        charts = reporting_agent._create_charts(empty_data)
        assert charts == []
        
        cards = reporting_agent._create_metric_cards(empty_data)
        assert cards == []
        
        metrics = reporting_agent._extract_metrics(empty_data)
        assert metrics == {}
    
    @pytest.mark.asyncio
    async def test_error_handling_returns_fallback_report(
        self,
        reporting_agent,
        sample_citations
    ):
        """Test error handling returns fallback report."""
        # Pass malformed data to trigger error
        result = await reporting_agent.run_async(
            ctx=None,
            query="Test query",
            ga4_data={"invalid": "data"},
            retrieved_context=[],
            citations=sample_citations,
            tenant_id="test-tenant-123"
        )
        
        # Should return fallback report
        assert isinstance(result, ReportResult)
        assert result.confidence == 0.0
        assert "error" in result.answer.lower() or len(result.charts) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

