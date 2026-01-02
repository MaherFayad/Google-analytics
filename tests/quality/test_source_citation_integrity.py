"""
Quality tests for Source Citation Integrity.

Tests Task P0-43: Citation Validator for ReportingAgent [CRITICAL]

Ensures LLM-generated numbers are properly cited and match source data.
"""

import pytest
from datetime import date

from server.services.validation.citation_validator import (
    CitationValidator,
    CitationMismatchError,
)
from agents.schemas.results import SourceCitation


@pytest.fixture
def sample_citations():
    """Sample source citations for testing."""
    return [
        SourceCitation(
            metric_id=101,
            property_id="123456789",
            metric_date="2026-01-05",
            raw_json={
                "sessions": 12450,
                "conversions": 234,
                "bounce_rate": 42.3,
                "device": "mobile"
            },
            similarity_score=0.92,
        ),
        SourceCitation(
            metric_id=102,
            property_id="123456789",
            metric_date="2026-01-04",
            raw_json={
                "sessions": 10233,
                "conversions": 195,
                "bounce_rate": 45.1,
                "device": "mobile"
            },
            similarity_score=0.87,
        ),
    ]


class TestCitationValidation:
    """Test citation validation logic."""
    
    @pytest.mark.asyncio
    async def test_exact_match_valid(self, sample_citations):
        """Test exact match passes validation."""
        validator = CitationValidator(tolerance_percent=5.0)
        
        llm_response = "Mobile sessions: 12,450 with 234 conversions"
        
        report = await validator.validate_citations(llm_response, sample_citations)
        
        assert report.is_valid
        assert report.matched_numbers == 2
        assert report.total_numbers == 2
    
    @pytest.mark.asyncio
    async def test_within_tolerance_valid(self, sample_citations):
        """Test values within tolerance pass."""
        validator = CitationValidator(tolerance_percent=5.0)
        
        # LLM says "approximately 12,500" (actual: 12,450)
        # Deviation: (12500-12450)/12450 = 0.4% < 5%
        llm_response = "Mobile had approximately 12,500 sessions"
        
        report = await validator.validate_citations(llm_response, sample_citations)
        
        assert report.is_valid
        assert report.max_deviation_percent < 5.0
    
    @pytest.mark.asyncio
    async def test_outside_tolerance_invalid(self, sample_citations):
        """Test values outside tolerance fail."""
        validator = CitationValidator(tolerance_percent=5.0)
        
        # LLM says "15,000 sessions" (actual: 12,450)
        # Deviation: (15000-12450)/12450 = 20.5% > 5%
        llm_response = "Mobile had 15,000 sessions"
        
        report = await validator.validate_citations(llm_response, sample_citations)
        
        assert not report.is_valid
        assert len(report.mismatches) > 0
        assert report.max_deviation_percent > 20
    
    @pytest.mark.asyncio
    async def test_strict_mode_raises_exception(self, sample_citations):
        """Test strict mode raises CitationMismatchError."""
        validator = CitationValidator(tolerance_percent=5.0)
        
        llm_response = "Mobile had 15,000 sessions"
        
        with pytest.raises(CitationMismatchError) as exc_info:
            await validator.validate_citations(
                llm_response,
                sample_citations,
                strict_mode=True
            )
        
        assert exc_info.value.deviation_percent > 5.0


class TestCitationAnnotation:
    """Test footnote annotation."""
    
    @pytest.mark.asyncio
    async def test_annotate_with_footnotes(self, sample_citations):
        """Test text is annotated with footnote markers."""
        validator = CitationValidator()
        
        llm_response = "Mobile sessions: 12,450 with 234 conversions"
        
        annotated_text, report = await validator.validate_and_annotate(
            llm_response,
            sample_citations
        )
        
        # Should contain footnote markers
        assert "[1]" in annotated_text or "[2]" in annotated_text
        assert "Sources:" in annotated_text
        assert "metric_id=" in annotated_text
    
    @pytest.mark.asyncio
    async def test_footnote_legend_format(self, sample_citations):
        """Test footnote legend is properly formatted."""
        validator = CitationValidator()
        
        llm_response = "Sessions: 12,450"
        
        annotated_text, report = await validator.validate_and_annotate(
            llm_response,
            sample_citations
        )
        
        # Verify footnote legend format
        assert "---" in annotated_text
        assert "Sources:" in annotated_text
        assert "GA4 Property" in annotated_text
        assert "2026-01-05" in annotated_text
    
    @pytest.mark.asyncio
    async def test_multiple_citations(self, sample_citations):
        """Test multiple citations are tracked."""
        validator = CitationValidator()
        
        llm_response = """
        This week: 12,450 sessions with 234 conversions
        Last week: 10,233 sessions with 195 conversions
        Change: +21.7% sessions, +20.0% conversions
        """
        
        annotated_text, report = await validator.validate_and_annotate(
            llm_response,
            sample_citations
        )
        
        # Should have multiple footnote markers
        assert annotated_text.count("[") >= 2
        assert report.matched_numbers >= 2


class TestRealWorldReports:
    """Test real-world report scenarios."""
    
    @pytest.mark.asyncio
    async def test_weekly_summary_report(self, sample_citations):
        """Test weekly summary with multiple metrics."""
        validator = CitationValidator()
        
        llm_response = """
        Weekly Mobile Traffic Report (Jan 1-7, 2026):
        
        Traffic Overview:
        - Total sessions: 12,450
        - Conversions: 234
        - Conversion rate: 1.88%
        - Bounce rate: 42.3%
        
        Compared to previous week:
        - Sessions: +21.7% (from 10,233)
        - Conversions: +20.0% (from 195)
        - Bounce rate: -6.2% (from 45.1%)
        """
        
        report = await validator.validate_citations(llm_response, sample_citations)
        
        # Should match multiple metrics
        assert report.matched_numbers >= 4
        assert report.match_rate > 50.0
    
    @pytest.mark.asyncio
    async def test_comparison_report_with_percentages(self):
        """Test comparison report with percentage changes."""
        validator = CitationValidator()
        
        citations = [
            SourceCitation(
                metric_id=1,
                property_id="123",
                metric_date="2026-01-07",
                raw_json={"sessions": 12450, "period": "current"},
                similarity_score=0.95,
            ),
            SourceCitation(
                metric_id=2,
                property_id="123",
                metric_date="2025-12-31",
                raw_json={"sessions": 10233, "period": "previous"},
                similarity_score=0.90,
            ),
        ]
        
        llm_response = """
        Traffic Comparison:
        - Current period: 12,450 sessions
        - Previous period: 10,233 sessions
        - Change: +21.7%
        """
        
        report = await validator.validate_citations(llm_response, citations)
        
        # Should match both session counts
        assert report.matched_numbers >= 2


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    @pytest.mark.asyncio
    async def test_no_citations_available(self):
        """Test validation when no citations provided."""
        validator = CitationValidator()
        
        llm_response = "Mobile had 12,450 sessions"
        
        report = await validator.validate_citations(llm_response, [])
        
        # All numbers should be unmatched
        assert len(report.unmatched_numbers) > 0
    
    @pytest.mark.asyncio
    async def test_no_numbers_in_text(self, sample_citations):
        """Test validation when text has no numbers."""
        validator = CitationValidator()
        
        llm_response = "Your analytics data is being processed"
        
        report = await validator.validate_citations(llm_response, sample_citations)
        
        assert report.total_numbers == 0
        assert report.matched_numbers == 0
    
    @pytest.mark.asyncio
    async def test_ambiguous_metric_resolution(self):
        """Test resolution when metric name is ambiguous."""
        validator = CitationValidator()
        
        # Both citations have "sessions" metric
        citations = [
            SourceCitation(
                metric_id=1,
                property_id="123",
                metric_date="2026-01-05",
                raw_json={"sessions": 12450, "device": "mobile"},
                similarity_score=0.92,
            ),
            SourceCitation(
                metric_id=2,
                property_id="123",
                metric_date="2026-01-05",
                raw_json={"sessions": 8234, "device": "desktop"},
                similarity_score=0.88,
            ),
        ]
        
        # LLM says "12,450 sessions" - should match first citation
        llm_response = "You had 12,450 sessions"
        
        report = await validator.validate_citations(llm_response, citations)
        
        # Should match to closest value
        assert report.matched_numbers >= 1


class TestPerformance:
    """Test citation validation performance."""
    
    @pytest.mark.asyncio
    async def test_large_report_performance(self):
        """Test validation performance on large reports."""
        import time
        
        validator = CitationValidator()
        
        # Generate large report with 20 metrics
        llm_response = "\n".join([
            f"Metric {i}: {1000 + i * 100}" for i in range(20)
        ])
        
        # Generate citations
        citations = [
            SourceCitation(
                metric_id=i,
                property_id="123",
                metric_date="2026-01-01",
                raw_json={f"metric_{i}": 1000 + i * 100},
                similarity_score=0.9,
            )
            for i in range(20)
        ]
        
        # Measure validation time
        start = time.time()
        report = await validator.validate_citations(llm_response, citations)
        elapsed = time.time() - start
        
        # Should complete quickly (<200ms)
        assert elapsed < 0.2, f"Validation took {elapsed:.2f}s (expected <0.2s)"
        assert report.matched_numbers > 0

