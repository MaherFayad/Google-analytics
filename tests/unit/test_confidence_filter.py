"""
Unit Tests for RAG Confidence Filtering

Implements Task P0-19: RAG Retrieval Confidence Filtering

Tests:
- Confidence threshold filtering
- Status level determination
- Minimum results enforcement
- Threshold relaxation
- Graceful degradation logic
"""

import pytest
from src.server.services.search.confidence_filter import (
    ConfidenceFilter,
    VectorSearchResult,
    FilteredResults
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def confidence_filter():
    """Default confidence filter instance."""
    return ConfidenceFilter()


@pytest.fixture
def mock_high_confidence_results():
    """Mock high confidence search results."""
    return [
        VectorSearchResult(
            content="Mobile conversions increased 21.7%",
            similarity_score=0.92,
            metadata={"source": "ga4_metrics", "date": "2025-01-01"}
        ),
        VectorSearchResult(
            content="Desktop sessions decreased 5.2%",
            similarity_score=0.88,
            metadata={"source": "ga4_metrics", "date": "2025-01-02"}
        ),
        VectorSearchResult(
            content="Bounce rate improved from 45% to 42%",
            similarity_score=0.85,
            metadata={"source": "ga4_metrics", "date": "2025-01-03"}
        ),
    ]


@pytest.fixture
def mock_mixed_confidence_results():
    """Mock mixed confidence search results."""
    return [
        VectorSearchResult(
            content="Mobile conversions increased 21.7%",
            similarity_score=0.92,
            metadata={"source": "ga4_metrics"}
        ),
        VectorSearchResult(
            content="Irrelevant homepage data",
            similarity_score=0.45,
            metadata={"source": "ga4_metrics"}
        ),
        VectorSearchResult(
            content="Desktop sessions decreased 5.2%",
            similarity_score=0.88,
            metadata={"source": "ga4_metrics"}
        ),
        VectorSearchResult(
            content="Another low quality match",
            similarity_score=0.35,
            metadata={"source": "ga4_metrics"}
        ),
    ]


@pytest.fixture
def mock_low_confidence_results():
    """Mock low confidence search results."""
    return [
        VectorSearchResult(
            content="Loosely related content",
            similarity_score=0.55,
            metadata={"source": "ga4_metrics"}
        ),
        VectorSearchResult(
            content="Another low match",
            similarity_score=0.52,
            metadata={"source": "ga4_metrics"}
        ),
        VectorSearchResult(
            content="Barely relevant",
            similarity_score=0.51,
            metadata={"source": "ga4_metrics"}
        ),
    ]


# ============================================================================
# Filter Results Tests
# ============================================================================

def test_filter_high_confidence_results(confidence_filter, mock_high_confidence_results):
    """Test: High confidence results pass through unfiltered."""
    filtered = confidence_filter.filter_results(mock_high_confidence_results, threshold=0.70)
    
    assert len(filtered.results) == 3
    assert filtered.confidence >= 0.85
    assert filtered.status == "high_confidence"
    assert filtered.filtered_count == 0
    assert filtered.total_found == 3


def test_filter_mixed_confidence_results(confidence_filter, mock_mixed_confidence_results):
    """Test: Low confidence results filtered out."""
    filtered = confidence_filter.filter_results(mock_mixed_confidence_results, threshold=0.70)
    
    assert len(filtered.results) == 2  # 2 high quality results
    assert filtered.confidence >= 0.85  # Average of 0.92 and 0.88
    assert filtered.status == "high_confidence"
    assert filtered.filtered_count == 2  # 2 filtered out
    assert filtered.total_found == 4


def test_filter_low_confidence_results(confidence_filter, mock_low_confidence_results):
    """Test: Low confidence results returned when no high confidence available."""
    filtered = confidence_filter.filter_results(mock_low_confidence_results, threshold=0.70)
    
    # Should relax threshold to return min_results
    assert len(filtered.results) == 3  # min_results = 3
    assert 0.50 <= filtered.confidence < 0.70
    assert filtered.status == "low_confidence"
    assert filtered.total_found == 3


def test_filter_no_relevant_context():
    """Test: Very low confidence results marked as no_relevant_context."""
    filter = ConfidenceFilter()
    
    very_low_results = [
        VectorSearchResult(content="Irrelevant", similarity_score=0.20, metadata={}),
        VectorSearchResult(content="Not related", similarity_score=0.15, metadata={}),
    ]
    
    filtered = filter.filter_results(very_low_results, threshold=0.70)
    
    assert len(filtered.results) <= 2
    assert filtered.confidence < 0.50
    assert filtered.status == "no_relevant_context"


def test_filter_empty_results(confidence_filter):
    """Test: Empty results handled gracefully."""
    filtered = confidence_filter.filter_results([], threshold=0.70)
    
    assert len(filtered.results) == 0
    assert filtered.confidence == 0.0
    assert filtered.status == "no_relevant_context"
    assert filtered.filtered_count == 0
    assert filtered.total_found == 0


# ============================================================================
# Threshold Configuration Tests
# ============================================================================

def test_custom_thresholds():
    """Test: Custom thresholds applied correctly."""
    filter = ConfidenceFilter(
        high_threshold=0.90,
        medium_threshold=0.75,
        low_threshold=0.60
    )
    
    assert filter.high_threshold == 0.90
    assert filter.medium_threshold == 0.75
    assert filter.low_threshold == 0.60


def test_min_results_enforcement(confidence_filter):
    """Test: Min results enforced even with low confidence."""
    results = [
        VectorSearchResult(content="Result 1", similarity_score=0.65, metadata={}),
        VectorSearchResult(content="Result 2", similarity_score=0.62, metadata={}),
        VectorSearchResult(content="Result 3", similarity_score=0.60, metadata={}),
        VectorSearchResult(content="Result 4", similarity_score=0.55, metadata={}),
    ]
    
    filtered = confidence_filter.filter_results(results, threshold=0.70)
    
    # Should relax threshold to return min_results (3)
    assert len(filtered.results) == 3


def test_max_results_limit(confidence_filter, mock_high_confidence_results):
    """Test: Max results limit enforced."""
    # Create many high confidence results
    many_results = mock_high_confidence_results * 5  # 15 results
    
    filtered = confidence_filter.filter_results(many_results, threshold=0.70, max_results=5)
    
    assert len(filtered.results) == 5


# ============================================================================
# Confidence Status Tests
# ============================================================================

def test_confidence_status_high(confidence_filter):
    """Test: High confidence status determination."""
    status = confidence_filter._get_confidence_status(0.90)
    assert status == "high_confidence"


def test_confidence_status_medium(confidence_filter):
    """Test: Medium confidence status determination."""
    status = confidence_filter._get_confidence_status(0.75)
    assert status == "medium_confidence"


def test_confidence_status_low(confidence_filter):
    """Test: Low confidence status determination."""
    status = confidence_filter._get_confidence_status(0.55)
    assert status == "low_confidence"


def test_confidence_status_none(confidence_filter):
    """Test: No relevant context status determination."""
    status = confidence_filter._get_confidence_status(0.30)
    assert status == "no_relevant_context"


# ============================================================================
# Graceful Degradation Tests
# ============================================================================

def test_should_use_fresh_data_only(confidence_filter):
    """Test: Fresh data fallback logic."""
    assert confidence_filter.should_use_fresh_data_only("no_relevant_context") is True
    assert confidence_filter.should_use_fresh_data_only("low_confidence") is False
    assert confidence_filter.should_use_fresh_data_only("medium_confidence") is False
    assert confidence_filter.should_use_fresh_data_only("high_confidence") is False


def test_confidence_disclaimer_high(confidence_filter):
    """Test: No disclaimer for high confidence."""
    disclaimer = confidence_filter.get_confidence_disclaimer("high_confidence", 0.90)
    assert disclaimer is None


def test_confidence_disclaimer_medium(confidence_filter):
    """Test: Medium confidence disclaimer."""
    disclaimer = confidence_filter.get_confidence_disclaimer("medium_confidence", 0.75)
    assert "moderately relevant" in disclaimer.lower()
    assert "75%" in disclaimer


def test_confidence_disclaimer_low(confidence_filter):
    """Test: Low confidence disclaimer."""
    disclaimer = confidence_filter.get_confidence_disclaimer("low_confidence", 0.55)
    assert "loosely related" in disclaimer.lower()
    assert "exploratory" in disclaimer.lower()


def test_confidence_disclaimer_none(confidence_filter):
    """Test: No relevant context disclaimer."""
    disclaimer = confidence_filter.get_confidence_disclaimer("no_relevant_context", 0.0)
    assert "no" in disclaimer.lower()
    assert "historical" in disclaimer.lower()


# ============================================================================
# Threshold Relaxation Tests
# ============================================================================

def test_threshold_relaxation_applied():
    """Test: Threshold relaxation when insufficient results."""
    filter = ConfidenceFilter(min_results=3)
    
    results = [
        VectorSearchResult(content="High", similarity_score=0.75, metadata={}),
        VectorSearchResult(content="Medium", similarity_score=0.65, metadata={}),
        VectorSearchResult(content="Medium2", similarity_score=0.64, metadata={}),
        VectorSearchResult(content="Low", similarity_score=0.50, metadata={}),
    ]
    
    # With threshold 0.70, only 1 result qualifies
    # Should relax to 0.70 * 0.9 = 0.63 to get min_results
    filtered = filter.filter_results(results, threshold=0.70)
    
    assert len(filtered.results) >= 3


def test_no_relaxation_when_sufficient():
    """Test: No relaxation when sufficient high confidence results."""
    filter = ConfidenceFilter(min_results=3)
    
    results = [
        VectorSearchResult(content="High1", similarity_score=0.90, metadata={}),
        VectorSearchResult(content="High2", similarity_score=0.88, metadata={}),
        VectorSearchResult(content="High3", similarity_score=0.85, metadata={}),
        VectorSearchResult(content="Low", similarity_score=0.40, metadata={}),
    ]
    
    filtered = filter.filter_results(results, threshold=0.70)
    
    # Should not include the 0.40 result
    assert len(filtered.results) == 3
    assert all(r.similarity_score >= 0.70 for r in filtered.results)


# ============================================================================
# Filter Stats Tests
# ============================================================================

def test_get_stats(confidence_filter):
    """Test: Filter statistics returned correctly."""
    stats = confidence_filter.get_stats()
    
    assert "high_threshold" in stats
    assert "medium_threshold" in stats
    assert "low_threshold" in stats
    assert "min_results" in stats
    assert stats["high_threshold"] == 0.85
    assert stats["medium_threshold"] == 0.70
    assert stats["min_results"] == 3


# ============================================================================
# Edge Cases
# ============================================================================

def test_single_result_below_threshold(confidence_filter):
    """Test: Single low confidence result handling."""
    results = [
        VectorSearchResult(content="Low", similarity_score=0.60, metadata={})
    ]
    
    filtered = confidence_filter.filter_results(results, threshold=0.70)
    
    # Should still return the result due to min_results enforcement
    assert len(filtered.results) == 1
    assert filtered.status == "low_confidence"


def test_threshold_edge_cases(confidence_filter):
    """Test: Results exactly at threshold boundaries."""
    results = [
        VectorSearchResult(content="Exact high", similarity_score=0.85, metadata={}),
        VectorSearchResult(content="Exact medium", similarity_score=0.70, metadata={}),
        VectorSearchResult(content="Exact low", similarity_score=0.50, metadata={}),
    ]
    
    filtered = confidence_filter.filter_results(results, threshold=0.70)
    
    # Should include >= threshold
    assert len(filtered.results) >= 2
    assert all(r.similarity_score >= 0.50 for r in filtered.results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

