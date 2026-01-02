"""
EmbeddingAgent - Generates embeddings with quality validation.

Implements Task P0-1: EmbeddingAgent

Responsibilities:
- Generate embeddings using OpenAI text-embedding-3-small
- Validate embedding quality (dimension, NaN, zero vectors)
- Handle batch processing efficiently
- Return typed EmbeddingResult
"""

import logging
from typing import Any, List, Optional

import openai
from pydantic_ai import RunContext

from .base_agent import BaseAgent
from .schemas.results import EmbeddingResult

logger = logging.getLogger(__name__)


class EmbeddingAgent(BaseAgent[EmbeddingResult]):
    """
    Agent for generating embeddings with quality validation.
    
    Implements Task P0-1: EmbeddingAgent
    
    Features:
    - OpenAI text-embedding-3-small (1536 dimensions)
    - Quality validation (Task P0-5, P0-16)
    - Batch processing support
    - Error handling and retry logic
    
    Contract:
        EmbeddingAgent.embed() → EmbeddingResult(embeddings, quality_score)
    """
    
    EXPECTED_DIMENSION = 1536
    MODEL = "text-embedding-3-small"
    
    def __init__(self, openai_api_key: str):
        """
        Initialize Embedding agent.
        
        Args:
            openai_api_key: OpenAI API key
        """
        super().__init__(
            name="embedding",
            model="openai:gpt-4o",  # Not used for embeddings
            retries=3,
            timeout_seconds=30,
        )
        self.openai_client = openai.AsyncOpenAI(api_key=openai_api_key)
    
    def get_system_prompt(self) -> str:
        """System prompt for Embedding agent."""
        return """You are an embedding generation specialist.
        Your job is to create high-quality vector embeddings for semantic search."""
    
    async def run_async(
        self,
        ctx: RunContext,
        texts: List[str],
        tenant_id: str,
        **kwargs: Any
    ) -> EmbeddingResult:
        """
        Generate embeddings for text inputs.
        
        Args:
            ctx: Run context
            texts: List of texts to embed
            tenant_id: Tenant ID for logging
            
        Returns:
            EmbeddingResult with embeddings and quality score
        """
        try:
            # Generate embeddings using OpenAI
            logger.info(f"Generating {len(texts)} embeddings for tenant {tenant_id}")
            
            response = await self.openai_client.embeddings.create(
                model=self.MODEL,
                input=texts,
                encoding_format="float",
            )
            
            # Extract embeddings
            embeddings = [item.embedding for item in response.data]
            
            # Validate quality (Task P0-16)
            validation_errors = []
            quality_score = 1.0
            
            for idx, embedding in enumerate(embeddings):
                # Check dimension
                if len(embedding) != self.EXPECTED_DIMENSION:
                    error = f"Embedding {idx}: Invalid dimension {len(embedding)}, expected {self.EXPECTED_DIMENSION}"
                    validation_errors.append(error)
                    quality_score -= 0.2
                
                # Check for NaN or Inf
                if any(not isinstance(x, (int, float)) or x != x or abs(x) == float('inf') for x in embedding):
                    error = f"Embedding {idx}: Contains NaN or Inf values"
                    validation_errors.append(error)
                    quality_score -= 0.3
                
                # Check for zero vector
                if all(x == 0 for x in embedding):
                    error = f"Embedding {idx}: Zero vector detected"
                    validation_errors.append(error)
                    quality_score -= 0.3
                
                # Check magnitude (should be normalized)
                magnitude = sum(x ** 2 for x in embedding) ** 0.5
                if magnitude < 0.1 or magnitude > 100.0:
                    error = f"Embedding {idx}: Invalid magnitude {magnitude}"
                    validation_errors.append(error)
                    quality_score -= 0.1
            
            quality_score = max(0.0, min(1.0, quality_score))
            
            if validation_errors:
                logger.warning(
                    f"Embedding quality issues: {len(validation_errors)} errors",
                    extra={"errors": validation_errors}
                )
            
            logger.info(
                f"Generated {len(embeddings)} embeddings (quality: {quality_score:.2f})"
            )
            
            return EmbeddingResult(
                embeddings=embeddings,
                quality_score=quality_score,
                validation_errors=validation_errors,
                dimension=self.EXPECTED_DIMENSION,
                model=self.MODEL,
                tenant_id=tenant_id,
            )
            
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}", exc_info=True)
            
            # Return failed result
            return EmbeddingResult(
                embeddings=[],
                quality_score=0.0,
                validation_errors=[str(e)],
                dimension=self.EXPECTED_DIMENSION,
                model=self.MODEL,
                tenant_id=tenant_id,
            )
    
    async def embed_single(
        self,
        text: str,
        tenant_id: str
    ) -> EmbeddingResult:
        """
        Generate embedding for a single text.
        
        Convenience method for single-text embedding.
        
        Args:
            text: Text to embed
            tenant_id: Tenant ID
            
        Returns:
            EmbeddingResult
        """
        return await self.run_async(None, texts=[text], tenant_id=tenant_id)  # type: ignore


