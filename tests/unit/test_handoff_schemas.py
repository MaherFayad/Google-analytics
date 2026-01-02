"""
Unit tests for agent handoff protocol schemas.

Tests Task P0-38: Agent Handoff Protocol Schema Definition

Verifies:
- All 6 handoff transitions have valid schemas
- Trigger conditions are properly defined
- Timeout and rollback strategies are specified
- Validation rules work correctly
- Decision tree routing logic
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from src.agents.schemas.handoff_protocol import (
    AgentHandoffProtocol,
    TriggerCondition,
    RollbackStrategy,
    DataFetcherToEmbeddingHandoff,
    DataFetcherToRagHandoff,
    EmbeddingToRagHandoff,
    RagToReportingHandoff,
    AnyAgentToFallbackHandoff,
    ReportingToCompleteHandoff,
    HandoffDecisionTree,
    HANDOFF_REGISTRY,
    get_handoff_schema,
)


class TestTriggerConditionsAndStrategies:
    """Test enum definitions."""
    
    def test_trigger_condition_values(self):
        """Test TriggerCondition enum has all expected values."""
        assert TriggerCondition.SUCCESS == "success"
        assert TriggerCondition.CACHED == "cached"
        assert TriggerCondition.PARTIAL == "partial"
        assert TriggerCondition.FAILED == "failed"
        assert TriggerCondition.TIMEOUT == "timeout"
    
    def test_rollback_strategy_values(self):
        """Test RollbackStrategy enum has all expected values."""
        assert RollbackStrategy.CACHE_FALLBACK == "cache_fallback"
        assert RollbackStrategy.RETRY == "retry"
        assert RollbackStrategy.ABORT == "abort"
        assert RollbackStrategy.SKIP_TO_NEXT == "skip_to_next"


class TestTransition1_DataFetcherToEmbedding:
    """Test Transition 1: DataFetcherAgent → EmbeddingAgent"""
    
    def test_valid_handoff(self):
        """Test creating valid DataFetcher → Embedding handoff."""
        handoff = DataFetcherToEmbeddingHandoff(
            data_row_count=100,
            property_id="12345"
        )
        
        assert handoff.from_agent == "DataFetcherAgent"
        assert handoff.to_agent == "EmbeddingAgent"
        assert handoff.trigger_condition == TriggerCondition.SUCCESS
        assert handoff.rollback_strategy == RollbackStrategy.RETRY
        assert handoff.timeout_ms == 60000  # Default 60 seconds
        assert handoff.data_row_count == 100
    
    def test_excessive_row_count_validation(self):
        """Test validation fails for excessive row count."""
        with pytest.raises(ValidationError) as exc_info:
            DataFetcherToEmbeddingHandoff(
                data_row_count=15000,  # > 10,000 limit
                property_id="12345"
            )
        
        errors = exc_info.value.errors()
        assert any("10,000" in str(err) for err in errors)
    
    def test_custom_timeout(self):
        """Test custom timeout value."""
        handoff = DataFetcherToEmbeddingHandoff(
            data_row_count=50,
            property_id="12345",
            timeout_ms=30000  # Custom 30 seconds
        )
        
        assert handoff.timeout_ms == 30000


class TestTransition2_DataFetcherToRag:
    """Test Transition 2: DataFetcherAgent → RagAgent (cached)"""
    
    def test_valid_cached_handoff(self):
        """Test creating valid DataFetcher → RAG handoff for cached data."""
        handoff = DataFetcherToRagHandoff(
            cache_key="ga4:cache:tenant123:query456",
            cache_age_seconds=300
        )
        
        assert handoff.from_agent == "DataFetcherAgent"
        assert handoff.to_agent == "RagAgent"
        assert handoff.trigger_condition == TriggerCondition.CACHED
        assert handoff.rollback_strategy == RollbackStrategy.CACHE_FALLBACK
        assert handoff.timeout_ms == 30000  # Default 30 seconds
        assert handoff.cache_age_seconds == 300
    
    def test_cache_key_required(self):
        """Test cache_key is required field."""
        with pytest.raises(ValidationError):
            DataFetcherToRagHandoff(
                cache_age_seconds=300
                # Missing cache_key
            )


class TestTransition3_EmbeddingToRag:
    """Test Transition 3: EmbeddingAgent → RagAgent"""
    
    def test_valid_embedding_handoff(self):
        """Test creating valid Embedding → RAG handoff."""
        handoff = EmbeddingToRagHandoff(
            embedding_quality_score=0.95,
            embedding_count=50
        )
        
        assert handoff.from_agent == "EmbeddingAgent"
        assert handoff.to_agent == "RagAgent"
        assert handoff.trigger_condition == TriggerCondition.SUCCESS
        assert handoff.rollback_strategy == RollbackStrategy.SKIP_TO_NEXT
        assert handoff.timeout_ms == 45000  # Default 45 seconds
    
    def test_low_quality_score_warning(self):
        """Test low quality score is accepted (with warning)."""
        # Should not raise, but may log warning
        handoff = EmbeddingToRagHandoff(
            embedding_quality_score=0.5,  # Low but valid
            embedding_count=50
        )
        
        assert handoff.embedding_quality_score == 0.5
    
    def test_quality_score_bounds(self):
        """Test quality score must be 0-1."""
        with pytest.raises(ValidationError):
            EmbeddingToRagHandoff(
                embedding_quality_score=1.5,  # > 1.0
                embedding_count=50
            )
        
        with pytest.raises(ValidationError):
            EmbeddingToRagHandoff(
                embedding_quality_score=-0.1,  # < 0.0
                embedding_count=50
            )


class TestTransition4_RagToReporting:
    """Test Transition 4: RagAgent → ReportingAgent"""
    
    def test_valid_rag_to_reporting_handoff(self):
        """Test creating valid RAG → Reporting handoff."""
        handoff = RagToReportingHandoff(
            retrieval_confidence=0.85,
            context_document_count=5
        )
        
        assert handoff.from_agent == "RagAgent"
        assert handoff.to_agent == "ReportingAgent"
        assert handoff.trigger_condition == TriggerCondition.SUCCESS
        assert handoff.rollback_strategy == RollbackStrategy.SKIP_TO_NEXT
        assert handoff.timeout_ms == 90000  # Default 90 seconds (LLM generation)
    
    def test_low_confidence_validation(self):
        """Test low retrieval confidence is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RagToReportingHandoff(
                retrieval_confidence=0.3,  # < 0.5 minimum
                context_document_count=5
            )
        
        errors = exc_info.value.errors()
        assert any("too low" in str(err).lower() for err in errors)
    
    def test_minimum_confidence_accepted(self):
        """Test minimum confidence threshold (0.5) is accepted."""
        handoff = RagToReportingHandoff(
            retrieval_confidence=0.5,
            context_document_count=5
        )
        
        assert handoff.retrieval_confidence == 0.5


class TestTransition5_AnyToFallback:
    """Test Transition 5: Any Agent → FallbackAgent (error recovery)"""
    
    def test_valid_fallback_handoff(self):
        """Test creating valid error → Fallback handoff."""
        handoff = AnyAgentToFallbackHandoff(
            from_agent="EmbeddingAgent",
            error_message="Embedding generation failed due to API timeout"
        )
        
        assert handoff.from_agent == "EmbeddingAgent"
        assert handoff.to_agent == "FallbackAgent"
        assert handoff.trigger_condition == TriggerCondition.FAILED
        assert handoff.rollback_strategy == RollbackStrategy.CACHE_FALLBACK
        assert handoff.timeout_ms == 15000  # Quick fallback
    
    def test_fallback_with_partial_result(self):
        """Test fallback can include partial results."""
        handoff = AnyAgentToFallbackHandoff(
            from_agent="DataFetcherAgent",
            error_message="GA4 API rate limit exceeded",
            partial_result={"rows": [1, 2, 3]}
        )
        
        assert handoff.partial_result is not None
        assert len(handoff.partial_result["rows"]) == 3
    
    def test_timeout_trigger_condition(self):
        """Test fallback can be triggered by timeout."""
        handoff = AnyAgentToFallbackHandoff(
            from_agent="ReportingAgent",
            trigger_condition=TriggerCondition.TIMEOUT,
            error_message="LLM generation timed out after 90s"
        )
        
        assert handoff.trigger_condition == TriggerCondition.TIMEOUT


class TestTransition6_ReportingToComplete:
    """Test Transition 6: ReportingAgent → Complete"""
    
    def test_valid_completion_handoff(self):
        """Test creating valid Reporting → Complete handoff."""
        handoff = ReportingToCompleteHandoff(
            report_confidence=0.92,
            chart_count=3,
            metric_count=5
        )
        
        assert handoff.from_agent == "ReportingAgent"
        assert handoff.to_agent == "Complete"
        assert handoff.trigger_condition == TriggerCondition.SUCCESS
        assert handoff.rollback_strategy == RollbackStrategy.ABORT
        assert handoff.timeout_ms == 5000  # Quick finalization
    
    def test_zero_charts_and_metrics_allowed(self):
        """Test report can have zero charts and metrics."""
        handoff = ReportingToCompleteHandoff(
            report_confidence=0.8,
            chart_count=0,
            metric_count=0
        )
        
        assert handoff.chart_count == 0
        assert handoff.metric_count == 0


class TestHandoffRegistry:
    """Test handoff registry and lookup functions."""
    
    def test_registry_has_all_transitions(self):
        """Test registry contains all 6 transitions."""
        expected_keys = [
            "DataFetcherAgent->EmbeddingAgent",
            "DataFetcherAgent->RagAgent",
            "EmbeddingAgent->RagAgent",
            "RagAgent->ReportingAgent",
            "*->FallbackAgent",
            "ReportingAgent->Complete"
        ]
        
        for key in expected_keys:
            assert key in HANDOFF_REGISTRY
    
    def test_get_handoff_schema_valid(self):
        """Test getting handoff schema for valid transition."""
        schema = get_handoff_schema("DataFetcherAgent", "EmbeddingAgent")
        assert schema == DataFetcherToEmbeddingHandoff
        
        schema = get_handoff_schema("RagAgent", "ReportingAgent")
        assert schema == RagToReportingHandoff
    
    def test_get_handoff_schema_wildcard_fallback(self):
        """Test wildcard fallback for error handling."""
        schema = get_handoff_schema("SomeAgent", "FallbackAgent")
        assert schema == AnyAgentToFallbackHandoff
    
    def test_get_handoff_schema_invalid(self):
        """Test getting schema for invalid transition raises KeyError."""
        with pytest.raises(KeyError) as exc_info:
            get_handoff_schema("InvalidAgent", "NonExistentAgent")
        
        assert "not found in registry" in str(exc_info.value)
        assert "Available transitions" in str(exc_info.value)


class TestHandoffDecisionTree:
    """Test decision tree routing logic."""
    
    def test_decision_tree_datafetcher_fresh_data(self):
        """Test routing DataFetcher result (fresh data) → Embedding."""
        tree = HandoffDecisionTree(
            current_agent="DataFetcherAgent",
            trigger_condition=TriggerCondition.SUCCESS
        )
        
        agent_result = {
            "cached": False,
            "data": {"rows": [1, 2, 3]},
            "property_id": "12345"
        }
        
        next_handoff = tree.get_next_handoff(agent_result)
        
        assert isinstance(next_handoff, DataFetcherToEmbeddingHandoff)
        assert next_handoff.data_row_count == 3
        assert next_handoff.property_id == "12345"
    
    def test_decision_tree_datafetcher_cached_data(self):
        """Test routing DataFetcher result (cached) → RAG."""
        tree = HandoffDecisionTree(
            current_agent="DataFetcherAgent",
            trigger_condition=TriggerCondition.CACHED
        )
        
        agent_result = {
            "cached": True,
            "cache_key": "test_key",
            "cache_age_seconds": 300
        }
        
        next_handoff = tree.get_next_handoff(agent_result)
        
        assert isinstance(next_handoff, DataFetcherToRagHandoff)
        assert next_handoff.cache_key == "test_key"
        assert next_handoff.cache_age_seconds == 300
    
    def test_decision_tree_embedding_to_rag(self):
        """Test routing Embedding result → RAG."""
        tree = HandoffDecisionTree(
            current_agent="EmbeddingAgent",
            trigger_condition=TriggerCondition.SUCCESS
        )
        
        agent_result = {
            "quality_score": 0.95,
            "embeddings": [[0.1] * 1536, [0.2] * 1536]
        }
        
        next_handoff = tree.get_next_handoff(agent_result)
        
        assert isinstance(next_handoff, EmbeddingToRagHandoff)
        assert next_handoff.embedding_quality_score == 0.95
        assert next_handoff.embedding_count == 2
    
    def test_decision_tree_rag_to_reporting(self):
        """Test routing RAG result → Reporting."""
        tree = HandoffDecisionTree(
            current_agent="RagAgent",
            trigger_condition=TriggerCondition.SUCCESS
        )
        
        agent_result = {
            "confidence": 0.87,
            "documents": ["Doc 1", "Doc 2", "Doc 3"]
        }
        
        next_handoff = tree.get_next_handoff(agent_result)
        
        assert isinstance(next_handoff, RagToReportingHandoff)
        assert next_handoff.retrieval_confidence == 0.87
        assert next_handoff.context_document_count == 3
    
    def test_decision_tree_reporting_to_complete(self):
        """Test routing Reporting result → Complete."""
        tree = HandoffDecisionTree(
            current_agent="ReportingAgent",
            trigger_condition=TriggerCondition.SUCCESS
        )
        
        agent_result = {
            "confidence": 0.92,
            "charts": [{"type": "line"}],
            "metrics": [{"label": "Sessions"}]
        }
        
        next_handoff = tree.get_next_handoff(agent_result)
        
        assert isinstance(next_handoff, ReportingToCompleteHandoff)
        assert next_handoff.report_confidence == 0.92
        assert next_handoff.chart_count == 1
        assert next_handoff.metric_count == 1
    
    def test_decision_tree_returns_none_for_unknown_agent(self):
        """Test decision tree returns None for unknown agent."""
        tree = HandoffDecisionTree(
            current_agent="UnknownAgent",
            trigger_condition=TriggerCondition.SUCCESS
        )
        
        next_handoff = tree.get_next_handoff({})
        assert next_handoff is None


class TestTimeoutValidation:
    """Test timeout validation across all handoffs."""
    
    def test_timeout_must_be_positive(self):
        """Test timeout must be > 0."""
        with pytest.raises(ValidationError):
            DataFetcherToEmbeddingHandoff(
                data_row_count=100,
                property_id="12345",
                timeout_ms=0  # Invalid
            )
    
    def test_timeout_max_5_minutes(self):
        """Test timeout cannot exceed 5 minutes (300,000ms)."""
        with pytest.raises(ValidationError):
            DataFetcherToEmbeddingHandoff(
                data_row_count=100,
                property_id="12345",
                timeout_ms=600000  # 10 minutes, exceeds limit
            )


class TestRetryCountValidation:
    """Test retry count validation."""
    
    def test_retry_count_max_3(self):
        """Test retry count cannot exceed 3."""
        with pytest.raises(ValidationError):
            DataFetcherToEmbeddingHandoff(
                data_row_count=100,
                property_id="12345",
                retry_count=5  # Exceeds max of 3
            )
    
    def test_retry_count_cannot_be_negative(self):
        """Test retry count cannot be negative."""
        with pytest.raises(ValidationError):
            DataFetcherToEmbeddingHandoff(
                data_row_count=100,
                property_id="12345",
                retry_count=-1
            )


class TestMetadataField:
    """Test metadata field functionality."""
    
    def test_metadata_optional(self):
        """Test metadata is optional."""
        handoff = DataFetcherToEmbeddingHandoff(
            data_row_count=100,
            property_id="12345"
        )
        
        assert handoff.metadata == {}
    
    def test_metadata_can_store_custom_data(self):
        """Test metadata can store custom key-value pairs."""
        handoff = DataFetcherToEmbeddingHandoff(
            data_row_count=100,
            property_id="12345",
            metadata={
                "user_id": "user-123",
                "query": "Show mobile traffic",
                "debug": True
            }
        )
        
        assert handoff.metadata["user_id"] == "user-123"
        assert handoff.metadata["debug"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

