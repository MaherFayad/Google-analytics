"""
Example SSE Endpoint with Graceful Shutdown

Implements Task P0-20: Graceful SSE Connection Shutdown

Demonstrates proper SSE connection handling with graceful shutdown support.
"""

import asyncio
import logging
import json
import uuid
from datetime import datetime
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, status, Query
from sse_starlette.sse import EventSourceResponse

from ...core.connection_manager import connection_manager

logger = logging.getLogger(__name__)
router = APIRouter()


async def generate_events(
    connection_id: str,
    tenant_id: str,
    duration: int = 60
) -> AsyncGenerator:
    """
    Generate SSE events with shutdown awareness.
    
    Args:
        connection_id: Unique connection identifier
        tenant_id: Tenant ID
        duration: Max duration in seconds
        
    Yields:
        SSE events
    """
    start_time = asyncio.get_event_loop().time()
    counter = 0
    
    try:
        while asyncio.get_event_loop().time() - start_time < duration:
            # Check if server is shutting down
            if connection_manager.is_shutting_down:
                logger.info(f"Connection {connection_id}: Server shutting down, notifying client")
                
                # Send shutdown notification
                yield connection_manager.get_shutdown_notification_event(reconnect_delay=30)
                
                # Allow client to receive the message before closing
                await asyncio.sleep(0.5)
                break
            
            # Send regular status event
            counter += 1
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": "status",
                    "message": f"Event {counter}",
                    "connection_id": connection_id,
                    "timestamp": datetime.now().isoformat()
                })
            }
            
            # Wait between events
            await asyncio.sleep(2)
        
        # Send completion event if not shutting down
        if not connection_manager.is_shutting_down:
            yield {
                "event": "complete",
                "data": json.dumps({
                    "type": "complete",
                    "message": "Stream completed",
                    "total_events": counter,
                    "timestamp": datetime.now().isoformat()
                })
            }
    
    except asyncio.CancelledError:
        logger.info(f"Connection {connection_id}: Cancelled")
        raise
    
    except Exception as e:
        logger.error(f"Connection {connection_id}: Error: {e}", exc_info=True)
        yield {
            "event": "error",
            "data": json.dumps({
                "type": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat()
            })
        }


@router.get("/stream/example")
async def stream_example(
    tenant_id: str = Query(..., description="Tenant ID"),
    duration: int = Query(60, ge=1, le=300, description="Stream duration in seconds")
):
    """
    Example SSE endpoint with graceful shutdown support.
    
    Demonstrates:
    - Connection registration with connection manager
    - Shutdown notification handling
    - Proper cleanup
    
    **Features:**
    - Sends status events every 2 seconds
    - Notifies client when server is shutting down
    - Auto-closes after specified duration
    
    **Usage:**
    ```javascript
    const eventSource = new EventSource('/api/v1/stream/example?tenant_id=tenant-123');
    
    eventSource.addEventListener('message', (e) => {
        const data = JSON.parse(e.data);
        console.log('Status:', data.message);
    });
    
    eventSource.addEventListener('shutdown', (e) => {
        const data = JSON.parse(e.data);
        console.log('Server shutting down:', data.message);
        // Reconnect after delay
        setTimeout(() => {
            // Create new EventSource
        }, data.reconnect_delay_seconds * 1000);
    });
    ```
    """
    # Check if server is shutting down
    if connection_manager.is_shutting_down:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server is shutting down. Please reconnect in 30 seconds."
        )
    
    # Generate unique connection ID
    connection_id = str(uuid.uuid4())
    
    logger.info(
        f"New SSE connection: {connection_id} "
        f"(tenant={tenant_id}, duration={duration}s)"
    )
    
    # Create event generator with connection tracking
    async def event_generator():
        async with connection_manager.track_connection(
            connection_id=connection_id,
            tenant_id=tenant_id,
            endpoint="/stream/example",
            metadata={"duration": duration}
        ):
            async for event in generate_events(connection_id, tenant_id, duration):
                yield event
    
    return EventSourceResponse(event_generator())


@router.get("/stream/status")
async def stream_status():
    """
    Get SSE connection status and statistics.
    
    Returns:
        Connection statistics including active connections,
        shutdown status, and per-endpoint/tenant breakdown
    """
    stats = connection_manager.get_stats()
    
    return {
        "status": "shutting_down" if stats["is_shutting_down"] else "operational",
        "active_connections": stats["total_connections"],
        "connections_by_endpoint": stats["connections_by_endpoint"],
        "connections_by_tenant": stats["connections_by_tenant"],
        "oldest_connection_age_seconds": stats["oldest_connection_age_seconds"]
    }

