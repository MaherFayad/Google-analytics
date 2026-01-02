"""
Validation services for data quality and integrity.

This package contains validators for ensuring:
- Ground truth consistency (LLM vs raw metrics)
- Citation accuracy (source tracking)
- Context grounding (no hallucinations)
"""

from .ground_truth_validator import (
    GroundTruthValidator,
    ValidationResult,
    ValidationError,
)
from .number_extractor import NumberExtractor, ExtractedNumber
from .citation_validator import (
    CitationValidator,
    CitationValidationReport,
    CitationMismatchError,
)
from .context_grounding_checker import (
    ContextGroundingChecker,
    GroundingReport,
    GroundingStatus,
)

__all__ = [
    "GroundTruthValidator",
    "ValidationResult",
    "ValidationError",
    "NumberExtractor",
    "ExtractedNumber",
    "CitationValidator",
    "CitationValidationReport",
    "CitationMismatchError",
    "ContextGroundingChecker",
    "GroundingReport",
    "GroundingStatus",
]

