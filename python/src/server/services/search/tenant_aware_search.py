"""
Tenant-aware vector search service.

Implements Task 11: Multi-Tenant Security Foundation

This service ensures all vector searches respect tenant isolation:
1. All queries filtered by tenant_id (enforced by RLS policies)
2. No cross-tenant data leakage in vector similarity results
3. Integrates with HNSW index for fast, isolated search
4. Validates tenant context before executing queries

CRITICAL SECURITY: Task P0-3 proves these queries respect RLS policies
"""

import logging
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
import numpy as np

from ...models.chat import ChatSession, ChatMessage
from ...database import async_session_maker

logger = logging.getLogger(__name__)


class TenantAwareSearchService:
    """
    Tenant-aware vector similarity search.
    
    All searches are automatically filtered by tenant_id via RLS policies.
    Implements Task 11 security requirements.
    """
    
    def __init__(self):
        """Initialize tenant-aware search service."""
        logger.info("TenantAwareSearchService initialized")
    
    async def search_similar_patterns(
        self,
        query_embedding: List[float],
        tenant_id: UUID,
        user_id: UUID,
        match_count: int = 5,
        temporal_filter: Optional[Dict[str, Any]] = None,
        ef_search: int = 40,
        session: Optional[AsyncSession] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar GA4 patterns using vector similarity.
        
        SECURITY: Automatically filtered by tenant_id via RLS policies (Task 7.4).
        Task P0-3 validates this prevents cross-tenant leakage.
        
        Args:
            query_embedding: 1536-dim vector from OpenAI
            tenant_id: Tenant UUID (CRITICAL: Must match current session)
            user_id: User UUID
            match_count: Number of results to return
            temporal_filter: Optional JSONB filter for time-series context
            ef_search: HNSW search accuracy (default: 40)
            session: Optional database session
            
        Returns:
            List of similar patterns with similarity scores
            
        Raises:
            ValueError: If embedding dimensions incorrect
            RuntimeError: If database query fails
            
        Example:
            results = await search_service.search_similar_patterns(
                query_embedding=[0.123, 0.456, ...],  # 1536 dims
                tenant_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
                user_id=UUID("123e4567-e89b-12d3-a456-426614174001"),
                match_count=10,
                temporal_filter={"metric_type": "conversion_rate"}
            )
        """
        # Validate embedding dimensions
        if len(query_embedding) != 1536:
            raise ValueError(
                f"Invalid embedding dimensions. Expected 1536, got {len(query_embedding)}"
            )
        
        # Convert to numpy array for validation
        embedding_array = np.array(query_embedding)
        
        # Check for NaN or Inf values (Task P0-16: Embedding Dimension Validation)
        if np.isnan(embedding_array).any() or np.isinf(embedding_array).any():
            raise ValueError("Embedding contains NaN or Inf values")
        
        # Check magnitude (Task P0-5: Embedding Quality Assurance)
        magnitude = np.linalg.norm(embedding_array)
        if magnitude < 0.1 or magnitude > 100.0:
            logger.warning(
                f"Embedding magnitude {magnitude} outside normal range [0.1, 100.0]"
            )
        
        # Use provided session or create new one
        own_session = False
        if session is None:
            session = async_session_maker()
            own_session = True
        
        try:
            # Set RLS context for this session
            # CRITICAL SECURITY: This ensures all queries filtered by tenant
            await session.execute(
                text("SET LOCAL app.tenant_id = :tenant_id"),
                {"tenant_id": str(tenant_id)}
            )
            await session.execute(
                text("SET LOCAL app.user_id = :user_id"),
                {"user_id": str(user_id)}
            )
            
            logger.debug(
                f"RLS context set for search: tenant={tenant_id}, user={user_id}"
            )
            
            # Prepare embedding string for pgvector
            embedding_str = f"[{','.join(map(str, query_embedding))}]"
            
            # Build query parameters
            params = {
                "query_embedding": embedding_str,
                "tenant_id": str(tenant_id),
                "user_id": str(user_id),
                "match_count": match_count,
                "ef_search": ef_search
            }
            
            # Add temporal filter if provided
            if temporal_filter:
                params["temporal_filter"] = temporal_filter
                temporal_clause = "AND ga4_embeddings.temporal_metadata @> :temporal_filter::jsonb"
            else:
                temporal_clause = ""
            
            # Call search_similar_ga4_patterns function (Task 7.4)
            # This function uses HNSW index for fast search
            # RLS policies automatically filter by tenant_id
            query = text(f"""
                SELECT * FROM search_similar_ga4_patterns(
                    p_query_embedding := :query_embedding::vector(1536),
                    p_tenant_id := :tenant_id::uuid,
                    p_user_id := :user_id::uuid,
                    p_match_count := :match_count,
                    p_temporal_filter := :temporal_filter::jsonb,
                    p_ef_search := :ef_search
                )
            """)
            
            # Execute query
            result = await session.execute(query, params)
            rows = result.fetchall()
            
            # Format results
            results = []
            for row in rows:
                results.append({
                    "id": str(row.id),
                    "content": row.content,
                    "similarity": float(row.similarity),
                    "temporal_metadata": row.temporal_metadata,
                    "source_metric_id": row.source_metric_id,
                    "created_at": row.created_at.isoformat()
                })
            
            logger.info(
                f"Vector search completed: tenant={tenant_id}, "
                f"results={len(results)}, ef_search={ef_search}"
            )
            
            return results
            
        except Exception as e:
            logger.error(
                f"Vector search failed: tenant={tenant_id}, error={e}",
                exc_info=True
            )
            raise RuntimeError(f"Vector search failed: {e}") from e
        
        finally:
            if own_session:
                await session.close()
    
    async def search_chat_history(
        self,
        query: str,
        tenant_id: UUID,
        user_id: UUID,
        limit: int = 10,
        session: Optional[AsyncSession] = None
    ) -> List[Dict[str, Any]]:
        """
        Search chat history for user within tenant.
        
        SECURITY: Automatically filtered by RLS policies (Task 7.1).
        
        Args:
            query: Search query (keyword search)
            tenant_id: Tenant UUID
            user_id: User UUID
            limit: Maximum results
            session: Optional database session
            
        Returns:
            List of matching chat sessions
        """
        own_session = False
        if session is None:
            session = async_session_maker()
            own_session = True
        
        try:
            # Set RLS context
            await session.execute(
                text("SET LOCAL app.tenant_id = :tenant_id"),
                {"tenant_id": str(tenant_id)}
            )
            await session.execute(
                text("SET LOCAL app.user_id = :user_id"),
                {"user_id": str(user_id)}
            )
            
            # Search chat sessions
            # RLS policies automatically filter by tenant_id
            stmt = select(ChatSession).where(
                ChatSession.user_id == user_id,
                ChatSession.tenant_id == str(tenant_id),
                ChatSession.title.ilike(f"%{query}%")
            ).order_by(
                ChatSession.last_message_at.desc()
            ).limit(limit)
            
            result = await session.execute(stmt)
            sessions = result.scalars().all()
            
            # Format results
            results = []
            for session_obj in sessions:
                results.append({
                    "id": str(session_obj.id),
                    "title": session_obj.title,
                    "persona": session_obj.persona,
                    "created_at": session_obj.created_at.isoformat(),
                    "updated_at": session_obj.updated_at.isoformat(),
                    "last_message_at": (
                        session_obj.last_message_at.isoformat()
                        if session_obj.last_message_at else None
                    )
                })
            
            logger.info(
                f"Chat history search completed: tenant={tenant_id}, "
                f"query='{query}', results={len(results)}"
            )
            
            return results
            
        except Exception as e:
            logger.error(
                f"Chat history search failed: tenant={tenant_id}, error={e}",
                exc_info=True
            )
            raise RuntimeError(f"Chat history search failed: {e}") from e
        
        finally:
            if own_session:
                await session.close()
    
    async def validate_tenant_isolation(
        self,
        tenant_id: UUID,
        user_id: UUID,
        session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Validate tenant isolation is working correctly.
        
        Used by Task P0-3: Vector Search Tenant Isolation Integration Test.
        
        Args:
            tenant_id: Tenant UUID
            user_id: User UUID
            session: Optional database session
            
        Returns:
            Validation results with counts
            
        Example:
            validation = await search_service.validate_tenant_isolation(
                tenant_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
                user_id=UUID("123e4567-e89b-12d3-a456-426614174001")
            )
            # {"embeddings_count": 100, "chat_sessions_count": 5, "isolated": True}
        """
        own_session = False
        if session is None:
            session = async_session_maker()
            own_session = True
        
        try:
            # Set RLS context
            await session.execute(
                text("SET LOCAL app.tenant_id = :tenant_id"),
                {"tenant_id": str(tenant_id)}
            )
            await session.execute(
                text("SET LOCAL app.user_id = :user_id"),
                {"user_id": str(user_id)}
            )
            
            # Count embeddings for this tenant
            result = await session.execute(
                text("""
                    SELECT COUNT(*) 
                    FROM ga4_embeddings 
                    WHERE tenant_id = :tenant_id AND user_id = :user_id
                """),
                {"tenant_id": str(tenant_id), "user_id": str(user_id)}
            )
            embeddings_count = result.scalar()
            
            # Count chat sessions
            result = await session.execute(
                text("""
                    SELECT COUNT(*) 
                    FROM chat_sessions 
                    WHERE tenant_id = :tenant_id::text AND user_id = :user_id
                """),
                {"tenant_id": str(tenant_id), "user_id": str(user_id)}
            )
            chat_sessions_count = result.scalar()
            
            # Verify no access to other tenants
            result = await session.execute(
                text("""
                    SELECT COUNT(*) 
                    FROM ga4_embeddings 
                    WHERE tenant_id != :tenant_id
                """),
                {"tenant_id": str(tenant_id)}
            )
            other_tenant_embeddings = result.scalar()
            
            validation_result = {
                "tenant_id": str(tenant_id),
                "user_id": str(user_id),
                "embeddings_count": int(embeddings_count),
                "chat_sessions_count": int(chat_sessions_count),
                "other_tenant_embeddings_visible": int(other_tenant_embeddings),
                "isolated": other_tenant_embeddings == 0,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            if not validation_result["isolated"]:
                logger.error(
                    f"SECURITY VIOLATION: Tenant {tenant_id} can see "
                    f"{other_tenant_embeddings} embeddings from other tenants!"
                )
            
            return validation_result
            
        except Exception as e:
            logger.error(
                f"Tenant isolation validation failed: tenant={tenant_id}, error={e}",
                exc_info=True
            )
            raise RuntimeError(f"Validation failed: {e}") from e
        
        finally:
            if own_session:
                await session.close()


# Global instance
tenant_aware_search = TenantAwareSearchService()


async def search_similar_ga4_patterns(
    query_embedding: List[float],
    tenant_id: UUID,
    user_id: UUID,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Convenience function for tenant-aware vector search.
    
    Usage:
        from server.services.search.tenant_aware_search import search_similar_ga4_patterns
        
        results = await search_similar_ga4_patterns(
            query_embedding=[0.123, ...],
            tenant_id=UUID("..."),
            user_id=UUID("..."),
            match_count=10
        )
    """
    return await tenant_aware_search.search_similar_patterns(
        query_embedding=query_embedding,
        tenant_id=tenant_id,
        user_id=user_id,
        **kwargs
    )

