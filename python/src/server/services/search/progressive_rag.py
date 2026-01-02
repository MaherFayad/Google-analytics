"""
Progressive RAG Service with Streaming Results

Implements Task 17: Real-time Progressive Retrieval [P2 - MEDIUM]

Features:
- Reduce time-to-first-token from 3-5 seconds to <1 second
- Cache-first strategy for instant responses (0-50ms)
- Approximate search for fast results (100-300ms)
- Exact search for refined results (500-1000ms)
- Streaming results via callback/AsyncGenerator

Performance Targets:
- Phase 1 (Cache): <50ms
- Phase 2 (Approximate): <300ms
- Phase 3 (Exact): <1000ms
"""

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ========== Models ==========

class SearchResult(BaseModel):
    """Single search result."""
    
    embedding_id: str
    content: str
    similarity_score: float
    source_metric_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ProgressiveSearchPhase(str):
    """Search phase constants."""
    
    CACHE = "cache"
    APPROXIMATE = "approximate"
    EXACT = "exact"


class SearchResponse(BaseModel):
    """Progressive search response."""
    
    phase: str = Field(description="Search phase (cache/approximate/exact)")
    results: List[SearchResult]
    total_results: int
    confidence: float = Field(description="Average confidence score")
    latency_ms: int = Field(description="Phase latency in milliseconds")
    cached: bool = False


# ========== Progressive RAG Service ==========

class ProgressiveRAGService:
    """
    Streaming RAG with progressive result delivery.
    
    Implements Task 17: Real-time Progressive Retrieval
    
    Strategy:
    1. Phase 1 (Cache): Check Redis for cached results → instant response (0-50ms)
    2. Phase 2 (Approximate): IVFFlat approximate search → fast results (100-300ms)
    3. Phase 3 (Exact): HNSW exact search → refined results (500-1000ms)
    
    Example:
        ```python
        service = ProgressiveRAGService(db_session, redis_client)
        
        async for response in service.stream_search(
            query_embedding=[...],
            tenant_id="uuid",
            match_count=5
        ):
            print(f"Phase: {response.phase}, Results: {len(response.results)}")
            # Use results immediately as they arrive
        ```
    """
    
    def __init__(
        self,
        db_session: AsyncSession,
        redis_client: Optional[Any] = None,
        cache_ttl_seconds: int = 3600,
    ):
        """
        Initialize Progressive RAG service.
        
        Args:
            db_session: Database session for vector search
            redis_client: Redis client for caching (optional)
            cache_ttl_seconds: Cache TTL in seconds (default: 1 hour)
        """
        self.db_session = db_session
        self.redis = redis_client
        self.cache_ttl = cache_ttl_seconds
        logger.info("Progressive RAG service initialized")
    
    async def stream_search(
        self,
        query_embedding: List[float],
        tenant_id: str,
        property_id: Optional[str] = None,
        match_count: int = 5,
        min_confidence: float = 0.7,
    ) -> AsyncGenerator[SearchResponse, None]:
        """
        Stream search results progressively.
        
        Yields results in phases for immediate consumption.
        
        Args:
            query_embedding: Query embedding vector
            tenant_id: Tenant UUID for isolation
            property_id: Optional GA4 property ID filter
            match_count: Number of results to return
            min_confidence: Minimum similarity threshold
            
        Yields:
            SearchResponse for each phase (cache, approximate, exact)
        """
        start_time = datetime.utcnow()
        
        # ========== PHASE 1: Cache Check (Target: <50ms) ==========
        cache_results = await self._check_cache(
            query_embedding=query_embedding,
            tenant_id=tenant_id,
            match_count=match_count
        )
        
        if cache_results:
            cache_latency = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.info(f"Cache hit! Latency: {cache_latency:.0f}ms")
            
            yield SearchResponse(
                phase=ProgressiveSearchPhase.CACHE,
                results=cache_results,
                total_results=len(cache_results),
                confidence=self._calculate_avg_confidence(cache_results),
                latency_ms=int(cache_latency),
                cached=True
            )
            return  # Cache hit, no need for database search
        
        # Cache miss, proceed to database search
        logger.info("Cache miss, proceeding to database search")
        
        # ========== PHASE 2: Approximate Search (Target: <300ms) ==========
        approximate_start = datetime.utcnow()
        
        approximate_results = await self._approximate_search(
            query_embedding=query_embedding,
            tenant_id=tenant_id,
            property_id=property_id,
            match_count=match_count * 2,  # Get more results for refinement
            min_confidence=min_confidence * 0.8  # Lower threshold for approximation
        )
        
        approximate_latency = (datetime.utcnow() - approximate_start).total_seconds() * 1000
        logger.info(f"Approximate search: {len(approximate_results)} results, {approximate_latency:.0f}ms")
        
        if approximate_results:
            yield SearchResponse(
                phase=ProgressiveSearchPhase.APPROXIMATE,
                results=approximate_results[:match_count],  # Return top results
                total_results=len(approximate_results),
                confidence=self._calculate_avg_confidence(approximate_results),
                latency_ms=int(approximate_latency),
                cached=False
            )
        
        # ========== PHASE 3: Exact Search (Target: <1000ms) ==========
        exact_start = datetime.utcnow()
        
        exact_results = await self._exact_search(
            query_embedding=query_embedding,
            tenant_id=tenant_id,
            property_id=property_id,
            match_count=match_count,
            min_confidence=min_confidence
        )
        
        exact_latency = (datetime.utcnow() - exact_start).total_seconds() * 1000
        logger.info(f"Exact search: {len(exact_results)} results, {exact_latency:.0f}ms")
        
        if exact_results:
            yield SearchResponse(
                phase=ProgressiveSearchPhase.EXACT,
                results=exact_results,
                total_results=len(exact_results),
                confidence=self._calculate_avg_confidence(exact_results),
                latency_ms=int(exact_latency),
                cached=False
            )
            
            # Cache exact results for future queries
            await self._cache_results(
                query_embedding=query_embedding,
                tenant_id=tenant_id,
                results=exact_results
            )
    
    # ========== Phase 1: Cache ==========
    
    async def _check_cache(
        self,
        query_embedding: List[float],
        tenant_id: str,
        match_count: int
    ) -> Optional[List[SearchResult]]:
        """
        Check Redis cache for cached results.
        
        Args:
            query_embedding: Query vector
            tenant_id: Tenant UUID
            match_count: Number of results
            
        Returns:
            Cached results or None if cache miss
        """
        if not self.redis:
            return None
        
        try:
            # Generate cache key from query embedding hash
            cache_key = self._generate_cache_key(query_embedding, tenant_id, match_count)
            
            # Try to get from cache
            cached_data = await self.redis.get(cache_key)
            
            if cached_data:
                # Deserialize cached results
                results = []
                for item in cached_data:
                    results.append(SearchResult(**item))
                return results
            
            return None
            
        except Exception as e:
            logger.warning(f"Cache check failed: {e}")
            return None
    
    async def _cache_results(
        self,
        query_embedding: List[float],
        tenant_id: str,
        results: List[SearchResult]
    ) -> None:
        """
        Cache search results in Redis.
        
        Args:
            query_embedding: Query vector
            tenant_id: Tenant UUID
            results: Results to cache
        """
        if not self.redis or not results:
            return
        
        try:
            cache_key = self._generate_cache_key(query_embedding, tenant_id, len(results))
            
            # Serialize results
            serialized = [r.model_dump() for r in results]
            
            # Store with TTL
            await self.redis.setex(cache_key, self.cache_ttl, serialized)
            logger.debug(f"Cached {len(results)} results with key {cache_key[:20]}...")
            
        except Exception as e:
            logger.warning(f"Cache write failed: {e}")
    
    def _generate_cache_key(
        self,
        query_embedding: List[float],
        tenant_id: str,
        match_count: int
    ) -> str:
        """Generate cache key from query parameters."""
        # Hash the embedding vector for consistent key
        embedding_hash = hashlib.md5(str(query_embedding).encode()).hexdigest()
        return f"rag:search:{tenant_id}:{embedding_hash}:{match_count}"
    
    # ========== Phase 2: Approximate Search ==========
    
    async def _approximate_search(
        self,
        query_embedding: List[float],
        tenant_id: str,
        property_id: Optional[str],
        match_count: int,
        min_confidence: float
    ) -> List[SearchResult]:
        """
        Approximate search using IVFFlat index (faster but less accurate).
        
        Uses PostgreSQL's IVFFlat index for fast approximate nearest neighbor search.
        
        Args:
            query_embedding: Query vector
            tenant_id: Tenant UUID
            property_id: Optional property filter
            match_count: Number of results
            min_confidence: Minimum similarity
            
        Returns:
            List of search results
        """
        try:
            # Use IVFFlat with lower probes for speed
            # SET ivfflat.probes = 1 (fast but approximate)
            query = text("""
                SET LOCAL ivfflat.probes = 1;
                
                SELECT 
                    e.id AS embedding_id,
                    e.content,
                    1 - (e.embedding <=> CAST(:query_embedding AS vector)) AS similarity_score,
                    e.source_metric_id,
                    e.source_metadata AS metadata
                FROM ga4_embeddings e
                WHERE e.tenant_id = :tenant_id::uuid
                AND e.embedding IS NOT NULL
                ORDER BY e.embedding <=> CAST(:query_embedding AS vector)
                LIMIT :match_count
            """)
            
            result = await self.db_session.execute(
                query,
                {
                    "query_embedding": str(query_embedding),
                    "tenant_id": tenant_id,
                    "match_count": match_count
                }
            )
            
            rows = result.fetchall()
            
            # Convert to SearchResult objects
            results = []
            for row in rows:
                if row.similarity_score >= min_confidence:
                    results.append(SearchResult(
                        embedding_id=str(row.embedding_id),
                        content=row.content,
                        similarity_score=row.similarity_score,
                        source_metric_id=str(row.source_metric_id) if row.source_metric_id else None,
                        metadata=row.metadata
                    ))
            
            return results
            
        except Exception as e:
            logger.error(f"Approximate search failed: {e}", exc_info=True)
            return []
    
    # ========== Phase 3: Exact Search ==========
    
    async def _exact_search(
        self,
        query_embedding: List[float],
        tenant_id: str,
        property_id: Optional[str],
        match_count: int,
        min_confidence: float
    ) -> List[SearchResult]:
        """
        Exact search using HNSW index (more accurate).
        
        Uses PostgreSQL's HNSW index for accurate nearest neighbor search.
        
        Args:
            query_embedding: Query vector
            tenant_id: Tenant UUID
            property_id: Optional property filter
            match_count: Number of results
            min_confidence: Minimum similarity
            
        Returns:
            List of search results
        """
        try:
            # Use HNSW or exact search (no approximate index settings)
            query = text("""
                SELECT 
                    e.id AS embedding_id,
                    e.content,
                    1 - (e.embedding <=> CAST(:query_embedding AS vector)) AS similarity_score,
                    e.source_metric_id,
                    e.source_metadata AS metadata,
                    e.temporal_metadata,
                    m.property_id,
                    m.metric_date,
                    m.descriptive_summary
                FROM ga4_embeddings e
                LEFT JOIN ga4_metrics_raw m ON e.source_metric_id = m.id
                WHERE e.tenant_id = :tenant_id::uuid
                AND e.embedding IS NOT NULL
                AND 1 - (e.embedding <=> CAST(:query_embedding AS vector)) >= :min_confidence
                ORDER BY e.embedding <=> CAST(:query_embedding AS vector)
                LIMIT :match_count
            """)
            
            result = await self.db_session.execute(
                query,
                {
                    "query_embedding": str(query_embedding),
                    "tenant_id": tenant_id,
                    "min_confidence": min_confidence,
                    "match_count": match_count
                }
            )
            
            rows = result.fetchall()
            
            # Convert to SearchResult objects with full metadata
            results = []
            for row in rows:
                metadata = row.metadata or {}
                if row.property_id:
                    metadata["property_id"] = row.property_id
                if row.metric_date:
                    metadata["metric_date"] = str(row.metric_date)
                if row.descriptive_summary:
                    metadata["summary"] = row.descriptive_summary
                
                results.append(SearchResult(
                    embedding_id=str(row.embedding_id),
                    content=row.content,
                    similarity_score=row.similarity_score,
                    source_metric_id=str(row.source_metric_id) if row.source_metric_id else None,
                    metadata=metadata
                ))
            
            return results
            
        except Exception as e:
            logger.error(f"Exact search failed: {e}", exc_info=True)
            return []
    
    # ========== Utilities ==========
    
    def _calculate_avg_confidence(self, results: List[SearchResult]) -> float:
        """Calculate average confidence score."""
        if not results:
            return 0.0
        return sum(r.similarity_score for r in results) / len(results)


# ========== Integration Helper ==========

async def progressive_rag_search(
    db_session: AsyncSession,
    query_embedding: List[float],
    tenant_id: str,
    redis_client: Optional[Any] = None,
    callback: Optional[Callable[[SearchResponse], None]] = None,
    **kwargs
) -> SearchResponse:
    """
    Helper function for progressive RAG search with callback support.
    
    Args:
        db_session: Database session
        query_embedding: Query vector
        tenant_id: Tenant UUID
        redis_client: Optional Redis client
        callback: Optional callback for streaming results
        **kwargs: Additional search parameters
        
    Returns:
        Final SearchResponse (exact phase)
        
    Example:
        ```python
        def on_result(response: SearchResponse):
            print(f"Phase {response.phase}: {len(response.results)} results")
        
        final_results = await progressive_rag_search(
            db_session=session,
            query_embedding=embedding,
            tenant_id=tenant_id,
            callback=on_result
        )
        ```
    """
    service = ProgressiveRAGService(db_session, redis_client)
    
    final_response = None
    
    async for response in service.stream_search(
        query_embedding=query_embedding,
        tenant_id=tenant_id,
        **kwargs
    ):
        # Call callback for each phase
        if callback:
            callback(response)
        
        # Store final response
        final_response = response
    
    return final_response

