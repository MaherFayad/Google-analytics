"""
Rate Limit Backoff Queue for GA4 API.

Implements Task P0-14: Rate Limit Backoff Queue for GA4 API [HIGH]

When GA4 API returns 429 (Too Many Requests), this module:
1. Queues the request instead of failing
2. Applies exponential backoff (2x, 4x, 8x delays)
3. Retries with intelligent backoff timing
4. Tracks rate limit state per tenant

Features:
- Intelligent request queuing on 429 errors
- Exponential backoff: 2s → 4s → 8s → 16s
- Per-tenant rate limit tracking
- Priority-based request ordering
- Automatic retry with backoff
- Queue health metrics for monitoring

Integration with ResilientGA4Client:

```python
from server.services.ga4.rate_limiter import RateLimiter

# Initialize rate limiter
rate_limiter = RateLimiter()

# Make rate-limited request
try:
    result = await rate_limiter.execute(
        tenant_id="tenant-123",
        request_func=lambda: client.run_report(...),
        priority=80
    )
except RateLimitExceeded:
    # Queue is full or max backoff reached
    raise
```
"""

import logging
import asyncio
import time
from typing import Callable, Any, Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from uuid import uuid4
import heapq

from prometheus_client import Counter, Histogram, Gauge

logger = logging.getLogger(__name__)


# ============================================================================
# Prometheus Metrics
# ============================================================================

rate_limit_hits_total = Counter(
    'ga4_rate_limit_hits_total',
    'Total number of 429 rate limit responses',
    ['tenant_id', 'endpoint']
)

rate_limit_queue_size = Gauge(
    'ga4_rate_limit_queue_size',
    'Number of requests in rate limit queue',
    ['tenant_id']
)

rate_limit_backoff_duration_seconds = Histogram(
    'ga4_rate_limit_backoff_duration_seconds',
    'Duration of rate limit backoff periods',
    ['tenant_id'],
    buckets=(1, 2, 4, 8, 16, 32, 64, 128, 256)
)

rate_limit_retries_total = Counter(
    'ga4_rate_limit_retries_total',
    'Total number of request retries after rate limit',
    ['tenant_id', 'success']  # success: 'true' or 'false'
)

rate_limit_queue_wait_seconds = Histogram(
    'ga4_rate_limit_queue_wait_seconds',
    'Time spent waiting in rate limit queue',
    ['tenant_id'],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600)
)


# ============================================================================
# Exceptions
# ============================================================================

class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded and queue is full."""
    pass


class MaxBackoffReached(Exception):
    """Raised when maximum backoff time is reached."""
    pass


# ============================================================================
# Request Priority
# ============================================================================

class RequestPriority(int, Enum):
    """Request priority levels."""
    CRITICAL = 100  # Owner/admin requests
    HIGH = 80       # Normal user requests
    NORMAL = 50     # Background jobs
    LOW = 20        # Bulk operations


# ============================================================================
# Rate Limit State
# ============================================================================

@dataclass
class RateLimitState:
    """Tracks rate limit state for a tenant."""
    
    tenant_id: str
    
    # Rate limit tracking
    is_rate_limited: bool = False
    rate_limit_until: Optional[datetime] = None
    consecutive_429s: int = 0
    
    # Backoff calculation
    current_backoff_seconds: float = 2.0  # Start at 2 seconds
    max_backoff_seconds: float = 256.0    # Max 256 seconds (4+ minutes)
    backoff_multiplier: float = 2.0       # Double each time
    
    # Queue stats
    queued_requests: int = 0
    completed_requests: int = 0
    failed_requests: int = 0
    
    # Last update
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    def record_429(self):
        """Record a 429 rate limit response."""
        self.consecutive_429s += 1
        self.is_rate_limited = True
        
        # Calculate backoff time (exponential)
        self.current_backoff_seconds = min(
            self.current_backoff_seconds * self.backoff_multiplier,
            self.max_backoff_seconds
        )
        
        # Set rate limit until time
        self.rate_limit_until = datetime.utcnow() + timedelta(
            seconds=self.current_backoff_seconds
        )
        
        self.last_updated = datetime.utcnow()
        
        logger.warning(
            f"Rate limit hit for tenant {self.tenant_id}. "
            f"Backoff: {self.current_backoff_seconds:.1f}s, "
            f"Consecutive 429s: {self.consecutive_429s}"
        )
    
    def record_success(self):
        """Record a successful request (resets backoff)."""
        self.consecutive_429s = 0
        self.is_rate_limited = False
        self.rate_limit_until = None
        self.current_backoff_seconds = 2.0  # Reset to initial
        self.completed_requests += 1
        self.last_updated = datetime.utcnow()
    
    def record_failure(self):
        """Record a failed request (non-429 error)."""
        self.failed_requests += 1
        self.last_updated = datetime.utcnow()
    
    def is_ready(self) -> bool:
        """Check if we can make a request (backoff period ended)."""
        if not self.is_rate_limited:
            return True
        
        if self.rate_limit_until is None:
            return True
        
        now = datetime.utcnow()
        return now >= self.rate_limit_until
    
    def time_until_ready(self) -> Optional[float]:
        """Get seconds until ready to make requests."""
        if self.is_ready():
            return 0.0
        
        if self.rate_limit_until is None:
            return None
        
        now = datetime.utcnow()
        delta = self.rate_limit_until - now
        return max(0.0, delta.total_seconds())


# ============================================================================
# Queued Request
# ============================================================================

@dataclass(order=True)
class QueuedRequest:
    """Represents a request waiting in the rate limit queue."""
    
    # Priority for heap ordering (lower = higher priority)
    priority: float = field(compare=True)
    
    # Request details (not compared)
    request_id: str = field(default_factory=lambda: str(uuid4()), compare=False)
    tenant_id: str = field(default="", compare=False)
    request_func: Optional[Callable] = field(default=None, compare=False)
    
    # Timing
    queued_at: float = field(default_factory=time.time, compare=False)
    retry_count: int = field(default=0, compare=False)
    max_retries: int = field(default=3, compare=False)
    
    # Result tracking
    result_future: Optional[asyncio.Future] = field(default=None, compare=False)


# ============================================================================
# Rate Limiter
# ============================================================================

class RateLimiter:
    """
    Intelligent rate limiter with exponential backoff queue.
    
    When GA4 API returns 429, this rate limiter:
    1. Queues the request instead of failing immediately
    2. Applies exponential backoff (2s → 4s → 8s → 16s → ...)
    3. Retries requests automatically when backoff period ends
    4. Tracks per-tenant rate limit state
    
    Features:
    - Exponential backoff with configurable multiplier
    - Priority-based request queue (heap)
    - Per-tenant rate limit tracking
    - Automatic queue processing
    - Prometheus metrics
    
    Example:
        >>> limiter = RateLimiter()
        >>> 
        >>> # Execute with rate limiting
        >>> result = await limiter.execute(
        ...     tenant_id="tenant-123",
        ...     request_func=lambda: client.run_report(...),
        ...     priority=RequestPriority.HIGH
        ... )
    """
    
    def __init__(
        self,
        max_queue_size: int = 1000,
        worker_count: int = 5
    ):
        """
        Initialize rate limiter.
        
        Args:
            max_queue_size: Maximum requests in queue per tenant
            worker_count: Number of worker tasks processing queue
        """
        self.max_queue_size = max_queue_size
        self.worker_count = worker_count
        
        # Per-tenant state tracking
        self._states: Dict[str, RateLimitState] = {}
        self._state_lock = asyncio.Lock()
        
        # Priority queue (min-heap)
        self._queue: List[QueuedRequest] = []
        self._queue_lock = asyncio.Lock()
        
        # Worker tasks
        self._workers: List[asyncio.Task] = []
        self._is_running = False
        
        logger.info(
            f"Rate limiter initialized (max_queue={max_queue_size}, "
            f"workers={worker_count})"
        )
    
    async def start(self):
        """Start queue processing workers."""
        if self._is_running:
            logger.warning("Rate limiter already running")
            return
        
        self._is_running = True
        
        # Start worker tasks
        for i in range(self.worker_count):
            worker = asyncio.create_task(self._worker_loop(i))
            self._workers.append(worker)
        
        logger.info(f"Started {self.worker_count} rate limiter workers")
    
    async def stop(self):
        """Stop queue processing workers."""
        if not self._is_running:
            return
        
        self._is_running = False
        
        # Cancel all workers
        for worker in self._workers:
            worker.cancel()
        
        # Wait for workers to finish
        await asyncio.gather(*self._workers, return_exceptions=True)
        
        self._workers.clear()
        logger.info("Rate limiter workers stopped")
    
    async def execute(
        self,
        tenant_id: str,
        request_func: Callable,
        priority: int = RequestPriority.NORMAL,
        max_retries: int = 3
    ) -> Any:
        """
        Execute request with rate limiting.
        
        If rate limit is hit (429), request is queued and retried
        with exponential backoff.
        
        Args:
            tenant_id: Tenant ID
            request_func: Async function to execute
            priority: Request priority (0-100, higher = more urgent)
            max_retries: Maximum retry attempts
            
        Returns:
            Result from request_func
            
        Raises:
            RateLimitExceeded: If queue is full
            MaxBackoffReached: If max backoff time reached
            
        Example:
            >>> result = await limiter.execute(
            ...     tenant_id="tenant-123",
            ...     request_func=lambda: client.run_report(...),
            ...     priority=80
            ... )
        """
        # Get or create state for tenant
        state = await self._get_state(tenant_id)
        
        # Check if currently rate limited
        if state.is_rate_limited and not state.is_ready():
            # Queue request instead of executing immediately
            logger.info(
                f"Queuing request for tenant {tenant_id} "
                f"(rate limited for {state.time_until_ready():.1f}s)"
            )
            
            return await self._queue_request(
                tenant_id=tenant_id,
                request_func=request_func,
                priority=priority,
                max_retries=max_retries
            )
        
        # Execute request
        try:
            result = await self._execute_with_retry(
                tenant_id=tenant_id,
                request_func=request_func,
                state=state,
                max_retries=max_retries
            )
            
            # Record success
            state.record_success()
            
            return result
        
        except Exception as e:
            # Check if it's a 429 rate limit error
            if self._is_rate_limit_error(e):
                # Record 429 and queue request
                state.record_429()
                
                rate_limit_hits_total.labels(
                    tenant_id=tenant_id,
                    endpoint="unknown"
                ).inc()
                
                rate_limit_backoff_duration_seconds.labels(
                    tenant_id=tenant_id
                ).observe(state.current_backoff_seconds)
                
                # Queue for retry
                return await self._queue_request(
                    tenant_id=tenant_id,
                    request_func=request_func,
                    priority=priority,
                    max_retries=max_retries
                )
            else:
                # Non-429 error
                state.record_failure()
                raise
    
    async def _execute_with_retry(
        self,
        tenant_id: str,
        request_func: Callable,
        state: RateLimitState,
        max_retries: int
    ) -> Any:
        """Execute request with retry logic."""
        last_error = None
        
        for attempt in range(max_retries):
            try:
                result = await request_func()
                
                # Success
                if attempt > 0:
                    rate_limit_retries_total.labels(
                        tenant_id=tenant_id,
                        success="true"
                    ).inc()
                
                return result
            
            except Exception as e:
                last_error = e
                
                if not self._is_rate_limit_error(e):
                    # Non-rate-limit error, don't retry
                    raise
                
                # Rate limit hit
                if attempt < max_retries - 1:
                    # Wait before retry
                    wait_time = state.current_backoff_seconds
                    logger.info(
                        f"Rate limit hit (attempt {attempt + 1}/{max_retries}). "
                        f"Waiting {wait_time:.1f}s"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    # Max retries reached
                    rate_limit_retries_total.labels(
                        tenant_id=tenant_id,
                        success="false"
                    ).inc()
                    raise last_error
        
        # Should not reach here
        raise last_error
    
    async def _queue_request(
        self,
        tenant_id: str,
        request_func: Callable,
        priority: int,
        max_retries: int
    ) -> Any:
        """Queue request for later execution."""
        async with self._queue_lock:
            # Check queue size
            tenant_queue_size = sum(
                1 for req in self._queue if req.tenant_id == tenant_id
            )
            
            if tenant_queue_size >= self.max_queue_size:
                raise RateLimitExceeded(
                    f"Rate limit queue full for tenant {tenant_id} "
                    f"({tenant_queue_size}/{self.max_queue_size})"
                )
            
            # Create queued request
            result_future = asyncio.Future()
            
            queued_req = QueuedRequest(
                priority=-priority,  # Negate for min-heap (higher priority = lower value)
                tenant_id=tenant_id,
                request_func=request_func,
                max_retries=max_retries,
                result_future=result_future
            )
            
            # Add to priority queue
            heapq.heappush(self._queue, queued_req)
            
            # Update metrics
            rate_limit_queue_size.labels(tenant_id=tenant_id).set(tenant_queue_size + 1)
            
            logger.info(
                f"Queued request {queued_req.request_id} for tenant {tenant_id} "
                f"(priority={priority}, queue_size={tenant_queue_size + 1})"
            )
        
        # Wait for result
        return await result_future
    
    async def _worker_loop(self, worker_id: int):
        """Worker task that processes queued requests."""
        logger.info(f"Rate limiter worker {worker_id} started")
        
        while self._is_running:
            try:
                # Get next request from queue
                queued_req = await self._get_next_ready_request()
                
                if queued_req is None:
                    # No requests ready, wait briefly
                    await asyncio.sleep(0.5)
                    continue
                
                # Execute request
                tenant_id = queued_req.tenant_id
                state = await self._get_state(tenant_id)
                
                try:
                    # Calculate wait time
                    wait_time = time.time() - queued_req.queued_at
                    rate_limit_queue_wait_seconds.labels(tenant_id=tenant_id).observe(wait_time)
                    
                    logger.info(
                        f"Worker {worker_id} processing request {queued_req.request_id} "
                        f"(waited {wait_time:.1f}s)"
                    )
                    
                    # Execute
                    result = await self._execute_with_retry(
                        tenant_id=tenant_id,
                        request_func=queued_req.request_func,
                        state=state,
                        max_retries=queued_req.max_retries
                    )
                    
                    # Success
                    state.record_success()
                    queued_req.result_future.set_result(result)
                    
                    logger.info(f"Request {queued_req.request_id} completed successfully")
                
                except Exception as e:
                    # Failed
                    state.record_failure()
                    queued_req.result_future.set_exception(e)
                    
                    logger.error(
                        f"Request {queued_req.request_id} failed: {e}",
                        exc_info=True
                    )
            
            except asyncio.CancelledError:
                logger.info(f"Rate limiter worker {worker_id} cancelled")
                break
            except Exception as e:
                logger.error(f"Error in worker {worker_id}: {e}", exc_info=True)
                await asyncio.sleep(1)  # Brief pause before continuing
        
        logger.info(f"Rate limiter worker {worker_id} stopped")
    
    async def _get_next_ready_request(self) -> Optional[QueuedRequest]:
        """Get next request that's ready to execute (backoff period ended)."""
        async with self._queue_lock:
            # Find first request whose tenant is ready
            for i, req in enumerate(self._queue):
                state = self._states.get(req.tenant_id)
                
                if state is None or state.is_ready():
                    # Remove from queue
                    del self._queue[i]
                    heapq.heapify(self._queue)  # Rebuild heap
                    
                    # Update metrics
                    queue_size = sum(1 for r in self._queue if r.tenant_id == req.tenant_id)
                    rate_limit_queue_size.labels(tenant_id=req.tenant_id).set(queue_size)
                    
                    return req
            
            return None
    
    async def _get_state(self, tenant_id: str) -> RateLimitState:
        """Get or create rate limit state for tenant."""
        async with self._state_lock:
            if tenant_id not in self._states:
                self._states[tenant_id] = RateLimitState(tenant_id=tenant_id)
            
            return self._states[tenant_id]
    
    def _is_rate_limit_error(self, error: Exception) -> bool:
        """Check if error is a 429 rate limit error."""
        # Check exception type
        if isinstance(error, Exception):
            error_name = type(error).__name__
            if "RateLimit" in error_name or "429" in str(error):
                return True
        
        # Check HTTP status code if available
        if hasattr(error, "status_code") and error.status_code == 429:
            return True
        
        # Check error message
        error_msg = str(error).lower()
        if "429" in error_msg or "rate limit" in error_msg or "too many requests" in error_msg:
            return True
        
        return False
    
    async def get_state_info(self, tenant_id: str) -> Dict[str, Any]:
        """Get rate limit state information for tenant."""
        state = await self._get_state(tenant_id)
        
        return {
            "tenant_id": tenant_id,
            "is_rate_limited": state.is_rate_limited,
            "consecutive_429s": state.consecutive_429s,
            "current_backoff_seconds": state.current_backoff_seconds,
            "time_until_ready_seconds": state.time_until_ready(),
            "queued_requests": state.queued_requests,
            "completed_requests": state.completed_requests,
            "failed_requests": state.failed_requests,
            "last_updated": state.last_updated.isoformat(),
        }


# ============================================================================
# Global Rate Limiter Instance
# ============================================================================

_rate_limiter: Optional[RateLimiter] = None


async def get_rate_limiter() -> RateLimiter:
    """Get global rate limiter instance."""
    global _rate_limiter
    
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
        await _rate_limiter.start()
    
    return _rate_limiter


async def stop_rate_limiter():
    """Stop global rate limiter."""
    global _rate_limiter
    
    if _rate_limiter is not None:
        await _rate_limiter.stop()
        _rate_limiter = None

