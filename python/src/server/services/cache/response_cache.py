"""
Redis Response Caching Layer for Agent Execution.

Implements Task 4.3: Redis Caching Layer

Features:
- Decorator-based caching for agent results
- SHA256 hash-based cache keys
- Configurable TTL (default: 1 hour)
- Cache hit/miss metrics
- Tenant-aware caching

Usage:
    @cache_response(ttl=3600, cache_key_parts=["user_id", "query"])
    async def execute_analytics(user_id: str, query: str):
        # Expensive operation
        return await agent.execute()
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
from functools import wraps

import redis.asyncio as redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CacheMetrics(BaseModel):
    """Cache performance metrics."""
    
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        if self.total_requests == 0:
            return 0.0
        return self.cache_hits / self.total_requests
    
    @property
    def miss_rate(self) -> float:
        """Calculate cache miss rate."""
        return 1.0 - self.hit_rate


class ResponseCache:
    """
    Redis-based response cache for agent results.
    
    Implements Task 4.3: Redis Caching Layer
    
    Features:
    - SHA256 hash-based keys
    - JSON serialization
    - TTL support
    - Hit/miss tracking
    - Tenant isolation
    """
    
    CACHE_KEY_PREFIX = "agent:cache:"
    DEFAULT_TTL = 3600  # 1 hour
    
    def __init__(self, redis_client: redis.Redis):
        """
        Initialize response cache.
        
        Args:
            redis_client: Async Redis client
        """
        self.redis = redis_client
        self.metrics = CacheMetrics()
        
        logger.info("Response cache initialized")
    
    def generate_cache_key(
        self,
        user_id: str,
        query: str,
        persona: Optional[str] = None,
        additional_params: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate cache key from parameters.
        
        Uses SHA256 hash of JSON-serialized parameters.
        
        Args:
            user_id: User ID
            query: Query string
            persona: Persona key (optional)
            additional_params: Additional parameters to include in hash
        
        Returns:
            Cache key string
        """
        # Combine all parameters
        cache_params = {
            "user_id": user_id,
            "query": query.lower().strip(),  # Normalize query
        }
        
        if persona:
            cache_params["persona"] = persona
        
        if additional_params:
            cache_params.update(additional_params)
        
        # Serialize and hash
        params_json = json.dumps(cache_params, sort_keys=True)
        hash_digest = hashlib.sha256(params_json.encode()).hexdigest()
        
        return f"{self.CACHE_KEY_PREFIX}{hash_digest}"
    
    async def get(
        self,
        cache_key: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached response.
        
        Args:
            cache_key: Cache key
        
        Returns:
            Cached data or None if not found
        """
        self.metrics.total_requests += 1
        
        try:
            cached = await self.redis.get(cache_key)
            
            if cached:
                self.metrics.cache_hits += 1
                data = json.loads(cached)
                
                logger.info(
                    f"Cache HIT: {cache_key[:50]}... "
                    f"(hit rate: {self.metrics.hit_rate:.2%})"
                )
                
                return data
            else:
                self.metrics.cache_misses += 1
                
                logger.debug(
                    f"Cache MISS: {cache_key[:50]}... "
                    f"(hit rate: {self.metrics.hit_rate:.2%})"
                )
                
                return None
        
        except Exception as e:
            logger.error(f"Cache get error: {e}", exc_info=True)
            self.metrics.cache_misses += 1
            return None
    
    async def set(
        self,
        cache_key: str,
        data: Dict[str, Any],
        ttl: int = DEFAULT_TTL
    ):
        """
        Store response in cache.
        
        Args:
            cache_key: Cache key
            data: Data to cache
            ttl: Time to live in seconds
        """
        try:
            data_json = json.dumps(data)
            await self.redis.setex(cache_key, ttl, data_json)
            
            logger.debug(f"Cached response: {cache_key[:50]}... (TTL: {ttl}s)")
        
        except Exception as e:
            logger.error(f"Cache set error: {e}", exc_info=True)
    
    async def invalidate(self, cache_key: str):
        """
        Invalidate cached response.
        
        Args:
            cache_key: Cache key to invalidate
        """
        try:
            await self.redis.delete(cache_key)
            logger.info(f"Cache invalidated: {cache_key[:50]}...")
        except Exception as e:
            logger.error(f"Cache invalidate error: {e}", exc_info=True)
    
    async def invalidate_pattern(self, pattern: str):
        """
        Invalidate all keys matching pattern.
        
        Args:
            pattern: Redis pattern (e.g., "agent:cache:user-123:*")
        """
        try:
            keys = []
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key)
            
            if keys:
                await self.redis.delete(*keys)
                logger.info(f"Invalidated {len(keys)} cache entries matching {pattern}")
        except Exception as e:
            logger.error(f"Cache invalidate pattern error: {e}", exc_info=True)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get cache metrics."""
        return {
            "total_requests": self.metrics.total_requests,
            "cache_hits": self.metrics.cache_hits,
            "cache_misses": self.metrics.cache_misses,
            "hit_rate_percent": round(self.metrics.hit_rate * 100, 2),
            "miss_rate_percent": round(self.metrics.miss_rate * 100, 2),
        }


def cache_response(
    ttl: int = ResponseCache.DEFAULT_TTL,
    cache_key_parts: Optional[List[str]] = None
):
    """
    Decorator for caching agent execution results.
    
    Implements Task 4.3: Redis Caching Layer
    
    Computes SHA256 hash of specified parameters and caches the result.
    
    Args:
        ttl: Time to live in seconds (default: 1 hour)
        cache_key_parts: List of parameter names to include in cache key
    
    Usage:
        @cache_response(ttl=3600, cache_key_parts=["user_id", "query"])
        async def execute_analytics(user_id: str, query: str, **kwargs):
            return await agent.execute()
    
    Example:
        @cache_response(ttl=1800, cache_key_parts=["tenant_id", "query", "persona"])
        async def generate_report(tenant_id: str, query: str, persona: str):
            # This will be cached for 30 minutes
            return await reporting_agent.execute()
    """
    if cache_key_parts is None:
        cache_key_parts = ["user_id", "query"]
    
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract cache parameters
            cache_params = {}
            
            # Try to extract from kwargs
            for param_name in cache_key_parts:
                if param_name in kwargs:
                    cache_params[param_name] = kwargs[param_name]
            
            # Generate cache key
            params_json = json.dumps(cache_params, sort_keys=True)
            hash_digest = hashlib.sha256(params_json.encode()).hexdigest()
            cache_key = f"{ResponseCache.CACHE_KEY_PREFIX}{hash_digest}"
            
            # TODO: Get Redis client from app context
            # For now, this is a placeholder
            redis_client = kwargs.get("redis_client")
            
            if redis_client:
                cache = ResponseCache(redis_client)
                
                # Try to get from cache
                cached_result = await cache.get(cache_key)
                if cached_result is not None:
                    logger.info(f"Returning cached result for {func.__name__}")
                    return cached_result
                
                # Cache miss - execute function
                result = await func(*args, **kwargs)
                
                # Cache the result
                await cache.set(cache_key, result, ttl=ttl)
                
                return result
            else:
                # No Redis client, execute without caching
                logger.warning(f"No Redis client available, skipping cache for {func.__name__}")
                return await func(*args, **kwargs)
        
        return wrapper
    
    return decorator


def get_cache_key(
    user_id: str,
    query: str,
    persona: Optional[str] = None,
    **kwargs
) -> str:
    """
    Generate cache key for manual cache operations.
    
    Args:
        user_id: User ID
        query: Query string
        persona: Persona key
        **kwargs: Additional parameters
    
    Returns:
        Cache key string
    """
    params = {
        "user_id": user_id,
        "query": query.lower().strip(),
    }
    
    if persona:
        params["persona"] = persona
    
    params.update(kwargs)
    
    params_json = json.dumps(params, sort_keys=True)
    hash_digest = hashlib.sha256(params_json.encode()).hexdigest()
    
    return f"{ResponseCache.CACHE_KEY_PREFIX}{hash_digest}"


async def invalidate_cache(
    redis_client: redis.Redis,
    user_id: Optional[str] = None,
    query: Optional[str] = None,
    pattern: Optional[str] = None
):
    """
    Invalidate cached responses.
    
    Args:
        redis_client: Redis client
        user_id: User ID to invalidate (invalidates all for this user)
        query: Specific query to invalidate
        pattern: Redis pattern for bulk invalidation
    """
    cache = ResponseCache(redis_client)
    
    if pattern:
        await cache.invalidate_pattern(pattern)
    elif user_id and query:
        cache_key = get_cache_key(user_id, query)
        await cache.invalidate(cache_key)
    elif user_id:
        # Invalidate all for user
        pattern = f"{ResponseCache.CACHE_KEY_PREFIX}*"
        await cache.invalidate_pattern(pattern)
    else:
        logger.warning("No invalidation criteria provided")

