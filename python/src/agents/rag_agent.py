"""
RagAgent - Retrieves context using vector similarity search.

Implements Task P0-1: RagAgent
Enhanced with Task P0-19: RAG Retrieval Confidence Filtering

Responsibilities:
- Perform vector similarity search with pgvector
- Enforce tenant isolation (Task P0-2)
- Return relevant documents with citations
- Filter by confidence threshold with status levels (Task P0-19)
"""

import logging
from typing import Any, List, Optional

from pydantic_ai import RunContext
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .base_agent import BaseAgent
from .schemas.results import RetrievalResult, SourceCitation

logger = logging.getLogger(__name__)

# Import monitoring (optional, for production)
try:
    from ..server.monitoring.metrics import record_rag_retrieval
    MONITORING_ENABLED = True
except ImportError:
    MONITORING_ENABLED = False
    logger.warning("Monitoring not available, RAG metrics disabled")


class RagAgent(BaseAgent[RetrievalResult]):
    """
    Agent for RAG retrieval with tenant filtering.
    
    Implements Task P0-1: RagAgent
    
    Features:
    - pgvector similarity search
    - Tenant isolation enforcement
    - Confidence-based filtering (Task P0-19)
    - Source citation tracking (Task P0-42)
    
    Contract:
        RagAgent.retrieve() → RetrievalResult(documents, confidence)
    """
    
    CONFIDENCE_THRESHOLD = 0.7  # Task P0-19: Minimum similarity score
    
    def __init__(self, db_session: Optional[AsyncSession] = None):
        """
        Initialize RAG agent.
        
        Args:
            db_session: Database session for vector search
        """
        super().__init__(
            name="rag",
            model="openai:gpt-4o",
            retries=2,
            timeout_seconds=10,
        )
        self.db_session = db_session
    
    def get_system_prompt(self) -> str:
        """System prompt for RAG agent."""
        return """You are a retrieval specialist for finding relevant GA4 metrics.
        Your job is to find the most relevant historical data for user queries."""
    
    async def run_async(
        self,
        ctx: RunContext,
        query_embedding: List[float],
        tenant_id: str,
        match_count: int = 5,
        min_confidence: Optional[float] = None,
        **kwargs: Any
    ) -> RetrievalResult:
        """
        Retrieve relevant documents using vector search.
        
        Args:
            ctx: Run context
            query_embedding: Query vector (1536-dim)
            tenant_id: Tenant ID for isolation
            match_count: Number of results to return
            min_confidence: Minimum similarity threshold (default: 0.7)
            
        Returns:
            RetrievalResult with documents and citations
        """
        min_confidence = min_confidence or self.CONFIDENCE_THRESHOLD
        
        try:
            logger.info(
                f"RAG search: tenant={tenant_id}, matches={match_count}, threshold={min_confidence}"
            )
            
            # Task P0-42: Source Citation Tracking Implementation
            # Join ga4_embeddings with ga4_metrics_raw to get full provenance
            
            if self.db_session:
                # Production pgvector query with source citations
                query_sql = text("""
                    WITH ranked_results AS (
                        SELECT 
                            e.id AS embedding_id,
                            e.content AS embedding_content,
                            e.embedding <=> CAST(:query_embedding AS vector) AS distance,
                            1 - (e.embedding <=> CAST(:query_embedding AS vector)) AS similarity_score,
                            e.source_metric_id,
                            e.source_metadata,
                            e.temporal_metadata,
                            e.transformation_version,
                            -- Join with source metrics for full provenance
                            m.id AS metric_id,
                            m.property_id,
                            m.metric_date,
                            m.event_name,
                            m.dimension_context AS metric_dimensions,
                            m.metric_values,
                            m.descriptive_summary
                        FROM ga4_embeddings e
                        LEFT JOIN ga4_metrics_raw m ON e.source_metric_id = m.id
                        WHERE e.tenant_id = :tenant_id::uuid
                        AND e.embedding IS NOT NULL
                        ORDER BY e.embedding <=> CAST(:query_embedding AS vector)
                        LIMIT :match_count
                    )
                    SELECT * FROM ranked_results
                    WHERE similarity_score >= :min_confidence
                """)
                
                result = await self.db_session.execute(
                    query_sql,
                    {
                        "query_embedding": str(query_embedding),
                        "tenant_id": tenant_id,
                        "match_count": match_count * 2,  # Fetch extra, filter by confidence
                        "min_confidence": min_confidence,
                    }
                )
                
                rows = result.fetchall()
                
                documents = []
                citations = []
                
                for row in rows:
                    documents.append(row.embedding_content)
                    
                    # Create source citation
                    citation = SourceCitation(
                        metric_id=row.metric_id or 0,
                        property_id=row.property_id or "unknown",
                        metric_date=row.metric_date.isoformat() if row.metric_date else "unknown",
                        raw_json=row.metric_values or {},
                        similarity_score=row.similarity_score,
                    )
                    citations.append(citation)
                
                # Calculate average confidence and determine status (Task P0-19)
                avg_confidence = (
                    sum(c.similarity_score for c in citations) / len(citations)
                    if citations else 0.0
                )
                
                # Determine confidence status
                status = self._get_confidence_status(avg_confidence, min_confidence)
                
                # Count filtered results
                filtered_count = match_count * 2 - len(rows)
                total_found = match_count * 2
                
                logger.info(
                    f"RAG retrieved {len(documents)} documents from DB "
                    f"(confidence: {avg_confidence:.2f}, status: {status}, "
                    f"filtered: {filtered_count}/{total_found})"
                )
                
                # Record monitoring metrics (Task P0-19)
                if MONITORING_ENABLED:
                    record_rag_retrieval(tenant_id, avg_confidence, status, filtered_count)
                
            else:
                # Mock results for testing (when db_session not available)
                logger.warning("No DB session, using mock RAG results")
                
                documents = [
                    "Mobile conversions increased 21.7% last week (Jan 1-7, 2025)",
                    "Desktop sessions decreased 5.2% over the same period",
                    "Bounce rate on mobile improved from 45% to 42%",
                ]
                
                citations = [
                    SourceCitation(
                        metric_id=1,
                        property_id="123456789",
                        metric_date="2025-01-01",
                        raw_json={"sessions": 1234, "conversions": 56},
                        similarity_score=0.92,
                    ),
                    SourceCitation(
                        metric_id=2,
                        property_id="123456789",
                        metric_date="2025-01-02",
                        raw_json={"sessions": 1456, "conversions": 62},
                        similarity_score=0.87,
                    ),
                    SourceCitation(
                        metric_id=3,
                        property_id="123456789",
                        metric_date="2025-01-03",
                        raw_json={"bounce_rate": 0.42},
                        similarity_score=0.81,
                    ),
                ]
                
                avg_confidence = sum(c.similarity_score for c in citations) / len(citations)
                status = self._get_confidence_status(avg_confidence, min_confidence)
                filtered_count = 0
                total_found = len(documents)
                
                # Record monitoring metrics (Task P0-19)
                if MONITORING_ENABLED:
                    record_rag_retrieval(tenant_id, avg_confidence, status, filtered_count)
            
            return RetrievalResult(
                documents=documents,
                citations=citations,
                confidence=avg_confidence,
                status=status,
                filtered_count=filtered_count,
                total_found=total_found,
                tenant_id=tenant_id,
                query_embedding=query_embedding,
                match_count=len(documents),
            )
            
        except Exception as e:
            logger.error(f"RAG retrieval failed: {e}", exc_info=True)
            
            # Return empty result on failure
            return RetrievalResult(
                documents=[],
                citations=[],
                confidence=0.0,
                status="no_relevant_context",
                filtered_count=0,
                total_found=0,
                tenant_id=tenant_id,
                query_embedding=query_embedding,
                match_count=0,
            )
    
    def _get_confidence_status(
        self,
        confidence: float,
        threshold: float
    ) -> str:
        """
        Determine confidence status level (Task P0-19).
        
        Args:
            confidence: Average similarity score
            threshold: Current threshold
            
        Returns:
            Confidence status: high_confidence, medium_confidence,
            low_confidence, or no_relevant_context
        """
        # Configurable thresholds (from Settings in production)
        HIGH_THRESHOLD = 0.85
        MEDIUM_THRESHOLD = 0.70
        LOW_THRESHOLD = 0.50
        
        if confidence >= HIGH_THRESHOLD:
            return "high_confidence"
        elif confidence >= MEDIUM_THRESHOLD:
            return "medium_confidence"
        elif confidence >= LOW_THRESHOLD:
            return "low_confidence"
        else:
            return "no_relevant_context"

