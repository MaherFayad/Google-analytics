"""
Embedding services for vector generation and validation.

This package contains:
- validator: Embedding quality validation (Task P0-16)
- generator: Embedding generation from OpenAI (Task 8.2)
- quality_checker: Quality assurance pipeline (Task P0-5)
- version_migrator: Blue-green embedding model migration (Task P0-26)
- quality_comparator: A/B testing for model versions (Task P0-26)
"""

from .validator import EmbeddingValidator, validate_embedding, EmbeddingValidationError
from .generator import EmbeddingGenerator, EmbeddingGenerationError
from .version_migrator import (
    EmbeddingVersionMigrator,
    EmbeddingModelConfig,
    MigrationPhase,
    MigrationStatus,
    MigrationResult
)
from .quality_comparator import (
    EmbeddingQualityComparator,
    VersionComparisonResult
)

__all__ = [
    "EmbeddingValidator",
    "validate_embedding",
    "EmbeddingValidationError",
    "EmbeddingGenerator",
    "EmbeddingGenerationError",
    "EmbeddingVersionMigrator",
    "EmbeddingModelConfig",
    "MigrationPhase",
    "MigrationStatus",
    "MigrationResult",
    "EmbeddingQualityComparator",
    "VersionComparisonResult",
]

