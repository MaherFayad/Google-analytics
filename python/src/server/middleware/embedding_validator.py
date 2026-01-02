"""
Embedding validation middleware for FastAPI.

Implements Task P0-16: Embedding Dimension Validation Middleware

This middleware intercepts requests containing embeddings and validates them
before they reach the database. Prevents pgvector crashes from dimension mismatches.

Usage:
    from server.middleware.embedding_validator import EmbeddingValidationMiddleware
    
    app.add_middleware(EmbeddingValidationMiddleware, enforce=True)
"""

import logging
from typing import Callable, Dict, Any
import json

from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware

from ..services.embedding import validate_embedding, EmbeddingValidationError

logger = logging.getLogger(__name__)


class EmbeddingValidationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to validate embeddings in API requests.
    
    Automatically validates embedding vectors in request bodies
    before they reach database operations.
    
    Task P0-16 Implementation:
    - Intercepts requests with embeddings
    - Validates dimensions, NaN/Inf, zero vectors
    - Returns 400 Bad Request on validation failure
    - Logs validation errors for debugging
    """
    
    # Endpoints that handle embeddings
    EMBEDDING_ENDPOINTS = {
        "/api/v1/embeddings/generate",
        "/api/v1/embeddings/store",
        "/api/v1/analytics/embed",
    }
    
    # JSON keys that might contain embeddings
    EMBEDDING_KEYS = {"embedding", "embeddings", "vector", "vectors"}
    
    def __init__(self, app, enforce: bool = True):
        """
        Initialize embedding validation middleware.
        
        Args:
            app: FastAPI application
            enforce: Whether to enforce validation (reject invalid embeddings)
        """
        super().__init__(app)
        self.enforce = enforce
        logger.info(f"EmbeddingValidationMiddleware initialized (enforce={enforce})")
    
    async def dispatch(
        self,
        request: Request,
        call_next: Callable
    ) -> Response:
        """
        Validate embeddings in request body.
        
        Args:
            request: FastAPI request
            call_next: Next middleware/endpoint
            
        Returns:
            Response from endpoint
            
        Raises:
            HTTPException: If embedding validation fails (when enforce=True)
        """
        # Skip validation for non-embedding endpoints
        if request.url.path not in self.EMBEDDING_ENDPOINTS:
            return await call_next(request)
        
        # Skip for non-POST requests
        if request.method not in ("POST", "PUT", "PATCH"):
            return await call_next(request)
        
        # Read and validate request body
        try:
            body = await request.body()
            
            if not body:
                return await call_next(request)
            
            # Parse JSON
            try:
                data = json.loads(body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.error(f"Failed to parse request body: {e}")
                return await call_next(request)
            
            # Find and validate embeddings in request
            validation_errors = []
            
            for key in self.EMBEDDING_KEYS:
                if key in data:
                    embedding_data = data[key]
                    
                    # Handle single embedding
                    if isinstance(embedding_data, list) and isinstance(embedding_data[0], (int, float)):
                        try:
                            validate_embedding(embedding_data, strict=True)
                            logger.debug(f"Validated single embedding in key '{key}'")
                        except EmbeddingValidationError as e:
                            validation_errors.append(f"{key}: {str(e)}")
                    
                    # Handle batch of embeddings
                    elif isinstance(embedding_data, list):
                        for i, embedding in enumerate(embedding_data):
                            if isinstance(embedding, list):
                                try:
                                    validate_embedding(embedding, strict=True)
                                except EmbeddingValidationError as e:
                                    validation_errors.append(f"{key}[{i}]: {str(e)}")
            
            # If validation errors found
            if validation_errors:
                logger.error(
                    f"Embedding validation failed for {request.url.path}: "
                    f"{', '.join(validation_errors)}"
                )
                
                if self.enforce:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "Embedding validation failed",
                            "validation_errors": validation_errors,
                            "hint": "Embeddings must be 1536-dimensional float arrays "
                                   "without NaN/Inf values"
                        }
                    )
                else:
                    logger.warning(
                        "Embedding validation failed but enforcement disabled. "
                        "Request proceeding..."
                    )
            
            # Restore body for downstream processing
            # FastAPI reads body, so we need to restore it
            async def receive():
                return {"type": "http.request", "body": body}
            
            request._receive = receive
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in embedding validation middleware: {e}", exc_info=True)
            # Don't block request on middleware errors
            if self.enforce:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Embedding validation error"
                )
        
        # Continue to endpoint
        response = await call_next(request)
        return response


def validate_embedding_in_dict(
    data: Dict[str, Any],
    key: str = "embedding",
    strict: bool = True
) -> Dict[str, Any]:
    """
    Validate embedding in dictionary (dependency injection).
    
    Can be used as FastAPI dependency for specific endpoints.
    
    Args:
        data: Request data dictionary
        key: Key containing embedding
        strict: Whether to raise exception on validation failure
        
    Returns:
        Data dict (unchanged if valid)
        
    Raises:
        HTTPException: If validation fails and strict=True
        
    Usage:
        from fastapi import Depends
        
        @app.post("/api/v1/embeddings/store")
        async def store_embedding(
            data: dict = Depends(validate_embedding_in_dict)
        ):
            # data["embedding"] is guaranteed to be valid
            ...
    """
    if key not in data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required field: {key}"
        )
    
    embedding = data[key]
    
    try:
        result = validate_embedding(embedding, strict=strict)
        
        if not result.valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Invalid embedding",
                    "errors": result.errors,
                    "warnings": result.warnings,
                    "metadata": result.metadata
                }
            )
        
        # Log warnings even if valid
        if result.warnings:
            logger.warning(
                f"Embedding validation warnings: {', '.join(result.warnings)}"
            )
        
        return data
        
    except EmbeddingValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Embedding validation failed: {str(e)}"
        )

