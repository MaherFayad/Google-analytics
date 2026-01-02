"""
Ground Truth Validator for LLM Response Accuracy.

Implements Task P0-11: Semantic Consistency Ground Truth Validator [CRITICAL]

Validates that LLM-generated numeric claims match raw GA4 metrics
to prevent hallucinations and maintain user trust.

Example Attack Vector (Prevented):
    User: "What were my conversions yesterday?"
    GA4 Data: {"conversions": 1234}
    LLM Says: "approximately 1,500 conversions"
    
    Validator: ❌ REJECTED - 21.5% deviation (threshold: 5%)
    Action: Retry with explicit grounding
"""

import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, Field

from .number_extractor import NumberExtractor, ExtractedNumber, NumberType

logger = logging.getLogger(__name__)


class ValidationStatus(str, Enum):
    """Status of validation."""
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


class ValidationError(Exception):
    """Raised when validation fails."""
    
    def __init__(
        self,
        message: str,
        llm_value: float,
        actual_value: float,
        deviation_percent: float,
        metric_name: str
    ):
        self.llm_value = llm_value
        self.actual_value = actual_value
        self.deviation_percent = deviation_percent
        self.metric_name = metric_name
        super().__init__(message)


@dataclass
class MetricComparison:
    """Comparison between LLM value and actual value."""
    
    metric_name: str
    llm_value: float
    actual_value: float
    deviation_percent: float
    is_valid: bool
    context: str
    
    def __str__(self) -> str:
        """String representation."""
        status = "✓" if self.is_valid else "✗"
        return (
            f"{status} {self.metric_name}: LLM={self.llm_value:.1f}, "
            f"Actual={self.actual_value:.1f}, "
            f"Deviation={self.deviation_percent:.1f}%"
        )


class ValidationResult(BaseModel):
    """Result of ground truth validation."""
    
    status: ValidationStatus
    is_valid: bool
    comparisons: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    total_numbers_checked: int = 0
    total_numbers_matched: int = 0
    max_deviation_percent: float = 0.0
    
    @property
    def accuracy_rate(self) -> float:
        """Calculate accuracy rate (0-100%)."""
        if self.total_numbers_checked == 0:
            return 100.0
        return (self.total_numbers_matched / self.total_numbers_checked) * 100


class GroundTruthValidator:
    """
    Validates LLM responses against raw GA4 metrics.
    
    Features:
    - Extracts numbers from LLM-generated text
    - Matches numbers to corresponding metrics in raw data
    - Validates deviation is within tolerance (<5%)
    - Provides detailed validation report
    - Supports retry with explicit grounding on failure
    
    Example:
        >>> validator = GroundTruthValidator(tolerance_percent=5.0)
        >>> 
        >>> llm_response = "You had 1,234 sessions with 56 conversions"
        >>> raw_metrics = {"sessions": 1234, "conversions": 56}
        >>> 
        >>> result = await validator.validate(llm_response, raw_metrics)
        >>> print(result.is_valid)  # True
        >>> print(result.accuracy_rate)  # 100.0
    """
    
    DEFAULT_TOLERANCE = 5.0  # 5% deviation allowed
    
    def __init__(
        self,
        tolerance_percent: float = DEFAULT_TOLERANCE,
        context_window: int = 5
    ):
        """
        Initialize ground truth validator.
        
        Args:
            tolerance_percent: Maximum allowed deviation (default: 5%)
            context_window: Words of context to extract around numbers
        """
        self.tolerance_percent = tolerance_percent
        self.extractor = NumberExtractor(context_window=context_window)
        
        logger.info(f"Ground truth validator initialized (tolerance={tolerance_percent}%)")
    
    async def validate(
        self,
        llm_response: str,
        raw_metrics: Dict[str, Any],
        strict_mode: bool = False
    ) -> ValidationResult:
        """
        Validate LLM response against raw GA4 metrics.
        
        Args:
            llm_response: LLM-generated text to validate
            raw_metrics: Raw GA4 metrics dictionary
            strict_mode: If True, fail on any mismatch (default: False)
            
        Returns:
            ValidationResult with detailed comparison
            
        Raises:
            ValidationError: If strict_mode=True and validation fails
            
        Example:
            >>> result = await validator.validate(
            ...     llm_response="Mobile had 1,234 sessions",
            ...     raw_metrics={"sessions": 1234, "device": "mobile"}
            ... )
            >>> if not result.is_valid:
            ...     print(result.errors)
        """
        logger.info(f"Validating LLM response (strict={strict_mode})")
        
        # Extract numbers from LLM response
        extracted_numbers = self.extractor.extract(llm_response)
        
        logger.debug(f"Extracted {len(extracted_numbers)} numbers from LLM response")
        
        # Compare each extracted number to raw metrics
        comparisons = []
        errors = []
        warnings = []
        matched_count = 0
        max_deviation = 0.0
        
        for extracted in extracted_numbers:
            # Try to find matching metric in raw data
            comparison = self._compare_to_raw_metrics(extracted, raw_metrics)
            
            if comparison:
                comparisons.append(comparison)
                
                if comparison.is_valid:
                    matched_count += 1
                else:
                    error_msg = (
                        f"{comparison.metric_name}: LLM value {comparison.llm_value} "
                        f"deviates {comparison.deviation_percent:.1f}% from actual "
                        f"{comparison.actual_value} (tolerance: {self.tolerance_percent}%)"
                    )
                    errors.append(error_msg)
                    logger.warning(error_msg)
                
                max_deviation = max(max_deviation, comparison.deviation_percent)
            else:
                # Could not match number to any metric
                warning_msg = (
                    f"Could not match '{extracted.raw_text}' "
                    f"(context: '{extracted.context[:50]}...') to any metric"
                )
                warnings.append(warning_msg)
                logger.debug(warning_msg)
        
        # Determine overall status
        total_checked = len(comparisons)
        is_valid = matched_count == total_checked and total_checked > 0
        
        if total_checked == 0:
            status = ValidationStatus.SKIPPED
            warnings.append("No numbers found to validate")
        elif is_valid:
            status = ValidationStatus.PASSED
        elif matched_count > 0:
            status = ValidationStatus.WARNING
        else:
            status = ValidationStatus.FAILED
        
        result = ValidationResult(
            status=status,
            is_valid=is_valid,
            comparisons=[self._comparison_to_dict(c) for c in comparisons],
            errors=errors,
            warnings=warnings,
            total_numbers_checked=total_checked,
            total_numbers_matched=matched_count,
            max_deviation_percent=max_deviation,
        )
        
        logger.info(
            f"Validation complete: status={status}, "
            f"matched={matched_count}/{total_checked}, "
            f"max_deviation={max_deviation:.1f}%"
        )
        
        # Raise error in strict mode
        if strict_mode and not is_valid:
            if errors:
                raise ValidationError(
                    message=f"Validation failed: {errors[0]}",
                    llm_value=comparisons[0].llm_value if comparisons else 0,
                    actual_value=comparisons[0].actual_value if comparisons else 0,
                    deviation_percent=comparisons[0].deviation_percent if comparisons else 0,
                    metric_name=comparisons[0].metric_name if comparisons else "unknown"
                )
        
        return result
    
    def _compare_to_raw_metrics(
        self,
        extracted: ExtractedNumber,
        raw_metrics: Dict[str, Any]
    ) -> Optional[MetricComparison]:
        """
        Compare extracted number to raw metrics.
        
        Args:
            extracted: Extracted number with context
            raw_metrics: Raw GA4 metrics
            
        Returns:
            MetricComparison or None if no match found
        """
        # Try to find matching metric
        metric_name = extracted.metric_name
        
        if not metric_name:
            # Try to infer from keys in raw_metrics
            for key in raw_metrics.keys():
                if key.lower() in extracted.context.lower():
                    metric_name = key
                    break
        
        if not metric_name or metric_name not in raw_metrics:
            return None
        
        # Get actual value
        actual_value = raw_metrics[metric_name]
        
        # Handle nested values (e.g., {"metrics": {"sessions": 1234}})
        if isinstance(actual_value, dict):
            # Try to extract value from nested dict
            if 'value' in actual_value:
                actual_value = actual_value['value']
            else:
                return None
        
        # Convert to float
        try:
            actual_value = float(actual_value)
        except (ValueError, TypeError):
            logger.warning(f"Could not convert actual value to float: {actual_value}")
            return None
        
        # Calculate deviation
        deviation = self._calculate_deviation(extracted.value, actual_value)
        
        # Check if within tolerance
        is_valid = deviation <= self.tolerance_percent
        
        return MetricComparison(
            metric_name=metric_name,
            llm_value=extracted.value,
            actual_value=actual_value,
            deviation_percent=deviation,
            is_valid=is_valid,
            context=extracted.context,
        )
    
    def _calculate_deviation(self, llm_value: float, actual_value: float) -> float:
        """
        Calculate percentage deviation between LLM and actual values.
        
        Args:
            llm_value: Value from LLM response
            actual_value: Actual value from raw data
            
        Returns:
            Deviation percentage (0-100+)
            
        Example:
            >>> validator._calculate_deviation(1500, 1234)
            21.6  # 21.6% deviation
        """
        if actual_value == 0:
            # Avoid division by zero
            return 100.0 if llm_value != 0 else 0.0
        
        deviation = abs(llm_value - actual_value) / actual_value * 100
        return deviation
    
    def _comparison_to_dict(self, comparison: MetricComparison) -> Dict[str, Any]:
        """Convert MetricComparison to dict for serialization."""
        return {
            "metric_name": comparison.metric_name,
            "llm_value": comparison.llm_value,
            "actual_value": comparison.actual_value,
            "deviation_percent": comparison.deviation_percent,
            "is_valid": comparison.is_valid,
            "context": comparison.context,
        }
    
    async def validate_with_retry(
        self,
        llm_response: str,
        raw_metrics: Dict[str, Any],
        retry_callback: Optional[callable] = None,
        max_retries: int = 2
    ) -> Tuple[ValidationResult, int]:
        """
        Validate with automatic retry on failure.
        
        If validation fails, calls retry_callback to regenerate
        LLM response with explicit grounding.
        
        Args:
            llm_response: Initial LLM response
            raw_metrics: Raw GA4 metrics
            retry_callback: Async function to regenerate response
            max_retries: Maximum retry attempts
            
        Returns:
            Tuple of (ValidationResult, attempts_used)
            
        Example:
            >>> async def retry_with_grounding():
            ...     return reporting_agent.regenerate_with_grounding(raw_metrics)
            >>> 
            >>> result, attempts = await validator.validate_with_retry(
            ...     llm_response=initial_response,
            ...     raw_metrics=raw_metrics,
            ...     retry_callback=retry_with_grounding
            ... )
        """
        for attempt in range(max_retries + 1):
            result = await self.validate(llm_response, raw_metrics)
            
            if result.is_valid or not retry_callback:
                return result, attempt + 1
            
            logger.warning(
                f"Validation failed (attempt {attempt + 1}/{max_retries + 1}). "
                f"Errors: {result.errors}"
            )
            
            if attempt < max_retries:
                # Retry with callback
                logger.info("Retrying with explicit grounding...")
                llm_response = await retry_callback(
                    errors=result.errors,
                    raw_metrics=raw_metrics
                )
        
        # All retries exhausted
        return result, max_retries + 1

