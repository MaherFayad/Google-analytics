"""
Integration tests for Agent Handoff Orchestration Logic.

Tests Task P0-18: Agent Handoff Orchestration Logic [HIGH]
"""

import pytest
import asyncio
import time
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock
from uuid import uuid4

from agents.orchestrator_with_handoff import EnhancedOrchestratorAgent
from agents.schemas.results import (
    DataFetchResult,
    EmbeddingResult,
    RetrievalResult,
    ReportResult,
)


@pytest.fixture
def tenant_id():
    """Generate tenant ID."""
    return str(uuid4())


@pytest.fixture
def enhanced_orchestrator():
    """Create enhanced orchestrator with mocked dependencies."""
    with patch('agents.orchestrator_with_handoff.DataFetcherAgent'):
        with patch('agents.orchestrator_with_handoff.EmbeddingAgent'):
            with patch('agents.orchestrator_with_handoff.RagAgent'):
                with patch('agents.orchestrator_with_handoff.ReportingAgent'):
                    orchestrator = EnhancedOrchestratorAgent(
                        openai_api_key="test_key"
                    )
                    return orchestrator


class TestParallelExecution:
    """Test parallel execution of DataFetcher + RAG."""
    
    @pytest.mark.asyncio
    async def test_parallel_data_fetcher_and_rag(self, enhanced_orchestrator, tenant_id):
        """Test DataFetcher and RAG execute in parallel."""
        # Mock agents with delays
        data_fetcher_delay = 2.0  # 2 seconds
        embedding_delay = 0.5  # 0.5 seconds
        
        async def mock_data_fetch(*args, **kwargs):
            await asyncio.sleep(data_fetcher_delay)
            return DataFetchResult(
                status="success",
                data={"sessions": 1000},
                cached=False,
                tenant_id=tenant_id,
            )
        
        async def mock_embedding(*args, **kwargs):
            await asyncio.sleep(embedding_delay)
            return EmbeddingResult(
                embeddings=[[0.1] * 1536],
                quality_score=0.95,
            )
        
        enhanced_orchestrator.data_fetcher.execute = mock_data_fetch
        enhanced_orchestrator.embedding_agent.execute = mock_embedding
        
        # Mock other agents
        enhanced_orchestrator.rag_agent.execute = AsyncMock(return_value=RetrievalResult(
            documents=[],
            citations=[],
            confidence=0.8,
            tenant_id=tenant_id,
            query_embedding=[0.1] * 1536,
            match_count=0,
        ))
        
        enhanced_orchestrator.reporting_agent.execute = AsyncMock(return_value=ReportResult(
            answer="Test report",
            charts=[],
            metrics=[],
            citations=[],
            confidence=0.9,
            tenant_id=tenant_id,
            query="test query",
        ))
        
        # Execute pipeline and measure time
        start = time.time()
        
        events = []
        async for event in enhanced_orchestrator.execute_pipeline_streaming(
            query="test query",
            tenant_id=tenant_id,
            user_id="user-123",
            property_id="prop-123",
            access_token="token",
        ):
            events.append(event)
        
        elapsed = time.time() - start
        
        # Assert: Parallel execution should take ~2s (max of both)
        # NOT 2.5s (sequential: 2s + 0.5s)
        assert elapsed < 2.8, f"Expected <2.8s (parallel), got {elapsed:.2f}s"
        assert elapsed > 1.8, f"Expected >1.8s (realistic timing), got {elapsed:.2f}s"
        
        # Verify pipeline completed
        result_events = [e for e in events if e["type"] == "result"]
        assert len(result_events) == 1


class TestConditionalBranching:
    """Test conditional embedding generation."""
    
    @pytest.mark.asyncio
    async def test_fresh_data_generates_embeddings(self, enhanced_orchestrator, tenant_id):
        """Test fresh data triggers embedding generation."""
        # Mock fresh data result
        enhanced_orchestrator.data_fetcher.execute = AsyncMock(return_value=DataFetchResult(
            status="success",
            data={"sessions": 1000, "conversions": 50},
            cached=False,  # Fresh data
            tenant_id=tenant_id,
        ))
        
        embedding_call_count = 0
        
        async def mock_embedding(*args, **kwargs):
            nonlocal embedding_call_count
            embedding_call_count += 1
            return EmbeddingResult(
                embeddings=[[0.1] * 1536],
                quality_score=0.95,
            )
        
        enhanced_orchestrator.embedding_agent.execute = mock_embedding
        
        # Mock other agents
        enhanced_orchestrator.rag_agent.execute = AsyncMock(return_value=RetrievalResult(
            documents=[],
            citations=[],
            confidence=0.5,
            tenant_id=tenant_id,
            query_embedding=[0.1] * 1536,
            match_count=0,
        ))
        
        enhanced_orchestrator.reporting_agent.execute = AsyncMock(return_value=ReportResult(
            answer="Test report",
            charts=[],
            metrics=[],
            citations=[],
            confidence=0.9,
            tenant_id=tenant_id,
            query="test query",
        ))
        
        # Execute pipeline
        events = []
        async for event in enhanced_orchestrator.execute_pipeline_streaming(
            query="test query",
            tenant_id=tenant_id,
            user_id="user-123",
            property_id="prop-123",
            access_token="token",
        ):
            events.append(event)
        
        # Assert: Embedding should be called twice (query + data)
        assert embedding_call_count == 2, f"Expected 2 embedding calls, got {embedding_call_count}"
    
    @pytest.mark.asyncio
    async def test_cached_data_skips_embeddings(self, enhanced_orchestrator, tenant_id):
        """Test cached data skips data embedding generation."""
        # Mock cached data result
        enhanced_orchestrator.data_fetcher.execute = AsyncMock(return_value=DataFetchResult(
            status="success",
            data={"sessions": 1000},
            cached=True,  # Cached data
            cache_age_seconds=300,
            tenant_id=tenant_id,
        ))
        
        embedding_call_count = 0
        
        async def mock_embedding(*args, **kwargs):
            nonlocal embedding_call_count
            embedding_call_count += 1
            return EmbeddingResult(
                embeddings=[[0.1] * 1536],
                quality_score=0.95,
            )
        
        enhanced_orchestrator.embedding_agent.execute = mock_embedding
        
        # Mock other agents
        enhanced_orchestrator.rag_agent.execute = AsyncMock(return_value=RetrievalResult(
            documents=[],
            citations=[],
            confidence=0.8,
            tenant_id=tenant_id,
            query_embedding=[0.1] * 1536,
            match_count=0,
        ))
        
        enhanced_orchestrator.reporting_agent.execute = AsyncMock(return_value=ReportResult(
            answer="Test report",
            charts=[],
            metrics=[],
            citations=[],
            confidence=0.9,
            tenant_id=tenant_id,
            query="test query",
        ))
        
        # Execute pipeline
        events = []
        async for event in enhanced_orchestrator.execute_pipeline_streaming(
            query="test query",
            tenant_id=tenant_id,
            user_id="user-123",
            property_id="prop-123",
            access_token="token",
        ):
            events.append(event)
        
        # Assert: Embedding should be called only once (query only, not data)
        assert embedding_call_count == 1, f"Expected 1 embedding call (query only), got {embedding_call_count}"


class TestGracefulDegradation:
    """Test graceful degradation when agents fail."""
    
    @pytest.mark.asyncio
    async def test_ga4_failure_with_high_rag_confidence(self, enhanced_orchestrator, tenant_id):
        """Test GA4 API failure with high RAG confidence proceeds with cache."""
        # Mock GA4 failure
        enhanced_orchestrator.data_fetcher.execute = AsyncMock(return_value=DataFetchResult(
            status="failed",
            data={},
            cached=False,
            tenant_id=tenant_id,
        ))
        
        # Mock high-confidence RAG result
        enhanced_orchestrator.embedding_agent.execute = AsyncMock(return_value=EmbeddingResult(
            embeddings=[[0.1] * 1536],
            quality_score=0.95,
        ))
        
        enhanced_orchestrator.rag_agent.execute = AsyncMock(return_value=RetrievalResult(
            documents=["Historical data point 1", "Historical data point 2"],
            citations=[],
            confidence=0.85,  # High confidence (>0.70 threshold)
            tenant_id=tenant_id,
            query_embedding=[0.1] * 1536,
            match_count=2,
        ))
        
        enhanced_orchestrator.reporting_agent.execute = AsyncMock(return_value=ReportResult(
            answer="Report based on historical data",
            charts=[],
            metrics=[],
            citations=[],
            confidence=0.8,
            tenant_id=tenant_id,
            query="test query",
        ))
        
        # Execute pipeline
        events = []
        async for event in enhanced_orchestrator.execute_pipeline_streaming(
            query="test query",
            tenant_id=tenant_id,
            user_id="user-123",
            property_id="prop-123",
            access_token="token",
        ):
            events.append(event)
        
        # Assert: Pipeline should complete with warning
        warning_events = [e for e in events if e["type"] == "warning"]
        assert len(warning_events) > 0, "Expected warning about using historical data"
        
        result_events = [e for e in events if e["type"] == "result"]
        assert len(result_events) == 1, "Expected pipeline to complete successfully"
    
    @pytest.mark.asyncio
    async def test_ga4_failure_with_low_rag_confidence(self, enhanced_orchestrator, tenant_id):
        """Test GA4 API failure with low RAG confidence returns error."""
        # Mock GA4 failure
        enhanced_orchestrator.data_fetcher.execute = AsyncMock(return_value=DataFetchResult(
            status="failed",
            data={},
            cached=False,
            tenant_id=tenant_id,
        ))
        
        # Mock low-confidence RAG result
        enhanced_orchestrator.embedding_agent.execute = AsyncMock(return_value=EmbeddingResult(
            embeddings=[[0.1] * 1536],
            quality_score=0.95,
        ))
        
        enhanced_orchestrator.rag_agent.execute = AsyncMock(return_value=RetrievalResult(
            documents=[],
            citations=[],
            confidence=0.3,  # Low confidence (<0.70 threshold)
            tenant_id=tenant_id,
            query_embedding=[0.1] * 1536,
            match_count=0,
        ))
        
        # Execute pipeline
        events = []
        async for event in enhanced_orchestrator.execute_pipeline_streaming(
            query="test query",
            tenant_id=tenant_id,
            user_id="user-123",
            property_id="prop-123",
            access_token="token",
        ):
            events.append(event)
        
        # Assert: Pipeline should return error
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) > 0, "Expected error when both GA4 and RAG fail"
        
        result_events = [e for e in events if e["type"] == "result"]
        assert len(result_events) == 0, "Expected no result when data unavailable"


class TestStreamingProgress:
    """Test streaming progress updates."""
    
    @pytest.mark.asyncio
    async def test_progress_updates_streamed(self, enhanced_orchestrator, tenant_id):
        """Test progress updates are streamed throughout pipeline."""
        # Mock successful pipeline
        enhanced_orchestrator.data_fetcher.execute = AsyncMock(return_value=DataFetchResult(
            status="success",
            data={"sessions": 1000},
            cached=False,
            tenant_id=tenant_id,
        ))
        
        enhanced_orchestrator.embedding_agent.execute = AsyncMock(return_value=EmbeddingResult(
            embeddings=[[0.1] * 1536],
            quality_score=0.95,
        ))
        
        enhanced_orchestrator.rag_agent.execute = AsyncMock(return_value=RetrievalResult(
            documents=[],
            citations=[],
            confidence=0.8,
            tenant_id=tenant_id,
            query_embedding=[0.1] * 1536,
            match_count=0,
        ))
        
        enhanced_orchestrator.reporting_agent.execute = AsyncMock(return_value=ReportResult(
            answer="Test report",
            charts=[],
            metrics=[],
            citations=[],
            confidence=0.9,
            tenant_id=tenant_id,
            query="test query",
        ))
        
        # Execute pipeline and collect events
        events = []
        async for event in enhanced_orchestrator.execute_pipeline_streaming(
            query="test query",
            tenant_id=tenant_id,
            user_id="user-123",
            property_id="prop-123",
            access_token="token",
        ):
            events.append(event)
        
        # Assert: Should have multiple status updates
        status_events = [e for e in events if e["type"] == "status"]
        assert len(status_events) >= 4, f"Expected >=4 status updates, got {len(status_events)}"
        
        # Assert: Progress values should increase
        progress_values = [e.get("progress", 0) for e in events if "progress" in e]
        assert progress_values == sorted(progress_values), "Progress should increase monotonically"
        
        # Assert: Final progress should be 1.0
        result_event = [e for e in events if e["type"] == "result"][0]
        assert result_event["progress"] == 1.0, "Final progress should be 1.0"


class TestStateMachineIntegration:
    """Test state machine integration."""
    
    @pytest.mark.asyncio
    async def test_state_machine_audit_trail(self, enhanced_orchestrator, tenant_id):
        """Test state machine creates audit trail."""
        # Mock successful pipeline
        enhanced_orchestrator.data_fetcher.execute = AsyncMock(return_value=DataFetchResult(
            status="success",
            data={"sessions": 1000},
            cached=False,
            tenant_id=tenant_id,
        ))
        
        enhanced_orchestrator.embedding_agent.execute = AsyncMock(return_value=EmbeddingResult(
            embeddings=[[0.1] * 1536],
            quality_score=0.95,
        ))
        
        enhanced_orchestrator.rag_agent.execute = AsyncMock(return_value=RetrievalResult(
            documents=[],
            citations=[],
            confidence=0.8,
            tenant_id=tenant_id,
            query_embedding=[0.1] * 1536,
            match_count=0,
        ))
        
        enhanced_orchestrator.reporting_agent.execute = AsyncMock(return_value=ReportResult(
            answer="Test report",
            charts=[],
            metrics=[],
            citations=[],
            confidence=0.9,
            tenant_id=tenant_id,
            query="test query",
        ))
        
        # Execute pipeline
        events = []
        async for event in enhanced_orchestrator.execute_pipeline_streaming(
            query="test query",
            tenant_id=tenant_id,
            user_id="user-123",
            property_id="prop-123",
            access_token="token",
        ):
            events.append(event)
        
        # Assert: Metadata should include state_transitions count
        result_event = [e for e in events if e["type"] == "result"][0]
        assert "metadata" in result_event["payload"]
        assert "state_transitions" in result_event["payload"]["metadata"]
        assert result_event["payload"]["metadata"]["state_transitions"] > 0


class TestPerformanceMetrics:
    """Test performance tracking."""
    
    @pytest.mark.asyncio
    async def test_duration_tracking(self, enhanced_orchestrator, tenant_id):
        """Test pipeline duration is tracked."""
        # Mock successful pipeline
        enhanced_orchestrator.data_fetcher.execute = AsyncMock(return_value=DataFetchResult(
            status="success",
            data={"sessions": 1000},
            cached=False,
            tenant_id=tenant_id,
        ))
        
        enhanced_orchestrator.embedding_agent.execute = AsyncMock(return_value=EmbeddingResult(
            embeddings=[[0.1] * 1536],
            quality_score=0.95,
        ))
        
        enhanced_orchestrator.rag_agent.execute = AsyncMock(return_value=RetrievalResult(
            documents=[],
            citations=[],
            confidence=0.8,
            tenant_id=tenant_id,
            query_embedding=[0.1] * 1536,
            match_count=0,
        ))
        
        enhanced_orchestrator.reporting_agent.execute = AsyncMock(return_value=ReportResult(
            answer="Test report",
            charts=[],
            metrics=[],
            citations=[],
            confidence=0.9,
            tenant_id=tenant_id,
            query="test query",
        ))
        
        # Execute pipeline
        events = []
        async for event in enhanced_orchestrator.execute_pipeline_streaming(
            query="test query",
            tenant_id=tenant_id,
            user_id="user-123",
            property_id="prop-123",
            access_token="token",
        ):
            events.append(event)
        
        # Assert: Result includes duration_ms
        result_event = [e for e in events if e["type"] == "result"][0]
        assert "metadata" in result_event["payload"]
        assert "duration_ms" in result_event["payload"]["metadata"]
        assert result_event["payload"]["metadata"]["duration_ms"] > 0

