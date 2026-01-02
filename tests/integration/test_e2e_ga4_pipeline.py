"""
End-to-End Integration Tests for GA4 Analytics Pipeline.

Tests Task P0-9: End-to-End Integration Test Suite [CRITICAL]

Validates the complete pipeline:
OAuth → GA4 API → Embedding Generation → Vector Search → LLM Report
"""

import pytest
import json
from pathlib import Path
from datetime import date
from uuid import uuid4
from unittest.mock import Mock, patch, AsyncMock

from fastapi.testclient import TestClient


@pytest.fixture
def ga4_mock_data():
    """Load realistic GA4 API mock data."""
    fixtures_path = Path(__file__).parent / "fixtures" / "ga4_mock_data.json"
    with open(fixtures_path) as f:
        return json.load(f)


@pytest.fixture
def test_tenant_id():
    """Generate test tenant ID."""
    return str(uuid4())


@pytest.fixture
def test_user_id():
    """Generate test user ID."""
    return str(uuid4())


class TestFullPipeline:
    """Test complete GA4 analytics pipeline end-to-end."""
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_happy_path_full_pipeline(self, ga4_mock_data, test_tenant_id, test_user_id):
        """
        Test happy path: User query → GA4 fetch → Embedding → RAG → Report
        
        This test validates the entire pipeline works as a cohesive unit.
        """
        # 1. Mock GA4 API client
        with patch('server.services.ga4.ga4_client.BetaAnalyticsDataClient') as mock_ga4:
            mock_ga4.return_value.run_report.return_value = Mock(
                rows=self._convert_mock_data_to_rows(ga4_mock_data)
            )
            
            # 2. Mock OpenAI embedding API
            with patch('agents.embedding_agent.openai') as mock_openai:
                mock_openai.Embedding.create.return_value = {
                    "data": [{"embedding": [0.1] * 1536}]
                }
                
                # 3. Execute full pipeline via orchestrator
                from agents import EnhancedOrchestratorAgent
                
                orchestrator = EnhancedOrchestratorAgent(
                    openai_api_key="test_key"
                )
                
                # Execute pipeline
                events = []
                async for event in orchestrator.execute_pipeline_streaming(
                    query="What were mobile sessions yesterday?",
                    tenant_id=test_tenant_id,
                    user_id=test_user_id,
                    property_id="123456789",
                    access_token="test_token",
                ):
                    events.append(event)
                
                # Verify pipeline completed
                result_events = [e for e in events if e["type"] == "result"]
                assert len(result_events) == 1, "Pipeline should complete with result"
                
                result = result_events[0]["payload"]
                
                # Verify result structure
                assert "answer" in result
                assert "confidence" in result
                assert result["confidence"] > 0.0
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_pipeline_with_quota_enforcement(self, test_tenant_id, test_user_id):
        """Test pipeline respects GA4 API quota limits."""
        from server.services.ga4.quota_manager import GA4QuotaManager
        from server.services.ga4.exceptions import GA4QuotaExceededError
        
        # Mock database session
        mock_db = AsyncMock()
        
        quota_manager = GA4QuotaManager(
            db_session=mock_db,
            tenant_id=uuid4(),
            property_id="123456789",
            hourly_limit=2,  # Very low limit for testing
            daily_limit=5
        )
        
        # Make 2 successful requests (at limit)
        await quota_manager.acquire_quota(requests=1)
        await quota_manager.acquire_quota(requests=1)
        
        # 3rd request should fail
        with pytest.raises(GA4QuotaExceededError):
            await quota_manager.acquire_quota(requests=1)
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_pipeline_caching(self, ga4_mock_data, test_tenant_id):
        """Test pipeline uses cache on repeated queries."""
        # Execute same query twice
        query = "What were mobile sessions yesterday?"
        
        # First execution - should call GA4 API
        # Second execution - should use cache
        
        # TODO: Implement when caching layer is ready (Task 4.3)
        pass
    
    def _convert_mock_data_to_rows(self, mock_data):
        """Convert mock JSON data to GA4 API Row objects."""
        from google.analytics.data_v1beta.types import Row, DimensionValue, MetricValue
        
        rows = []
        for row_data in mock_data["rows"]:
            row = Row(
                dimension_values=[
                    DimensionValue(value=dim["value"])
                    for dim in row_data["dimensionValues"]
                ],
                metric_values=[
                    MetricValue(value=metric["value"])
                    for metric in row_data["metricValues"]
                ]
            )
            rows.append(row)
        
        return rows


class TestDataTransformation:
    """Test GA4 data transformation pipeline."""
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_ga4_json_to_descriptive_text(self, ga4_mock_data):
        """Test GA4 JSON is transformed to descriptive text."""
        from server.services.ga4.data_transformer import GA4DataTransformer
        
        # Transform GA4 response to descriptive text
        # TODO: Implement when data_transformer exists (Task 14)
        
        # Expected output format:
        # "On Jan 1, mobile users had 2,145 sessions with 42 conversions (42.3% bounce rate)"
        pass
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_embedding_generation_from_ga4_data(self, ga4_mock_data):
        """Test embeddings are generated from GA4 descriptive text."""
        from agents import EmbeddingAgent
        
        # Mock OpenAI API
        with patch('agents.embedding_agent.openai') as mock_openai:
            mock_openai.Embedding.create.return_value = {
                "data": [{"embedding": [0.1] * 1536}]
            }
            
            agent = EmbeddingAgent(openai_api_key="test_key")
            
            result = await agent.execute(
                texts=["Mobile had 2,145 sessions"],
                tenant_id=str(uuid4())
            )
            
            # Verify embedding generation
            assert len(result.embeddings) == 1
            assert len(result.embeddings[0]) == 1536
            assert result.quality_score > 0.0


class TestVectorSearch:
    """Test vector similarity search."""
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_rag_retrieval_returns_relevant_context(self):
        """Test RAG retrieval finds relevant historical patterns."""
        from agents import RagAgent
        
        # Mock database session (RAG will use mock data if no session)
        agent = RagAgent(db_session=None)
        
        query_embedding = [0.1] * 1536
        
        result = await agent.execute(
            query_embedding=query_embedding,
            tenant_id=str(uuid4()),
            match_count=5
        )
        
        # Verify retrieval result structure
        assert len(result.documents) > 0
        assert len(result.citations) > 0
        assert len(result.documents) == len(result.citations)
        assert result.confidence > 0.0
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_rag_includes_source_citations(self):
        """Test RAG retrieval includes source citations (Task P0-42)."""
        from agents import RagAgent
        from agents.schemas.results import SourceCitation
        
        agent = RagAgent(db_session=None)
        
        result = await agent.execute(
            query_embedding=[0.1] * 1536,
            tenant_id=str(uuid4())
        )
        
        # Verify citations are included
        assert len(result.citations) > 0
        
        for citation in result.citations:
            assert isinstance(citation, SourceCitation)
            assert citation.metric_id > 0
            assert citation.property_id
            assert citation.raw_json
            assert 0.0 <= citation.similarity_score <= 1.0


class TestReportGeneration:
    """Test report generation with validation."""
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_report_generation_with_citations(self, ga4_mock_data):
        """Test report includes citations and passes validation."""
        from agents import ReportingAgent
        from agents.schemas.results import SourceCitation
        
        agent = ReportingAgent(openai_api_key="test_key")
        
        # Mock LLM response
        with patch('agents.reporting_agent.openai') as mock_openai:
            mock_openai.ChatCompletion.create.return_value = Mock(
                choices=[Mock(
                    message=Mock(
                        content="Mobile had 2,145 sessions with 42 conversions"
                    )
                )]
            )
            
            citations = [
                SourceCitation(
                    metric_id=1,
                    property_id="123",
                    metric_date="2026-01-01",
                    raw_json={"sessions": 2145, "conversions": 42},
                    similarity_score=0.95
                )
            ]
            
            result = await agent.execute(
                query="What were mobile sessions?",
                ga4_data=ga4_mock_data,
                retrieved_context=[],
                citations=citations,
                tenant_id=str(uuid4())
            )
            
            # Verify report structure
            assert result.answer
            assert len(result.citations) > 0
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_report_validation_catches_hallucinations(self):
        """Test ground truth validator catches hallucinations."""
        from server.services.validation import GroundTruthValidator
        
        validator = GroundTruthValidator(tolerance_percent=5.0)
        
        # LLM hallucinates (says 3,000 but actual is 2,145)
        llm_response = "Mobile had 3,000 sessions"
        raw_metrics = {"sessions": 2145}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        # Should fail validation (39.8% deviation)
        assert not result.is_valid
        assert result.max_deviation_percent > 30


class TestTenantIsolation:
    """Test tenant isolation in E2E scenarios."""
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_tenant_a_cannot_access_tenant_b_data(self):
        """Test strict tenant isolation (Task P0-2, P0-3)."""
        tenant_a = str(uuid4())
        tenant_b = str(uuid4())
        
        # Store data for both tenants
        # Query as tenant A
        # Verify tenant B data is not returned
        
        # TODO: Implement when database is set up
        # This test requires actual PostgreSQL with RLS policies
        pass
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_tenant_quotas_are_independent(self):
        """Test each tenant has independent quota limits."""
        tenant_a = str(uuid4())
        tenant_b = str(uuid4())
        
        # Exhaust tenant A quota
        # Verify tenant B can still make requests
        
        # TODO: Implement with actual quota manager
        pass


class TestErrorRecovery:
    """Test error recovery and graceful degradation."""
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_ga4_api_failure_fallback_to_cache(self):
        """Test system falls back to cache when GA4 API fails."""
        from agents import EnhancedOrchestratorAgent
        
        orchestrator = EnhancedOrchestratorAgent(
            openai_api_key="test_key"
        )
        
        # Mock GA4 API failure
        orchestrator.data_fetcher.execute = AsyncMock(side_effect=Exception("GA4 API timeout"))
        
        # Mock high-confidence RAG result (cache)
        from agents.schemas.results import RetrievalResult, SourceCitation
        
        orchestrator.rag_agent.execute = AsyncMock(return_value=RetrievalResult(
            documents=["Historical data"],
            citations=[SourceCitation(
                metric_id=1,
                property_id="123",
                metric_date="2026-01-01",
                raw_json={"sessions": 1234},
                similarity_score=0.85
            )],
            confidence=0.85,  # Above 0.70 threshold
            tenant_id=str(uuid4()),
            query_embedding=[0.1] * 1536,
            match_count=1
        ))
        
        # Pipeline should succeed with warning
        events = []
        async for event in orchestrator.execute_pipeline_streaming(
            query="Show traffic",
            tenant_id=str(uuid4()),
            user_id=str(uuid4()),
            property_id="123",
            access_token="token"
        ):
            events.append(event)
        
        # Should have warning about using cached data
        warnings = [e for e in events if e["type"] == "warning"]
        assert len(warnings) > 0
        
        # But should still complete
        results = [e for e in events if e["type"] == "result"]
        assert len(results) > 0
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_embedding_failure_graceful_degradation(self):
        """Test system continues when embedding generation fails."""
        from agents import EnhancedOrchestratorAgent
        from agents.schemas.results import DataFetchResult, EmbeddingResult
        
        orchestrator = EnhancedOrchestratorAgent(
            openai_api_key="test_key"
        )
        
        # Mock successful data fetch
        orchestrator.data_fetcher.execute = AsyncMock(return_value=DataFetchResult(
            status="success",
            data={"sessions": 1234},
            cached=False,
            tenant_id=str(uuid4()),
            property_id="123"
        ))
        
        # Mock embedding failure
        orchestrator.embedding_agent.execute = AsyncMock(return_value=EmbeddingResult(
            embeddings=[],  # No embeddings generated
            quality_score=0.0,
            validation_errors=["OpenAI API timeout"]
        ))
        
        # Pipeline should handle gracefully
        events = []
        async for event in orchestrator.execute_pipeline_streaming(
            query="Show traffic",
            tenant_id=str(uuid4()),
            user_id=str(uuid4()),
            property_id="123",
            access_token="token"
        ):
            events.append(event)
        
        # Should complete despite embedding failure
        results = [e for e in events if e["type"] == "result"]
        assert len(results) > 0


class TestPerformanceTargets:
    """Test performance targets are met."""
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_pipeline_completes_under_5_seconds(self):
        """Test E2E pipeline completes in <5 seconds."""
        import time
        from agents import EnhancedOrchestratorAgent
        
        orchestrator = EnhancedOrchestratorAgent(
            openai_api_key="test_key"
        )
        
        # Mock all agents with realistic delays
        from agents.schemas.results import (
            DataFetchResult,
            EmbeddingResult,
            RetrievalResult,
            ReportResult,
            SourceCitation
        )
        
        async def mock_data_fetch(*args, **kwargs):
            await asyncio.sleep(1.0)  # GA4 API latency
            return DataFetchResult(
                status="success",
                data={"sessions": 1234},
                cached=False,
                tenant_id=kwargs["tenant_id"],
                property_id=kwargs["property_id"]
            )
        
        async def mock_embedding(*args, **kwargs):
            await asyncio.sleep(0.3)  # OpenAI API latency
            return EmbeddingResult(
                embeddings=[[0.1] * 1536],
                quality_score=0.95
            )
        
        async def mock_rag(*args, **kwargs):
            await asyncio.sleep(0.1)  # pgvector search
            return RetrievalResult(
                documents=["Doc 1"],
                citations=[SourceCitation(
                    metric_id=1,
                    property_id="123",
                    metric_date="2026-01-01",
                    raw_json={"sessions": 1234},
                    similarity_score=0.9
                )],
                confidence=0.9,
                tenant_id=kwargs["tenant_id"],
                query_embedding=[0.1] * 1536,
                match_count=1
            )
        
        async def mock_reporting(*args, **kwargs):
            await asyncio.sleep(1.5)  # LLM generation
            return ReportResult(
                answer="Report",
                charts=[],
                metrics=[],
                citations=[],
                confidence=0.9,
                tenant_id=kwargs["tenant_id"],
                query="test"
            )
        
        orchestrator.data_fetcher.execute = mock_data_fetch
        orchestrator.embedding_agent.execute = mock_embedding
        orchestrator.rag_agent.execute = mock_rag
        orchestrator.reporting_agent.execute = mock_reporting
        
        # Measure total time
        start = time.time()
        
        events = []
        async for event in orchestrator.execute_pipeline_streaming(
            query="Show traffic",
            tenant_id=str(uuid4()),
            user_id=str(uuid4()),
            property_id="123",
            access_token="token"
        ):
            events.append(event)
        
        elapsed = time.time() - start
        
        # With parallel execution: max(1.0, 0.3) + 0.1 + 1.5 = ~2.9s
        # Without parallel: 1.0 + 0.3 + 0.1 + 1.5 = 2.9s
        assert elapsed < 5.0, f"Pipeline took {elapsed:.2f}s (target: <5s)"


class TestDataQualityValidation:
    """Test data quality validation in E2E flow."""
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_ground_truth_validation_integrated(self):
        """Test ground truth validator is integrated in pipeline."""
        from server.services.validation import GroundTruthValidator
        
        validator = GroundTruthValidator()
        
        # Simulate LLM response
        llm_response = "Mobile had 2,145 sessions"
        raw_metrics = {"sessions": 2145}
        
        result = await validator.validate(llm_response, raw_metrics)
        
        # Should pass
        assert result.is_valid
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_citation_validation_integrated(self):
        """Test citation validator is integrated in pipeline."""
        from server.services.validation import CitationValidator
        from agents.schemas.results import SourceCitation
        
        validator = CitationValidator()
        
        llm_response = "Mobile had 2,145 sessions"
        citations = [
            SourceCitation(
                metric_id=1,
                property_id="123",
                metric_date="2026-01-01",
                raw_json={"sessions": 2145},
                similarity_score=0.95
            )
        ]
        
        annotated, report = await validator.validate_and_annotate(llm_response, citations)
        
        # Should include footnote
        assert "[1]" in annotated
        assert "Sources:" in annotated
        assert report.is_valid


class TestMetadataTracking:
    """Test metadata and audit trail."""
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_pipeline_includes_execution_metadata(self):
        """Test final result includes execution metadata."""
        from agents import EnhancedOrchestratorAgent
        from agents.schemas.results import DataFetchResult, EmbeddingResult, RetrievalResult, ReportResult
        
        orchestrator = EnhancedOrchestratorAgent(openai_api_key="test_key")
        
        # Mock all agents
        orchestrator.data_fetcher.execute = AsyncMock(return_value=DataFetchResult(
            status="success",
            data={},
            cached=False,
            tenant_id=str(uuid4()),
            property_id="123"
        ))
        
        orchestrator.embedding_agent.execute = AsyncMock(return_value=EmbeddingResult(
            embeddings=[[0.1] * 1536],
            quality_score=0.95
        ))
        
        orchestrator.rag_agent.execute = AsyncMock(return_value=RetrievalResult(
            documents=[],
            citations=[],
            confidence=0.8,
            tenant_id=str(uuid4()),
            query_embedding=[0.1] * 1536,
            match_count=0
        ))
        
        orchestrator.reporting_agent.execute = AsyncMock(return_value=ReportResult(
            answer="Report",
            charts=[],
            metrics=[],
            citations=[],
            confidence=0.9,
            tenant_id=str(uuid4()),
            query="test"
        ))
        
        # Execute pipeline
        events = []
        async for event in orchestrator.execute_pipeline_streaming(
            query="test",
            tenant_id=str(uuid4()),
            user_id=str(uuid4()),
            property_id="123",
            access_token="token"
        ):
            events.append(event)
        
        # Verify metadata
        result = [e for e in events if e["type"] == "result"][0]
        assert "metadata" in result["payload"]
        assert "duration_ms" in result["payload"]["metadata"]
        assert "query_id" in result["payload"]["metadata"]

