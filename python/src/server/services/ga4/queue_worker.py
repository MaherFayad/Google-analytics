"""
Queue Worker Manager for GA4 API Request Processing.

Implements Task P0-14: Background workers for queue processing

Features:
- Multiple concurrent workers per tenant
- Automatic scaling based on queue length
- Health monitoring
- Graceful shutdown
"""

import logging
import asyncio
from typing import Dict, Set
from uuid import UUID

import redis.asyncio as redis

from .request_queue import GA4RequestQueue

logger = logging.getLogger(__name__)


class QueueWorkerManager:
    """
    Manages background workers for GA4 request queue processing.
    
    Features:
    - Auto-scaling workers based on queue length
    - Health monitoring
    - Graceful shutdown
    - Per-tenant worker pools
    
    Usage:
        manager = QueueWorkerManager(redis_client)
        await manager.start()
        
        # Workers automatically process queued requests
        
        await manager.shutdown()
    """
    
    # Worker scaling settings
    MIN_WORKERS_PER_TENANT = 1
    MAX_WORKERS_PER_TENANT = 5
    REQUESTS_PER_WORKER = 10  # Scale up when queue > this threshold
    
    # Health check settings
    HEALTH_CHECK_INTERVAL = 30  # Seconds
    
    def __init__(self, redis_client: redis.Redis):
        """
        Initialize worker manager.
        
        Args:
            redis_client: Async Redis client
        """
        self.redis = redis_client
        self.queue = GA4RequestQueue(redis_client)
        
        self._workers: Dict[str, Set[asyncio.Task]] = {}
        self._health_check_task: Optional[asyncio.Task] = None
        self._shutdown = False
        
        logger.info("Queue Worker Manager initialized")
    
    async def start(self):
        """Start worker manager and health monitoring."""
        logger.info("Starting Queue Worker Manager...")
        
        # Start health check task
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        logger.info("Queue Worker Manager started")
    
    async def shutdown(self):
        """Gracefully shutdown all workers."""
        logger.info("Shutting down Queue Worker Manager...")
        self._shutdown = True
        
        # Cancel health check
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # Shutdown queue
        await self.queue.shutdown()
        
        # Wait for all workers
        all_workers = []
        for worker_set in self._workers.values():
            all_workers.extend(worker_set)
        
        if all_workers:
            await asyncio.gather(*all_workers, return_exceptions=True)
        
        logger.info("Queue Worker Manager shutdown complete")
    
    async def _health_check_loop(self):
        """Periodically check worker health and scale as needed."""
        while not self._shutdown:
            try:
                await self._check_and_scale_workers()
                await asyncio.sleep(self.HEALTH_CHECK_INTERVAL)
            
            except asyncio.CancelledError:
                break
            
            except Exception as e:
                logger.error(f"Error in health check loop: {e}", exc_info=True)
                await asyncio.sleep(self.HEALTH_CHECK_INTERVAL)
    
    async def _check_and_scale_workers(self):
        """Check worker health and scale based on queue length."""
        # Get all tenant queues
        queue_pattern = f"{GA4RequestQueue.QUEUE_KEY_PREFIX}*"
        tenant_queues = []
        
        async for key in self.redis.scan_iter(match=queue_pattern):
            tenant_id = key.decode().split(":")[-1]
            queue_length = await self.queue.get_queue_length(UUID(tenant_id))
            
            if queue_length > 0:
                tenant_queues.append((tenant_id, queue_length))
        
        # Scale workers for each tenant
        for tenant_id, queue_length in tenant_queues:
            await self._scale_workers_for_tenant(tenant_id, queue_length)
        
        # Clean up workers for empty queues
        for tenant_id in list(self._workers.keys()):
            if tenant_id not in [t[0] for t in tenant_queues]:
                await self._remove_tenant_workers(tenant_id)
    
    async def _scale_workers_for_tenant(self, tenant_id: str, queue_length: int):
        """
        Scale workers for tenant based on queue length.
        
        Args:
            tenant_id: Tenant ID
            queue_length: Current queue length
        """
        # Calculate desired worker count
        desired_workers = min(
            max(
                self.MIN_WORKERS_PER_TENANT,
                queue_length // self.REQUESTS_PER_WORKER
            ),
            self.MAX_WORKERS_PER_TENANT
        )
        
        # Get current worker count
        current_workers = len(self._workers.get(tenant_id, set()))
        
        if desired_workers > current_workers:
            # Scale up
            to_add = desired_workers - current_workers
            logger.info(
                f"Scaling up workers for tenant {tenant_id}: "
                f"{current_workers} -> {desired_workers} (queue: {queue_length})"
            )
            
            for _ in range(to_add):
                await self._add_worker(tenant_id)
        
        elif desired_workers < current_workers:
            # Scale down
            to_remove = current_workers - desired_workers
            logger.info(
                f"Scaling down workers for tenant {tenant_id}: "
                f"{current_workers} -> {desired_workers} (queue: {queue_length})"
            )
            
            for _ in range(to_remove):
                await self._remove_worker(tenant_id)
    
    async def _add_worker(self, tenant_id: str):
        """Add a worker for tenant."""
        if tenant_id not in self._workers:
            self._workers[tenant_id] = set()
        
        worker = asyncio.create_task(self.queue._process_queue(tenant_id))
        self._workers[tenant_id].add(worker)
        
        # Remove worker from set when done
        worker.add_done_callback(
            lambda t: self._workers.get(tenant_id, set()).discard(t)
        )
    
    async def _remove_worker(self, tenant_id: str):
        """Remove a worker for tenant."""
        if tenant_id not in self._workers or not self._workers[tenant_id]:
            return
        
        # Cancel one worker
        worker = self._workers[tenant_id].pop()
        worker.cancel()
        
        try:
            await worker
        except asyncio.CancelledError:
            pass
    
    async def _remove_tenant_workers(self, tenant_id: str):
        """Remove all workers for tenant."""
        if tenant_id not in self._workers:
            return
        
        logger.info(f"Removing all workers for tenant {tenant_id}")
        
        workers = self._workers.pop(tenant_id)
        for worker in workers:
            worker.cancel()
        
        await asyncio.gather(*workers, return_exceptions=True)
    
    async def get_stats(self) -> Dict:
        """
        Get worker manager statistics.
        
        Returns:
            Dict with worker stats
        """
        total_workers = sum(len(workers) for workers in self._workers.values())
        
        tenant_stats = {}
        for tenant_id, workers in self._workers.items():
            queue_length = await self.queue.get_queue_length(UUID(tenant_id))
            tenant_stats[tenant_id] = {
                "workers": len(workers),
                "queue_length": queue_length
            }
        
        return {
            "total_workers": total_workers,
            "active_tenants": len(self._workers),
            "tenant_stats": tenant_stats
        }

