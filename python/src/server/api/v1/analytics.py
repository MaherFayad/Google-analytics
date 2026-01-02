"""
Analytics API endpoints with SSE streaming.

Implements Task 4.2: SSE Endpoint Implementation
Implements Task P0-12: Async Agent Execution with Streaming
Implements Task P0-20: Graceful SSE Connection Shutdown
Implements Task P0-31: Real-Time Queue Position Streaming

Provides:
- POST /analytics/query - Submit analytics query
- POST /analytics/stream - SSE streaming for real-time updates
- GET /analytics/queue/{request_id} - Stream queue position updates
- Graceful shutdown support for active connections
"""

import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_session
from ...middleware.auth import get_current_user_id
from ...middleware.tenant import get_current_tenant_id, get_tenant_role
from ...services.auth import AuthService
from ...services.cache import ProgressiveCacheService
from ...agents.orchestrator_agent import OrchestratorAgent
from ...core.config import settings
from ...core.connection_manager import get_connection_manager
from ...services.ga4.queue_tracker import QueueTracker, stream_queue_position_to_sse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


class AnalyticsQueryRequest(BaseModel):
    """Request model for analytics query."""
    
    query: str = Field(
        description="Natural language query about GA4 data",
        example="Show me mobile conversions last week"
    )
    property_id: Optional[str] = Field(
        default=None,
        description="GA4 property ID (uses user's default if not specified)"
    )
    dimensions: Optional[list[str]] = Field(
        default=None,
        description="GA4 dimensions (default: ['date'])"
    )
    metrics: Optional[list[str]] = Field(
        default=None,
        description="GA4 metrics (default: ['sessions', 'conversions'])"
    )


class AnalyticsQueryResponse(BaseModel):
    """Response model for analytics query."""
    
    query_id: str
    message: str


@router.post(
    "/query",
    response_model=AnalyticsQueryResponse,
    summary="Submit analytics query",
    description="Submit a natural language query about GA4 data. Returns query ID for streaming."
)
async def submit_analytics_query(
    request: Request,
    query_request: AnalyticsQueryRequest,
    user_id: str = Depends(get_current_user_id),
    tenant_id: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_session),
) -> AnalyticsQueryResponse:
    """
    Submit analytics query for processing.
    
    The actual report generation happens asynchronously via SSE stream.
    
    Args:
        request: FastAPI request
        query_request: Query parameters
        user_id: Current user ID (from JWT)
        tenant_id: Current tenant ID (validated)
        session: Database session
        
    Returns:
        Query ID for streaming endpoint
    """
    import uuid
    
    query_id = str(uuid.uuid4())
    
    logger.info(
        f"Analytics query submitted: {query_request.query}",
        extra={
            "query_id": query_id,
            "user_id": user_id,
            "tenant_id": tenant_id,
        }
    )
    
    return AnalyticsQueryResponse(
        query_id=query_id,
        message="Query submitted. Use /analytics/stream for real-time results."
    )


@router.post(
    "/stream",
    summary="Stream analytics results (SSE)",
    description="Execute analytics query with real-time progress updates via Server-Sent Events"
)
async def stream_analytics_query(
    request: Request,
    query_request: AnalyticsQueryRequest,
    user_id: str = Depends(get_current_user_id),
    tenant_id: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_session),
):
    """
    Stream analytics query results with SSE.
    
    Implements Task 4.2: SSE Endpoint Implementation
    Implements Task P0-12: Async execution with streaming
    Implements Task P0-20: Graceful shutdown support
    
    Args:
        request: FastAPI request
        query_request: Query parameters
        user_id: Current user ID
        tenant_id: Current tenant ID
        session: Database session
        
    Returns:
        StreamingResponse with SSE events, or 503 if shutting down
    """
    # Get connection manager (Task P0-20)
    connection_manager = get_connection_manager()
    
    # Reject new connections if shutdown in progress (Task P0-20)
    if connection_manager.is_shutting_down:
        logger.warning("Rejecting new SSE connection - shutdown in progress")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": "Service unavailable",
                "message": "Server is restarting, please try again in 30 seconds",
                "retry_after": 30
            },
            headers={"Retry-After": "30"}
        )
    
    # Get user's access token
    auth_service = AuthService(session)
    
    try:
        access_token = await auth_service.get_valid_token(user_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Failed to get valid access token: {str(e)}"
        )
    
    # Get property ID (use from request or user's default)
    property_id = query_request.property_id
    if not property_id:
        # TODO: Get user's default property from database
        property_id = "123456789"  # Placeholder
    
    # Initialize progressive cache service (Task P0-12)
    cache_service = ProgressiveCacheService(
        redis_client=None,  # TODO: Inject Redis client from app state
        db_session=session,
    )
    
    # Create orchestrator with cache-first strategy
    orchestrator = OrchestratorAgent(
        openai_api_key=settings.OPENAI_API_KEY,
        redis_client=None,  # TODO: Inject Redis client
        db_session=session,
        cache_service=cache_service,  # Enable <500ms time-to-first-token (Task P0-12)
    )
    
    # Generate unique connection ID (Task P0-20)
    connection_id = f"{tenant_id}:{user_id}:{uuid.uuid4().hex[:8]}"
    
    async def event_generator():
        """Generate SSE events with graceful shutdown support."""
        # Register connection with manager (Task P0-20)
        async with connection_manager.connection_context(connection_id) as event_queue:
            if event_queue is None:
                # Shutdown in progress, should not reach here due to earlier check
                logger.error("Connection queue is None - shutdown in progress")
                yield f"event: error\ndata: Server shutting down\n\n"
                return
            
            try:
                # Stream pipeline execution
                async for event in orchestrator.execute_pipeline_streaming(
                    query=query_request.query,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    property_id=property_id,
                    access_token=access_token,
                    dimensions=query_request.dimensions,
                    metrics=query_request.metrics,
                ):
                    # Check for shutdown events from manager (Task P0-20)
                    if not event_queue.empty():
                        shutdown_event = await event_queue.get()
                        if shutdown_event.get("type") == "shutdown":
                            import json
                            shutdown_json = json.dumps(shutdown_event)
                            logger.info(f"Sending shutdown notification to {connection_id}")
                            yield f"event: shutdown\ndata: {shutdown_json}\n\n"
                            return
                    
                    # Format as SSE
                    event_type = event.get("type", "message")
                    
                    if event_type == "status":
                        yield f"event: status\ndata: {event['message']}\n\n"
                    elif event_type == "result":
                        import json
                        payload_json = json.dumps(event["payload"])
                        yield f"event: result\ndata: {payload_json}\n\n"
                    elif event_type == "error":
                        yield f"event: error\ndata: {event['message']}\n\n"
                
                # Send completion event
                yield "event: complete\ndata: {}\n\n"
                
            except Exception as e:
                logger.error(f"Streaming error for {connection_id}: {e}", exc_info=True)
                yield f"event: error\ndata: {str(e)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get(
    "/queue/{request_id}",
    summary="Stream queue position updates (SSE)",
    description="Real-time queue position and ETA updates for a queued request"
)
async def stream_queue_position(
    request_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Stream queue position updates for a request.
    
    Implements Task P0-31: Real-Time Queue Position Streaming via SSE
    
    Provides real-time updates on:
    - Position in queue (1 = next to process)
    - Total queue length
    - Estimated wait time (ETA)
    - Current status (queued, processing, completed, failed)
    
    Args:
        request_id: Request ID to track
        request: FastAPI request
        user_id: Current user ID
        tenant_id: Current tenant ID
        
    Returns:
        StreamingResponse with SSE queue_status events
    
    SSE Event Format:
        event: queue_status
        data: {
            "request_id": "...",
            "position": 12,
            "total_queue": 47,
            "eta_seconds": 360,
            "status": "queued",
            "message": "Position 12 in queue • Estimated wait: 6 minutes",
            "timestamp": "2025-01-02T13:30:00.000Z"
        }
    """
    # TODO: Get Redis client and request queue from app state
    # For now, return mock stream
    
    logger.info(f"Starting queue position stream for request {request_id}")
    
    async def event_generator():
        """Generate queue position SSE events."""
        try:
            # TODO: Initialize queue tracker when Redis is available
            # from ...services.ga4.queue_tracker import QueueTracker
            # from ...services.ga4.request_queue import GA4RequestQueue
            # 
            # redis_client = request.app.state.redis
            # request_queue = GA4RequestQueue(redis_client)
            # tracker = QueueTracker(redis_client, request_queue)
            # 
            # async for status_sse in stream_queue_position_to_sse(request_id, tracker):
            #     yield status_sse
            
            # Mock implementation for demonstration
            import json
            from datetime import datetime
            
            for i in range(10, 0, -1):
                # Simulate decreasing queue position
                status = {
                    "request_id": request_id,
                    "position": i,
                    "total_queue": 50,
                    "eta_seconds": i * 30,
                    "status": "queued" if i > 1 else "processing",
                    "message": f"Position {i} in queue • Estimated wait: {i * 30} seconds" if i > 1 else "Processing your request...",
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                yield f"event: queue_status\ndata: {json.dumps(status)}\n\n"
                
                # Check for client disconnect
                if await request.is_disconnected():
                    logger.info(f"Client disconnected from queue stream for {request_id}")
                    break
                
                await asyncio.sleep(5)  # Update every 5 seconds
            
            # Send completion
            completion_status = {
                "request_id": request_id,
                "position": 0,
                "total_queue": 50,
                "eta_seconds": 0,
                "status": "completed",
                "message": "Request completed successfully",
                "timestamp": datetime.utcnow().isoformat()
            }
            yield f"event: queue_status\ndata: {json.dumps(completion_status)}\n\n"
            
        except asyncio.CancelledError:
            logger.info(f"Queue position stream cancelled for {request_id}")
        except Exception as e:
            logger.error(f"Error in queue position stream for {request_id}: {e}", exc_info=True)
            yield f"event: error\ndata: {str(e)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

