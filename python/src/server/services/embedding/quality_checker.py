"""
Comprehensive Embedding Quality Assurance Pipeline.

Implements Task P0-5: Embedding Quality Assurance Pipeline

Features:
- Pre-storage validation (extends Task P0-16 validator)
- Semantic consistency checks
- Quality scoring
- Batch validation with statistics
- Integration with drift detector

Quality Checks:
1. Dimension validation (1536 for text-embedding-3-small)
2. NaN/Inf detection
3. Zero vector detection
4. Magnitude validation (0.1 - 100)
5. Semantic consistency (re-embed and compare)
6. Distribution analysis
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from datetime import datetime

from pydantic import BaseModel, Field

from .validator import EmbeddingValidator, EmbeddingValidationResult, EmbeddingValidationError

logger = logging.getLogger(__name__)


class EmbeddingQualityScore(BaseModel):
    """
    Quality score for embedding.
    
    Score calculation (0.0 - 1.0):
    - Dimension correct: +0.3
    - No NaN/Inf: +0.2
    - Not zero vector: +0.2
    - Magnitude in range: +0.1
    - Good distribution (std > 0.01): +0.1
    - Semantic consistency > 95%: +0.1
    """
    
    score: float = Field(ge=0.0, le=1.0, description="Overall quality score")
    dimension_valid: bool = True
    no_invalid_values: bool = True  # No NaN/Inf
    not_zero_vector: bool = True
    magnitude_ok: bool = True
    distribution_ok: bool = True
    semantic_consistency: Optional[float] = None  # If tested
    
    details: Dict[str, Any] = Field(default_factory=dict)


class EmbeddingQualityChecker:
    """
    Comprehensive quality checker for embeddings.
    
    Implements Task P0-5: Embedding Quality Assurance Pipeline
    
    Usage:
        checker = EmbeddingQualityChecker()
        
        # Check single embedding
        quality = await checker.check_quality(
            embedding=vector,
            text="Original text for semantic check"
        )
        
        if quality.score < 0.7:
            logger.warning("Low quality embedding detected")
    """
    
    def __init__(self, embedding_generator=None):
        """
        Initialize quality checker.
        
        Args:
            embedding_generator: Optional generator for semantic consistency checks
        """
        self.embedding_generator = embedding_generator
        self.validator = EmbeddingValidator()
        
        # Statistics
        self._total_checked = 0
        self._high_quality_count = 0  # score >= 0.8
        self._low_quality_count = 0   # score < 0.7
        
        logger.info("Embedding quality checker initialized")
    
    async def check_quality(
        self,
        embedding: List[float],
        text: Optional[str] = None,
        check_semantic_consistency: bool = False,
        model: str = "text-embedding-3-small"
    ) -> EmbeddingQualityScore:
        """
        Perform comprehensive quality check on embedding.
        
        Args:
            embedding: Embedding vector to check
            text: Original text (for semantic consistency check)
            check_semantic_consistency: If True, re-embed and compare
            model: Embedding model name
        
        Returns:
            EmbeddingQualityScore with detailed quality assessment
        """
        self._total_checked += 1
        
        quality = EmbeddingQualityScore(score=0.0)
        
        # 1. Run basic validation (from Task P0-16)
        try:
            validation = self.validator.validate(embedding, strict=False, model=model)
            
            quality.dimension_valid = validation.valid and not any(
                "dimension" in err.lower() for err in validation.errors
            )
            quality.no_invalid_values = not any(
                "nan" in err.lower() or "inf" in err.lower()
                for err in validation.errors
            )
            quality.not_zero_vector = not any(
                "zero vector" in err.lower() for err in validation.errors
            )
            
            # Check magnitude
            magnitude = validation.metadata.get("magnitude", 0)
            quality.magnitude_ok = (
                self.validator.MIN_MAGNITUDE <= magnitude <= self.validator.MAX_MAGNITUDE
            )
            
            # Check distribution
            std = validation.metadata.get("std", 0)
            quality.distribution_ok = std >= 0.01
            
            quality.details = validation.metadata
        
        except Exception as e:
            logger.error(f"Quality check failed during validation: {e}")
            quality.score = 0.0
            return quality
        
        # Calculate base score
        score = 0.0
        if quality.dimension_valid:
            score += 0.3
        if quality.no_invalid_values:
            score += 0.2
        if quality.not_zero_vector:
            score += 0.2
        if quality.magnitude_ok:
            score += 0.1
        if quality.distribution_ok:
            score += 0.1
        
        # 2. Semantic consistency check (optional, expensive)
        if check_semantic_consistency and text and self.embedding_generator:
            try:
                semantic_score = await self._check_semantic_consistency(
                    embedding, text
                )
                quality.semantic_consistency = semantic_score
                
                if semantic_score >= 0.95:
                    score += 0.1
                else:
                    logger.warning(
                        f"Low semantic consistency: {semantic_score:.4f} "
                        "(expected >= 0.95)"
                    )
            
            except Exception as e:
                logger.error(f"Semantic consistency check failed: {e}")
        
        quality.score = score
        
        # Track statistics
        if score >= 0.8:
            self._high_quality_count += 1
        elif score < 0.7:
            self._low_quality_count += 1
        
        logger.debug(
            f"Embedding quality score: {score:.2f} "
            f"(dimension: {quality.dimension_valid}, "
            f"no_invalid: {quality.no_invalid_values})"
        )
        
        return quality
    
    async def _check_semantic_consistency(
        self,
        original_embedding: List[float],
        text: str
    ) -> float:
        """
        Check semantic consistency by re-embedding.
        
        Generates new embedding from same text and computes similarity.
        
        Args:
            original_embedding: Original embedding vector
            text: Source text
        
        Returns:
            Cosine similarity score (0.0 - 1.0)
        """
        if not self.embedding_generator:
            logger.warning("No embedding generator available for consistency check")
            return 1.0
        
        try:
            # Generate new embedding
            new_embedding = await self.embedding_generator.generate(text)
            
            # Compute cosine similarity
            similarity = self._cosine_similarity(original_embedding, new_embedding)
            
            logger.debug(f"Semantic consistency: {similarity:.4f}")
            
            return similarity
        
        except Exception as e:
            logger.error(f"Failed to check semantic consistency: {e}")
            return 0.0
    
    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """
        Compute cosine similarity between two vectors.
        
        Args:
            vec1: First vector
            vec2: Second vector
        
        Returns:
            Cosine similarity (0.0 - 1.0)
        """
        arr1 = np.array(vec1)
        arr2 = np.array(vec2)
        
        # Compute cosine similarity
        dot_product = np.dot(arr1, arr2)
        norm1 = np.linalg.norm(arr1)
        norm2 = np.linalg.norm(arr2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        similarity = dot_product / (norm1 * norm2)
        
        # Clamp to [0, 1] range
        return float(max(0.0, min(1.0, similarity)))
    
    async def check_batch_quality(
        self,
        embeddings: List[List[float]],
        texts: Optional[List[str]] = None,
        check_semantic: bool = False,
        model: str = "text-embedding-3-small"
    ) -> Tuple[List[EmbeddingQualityScore], Dict[str, Any]]:
        """
        Check quality of batch of embeddings.
        
        Args:
            embeddings: List of embedding vectors
            texts: Original texts (for semantic check)
            check_semantic: Enable semantic consistency checks
            model: Embedding model name
        
        Returns:
            Tuple of (quality scores list, batch statistics)
        """
        logger.info(f"Checking quality for batch of {len(embeddings)} embeddings")
        
        # Check each embedding
        quality_scores = []
        for i, embedding in enumerate(embeddings):
            text = texts[i] if texts and i < len(texts) else None
            
            quality = await self.check_quality(
                embedding=embedding,
                text=text,
                check_semantic_consistency=check_semantic,
                model=model
            )
            
            quality_scores.append(quality)
        
        # Calculate batch statistics
        avg_score = np.mean([q.score for q in quality_scores])
        min_score = np.min([q.score for q in quality_scores])
        max_score = np.max([q.score for q in quality_scores])
        
        high_quality = sum(1 for q in quality_scores if q.score >= 0.8)
        low_quality = sum(1 for q in quality_scores if q.score < 0.7)
        
        stats = {
            "total_embeddings": len(embeddings),
            "avg_quality_score": float(avg_score),
            "min_quality_score": float(min_score),
            "max_quality_score": float(max_score),
            "high_quality_count": high_quality,
            "low_quality_count": low_quality,
            "high_quality_percent": round(high_quality / len(embeddings) * 100, 2),
            "low_quality_percent": round(low_quality / len(embeddings) * 100, 2),
        }
        
        logger.info(
            f"Batch quality check complete: avg={avg_score:.3f}, "
            f"high_quality={high_quality}/{len(embeddings)}, "
            f"low_quality={low_quality}/{len(embeddings)}"
        )
        
        return quality_scores, stats
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get quality checker statistics."""
        return {
            "total_checked": self._total_checked,
            "high_quality_count": self._high_quality_count,
            "low_quality_count": self._low_quality_count,
            "high_quality_percent": (
                round(self._high_quality_count / self._total_checked * 100, 2)
                if self._total_checked > 0 else 0
            )
        }

