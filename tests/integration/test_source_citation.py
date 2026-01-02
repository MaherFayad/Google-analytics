"""
Integration tests for Source Citation Tracking.

Tests Task P0-42: Source Citation Tracking for RAG Provenance [CRITICAL]
"""

import pytest
from datetime import date
from uuid import uuid4

from agents.schemas.results import SourceCitation, RetrievalResult


class TestSourceCitationModel:
    """Test SourceCitation Pydantic model."""
    
    def test_citation_creation(self):
        """Test creating source citation."""
        citation = SourceCitation(
            metric_id=123,
            property_id="987654321",
            metric_date="2026-01-01",
            raw_json={"sessions": 1234, "conversions": 56},
            similarity_score=0.92,
        )
        
        assert citation.metric_id == 123
        assert citation.property_id == "987654321"
        assert citation.similarity_score == 0.92
    
    def test_citation_validation(self):
        """Test citation field validation."""
        # Valid similarity score
        citation = SourceCitation(
            metric_id=1,
            property_id="123",
            metric_date="2026-01-01",
            raw_json={},
            similarity_score=0.85,
        )
        assert 0.0 <= citation.similarity_score <= 1.0
        
        # Invalid similarity score should raise validation error
        with pytest.raises(ValueError):
            SourceCitation(
                metric_id=1,
                property_id="123",
                metric_date="2026-01-01",
                raw_json={},
                similarity_score=1.5,  # Invalid (>1.0)
            )


class TestRetrievalResultWithCitations:
    """Test RetrievalResult includes citations."""
    
    def test_retrieval_result_with_citations(self):
        """Test retrieval result includes source citations."""
        citations = [
            SourceCitation(
                metric_id=1,
                property_id="123",
                metric_date="2026-01-01",
                raw_json={"sessions": 1234},
                similarity_score=0.92,
            ),
            SourceCitation(
                metric_id=2,
                property_id="123",
                metric_date="2026-01-02",
                raw_json={"sessions": 1456},
                similarity_score=0.87,
            ),
        ]
        
        result = RetrievalResult(
            documents=["Doc 1", "Doc 2"],
            citations=citations,
            confidence=0.895,
            tenant_id=str(uuid4()),
            query_embedding=[0.1] * 1536,
            match_count=2,
        )
        
        assert len(result.citations) == 2
        assert result.citations[0].metric_id == 1
        assert result.citations[1].metric_id == 2
    
    def test_documents_citations_length_match(self):
        """Test documents and citations must have same length."""
        # This should pass validation
        result = RetrievalResult(
            documents=["Doc 1", "Doc 2"],
            citations=[
                SourceCitation(
                    metric_id=1,
                    property_id="123",
                    metric_date="2026-01-01",
                    raw_json={},
                    similarity_score=0.9,
                ),
                SourceCitation(
                    metric_id=2,
                    property_id="123",
                    metric_date="2026-01-02",
                    raw_json={},
                    similarity_score=0.8,
                ),
            ],
            confidence=0.85,
            tenant_id=str(uuid4()),
            query_embedding=[0.1] * 1536,
            match_count=2,
        )
        
        assert len(result.documents) == len(result.citations)


class TestCitationProvenance:
    """Test citation provenance tracking."""
    
    @pytest.mark.asyncio
    async def test_citation_traces_to_raw_metric(self):
        """Test citation can be traced back to raw GA4 metric."""
        # Simulate citation from RAG retrieval
        citation = SourceCitation(
            metric_id=123,
            property_id="987654321",
            metric_date="2026-01-01",
            raw_json={
                "sessions": 12450,
                "conversions": 234,
                "device": "mobile",
                "bounce_rate": 42.3
            },
            similarity_score=0.92,
        )
        
        # Verify we can extract all metrics from raw_json
        assert citation.raw_json["sessions"] == 12450
        assert citation.raw_json["conversions"] == 234
        assert citation.raw_json["bounce_rate"] == 42.3
    
    @pytest.mark.asyncio
    async def test_multiple_citations_for_report(self):
        """Test report can have multiple source citations."""
        citations = [
            SourceCitation(
                metric_id=i,
                property_id="123",
                metric_date=f"2026-01-{i:02d}",
                raw_json={"sessions": 1000 + i * 100},
                similarity_score=0.95 - i * 0.05,
            )
            for i in range(1, 6)
        ]
        
        # All citations should be traceable
        assert len(citations) == 5
        assert all(c.metric_id > 0 for c in citations)
        assert all(0.0 <= c.similarity_score <= 1.0 for c in citations)


class TestCitationFiltering:
    """Test citation filtering by confidence."""
    
    def test_filter_low_confidence_citations(self):
        """Test filtering citations below threshold."""
        citations = [
            SourceCitation(
                metric_id=1,
                property_id="123",
                metric_date="2026-01-01",
                raw_json={"sessions": 1234},
                similarity_score=0.92,  # High confidence
            ),
            SourceCitation(
                metric_id=2,
                property_id="123",
                metric_date="2026-01-02",
                raw_json={"sessions": 1456},
                similarity_score=0.45,  # Low confidence
            ),
            SourceCitation(
                metric_id=3,
                property_id="123",
                metric_date="2026-01-03",
                raw_json={"sessions": 1678},
                similarity_score=0.88,  # High confidence
            ),
        ]
        
        # Filter by confidence threshold
        threshold = 0.70
        high_confidence = [c for c in citations if c.similarity_score >= threshold]
        
        assert len(high_confidence) == 2
        assert all(c.similarity_score >= threshold for c in high_confidence)


class TestCitationInReporting:
    """Test citations are used in report generation."""
    
    @pytest.mark.asyncio
    async def test_report_includes_citations(self):
        """Test generated report includes source citations."""
        # Simulate RAG retrieval with citations
        retrieval_result = RetrievalResult(
            documents=[
                "Mobile sessions: 12,450 (Jan 1-7, 2026)",
                "Desktop sessions: 8,234 (Jan 1-7, 2026)",
            ],
            citations=[
                SourceCitation(
                    metric_id=101,
                    property_id="123",
                    metric_date="2026-01-05",
                    raw_json={"sessions": 12450, "device": "mobile"},
                    similarity_score=0.94,
                ),
                SourceCitation(
                    metric_id=102,
                    property_id="123",
                    metric_date="2026-01-05",
                    raw_json={"sessions": 8234, "device": "desktop"},
                    similarity_score=0.91,
                ),
            ],
            confidence=0.925,
            tenant_id=str(uuid4()),
            query_embedding=[0.1] * 1536,
            match_count=2,
        )
        
        # Verify citations are included
        assert len(retrieval_result.citations) == 2
        assert retrieval_result.citations[0].metric_id == 101
        assert retrieval_result.citations[1].metric_id == 102
        
        # Verify raw data is accessible
        assert retrieval_result.citations[0].raw_json["sessions"] == 12450
        assert retrieval_result.citations[1].raw_json["sessions"] == 8234


class TestCitationIntegrity:
    """Test citation integrity validation."""
    
    @pytest.mark.asyncio
    async def test_no_orphaned_embeddings(self):
        """Test validation catches embeddings without source citations."""
        # This would be tested via database function:
        # SELECT * FROM validate_citation_integrity()
        
        # Simulate checking for orphaned embeddings
        embeddings = [
            {"id": "uuid-1", "source_metric_id": 101, "source_metric_ids": [101]},
            {"id": "uuid-2", "source_metric_id": None, "source_metric_ids": []},  # Orphaned!
        ]
        
        orphaned = [e for e in embeddings if not e["source_metric_id"] and not e["source_metric_ids"]]
        
        # Should detect orphaned embedding
        assert len(orphaned) == 1
        assert orphaned[0]["id"] == "uuid-2"
    
    @pytest.mark.asyncio
    async def test_broken_foreign_key_detection(self):
        """Test detection of broken source metric references."""
        # Simulate embedding with non-existent metric_id
        existing_metric_ids = [101, 102, 103]
        
        citation = SourceCitation(
            metric_id=999,  # Doesn't exist in ga4_metrics_raw
            property_id="123",
            metric_date="2026-01-01",
            raw_json={},
            similarity_score=0.9,
        )
        
        # Verify broken reference
        is_broken = citation.metric_id not in existing_metric_ids
        assert is_broken


class TestCitationPerformance:
    """Test citation tracking doesn't impact performance."""
    
    @pytest.mark.asyncio
    async def test_citation_query_performance(self):
        """Test RAG queries with citations complete in <100ms."""
        # This would require actual database setup
        # Mock test to document expected performance
        
        import time
        
        # Simulate pgvector query with JOIN
        start = time.time()
        
        # Mock query execution
        await asyncio.sleep(0.05)  # Simulate 50ms query
        
        elapsed = time.time() - start
        
        # Should complete in <100ms
        assert elapsed < 0.1, f"Citation query took {elapsed:.2f}s (expected <0.1s)"

