"""
Integration Tests for RAG Confidence Filtering

Implements Task P0-19: RAG Retrieval Confidence Filtering

Tests end-to-end RAG retrieval with confidence filtering,
including database integration and monitoring metrics.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.rag_agent import RagAgent
from src.agents.schemas.results import RetrievalResult


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
async def mock_db_session():
    """Mock database session."""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.fixture
def rag_agent(mock_db_session):
    """RAG agent with mock database."""
    return RagAgent(db_session=mock_db_session)


@pytest.fixture
def mock_high_confidence_db_results():
    """Mock high confidence database results."""
    return [
        MagicMock(
            embedding_content="Mobile conversions increased 21.7%",
            similarity_score=0.92,
            metric_id=1,
            property_id="123456789",
            metric_date=MagicMock(isoformat=lambda: "2025-01-01"),
            metric_values={"conversions": 56},
        ),
        MagicMock(
            embedding_content="Desktop sessions decreased 5.2%",
            similarity_score=0.88,
            metric_id=2,
            property_id="123456789",
            metric_date=MagicMock(isoformat=lambda: "2025-01-02"),
            metric_values={"sessions": 1456},
        ),
    ]


@pytest.fixture
def mock_mixed_confidence_db_results():
    """Mock mixed confidence database results."""
    return [
        MagicMock(
            embedding_content="Mobile conversions increased 21.7%",
            similarity_score=0.92,
            metric_id=1,
            property_id="123456789",
            metric_date=MagicMock(isoformat=lambda: "2025-01-01"),
            metric_values={"conversions": 56},
        ),
        MagicMock(
            embedding_content="Irrelevant homepage data",
            similarity_score=0.45,
            metric_id=2,
            property_id="123456789",
            metric_date=MagicMock(isoformat=lambda: "2025-01-02"),
            metric_values={"pageviews": 1000},
        ),
    ]


# ============================================================================
# RAG Retrieval Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_rag_retrieval_high_confidence(rag_agent, mock_db_session, mock_high_confidence_db_results):
    """Test: RAG retrieval returns high confidence results."""
    # Mock database query
    mock_result = AsyncMock()
    mock_result.fetchall.return_value = mock_high_confidence_db_results
    mock_db_session.execute.return_value = mock_result
    
    # Execute retrieval
    result = await rag_agent.run_async(
        ctx=AsyncMock(),
        query_embedding=[0.1] * 1536,
        tenant_id="tenant-123",
        match_count=5,
        min_confidence=0.70
    )
    
    # Assertions
    assert isinstance(result, RetrievalResult)
    assert len(result.documents) == 2
    assert result.confidence >= 0.85
    assert result.status == "high_confidence"
    assert result.filtered_count >= 0
    assert len(result.citations) == 2


@pytest.mark.asyncio
async def test_rag_retrieval_filters_low_confidence(rag_agent, mock_db_session, mock_mixed_confidence_db_results):
    """Test: RAG filters out low confidence results."""
    # Mock database query
    mock_result = AsyncMock()
    mock_result.fetchall.return_value = mock_mixed_confidence_db_results
    mock_db_session.execute.return_value = mock_result
    
    # Execute retrieval
    result = await rag_agent.run_async(
        ctx=AsyncMock(),
        query_embedding=[0.1] * 1536,
        tenant_id="tenant-123",
        match_count=5,
        min_confidence=0.70
    )
    
    # Assertions
    assert isinstance(result, RetrievalResult)
    # Should only include high confidence result (0.92), not low confidence (0.45)
    assert all(citation.similarity_score >= 0.70 for citation in result.citations)


@pytest.mark.asyncio
async def test_rag_retrieval_no_relevant_context(rag_agent, mock_db_session):
    """Test: RAG handles no relevant context scenario."""
    # Mock empty database results
    mock_result = AsyncMock()
    mock_result.fetchall.return_value = []
    mock_db_session.execute.return_value = mock_result
    
    # Execute retrieval
    result = await rag_agent.run_async(
        ctx=AsyncMock(),
        query_embedding=[0.1] * 1536,
        tenant_id="tenant-123",
        match_count=5,
        min_confidence=0.70
    )
    
    # Assertions
    assert isinstance(result, RetrievalResult)
    assert len(result.documents) == 0
    assert result.confidence == 0.0
    assert result.status == "no_relevant_context"


@pytest.mark.asyncio
async def test_rag_retrieval_custom_threshold(rag_agent, mock_db_session, mock_high_confidence_db_results):
    """Test: RAG respects custom confidence threshold."""
    mock_result = AsyncMock()
    mock_result.fetchall.return_value = mock_high_confidence_db_results
    mock_db_session.execute.return_value = mock_result
    
    # Execute with high threshold (0.90)
    result = await rag_agent.run_async(
        ctx=AsyncMock(),
        query_embedding=[0.1] * 1536,
        tenant_id="tenant-123",
        match_count=5,
        min_confidence=0.90  # Higher threshold
    )
    
    # Should respect threshold in query
    assert mock_db_session.execute.called
    call_args = mock_db_session.execute.call_args
    assert call_args[0][1]["min_confidence"] == 0.90


@pytest.mark.asyncio
async def test_rag_retrieval_without_db_session():
    """Test: RAG agent works without database (mock mode)."""
    rag_agent = RagAgent(db_session=None)
    
    result = await rag_agent.run_async(
        ctx=AsyncMock(),
        query_embedding=[0.1] * 1536,
        tenant_id="tenant-123",
        match_count=5
    )
    
    # Should return mock results
    assert isinstance(result, RetrievalResult)
    assert len(result.documents) > 0
    assert result.confidence > 0.0
    assert result.status in ["high_confidence", "medium_confidence", "low_confidence"]


# ============================================================================
# Confidence Status Determination Tests
# ============================================================================

def test_confidence_status_determination_high(rag_agent):
    """Test: High confidence status determination."""
    status = rag_agent._get_confidence_status(0.90, 0.70)
    assert status == "high_confidence"


def test_confidence_status_determination_medium(rag_agent):
    """Test: Medium confidence status determination."""
    status = rag_agent._get_confidence_status(0.75, 0.70)
    assert status == "medium_confidence"


def test_confidence_status_determination_low(rag_agent):
    """Test: Low confidence status determination."""
    status = rag_agent._get_confidence_status(0.55, 0.70)
    assert status == "low_confidence"


def test_confidence_status_determination_none(rag_agent):
    """Test: No relevant context status determination."""
    status = rag_agent._get_confidence_status(0.30, 0.70)
    assert status == "no_relevant_context"


# ============================================================================
# Monitoring Integration Tests
# ============================================================================

@pytest.mark.asyncio
@patch('src.agents.rag_agent.record_rag_retrieval')
async def test_rag_records_monitoring_metrics(mock_record, rag_agent, mock_db_session, mock_high_confidence_db_results):
    """Test: RAG retrieval records monitoring metrics."""
    mock_result = AsyncMock()
    mock_result.fetchall.return_value = mock_high_confidence_db_results
    mock_db_session.execute.return_value = mock_result
    
    # Execute retrieval
    with patch('src.agents.rag_agent.MONITORING_ENABLED', True):
        result = await rag_agent.run_async(
            ctx=AsyncMock(),
            query_embedding=[0.1] * 1536,
            tenant_id="tenant-123",
            match_count=5
        )
    
    # Verify metrics recorded
    assert mock_record.called


# ============================================================================
# Error Handling Tests
# ============================================================================

@pytest.mark.asyncio
async def test_rag_handles_database_error(rag_agent, mock_db_session):
    """Test: RAG handles database errors gracefully."""
    # Mock database error
    mock_db_session.execute.side_effect = Exception("Database connection failed")
    
    # Execute retrieval
    result = await rag_agent.run_async(
        ctx=AsyncMock(),
        query_embedding=[0.1] * 1536,
        tenant_id="tenant-123",
        match_count=5
    )
    
    # Should return empty result, not raise exception
    assert isinstance(result, RetrievalResult)
    assert len(result.documents) == 0
    assert result.confidence == 0.0
    assert result.status == "no_relevant_context"


# ============================================================================
# Result Structure Tests
# ============================================================================

@pytest.mark.asyncio
async def test_rag_result_structure(rag_agent, mock_db_session, mock_high_confidence_db_results):
    """Test: RAG result has correct structure."""
    mock_result = AsyncMock()
    mock_result.fetchall.return_value = mock_high_confidence_db_results
    mock_db_session.execute.return_value = mock_result
    
    result = await rag_agent.run_async(
        ctx=AsyncMock(),
        query_embedding=[0.1] * 1536,
        tenant_id="tenant-123",
        match_count=5
    )
    
    # Verify structure
    assert hasattr(result, 'documents')
    assert hasattr(result, 'citations')
    assert hasattr(result, 'confidence')
    assert hasattr(result, 'status')
    assert hasattr(result, 'filtered_count')
    assert hasattr(result, 'total_found')
    assert hasattr(result, 'tenant_id')
    assert hasattr(result, 'match_count')
    
    # Verify documents and citations match
    assert len(result.documents) == len(result.citations)


# ============================================================================
# Tenant Isolation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_rag_enforces_tenant_isolation(rag_agent, mock_db_session):
    """Test: RAG enforces tenant isolation in query."""
    mock_result = AsyncMock()
    mock_result.fetchall.return_value = []
    mock_db_session.execute.return_value = mock_result
    
    tenant_id = "tenant-abc-123"
    
    await rag_agent.run_async(
        ctx=AsyncMock(),
        query_embedding=[0.1] * 1536,
        tenant_id=tenant_id,
        match_count=5
    )
    
    # Verify tenant_id passed to query
    call_args = mock_db_session.execute.call_args
    assert call_args[0][1]["tenant_id"] == tenant_id


# ============================================================================
# Performance Tests
# ============================================================================

@pytest.mark.asyncio
async def test_rag_handles_large_result_set(rag_agent, mock_db_session):
    """Test: RAG handles large result sets efficiently."""
    # Create large mock result set
    large_results = [
        MagicMock(
            embedding_content=f"Document {i}",
            similarity_score=0.90 - (i * 0.01),
            metric_id=i,
            property_id="123456789",
            metric_date=MagicMock(isoformat=lambda: "2025-01-01"),
            metric_values={"metric": i},
        )
        for i in range(50)  # 50 results
    ]
    
    mock_result = AsyncMock()
    mock_result.fetchall.return_value = large_results
    mock_db_session.execute.return_value = mock_result
    
    result = await rag_agent.run_async(
        ctx=AsyncMock(),
        query_embedding=[0.1] * 1536,
        tenant_id="tenant-123",
        match_count=10  # Limit to 10
    )
    
    # Should handle large set and return only requested count
    assert isinstance(result, RetrievalResult)
    assert len(result.documents) <= 10


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

