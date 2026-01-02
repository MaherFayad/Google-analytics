"""
Semantic Consistency Ground Truth Tests.

Implements Task P0-11: Semantic Consistency Ground Truth Tests [CRITICAL]

Validates that LLM-generated reports accurately reflect raw GA4 metrics
to prevent hallucinations and maintain user trust.

Test Scenarios:
1. Exact match validation
2. Within-tolerance validation (±5%)
3. Outside-tolerance rejection (>5%)
4. Multi-metric reports
5. Period comparison accuracy
6. Percentage calculation validation
7. Aggregation accuracy
8. Device/dimension consistency
9. Time period matching
10. Trend statement validation
"""

import pytest
import yaml
from pathlib import Path
from typing import Dict, Any

from server.services.validation.ground_truth_validator import (
    GroundTruthValidator,
    ValidationStatus,
    ValidationError,
)


# Load test cases from YAML
TEST_CASES_PATH = Path(__file__).parent / "ground_truth_queries.yaml"


@pytest.fixture
def validator():
    """Create ground truth validator with 5% tolerance."""
    return GroundTruthValidator(tolerance_percent=5.0, context_window=5)


@pytest.fixture
def strict_validator():
    """Create strict validator with 1% tolerance."""
    return GroundTruthValidator(tolerance_percent=1.0)


@pytest.fixture
def test_cases():
    """Load test cases from YAML file."""
    if TEST_CASES_PATH.exists():
        with open(TEST_CASES_PATH, 'r') as f:
            return yaml.safe_load(f)
    return None


class TestExactMatches:
    """Test validation with exact numeric matches."""
    
    @pytest.mark.asyncio
    async def test_exact_single_metric(self, validator):
        """Test exact match for single metric."""
        llm_response = "You had 1,234 sessions yesterday"
        raw_metrics = {"sessions": 1234}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        assert result.status == ValidationStatus.PASSED
        assert result.is_valid
        assert result.total_numbers_matched == 1
        assert result.max_deviation_percent < 0.1
        assert result.accuracy_rate == 100.0
    
    @pytest.mark.asyncio
    async def test_exact_multiple_metrics(self, validator):
        """Test exact match for multiple metrics."""
        llm_response = """
        Mobile Analytics Summary:
        - Sessions: 12,450
        - Conversions: 234
        - Bounce Rate: 42.3%
        """
        
        raw_metrics = {
            "sessions": 12450,
            "conversions": 234,
            "bounce_rate": 42.3,
        }
        
        result = await validator.validate(llm_response, raw_metrics)
        
        assert result.status == ValidationStatus.PASSED
        assert result.is_valid
        assert result.total_numbers_matched == 3
        assert result.accuracy_rate == 100.0
    
    @pytest.mark.asyncio
    async def test_exact_with_formatting(self, validator):
        """Test exact match with various number formats."""
        llm_response = """
        Traffic Report:
        - Sessions: 1,234,567
        - Revenue: $5,678.90
        - Conversion Rate: 3.45%
        """
        
        raw_metrics = {
            "sessions": 1234567,
            "revenue": 5678.90,
            "conversion_rate": 3.45,
        }
        
        result = await validator.validate(llm_response, raw_metrics)
        
        assert result.status == ValidationStatus.PASSED
        assert result.total_numbers_matched >= 2


class TestToleranceValidation:
    """Test validation with tolerance thresholds."""
    
    @pytest.mark.asyncio
    async def test_within_tolerance_passes(self, validator):
        """Test values within 5% tolerance pass."""
        # LLM says "approximately 1,300" (actual: 1,234)
        # Deviation: (1300-1234)/1234 = 5.35% > 5% (should fail)
        # Let's use a closer value: 1,250
        # Deviation: (1250-1234)/1234 = 1.3% < 5% (should pass)
        
        llm_response = "You had approximately 1,250 sessions"
        raw_metrics = {"sessions": 1234}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        assert result.status == ValidationStatus.PASSED
        assert result.is_valid
        assert result.max_deviation_percent < 5.0
    
    @pytest.mark.asyncio
    async def test_outside_tolerance_fails(self, validator):
        """Test values outside 5% tolerance fail."""
        # LLM says 1,500 (actual: 1,234)
        # Deviation: (1500-1234)/1234 = 21.6% > 5%
        
        llm_response = "You had 1,500 sessions"
        raw_metrics = {"sessions": 1234}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        assert result.status in [ValidationStatus.FAILED, ValidationStatus.WARNING]
        assert not result.is_valid
        assert result.max_deviation_percent > 5.0
        assert len(result.errors) > 0
    
    @pytest.mark.asyncio
    async def test_strict_mode_raises_exception(self, validator):
        """Test strict mode raises ValidationError on mismatch."""
        llm_response = "You had 1,500 sessions"
        raw_metrics = {"sessions": 1234}
        
        with pytest.raises(ValidationError) as exc_info:
            await validator.validate(llm_response, raw_metrics, strict_mode=True)
        
        assert exc_info.value.deviation_percent > 5.0
        assert exc_info.value.metric_name == "sessions"
    
    @pytest.mark.asyncio
    async def test_strict_validator_lower_tolerance(self, strict_validator):
        """Test strict validator with 1% tolerance."""
        # Deviation: (1250-1234)/1234 = 1.3% > 1%
        llm_response = "You had 1,250 sessions"
        raw_metrics = {"sessions": 1234}
        
        result = await strict_validator.validate(llm_response, raw_metrics)
        
        assert not result.is_valid


class TestMultiMetricReports:
    """Test validation of reports with multiple metrics."""
    
    @pytest.mark.asyncio
    async def test_weekly_summary_report(self, validator):
        """Test weekly summary with multiple metrics."""
        llm_response = """
        Weekly Mobile Traffic Report (Jan 1-7, 2026):
        
        Traffic Overview:
        - Total sessions: 45,678
        - Unique users: 32,456
        - Conversions: 1,234
        - Revenue: $12,345.67
        
        Engagement:
        - Bounce rate: 42.3%
        - Pages per session: 3.2
        - Avg session duration: 145 seconds
        """
        
        raw_metrics = {
            "sessions": 45678,
            "users": 32456,
            "conversions": 1234,
            "revenue": 12345.67,
            "bounce_rate": 42.3,
            "pages_per_session": 3.2,
            "avg_session_duration": 145,
        }
        
        result = await validator.validate(llm_response, raw_metrics)
        
        assert result.status == ValidationStatus.PASSED
        assert result.total_numbers_matched >= 5
        assert result.accuracy_rate >= 80.0
    
    @pytest.mark.asyncio
    async def test_partial_match_warning(self, validator):
        """Test report with some correct and some incorrect values."""
        llm_response = """
        Traffic Report:
        - Sessions: 1,234 (correct)
        - Conversions: 100 (incorrect - actual is 56)
        """
        
        raw_metrics = {
            "sessions": 1234,
            "conversions": 56,  # LLM said 100, actual is 56
        }
        
        result = await validator.validate(llm_response, raw_metrics)
        
        assert result.status == ValidationStatus.WARNING
        assert not result.is_valid
        assert result.total_numbers_matched == 1  # Only sessions matched
        assert len(result.errors) > 0


class TestPeriodComparison:
    """Test period-over-period comparison accuracy."""
    
    @pytest.mark.asyncio
    async def test_period_comparison_exact(self, validator):
        """Test period comparison with exact values."""
        llm_response = """
        This Week vs Last Week:
        - Sessions: 12,450 vs 10,233 (+21.7%)
        - Conversions: 234 vs 195 (+20.0%)
        """
        
        raw_metrics = {
            "current_sessions": 12450,
            "previous_sessions": 10233,
            "current_conversions": 234,
            "previous_conversions": 195,
        }
        
        result = await validator.validate(llm_response, raw_metrics)
        
        # Should match all 4 base numbers (percentages calculated)
        assert result.total_numbers_matched >= 4
        assert result.accuracy_rate >= 80.0
    
    @pytest.mark.asyncio
    async def test_percentage_change_calculation(self, validator):
        """Test percentage change calculations are accurate."""
        # Sessions: 12,450 vs 10,233
        # Change: (12450-10233)/10233 = 21.67% ≈ 21.7%
        
        llm_response = "Sessions increased 21.7% (from 10,233 to 12,450)"
        
        raw_metrics = {
            "current_sessions": 12450,
            "previous_sessions": 10233,
        }
        
        result = await validator.validate(llm_response, raw_metrics)
        
        # Should match the base numbers
        assert result.total_numbers_matched >= 2


class TestAggregations:
    """Test aggregation and calculation accuracy."""
    
    @pytest.mark.asyncio
    async def test_correct_aggregation(self, validator):
        """Test correct aggregation passes validation."""
        llm_response = """
        Weekly Total:
        - Total sessions: 68,456
        - Daily breakdown: Mon (9,876), Tue (10,234), Wed (9,456), 
          Thu (10,567), Fri (11,234), Sat (8,945), Sun (8,144)
        """
        
        # Sum: 9876 + 10234 + 9456 + 10567 + 11234 + 8945 + 8144 = 68,456
        raw_metrics = {
            "total_sessions": 68456,
            "mon_sessions": 9876,
            "tue_sessions": 10234,
            "wed_sessions": 9456,
            "thu_sessions": 10567,
            "fri_sessions": 11234,
            "sat_sessions": 8945,
            "sun_sessions": 8144,
        }
        
        result = await validator.validate(llm_response, raw_metrics)
        
        assert result.status == ValidationStatus.PASSED
        assert result.total_numbers_matched >= 8
    
    @pytest.mark.asyncio
    async def test_incorrect_aggregation_fails(self, validator):
        """Test incorrect aggregation fails validation."""
        llm_response = "Total sessions this week: 70,000"
        
        # Actual sum is 68,456 (LLM said 70,000)
        raw_metrics = {"total_sessions": 68456}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        # Deviation: (70000-68456)/68456 = 2.26% < 5% (might pass)
        # Let's use a worse example
        llm_response = "Total sessions: 75,000"
        result = await validator.validate(llm_response, raw_metrics)
        
        # Deviation: (75000-68456)/68456 = 9.6% > 5% (should fail)
        assert not result.is_valid


class TestDimensionConsistency:
    """Test device/dimension consistency."""
    
    @pytest.mark.asyncio
    async def test_device_breakdown_accuracy(self, validator):
        """Test device breakdown is accurate."""
        llm_response = """
        Device Breakdown:
        - Mobile: 12,450 sessions (60%)
        - Desktop: 8,300 sessions (40%)
        """
        
        raw_metrics = {
            "mobile_sessions": 12450,
            "desktop_sessions": 8300,
        }
        
        result = await validator.validate(llm_response, raw_metrics)
        
        assert result.status == ValidationStatus.PASSED
        assert result.total_numbers_matched >= 2


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    @pytest.mark.asyncio
    async def test_zero_values(self, validator):
        """Test validation with zero values."""
        llm_response = "No conversions recorded (0 conversions)"
        raw_metrics = {"conversions": 0}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        assert result.status == ValidationStatus.PASSED
        assert result.is_valid
    
    @pytest.mark.asyncio
    async def test_very_large_numbers(self, validator):
        """Test validation with very large numbers."""
        llm_response = "Total pageviews: 12,345,678"
        raw_metrics = {"pageviews": 12345678}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        assert result.status == ValidationStatus.PASSED
        assert result.is_valid
    
    @pytest.mark.asyncio
    async def test_decimal_precision(self, validator):
        """Test validation with decimal precision."""
        llm_response = "Conversion rate: 3.45%"
        raw_metrics = {"conversion_rate": 3.45}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        assert result.status == ValidationStatus.PASSED
    
    @pytest.mark.asyncio
    async def test_no_numbers_in_response(self, validator):
        """Test validation when response has no numbers."""
        llm_response = "Analytics data is being processed"
        raw_metrics = {"sessions": 1234}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        assert result.status == ValidationStatus.SKIPPED
        assert result.total_numbers_checked == 0
    
    @pytest.mark.asyncio
    async def test_empty_metrics(self, validator):
        """Test validation with empty metrics."""
        llm_response = "Sessions: 1,234"
        raw_metrics = {}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        # Should have warnings about unmatched numbers
        assert len(result.warnings) > 0


class TestYAMLTestCases:
    """Test cases loaded from YAML file."""
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not TEST_CASES_PATH.exists(), reason="YAML test cases not found")
    async def test_yaml_success_cases(self, validator, test_cases):
        """Test all success cases from YAML."""
        if not test_cases or 'success_cases' not in test_cases:
            pytest.skip("No success cases in YAML")
        
        for case in test_cases['success_cases']:
            result = await validator.validate(
                case['llm_response'],
                case['raw_metrics']
            )
            
            assert result.is_valid, f"Failed case: {case.get('description', 'unknown')}"
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not TEST_CASES_PATH.exists(), reason="YAML test cases not found")
    async def test_yaml_failure_cases(self, validator, test_cases):
        """Test all failure cases from YAML."""
        if not test_cases or 'failure_cases' not in test_cases:
            pytest.skip("No failure cases in YAML")
        
        for case in test_cases['failure_cases']:
            result = await validator.validate(
                case['llm_response'],
                case['raw_metrics']
            )
            
            assert not result.is_valid, f"Should have failed: {case.get('description', 'unknown')}"
            assert result.max_deviation_percent > validator.tolerance_percent


class TestValidationWithRetry:
    """Test validation with retry mechanism."""
    
    @pytest.mark.asyncio
    async def test_retry_on_failure(self, validator):
        """Test retry mechanism when validation fails."""
        # Initial bad response
        initial_response = "You had 1,500 sessions"
        raw_metrics = {"sessions": 1234}
        
        # Mock retry callback that returns corrected response
        retry_count = 0
        
        async def mock_retry_callback(errors, raw_metrics):
            nonlocal retry_count
            retry_count += 1
            # Return corrected response
            return f"You had {raw_metrics['sessions']} sessions"
        
        result, attempts = await validator.validate_with_retry(
            llm_response=initial_response,
            raw_metrics=raw_metrics,
            retry_callback=mock_retry_callback,
            max_retries=2
        )
        
        assert result.is_valid
        assert attempts == 2  # Failed once, succeeded on retry
        assert retry_count == 1
    
    @pytest.mark.asyncio
    async def test_no_retry_on_success(self, validator):
        """Test no retry when validation passes on first attempt."""
        llm_response = "You had 1,234 sessions"
        raw_metrics = {"sessions": 1234}
        
        retry_count = 0
        
        async def mock_retry_callback(errors, raw_metrics):
            nonlocal retry_count
            retry_count += 1
            return llm_response
        
        result, attempts = await validator.validate_with_retry(
            llm_response=llm_response,
            raw_metrics=raw_metrics,
            retry_callback=mock_retry_callback,
            max_retries=2
        )
        
        assert result.is_valid
        assert attempts == 1  # No retry needed
        assert retry_count == 0


class TestPerformance:
    """Test validation performance."""
    
    @pytest.mark.asyncio
    async def test_large_report_performance(self, validator):
        """Test validation performance on large reports."""
        import time
        
        # Generate large report with 50 metrics
        llm_response = "\n".join([
            f"Metric {i}: {1000 + i * 100}" for i in range(50)
        ])
        
        raw_metrics = {
            f"metric_{i}": 1000 + i * 100 for i in range(50)
        }
        
        start = time.time()
        result = await validator.validate(llm_response, raw_metrics)
        elapsed = time.time() - start
        
        # Should complete in <500ms
        assert elapsed < 0.5, f"Validation took {elapsed:.2f}s (expected <0.5s)"
        assert result.total_numbers_matched >= 40


class TestRealWorldScenarios:
    """Test real-world report scenarios."""
    
    @pytest.mark.asyncio
    async def test_executive_summary(self, validator):
        """Test executive summary report."""
        llm_response = """
        Executive Summary - Mobile Analytics (January 2026)
        
        Traffic Performance:
        Your mobile traffic reached 45,678 sessions this month, representing
        a 21.7% increase from December's 37,512 sessions.
        
        Conversion Metrics:
        - Total conversions: 1,234
        - Conversion rate: 2.7%
        - Revenue: $12,345.67
        
        User Engagement:
        - Bounce rate: 42.3%
        - Pages per session: 3.2
        - Avg session duration: 2 minutes 25 seconds
        """
        
        raw_metrics = {
            "sessions": 45678,
            "previous_sessions": 37512,
            "conversions": 1234,
            "conversion_rate": 2.7,
            "revenue": 12345.67,
            "bounce_rate": 42.3,
            "pages_per_session": 3.2,
            "avg_session_duration": 145,  # 2min 25sec = 145 seconds
        }
        
        result = await validator.validate(llm_response, raw_metrics)
        
        assert result.status == ValidationStatus.PASSED
        assert result.accuracy_rate >= 80.0
    
    @pytest.mark.asyncio
    async def test_comparison_report(self, validator):
        """Test period comparison report."""
        llm_response = """
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
        
        raw_metrics = {
            "current_sessions": 12450,
            "previous_sessions": 10233,
            "session_change": 2217,
            "current_conversions": 234,
            "previous_conversions": 195,
            "conversion_change": 39,
        }
        
        result = await validator.validate(llm_response, raw_metrics)
        
        assert result.status == ValidationStatus.PASSED
        assert result.total_numbers_matched >= 6

