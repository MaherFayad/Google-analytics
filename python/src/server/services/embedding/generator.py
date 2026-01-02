"""
Embedding Generation Pipeline.

Implements Task 8.2: Embedding Generation Pipeline

Generates 1536-dim embeddings from GA4 descriptive summaries using OpenAI
text-embedding-3-small and stores them in ga4_embeddings table for vector search.

Features:
1. Batch processing (100 records at a time)
2. OpenAI API integration
3. Temporal metadata attachment
4. Quality validation
5. Tenant isolation
"""

import logging
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from uuid import UUID
import json

import openai
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .validator import validate_embedding, EmbeddingValidationError
from ..core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingGenerationError(Exception):
    """Raised when embedding generation fails."""
    pass


class EmbeddingGenerator:
    """
    Service to generate embeddings from GA4 descriptive text.
    
    Task 8.2 Implementation:
    - Batch processes ga4_metrics_raw records
    - Generates 1536-dim embeddings via OpenAI
    - Validates embedding quality
    - Stores in ga4_embeddings table
    """
    
    BATCH_SIZE = 100  # Process 100 records at a time
    MODEL = "text-embedding-3-small"
    DIMENSIONS = 1536
    
    def __init__(self, session: AsyncSession):
        """
        Initialize embedding generator.
        
        Args:
            session: Database session
        """
        self.session = session
        self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    
    async def generate_embeddings_for_metrics(
        self,
        tenant_id: UUID,
        user_id: UUID,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate embeddings for all unprocessed GA4 metrics.
        
        Args:
            tenant_id: Tenant UUID
            user_id: User UUID  
            limit: Optional limit on number of records to process
            
        Returns:
            Dict with processing stats
            
        Example:
            generator = EmbeddingGenerator(session)
            stats = await generator.generate_embeddings_for_metrics(
                tenant_id=UUID("..."),
                user_id=UUID("..."),
                limit=1000
            )
            # {"processed": 850, "success": 845, "failed": 5, "skipped": 150}
        """
        logger.info(
            f"Starting embedding generation: tenant={tenant_id}, limit={limit or 'no limit'}"
        )
        
        # Set RLS context
        await self.session.execute(
            text("SET LOCAL app.tenant_id = :tenant_id"),
            {"tenant_id": str(tenant_id)}
        )
        await self.session.execute(
            text("SET LOCAL app.user_id = :user_id"),
            {"user_id": str(user_id)}
        )
        
        # Get unprocessed metrics
        unprocessed = await self._get_unprocessed_metrics(
            tenant_id=tenant_id,
            limit=limit
        )
        
        if not unprocessed:
            logger.info(f"No unprocessed metrics found for tenant {tenant_id}")
            return {
                "processed": 0,
                "success": 0,
                "failed": 0,
                "skipped": 0
            }
        
        # Process in batches
        stats = {
            "processed": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0
        }
        
        for i in range(0, len(unprocessed), self.BATCH_SIZE):
            batch = unprocessed[i:i + self.BATCH_SIZE]
            batch_num = i // self.BATCH_SIZE + 1
            total_batches = (len(unprocessed) + self.BATCH_SIZE - 1) // self.BATCH_SIZE
            
            logger.info(
                f"Processing batch {batch_num}/{total_batches} "
                f"({len(batch)} records)"
            )
            
            batch_stats = await self._process_batch(
                batch=batch,
                tenant_id=tenant_id,
                user_id=user_id
            )
            
            stats["processed"] += batch_stats["processed"]
            stats["success"] += batch_stats["success"]
            stats["failed"] += batch_stats["failed"]
        
        logger.info(
            f"Embedding generation complete: tenant={tenant_id}, "
            f"processed={stats['processed']}, success={stats['success']}, "
            f"failed={stats['failed']}"
        )
        
        return stats
    
    async def _get_unprocessed_metrics(
        self,
        tenant_id: UUID,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get GA4 metrics that don't have embeddings yet.
        
        Args:
            tenant_id: Tenant UUID
            limit: Optional limit
            
        Returns:
            List of unprocessed metric records
        """
        limit_clause = f"LIMIT {limit}" if limit else ""
        
        stmt = text(f"""
            SELECT 
                m.id,
                m.tenant_id,
                m.user_id,
                m.property_id,
                m.metric_date,
                m.dimension_context,
                m.metric_values,
                m.descriptive_summary
            FROM ga4_metrics_raw m
            LEFT JOIN ga4_embeddings e ON e.source_metric_id = m.id
            WHERE m.tenant_id = :tenant_id
              AND e.id IS NULL
            ORDER BY m.metric_date DESC, m.created_at DESC
            {limit_clause}
        """)
        
        result = await self.session.execute(
            stmt,
            {"tenant_id": str(tenant_id)}
        )
        
        rows = result.fetchall()
        
        return [
            {
                "id": row.id,
                "tenant_id": row.tenant_id,
                "user_id": row.user_id,
                "property_id": row.property_id,
                "metric_date": row.metric_date,
                "dimension_context": row.dimension_context,
                "metric_values": row.metric_values,
                "descriptive_summary": row.descriptive_summary
            }
            for row in rows
        ]
    
    async def _process_batch(
        self,
        batch: List[Dict[str, Any]],
        tenant_id: UUID,
        user_id: UUID
    ) -> Dict[str, int]:
        """
        Process a batch of metrics to generate embeddings.
        
        Args:
            batch: List of metric records
            tenant_id: Tenant UUID
            user_id: User UUID
            
        Returns:
            Batch processing stats
        """
        stats = {"processed": 0, "success": 0, "failed": 0}
        
        # Extract text for embedding
        texts = [record["descriptive_summary"] for record in batch]
        
        # Generate embeddings via OpenAI
        try:
            embeddings = await self._generate_embeddings_openai(texts)
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}", exc_info=True)
            # Mark all as failed
            stats["processed"] = len(batch)
            stats["failed"] = len(batch)
            return stats
        
        # Store embeddings
        for i, record in enumerate(batch):
            stats["processed"] += 1
            
            try:
                embedding = embeddings[i]
                
                # Validate embedding (Task P0-16)
                validation_result = validate_embedding(
                    embedding,
                    strict=False,
                    model=self.MODEL
                )
                
                if not validation_result.valid:
                    logger.error(
                        f"Invalid embedding for metric {record['id']}: "
                        f"{validation_result.errors}"
                    )
                    stats["failed"] += 1
                    continue
                
                # Generate temporal metadata
                temporal_metadata = self._build_temporal_metadata(record)
                
                # Store embedding
                await self._store_embedding(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    content=record["descriptive_summary"],
                    embedding=embedding,
                    temporal_metadata=temporal_metadata,
                    source_metric_id=record["id"],
                    quality_score=self._calculate_quality_score(validation_result)
                )
                
                stats["success"] += 1
                
            except Exception as e:
                logger.error(
                    f"Failed to process metric {record['id']}: {e}",
                    exc_info=True
                )
                stats["failed"] += 1
        
        return stats
    
    async def _generate_embeddings_openai(
        self,
        texts: List[str]
    ) -> List[List[float]]:
        """
        Generate embeddings using OpenAI API.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
            
        Raises:
            EmbeddingGenerationError: If API call fails
        """
        try:
            response = await self.client.embeddings.create(
                model=self.MODEL,
                input=texts,
                dimensions=self.DIMENSIONS
            )
            
            embeddings = [item.embedding for item in response.data]
            
            logger.debug(
                f"Generated {len(embeddings)} embeddings via OpenAI "
                f"(model={self.MODEL}, dimensions={self.DIMENSIONS})"
            )
            
            return embeddings
            
        except Exception as e:
            logger.error(f"OpenAI embeddings API failed: {e}", exc_info=True)
            raise EmbeddingGenerationError(f"OpenAI API failed: {e}") from e
    
    def _build_temporal_metadata(
        self,
        record: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build temporal metadata for time-series RAG.
        
        Args:
            record: Metric record
            
        Returns:
            Temporal metadata dict
            
        Example output:
            {
                "date_range": {"start": "2025-01-05", "end": "2025-01-05"},
                "metric_type": "daily_metrics",
                "dimension_context": {"device": "mobile", "page_path": "/products"}
            }
        """
        metric_date = record["metric_date"]
        
        # Convert date to string if needed
        if isinstance(metric_date, date):
            date_str = metric_date.isoformat()
        else:
            date_str = metric_date
        
        temporal_metadata = {
            "date_range": {
                "start": date_str,
                "end": date_str
            },
            "metric_type": "daily_metrics",
            "dimension_context": record["dimension_context"],
            "property_id": record["property_id"]
        }
        
        return temporal_metadata
    
    def _calculate_quality_score(
        self,
        validation_result
    ) -> float:
        """
        Calculate quality score from validation result.
        
        Args:
            validation_result: EmbeddingValidationResult
            
        Returns:
            Quality score (0.0-1.0)
        """
        if not validation_result.valid:
            return 0.0
        
        score = 1.0
        
        # Reduce score for warnings
        score -= len(validation_result.warnings) * 0.1
        
        # Check metadata
        if "magnitude" in validation_result.metadata:
            magnitude = validation_result.metadata["magnitude"]
            # Penalize very low or very high magnitudes
            if magnitude < 0.5 or magnitude > 50.0:
                score -= 0.1
        
        if "zero_count" in validation_result.metadata:
            zero_count = validation_result.metadata["zero_count"]
            # Penalize high zero count
            if zero_count > 100:
                score -= 0.2
        
        return max(0.0, min(1.0, score))
    
    async def _store_embedding(
        self,
        tenant_id: UUID,
        user_id: UUID,
        content: str,
        embedding: List[float],
        temporal_metadata: Dict[str, Any],
        source_metric_id: int,
        quality_score: float
    ) -> int:
        """
        Store embedding in database.
        
        Args:
            tenant_id: Tenant UUID
            user_id: User UUID
            content: Original descriptive text
            embedding: 1536-dim embedding vector
            temporal_metadata: Time-series metadata
            source_metric_id: Link to source ga4_metrics_raw record
            quality_score: Embedding quality score
            
        Returns:
            Inserted embedding ID
        """
        # Convert embedding to pgvector format
        embedding_str = f"[{','.join(map(str, embedding))}]"
        
        stmt = text("""
            INSERT INTO ga4_embeddings (
                tenant_id,
                user_id,
                content,
                embedding,
                temporal_metadata,
                source_metric_id,
                embedding_model,
                embedding_dimensions,
                quality_score
            ) VALUES (
                :tenant_id,
                :user_id,
                :content,
                :embedding::vector(1536),
                :temporal_metadata::jsonb,
                :source_metric_id,
                :model,
                :dimensions,
                :quality_score
            )
            RETURNING id
        """)
        
        result = await self.session.execute(
            stmt,
            {
                "tenant_id": str(tenant_id),
                "user_id": str(user_id),
                "content": content,
                "embedding": embedding_str,
                "temporal_metadata": json.dumps(temporal_metadata),
                "source_metric_id": source_metric_id,
                "model": self.MODEL,
                "dimensions": self.DIMENSIONS,
                "quality_score": quality_score
            }
        )
        
        row = result.fetchone()
        await self.session.commit()
        
        return row.id

