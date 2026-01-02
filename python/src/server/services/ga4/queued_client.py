"""
Queued GA4 Client - Integrates request queue with resilient client.

Implements Task P0-14: Integration layer between queue and GA4 API

This client automatically queues requests when quota is exhausted,
providing a seamless experience for users.
"""

import logging
from typing import Dict, Any, Optional, List
from uuid import UUID

import redis.asyncio as redis

from .request_queue import GA4RequestQueue
from .resilient_client import ResilientGA4Client
from .exceptions import GA4RateLimitError, GA4QuotaExceededError

logger = logging.getLogger(__name__)


class QueuedGA4Client:
    """
    GA4 Client with automatic request queueing.
    
    Wraps ResilientGA4Client and automatically queues requests
    when quota is exhausted or rate limits are hit.
    
    Usage:
        client = QueuedGA4Client(
            redis_client=redis_client,
            property_id="123456789",
            tenant_id=UUID("..."),
            user_id=UUID("..."),
            user_role="member"
        )
        
        # Automatically queues if quota exhausted
        result = await client.fetch_page_views(
            start_date="2025-01-01",
            end_date="2025-01-07"
        )
    """
    
    def __init__(
        self,
        redis_client: redis.Redis,
        property_id: str,
        tenant_id: UUID,
        user_id: UUID,
        user_role: str = "member",
        credentials: Optional[Dict] = None
    ):
        """
        Initialize queued GA4 client.
        
        Args:
            redis_client: Async Redis client
            property_id: GA4 property ID
            tenant_id: Tenant UUID
            user_id: User UUID
            user_role: User role (for queue priority)
            credentials: GA4 OAuth credentials
        """
        self.redis = redis_client
        self.property_id = property_id
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.user_role = user_role
        
        # Initialize queue
        self.queue = GA4RequestQueue(redis_client)
        
        # Initialize resilient client
        self.resilient_client = ResilientGA4Client(
            property_id=property_id,
            tenant_id=tenant_id,
            user_id=user_id,
            credentials=credentials
        )
    
    async def fetch_page_views(
        self,
        start_date: str,
        end_date: str,
        dimensions: Optional[List[str]] = None,
        metrics: Optional[List[str]] = None,
        use_cache: bool = True,
        priority: int = 50
    ) -> Dict[str, Any]:
        """
        Fetch page views with automatic queueing.
        
        Args:
            start_date: Start date (YYYY-MM-DD or NdaysAgo)
            end_date: End date (YYYY-MM-DD or today)
            dimensions: GA4 dimensions to include
            metrics: GA4 metrics to include
            use_cache: Whether to use cached data
            priority: Queue priority (0-100, higher = more urgent)
        
        Returns:
            GA4 API response
        """
        try:
            # Try direct API call first
            return await self.resilient_client.fetch_page_views_safe(
                start_date=start_date,
                end_date=end_date,
                dimensions=dimensions,
                metrics=metrics,
                use_cache=use_cache
            )
        
        except (GA4RateLimitError, GA4QuotaExceededError) as e:
            # Quota exhausted - queue the request
            logger.info(
                f"Quota exhausted for tenant {self.tenant_id}, queueing request: {e}"
            )
            
            request_id = await self.queue.enqueue(
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                user_role=self.user_role,
                endpoint="fetch_page_views",
                params={
                    "start_date": start_date,
                    "end_date": end_date,
                    "dimensions": dimensions,
                    "metrics": metrics,
                    "use_cache": use_cache
                },
                priority=priority
            )
            
            # Get queue position for user feedback
            position = await self.queue.get_queue_position(request_id)
            wait_time = await self.queue.get_estimated_wait_time(request_id)
            
            logger.info(
                f"Request queued: {request_id}, position: {position}, "
                f"estimated wait: {wait_time}s"
            )
            
            # Wait for result
            result = await self.queue.wait_for_result(request_id, timeout=600)
            
            return result
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """
        Get current queue status for this tenant.
        
        Returns:
            Queue statistics
        """
        queue_length = await self.queue.get_queue_length(self.tenant_id)
        
        return {
            "tenant_id": str(self.tenant_id),
            "queue_length": queue_length,
            "user_role": self.user_role
        }


async def get_queued_ga4_client(
    redis_client: redis.Redis,
    property_id: str,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str = "member",
    credentials: Optional[Dict] = None
) -> QueuedGA4Client:
    """
    Factory function to create queued GA4 client.
    
    Args:
        redis_client: Async Redis client
        property_id: GA4 property ID
        tenant_id: Tenant UUID
        user_id: User UUID
        user_role: User role
        credentials: GA4 OAuth credentials
    
    Returns:
        QueuedGA4Client instance
    """
    return QueuedGA4Client(
        redis_client=redis_client,
        property_id=property_id,
        tenant_id=tenant_id,
        user_id=user_id,
        user_role=user_role,
        credentials=credentials
    )

