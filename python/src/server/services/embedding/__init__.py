"""
Embedding services for vector generation and validation.

This package contains:
- validator: Embedding quality validation (Task P0-16)
- generator: Embedding generation from OpenAI (Task 8.2)
- quality_checker: Quality assurance pipeline (Task P0-5)
"""

from .validator import EmbeddingValidator, validate_embedding, EmbeddingValidationError
from .generator import EmbeddingGenerator, EmbeddingGenerationError

__all__ = [
    "EmbeddingValidator",
    "validate_embedding",
    "EmbeddingValidationError",
    "EmbeddingGenerator",
    "EmbeddingGenerationError",
]

