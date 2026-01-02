"""
Queue Position Tracker with Real-Time SSE Streaming.

Implements Task P0-31: Real-Time Queue Position Streaming via SSE

Features:
- Track request position in queue
- Calculate estimated wait time
- Stream position updates via SSE
- Integration with existing GA4RequestQueue

Usage:
    tracker = QueueTracker(redis_client, request_queue)
    
    async for update in tracker.stream_queue_updates(request_id):
        # Yields position updates every 5 seconds
        yield f"event: queue_status\ndata: {json.dumps(update)}\n\n"
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Any, AsyncGenerator, Optional
import json

import redis.asyncio as redis
from pydantic import BaseModel, Field

from .request_queue import GA4RequestQueue

logger = logging.getLogger(__name__)


class QueueStatus(BaseModel):
    """Queue status for a specific request."""
    
    request_id: str
    position: int = Field(description="Position in queue (1 = next)")
    total_queue: int = Field(description="Total number of requests in queue")
    eta_seconds: int = Field(description="Estimated wait time in seconds")
    status: str = Field(description="Request status (queued, processing, completed, failed)")
    message: str = Field(description="Human-readable status message")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class QueueTracker:
    """
    Tracks queue position and streams real-time updates.
    
    Implements Task P0-31: Real-Time Queue Position Streaming
    
    Integrates with GA4RequestQueue to provide:
    - Real-time position tracking
    - ETA calculations
    - SSE streaming updates
    - User-friendly status messages
    
    Usage:
        tracker = QueueTracker(redis_client, request_queue)
        
        # Stream position updates
        async for status in tracker.stream_queue_updates(request_id):
            yield f"event: queue_status\ndata: {status.json()}\n\n"
    """
    
    # Update interval
    UPDATE_INTERVAL_SECONDS = 5  # Update position every 5 seconds
    
    # ETA calculations
    AVG_REQUEST_TIME_SECONDS = 30  # Average time per request
    
    def __init__(
        self,
        redis_client: redis.Redis,
        request_queue: GA4RequestQueue
    ):
        """
        Initialize queue tracker.
        
        Args:
            redis_client: Async Redis client
            request_queue: GA4RequestQueue instance
        """
        self.redis = redis_client
        self.queue = request_queue
        logger.info("Queue tracker initialized")
    
    async def get_queue_status(self, request_id: str) -> QueueStatus:
        """
        Get current queue status for a request.
        
        Args:
            request_id: Request ID to track
        
        Returns:
            QueueStatus with position, ETA, and message
        """
        # Get position from queue
        position = await self.queue.get_queue_position(request_id)
        
        # Get request details from Redis
        request_data = await self.redis.get(f"{self.queue.RESULT_KEY_PREFIX}{request_id}")
        
        if not request_data:
            return QueueStatus(
                request_id=request_id,
                position=0,
                total_queue=0,
                eta_seconds=0,
                status="not_found",
                message="Request not found"
            )
        
        # Parse request
        from .request_queue import QueuedRequest
        request = QueuedRequest.parse_raw(request_data)
        
        # Get queue length
        queue_length = await self.queue.get_queue_length(request.tenant_id)
        
        # Calculate ETA
        eta_seconds = await self._calculate_eta(request_id, position)
        
        # Generate user-friendly message
        message = self._generate_status_message(request.status, position, eta_seconds)
        
        return QueueStatus(
            request_id=request_id,
            position=position,
            total_queue=queue_length,
            eta_seconds=eta_seconds,
            status=request.status,
            message=message
        )
    
    async def stream_queue_updates(
        self,
        request_id: str,
        max_duration: int = 600  # 10 minutes max
    ) -> AsyncGenerator[QueueStatus, None]:
        """
        Stream real-time queue position updates.
        
        Yields position updates every UPDATE_INTERVAL_SECONDS until
        request is completed or max_duration is reached.
        
        Args:
            request_id: Request ID to track
            max_duration: Maximum streaming duration in seconds
        
        Yields:
            QueueStatus updates
        """
        start_time = time.time()
        last_position = None
        
        logger.info(f"Starting queue position streaming for request {request_id}")
        
        while time.time() - start_time < max_duration:
            try:
                # Get current status
                status = await self.get_queue_status(request_id)
                
                # Yield update if position changed or status changed
                if (status.position != last_position or
                    status.status in ("completed", "failed", "processing")):
                    
                    logger.debug(
                        f"Queue update for {request_id}: position={status.position}, "
                        f"eta={status.eta_seconds}s, status={status.status}"
                    )
                    
                    yield status
                    last_position = status.position
                
                # Stop streaming if request is completed or failed
                if status.status in ("completed", "failed", "not_found"):
                    logger.info(
                        f"Stopping queue streaming for {request_id}: status={status.status}"
                    )
                    break
                
                # Wait before next update
                await asyncio.sleep(self.UPDATE_INTERVAL_SECONDS)
            
            except asyncio.CancelledError:
                logger.info(f"Queue streaming cancelled for {request_id}")
                break
            
            except Exception as e:
                logger.error(f"Error streaming queue updates for {request_id}: {e}", exc_info=True)
                await asyncio.sleep(self.UPDATE_INTERVAL_SECONDS)
        
        logger.info(f"Queue position streaming ended for request {request_id}")
    
    async def _calculate_eta(self, request_id: str, position: int) -> int:
        """
        Calculate estimated wait time.
        
        Uses exponentially weighted moving average of recent request times
        if available, otherwise falls back to AVG_REQUEST_TIME_SECONDS.
        
        Args:
            request_id: Request ID
            position: Current position in queue
        
        Returns:
            Estimated wait time in seconds
        """
        if position <= 0:
            return 0
        
        # TODO: Implement exponentially weighted moving average
        # For now, use simple calculation
        return position * self.AVG_REQUEST_TIME_SECONDS
    
    def _generate_status_message(
        self,
        status: str,
        position: int,
        eta_seconds: int
    ) -> str:
        """
        Generate human-readable status message.
        
        Args:
            status: Request status
            position: Queue position
            eta_seconds: Estimated wait time
        
        Returns:
            User-friendly message
        """
        if status == "completed":
            return "Request completed successfully"
        
        elif status == "failed":
            return "Request failed"
        
        elif status == "processing":
            return "Processing your request..."
        
        elif status == "queued":
            if position <= 0:
                return "Request not in queue"
            
            elif position == 1:
                return "Next in queue - processing shortly"
            
            else:
                # Format ETA
                if eta_seconds < 60:
                    eta_str = f"{eta_seconds} seconds"
                elif eta_seconds < 3600:
                    minutes = eta_seconds // 60
                    eta_str = f"{minutes} minute" + ("s" if minutes != 1 else "")
                else:
                    hours = eta_seconds // 3600
                    minutes = (eta_seconds % 3600) // 60
                    eta_str = f"{hours} hour" + ("s" if hours != 1 else "") + f" {minutes} minutes"
                
                return f"Position {position} in queue • Estimated wait: {eta_str}"
        
        return "Unknown status"


def format_queue_status_sse(status: QueueStatus) -> str:
    """
    Format queue status as SSE event.
    
    Args:
        status: QueueStatus to format
    
    Returns:
        SSE-formatted event string
    """
    return f"event: queue_status\ndata: {status.json()}\n\n"


async def stream_queue_position_to_sse(
    request_id: str,
    tracker: QueueTracker
) -> AsyncGenerator[str, None]:
    """
    Stream queue position updates as SSE events.
    
    Convenience function for SSE endpoints.
    
    Args:
        request_id: Request ID to track
        tracker: QueueTracker instance
    
    Yields:
        SSE-formatted event strings
    """
    async for status in tracker.stream_queue_updates(request_id):
        yield format_queue_status_sse(status)

