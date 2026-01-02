"""
RAG Confidence Filtering Service

Implements Task P0-19: RAG Retrieval Confidence Filtering

Filters vector search results based on similarity scores to prevent
low-quality, irrelevant context from degrading LLM reports.

Features:
- Configurable confidence thresholds
- Multi-level confidence status (high/medium/low/no_relevant)
- Minimum results enforcement
- Graceful degradation strategy

Usage:
    from src.server.services.search.confidence_filter import ConfidenceFilter
    
    filter = ConfidenceFilter()
    filtered = filter.filter_results(raw_results, threshold=0.70)
"""

import logging
from typing import List, Literal, Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class VectorSearchResult:
    """Individual vector search result."""
    content: str
    similarity_score: float
    metadata: Dict[str, Any]


@dataclass
class FilteredResults:
    """Filtered vector search results with confidence assessment."""
    results: List[VectorSearchResult]
    confidence: float
    status: Literal["high_confidence", "medium_confidence", "low_confidence", "no_relevant_context"]
    filtered_count: int
    total_found: int


class ConfidenceFilter:
    """
    Filters RAG retrieval results based on confidence thresholds.
    
    Implements Task P0-19: RAG Retrieval Confidence Filtering
    
    Prevents low-quality, irrelevant context from degrading LLM reports
    by filtering out results below configurable similarity thresholds.
    """
    
    # Default thresholds (configurable via Settings)
    HIGH_CONFIDENCE_THRESHOLD = 0.85
    MEDIUM_CONFIDENCE_THRESHOLD = 0.70
    LOW_CONFIDENCE_THRESHOLD = 0.50
    
    # Minimum results to return (even if below threshold)
    MIN_RESULTS = 3
    
    # Threshold relaxation factor when min_results not met
    RELAXATION_FACTOR = 0.9
    
    def __init__(
        self,
        high_threshold: float = HIGH_CONFIDENCE_THRESHOLD,
        medium_threshold: float = MEDIUM_CONFIDENCE_THRESHOLD,
        low_threshold: float = LOW_CONFIDENCE_THRESHOLD,
        min_results: int = MIN_RESULTS
    ):
        """
        Initialize confidence filter with custom thresholds.
        
        Args:
            high_threshold: Threshold for high confidence (default: 0.85)
            medium_threshold: Threshold for medium confidence (default: 0.70)
            low_threshold: Threshold for low confidence (default: 0.50)
            min_results: Minimum results to return (default: 3)
        """
        self.high_threshold = high_threshold
        self.medium_threshold = medium_threshold
        self.low_threshold = low_threshold
        self.min_results = min_results
        
        logger.info(
            f"Confidence filter initialized: "
            f"high={high_threshold}, medium={medium_threshold}, "
            f"low={low_threshold}, min_results={min_results}"
        )
    
    def filter_results(
        self,
        results: List[VectorSearchResult],
        threshold: Optional[float] = None,
        max_results: int = 10
    ) -> FilteredResults:
        """
        Filter results by confidence threshold.
        
        Args:
            results: Raw vector search results
            threshold: Minimum similarity threshold (default: medium_threshold)
            max_results: Maximum number of results to return
            
        Returns:
            FilteredResults with confidence assessment
        """
        threshold = threshold or self.medium_threshold
        total_found = len(results)
        
        # Filter by threshold
        high_confidence_results = [
            r for r in results
            if r.similarity_score >= threshold
        ]
        
        filtered_count = total_found - len(high_confidence_results)
        
        # Handle insufficient results
        if len(high_confidence_results) < self.min_results and total_found > 0:
            logger.info(
                f"Insufficient high-confidence results ({len(high_confidence_results)}), "
                f"relaxing threshold to meet min_results={self.min_results}"
            )
            
            # Relax threshold to get minimum results
            relaxed_threshold = threshold * self.RELAXATION_FACTOR
            high_confidence_results = [
                r for r in results
                if r.similarity_score >= relaxed_threshold
            ][:self.min_results]
            
            filtered_count = total_found - len(high_confidence_results)
        
        # Limit to max_results
        final_results = high_confidence_results[:max_results]
        
        # Calculate average confidence
        if final_results:
            avg_confidence = sum(r.similarity_score for r in final_results) / len(final_results)
        else:
            avg_confidence = 0.0
        
        # Determine confidence status
        status = self._get_confidence_status(avg_confidence)
        
        logger.info(
            f"Confidence filtering complete: "
            f"total={total_found}, filtered={filtered_count}, "
            f"returned={len(final_results)}, confidence={avg_confidence:.2f}, "
            f"status={status}"
        )
        
        return FilteredResults(
            results=final_results,
            confidence=avg_confidence,
            status=status,
            filtered_count=filtered_count,
            total_found=total_found
        )
    
    def _get_confidence_status(
        self,
        confidence: float
    ) -> Literal["high_confidence", "medium_confidence", "low_confidence", "no_relevant_context"]:
        """
        Determine confidence status level.
        
        Args:
            confidence: Average similarity score
            
        Returns:
            Confidence status level
        """
        if confidence >= self.high_threshold:
            return "high_confidence"
        elif confidence >= self.medium_threshold:
            return "medium_confidence"
        elif confidence >= self.low_threshold:
            return "low_confidence"
        else:
            return "no_relevant_context"
    
    def should_use_fresh_data_only(self, status: str) -> bool:
        """
        Determine if system should fallback to fresh data only.
        
        When no relevant cached context is found, the system should
        proceed with fresh GA4 data only (graceful degradation).
        
        Args:
            status: Confidence status level
            
        Returns:
            True if should use fresh data only, False otherwise
        """
        return status == "no_relevant_context"
    
    def get_confidence_disclaimer(
        self,
        status: str,
        confidence: float
    ) -> Optional[str]:
        """
        Generate confidence disclaimer for reports.
        
        Args:
            status: Confidence status level
            confidence: Average confidence score
            
        Returns:
            Disclaimer text or None
        """
        if status == "high_confidence":
            return None  # No disclaimer needed
        
        elif status == "medium_confidence":
            return (
                f"This analysis is based on moderately relevant historical patterns "
                f"({confidence:.0%} confidence). Insights should be considered as "
                f"general guidance."
            )
        
        elif status == "low_confidence":
            return (
                f"This analysis is based on loosely related patterns "
                f"({confidence:.0%} confidence). Consider this as exploratory "
                f"analysis and validate findings with additional data."
            )
        
        else:  # no_relevant_context
            return (
                "No highly relevant historical patterns found. "
                "This analysis is based solely on current data without "
                "historical context for comparison."
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get filter statistics.
        
        Returns:
            Filter configuration and statistics
        """
        return {
            "high_threshold": self.high_threshold,
            "medium_threshold": self.medium_threshold,
            "low_threshold": self.low_threshold,
            "min_results": self.min_results,
            "relaxation_factor": self.RELAXATION_FACTOR
        }


# Default filter instance
default_confidence_filter = ConfidenceFilter()

