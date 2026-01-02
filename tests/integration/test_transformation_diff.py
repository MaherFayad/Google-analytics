"""
Integration tests for Transformation Diff API.

Implements Task P0-50: Transformation Diff API for Safe Upgrades [HIGH]

Tests:
1. Compare two transformation versions successfully
2. Handle major deviations correctly
3. Provide correct deployment recommendations
4. Export diff as CSV
5. List available transformation versions
6. Handle missing data gracefully
7. Enforce admin-only access
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from datetime import datetime, date

from src.server.main import app
from src.server.api.v1.admin.transformation_diff import (
    DeploymentRecommendation,
    _cosine_similarity,
    _analyze_deviation,
    _get_deployment_recommendation,
)


@pytest.fixture
def admin_headers():
    """Mock headers for admin user."""
    return {
        "Authorization": "Bearer admin_token",
        "X-Tenant-ID": "test_tenant_123"
    }


@pytest.fixture
def non_admin_headers():
    """Mock headers for non-admin user."""
    return {
        "Authorization": "Bearer user_token",
        "X-Tenant-ID": "test_tenant_123"
    }


@pytest.fixture
def mock_ga4_metrics():
    """Mock GA4 metrics data."""
    return [
        Mock(
            id=1,
            metric_date=date(2025, 1, 1),
            dimension_context={"device": "mobile"},
            metric_values={"sessions": 10234, "conversions": 456}
        ),
        Mock(
            id=2,
            metric_date=date(2025, 1, 2),
            dimension_context={"device": "desktop"},
            metric_values={"sessions": 8765, "conversions": 321}
        ),
    ]


@pytest.mark.asyncio
async def test_compare_transformation_versions_success(admin_headers, mock_ga4_metrics):
    """
    Test successful transformation comparison.
    
    Scenario:
        - Admin compares v1.0.0 vs v1.1.0
        - Sample size: 100 rows
        - Expected: Comparison report with similarity scores
    """
    client = TestClient(app)
    
    # Mock dependencies
    with patch('src.server.api.v1.admin.transformation_diff._fetch_sample_data') as mock_fetch, \
         patch('src.server.api.v1.admin.transformation_diff.EmbeddingService') as MockEmbedding, \
         patch('src.server.api.v1.admin.transformation_diff.GA4DataTransformer') as MockTransformer, \
         patch('src.server.middleware.tenant.get_current_tenant_id', return_value="test_tenant_123"), \
         patch('src.server.middleware.tenant.get_tenant_role', return_value="admin"):
        
        # Setup mocks
        mock_fetch.return_value = mock_ga4_metrics
        
        mock_embedding = MockEmbedding.return_value
        mock_embedding.generate_embedding = AsyncMock(side_effect=[
            [0.1] * 1536,  # embedding v1 for row 1
            [0.11] * 1536,  # embedding v2 for row 1 (similar)
            [0.2] * 1536,  # embedding v1 for row 2
            [0.21] * 1536,  # embedding v2 for row 2 (similar)
        ])
        
        mock_transformer_v1 = MockTransformer.return_value
        mock_transformer_v1.transform_to_descriptive_text.return_value = "Mobile sessions: 10,234"
        
        mock_transformer_v2 = MockTransformer.return_value
        mock_transformer_v2.transform_to_descriptive_text.return_value = "Mobile sessions: 10,234"
        
        # Make request
        response = client.post(
            "/api/v1/admin/transformation/compare",
            json={
                "version_a": "v1.0.0",
                "version_b": "v1.1.0",
                "sample_size": 100
            },
            headers=admin_headers
        )
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        assert data["version_a"] == "v1.0.0"
        assert data["version_b"] == "v1.1.0"
        assert data["rows_compared"] == 2
        assert 0.0 <= data["average_similarity"] <= 1.0
        assert data["recommendation"] in [r.value for r in DeploymentRecommendation]


@pytest.mark.asyncio
async def test_major_deviations_detected(admin_headers, mock_ga4_metrics):
    """
    Test that major deviations are detected correctly.
    
    Scenario:
        - Transformation v2 produces very different output
        - Similarity <0.8
        - Expected: Deviations listed in response
    """
    client = TestClient(app)
    
    with patch('src.server.api.v1.admin.transformation_diff._fetch_sample_data') as mock_fetch, \
         patch('src.server.api.v1.admin.transformation_diff.EmbeddingService') as MockEmbedding, \
         patch('src.server.api.v1.admin.transformation_diff.GA4DataTransformer') as MockTransformer, \
         patch('src.server.middleware.tenant.get_current_tenant_id', return_value="test_tenant_123"), \
         patch('src.server.middleware.tenant.get_tenant_role', return_value="admin"):
        
        mock_fetch.return_value = mock_ga4_metrics
        
        # Create very different embeddings (low similarity)
        mock_embedding = MockEmbedding.return_value
        mock_embedding.generate_embedding = AsyncMock(side_effect=[
            [1.0] + [0.0] * 1535,  # embedding v1
            [0.0] * 1535 + [1.0],  # embedding v2 (very different)
            [1.0] + [0.0] * 1535,  # embedding v1
            [0.0] * 1535 + [1.0],  # embedding v2 (very different)
        ])
        
        mock_transformer_v1 = MockTransformer.return_value
        mock_transformer_v1.transform_to_descriptive_text.return_value = "Mobile sessions: 10,234"
        
        mock_transformer_v2 = MockTransformer.return_value
        mock_transformer_v2.transform_to_descriptive_text.return_value = "Mobile conversions increased 15%"
        
        # Make request
        response = client.post(
            "/api/v1/admin/transformation/compare",
            json={
                "version_a": "v1.0.0",
                "version_b": "v2.0.0",
                "sample_size": 100
            },
            headers=admin_headers
        )
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        # Should have major deviations
        assert data["major_deviations_count"] > 0
        assert len(data["major_deviations"]) > 0
        
        # Check deviation structure
        deviation = data["major_deviations"][0]
        assert "metric_id" in deviation
        assert "text_v1" in deviation
        assert "text_v2" in deviation
        assert "similarity" in deviation
        assert deviation["similarity"] < 0.8


@pytest.mark.asyncio
async def test_deployment_recommendations():
    """
    Test deployment recommendation logic.
    
    Scenarios:
        - High similarity (>0.9) → SAFE_TO_DEPLOY
        - Medium similarity (0.8-0.9) → REVIEW_REQUIRED
        - Low similarity (<0.8) → UNSAFE_HIGH_DEVIATION
    """
    # Safe to deploy
    rec = _get_deployment_recommendation(avg_similarity=0.95, major_deviations_count=2)
    assert rec == DeploymentRecommendation.SAFE_TO_DEPLOY
    
    # Review required
    rec = _get_deployment_recommendation(avg_similarity=0.85, major_deviations_count=10)
    assert rec == DeploymentRecommendation.REVIEW_REQUIRED
    
    # Unsafe
    rec = _get_deployment_recommendation(avg_similarity=0.70, major_deviations_count=50)
    assert rec == DeploymentRecommendation.UNSAFE_HIGH_DEVIATION


@pytest.mark.asyncio
async def test_export_diff_as_csv(admin_headers, mock_ga4_metrics):
    """
    Test CSV export functionality.
    
    Scenario:
        - Admin requests CSV export
        - Expected: CSV file with comparison results
    """
    client = TestClient(app)
    
    with patch('src.server.api.v1.admin.transformation_diff._fetch_sample_data') as mock_fetch, \
         patch('src.server.api.v1.admin.transformation_diff.EmbeddingService') as MockEmbedding, \
         patch('src.server.api.v1.admin.transformation_diff.GA4DataTransformer') as MockTransformer, \
         patch('src.server.middleware.tenant.get_current_tenant_id', return_value="test_tenant_123"), \
         patch('src.server.middleware.tenant.get_tenant_role', return_value="admin"):
        
        mock_fetch.return_value = mock_ga4_metrics
        
        mock_embedding = MockEmbedding.return_value
        mock_embedding.generate_embedding = AsyncMock(return_value=[0.1] * 1536)
        
        mock_transformer = MockTransformer.return_value
        mock_transformer.transform_to_descriptive_text.return_value = "Test text"
        
        # Make request
        response = client.post(
            "/api/v1/admin/transformation/export-diff",
            json={
                "version_a": "v1.0.0",
                "version_b": "v1.1.0",
                "sample_size": 10
            },
            headers=admin_headers
        )
        
        # Verify response
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert "transformation_diff_v1.0.0_vs_v1.1.0.csv" in response.headers["content-disposition"]
        
        # Verify CSV content
        csv_content = response.text
        assert "Metric ID" in csv_content
        assert "Similarity" in csv_content
        assert "Summary" in csv_content


@pytest.mark.asyncio
async def test_list_transformation_versions(admin_headers):
    """
    Test listing available transformation versions.
    
    Scenario:
        - Admin requests list of versions
        - Expected: List of versions with usage counts
    """
    client = TestClient(app)
    
    with patch('src.server.middleware.tenant.get_current_tenant_id', return_value="test_tenant_123"), \
         patch('src.server.middleware.tenant.get_tenant_role', return_value="admin"), \
         patch('src.server.api.v1.admin.transformation_diff.AsyncSession') as MockSession:
        
        # Mock database query result
        mock_session = MockSession.return_value
        mock_result = Mock()
        mock_result.fetchall.return_value = [
            ("v1.1.0", 150),
            ("v1.0.0", 1000),
        ]
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # Make request
        response = client.get(
            "/api/v1/admin/transformation/versions",
            headers=admin_headers
        )
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        assert "versions" in data
        assert len(data["versions"]) == 2
        assert data["versions"][0]["version"] == "v1.1.0"
        assert data["versions"][0]["usage_count"] == 150


@pytest.mark.asyncio
async def test_non_admin_access_denied(non_admin_headers):
    """
    Test that non-admin users cannot access transformation diff API.
    
    Scenario:
        - Non-admin user tries to compare versions
        - Expected: 403 Forbidden
    """
    client = TestClient(app)
    
    with patch('src.server.middleware.tenant.get_current_tenant_id', return_value="test_tenant_123"), \
         patch('src.server.middleware.tenant.get_tenant_role', return_value="member"):
        
        # Make request
        response = client.post(
            "/api/v1/admin/transformation/compare",
            json={
                "version_a": "v1.0.0",
                "version_b": "v1.1.0",
                "sample_size": 100
            },
            headers=non_admin_headers
        )
        
        # Verify response
        assert response.status_code == 403
        assert "admin" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_no_data_available(admin_headers):
    """
    Test handling when no GA4 metrics data is available.
    
    Scenario:
        - No data in database for comparison
        - Expected: 404 Not Found
    """
    client = TestClient(app)
    
    with patch('src.server.api.v1.admin.transformation_diff._fetch_sample_data') as mock_fetch, \
         patch('src.server.middleware.tenant.get_current_tenant_id', return_value="test_tenant_123"), \
         patch('src.server.middleware.tenant.get_tenant_role', return_value="admin"):
        
        # Mock empty data
        mock_fetch.return_value = []
        
        # Make request
        response = client.post(
            "/api/v1/admin/transformation/compare",
            json={
                "version_a": "v1.0.0",
                "version_b": "v1.1.0",
                "sample_size": 100
            },
            headers=admin_headers
        )
        
        # Verify response
        assert response.status_code == 404
        assert "No GA4 metrics data found" in response.json()["detail"]


def test_cosine_similarity():
    """
    Test cosine similarity calculation.
    
    Scenarios:
        - Identical vectors → similarity = 1.0
        - Orthogonal vectors → similarity = 0.0
        - Similar vectors → similarity > 0.9
    """
    # Identical vectors
    vec1 = [1.0, 2.0, 3.0]
    vec2 = [1.0, 2.0, 3.0]
    assert _cosine_similarity(vec1, vec2) == pytest.approx(1.0, abs=0.01)
    
    # Orthogonal vectors
    vec1 = [1.0, 0.0, 0.0]
    vec2 = [0.0, 1.0, 0.0]
    assert _cosine_similarity(vec1, vec2) == pytest.approx(0.0, abs=0.01)
    
    # Similar vectors
    vec1 = [1.0, 2.0, 3.0]
    vec2 = [1.1, 2.1, 3.1]
    similarity = _cosine_similarity(vec1, vec2)
    assert similarity > 0.99


def test_analyze_deviation():
    """
    Test deviation analysis.
    
    Scenarios:
        - Numeric differences → "Numeric value differences"
        - Length differences → "Significant length difference"
        - Wording changes → "Wording changes"
    """
    # Numeric differences
    text_v1 = "Mobile sessions: 10,234"
    text_v2 = "Mobile sessions: 10,235"
    reason = _analyze_deviation(text_v1, text_v2, 0.95)
    assert "Numeric" in reason or "rounding" in reason.lower()
    
    # Length differences
    text_v1 = "Short text"
    text_v2 = "This is a much longer text with many more words and details about the metrics"
    reason = _analyze_deviation(text_v1, text_v2, 0.60)
    assert "length" in reason.lower()
    
    # Wording changes
    text_v1 = "Mobile sessions increased"
    text_v2 = "Mobile sessions grew"
    reason = _analyze_deviation(text_v1, text_v2, 0.85)
    assert "Wording" in reason or "change" in reason.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

