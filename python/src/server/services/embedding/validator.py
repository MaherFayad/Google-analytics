"""
Embedding validation service.

Implements Task P0-16: Embedding Dimension Validation Middleware

This module validates embedding vectors to prevent database crashes:
1. Dimension validation (must be exactly 1536 for text-embedding-3-small)
2. NaN/Inf detection
3. Zero vector detection
4. Magnitude validation
5. Type validation

CRITICAL: Prevents pgvector crashes with dimension mismatches.
"""

import logging
from typing import List, Optional, Union, Dict, Any
import numpy as np
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class EmbeddingValidationError(Exception):
    """Raised when embedding fails validation."""
    pass


class EmbeddingValidationResult(BaseModel):
    """Result of embedding validation."""
    
    valid: bool = Field(description="Whether embedding passed validation")
    errors: List[str] = Field(default_factory=list, description="List of validation errors")
    warnings: List[str] = Field(default_factory=list, description="List of validation warnings")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Validation metadata")
    
    def add_error(self, error: str) -> None:
        """Add validation error."""
        self.valid = False
        self.errors.append(error)
    
    def add_warning(self, warning: str) -> None:
        """Add validation warning."""
        self.warnings.append(warning)


class EmbeddingValidator:
    """
    Validate embedding vectors before database insertion.
    
    Task P0-16 Implementation:
    - Prevents dimension mismatches (must be 1536)
    - Detects NaN/Inf values
    - Identifies zero vectors
    - Validates magnitude range
    - Ensures proper type (List[float])
    """
    
    # Configuration
    EXPECTED_DIMENSION = 1536  # text-embedding-3-small
    MIN_MAGNITUDE = 0.1
    MAX_MAGNITUDE = 100.0
    MAX_ZERO_ELEMENTS = 10  # Allow up to 10 zero elements
    
    @staticmethod
    def validate(
        embedding: Union[List[float], np.ndarray],
        strict: bool = True,
        model: str = "text-embedding-3-small"
    ) -> EmbeddingValidationResult:
        """
        Validate embedding vector.
        
        Args:
            embedding: Embedding vector (1536-dim for text-embedding-3-small)
            strict: If True, raise exception on validation failure
            model: Embedding model name (for dimension lookup)
            
        Returns:
            EmbeddingValidationResult with validation status
            
        Raises:
            EmbeddingValidationError: If strict=True and validation fails
            
        Example:
            result = EmbeddingValidator.validate(embedding, strict=False)
            if not result.valid:
                logger.error(f"Validation errors: {result.errors}")
        """
        result = EmbeddingValidationResult(valid=True)
        
        # Get expected dimension for model
        expected_dim = EmbeddingValidator._get_expected_dimension(model)
        
        # 1. Type validation
        if not isinstance(embedding, (list, np.ndarray)):
            result.add_error(
                f"Invalid type: {type(embedding)}. Expected list or np.ndarray"
            )
            if strict:
                raise EmbeddingValidationError(result.errors[0])
            return result
        
        # Convert to numpy array for validation
        try:
            embedding_array = np.array(embedding, dtype=np.float32)
        except (ValueError, TypeError) as e:
            result.add_error(f"Cannot convert to numpy array: {e}")
            if strict:
                raise EmbeddingValidationError(result.errors[0])
            return result
        
        # 2. Dimension validation (CRITICAL)
        if embedding_array.shape[0] != expected_dim:
            result.add_error(
                f"Invalid dimensions: got {embedding_array.shape[0]}, "
                f"expected {expected_dim} for {model}"
            )
            if strict:
                raise EmbeddingValidationError(result.errors[0])
            return result
        
        # Store dimension in metadata
        result.metadata["dimension"] = int(embedding_array.shape[0])
        result.metadata["model"] = model
        
        # 3. NaN/Inf detection (CRITICAL)
        nan_count = np.isnan(embedding_array).sum()
        inf_count = np.isinf(embedding_array).sum()
        
        if nan_count > 0:
            result.add_error(f"Contains {nan_count} NaN values")
        
        if inf_count > 0:
            result.add_error(f"Contains {inf_count} Inf values")
        
        if nan_count > 0 or inf_count > 0:
            if strict:
                raise EmbeddingValidationError(
                    f"Embedding contains NaN ({nan_count}) or Inf ({inf_count}) values"
                )
            return result
        
        # 4. Zero vector detection
        zero_count = (embedding_array == 0).sum()
        
        if zero_count == len(embedding_array):
            result.add_error("Embedding is a zero vector (all elements are 0)")
            if strict:
                raise EmbeddingValidationError(result.errors[0])
            return result
        
        if zero_count > EmbeddingValidator.MAX_ZERO_ELEMENTS:
            result.add_warning(
                f"High number of zero elements: {zero_count} "
                f"(threshold: {EmbeddingValidator.MAX_ZERO_ELEMENTS})"
            )
        
        result.metadata["zero_count"] = int(zero_count)
        
        # 5. Magnitude validation
        magnitude = float(np.linalg.norm(embedding_array))
        result.metadata["magnitude"] = magnitude
        
        if magnitude < EmbeddingValidator.MIN_MAGNITUDE:
            result.add_warning(
                f"Low magnitude: {magnitude:.4f} "
                f"(min threshold: {EmbeddingValidator.MIN_MAGNITUDE})"
            )
        
        if magnitude > EmbeddingValidator.MAX_MAGNITUDE:
            result.add_warning(
                f"High magnitude: {magnitude:.4f} "
                f"(max threshold: {EmbeddingValidator.MAX_MAGNITUDE})"
            )
        
        # 6. Statistical checks
        mean_value = float(np.mean(embedding_array))
        std_value = float(np.std(embedding_array))
        min_value = float(np.min(embedding_array))
        max_value = float(np.max(embedding_array))
        
        result.metadata.update({
            "mean": mean_value,
            "std": std_value,
            "min": min_value,
            "max": max_value
        })
        
        # Check for unusual distributions
        if std_value < 0.01:
            result.add_warning(
                f"Very low standard deviation: {std_value:.6f}. "
                "Embedding may be degenerate."
            )
        
        # Log validation result
        if result.valid:
            logger.debug(
                f"Embedding validation passed: dim={result.metadata['dimension']}, "
                f"magnitude={magnitude:.4f}, zero_count={zero_count}"
            )
        else:
            logger.error(
                f"Embedding validation failed: {', '.join(result.errors)}"
            )
        
        if result.warnings:
            logger.warning(
                f"Embedding validation warnings: {', '.join(result.warnings)}"
            )
        
        return result
    
    @staticmethod
    def _get_expected_dimension(model: str) -> int:
        """
        Get expected dimension for embedding model.
        
        Args:
            model: Model name
            
        Returns:
            Expected dimension
        """
        model_dimensions = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        
        return model_dimensions.get(model, 1536)  # Default to 1536
    
    @staticmethod
    def validate_batch(
        embeddings: List[Union[List[float], np.ndarray]],
        strict: bool = False,
        model: str = "text-embedding-3-small"
    ) -> List[EmbeddingValidationResult]:
        """
        Validate a batch of embeddings.
        
        Args:
            embeddings: List of embedding vectors
            strict: If True, raise exception on first validation failure
            model: Embedding model name
            
        Returns:
            List of validation results
            
        Raises:
            EmbeddingValidationError: If strict=True and any validation fails
        """
        results = []
        
        for i, embedding in enumerate(embeddings):
            try:
                result = EmbeddingValidator.validate(embedding, strict=strict, model=model)
                results.append(result)
            except EmbeddingValidationError as e:
                logger.error(f"Batch validation failed at index {i}: {e}")
                if strict:
                    raise
                # Create failed result
                failed_result = EmbeddingValidationResult(valid=False)
                failed_result.add_error(str(e))
                results.append(failed_result)
        
        # Log batch summary
        total = len(results)
        valid_count = sum(1 for r in results if r.valid)
        invalid_count = total - valid_count
        
        logger.info(
            f"Batch validation complete: {valid_count}/{total} valid, "
            f"{invalid_count} invalid"
        )
        
        return results


# Convenience function
def validate_embedding(
    embedding: Union[List[float], np.ndarray],
    strict: bool = True,
    model: str = "text-embedding-3-small"
) -> EmbeddingValidationResult:
    """
    Validate single embedding vector.
    
    Convenience function for EmbeddingValidator.validate().
    
    Args:
        embedding: Embedding vector
        strict: If True, raise exception on validation failure
        model: Embedding model name
        
    Returns:
        EmbeddingValidationResult
        
    Raises:
        EmbeddingValidationError: If strict=True and validation fails
        
    Usage:
        from server.services.embedding import validate_embedding
        
        try:
            result = validate_embedding(embedding, strict=True)
            # Embedding is valid
        except EmbeddingValidationError as e:
            logger.error(f"Invalid embedding: {e}")
    """
    return EmbeddingValidator.validate(embedding, strict=strict, model=model)

