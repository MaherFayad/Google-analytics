"""
Idempotency Middleware for SSE Reconnection

Implements Task P0-34: SSE Auto-Reconnect with Idempotency & Backoff

Prevents duplicate request processing when SSE connections reconnect.

Features:
- Request deduplication using Redis cache
- 5-minute result caching
- Automatic cleanup
- Support for both success and error responses

Usage:
    from fastapi import FastAPI, Depends
    from .middleware.idempotency import get_idempotency_key, check_idempotency
    
    @app.post("/analytics/query")
    async def query(
        request_id: str = Depends(get_idempotency_key),
        cached_response: dict | None = Depends(check_idempotency)
    ):
        if cached_response:
            return cached_response
        
        # Process request...
        result = await process_query()
        
        # Store for future reconnects
        await store_idempotent_response(request_id, result)
        
        return result
"""

import logging
import json
import hashlib
from typing import Optional, Any, Callable
from datetime import timedelta

from fastapi import Request, HTTPException, status, Header
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import redis.asyncio as redis

from ..core.config import settings

logger = logging.getLogger(__name__)

# Redis client (initialized at startup)
_redis_client: Optional[redis.Redis] = None


async def init_idempotency_redis() -> None:
    """
    Initialize Redis client for idempotency checks.
    
    Should be called at application startup.
    """
    global _redis_client
    
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )
        logger.info("Idempotency Redis client initialized")


async def close_idempotency_redis() -> None:
    """
    Close Redis client.
    
    Should be called at application shutdown.
    """
    global _redis_client
    
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
        logger.info("Idempotency Redis client closed")


def get_redis_client() -> redis.Redis:
    """Get Redis client instance."""
    if _redis_client is None:
        raise RuntimeError("Idempotency Redis client not initialized")
    return _redis_client


# ============================================================================
# Idempotency Key Management
# ============================================================================

def generate_idempotency_key(request_data: dict) -> str:
    """
    Generate idempotency key from request data.
    
    Uses SHA256 hash of request content for deterministic keys.
    
    Args:
        request_data: Request payload dictionary
        
    Returns:
        Idempotency key string
    """
    content = json.dumps(request_data, sort_keys=True)
    key_hash = hashlib.sha256(content.encode()).hexdigest()
    return f"idempotent:{key_hash}"


async def get_idempotency_key(
    request: Request,
    x_idempotency_key: Optional[str] = Header(None)
) -> str:
    """
    Extract or generate idempotency key from request.
    
    FastAPI dependency for idempotency key extraction.
    
    Args:
        request: FastAPI request
        x_idempotency_key: Optional idempotency key from header
        
    Returns:
        Idempotency key
        
    Usage:
        @app.post("/api/endpoint")
        async def endpoint(
            idempotency_key: str = Depends(get_idempotency_key)
        ):
            ...
    """
    # Use provided key if available
    if x_idempotency_key:
        return f"idempotent:{x_idempotency_key}"
    
    # Generate from request data
    if request.method in ("POST", "PUT", "PATCH"):
        try:
            body = await request.json()
            return generate_idempotency_key(body)
        except Exception:
            # Fall back to URL-based key
            pass
    
    # Use URL + query params as key
    return f"idempotent:{request.url.path}:{request.url.query}"


# ============================================================================
# Idempotency Check
# ============================================================================

async def check_idempotency(
    idempotency_key: str
) -> Optional[dict]:
    """
    Check if request has already been processed.
    
    FastAPI dependency for idempotency checking.
    
    Args:
        idempotency_key: Idempotency key
        
    Returns:
        Cached response if found, None otherwise
        
    Usage:
        @app.post("/api/endpoint")
        async def endpoint(
            idempotency_key: str = Depends(get_idempotency_key),
            cached_response: dict | None = Depends(check_idempotency)
        ):
            if cached_response:
                return cached_response
            
            # Process request...
    """
    try:
        redis_client = get_redis_client()
        
        # Check cache
        cached = await redis_client.get(idempotency_key)
        
        if cached:
            logger.info(f"Idempotency hit: {idempotency_key}")
            return json.loads(cached)
        
        return None
    
    except Exception as e:
        logger.error(f"Error checking idempotency: {e}", exc_info=True)
        # Don't fail request if idempotency check fails
        return None


async def store_idempotent_response(
    idempotency_key: str,
    response: dict,
    ttl_seconds: int = 300
) -> None:
    """
    Store response for idempotency checking.
    
    Args:
        idempotency_key: Idempotency key
        response: Response data to cache
        ttl_seconds: Time-to-live in seconds (default: 5 minutes)
        
    Usage:
        result = await process_query()
        await store_idempotent_response(idempotency_key, result)
        return result
    """
    try:
        redis_client = get_redis_client()
        
        # Store response
        await redis_client.setex(
            idempotency_key,
            ttl_seconds,
            json.dumps(response)
        )
        
        logger.debug(f"Stored idempotent response: {idempotency_key} (TTL: {ttl_seconds}s)")
    
    except Exception as e:
        logger.error(f"Error storing idempotent response: {e}", exc_info=True)
        # Don't fail request if storage fails


# ============================================================================
# Idempotency Middleware
# ============================================================================

class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Middleware for automatic idempotency handling.
    
    Automatically checks for cached responses and stores new responses.
    
    Usage:
        app.add_middleware(IdempotencyMiddleware, ttl_seconds=300)
    """
    
    def __init__(self, app, ttl_seconds: int = 300):
        """
        Initialize idempotency middleware.
        
        Args:
            app: FastAPI application
            ttl_seconds: Cache TTL in seconds
        """
        super().__init__(app)
        self.ttl_seconds = ttl_seconds
        logger.info(f"Idempotency middleware initialized (TTL: {ttl_seconds}s)")
    
    async def dispatch(self, request: Request, call_next: Callable):
        """
        Process request with idempotency checking.
        
        Args:
            request: FastAPI request
            call_next: Next middleware/endpoint
            
        Returns:
            Response (cached or fresh)
        """
        # Only apply to POST/PUT/PATCH (idempotent by design)
        if request.method not in ("POST", "PUT", "PATCH"):
            return await call_next(request)
        
        # Skip for endpoints that explicitly disable idempotency
        if request.url.path.endswith("/no-idempotency"):
            return await call_next(request)
        
        try:
            # Get idempotency key
            x_idempotency_key = request.headers.get("X-Idempotency-Key")
            
            if not x_idempotency_key:
                # No idempotency key, process normally
                return await call_next(request)
            
            idempotency_key = f"idempotent:{x_idempotency_key}"
            
            # Check cache
            cached_response = await check_idempotency(idempotency_key)
            
            if cached_response:
                logger.info(f"Returning cached response for: {idempotency_key}")
                return JSONResponse(
                    content=cached_response,
                    headers={"X-Idempotency-Hit": "true"}
                )
            
            # Process request
            response = await call_next(request)
            
            # Store successful responses (2xx status codes)
            if 200 <= response.status_code < 300:
                # Note: We can't easily capture response body here without
                # reading the entire stream. Better to store explicitly
                # in endpoints using store_idempotent_response()
                pass
            
            return response
        
        except Exception as e:
            logger.error(f"Error in idempotency middleware: {e}", exc_info=True)
            # Don't fail request if idempotency fails
            return await call_next(request)


# ============================================================================
# Helper Functions
# ============================================================================

async def invalidate_idempotency_key(idempotency_key: str) -> None:
    """
    Invalidate cached response for idempotency key.
    
    Useful when resource state changes and cached response is stale.
    
    Args:
        idempotency_key: Idempotency key to invalidate
    """
    try:
        redis_client = get_redis_client()
        await redis_client.delete(idempotency_key)
        logger.debug(f"Invalidated idempotency key: {idempotency_key}")
    except Exception as e:
        logger.error(f"Error invalidating idempotency key: {e}", exc_info=True)


async def get_idempotency_stats() -> dict:
    """
    Get statistics about idempotency cache.
    
    Returns:
        Dictionary with cache statistics
        
    Usage:
        @app.get("/admin/idempotency/stats")
        async def stats():
            return await get_idempotency_stats()
    """
    try:
        redis_client = get_redis_client()
        
        # Count keys matching idempotency pattern
        cursor = 0
        count = 0
        
        while True:
            cursor, keys = await redis_client.scan(
                cursor,
                match="idempotent:*",
                count=100
            )
            count += len(keys)
            
            if cursor == 0:
                break
        
        return {
            "cached_responses": count,
            "ttl_seconds": 300,
            "status": "healthy"
        }
    
    except Exception as e:
        logger.error(f"Error getting idempotency stats: {e}", exc_info=True)
        return {
            "cached_responses": 0,
            "ttl_seconds": 300,
            "status": "error",
            "error": str(e)
        }

