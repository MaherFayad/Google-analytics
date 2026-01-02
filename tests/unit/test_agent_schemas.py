"""
Unit tests for agent schema validation.

Tests Task P0-22: Agent Result Schema Registry & Validation

Verifies:
- Schema structure and validation
- Runtime validation middleware
- Schema registry lookups
- Error handling and reporting
"""

import pytest
from datetime import datetime
from pydantic import ValidationError as PydanticValidationError

from src.agents.schemas import (
    DataFetchResult,
    EmbeddingResult,
    RetrievalResult,
    ReportResult,
    SourceCitation,
    ChartConfig,
    MetricCard,
    ChartDataPoint,
    AGENT_SCHEMA_REGISTRY,
    get_schema_for_agent,
)
from src.agents.middleware.schema_validator import (
    SchemaValidator,
    validate_agent_result,
    ValidationError,
    reset_validator,
)


class TestDataFetchResult:
    """Test DataFetchResult schema."""
    
    def test_valid_data_fetch_result(self):
        """Test creating valid DataFetchResult."""
        result = DataFetchResult(
            status="success",
            data={"rows": [], "dimensionHeaders": []},
            tenant_id="tenant-123",
            property_id="12345"
        )
        
        assert result.status == "success"
        assert result.cached is False  # default
        assert result.source == "ga4_api"  # default
        assert result.quota_consumed == 1  # default
    
    def test_cached_data_fetch_result(self):
        """Test DataFetchResult with cached data."""
        result = DataFetchResult(
            status="cached",
            data={"rows": []},
            cached=True,
            tenant_id="tenant-123",
            property_id="12345",
            source="cache"
        )
        
        assert result.status == "cached"
        assert result.cached is True
        assert result.source == "cache"
    
    def test_data_fetch_result_validation_error(self):
        """Test DataFetchResult validates data structure."""
        with pytest.raises(PydanticValidationError) as exc_info:
            DataFetchResult(
                status="success",
                data={"invalid": "structure"},  # Missing rows/dimensionHeaders
                tenant_id="tenant-123",
                property_id="12345"
            )
        
        errors = exc_info.value.errors()
        assert any("rows" in str(err) or "dimensionHeaders" in str(err) for err in errors)


class TestEmbeddingResult:
    """Test EmbeddingResult schema."""
    
    def test_valid_embedding_result(self):
        """Test creating valid EmbeddingResult."""
        embedding = [0.1] * 1536  # Valid 1536-dim embedding
        
        result = EmbeddingResult(
            embeddings=[embedding],
            quality_score=0.95,
            tenant_id="tenant-123"
        )
        
        assert len(result.embeddings[0]) == 1536
        assert result.quality_score == 0.95
        assert result.dimension == 1536
        assert result.model == "text-embedding-3-small"
    
    def test_embedding_dimension_validation(self):
        """Test EmbeddingResult validates dimension."""
        invalid_embedding = [0.1] * 100  # Wrong dimension
        
        with pytest.raises(PydanticValidationError) as exc_info:
            EmbeddingResult(
                embeddings=[invalid_embedding],
                quality_score=0.95,
                tenant_id="tenant-123"
            )
        
        errors = exc_info.value.errors()
        assert any("1536" in str(err) for err in errors)
    
    def test_embedding_zero_vector_validation(self):
        """Test EmbeddingResult rejects zero vectors."""
        zero_embedding = [0.0] * 1536  # Zero vector
        
        with pytest.raises(PydanticValidationError) as exc_info:
            EmbeddingResult(
                embeddings=[zero_embedding],
                quality_score=0.95,
                tenant_id="tenant-123"
            )
        
        errors = exc_info.value.errors()
        assert any("zero vector" in str(err).lower() for err in errors)
    
    def test_quality_score_bounds(self):
        """Test quality_score must be between 0 and 1."""
        embedding = [0.1] * 1536
        
        with pytest.raises(PydanticValidationError):
            EmbeddingResult(
                embeddings=[embedding],
                quality_score=1.5,  # > 1.0
                tenant_id="tenant-123"
            )
        
        with pytest.raises(PydanticValidationError):
            EmbeddingResult(
                embeddings=[embedding],
                quality_score=-0.1,  # < 0.0
                tenant_id="tenant-123"
            )


class TestRetrievalResult:
    """Test RetrievalResult schema."""
    
    def test_valid_retrieval_result(self):
        """Test creating valid RetrievalResult."""
        documents = ["Doc 1", "Doc 2", "Doc 3"]
        citations = [
            SourceCitation(
                metric_id=1,
                property_id="12345",
                metric_date="2025-01-01",
                raw_json={"value": 100},
                similarity_score=0.95
            )
            for _ in range(3)
        ]
        
        result = RetrievalResult(
            documents=documents,
            citations=citations,
            confidence=0.92,
            tenant_id="tenant-123",
            query_embedding=[0.1] * 1536
        )
        
        assert len(result.documents) == 3
        assert len(result.citations) == 3
        assert result.confidence == 0.92
    
    def test_documents_citations_length_mismatch(self):
        """Test RetrievalResult validates documents and citations match."""
        documents = ["Doc 1", "Doc 2"]
        citations = [
            SourceCitation(
                metric_id=1,
                property_id="12345",
                metric_date="2025-01-01",
                raw_json={},
                similarity_score=0.95
            )
        ]  # Only 1 citation for 2 documents
        
        with pytest.raises(PydanticValidationError) as exc_info:
            RetrievalResult(
                documents=documents,
                citations=citations,
                confidence=0.92,
                tenant_id="tenant-123",
                query_embedding=[0.1] * 1536
            )
        
        errors = exc_info.value.errors()
        assert any("must match" in str(err).lower() for err in errors)


class TestReportResult:
    """Test ReportResult schema."""
    
    def test_valid_report_result(self):
        """Test creating valid ReportResult."""
        result = ReportResult(
            answer="Mobile traffic increased 21.7% last week...",
            charts=[
                ChartConfig(
                    type="line",
                    title="Traffic Over Time",
                    x_label="Date",
                    y_label="Sessions",
                    data=[
                        ChartDataPoint(x="2025-01-01", y=1234),
                        ChartDataPoint(x="2025-01-02", y=1456),
                    ]
                )
            ],
            metrics=[
                MetricCard(
                    label="Sessions",
                    value="12,450",
                    change="+21.7%",
                    trend="up"
                )
            ],
            confidence=0.92,
            tenant_id="tenant-123",
            query="Show mobile traffic last week"
        )
        
        assert result.answer != ""
        assert len(result.charts) == 1
        assert len(result.metrics) == 1
        assert result.confidence == 0.92


class TestSchemaRegistry:
    """Test schema registry functionality."""
    
    def test_registry_has_all_agents(self):
        """Test registry contains all agent schemas."""
        expected_agents = [
            "DataFetcherAgent",
            "EmbeddingAgent",
            "RagAgent",
            "ReportingAgent"
        ]
        
        for agent_name in expected_agents:
            assert agent_name in AGENT_SCHEMA_REGISTRY
    
    def test_get_schema_for_agent_valid(self):
        """Test getting schema for valid agent name."""
        schema = get_schema_for_agent("DataFetcherAgent")
        assert schema == DataFetchResult
        
        schema = get_schema_for_agent("EmbeddingAgent")
        assert schema == EmbeddingResult
    
    def test_get_schema_for_agent_invalid(self):
        """Test getting schema for invalid agent name raises KeyError."""
        with pytest.raises(KeyError) as exc_info:
            get_schema_for_agent("NonExistentAgent")
        
        assert "not found in schema registry" in str(exc_info.value)
        assert "Available agents" in str(exc_info.value)


class TestSchemaValidator:
    """Test schema validator middleware."""
    
    @pytest.fixture(autouse=True)
    def reset(self):
        """Reset validator before each test."""
        reset_validator()
        yield
        reset_validator()
    
    def test_validator_success(self):
        """Test validator with valid data."""
        validator = SchemaValidator(strict=True)
        
        data = {
            "status": "success",
            "data": {"rows": []},
            "tenant_id": "tenant-123",
            "property_id": "12345"
        }
        
        result = validator.validate(
            data,
            DataFetchResult,
            agent_name="DataFetcherAgent"
        )
        
        assert isinstance(result, DataFetchResult)
        assert result.status == "success"
    
    def test_validator_failure_strict_mode(self):
        """Test validator raises in strict mode."""
        validator = SchemaValidator(strict=True)
        
        data = {
            "status": "invalid",  # Invalid status
            "data": {"rows": []},
            "tenant_id": "tenant-123",
            "property_id": "12345"
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validator.validate(
                data,
                DataFetchResult,
                agent_name="DataFetcherAgent"
            )
        
        error = exc_info.value
        assert error.agent_name == "DataFetcherAgent"
        assert error.schema_name == "DataFetchResult"
        assert len(error.errors) > 0
    
    def test_validator_failure_non_strict_mode(self):
        """Test validator returns None in non-strict mode."""
        validator = SchemaValidator(strict=False)
        
        data = {
            "status": "invalid",
            "data": {"rows": []},
            "tenant_id": "tenant-123",
            "property_id": "12345"
        }
        
        result = validator.validate(
            data,
            DataFetchResult,
            agent_name="DataFetcherAgent"
        )
        
        assert result is None  # Returns None instead of raising
    
    def test_validator_tracks_statistics(self):
        """Test validator tracks success/failure statistics."""
        validator = SchemaValidator(strict=False)
        
        # Successful validation
        validator.validate(
            {
                "status": "success",
                "data": {"rows": []},
                "tenant_id": "tenant-123",
                "property_id": "12345"
            },
            DataFetchResult,
            "DataFetcherAgent"
        )
        
        # Failed validation (non-strict, so continues)
        validator.validate(
            {"status": "invalid"},
            DataFetchResult,
            "DataFetcherAgent"
        )
        
        stats = validator.get_stats()
        assert stats["success_count"] == 1
        assert stats["failure_count"] == 1
        assert stats["total_validations"] == 2
        assert stats["success_rate_percent"] == 50.0
    
    def test_validate_agent_result_convenience_function(self):
        """Test convenience function for validation."""
        data = {
            "status": "success",
            "data": {"rows": []},
            "tenant_id": "tenant-123",
            "property_id": "12345"
        }
        
        result = validate_agent_result(
            data,
            DataFetchResult,
            agent_name="DataFetcherAgent"
        )
        
        assert isinstance(result, DataFetchResult)


class TestValidationErrorDetails:
    """Test validation error details and messages."""
    
    def test_validation_error_to_dict(self):
        """Test ValidationError can be converted to dict."""
        try:
            validate_agent_result(
                {"invalid": "data"},
                DataFetchResult,
                agent_name="DataFetcherAgent"
            )
        except ValidationError as e:
            error_dict = e.to_dict()
            
            assert error_dict["agent_name"] == "DataFetcherAgent"
            assert error_dict["schema_name"] == "DataFetchResult"
            assert "errors" in error_dict
            assert "original_data_keys" in error_dict
    
    def test_validation_error_message_format(self):
        """Test ValidationError has user-friendly message."""
        try:
            validate_agent_result(
                {"status": "invalid"},
                DataFetchResult,
                agent_name="DataFetcherAgent"
            )
        except ValidationError as e:
            message = str(e)
            
            assert "Schema validation failed" in message
            assert "DataFetcherAgent" in message
            assert "DataFetchResult" in message


class TestIntegrationWithAgents:
    """Integration tests with actual agent usage patterns."""
    
    def test_data_fetcher_agent_result_validation(self):
        """Test validating DataFetcherAgent output."""
        # Simulate DataFetcherAgent output
        agent_output = {
            "status": "success",
            "data": {
                "rows": [
                    {"dimensionValues": ["2025-01-01"], "metricValues": [{"value": "1234"}]}
                ],
                "dimensionHeaders": [{"name": "date"}],
                "metricHeaders": [{"name": "sessions"}]
            },
            "cached": False,
            "tenant_id": "tenant-123",
            "property_id": "12345",
            "quota_consumed": 1
        }
        
        validated = validate_agent_result(
            agent_output,
            DataFetchResult,
            agent_name="DataFetcherAgent"
        )
        
        assert validated.status == "success"
        assert not validated.cached
        assert validated.quota_consumed == 1
    
    def test_embedding_agent_result_validation(self):
        """Test validating EmbeddingAgent output."""
        # Simulate EmbeddingAgent output
        agent_output = {
            "embeddings": [[0.1] * 1536, [0.2] * 1536],
            "quality_score": 0.98,
            "dimension": 1536,
            "tenant_id": "tenant-123"
        }
        
        validated = validate_agent_result(
            agent_output,
            EmbeddingResult,
            agent_name="EmbeddingAgent"
        )
        
        assert len(validated.embeddings) == 2
        assert validated.quality_score == 0.98


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

