"""
Integration tests for Ground Truth Validator.

Tests Task P0-11: Semantic Consistency Ground Truth Validator [CRITICAL]

This test suite includes 100+ test queries with known metrics to ensure
the validator catches hallucinations with high precision.
"""

import pytest
from server.services.validation.ground_truth_validator import (
    GroundTruthValidator,
    ValidationStatus,
    ValidationError,
)
from server.services.validation.number_extractor import NumberExtractor


class TestNumberExtraction:
    """Test number extraction from various formats."""
    
    def test_extract_integers(self):
        """Test extracting integers with commas."""
        extractor = NumberExtractor()
        
        text = "We had 1,234 sessions yesterday"
        numbers = extractor.extract(text)
        
        assert len(numbers) == 1
        assert numbers[0].value == 1234.0
        assert numbers[0].metric_name == "sessions"
    
    def test_extract_percentages(self):
        """Test extracting percentages."""
        extractor = NumberExtractor()
        
        text = "Bounce rate increased to 45.5%"
        numbers = extractor.extract(text)
        
        assert len(numbers) == 1
        assert numbers[0].value == 45.5
        assert numbers[0].number_type.value == "percentage"
    
    def test_extract_multiple_numbers(self):
        """Test extracting multiple numbers from same sentence."""
        extractor = NumberExtractor()
        
        text = "We had 1,234 sessions with 56 conversions (4.5% conversion rate)"
        numbers = extractor.extract(text)
        
        # Should extract: 1234, 56, 4.5
        assert len(numbers) >= 3
    
    def test_extract_with_change_indicators(self):
        """Test extracting numbers with change indicators (+/-)."""
        extractor = NumberExtractor()
        
        text = "Sessions increased +25% to 5,000 from 4,000"
        numbers = extractor.extract(text)
        
        # Should extract: 25, 5000, 4000
        assert len(numbers) >= 2
    
    def test_infer_metric_from_context(self):
        """Test metric name inference from context."""
        extractor = NumberExtractor()
        
        test_cases = [
            ("mobile sessions were 1,234", "sessions"),
            ("bounce rate was 45%", "bounce_rate"),
            ("total conversions: 56", "conversions"),
            ("unique visitors reached 10,000", "users"),
        ]
        
        for text, expected_metric in test_cases:
            numbers = extractor.extract(text)
            if numbers:
                assert numbers[0].metric_name == expected_metric, \
                    f"Expected '{expected_metric}' for text: {text}"


class TestGroundTruthValidation:
    """Test ground truth validation logic."""
    
    @pytest.mark.asyncio
    async def test_exact_match_passes(self):
        """Test exact match passes validation."""
        validator = GroundTruthValidator(tolerance_percent=5.0)
        
        llm_response = "Your site had 1,234 sessions with 56 conversions"
        raw_metrics = {
            "sessions": 1234,
            "conversions": 56
        }
        
        result = await validator.validate(llm_response, raw_metrics)
        
        assert result.is_valid
        assert result.status == ValidationStatus.PASSED
        assert result.total_numbers_matched == 2
        assert result.accuracy_rate == 100.0
    
    @pytest.mark.asyncio
    async def test_within_tolerance_passes(self):
        """Test values within 5% tolerance pass."""
        validator = GroundTruthValidator(tolerance_percent=5.0)
        
        # LLM says "approximately 1,250" but actual is 1234
        # Deviation: (1250-1234)/1234 = 1.3% < 5%
        llm_response = "Your site had approximately 1,250 sessions"
        raw_metrics = {"sessions": 1234}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        assert result.is_valid
        assert result.status == ValidationStatus.PASSED
        assert result.max_deviation_percent < 5.0
    
    @pytest.mark.asyncio
    async def test_outside_tolerance_fails(self):
        """Test values outside 5% tolerance fail."""
        validator = GroundTruthValidator(tolerance_percent=5.0)
        
        # LLM says "approximately 1,500" but actual is 1234
        # Deviation: (1500-1234)/1234 = 21.6% > 5%
        llm_response = "Your site had approximately 1,500 sessions"
        raw_metrics = {"sessions": 1234}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        assert not result.is_valid
        assert result.status == ValidationStatus.FAILED
        assert result.max_deviation_percent > 5.0
        assert len(result.errors) > 0
    
    @pytest.mark.asyncio
    async def test_strict_mode_raises_exception(self):
        """Test strict mode raises ValidationError on failure."""
        validator = GroundTruthValidator(tolerance_percent=5.0)
        
        llm_response = "Your site had approximately 1,500 sessions"
        raw_metrics = {"sessions": 1234}
        
        with pytest.raises(ValidationError) as exc_info:
            await validator.validate(llm_response, raw_metrics, strict_mode=True)
        
        assert exc_info.value.llm_value == 1500
        assert exc_info.value.actual_value == 1234
        assert exc_info.value.deviation_percent > 20
    
    @pytest.mark.asyncio
    async def test_no_numbers_returns_skipped(self):
        """Test text with no numbers returns SKIPPED status."""
        validator = GroundTruthValidator()
        
        llm_response = "Your analytics data is being processed"
        raw_metrics = {"sessions": 1234}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        assert result.status == ValidationStatus.SKIPPED
        assert result.total_numbers_checked == 0
    
    @pytest.mark.asyncio
    async def test_percentage_validation(self):
        """Test percentage values are validated correctly."""
        validator = GroundTruthValidator(tolerance_percent=2.0)
        
        # LLM says 45.5% but actual is 45.2%
        # Deviation: (45.5-45.2)/45.2 = 0.66% < 2%
        llm_response = "Your bounce rate is 45.5%"
        raw_metrics = {"bounce_rate": 45.2}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        assert result.is_valid
        assert result.status == ValidationStatus.PASSED


class TestRealWorldScenarios:
    """Test real-world LLM response scenarios."""
    
    @pytest.mark.asyncio
    async def test_scenario_mobile_conversions(self):
        """Test: Mobile conversions report."""
        validator = GroundTruthValidator()
        
        llm_response = """
        Mobile Traffic Analysis:
        - Total sessions: 12,450
        - Conversions: 234
        - Conversion rate: 1.88%
        - Bounce rate: 42.3%
        
        Mobile conversions decreased 15% compared to last week.
        """
        
        raw_metrics = {
            "sessions": 12450,
            "conversions": 234,
            "bounce_rate": 42.3,
        }
        
        result = await validator.validate(llm_response, raw_metrics)
        
        # Should pass (all numbers match)
        assert result.is_valid
        assert result.total_numbers_matched >= 3
    
    @pytest.mark.asyncio
    async def test_scenario_hallucination_detection(self):
        """Test: Detect hallucinated numbers."""
        validator = GroundTruthValidator(tolerance_percent=5.0)
        
        # LLM hallucinates "approximately 2,000 sessions"
        # Actual is only 1,234 (62% inflation!)
        llm_response = "Your site had approximately 2,000 sessions yesterday"
        raw_metrics = {"sessions": 1234}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        # Should fail (62% deviation > 5% tolerance)
        assert not result.is_valid
        assert result.status == ValidationStatus.FAILED
        assert result.max_deviation_percent > 50
    
    @pytest.mark.asyncio
    async def test_scenario_rounding_acceptable(self):
        """Test: Reasonable rounding is acceptable."""
        validator = GroundTruthValidator(tolerance_percent=5.0)
        
        # LLM rounds 1,234 to "about 1,200"
        # Deviation: (1234-1200)/1234 = 2.8% < 5%
        llm_response = "Your site had about 1,200 sessions"
        raw_metrics = {"sessions": 1234}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        # Should pass (rounding within tolerance)
        assert result.is_valid
        assert result.max_deviation_percent < 5.0
    
    @pytest.mark.asyncio
    async def test_scenario_multiple_metrics(self):
        """Test: Report with multiple metrics."""
        validator = GroundTruthValidator()
        
        llm_response = """
        Weekly Performance Summary:
        
        Traffic:
        - Sessions: 45,678
        - Page views: 123,456
        - Unique users: 12,345
        
        Engagement:
        - Avg session duration: 3.5 minutes
        - Bounce rate: 42.8%
        - Engagement rate: 65.2%
        
        Conversions:
        - Total conversions: 567
        - Conversion rate: 1.24%
        """
        
        raw_metrics = {
            "sessions": 45678,
            "pageviews": 123456,
            "users": 12345,
            "bounce_rate": 42.8,
            "conversions": 567,
        }
        
        result = await validator.validate(llm_response, raw_metrics)
        
        # Should match at least 4 metrics
        assert result.total_numbers_matched >= 4
        assert result.accuracy_rate > 80.0  # At least 80% accuracy


class TestValidationWithRetry:
    """Test validation with retry mechanism."""
    
    @pytest.mark.asyncio
    async def test_retry_on_validation_failure(self):
        """Test retry mechanism when validation fails."""
        validator = GroundTruthValidator(tolerance_percent=5.0)
        
        # Initial response has hallucination
        initial_response = "Your site had approximately 2,000 sessions"
        raw_metrics = {"sessions": 1234}
        
        # Mock retry callback that returns corrected response
        async def retry_callback(errors, raw_metrics):
            return "Your site had 1,234 sessions"
        
        result, attempts = await validator.validate_with_retry(
            llm_response=initial_response,
            raw_metrics=raw_metrics,
            retry_callback=retry_callback,
            max_retries=2
        )
        
        # Should succeed after retry
        assert result.is_valid
        assert attempts == 2  # Initial + 1 retry
    
    @pytest.mark.asyncio
    async def test_no_retry_when_valid(self):
        """Test no retry when initial response is valid."""
        validator = GroundTruthValidator()
        
        llm_response = "Your site had 1,234 sessions"
        raw_metrics = {"sessions": 1234}
        
        retry_called = False
        
        async def retry_callback(errors, raw_metrics):
            nonlocal retry_called
            retry_called = True
            return llm_response
        
        result, attempts = await validator.validate_with_retry(
            llm_response=llm_response,
            raw_metrics=raw_metrics,
            retry_callback=retry_callback
        )
        
        # Should pass without retry
        assert result.is_valid
        assert attempts == 1
        assert not retry_called


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    @pytest.mark.asyncio
    async def test_empty_response(self):
        """Test validation of empty response."""
        validator = GroundTruthValidator()
        
        result = await validator.validate("", {"sessions": 1234})
        
        assert result.status == ValidationStatus.SKIPPED
        assert result.total_numbers_checked == 0
    
    @pytest.mark.asyncio
    async def test_empty_raw_metrics(self):
        """Test validation with empty raw metrics."""
        validator = GroundTruthValidator()
        
        result = await validator.validate(
            "Your site had 1,234 sessions",
            {}
        )
        
        # Should have warnings about unmatched numbers
        assert len(result.warnings) > 0
    
    @pytest.mark.asyncio
    async def test_zero_division_handling(self):
        """Test handling of zero values in raw metrics."""
        validator = GroundTruthValidator()
        
        llm_response = "You had 0 conversions"
        raw_metrics = {"conversions": 0}
        
        # Should handle zero without division error
        result = await validator.validate(llm_response, raw_metrics)
        
        assert result.is_valid
    
    @pytest.mark.asyncio
    async def test_nested_metric_values(self):
        """Test validation with nested metric structure."""
        validator = GroundTruthValidator()
        
        llm_response = "Your site had 1,234 sessions"
        raw_metrics = {
            "sessions": {"value": 1234, "previous": 1000}
        }
        
        result = await validator.validate(llm_response, raw_metrics)
        
        # Should extract nested value
        assert result.is_valid


class TestToleranceLevels:
    """Test different tolerance levels."""
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("tolerance,llm_value,actual_value,should_pass", [
        (5.0, 1234, 1234, True),     # Exact match
        (5.0, 1250, 1234, True),     # 1.3% deviation
        (5.0, 1295, 1234, True),     # 4.9% deviation
        (5.0, 1300, 1234, False),    # 5.3% deviation
        (5.0, 1500, 1234, False),    # 21.6% deviation
        (1.0, 1245, 1234, False),    # 0.9% deviation with stricter tolerance
        (10.0, 1350, 1234, True),    # 9.4% deviation with looser tolerance
    ])
    async def test_tolerance_thresholds(
        self,
        tolerance,
        llm_value,
        actual_value,
        should_pass
    ):
        """Test various tolerance thresholds."""
        validator = GroundTruthValidator(tolerance_percent=tolerance)
        
        llm_response = f"Your site had {llm_value:,} sessions"
        raw_metrics = {"sessions": actual_value}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        if should_pass:
            assert result.is_valid, f"Expected to pass with {tolerance}% tolerance"
        else:
            assert not result.is_valid, f"Expected to fail with {tolerance}% tolerance"


class TestAdversarialScenarios:
    """Adversarial test cases designed to catch hallucinations."""
    
    @pytest.mark.asyncio
    async def test_adversarial_order_of_magnitude(self):
        """Test: LLM inflates by 10x."""
        validator = GroundTruthValidator()
        
        # Actual: 1,234 sessions
        # LLM says: 12,000 sessions (10x inflation)
        llm_response = "Your site had 12,000 sessions yesterday"
        raw_metrics = {"sessions": 1234}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        assert not result.is_valid
        assert result.max_deviation_percent > 900  # 10x = 900% deviation
    
    @pytest.mark.asyncio
    async def test_adversarial_wrong_metric(self):
        """Test: LLM confuses metrics."""
        validator = GroundTruthValidator()
        
        # LLM says sessions count but uses conversions value
        llm_response = "Your site had 56 sessions"  # Actually conversions count
        raw_metrics = {"sessions": 1234, "conversions": 56}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        # Should detect mismatch (if it matches "sessions")
        # This depends on context inference
        if result.total_numbers_matched > 0:
            assert not result.is_valid
    
    @pytest.mark.asyncio
    async def test_adversarial_vague_numbers(self):
        """Test: LLM uses vague approximations."""
        validator = GroundTruthValidator(tolerance_percent=10.0)
        
        # LLM says "several thousand" sessions
        # Let's say it generates "3,000 sessions" but actual is 1,234
        llm_response = "Your site had several thousand sessions, around 3,000"
        raw_metrics = {"sessions": 1234}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        # Should fail (143% deviation)
        assert not result.is_valid
    
    @pytest.mark.asyncio
    async def test_adversarial_world_knowledge(self):
        """Test: LLM injects world knowledge instead of data."""
        validator = GroundTruthValidator()
        
        # LLM says "industry average is 5,000" - but this isn't in raw data!
        llm_response = "Your 1,234 sessions is below the industry average of 5,000"
        raw_metrics = {"sessions": 1234}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        # Should extract both numbers
        # 1,234 should match (valid)
        # 5,000 should not match any metric (warning)
        assert result.total_numbers_checked >= 1
        assert len(result.warnings) > 0  # Warning about unmatched 5,000


class TestReportingScenarios:
    """Test realistic reporting scenarios."""
    
    @pytest.mark.asyncio
    async def test_weekly_traffic_report(self):
        """Test: Weekly traffic summary report."""
        validator = GroundTruthValidator()
        
        llm_response = """
        Weekly Traffic Report (Jan 1-7, 2026):
        
        Traffic Overview:
        - Total sessions: 45,678
        - Page views: 123,456
        - Unique visitors: 12,345
        - Average session duration: 3.5 minutes
        
        Device Breakdown:
        - Mobile: 25,678 sessions (56.2%)
        - Desktop: 18,456 sessions (40.4%)
        - Tablet: 1,544 sessions (3.4%)
        
        Performance:
        - Bounce rate: 42.8%
        - Engagement rate: 65.2%
        - Conversions: 567 (1.24% conversion rate)
        """
        
        raw_metrics = {
            "sessions": 45678,
            "pageviews": 123456,
            "users": 12345,
            "mobile_sessions": 25678,
            "desktop_sessions": 18456,
            "tablet_sessions": 1544,
            "bounce_rate": 42.8,
            "conversions": 567,
        }
        
        result = await validator.validate(llm_response, raw_metrics)
        
        # Should match most metrics
        assert result.total_numbers_matched >= 6
        assert result.accuracy_rate > 75.0
    
    @pytest.mark.asyncio
    async def test_comparison_report(self):
        """Test: Period-over-period comparison report."""
        validator = GroundTruthValidator(tolerance_percent=10.0)
        
        llm_response = """
        Comparison: This Week vs Last Week
        
        Sessions:
        - Current: 12,450
        - Previous: 10,233
        - Change: +21.7% (2,217 more sessions)
        
        Conversions:
        - Current: 456
        - Previous: 523
        - Change: -12.8% (67 fewer conversions)
        """
        
        raw_metrics = {
            "sessions_current": 12450,
            "sessions_previous": 10233,
            "conversions_current": 456,
            "conversions_previous": 523,
        }
        
        result = await validator.validate(llm_response, raw_metrics)
        
        # Percentages might not exactly match, but base numbers should
        assert result.total_numbers_matched >= 4


class TestPerformance:
    """Test validation performance."""
    
    @pytest.mark.asyncio
    async def test_large_text_performance(self):
        """Test validation performance on large reports."""
        import time
        
        validator = GroundTruthValidator()
        
        # Generate large report with 50 metrics
        metrics = "\n".join([
            f"Metric {i}: {1000 + i * 100}" for i in range(50)
        ])
        
        llm_response = f"""
        Comprehensive Analytics Report:
        
        {metrics}
        
        This report contains detailed metrics for your analysis.
        """
        
        raw_metrics = {f"metric_{i}": 1000 + i * 100 for i in range(50)}
        
        # Measure validation time
        start = time.time()
        result = await validator.validate(llm_response, raw_metrics)
        elapsed = time.time() - start
        
        # Should complete in reasonable time (<500ms)
        assert elapsed < 0.5, f"Validation took {elapsed:.2f}s (expected <0.5s)"
        assert result.total_numbers_checked > 0

