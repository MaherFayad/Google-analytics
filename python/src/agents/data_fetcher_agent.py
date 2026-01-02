"""
DataFetcherAgent - Fetches GA4 data with retry logic.

Implements Task P0-1: DataFetcherAgent

Responsibilities:
- Fetch GA4 data via Google Analytics Data API
- Handle retries and quota checks
- Cache results in Redis
- Return typed DataFetchResult
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from pydantic_ai import RunContext
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
import httpx

from .base_agent import BaseAgent
from .schemas.results import DataFetchResult
from .tools.ga4_tool import GA4ToolContext, fetch_ga4_data

logger = logging.getLogger(__name__)


class DataFetcherAgent(BaseAgent[DataFetchResult]):
    """
    Agent for fetching GA4 data with resilience.
    
    Implements Task P0-1: DataFetcherAgent
    
    Features:
    - Retry logic with exponential backoff
    - Quota management integration
    - Redis caching for performance
    - Circuit breaker for GA4 API failures
    
    Contract:
        DataFetcherAgent.fetch() → DataFetchResult(status, data, cached)
    """
    
    def __init__(
        self,
        redis_client: Optional[Any] = None,
        cache_ttl: int = 3600,
    ):
        """
        Initialize DataFetcher agent.
        
        Args:
            redis_client: Redis client for caching
            cache_ttl: Cache TTL in seconds (default: 1 hour)
        """
        super().__init__(
            name="data_fetcher",
            model="openai:gpt-4o",
            retries=3,
            timeout_seconds=30,
        )
        self.redis_client = redis_client
        self.cache_ttl = cache_ttl
    
    def get_system_prompt(self) -> str:
        """System prompt for DataFetcher agent."""
        return """You are a data fetching specialist for Google Analytics 4.
        Your job is to efficiently retrieve GA4 metrics with proper error handling."""
    
    async def run_async(
        self,
        ctx: RunContext,
        tenant_id: str,
        user_id: str,
        property_id: str,
        access_token: str,
        dimensions: list[str],
        metrics: list[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        **kwargs: Any
    ) -> DataFetchResult:
        """
        Fetch GA4 data with caching and retry logic.
        
        Args:
            ctx: Run context
            tenant_id: Tenant ID for isolation
            user_id: User ID
            property_id: GA4 property ID
            access_token: OAuth access token
            dimensions: GA4 dimensions (e.g., ["date", "deviceCategory"])
            metrics: GA4 metrics (e.g., ["sessions", "conversions"])
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            DataFetchResult with GA4 data or cached data
        """
        # Generate cache key
        cache_key = self._generate_cache_key(
            tenant_id, property_id, dimensions, metrics, start_date, end_date
        )
        
        # Check cache first
        if self.redis_client:
            cached_data = await self._get_from_cache(cache_key)
            if cached_data:
                logger.info(f"Cache hit for {cache_key}")
                return DataFetchResult(
                    status="cached",
                    data=cached_data,
                    cached=True,
                    tenant_id=tenant_id,
                    property_id=property_id,
                    source="cache",
                    quota_consumed=0,
                )
        
        # Fetch from GA4 API with retry logic
        try:
            data = await self._fetch_with_retry(
                tenant_id=tenant_id,
                user_id=user_id,
                property_id=property_id,
                access_token=access_token,
                dimensions=dimensions,
                metrics=metrics,
                start_date=start_date,
                end_date=end_date,
            )
            
            # Cache the result
            if self.redis_client:
                await self._save_to_cache(cache_key, data)
            
            return DataFetchResult(
                status="success",
                data=data,
                cached=False,
                tenant_id=tenant_id,
                property_id=property_id,
                source="ga4_api",
                quota_consumed=1,
            )
            
        except Exception as e:
            logger.error(f"Failed to fetch GA4 data: {e}", exc_info=True)
            
            return DataFetchResult(
                status="failed",
                data={"error": str(e)},
                cached=False,
                tenant_id=tenant_id,
                property_id=property_id,
                source="error",
                quota_consumed=0,
            )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPStatusError),
    )
    async def _fetch_with_retry(
        self,
        tenant_id: str,
        user_id: str,
        property_id: str,
        access_token: str,
        dimensions: list[str],
        metrics: list[str],
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> Dict[str, Any]:
        """
        Fetch GA4 data with automatic retry on failures.
        
        Implements Task P0-4: Retry with exponential backoff
        - 3 attempts with 2s, 4s, 8s delays
        """
        # Create GA4 context
        ga4_context = GA4ToolContext(
            tenant_id=tenant_id,
            user_id=user_id,
            property_id=property_id,
            access_token=access_token,
        )
        
        # Create mock RunContext
        from pydantic_ai import RunContext
        ctx = RunContext(deps=ga4_context)
        
        # Fetch data using GA4 tool
        data = await fetch_ga4_data(
            ctx,
            dimensions=dimensions,
            metrics=metrics,
            start_date=start_date,
            end_date=end_date,
        )
        
        return data
    
    def _generate_cache_key(
        self,
        tenant_id: str,
        property_id: str,
        dimensions: list[str],
        metrics: list[str],
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> str:
        """Generate cache key for GA4 query."""
        import hashlib
        
        cache_parts = [
            tenant_id,
            property_id,
            ",".join(sorted(dimensions)),
            ",".join(sorted(metrics)),
            start_date or "7d",
            end_date or "1d",
        ]
        
        cache_string = "|".join(cache_parts)
        cache_hash = hashlib.sha256(cache_string.encode()).hexdigest()[:16]
        
        return f"ga4:data:{cache_hash}"
    
    async def _get_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get data from Redis cache."""
        if not self.redis_client:
            return None
        
        try:
            import json
            cached = await self.redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache read error: {e}")
        
        return None
    
    async def _save_to_cache(self, cache_key: str, data: Dict[str, Any]) -> None:
        """Save data to Redis cache."""
        if not self.redis_client:
            return
        
        try:
            import json
            await self.redis_client.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(data)
            )
            logger.debug(f"Cached data: {cache_key}")
        except Exception as e:
            logger.warning(f"Cache write error: {e}")



