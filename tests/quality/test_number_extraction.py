"""
Number Extraction Utility Tests.

Implements tests for Task P0-11: Number Extraction from LLM Text

Tests the NumberExtractor utility that extracts numeric values
and their context from natural language text.
"""

import pytest

from server.services.validation.number_extractor import (
    NumberExtractor,
    NumberType,
    ExtractedNumber,
)


@pytest.fixture
def extractor():
    """Create number extractor with default context window."""
    return NumberExtractor(context_window=5)


class TestBasicExtraction:
    """Test basic number extraction."""
    
    def test_extract_simple_integer(self, extractor):
        """Test extracting simple integer."""
        text = "You had 1234 sessions yesterday"
        numbers = extractor.extract(text)
        
        assert len(numbers) >= 1
        assert any(n.value == 1234 for n in numbers)
    
    def test_extract_comma_formatted_integer(self, extractor):
        """Test extracting comma-formatted integer."""
        text = "You had 1,234 sessions yesterday"
        numbers = extractor.extract(text)
        
        assert len(numbers) >= 1
        found = next((n for n in numbers if abs(n.value - 1234) < 0.1), None)
        assert found is not None
        assert found.number_type in [NumberType.INTEGER, NumberType.FLOAT]
    
    def test_extract_float(self, extractor):
        """Test extracting decimal number."""
        text = "Conversion rate was 3.45% yesterday"
        numbers = extractor.extract(text)
        
        assert len(numbers) >= 1
        found = next((n for n in numbers if abs(n.value - 3.45) < 0.01), None)
        assert found is not None
    
    def test_extract_percentage(self, extractor):
        """Test extracting percentage."""
        text = "Traffic increased by 25%"
        numbers = extractor.extract(text)
        
        assert len(numbers) >= 1
        found = next((n for n in numbers if abs(n.value - 25) < 0.1), None)
        assert found is not None
        assert found.number_type == NumberType.PERCENTAGE


class TestMultipleNumbers:
    """Test extracting multiple numbers."""
    
    def test_extract_multiple_metrics(self, extractor):
        """Test extracting multiple metrics from text."""
        text = "We had 1,234 sessions with 56 conversions and 42.3% bounce rate"
        numbers = extractor.extract(text)
        
        assert len(numbers) >= 3
        values = [n.value for n in numbers]
        assert 1234 in [int(v) for v in values]
        assert 56 in [int(v) for v in values]
        assert any(abs(v - 42.3) < 0.1 for v in values)
    
    def test_extract_period_comparison(self, extractor):
        """Test extracting numbers from period comparison."""
        text = "This week: 12,450 sessions vs last week: 10,233 sessions (+21.7%)"
        numbers = extractor.extract(text)
        
        assert len(numbers) >= 3
        values = [n.value for n in numbers]
        assert any(abs(v - 12450) < 1 for v in values)
        assert any(abs(v - 10233) < 1 for v in values)
        assert any(abs(v - 21.7) < 0.1 for v in values)


class TestMetricInference:
    """Test metric name inference from context."""
    
    def test_infer_sessions_metric(self, extractor):
        """Test inferring 'sessions' metric from context."""
        text = "Mobile sessions increased to 1,234 yesterday"
        numbers = extractor.extract(text)
        
        found = next((n for n in numbers if abs(n.value - 1234) < 1), None)
        assert found is not None
        assert found.metric_name == "sessions"
    
    def test_infer_conversions_metric(self, extractor):
        """Test inferring 'conversions' metric from context."""
        text = "You had 56 conversions from mobile traffic"
        numbers = extractor.extract(text)
        
        found = next((n for n in numbers if abs(n.value - 56) < 1), None)
        assert found is not None
        assert found.metric_name == "conversions"
    
    def test_infer_bounce_rate_metric(self, extractor):
        """Test inferring 'bounce_rate' metric from context."""
        text = "Your bounce rate was 42.3% this week"
        numbers = extractor.extract(text)
        
        found = next((n for n in numbers if abs(n.value - 42.3) < 0.1), None)
        assert found is not None
        assert found.metric_name == "bounce_rate"
    
    def test_infer_users_metric(self, extractor):
        """Test inferring 'users' metric from context."""
        text = "Total users reached 10,234 last month"
        numbers = extractor.extract(text)
        
        found = next((n for n in numbers if abs(n.value - 10234) < 1), None)
        assert found is not None
        assert found.metric_name == "users"
    
    def test_infer_revenue_metric(self, extractor):
        """Test inferring 'revenue' metric from context."""
        text = "Total revenue was $12,345.67 this quarter"
        numbers = extractor.extract(text)
        
        # Should find revenue number
        found = next((n for n in numbers if abs(n.value - 12345.67) < 1), None)
        assert found is not None
        assert found.metric_name == "revenue"


class TestContextExtraction:
    """Test context extraction around numbers."""
    
    def test_context_includes_surrounding_words(self, extractor):
        """Test context includes words before and after number."""
        text = "Your mobile traffic increased to 1,234 sessions yesterday afternoon"
        numbers = extractor.extract(text)
        
        found = next((n for n in numbers if abs(n.value - 1234) < 1), None)
        assert found is not None
        assert "mobile" in found.context.lower() or "traffic" in found.context.lower()
        assert "sessions" in found.context.lower()
    
    def test_context_window_size(self, extractor):
        """Test context window respects size limit."""
        long_text = " ".join(["word"] * 20) + " 1234 " + " ".join(["word"] * 20)
        numbers = extractor.extract(long_text)
        
        found = next((n for n in numbers if abs(n.value - 1234) < 1), None)
        assert found is not None
        # Context should not include all 40 words (window is 5)
        assert found.context.count("word") <= 11  # 5 before + number + 5 after


class TestNumberFormats:
    """Test various number formats."""
    
    def test_large_numbers_with_commas(self, extractor):
        """Test large numbers with comma separators."""
        text = "Pageviews reached 1,234,567 last month"
        numbers = extractor.extract(text)
        
        assert len(numbers) >= 1
        assert any(abs(n.value - 1234567) < 1 for n in numbers)
    
    def test_decimal_precision(self, extractor):
        """Test decimal numbers with precision."""
        text = "Conversion rate: 3.4567%"
        numbers = extractor.extract(text)
        
        assert len(numbers) >= 1
        assert any(abs(n.value - 3.4567) < 0.0001 for n in numbers)
    
    def test_positive_change(self, extractor):
        """Test positive change notation (+25%)."""
        text = "Traffic increased +25% this week"
        numbers = extractor.extract(text)
        
        assert len(numbers) >= 1
        assert any(abs(n.value - 25) < 0.1 for n in numbers)
    
    def test_negative_change(self, extractor):
        """Test negative change notation (-10%)."""
        text = "Bounce rate decreased -10% this month"
        numbers = extractor.extract(text)
        
        assert len(numbers) >= 1
        # Should extract 10 (absolute value)
        assert any(abs(n.value - 10) < 0.1 for n in numbers)
    
    def test_currency_formats(self, extractor):
        """Test currency formats."""
        texts = [
            ("Revenue: $1,234.56", 1234.56),
            ("Sales: €5,678.90", 5678.90),
            ("Income: £9,876.54", 9876.54),
        ]
        
        for text, expected_value in texts:
            numbers = extractor.extract(text)
            assert any(abs(n.value - expected_value) < 0.01 for n in numbers), \
                f"Failed to extract {expected_value} from '{text}'"


class TestDuplicateRemoval:
    """Test duplicate number removal."""
    
    def test_remove_duplicate_formats(self, extractor):
        """Test same number in different formats is deduplicated."""
        # "1234" and "1,234" are the same number
        text = "You had 1234 sessions (that's 1,234 total)"
        numbers = extractor.extract(text)
        
        # Should only count once
        session_numbers = [n for n in numbers if abs(n.value - 1234) < 1]
        assert len(session_numbers) == 1
    
    def test_keep_different_values(self, extractor):
        """Test different values are not deduplicated."""
        text = "Mobile: 1,234 sessions, Desktop: 5,678 sessions"
        numbers = extractor.extract(text)
        
        assert len(numbers) >= 2
        values = [int(n.value) for n in numbers]
        assert 1234 in values
        assert 5678 in values


class TestExtractByMetric:
    """Test extracting numbers for specific metrics."""
    
    def test_extract_sessions_only(self, extractor):
        """Test extracting only session numbers."""
        text = "1,234 sessions with 56 conversions"
        sessions = extractor.extract_by_metric(text, "sessions")
        
        assert len(sessions) == 1
        assert sessions[0].value == 1234
        assert sessions[0].metric_name == "sessions"
    
    def test_extract_conversions_only(self, extractor):
        """Test extracting only conversion numbers."""
        text = "1,234 sessions with 56 conversions"
        conversions = extractor.extract_by_metric(text, "conversions")
        
        assert len(conversions) == 1
        assert conversions[0].value == 56
        assert conversions[0].metric_name == "conversions"


class TestEdgeCases:
    """Test edge cases."""
    
    def test_empty_text(self, extractor):
        """Test extraction from empty text."""
        numbers = extractor.extract("")
        assert len(numbers) == 0
    
    def test_no_numbers(self, extractor):
        """Test extraction when no numbers present."""
        text = "Your analytics data is being processed"
        numbers = extractor.extract(text)
        assert len(numbers) == 0
    
    def test_only_numbers(self, extractor):
        """Test extraction from text with only numbers."""
        text = "1234 5678 90"
        numbers = extractor.extract(text)
        assert len(numbers) >= 2
    
    def test_special_characters(self, extractor):
        """Test extraction with special characters."""
        text = "Sessions: 1,234 | Conversions: 56 | Rate: 3.45%"
        numbers = extractor.extract(text)
        assert len(numbers) >= 3
    
    def test_scientific_notation(self, extractor):
        """Test scientific notation is handled."""
        text = "Very large number: 1.23e6"
        # Most text extractors don't handle scientific notation
        # This test documents expected behavior
        numbers = extractor.extract(text)
        # May or may not extract depending on implementation


class TestRealWorldScenarios:
    """Test real-world report scenarios."""
    
    def test_executive_summary(self, extractor):
        """Test number extraction from executive summary."""
        text = """
        Executive Summary - Mobile Analytics (January 2026)
        
        Traffic Performance:
        Your mobile traffic reached 45,678 sessions this month, representing
        a 21.7% increase from December's 37,512 sessions.
        
        Conversion Metrics:
        - Total conversions: 1,234
        - Conversion rate: 2.7%
        - Revenue: $12,345.67
        """
        
        numbers = extractor.extract(text)
        
        assert len(numbers) >= 6
        values = [n.value for n in numbers]
        assert any(abs(v - 45678) < 1 for v in values)
        assert any(abs(v - 21.7) < 0.1 for v in values)
        assert any(abs(v - 37512) < 1 for v in values)
        assert any(abs(v - 1234) < 1 for v in values)
        assert any(abs(v - 2.7) < 0.1 for v in values)
        assert any(abs(v - 12345.67) < 0.1 for v in values)
    
    def test_comparison_report(self, extractor):
        """Test number extraction from comparison report."""
        text = """
        Week-over-Week Comparison (Jan 1-7 vs Dec 25-31)
        
        Traffic:
        - This week: 12,450 sessions
        - Last week: 10,233 sessions
        - Change: +2,217 sessions (+21.7%)
        
        Conversions:
        - This week: 234 conversions
        - Last week: 195 conversions
        - Change: +39 conversions (+20.0%)
        """
        
        numbers = extractor.extract(text)
        
        assert len(numbers) >= 8
        
        # Check key metrics are extracted
        values = [n.value for n in numbers]
        assert any(abs(v - 12450) < 1 for v in values)
        assert any(abs(v - 10233) < 1 for v in values)
        assert any(abs(v - 234) < 1 for v in values)
        assert any(abs(v - 195) < 1 for v in values)
    
    def test_daily_breakdown(self, extractor):
        """Test number extraction from daily breakdown."""
        text = """
        Daily Sessions Breakdown:
        - Monday: 9,876
        - Tuesday: 10,234
        - Wednesday: 9,456
        - Thursday: 10,567
        - Friday: 11,234
        - Saturday: 8,945
        - Sunday: 8,144
        
        Total: 68,456 sessions
        """
        
        numbers = extractor.extract(text)
        
        assert len(numbers) >= 8  # 7 days + total
        
        # Verify total is extracted
        assert any(abs(n.value - 68456) < 1 for n in numbers)


class TestPerformance:
    """Test extraction performance."""
    
    def test_large_text_performance(self, extractor):
        """Test extraction performance on large text."""
        import time
        
        # Generate large report with 100 numbers
        text = "\n".join([
            f"Metric {i}: {1000 + i * 100}" for i in range(100)
        ])
        
        start = time.time()
        numbers = extractor.extract(text)
        elapsed = time.time() - start
        
        # Should complete quickly (<200ms)
        assert elapsed < 0.2, f"Extraction took {elapsed:.2f}s (expected <0.2s)"
        assert len(numbers) >= 90  # Should extract most numbers

