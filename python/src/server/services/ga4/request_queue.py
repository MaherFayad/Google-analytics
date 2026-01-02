"""
GA4 API Request Queue with Backpressure Handling.

Implements Task P0-14: GA4 API Request Queue with Backpressure

Features:
- Per-tenant request queuing
- Intelligent backpressure (queue when quota exhausted)
- Priority-based ordering (owner > admin > member)
- Real-time queue position tracking
- Exponential backoff on 429 errors
- Automatic queue processing

Architecture:
- Redis ZSET for distributed queue (score = timestamp + priority)
- Async worker processes queue in background
- SSE updates for real-time queue position
"""

import logging
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable
from uuid import UUID, uuid4
import json

import redis.asyncio as redis
from pydantic import BaseModel, Field

from .exceptions import GA4RateLimitError, GA4APIError

logger = logging.getLogger(__name__)


class QueuedRequest(BaseModel):
    """Represents a queued GA4 API request."""
    
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    user_id: str
    user_role: str = "member"  # owner, admin, member, viewer
    
    # Request details
    endpoint: str  # e.g., "fetch_page_views"
    params: Dict[str, Any]
    
    # Queue metadata
    queued_at: float = Field(default_factory=time.time)
    priority: int = Field(default=50)  # 0-100, higher = more urgent
    retry_count: int = 0
    max_retries: int = 3
    
    # Status tracking
    status: str = "queued"  # queued, processing, completed, failed
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    def get_score(self) -> float:
        """
        Calculate queue score (lower = higher priority).
        
        Score = timestamp - priority_adjustment
        
        Priority adjustments:
        - owner: -10000 (highest priority)
        - admin: -5000
        - member: 0
        - viewer: +5000 (lowest priority)
        """
        role_adjustments = {
            "owner": -10000,
            "admin": -5000,
            "member": 0,
            "viewer": 5000
        }
        
        adjustment = role_adjustments.get(self.user_role, 0)
        adjustment += (self.priority * -100)  # Higher priority = lower score
        
        return self.queued_at + adjustment


class GA4RequestQueue:
    """
    Distributed request queue for GA4 API calls.
    
    Implements Task P0-14: Intelligent request queuing with backpressure.
    
    Features:
    - Per-tenant queuing (fair distribution)
    - Priority-based ordering
    - Automatic queue processing
    - Real-time position tracking
    - Backpressure handling
    
    Usage:
        queue = GA4RequestQueue(redis_client)
        
        # Add request to queue
        request_id = await queue.enqueue(
            tenant_id="...",
            user_id="...",
            endpoint="fetch_page_views",
            params={...}
        )
        
        # Wait for result
        result = await queue.wait_for_result(request_id, timeout=300)
    """
    
    # Queue keys in Redis
    QUEUE_KEY_PREFIX = "ga4:queue:"
    RESULT_KEY_PREFIX = "ga4:result:"
    PROCESSING_KEY_PREFIX = "ga4:processing:"
    
    # Queue processing settings
    MAX_CONCURRENT_REQUESTS = 10  # Max concurrent GA4 API calls
    PROCESSING_TIMEOUT = 60  # Seconds before request is considered stuck
    
    # Backoff settings
    INITIAL_BACKOFF = 2  # Seconds
    MAX_BACKOFF = 60  # Seconds
    BACKOFF_MULTIPLIER = 2
    
    def __init__(self, redis_client: redis.Redis):
        """
        Initialize request queue.
        
        Args:
            redis_client: Async Redis client
        """
        self.redis = redis_client
        self._workers: Dict[str, asyncio.Task] = {}
        self._shutdown = False
        
        logger.info("GA4 Request Queue initialized")
    
    async def enqueue(
        self,
        tenant_id: UUID,
        user_id: UUID,
        user_role: str,
        endpoint: str,
        params: Dict[str, Any],
        priority: int = 50
    ) -> str:
        """
        Add request to queue.
        
        Args:
            tenant_id: Tenant UUID
            user_id: User UUID
            user_role: User role (owner, admin, member, viewer)
            endpoint: GA4 API endpoint to call
            params: Request parameters
            priority: Priority 0-100 (higher = more urgent)
        
        Returns:
            Request ID for tracking
        """
        request = QueuedRequest(
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            user_role=user_role,
            endpoint=endpoint,
            params=params,
            priority=priority
        )
        
        # Add to Redis sorted set (score = priority + timestamp)
        queue_key = f"{self.QUEUE_KEY_PREFIX}{tenant_id}"
        score = request.get_score()
        
        await self.redis.zadd(
            queue_key,
            {request.request_id: score}
        )
        
        # Store request details
        await self.redis.setex(
            f"{self.RESULT_KEY_PREFIX}{request.request_id}",
            3600,  # 1 hour TTL
            request.json()
        )
        
        logger.info(
            f"Request queued: {request.request_id} for tenant {tenant_id}, "
            f"position: {await self.get_queue_position(request.request_id)}"
        )
        
        # Ensure worker is running for this tenant
        await self._ensure_worker(str(tenant_id))
        
        return request.request_id
    
    async def get_queue_position(self, request_id: str) -> int:
        """
        Get position in queue (1-indexed).
        
        Args:
            request_id: Request ID
        
        Returns:
            Queue position (1 = next to process)
        """
        # Find request in all tenant queues
        request_data = await self.redis.get(f"{self.RESULT_KEY_PREFIX}{request_id}")
        if not request_data:
            return -1
        
        request = QueuedRequest.parse_raw(request_data)
        queue_key = f"{self.QUEUE_KEY_PREFIX}{request.tenant_id}"
        
        # Get rank in sorted set (0-indexed)
        rank = await self.redis.zrank(queue_key, request_id)
        
        if rank is None:
            # Not in queue (maybe processing or completed)
            return 0
        
        return rank + 1  # Convert to 1-indexed
    
    async def get_queue_length(self, tenant_id: UUID) -> int:
        """
        Get total queue length for tenant.
        
        Args:
            tenant_id: Tenant UUID
        
        Returns:
            Number of requests in queue
        """
        queue_key = f"{self.QUEUE_KEY_PREFIX}{tenant_id}"
        return await self.redis.zcard(queue_key)
    
    async def get_estimated_wait_time(self, request_id: str) -> int:
        """
        Estimate wait time in seconds.
        
        Assumes 30 seconds per request on average.
        
        Args:
            request_id: Request ID
        
        Returns:
            Estimated wait time in seconds
        """
        position = await self.get_queue_position(request_id)
        if position <= 0:
            return 0
        
        # Estimate 30 seconds per request
        return position * 30
    
    async def wait_for_result(
        self,
        request_id: str,
        timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Wait for request result.
        
        Polls Redis for result with exponential backoff.
        
        Args:
            request_id: Request ID
            timeout: Maximum wait time in seconds
        
        Returns:
            Request result
        
        Raises:
            TimeoutError: If timeout exceeded
            GA4APIError: If request failed
        """
        start_time = time.time()
        backoff = 0.1  # Start with 100ms
        
        while time.time() - start_time < timeout:
            # Check for result
            request_data = await self.redis.get(f"{self.RESULT_KEY_PREFIX}{request_id}")
            if not request_data:
                raise GA4APIError(f"Request {request_id} not found")
            
            request = QueuedRequest.parse_raw(request_data)
            
            if request.status == "completed":
                logger.info(f"Request {request_id} completed")
                return request.result
            
            elif request.status == "failed":
                raise GA4APIError(f"Request failed: {request.error}")
            
            # Wait before next poll (exponential backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 5)  # Max 5 seconds
        
        raise TimeoutError(f"Request {request_id} timed out after {timeout}s")
    
    async def _ensure_worker(self, tenant_id: str):
        """Ensure queue worker is running for tenant."""
        if tenant_id not in self._workers or self._workers[tenant_id].done():
            worker = asyncio.create_task(self._process_queue(tenant_id))
            self._workers[tenant_id] = worker
            logger.info(f"Started queue worker for tenant {tenant_id}")
    
    async def _process_queue(self, tenant_id: str):
        """
        Background worker to process queue.
        
        Args:
            tenant_id: Tenant ID to process queue for
        """
        queue_key = f"{self.QUEUE_KEY_PREFIX}{tenant_id}"
        
        logger.info(f"Queue worker started for tenant {tenant_id}")
        
        while not self._shutdown:
            try:
                # Get next request from queue
                items = await self.redis.zpopmin(queue_key, count=1)
                
                if not items:
                    # Queue empty, wait before checking again
                    await asyncio.sleep(1)
                    
                    # Stop worker if queue still empty
                    queue_length = await self.redis.zcard(queue_key)
                    if queue_length == 0:
                        logger.info(f"Queue worker stopping for tenant {tenant_id} (empty queue)")
                        break
                    
                    continue
                
                request_id, score = items[0]
                
                # Get request details
                request_data = await self.redis.get(f"{self.RESULT_KEY_PREFIX}{request_id}")
                if not request_data:
                    logger.warning(f"Request {request_id} not found, skipping")
                    continue
                
                request = QueuedRequest.parse_raw(request_data)
                
                # Process request
                await self._process_request(request)
            
            except Exception as e:
                logger.error(f"Error in queue worker for tenant {tenant_id}: {e}", exc_info=True)
                await asyncio.sleep(1)
        
        # Clean up
        if tenant_id in self._workers:
            del self._workers[tenant_id]
        
        logger.info(f"Queue worker stopped for tenant {tenant_id}")
    
    async def _process_request(self, request: QueuedRequest):
        """
        Process a single request.
        
        Args:
            request: Queued request
        """
        logger.info(f"Processing request {request.request_id}")
        
        # Update status
        request.status = "processing"
        await self._update_request(request)
        
        try:
            # Execute GA4 API call
            # TODO: Integrate with actual GA4 client
            result = await self._execute_ga4_call(request)
            
            # Mark as completed
            request.status = "completed"
            request.result = result
            await self._update_request(request)
            
            logger.info(f"Request {request.request_id} completed successfully")
        
        except GA4RateLimitError as e:
            # Rate limit hit - requeue with backoff
            if request.retry_count < request.max_retries:
                backoff = self.INITIAL_BACKOFF * (self.BACKOFF_MULTIPLIER ** request.retry_count)
                backoff = min(backoff, self.MAX_BACKOFF)
                
                logger.warning(
                    f"Rate limit hit for request {request.request_id}, "
                    f"requeueing with {backoff}s backoff"
                )
                
                # Wait before requeueing
                await asyncio.sleep(backoff)
                
                # Requeue with increased retry count
                request.retry_count += 1
                request.status = "queued"
                await self._requeue_request(request)
            else:
                # Max retries exceeded
                request.status = "failed"
                request.error = f"Max retries exceeded: {str(e)}"
                await self._update_request(request)
                logger.error(f"Request {request.request_id} failed after max retries")
        
        except Exception as e:
            # Other error - mark as failed
            request.status = "failed"
            request.error = str(e)
            await self._update_request(request)
            logger.error(f"Request {request.request_id} failed: {e}", exc_info=True)
    
    async def _execute_ga4_call(self, request: QueuedRequest) -> Dict[str, Any]:
        """
        Execute GA4 API call.
        
        TODO: Integrate with ResilientGA4Client
        
        Args:
            request: Queued request
        
        Returns:
            API response
        """
        # Placeholder - integrate with actual GA4 client
        logger.info(f"Executing GA4 call: {request.endpoint} with params: {request.params}")
        
        # Simulate API call
        await asyncio.sleep(0.5)
        
        return {
            "success": True,
            "endpoint": request.endpoint,
            "params": request.params,
            "data": []
        }
    
    async def _update_request(self, request: QueuedRequest):
        """Update request in Redis."""
        await self.redis.setex(
            f"{self.RESULT_KEY_PREFIX}{request.request_id}",
            3600,  # 1 hour TTL
            request.json()
        )
    
    async def _requeue_request(self, request: QueuedRequest):
        """Requeue request with updated priority."""
        queue_key = f"{self.QUEUE_KEY_PREFIX}{request.tenant_id}"
        score = request.get_score()
        
        await self.redis.zadd(queue_key, {request.request_id: score})
        await self._update_request(request)
        
        # Ensure worker is running
        await self._ensure_worker(request.tenant_id)
    
    async def shutdown(self):
        """Gracefully shutdown all workers."""
        logger.info("Shutting down GA4 request queue...")
        self._shutdown = True
        
        # Wait for all workers to finish
        if self._workers:
            await asyncio.gather(*self._workers.values(), return_exceptions=True)
        
        logger.info("GA4 request queue shutdown complete")

