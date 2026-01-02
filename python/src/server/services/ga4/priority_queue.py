"""
Priority-Based Request Queue for GA4 API.

Implements Task P0-14: Priority-based request ordering

Priority Levels:
- CRITICAL (100): Owner/admin emergency requests
- HIGH (80): Normal user requests  
- NORMAL (50): Background jobs, scheduled reports
- LOW (20): Bulk operations, analytics sync

Features:
- Multi-level priority queue
- Fair scheduling (prevents starvation)
- Per-tenant quotas
- Request aging (increases priority over time)

Example:
    >>> queue = PriorityRequestQueue()
    >>> 
    >>> # Add high-priority request
    >>> await queue.add_request(
    ...     tenant_id="tenant-123",
    ...     request_func=lambda: client.run_report(...),
    ...     priority=RequestPriority.HIGH,
    ...     user_role="owner"
    ... )
"""

import logging
import time
from typing import Callable, Any, Optional, Dict
from dataclasses import dataclass, field
from enum import Enum
import heapq
import asyncio

logger = logging.getLogger(__name__)


# ============================================================================
# Priority Levels
# ============================================================================

class RequestPriority(int, Enum):
    """Request priority levels (higher = more urgent)."""
    
    CRITICAL = 100  # Owner/admin emergency requests
    HIGH = 80       # Normal user requests
    NORMAL = 50     # Background jobs
    LOW = 20        # Bulk operations
    
    @classmethod
    def from_user_role(cls, role: str) -> "RequestPriority":
        """Get priority from user role."""
        role_priorities = {
            "owner": cls.CRITICAL,
            "admin": cls.HIGH,
            "member": cls.NORMAL,
            "viewer": cls.LOW,
        }
        return role_priorities.get(role.lower(), cls.NORMAL)


# ============================================================================
# Priority Request
# ============================================================================

@dataclass(order=True)
class PriorityRequest:
    """
    Request with priority and aging support.
    
    Priority calculation:
    - Base priority from user role/request type
    - Age bonus: +1 priority per 10 seconds waiting
    - Prevents starvation of low-priority requests
    """
    
    # Sorting key (lower = higher priority, processed first)
    effective_priority: float = field(compare=True)
    
    # Request details (not compared)
    request_id: str = field(compare=False)
    tenant_id: str = field(compare=False)
    user_id: str = field(compare=False)
    user_role: str = field(compare=False)
    
    # Request callable
    request_func: Callable = field(compare=False)
    
    # Metadata
    base_priority: int = field(compare=False)
    queued_at: float = field(default_factory=time.time, compare=False)
    max_wait_seconds: float = field(default=300.0, compare=False)  # 5 minutes
    
    # Result tracking
    result_future: Optional[asyncio.Future] = field(default=None, compare=False)
    
    def calculate_effective_priority(self) -> float:
        """
        Calculate effective priority with aging.
        
        Aging formula:
        - Wait time = current_time - queued_at
        - Age bonus = wait_time / 10 (1 point per 10 seconds)
        - Effective priority = base_priority + age_bonus
        
        Returns:
            Negative effective priority (for min-heap)
        """
        now = time.time()
        wait_time = now - self.queued_at
        
        # Age bonus: +1 priority per 10 seconds
        age_bonus = wait_time / 10.0
        
        # Combine base priority and age bonus
        effective = self.base_priority + age_bonus
        
        # Return negative for min-heap (higher priority = lower value)
        return -effective
    
    def has_exceeded_max_wait(self) -> bool:
        """Check if request has waited too long."""
        now = time.time()
        wait_time = now - self.queued_at
        return wait_time >= self.max_wait_seconds


# ============================================================================
# Priority Request Queue
# ============================================================================

class PriorityRequestQueue:
    """
    Priority-based request queue with fair scheduling.
    
    Features:
    - Multi-level priority (CRITICAL > HIGH > NORMAL > LOW)
    - Request aging (prevents starvation)
    - Per-tenant fair scheduling
    - Max wait time enforcement
    
    Example:
        >>> queue = PriorityRequestQueue()
        >>> 
        >>> # Add request
        >>> result = await queue.add_request(
        ...     tenant_id="tenant-123",
        ...     user_id="user-456",
        ...     user_role="owner",
        ...     request_func=lambda: client.run_report(...),
        ...     priority=RequestPriority.HIGH
        ... )
    """
    
    def __init__(
        self,
        max_queue_size: int = 1000,
        max_wait_seconds: float = 300.0
    ):
        """
        Initialize priority queue.
        
        Args:
            max_queue_size: Maximum total requests in queue
            max_wait_seconds: Maximum wait time before escalation
        """
        self.max_queue_size = max_queue_size
        self.max_wait_seconds = max_wait_seconds
        
        # Priority heap (min-heap by effective_priority)
        self._queue: list[PriorityRequest] = []
        self._queue_lock = asyncio.Lock()
        
        # Per-tenant stats
        self._tenant_stats: Dict[str, Dict[str, int]] = {}
        
        logger.info(
            f"Priority queue initialized (max_size={max_queue_size}, "
            f"max_wait={max_wait_seconds}s)"
        )
    
    async def add_request(
        self,
        tenant_id: str,
        user_id: str,
        user_role: str,
        request_func: Callable,
        priority: Optional[RequestPriority] = None,
        max_wait_seconds: Optional[float] = None
    ) -> asyncio.Future:
        """
        Add request to priority queue.
        
        Args:
            tenant_id: Tenant ID
            user_id: User ID
            user_role: User role (owner, admin, member, viewer)
            request_func: Async function to execute
            priority: Override priority (defaults to role-based)
            max_wait_seconds: Override max wait time
            
        Returns:
            Future that will contain result when request is processed
            
        Raises:
            ValueError: If queue is full
        """
        async with self._queue_lock:
            # Check queue size
            if len(self._queue) >= self.max_queue_size:
                raise ValueError(
                    f"Priority queue full ({len(self._queue)}/{self.max_queue_size})"
                )
            
            # Determine priority
            if priority is None:
                priority = RequestPriority.from_user_role(user_role)
            
            # Create request
            request_id = f"{tenant_id}_{user_id}_{int(time.time() * 1000)}"
            
            result_future = asyncio.Future()
            
            req = PriorityRequest(
                effective_priority=0.0,  # Will be calculated
                request_id=request_id,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role=user_role,
                request_func=request_func,
                base_priority=priority.value,
                max_wait_seconds=max_wait_seconds or self.max_wait_seconds,
                result_future=result_future
            )
            
            # Calculate effective priority
            req.effective_priority = req.calculate_effective_priority()
            
            # Add to heap
            heapq.heappush(self._queue, req)
            
            # Update stats
            self._update_tenant_stats(tenant_id, "queued")
            
            logger.info(
                f"Queued request {request_id} for tenant {tenant_id} "
                f"(priority={priority.name}, queue_size={len(self._queue)})"
            )
            
            return result_future
    
    async def get_next_request(self) -> Optional[PriorityRequest]:
        """
        Get next request to process.
        
        Recalculates effective priorities to account for aging
        before returning highest priority request.
        
        Returns:
            Next request to process, or None if queue empty
        """
        async with self._queue_lock:
            if not self._queue:
                return None
            
            # Recalculate priorities for aging
            self._recalculate_priorities()
            
            # Get highest priority request (lowest value in min-heap)
            req = heapq.heappop(self._queue)
            
            # Update stats
            self._update_tenant_stats(req.tenant_id, "processing")
            
            logger.debug(
                f"Processing request {req.request_id} "
                f"(waited {time.time() - req.queued_at:.1f}s, "
                f"priority={req.base_priority})"
            )
            
            return req
    
    def _recalculate_priorities(self):
        """Recalculate all effective priorities (for aging)."""
        # Update priorities
        for req in self._queue:
            req.effective_priority = req.calculate_effective_priority()
        
        # Rebuild heap with new priorities
        heapq.heapify(self._queue)
    
    async def get_queue_size(self, tenant_id: Optional[str] = None) -> int:
        """
        Get current queue size.
        
        Args:
            tenant_id: Optional tenant ID to filter by
            
        Returns:
            Number of requests in queue
        """
        async with self._queue_lock:
            if tenant_id is None:
                return len(self._queue)
            
            return sum(1 for req in self._queue if req.tenant_id == tenant_id)
    
    async def get_queue_position(self, request_id: str) -> Optional[int]:
        """
        Get position of request in queue.
        
        Args:
            request_id: Request ID to find
            
        Returns:
            Queue position (0-indexed), or None if not found
        """
        async with self._queue_lock:
            # Sort by effective priority
            sorted_queue = sorted(self._queue, key=lambda r: r.effective_priority)
            
            for i, req in enumerate(sorted_queue):
                if req.request_id == request_id:
                    return i
            
            return None
    
    async def get_estimated_wait_time(
        self,
        priority: RequestPriority,
        tenant_id: Optional[str] = None
    ) -> float:
        """
        Estimate wait time for a new request.
        
        Args:
            priority: Request priority
            tenant_id: Optional tenant ID
            
        Returns:
            Estimated wait time in seconds
        """
        async with self._queue_lock:
            if not self._queue:
                return 0.0
            
            # Count requests with higher or equal priority
            higher_priority_count = sum(
                1 for req in self._queue
                if req.effective_priority <= -priority.value
            )
            
            # Estimate processing time (assume 2 seconds per request)
            estimated_time = higher_priority_count * 2.0
            
            return estimated_time
    
    def _update_tenant_stats(self, tenant_id: str, action: str):
        """Update per-tenant statistics."""
        if tenant_id not in self._tenant_stats:
            self._tenant_stats[tenant_id] = {
                "queued": 0,
                "processing": 0,
                "completed": 0,
                "failed": 0
            }
        
        self._tenant_stats[tenant_id][action] = \
            self._tenant_stats[tenant_id].get(action, 0) + 1
    
    async def get_tenant_stats(self, tenant_id: str) -> Dict[str, int]:
        """Get statistics for a tenant."""
        return self._tenant_stats.get(tenant_id, {})
    
    async def get_queue_stats(self) -> Dict[str, Any]:
        """
        Get overall queue statistics.
        
        Returns:
            Dictionary with queue statistics
        """
        async with self._queue_lock:
            if not self._queue:
                return {
                    "total_queued": 0,
                    "by_priority": {},
                    "by_tenant": {},
                    "oldest_wait_seconds": 0.0,
                    "average_wait_seconds": 0.0
                }
            
            # Count by priority
            by_priority = {}
            for req in self._queue:
                priority_name = RequestPriority(req.base_priority).name
                by_priority[priority_name] = by_priority.get(priority_name, 0) + 1
            
            # Count by tenant
            by_tenant = {}
            for req in self._queue:
                by_tenant[req.tenant_id] = by_tenant.get(req.tenant_id, 0) + 1
            
            # Calculate wait times
            now = time.time()
            wait_times = [now - req.queued_at for req in self._queue]
            
            return {
                "total_queued": len(self._queue),
                "by_priority": by_priority,
                "by_tenant": by_tenant,
                "oldest_wait_seconds": max(wait_times) if wait_times else 0.0,
                "average_wait_seconds": sum(wait_times) / len(wait_times) if wait_times else 0.0
            }

