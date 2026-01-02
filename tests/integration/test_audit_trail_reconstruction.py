"""
Integration Tests for Audit Trail Reconstruction

Implements Task P0-44: Admin Audit Trail API for Data Lineage

Tests:
- Complete lineage reconstruction
- Data transformation tracking
- Validation result inclusion
- Performance requirements
- Authorization checks
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.api.v1.admin.audit_trail import (
    router as audit_trail_router,
    reconstruct_audit_trail,
    AuditTrailResponse,
    GA4APIRequest,
    RawMetric,
    EmbeddingUsed,
    LLMInteraction,
    ValidationResults,
    DataLineageStep,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def test_app():
    """Test FastAPI application with audit trail routes."""
    app = FastAPI()
    app.include_router(audit_trail_router, prefix="/api/v1/admin")
    return app


@pytest.fixture
def client(test_app):
    """Test client for API requests."""
    return TestClient(test_app)


@pytest.fixture
def admin_user():
    """Mock admin user."""
    return {
        "user_id": "admin-123",
        "role": "admin",
        "tenant_id": "tenant-456"
    }


@pytest.fixture
def regular_user():
    """Mock regular user (non-admin)."""
    return {
        "user_id": "user-789",
        "role": "user",
        "tenant_id": "tenant-456"
    }


@pytest.fixture
def mock_audit_trail():
    """Mock complete audit trail data."""
    return AuditTrailResponse(
        report_id="report-123",
        query="Show mobile conversions",
        tenant_id="tenant-456",
        user_id="user-789",
        created_at=datetime.now(),
        
        ga4_api_request=GA4APIRequest(
            endpoint="runReport",
            request_params={
                "property": "properties/123456789",
                "dateRanges": [{"startDate": "7daysAgo", "endDate": "today"}],
                "dimensions": [{"name": "deviceCategory"}],
                "metrics": [{"name": "conversions"}]
            },
            response_time_ms=234,
            cached=False,
            timestamp=datetime.now(),
            status="success"
        ),
        
        raw_metrics=[
            RawMetric(
                id=789,
                metric_date="2025-01-05",
                dimension_values={"deviceCategory": "mobile"},
                metric_values={"conversions": 1234.0},
                property_id="123456789"
            )
        ],
        
        embeddings_used=[
            EmbeddingUsed(
                id="embedding-uuid-1",
                similarity=0.92,
                content="Mobile conversions data",
                chunk_metadata={"source": "ga4_metrics"},
                timestamp_created=datetime.now()
            )
        ],
        
        llm_interaction=LLMInteraction(
            model="gpt-4",
            prompt="Analyze mobile conversions...",
            prompt_tokens=1500,
            response="Mobile conversions: 1,234",
            response_tokens=200,
            latency_ms=1200,
            temperature=0.7,
            timestamp=datetime.now()
        ),
        
        validation_results=ValidationResults(
            grounding_score=0.95,
            citation_accuracy=1.0,
            ungrounded_claims=[],
            confidence_score=0.93,
            validation_timestamp=datetime.now()
        ),
        
        lineage_steps=[
            DataLineageStep(
                step_number=1,
                step_name="GA4 API Request",
                input_data={"query": "Show mobile conversions"},
                output_data={"metrics_count": 1},
                duration_ms=234,
                timestamp=datetime.now()
            ),
            DataLineageStep(
                step_number=2,
                step_name="Generate Embeddings",
                input_data={"metrics_count": 1},
                output_data={"embeddings_count": 1},
                duration_ms=456,
                timestamp=datetime.now()
            ),
            DataLineageStep(
                step_number=3,
                step_name="Vector Search",
                input_data={"query_embedding": "..."},
                output_data={"results_count": 5},
                duration_ms=123,
                timestamp=datetime.now()
            ),
            DataLineageStep(
                step_number=4,
                step_name="LLM Generation",
                input_data={"context_chunks": 5},
                output_data={"report": "..."},
                duration_ms=1200,
                timestamp=datetime.now()
            )
        ],
        
        total_duration_ms=2013,
        cache_hits={
            "ga4_api": False,
            "embeddings": True,
            "vector_search": False
        },
        
        metadata={
            "api_version": "v1",
            "pipeline_version": "2.0"
        }
    )


# ============================================================================
# Audit Trail Reconstruction Tests
# ============================================================================

@pytest.mark.asyncio
async def test_reconstruct_audit_trail_success(mock_audit_trail):
    """Test successful audit trail reconstruction."""
    report_id = "report-123"
    tenant_id = "tenant-456"
    
    # Mock database session
    mock_session = AsyncMock()
    
    # Reconstruct audit trail
    audit_trail = await reconstruct_audit_trail(report_id, mock_session, tenant_id)
    
    # Verify structure
    assert audit_trail.report_id == report_id
    assert audit_trail.tenant_id == tenant_id
    assert audit_trail.ga4_api_request is not None
    assert len(audit_trail.raw_metrics) > 0
    assert len(audit_trail.embeddings_used) > 0
    assert audit_trail.llm_interaction is not None
    assert audit_trail.validation_results is not None
    assert len(audit_trail.lineage_steps) == 4


@pytest.mark.asyncio
async def test_audit_trail_includes_all_stages(mock_audit_trail):
    """Test that audit trail includes all pipeline stages."""
    report_id = "report-123"
    tenant_id = "tenant-456"
    mock_session = AsyncMock()
    
    audit_trail = await reconstruct_audit_trail(report_id, mock_session, tenant_id)
    
    # Verify all stages present
    stage_names = [step.step_name for step in audit_trail.lineage_steps]
    expected_stages = [
        "GA4 API Request",
        "Generate Embeddings",
        "Vector Search",
        "LLM Generation"
    ]
    
    for expected in expected_stages:
        assert expected in stage_names, f"Missing stage: {expected}"


@pytest.mark.asyncio
async def test_audit_trail_performance_metrics():
    """Test that performance metrics are tracked at each stage."""
    report_id = "report-123"
    tenant_id = "tenant-456"
    mock_session = AsyncMock()
    
    audit_trail = await reconstruct_audit_trail(report_id, mock_session, tenant_id)
    
    # Verify each step has duration
    for step in audit_trail.lineage_steps:
        assert step.duration_ms > 0, f"Step {step.step_name} missing duration"
    
    # Verify total duration
    assert audit_trail.total_duration_ms > 0
    
    # Verify total duration is sum of steps (approximately)
    total_step_duration = sum(step.duration_ms for step in audit_trail.lineage_steps)
    assert total_step_duration <= audit_trail.total_duration_ms


@pytest.mark.asyncio
async def test_audit_trail_validation_results():
    """Test validation results are included in audit trail."""
    report_id = "report-123"
    tenant_id = "tenant-456"
    mock_session = AsyncMock()
    
    audit_trail = await reconstruct_audit_trail(report_id, mock_session, tenant_id)
    
    # Verify validation results
    assert audit_trail.validation_results is not None
    assert 0.0 <= audit_trail.validation_results.grounding_score <= 1.0
    assert 0.0 <= audit_trail.validation_results.citation_accuracy <= 1.0
    assert 0.0 <= audit_trail.validation_results.confidence_score <= 1.0
    assert isinstance(audit_trail.validation_results.ungrounded_claims, list)


@pytest.mark.asyncio
async def test_audit_trail_cache_tracking():
    """Test cache hit tracking across stages."""
    report_id = "report-123"
    tenant_id = "tenant-456"
    mock_session = AsyncMock()
    
    audit_trail = await reconstruct_audit_trail(report_id, mock_session, tenant_id)
    
    # Verify cache tracking
    assert "cache_hits" in audit_trail.__dict__
    assert isinstance(audit_trail.cache_hits, dict)
    assert len(audit_trail.cache_hits) > 0
    
    # Verify cache values are boolean
    for stage, cached in audit_trail.cache_hits.items():
        assert isinstance(cached, bool), f"Cache hit for {stage} not boolean"


# ============================================================================
# API Endpoint Tests
# ============================================================================

def test_get_audit_trail_endpoint_requires_admin(client, regular_user):
    """Test that audit trail endpoint requires admin role."""
    report_id = "report-123"
    
    with patch('src.server.api.v1.admin.audit_trail.get_current_user', return_value=regular_user):
        with patch('src.server.api.v1.admin.audit_trail.get_tenant_context', return_value="tenant-456"):
            response = client.get(f"/api/v1/admin/reports/{report_id}/audit_trail")
    
    assert response.status_code == 403
    assert "Admin role required" in response.json()["detail"]


def test_get_audit_trail_endpoint_success(client, admin_user, mock_audit_trail):
    """Test successful audit trail retrieval."""
    report_id = "report-123"
    
    with patch('src.server.api.v1.admin.audit_trail.get_current_user', return_value=admin_user):
        with patch('src.server.api.v1.admin.audit_trail.get_tenant_context', return_value="tenant-456"):
            with patch('src.server.api.v1.admin.audit_trail.reconstruct_audit_trail', return_value=mock_audit_trail):
                response = client.get(f"/api/v1/admin/reports/{report_id}/audit_trail")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure
    assert data["report_id"] == report_id
    assert "ga4_api_request" in data
    assert "raw_metrics" in data
    assert "embeddings_used" in data
    assert "llm_interaction" in data
    assert "validation_results" in data
    assert "lineage_steps" in data


def test_list_audit_trails_pagination(client, admin_user):
    """Test audit trail list with pagination."""
    with patch('src.server.api.v1.admin.audit_trail.get_current_user', return_value=admin_user):
        response = client.get("/api/v1/admin/reports/audit_trails?limit=10&offset=0")
    
    assert response.status_code == 200
    data = response.json()
    
    assert isinstance(data, list)
    assert len(data) <= 10


def test_export_audit_trail_endpoint(client, admin_user, mock_audit_trail):
    """Test audit trail export as JSON."""
    report_id = "report-123"
    
    with patch('src.server.api.v1.admin.audit_trail.get_current_user', return_value=admin_user):
        with patch('src.server.api.v1.admin.audit_trail.get_tenant_context', return_value="tenant-456"):
            with patch('src.server.api.v1.admin.audit_trail.reconstruct_audit_trail', return_value=mock_audit_trail):
                response = client.post(f"/api/v1/admin/reports/{report_id}/audit_trail/export")
    
    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    assert f"audit_trail_{report_id}.json" in response.headers["content-disposition"]


# ============================================================================
# Data Completeness Tests
# ============================================================================

@pytest.mark.asyncio
async def test_audit_trail_completeness():
    """Test 100% lineage completeness for reports."""
    report_id = "report-123"
    tenant_id = "tenant-456"
    mock_session = AsyncMock()
    
    audit_trail = await reconstruct_audit_trail(report_id, mock_session, tenant_id)
    
    # Check all required fields are present
    required_fields = [
        "report_id",
        "query",
        "tenant_id",
        "user_id",
        "created_at",
        "lineage_steps",
        "total_duration_ms"
    ]
    
    for field in required_fields:
        assert hasattr(audit_trail, field), f"Missing required field: {field}"
        assert getattr(audit_trail, field) is not None, f"Field {field} is None"


@pytest.mark.asyncio
async def test_audit_trail_data_transformations_visible():
    """Test that all data transformations are visible in lineage."""
    report_id = "report-123"
    tenant_id = "tenant-456"
    mock_session = AsyncMock()
    
    audit_trail = await reconstruct_audit_trail(report_id, mock_session, tenant_id)
    
    # Verify each step has input and output data
    for step in audit_trail.lineage_steps:
        assert "input_data" in step.__dict__
        assert "output_data" in step.__dict__
        assert step.input_data is not None
        assert step.output_data is not None


# ============================================================================
# Performance Tests
# ============================================================================

@pytest.mark.asyncio
async def test_audit_trail_query_performance():
    """Test audit trail query completes within 500ms."""
    import time
    
    report_id = "report-123"
    tenant_id = "tenant-456"
    mock_session = AsyncMock()
    
    start_time = time.time()
    audit_trail = await reconstruct_audit_trail(report_id, mock_session, tenant_id)
    elapsed_ms = (time.time() - start_time) * 1000
    
    assert elapsed_ms < 500, f"Audit trail query took {elapsed_ms:.0f}ms (threshold: 500ms)"


# ============================================================================
# Error Handling Tests
# ============================================================================

@pytest.mark.asyncio
async def test_audit_trail_handles_missing_stages_gracefully():
    """Test graceful handling when some stages are missing."""
    report_id = "report-incomplete"
    tenant_id = "tenant-456"
    mock_session = AsyncMock()
    
    # Should not raise, even if some data is missing
    audit_trail = await reconstruct_audit_trail(report_id, mock_session, tenant_id)
    
    assert audit_trail is not None
    assert audit_trail.report_id == report_id


def test_audit_trail_unauthorized_access(client, regular_user):
    """Test unauthorized access is properly blocked."""
    report_id = "report-123"
    
    with patch('src.server.api.v1.admin.audit_trail.get_current_user', return_value=regular_user):
        with patch('src.server.api.v1.admin.audit_trail.get_tenant_context', return_value="tenant-456"):
            response = client.get(f"/api/v1/admin/reports/{report_id}/audit_trail")
    
    assert response.status_code == 403


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_full_audit_trail_workflow():
    """Test complete audit trail workflow from creation to retrieval."""
    report_id = "report-integration-test"
    tenant_id = "tenant-456"
    mock_session = AsyncMock()
    
    # Step 1: Create report (simulated)
    # Step 2: Reconstruct audit trail
    audit_trail = await reconstruct_audit_trail(report_id, mock_session, tenant_id)
    
    # Step 3: Verify completeness
    assert audit_trail.report_id == report_id
    assert len(audit_trail.lineage_steps) > 0
    assert audit_trail.total_duration_ms > 0
    
    # Step 4: Verify all stages represented
    assert audit_trail.ga4_api_request is not None
    assert len(audit_trail.embeddings_used) > 0
    assert audit_trail.llm_interaction is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

