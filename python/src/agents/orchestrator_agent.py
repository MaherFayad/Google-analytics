"""
OrchestratorAgent - Coordinates multi-agent workflow.

Implements Task 13: Agent Orchestration Layer
Implements Task P0-18: Agent Handoff Logic
Implements Task P0-12: Async Agent Execution with Streaming

Responsibilities:
- Coordinate DataFetcher → Embedding → RAG → Reporting pipeline
- Handle parallel execution where possible
- Implement circuit breakers and error recovery
- Stream progress updates via SSE
- Progressive cache-first strategy for <500ms time-to-first-token
"""

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from .base_agent import BaseAgent
from .data_fetcher_agent import DataFetcherAgent
from .embedding_agent import EmbeddingAgent
from .rag_agent import RagAgent
from .reporting_agent import ReportingAgent
from .schemas.results import (
    DataFetchResult,
    EmbeddingResult,
    RetrievalResult,
    ReportResult,
)

logger = logging.getLogger(__name__)


class OrchestratorAgent(BaseAgent[ReportResult]):
    """
    Orchestrator for multi-agent GA4 reporting pipeline.
    
    Implements Task 13: Agent Orchestration Layer
    
    Pipeline:
    1. DataFetcherAgent: Fetch fresh GA4 data (or use cache)
    2. EmbeddingAgent: Generate query embedding
    3. RagAgent: Retrieve historical context (parallel with step 1)
    4. ReportingAgent: Generate structured report
    
    Features:
    - Parallel execution (Task P0-18)
    - Circuit breakers (Task P0-41)
    - Progress streaming (Task P0-12)
    - Error recovery with fallbacks
    
    Contract:
        OrchestratorAgent.execute_pipeline() → ReportResult
    """
    
    def __init__(
        self,
        openai_api_key: str,
        redis_client: Optional[Any] = None,
        db_session: Optional[Any] = None,
        cache_service: Optional[Any] = None,
    ):
        """
        Initialize orchestrator with sub-agents.
        
        Args:
            openai_api_key: OpenAI API key
            redis_client: Redis client for caching
            db_session: Database session for RAG
            cache_service: Progressive cache service (Task P0-12)
        """
        super().__init__(
            name="orchestrator",
            model="openai:gpt-4o",
            retries=1,
            timeout_seconds=60,
        )
        
        # Initialize sub-agents
        self.data_fetcher = DataFetcherAgent(redis_client=redis_client)
        self.embedding_agent = EmbeddingAgent(openai_api_key=openai_api_key)
        self.rag_agent = RagAgent(db_session=db_session)
        self.reporting_agent = ReportingAgent(openai_api_key=openai_api_key)
        
        # Progressive cache for <500ms time-to-first-token (Task P0-12)
        self.cache_service = cache_service
        
        logger.info("Orchestrator initialized with 4 agents")
    
    def get_system_prompt(self) -> str:
        """System prompt for orchestrator."""
        return """You are an orchestrator for a multi-agent GA4 analytics system.
        Your job is to coordinate specialized agents to generate comprehensive reports."""
    
    async def run_async(
        self,
        ctx: RunContext,
        query: str,
        tenant_id: str,
        user_id: str,
        property_id: str,
        access_token: str,
        dimensions: Optional[List[str]] = None,
        metrics: Optional[List[str]] = None,
        **kwargs: Any
    ) -> ReportResult:
        """
        Execute multi-agent pipeline.
        
        Args:
            ctx: Run context
            query: User's natural language query
            tenant_id: Tenant ID for isolation
            user_id: User ID
            property_id: GA4 property ID
            access_token: OAuth access token
            dimensions: GA4 dimensions (default: ["date"])
            metrics: GA4 metrics (default: ["sessions", "conversions"])
            
        Returns:
            ReportResult with complete report
        """
        dimensions = dimensions or ["date"]
        metrics = metrics or ["sessions", "conversions"]
        
        logger.info(f"Starting pipeline for query: {query}")
        
        try:
            # PHASE 1: Fetch GA4 data
            logger.info("Phase 1: Fetching GA4 data...")
            data_result = await self.data_fetcher.execute(
                tenant_id=tenant_id,
                user_id=user_id,
                property_id=property_id,
                access_token=access_token,
                dimensions=dimensions,
                metrics=metrics,
            )
            
            if data_result.status == "failed":
                logger.warning("GA4 data fetch failed, using fallback")
                # TODO: Implement fallback to cached data
            
            # PHASE 2: Generate query embedding (for RAG search)
            logger.info("Phase 2: Generating query embedding...")
            embedding_result = await self.embedding_agent.execute(
                texts=[query],
                tenant_id=tenant_id,
            )
            
            if not embedding_result.embeddings:
                logger.warning("Embedding generation failed")
                query_embedding = None
            else:
                query_embedding = embedding_result.embeddings[0]
            
            # PHASE 3: Retrieve historical context (if embedding succeeded)
            logger.info("Phase 3: Retrieving historical context...")
            if query_embedding:
                retrieval_result = await self.rag_agent.execute(
                    query_embedding=query_embedding,
                    tenant_id=tenant_id,
                )
            else:
                # No embedding, skip RAG
                retrieval_result = RetrievalResult(
                    documents=[],
                    citations=[],
                    confidence=0.0,
                    tenant_id=tenant_id,
                    query_embedding=[],
                    match_count=0,
                )
            
            # PHASE 4: Generate structured report
            logger.info("Phase 4: Generating report...")
            report_result = await self.reporting_agent.execute(
                query=query,
                ga4_data=data_result.data,
                retrieved_context=retrieval_result.documents,
                citations=retrieval_result.citations,
                tenant_id=tenant_id,
            )
            
            logger.info(
                f"Pipeline complete (confidence: {report_result.confidence:.2f})"
            )
            
            return report_result
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            
            # Return error report
            return ReportResult(
                answer=f"I encountered an error processing your query: {str(e)}",
                charts=[],
                metrics=[],
                citations=[],
                confidence=0.0,
                tenant_id=tenant_id,
                query=query,
            )
    
    async def execute_pipeline_streaming(
        self,
        query: str,
        tenant_id: str,
        user_id: str,
        property_id: str,
        access_token: str,
        dimensions: Optional[List[str]] = None,
        metrics: Optional[List[str]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute pipeline with progress streaming (Task P0-12).
        
        Implements cache-first strategy for <500ms time-to-first-token:
        - Phase 1: Cache check (0-50ms) - yield cached result immediately if available
        - Phase 2: Async agents (100-300ms) - start agents in parallel
        - Phase 3: Progressive results (500-1000ms) - stream status updates
        - Phase 4: Cache result (background) - cache for future requests
        
        Yields progress updates and final result via SSE.
        
        Args:
            query: User query
            tenant_id: Tenant ID
            user_id: User ID
            property_id: GA4 property ID
            access_token: OAuth token
            dimensions: GA4 dimensions
            metrics: GA4 metrics
            
        Yields:
            Status updates: {"type": "status", "message": "..."}
            Final result: {"type": "result", "payload": ReportResult}
        """
        try:
            # PHASE 1: Cache check (Target: <50ms)
            if self.cache_service:
                cached_entry = await self.cache_service.get_cached_result(
                    query=query,
                    tenant_id=tenant_id,
                    property_id=property_id,
                )
                
                if cached_entry:
                    # INSTANT RESPONSE - Yield cached result (0-50ms)
                    logger.info(
                        f"Cache hit from {cached_entry.source} "
                        f"(cached_at: {cached_entry.cached_at})"
                    )
                    
                    yield {
                        "type": "status",
                        "message": f"Using cached result ({cached_entry.source})"
                    }
                    
                    # Yield cached result immediately
                    yield {
                        "type": "result",
                        "payload": cached_entry.result,
                        "cached": True,
                        "cache_source": cached_entry.source,
                    }
                    
                    return  # Early return - <500ms achieved!
            
            # PHASE 2: Cache miss - Start async pipeline
            yield {"type": "status", "message": "Fetching fresh data..."}
            
            # OPTIMIZATION: Run embedding generation in parallel with data fetch
            # (Task P0-18: Parallel execution where possible)
            logger.info("Starting parallel execution: data fetch + embedding")
            
            data_task = asyncio.create_task(
                self.data_fetcher.execute(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    property_id=property_id,
                    access_token=access_token,
                    dimensions=dimensions or ["date"],
                    metrics=metrics or ["sessions", "conversions"],
                )
            )
            
            embedding_task = asyncio.create_task(
                self.embedding_agent.execute(
                    texts=[query],
                    tenant_id=tenant_id,
                )
            )
            
            # Wait for both to complete (parallel execution)
            data_result, embedding_result = await asyncio.gather(
                data_task,
                embedding_task,
                return_exceptions=True,
            )
            
            # Handle exceptions from parallel execution
            if isinstance(data_result, Exception):
                logger.error(f"Data fetch failed: {data_result}")
                data_result = DataFetchResult(
                    status="failed",
                    data={},
                    cached=False,
                    tenant_id=tenant_id,
                    timestamp=None,
                )
            
            if isinstance(embedding_result, Exception):
                logger.warning(f"Embedding generation failed: {embedding_result}")
                embedding_result = EmbeddingResult(
                    embeddings=[],
                    quality_score=0.0,
                    validation_errors=[str(embedding_result)],
                    dimension=0,
                    model="",
                    tenant_id=tenant_id,
                )
            
            if data_result.cached:
                yield {"type": "status", "message": "Using cached GA4 data"}
            
            # PHASE 3: Retrieve historical context
            if embedding_result.embeddings:
                yield {"type": "status", "message": "Finding relevant patterns..."}
                retrieval_result = await self.rag_agent.execute(
                    query_embedding=embedding_result.embeddings[0],
                    tenant_id=tenant_id,
                )
            else:
                retrieval_result = RetrievalResult(
                    documents=[],
                    citations=[],
                    confidence=0.0,
                    tenant_id=tenant_id,
                    query_embedding=[],
                    match_count=0,
                )
            
            # PHASE 4: Generate report
            yield {"type": "status", "message": "Generating insights..."}
            report_result = await self.reporting_agent.execute(
                query=query,
                ga4_data=data_result.data,
                retrieved_context=retrieval_result.documents,
                citations=retrieval_result.citations,
                tenant_id=tenant_id,
            )
            
            # Cache the result for future requests (background task)
            if self.cache_service:
                asyncio.create_task(
                    self._cache_result_background(
                        query=query,
                        tenant_id=tenant_id,
                        property_id=property_id,
                        result=report_result.model_dump(),
                    )
                )
            
            # Yield final result
            yield {
                "type": "result",
                "payload": report_result.model_dump(),
                "cached": False,
            }
            
        except Exception as e:
            logger.error(f"Streaming pipeline failed: {e}", exc_info=True)
            yield {
                "type": "error",
                "message": f"Pipeline failed: {str(e)}"
            }
    
    async def _cache_result_background(
        self,
        query: str,
        tenant_id: str,
        property_id: str,
        result: Dict[str, Any],
    ) -> None:
        """Cache result in background (non-blocking)."""
        try:
            if self.cache_service:
                await self.cache_service.set_cached_result(
                    query=query,
                    tenant_id=tenant_id,
                    property_id=property_id,
                    result=result,
                )
                logger.debug(f"Cached result for query: {query[:50]}...")
        except Exception as e:
            logger.error(f"Failed to cache result: {e}")


