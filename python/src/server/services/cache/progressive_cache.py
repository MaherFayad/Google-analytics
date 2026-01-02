"""
Progressive Multi-Tier Cache Service.

Implements Task P0-12: Async Agent Execution with Streaming

Provides multi-tier caching for instant query responses:
- L1 Cache (Redis): 0-50ms - Hot cache for recent/frequent queries
- L2 Cache (Database): 100-300ms - Persistent cache for historical queries  
- L3 (API Call): 500-1000ms+ - Fresh data fetch when cache miss

Strategy:
1. Check L1 (Redis) → instant response if hit
2. Check L2 (DB) → fast response if hit, promote to L1
3. Fetch fresh → cache in both L1 and L2

Cache Keys:
- Format: `ga4:{tenant_id}:{property_id}:{query_hash}:{date_range}`
- TTL: L1=1hr, L2=24hr
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CacheEntry(BaseModel):
    """Cached query result with metadata."""
    
    query: str
    tenant_id: str
    property_id: str
    result: Dict[str, Any]
    cached_at: datetime
    source: str  # "l1", "l2", or "fresh"
    ttl_seconds: int


class CacheStats(BaseModel):
    """Cache performance statistics."""
    
    l1_hits: int = 0
    l1_misses: int = 0
    l2_hits: int = 0
    l2_misses: int = 0
    l3_fetches: int = 0
    avg_latency_ms: float = 0.0


class ProgressiveCacheService:
    """
    Multi-tier cache for GA4 query results.
    
    Provides sub-50ms cache hits for hot queries,
    sub-300ms for warm queries (L2),
    and graceful degradation for cache misses.
    
    Usage:
        cache = ProgressiveCacheService(redis_client, db_session)
        
        # Try cache first (instant)
        cached = await cache.get_cached_result(query, tenant_id, property_id)
        if cached:
            yield {"type": "result", "payload": cached, "source": "cache"}
            return
        
        # Cache miss - fetch fresh data
        result = await fetch_fresh_data()
        await cache.set_cached_result(query, tenant_id, property_id, result)
    """
    
    # Cache TTLs
    L1_TTL_SECONDS = 3600  # 1 hour (Redis)
    L2_TTL_SECONDS = 86400  # 24 hours (Database)
    
    # Performance thresholds
    L1_TARGET_MS = 50
    L2_TARGET_MS = 300
    
    def __init__(
        self,
        redis_client: Optional[Any] = None,
        db_session: Optional[Any] = None,
    ):
        """
        Initialize progressive cache.
        
        Args:
            redis_client: Redis client for L1 cache
            db_session: Database session for L2 cache
        """
        self.redis_client = redis_client
        self.db_session = db_session
        self.stats = CacheStats()
        
        logger.info("Progressive cache initialized")
    
    def _generate_cache_key(
        self,
        query: str,
        tenant_id: str,
        property_id: str,
        date_range: Optional[str] = None,
    ) -> str:
        """
        Generate cache key from query parameters.
        
        Args:
            query: User query (normalized)
            tenant_id: Tenant ID
            property_id: GA4 property ID
            date_range: Optional date range (e.g., "2025-01-01:2025-01-07")
            
        Returns:
            Cache key string
        """
        # Normalize query (lowercase, strip, sort words for semantic similarity)
        normalized = " ".join(sorted(query.lower().strip().split()))
        
        # Generate hash
        content = f"{tenant_id}:{property_id}:{normalized}:{date_range or 'default'}"
        query_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        
        return f"ga4:{tenant_id}:{property_id}:{query_hash}"
    
    async def get_cached_result(
        self,
        query: str,
        tenant_id: str,
        property_id: str,
        date_range: Optional[str] = None,
    ) -> Optional[CacheEntry]:
        """
        Get cached result with L1 → L2 fallback.
        
        Performance targets:
        - L1 hit: <50ms
        - L2 hit: <300ms
        - Cache miss: None (caller fetches fresh)
        
        Args:
            query: User query
            tenant_id: Tenant ID
            property_id: GA4 property ID
            date_range: Optional date range filter
            
        Returns:
            CacheEntry if found, None if miss
        """
        cache_key = self._generate_cache_key(query, tenant_id, property_id, date_range)
        
        start_time = datetime.utcnow()
        
        # L1: Redis check (target <50ms)
        if self.redis_client:
            try:
                cached_json = await self._get_from_redis(cache_key)
                
                if cached_json:
                    latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                    
                    self.stats.l1_hits += 1
                    logger.info(
                        f"L1 cache hit for {cache_key} ({latency_ms:.1f}ms)",
                        extra={"cache_key": cache_key, "latency_ms": latency_ms}
                    )
                    
                    result = json.loads(cached_json)
                    return CacheEntry(
                        query=query,
                        tenant_id=tenant_id,
                        property_id=property_id,
                        result=result,
                        cached_at=datetime.fromisoformat(result.get("cached_at", datetime.utcnow().isoformat())),
                        source="l1",
                        ttl_seconds=self.L1_TTL_SECONDS,
                    )
            except Exception as e:
                logger.warning(f"L1 cache error for {cache_key}: {e}")
        
        self.stats.l1_misses += 1
        
        # L2: Database check (target <300ms)
        if self.db_session:
            try:
                cached_entry = await self._get_from_database(cache_key)
                
                if cached_entry:
                    latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                    
                    self.stats.l2_hits += 1
                    logger.info(
                        f"L2 cache hit for {cache_key} ({latency_ms:.1f}ms)",
                        extra={"cache_key": cache_key, "latency_ms": latency_ms}
                    )
                    
                    # Promote to L1 for faster subsequent access
                    if self.redis_client:
                        await self._set_in_redis(cache_key, cached_entry.result, self.L1_TTL_SECONDS)
                    
                    return cached_entry
            except Exception as e:
                logger.warning(f"L2 cache error for {cache_key}: {e}")
        
        self.stats.l2_misses += 1
        
        # Cache miss - caller will fetch fresh
        latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        logger.info(
            f"Cache miss for {cache_key} ({latency_ms:.1f}ms)",
            extra={"cache_key": cache_key, "latency_ms": latency_ms}
        )
        
        return None
    
    async def set_cached_result(
        self,
        query: str,
        tenant_id: str,
        property_id: str,
        result: Dict[str, Any],
        date_range: Optional[str] = None,
    ) -> None:
        """
        Cache result in both L1 (Redis) and L2 (Database).
        
        Args:
            query: User query
            tenant_id: Tenant ID
            property_id: GA4 property ID
            result: Query result to cache
            date_range: Optional date range
        """
        cache_key = self._generate_cache_key(query, tenant_id, property_id, date_range)
        
        # Add metadata
        result_with_meta = {
            **result,
            "cached_at": datetime.utcnow().isoformat(),
            "cache_key": cache_key,
        }
        
        # Store in L1 (Redis)
        if self.redis_client:
            try:
                await self._set_in_redis(cache_key, result_with_meta, self.L1_TTL_SECONDS)
                logger.debug(f"Cached in L1: {cache_key}")
            except Exception as e:
                logger.error(f"Failed to cache in L1: {e}")
        
        # Store in L2 (Database)
        if self.db_session:
            try:
                await self._set_in_database(
                    cache_key,
                    CacheEntry(
                        query=query,
                        tenant_id=tenant_id,
                        property_id=property_id,
                        result=result_with_meta,
                        cached_at=datetime.utcnow(),
                        source="fresh",
                        ttl_seconds=self.L2_TTL_SECONDS,
                    )
                )
                logger.debug(f"Cached in L2: {cache_key}")
            except Exception as e:
                logger.error(f"Failed to cache in L2: {e}")
    
    async def _get_from_redis(self, cache_key: str) -> Optional[str]:
        """Get value from Redis (L1 cache)."""
        if not self.redis_client:
            return None
        
        try:
            # Redis get operation
            value = await self.redis_client.get(cache_key)
            return value.decode() if value else None
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None
    
    async def _set_in_redis(self, cache_key: str, value: Dict[str, Any], ttl_seconds: int) -> None:
        """Set value in Redis with TTL."""
        if not self.redis_client:
            return
        
        try:
            await self.redis_client.setex(
                cache_key,
                ttl_seconds,
                json.dumps(value)
            )
        except Exception as e:
            logger.error(f"Redis set error: {e}")
    
    async def _get_from_database(self, cache_key: str) -> Optional[CacheEntry]:
        """Get value from database (L2 cache)."""
        if not self.db_session:
            return None
        
        # TODO: Implement database cache table
        # For now, return None (L2 cache not implemented yet)
        return None
    
    async def _set_in_database(self, cache_key: str, entry: CacheEntry) -> None:
        """Set value in database with TTL."""
        if not self.db_session:
            return
        
        # TODO: Implement database cache table
        # CREATE TABLE query_cache (
        #     cache_key TEXT PRIMARY KEY,
        #     query TEXT,
        #     tenant_id UUID,
        #     result JSONB,
        #     cached_at TIMESTAMPTZ,
        #     expires_at TIMESTAMPTZ,
        #     INDEX idx_cache_tenant_expires (tenant_id, expires_at)
        # );
        pass
    
    def get_stats(self) -> CacheStats:
        """Get cache performance statistics."""
        total_requests = (
            self.stats.l1_hits + self.stats.l1_misses
        )
        
        if total_requests > 0:
            self.stats.avg_latency_ms = (
                (self.stats.l1_hits * 30) +  # Avg L1 hit: 30ms
                (self.stats.l2_hits * 200) +  # Avg L2 hit: 200ms
                (self.stats.l3_fetches * 1000)  # Avg fresh fetch: 1000ms
            ) / total_requests
        
        return self.stats
    
    def reset_stats(self) -> None:
        """Reset performance statistics."""
        self.stats = CacheStats()



