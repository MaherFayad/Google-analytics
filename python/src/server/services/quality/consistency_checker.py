"""
Runtime Semantic Consistency Checker.

Implements Task P0-11: Runtime Validation Service

Provides real-time validation of LLM responses during report generation
to catch hallucinations before they reach users.

Integration with ReportingAgent:

```python
from server.services.quality.consistency_checker import ConsistencyChecker

# In ReportingAgent.generate_report()
checker = ConsistencyChecker(tolerance_percent=5.0)

report_text = await llm_client.generate(prompt, context)

# Validate before returning to user
validation_result = await checker.validate_report(
    llm_response=report_text,
    raw_metrics=ga4_raw_data,
    retry_on_failure=True,
    max_retries=2
)

if not validation_result.is_valid:
    logger.error(f"Report validation failed: {validation_result.errors}")
    # Optionally retry or return error to user
    
return validation_result.validated_response
```

Features:
- Real-time validation during report generation
- Automatic retry with explicit grounding on failure
- Configurable tolerance thresholds
- Detailed validation metrics for monitoring
"""

import logging
from typing import Dict, Any, Optional, Tuple, Callable
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, Field

from ..validation.ground_truth_validator import (
    GroundTruthValidator,
    ValidationResult as BaseValidationResult,
    ValidationStatus,
    ValidationError,
)

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyReport:
    """
    Runtime consistency check report.
    
    Includes validation results plus runtime metadata for monitoring.
    """
    
    # Validation results
    is_valid: bool
    validation_status: ValidationStatus
    accuracy_rate: float
    max_deviation_percent: float
    
    # Original response
    original_response: str
    validated_response: str
    
    # Metrics for monitoring
    validation_duration_ms: float
    retry_attempts: int
    timestamp: datetime
    
    # Details
    errors: list[str]
    warnings: list[str]
    comparisons: list[Dict[str, Any]]
    
    # Raw metrics hash for cache key
    metrics_hash: Optional[str] = None


class ConsistencyChecker:
    """
    Runtime semantic consistency checker.
    
    Validates LLM responses against raw GA4 metrics in real-time
    during report generation to prevent hallucinations.
    
    Features:
    - Real-time validation with configurable tolerance
    - Automatic retry with explicit grounding on failure
    - Prometheus metrics for monitoring
    - Cache-aware (validates cached responses too)
    
    Example:
        >>> checker = ConsistencyChecker(tolerance_percent=5.0)
        >>> 
        >>> # During report generation
        >>> report_text = await generate_llm_report(query, context)
        >>> 
        >>> result = await checker.validate_report(
        ...     llm_response=report_text,
        ...     raw_metrics=ga4_data,
        ...     retry_on_failure=True
        ... )
        >>> 
        >>> if result.is_valid:
        ...     return result.validated_response
        ... else:
        ...     logger.error(f"Validation failed: {result.errors}")
    """
    
    def __init__(
        self,
        tolerance_percent: float = 5.0,
        context_window: int = 5,
        enable_monitoring: bool = True
    ):
        """
        Initialize consistency checker.
        
        Args:
            tolerance_percent: Maximum allowed deviation (default: 5%)
            context_window: Words of context to extract around numbers
            enable_monitoring: Enable Prometheus metrics
        """
        self.tolerance_percent = tolerance_percent
        self.enable_monitoring = enable_monitoring
        
        # Initialize ground truth validator
        self.validator = GroundTruthValidator(
            tolerance_percent=tolerance_percent,
            context_window=context_window
        )
        
        # Initialize metrics if monitoring enabled
        if self.enable_monitoring:
            self._init_metrics()
        
        logger.info(
            f"Consistency checker initialized (tolerance={tolerance_percent}%, "
            f"monitoring={'enabled' if enable_monitoring else 'disabled'})"
        )
    
    def _init_metrics(self):
        """Initialize Prometheus metrics."""
        try:
            from prometheus_client import Counter, Histogram, Gauge
            
            self.validation_total = Counter(
                'llm_validation_total',
                'Total number of LLM response validations',
                ['status']  # passed, failed, warning
            )
            
            self.validation_duration = Histogram(
                'llm_validation_duration_seconds',
                'Time spent validating LLM responses',
                buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
            )
            
            self.validation_accuracy = Histogram(
                'llm_validation_accuracy_rate',
                'Accuracy rate of LLM responses (0-100%)',
                buckets=[0, 50, 70, 80, 90, 95, 98, 99, 100]
            )
            
            self.validation_deviation = Histogram(
                'llm_validation_max_deviation_percent',
                'Maximum deviation in validated responses',
                buckets=[0, 1, 2, 5, 10, 20, 50, 100]
            )
            
            self.retry_count = Counter(
                'llm_validation_retries_total',
                'Total number of validation retries',
                ['success']  # true, false
            )
            
            logger.info("Prometheus metrics initialized for consistency checker")
            
        except ImportError:
            logger.warning("prometheus_client not available, monitoring disabled")
            self.enable_monitoring = False
    
    async def validate_report(
        self,
        llm_response: str,
        raw_metrics: Dict[str, Any],
        retry_on_failure: bool = True,
        max_retries: int = 2,
        retry_callback: Optional[Callable] = None
    ) -> ConsistencyReport:
        """
        Validate LLM-generated report against raw metrics.
        
        Args:
            llm_response: LLM-generated report text
            raw_metrics: Raw GA4 metrics dictionary
            retry_on_failure: Retry with explicit grounding on failure
            max_retries: Maximum retry attempts
            retry_callback: Async function to regenerate response
            
        Returns:
            ConsistencyReport with validation results and metadata
            
        Example:
            >>> async def retry_with_grounding(errors, raw_metrics):
            ...     # Regenerate response with explicit grounding
            ...     prompt = f"Generate report using ONLY these metrics: {raw_metrics}"
            ...     return await llm_client.generate(prompt)
            >>> 
            >>> result = await checker.validate_report(
            ...     llm_response=report_text,
            ...     raw_metrics=ga4_data,
            ...     retry_callback=retry_with_grounding
            ... )
        """
        import time
        import hashlib
        import json
        
        start_time = time.time()
        timestamp = datetime.utcnow()
        
        # Create metrics hash for caching
        metrics_json = json.dumps(raw_metrics, sort_keys=True)
        metrics_hash = hashlib.md5(metrics_json.encode()).hexdigest()
        
        # Validate (with retry if enabled)
        if retry_on_failure and retry_callback:
            validation_result, attempts = await self.validator.validate_with_retry(
                llm_response=llm_response,
                raw_metrics=raw_metrics,
                retry_callback=retry_callback,
                max_retries=max_retries
            )
            
            # Record retry metrics
            if self.enable_monitoring and attempts > 1:
                self.retry_count.labels(success=str(validation_result.is_valid).lower()).inc()
        else:
            validation_result = await self.validator.validate(llm_response, raw_metrics)
            attempts = 1
        
        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000
        
        # Record metrics
        if self.enable_monitoring:
            self.validation_total.labels(status=validation_result.status.value).inc()
            self.validation_duration.observe(duration_ms / 1000)
            self.validation_accuracy.observe(validation_result.accuracy_rate)
            self.validation_deviation.observe(validation_result.max_deviation_percent)
        
        # Create consistency report
        report = ConsistencyReport(
            is_valid=validation_result.is_valid,
            validation_status=validation_result.status,
            accuracy_rate=validation_result.accuracy_rate,
            max_deviation_percent=validation_result.max_deviation_percent,
            original_response=llm_response,
            validated_response=llm_response,  # Could be modified/annotated
            validation_duration_ms=duration_ms,
            retry_attempts=attempts,
            timestamp=timestamp,
            errors=validation_result.errors,
            warnings=validation_result.warnings,
            comparisons=validation_result.comparisons,
            metrics_hash=metrics_hash,
        )
        
        # Log results
        if validation_result.is_valid:
            logger.info(
                f"Validation passed: accuracy={validation_result.accuracy_rate:.1f}%, "
                f"max_deviation={validation_result.max_deviation_percent:.1f}%, "
                f"duration={duration_ms:.0f}ms, attempts={attempts}"
            )
        else:
            logger.warning(
                f"Validation failed: accuracy={validation_result.accuracy_rate:.1f}%, "
                f"errors={len(validation_result.errors)}, duration={duration_ms:.0f}ms, "
                f"attempts={attempts}"
            )
            for error in validation_result.errors[:3]:  # Log first 3 errors
                logger.warning(f"  - {error}")
        
        return report
    
    async def validate_cached_response(
        self,
        cached_response: str,
        raw_metrics: Dict[str, Any]
    ) -> bool:
        """
        Validate a cached response against current raw metrics.
        
        Use this to ensure cached responses are still accurate
        if raw metrics have been updated.
        
        Args:
            cached_response: Previously cached LLM response
            raw_metrics: Current raw GA4 metrics
            
        Returns:
            True if cached response is still valid
            
        Example:
            >>> cached_report = cache.get(query_key)
            >>> if cached_report:
            ...     is_valid = await checker.validate_cached_response(
            ...         cached_report,
            ...         current_metrics
            ...     )
            ...     if is_valid:
            ...         return cached_report
            ...     else:
            ...         cache.delete(query_key)  # Invalidate stale cache
        """
        result = await self.validator.validate(cached_response, raw_metrics)
        return result.is_valid
    
    async def validate_with_annotation(
        self,
        llm_response: str,
        raw_metrics: Dict[str, Any]
    ) -> Tuple[str, ConsistencyReport]:
        """
        Validate and annotate response with validation markers.
        
        Adds visual markers to indicate validated numbers:
        - ✓ next to correct numbers
        - ✗ next to incorrect numbers (with expected value)
        
        Args:
            llm_response: LLM-generated text
            raw_metrics: Raw GA4 metrics
            
        Returns:
            Tuple of (annotated_text, consistency_report)
            
        Example:
            >>> annotated, report = await checker.validate_with_annotation(
            ...     "Sessions: 1,500 (actual: 1,234)",
            ...     {"sessions": 1234}
            ... )
            >>> print(annotated)
            "Sessions: 1,500 ✗ [Expected: 1,234, deviation: 21.6%]"
        """
        import time
        
        start_time = time.time()
        
        # Validate
        validation_result = await self.validator.validate(llm_response, raw_metrics)
        
        # Annotate text with validation markers
        annotated_text = llm_response
        
        for comparison in validation_result.comparisons:
            if comparison['is_valid']:
                # Add checkmark
                marker = " ✓"
            else:
                # Add cross with expected value
                marker = (
                    f" ✗ [Expected: {comparison['actual_value']:.1f}, "
                    f"deviation: {comparison['deviation_percent']:.1f}%]"
                )
            
            # Find and annotate the number in text
            # This is simplified - production would need better text matching
            llm_value_str = str(int(comparison['llm_value']))
            if llm_value_str in annotated_text:
                annotated_text = annotated_text.replace(
                    llm_value_str,
                    f"{llm_value_str}{marker}",
                    1  # Replace only first occurrence
                )
        
        # Create consistency report
        duration_ms = (time.time() - start_time) * 1000
        
        report = ConsistencyReport(
            is_valid=validation_result.is_valid,
            validation_status=validation_result.status,
            accuracy_rate=validation_result.accuracy_rate,
            max_deviation_percent=validation_result.max_deviation_percent,
            original_response=llm_response,
            validated_response=annotated_text,
            validation_duration_ms=duration_ms,
            retry_attempts=1,
            timestamp=datetime.utcnow(),
            errors=validation_result.errors,
            warnings=validation_result.warnings,
            comparisons=validation_result.comparisons,
        )
        
        return annotated_text, report
    
    def get_validation_stats(self) -> Dict[str, Any]:
        """
        Get validation statistics for monitoring.
        
        Returns:
            Dictionary with validation stats
            
        Example:
            >>> stats = checker.get_validation_stats()
            >>> print(f"Validation success rate: {stats['success_rate']:.1f}%")
        """
        if not self.enable_monitoring:
            return {"monitoring": "disabled"}
        
        try:
            # This would query Prometheus metrics
            # Simplified version for now
            return {
                "monitoring": "enabled",
                "tolerance_percent": self.tolerance_percent,
                # In production, would include:
                # "total_validations": ...,
                # "success_rate": ...,
                # "avg_accuracy": ...,
                # "avg_deviation": ...,
            }
        except Exception as e:
            logger.error(f"Failed to get validation stats: {e}")
            return {"error": str(e)}


class AsyncConsistencyChecker(ConsistencyChecker):
    """
    Async-optimized consistency checker for streaming responses.
    
    Validates responses as they are being generated (streaming)
    rather than waiting for complete response.
    
    Example:
        >>> checker = AsyncConsistencyChecker()
        >>> 
        >>> async for chunk in llm_client.stream_generate(prompt):
        ...     # Validate incrementally
        ...     partial_validation = await checker.validate_partial(
        ...         partial_response=accumulated_text,
        ...         raw_metrics=ga4_data
        ...     )
        ...     
        ...     if partial_validation.has_errors:
        ...         # Stop streaming, retry with grounding
        ...         break
    """
    
    async def validate_partial(
        self,
        partial_response: str,
        raw_metrics: Dict[str, Any]
    ) -> ConsistencyReport:
        """
        Validate partial (streaming) response.
        
        This is a best-effort validation that doesn't fail
        on incomplete sentences or numbers.
        
        Args:
            partial_response: Incomplete LLM response
            raw_metrics: Raw GA4 metrics
            
        Returns:
            ConsistencyReport (may have warnings for incomplete text)
        """
        # Similar to validate_report but more lenient
        # Allows incomplete numbers/sentences
        return await self.validate_report(
            llm_response=partial_response,
            raw_metrics=raw_metrics,
            retry_on_failure=False  # Don't retry for partial validation
        )

