"""
Unit tests for Redis response caching.

Tests Task 4.3: Redis Caching Layer

Verifies:
- Cache key generation
- Cache hit/miss tracking
- TTL enforcement
- Decorator functionality
- Cache invalidation
"""

import pytest
import json
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

from src.server.services.cache.response_cache import (
    ResponseCache,
    CacheMetrics,
    get_cache_key,
    cache_response,
    invalidate_cache,
)


class TestCacheKeyGeneration:
    """Test cache key generation."""
    
    def test_generate_cache_key_basic(self):
        """Test basic cache key generation."""
        key = get_cache_key(
            user_id="user-123",
            query="Show mobile traffic"
        )
        
        assert key.startswith("agent:cache:")
        assert len(key) > 50  # Has hash
    
    def test_generate_cache_key_deterministic(self):
        """Test cache key is deterministic for same inputs."""
        key1 = get_cache_key(
            user_id="user-123",
            query="Show mobile traffic"
        )
        
        key2 = get_cache_key(
            user_id="user-123",
            query="Show mobile traffic"
        )
        
        assert key1 == key2
    
    def test_generate_cache_key_query_normalization(self):
        """Test query is normalized (case-insensitive, trimmed)."""
        key1 = get_cache_key(
            user_id="user-123",
            query="  Show Mobile Traffic  "
        )
        
        key2 = get_cache_key(
            user_id="user-123",
            query="show mobile traffic"
        )
        
        assert key1 == key2
    
    def test_generate_cache_key_with_persona(self):
        """Test cache key includes persona."""
        key_no_persona = get_cache_key(
            user_id="user-123",
            query="Show traffic"
        )
        
        key_with_persona = get_cache_key(
            user_id="user-123",
            query="Show traffic",
            persona="po"
        )
        
        # Should be different
        assert key_no_persona != key_with_persona
    
    def test_generate_cache_key_with_additional_params(self):
        """Test cache key can include additional parameters."""
        key1 = get_cache_key(
            user_id="user-123",
            query="Show traffic",
            property_id="12345"
        )
        
        key2 = get_cache_key(
            user_id="user-123",
            query="Show traffic",
            property_id="67890"
        )
        
        # Different property IDs should produce different keys
        assert key1 != key2


class TestCacheMetrics:
    """Test cache metrics tracking."""
    
    def test_cache_metrics_initialization(self):
        """Test metrics initialize to zero."""
        metrics = CacheMetrics()
        
        assert metrics.total_requests == 0
        assert metrics.cache_hits == 0
        assert metrics.cache_misses == 0
        assert metrics.hit_rate == 0.0
        assert metrics.miss_rate == 0.0
    
    def test_cache_metrics_hit_rate(self):
        """Test hit rate calculation."""
        metrics = CacheMetrics(
            total_requests=10,
            cache_hits=7,
            cache_misses=3
        )
        
        assert metrics.hit_rate == 0.7
        assert metrics.miss_rate == 0.3


class TestResponseCache:
    """Test ResponseCache class."""
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock()
        redis_mock.setex = AsyncMock()
        redis_mock.delete = AsyncMock()
        return redis_mock
    
    @pytest.mark.asyncio
    async def test_cache_miss(self, mock_redis):
        """Test cache miss returns None."""
        mock_redis.get.return_value = None
        
        cache = ResponseCache(mock_redis)
        result = await cache.get("test-key")
        
        assert result is None
        assert cache.metrics.cache_misses == 1
        assert cache.metrics.cache_hits == 0
    
    @pytest.mark.asyncio
    async def test_cache_hit(self, mock_redis):
        """Test cache hit returns data."""
        cached_data = {"result": "cached", "value": 123}
        mock_redis.get.return_value = json.dumps(cached_data)
        
        cache = ResponseCache(mock_redis)
        result = await cache.get("test-key")
        
        assert result == cached_data
        assert cache.metrics.cache_hits == 1
        assert cache.metrics.cache_misses == 0
    
    @pytest.mark.asyncio
    async def test_cache_set(self, mock_redis):
        """Test cache set stores data."""
        cache = ResponseCache(mock_redis)
        data = {"result": "test", "value": 456}
        
        await cache.set("test-key", data, ttl=1800)
        
        # Verify Redis was called
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "test-key"
        assert call_args[0][1] == 1800  # TTL
    
    @pytest.mark.asyncio
    async def test_cache_invalidate(self, mock_redis):
        """Test cache invalidation."""
        cache = ResponseCache(mock_redis)
        
        await cache.invalidate("test-key")
        
        mock_redis.delete.assert_called_once_with("test-key")
    
    @pytest.mark.asyncio
    async def test_cache_invalidate_pattern(self, mock_redis):
        """Test pattern-based cache invalidation."""
        # Mock scan_iter to return some keys
        async def mock_scan_iter(match=None):
            for key in ["key1", "key2", "key3"]:
                yield key
        
        mock_redis.scan_iter = mock_scan_iter
        
        cache = ResponseCache(mock_redis)
        
        await cache.invalidate_pattern("agent:cache:user-123:*")
        
        # Should delete all matched keys
        mock_redis.delete.assert_called_once()
    
    def test_get_cache_metrics(self, mock_redis):
        """Test getting cache metrics."""
        cache = ResponseCache(mock_redis)
        
        # Simulate some requests
        cache.metrics.total_requests = 100
        cache.metrics.cache_hits = 80
        cache.metrics.cache_misses = 20
        
        metrics = cache.get_metrics()
        
        assert metrics["total_requests"] == 100
        assert metrics["cache_hits"] == 80
        assert metrics["cache_misses"] == 20
        assert metrics["hit_rate_percent"] == 80.0


class TestCacheDecorator:
    """Test @cache_response decorator."""
    
    @pytest.mark.asyncio
    async def test_decorator_caches_result(self):
        """Test decorator caches function result."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)  # Cache miss
        mock_redis.setex = AsyncMock()
        
        call_count = 0
        
        @cache_response(ttl=1800, cache_key_parts=["user_id", "query"])
        async def test_function(user_id: str, query: str, redis_client=None):
            nonlocal call_count
            call_count += 1
            return {"result": "computed", "count": call_count}
        
        # First call - cache miss
        result1 = await test_function(
            user_id="user-123",
            query="test query",
            redis_client=mock_redis
        )
        
        assert result1["count"] == 1
        assert call_count == 1
        
        # Redis setex should have been called
        assert mock_redis.setex.called
    
    @pytest.mark.asyncio
    async def test_decorator_returns_cached_on_hit(self):
        """Test decorator returns cached result on hit."""
        cached_data = {"result": "cached", "value": 999}
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))
        
        call_count = 0
        
        @cache_response(ttl=1800, cache_key_parts=["user_id", "query"])
        async def test_function(user_id: str, query: str, redis_client=None):
            nonlocal call_count
            call_count += 1
            return {"result": "computed"}
        
        # Should return cached result without calling function
        result = await test_function(
            user_id="user-123",
            query="test query",
            redis_client=mock_redis
        )
        
        assert result == cached_data
        assert call_count == 0  # Function not called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

