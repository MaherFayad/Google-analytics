"""
End-to-end agent pipeline tests.

Implements Task P0-1: E2E test for full agent pipeline

Tests the complete flow:
User Query → DataFetcher → Embedding → RAG → Reporting → Structured Report
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.orchestrator_agent import OrchestratorAgent
from src.agents.schemas.results import ReportResult


class TestAgentPipeline:
    """Test complete agent pipeline (Task P0-1 acceptance criteria)."""
    
    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mocked dependencies."""
        return OrchestratorAgent(
            openai_api_key="test-key",
            redis_client=None,
            db_session=None,
        )
    
    @pytest.mark.asyncio
    async def test_full_pipeline_execution(self, orchestrator):
        """
        CRITICAL TEST: Full pipeline from query to report.
        
        Acceptance criteria: User query → full pipeline → structured report
        """
        # Mock GA4 API response
        mock_ga4_data = {
            "dimensionHeaders": [{"name": "date"}],
            "metricHeaders": [{"name": "sessions"}],
            "rows": [
                {
                    "dimensionValues": [{"value": "2025-01-01"}],
                    "metricValues": [{"value": "1234"}]
                }
            ],
            "rowCount": 1
        }
        
        # Mock DataFetcher
        with patch.object(
            orchestrator.data_fetcher,
            'execute',
            new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = MagicMock(
                status="success",
                data=mock_ga4_data,
                cached=False,
            )
            
            # Mock EmbeddingAgent
            with patch.object(
                orchestrator.embedding_agent,
                'execute',
                new_callable=AsyncMock
            ) as mock_embed:
                mock_embed.return_value = MagicMock(
                    embeddings=[[0.1] * 1536],
                    quality_score=0.95,
                    validation_errors=[],
                )
                
                # Execute pipeline
                result = await orchestrator.execute(
                    query="Show me last week's sessions",
                    tenant_id="test-tenant",
                    user_id="test-user",
                    property_id="123456789",
                    access_token="test-token",
                )
                
                # Verify result structure
                assert isinstance(result, ReportResult)
                assert result.answer is not None
                assert result.tenant_id == "test-tenant"
                assert result.query == "Show me last week's sessions"
                assert 0.0 <= result.confidence <= 1.0
    
    @pytest.mark.asyncio
    async def test_pipeline_with_cache_hit(self, orchestrator):
        """
        Test pipeline performance with cached data.
        
        Acceptance criteria: Cached data should skip GA4 API call
        """
        with patch.object(
            orchestrator.data_fetcher,
            'execute',
            new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = MagicMock(
                status="cached",
                data={"rows": []},
                cached=True,  # Cache hit
            )
            
            result = await orchestrator.execute(
                query="Test query",
                tenant_id="test-tenant",
                user_id="test-user",
                property_id="123456789",
                access_token="test-token",
            )
            
            # Verify cache was used
            mock_fetch.assert_called_once()
            assert isinstance(result, ReportResult)
    
    @pytest.mark.asyncio
    async def test_pipeline_error_recovery(self, orchestrator):
        """
        Test error recovery when DataFetcher fails.
        
        Acceptance criteria: Pipeline should degrade gracefully
        """
        with patch.object(
            orchestrator.data_fetcher,
            'execute',
            new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = MagicMock(
                status="failed",
                data={"error": "API timeout"},
                cached=False,
            )
            
            # Pipeline should still complete with fallback
            result = await orchestrator.execute(
                query="Test query",
                tenant_id="test-tenant",
                user_id="test-user",
                property_id="123456789",
                access_token="test-token",
            )
            
            assert isinstance(result, ReportResult)
            assert result.confidence < 1.0  # Lower confidence due to error
    
    @pytest.mark.asyncio
    async def test_pipeline_streaming(self, orchestrator):
        """
        Test streaming pipeline with progress updates.
        
        Task P0-12: Async execution with streaming
        """
        events = []
        
        async for event in orchestrator.execute_pipeline_streaming(
            query="Test query",
            tenant_id="test-tenant",
            user_id="test-user",
            property_id="123456789",
            access_token="test-token",
        ):
            events.append(event)
        
        # Verify we got status updates
        status_events = [e for e in events if e.get("type") == "status"]
        assert len(status_events) > 0
        
        # Verify we got final result
        result_events = [e for e in events if e.get("type") == "result"]
        assert len(result_events) == 1
        
        final_result = result_events[0]["payload"]
        assert "answer" in final_result
        assert "tenant_id" in final_result




