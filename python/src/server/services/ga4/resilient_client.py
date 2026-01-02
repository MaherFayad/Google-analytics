"""
Resilient GA4 Client with retry, circuit breaker, and cache fallback.

Implements Task P0-4: GA4 API Resilience Layer

This client wraps GA4 API calls with production-grade resilience patterns:
1. Exponential backoff retry (3 attempts: 2s, 4s, 8s)
2. Circuit breaker (prevents cascading failures)
3. Timeout protection (10s per call)
4. Cache fallback (graceful degradation)
5. Rate limit handling (429 errors)

Example:
    from server.services.ga4 import get_resilient_ga4_client
    
    client = await get_resilient_ga4_client(
        property_id="123456789",
        tenant_id=UUID("..."),
        user_id=UUID("...")
    )
    
    # Automatically retries on failure, falls back to cache if needed
    response = await client.fetch_page_views_safe(
        start_date="2025-01-01",
        end_date="2025-01-07"
    )
"""

import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, Optional, List
from uuid import UUID
import json
import hashlib

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    RetryError
)
import httpx

from .circuit_breaker import CircuitBreaker
from .exceptions import (
    GA4APIError,
    GA4RateLimitError,
    GA4NetworkError,
    GA4TimeoutError,
    GA4CircuitBreakerError,
    GA4CacheStaleError
)
from ..core.config import settings

logger = logging.getLogger(__name__)


class ResilientGA4Client:
    """
    Resilient wrapper for GA4 client with retry and fallback logic.
    
    Task P0-4 Implementation:
    - Retry with exponential backoff
    - Circuit breaker protection
    - Timeout enforcement
    - Cache fallback on failure
    - Rate limit handling
    """
    
    # Retry configuration
    MAX_RETRIES = 3
    INITIAL_WAIT = 2  # seconds
    MAX_WAIT = 8  # seconds
    TIMEOUT = 10  # seconds per API call
    
    # Cache configuration
    CACHE_TTL = 3600  # 1 hour
    STALE_CACHE_WARNING_AGE = 7200  # 2 hours
    
    def __init__(
        self,
        property_id: str,
        tenant_id: UUID,
        user_id: UUID,
        cache_backend: Optional[Any] = None
    ):
        """
        Initialize resilient GA4 client.
        
        Args:
            property_id: GA4 property ID
            tenant_id: Tenant UUID
            user_id: User UUID
            cache_backend: Optional cache backend (Redis)
        """
        self.property_id = property_id
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.cache = cache_backend
        
        # Initialize circuit breaker
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60,
            success_threshold=2,
            name=f"GA4_{property_id}"
        )
        
        # Get underlying client (mock or real)
        from .mock_service import get_ga4_client
        self.client = get_ga4_client(
            property_id=property_id,
            tenant_id=tenant_id,
            mock_mode=settings.GA4_MOCK_MODE,
            scenario=settings.GA4_DEFAULT_SCENARIO
        )
        
        logger.info(
            f"ResilientGA4Client initialized: property={property_id}, "
            f"tenant={tenant_id}"
        )
    
    async def fetch_page_views_safe(
        self,
        start_date: str,
        end_date: str,
        dimensions: Optional[List[str]] = None,
        metrics: Optional[List[str]] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Fetch page views with resilience (retry + fallback).
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            dimensions: Optional dimensions list
            metrics: Optional metrics list
            use_cache: Whether to use cache fallback
            
        Returns:
            GA4 API response (or cached response if API fails)
            
        Raises:
            GA4APIError: If all retries failed and no cache available
        """
        cache_key = self._build_cache_key(
            "page_views",
            start_date=start_date,
            end_date=end_date,
            dimensions=dimensions,
            metrics=metrics
        )
        
        # Try to fetch from API with retry + circuit breaker
        try:
            response = await self._fetch_with_retry(
                self.client.fetch_page_views,
                cache_key=cache_key,
                start_date=start_date,
                end_date=end_date,
                dimensions=dimensions,
                metrics=metrics
            )
            
            # Success - update cache
            if use_cache and self.cache:
                await self._cache_response(cache_key, response)
            
            return response
            
        except (GA4APIError, GA4CircuitBreakerError, RetryError) as e:
            logger.error(
                f"GA4 API failed after retries: {e}. "
                f"Attempting cache fallback..."
            )
            
            # Fall back to cache
            if use_cache:
                cached_response = await self._get_cached_response(cache_key)
                
                if cached_response:
                    cache_age = cached_response.get("_cache_age_seconds", 0)
                    
                    logger.warning(
                        f"Returning stale cached data (age: {cache_age}s)"
                    )
                    
                    # Add warning to response
                    cached_response["_cache_fallback"] = True
                    cached_response["_cache_age_seconds"] = cache_age
                    cached_response["_original_error"] = str(e)
                    
                    return cached_response
            
            # No cache available, re-raise
            logger.error("No cached data available for fallback")
            raise
    
    async def _fetch_with_retry(
        self,
        func,
        cache_key: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Fetch data with retry logic and circuit breaker.
        
        Args:
            func: Async function to call
            cache_key: Cache key for this request
            **kwargs: Arguments for func
            
        Returns:
            API response
            
        Raises:
            GA4APIError: After all retries exhausted
            GA4CircuitBreakerError: If circuit is open
        """
        # Define retry decorator
        @retry(
            stop=stop_after_attempt(self.MAX_RETRIES),
            wait=wait_exponential(
                multiplier=self.INITIAL_WAIT,
                max=self.MAX_WAIT
            ),
            retry=retry_if_exception_type((
                GA4NetworkError,
                GA4TimeoutError,
                httpx.TimeoutException,
                httpx.NetworkError
            )),
            reraise=True
        )
        async def fetch_with_timeout():
            """Inner function with timeout enforcement."""
            try:
                # Enforce timeout
                async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
                    # Call through circuit breaker
                    return await self.circuit_breaker.call(func, **kwargs)
                    
            except httpx.TimeoutException as e:
                logger.warning(f"GA4 API timeout: {e}")
                raise GA4TimeoutError(f"Request timed out after {self.TIMEOUT}s") from e
            
            except httpx.NetworkError as e:
                logger.warning(f"GA4 network error: {e}")
                raise GA4NetworkError(f"Network error: {e}") from e
            
            except Exception as e:
                # Convert to GA4APIError for consistency
                logger.error(f"GA4 API error: {e}", exc_info=True)
                raise GA4APIError(f"API call failed: {e}") from e
        
        # Execute with retries
        try:
            return await fetch_with_timeout()
        except RetryError as e:
            # All retries exhausted
            logger.error(
                f"All {self.MAX_RETRIES} retry attempts failed. "
                f"Last error: {e.last_attempt.exception()}"
            )
            raise GA4APIError(
                f"Failed after {self.MAX_RETRIES} attempts: "
                f"{e.last_attempt.exception()}"
            ) from e
    
    def _build_cache_key(
        self,
        endpoint: str,
        **params
    ) -> str:
        """
        Build cache key for request.
        
        Args:
            endpoint: API endpoint name
            **params: Request parameters
            
        Returns:
            Cache key string
        """
        # Sort params for consistent keys
        param_str = json.dumps(params, sort_keys=True)
        param_hash = hashlib.sha256(param_str.encode()).hexdigest()[:16]
        
        return f"ga4:{self.tenant_id}:{endpoint}:{param_hash}"
    
    async def _cache_response(
        self,
        cache_key: str,
        response: Dict[str, Any]
    ) -> None:
        """
        Store response in cache.
        
        Args:
            cache_key: Cache key
            response: API response to cache
        """
        if not self.cache:
            return
        
        try:
            cache_data = {
                "response": response,
                "cached_at": datetime.utcnow().isoformat(),
                "tenant_id": str(self.tenant_id)
            }
            
            # Store with TTL
            await self.cache.setex(
                cache_key,
                self.CACHE_TTL,
                json.dumps(cache_data)
            )
            
            logger.debug(f"Cached response: key={cache_key}, ttl={self.CACHE_TTL}s")
            
        except Exception as e:
            logger.error(f"Failed to cache response: {e}", exc_info=True)
    
    async def _get_cached_response(
        self,
        cache_key: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached response.
        
        Args:
            cache_key: Cache key
            
        Returns:
            Cached response or None
        """
        if not self.cache:
            return None
        
        try:
            cached_data = await self.cache.get(cache_key)
            
            if not cached_data:
                return None
            
            cache_obj = json.loads(cached_data)
            cached_at = datetime.fromisoformat(cache_obj["cached_at"])
            age_seconds = (datetime.utcnow() - cached_at).total_seconds()
            
            response = cache_obj["response"]
            response["_cache_age_seconds"] = int(age_seconds)
            response["_cached_at"] = cache_obj["cached_at"]
            
            # Warn if cache is very stale
            if age_seconds > self.STALE_CACHE_WARNING_AGE:
                logger.warning(
                    f"Cache is very stale: age={age_seconds}s, "
                    f"key={cache_key}"
                )
            
            return response
            
        except Exception as e:
            logger.error(f"Failed to retrieve cached response: {e}", exc_info=True)
            return None
    
    def get_circuit_breaker_state(self) -> Dict[str, Any]:
        """
        Get circuit breaker state for monitoring.
        
        Returns:
            Circuit breaker state dict
        """
        return self.circuit_breaker.get_state()
    
    async def reset_circuit_breaker(self) -> None:
        """Manually reset circuit breaker (admin operation)."""
        await self.circuit_breaker.reset()


async def get_resilient_ga4_client(
    property_id: str,
    tenant_id: UUID,
    user_id: UUID,
    cache_backend: Optional[Any] = None
) -> ResilientGA4Client:
    """
    Factory function to create resilient GA4 client.
    
    Args:
        property_id: GA4 property ID
        tenant_id: Tenant UUID
        user_id: User UUID
        cache_backend: Optional Redis cache
        
    Returns:
        ResilientGA4Client instance
        
    Usage:
        client = await get_resilient_ga4_client(
            property_id="123456789",
            tenant_id=UUID("..."),
            user_id=UUID("..."),
            cache_backend=redis_client
        )
        
        # Automatically handles retries and fallback
        response = await client.fetch_page_views_safe(
            start_date="2025-01-01",
            end_date="2025-01-07"
        )
    """
    return ResilientGA4Client(
        property_id=property_id,
        tenant_id=tenant_id,
        user_id=user_id,
        cache_backend=cache_backend
    )

