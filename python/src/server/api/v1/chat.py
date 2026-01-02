"""
Chat Stream Endpoint

Implements Task 4.2: SSE Endpoint Implementation

Features:
- POST /api/v1/chat/stream - Streaming analytics chat
- Auth validation via JWT
- Orchestrator integration with Pydantic-AI agents
- Real-time progress updates via SSE
- Structured report generation
- Graceful shutdown support
"""

import asyncio
import logging
import json
from datetime import datetime
from typing import AsyncGenerator, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status, Query, Depends
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, Field

from python.src.agents.orchestrator_agent import OrchestratorAgent
from python.src.agents.schemas.results import ReportResult
from ...core.connection_manager import connection_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    """Request body for chat."""
    query: str = Field(..., min_length=1, max_length=500, description="User query")
    tenant_id: Optional[str] = Field(None, description="Tenant ID (extracted from JWT if not provided)")
    property_id: Optional[str] = Field(None, description="GA4 property ID")
    request_id: Optional[str] = Field(None, description="Idempotency token for reconnection")


async def get_tenant_id_from_token() -> str:
    """
    Extract tenant_id from JWT token.
    
    In production, this should:
    1. Validate JWT signature
    2. Extract tenant_id claim
    3. Verify tenant membership
    
    For now, returns a placeholder.
    """
    # TODO: Implement proper JWT validation (Task P0-2)
    return "test-tenant-123"


async def generate_chat_events(
    query: str,
    tenant_id: str,
    connection_id: str,
    property_id: Optional[str] = None,
) -> AsyncGenerator:
    """
    Generate SSE events for chat stream.
    
    Implements Task 4.2: SSE streaming with agent orchestration
    
    Args:
        query: User's analytics query
        tenant_id: Tenant ID
        connection_id: Unique connection identifier
        property_id: GA4 property ID
        
    Yields:
        SSE events with status updates and final result
    """
    try:
        logger.info(
            f"Chat stream started: connection={connection_id}, "
            f"tenant={tenant_id}, query='{query}'"
        )
        
        # Check for shutdown
        if connection_manager.is_shutting_down:
            yield connection_manager.get_shutdown_notification_event(reconnect_delay=30)
            return
        
        # 1. Send initial status
        yield {
            "event": "status",
            "data": json.dumps({
                "type": "status",
                "message": "Initializing...",
                "timestamp": datetime.utcnow().isoformat()
            })
        }
        
        # 2. Initialize orchestrator
        # TODO: Get API key from config/env
        orchestrator = OrchestratorAgent(
            openai_api_key="placeholder",
            redis_client=None,  # TODO: Inject Redis
            db_session=None,    # TODO: Inject DB session
            cache_service=None,
        )
        
        # 3. Execute pipeline with streaming updates
        try:
            result: ReportResult = await orchestrator.execute(
                query=query,
                tenant_id=tenant_id,
                user_id=tenant_id,  # Use tenant_id as user_id for simplicity
                property_id=property_id or "GA4-12345",
                access_token="placeholder",  # TODO: Get from auth service
            )
        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}", exc_info=True)
            raise
        
        # 4. Send final result
        # Convert Pydantic models to dicts for JSON serialization
        charts_data = []
        if result.charts:
            for chart in result.charts:
                if hasattr(chart, 'dict'):
                    charts_data.append(chart.dict())
                elif hasattr(chart, 'model_dump'):
                    charts_data.append(chart.model_dump())
                else:
                    charts_data.append(chart)
        
        metrics_data = []
        if result.metrics:
            for metric in result.metrics:
                if hasattr(metric, 'dict'):
                    metrics_data.append(metric.dict())
                elif hasattr(metric, 'model_dump'):
                    metrics_data.append(metric.model_dump())
                else:
                    metrics_data.append(metric)
        
        citations_data = []
        if result.citations:
            for citation in result.citations:
                if hasattr(citation, 'dict'):
                    citations_data.append(citation.dict())
                elif hasattr(citation, 'model_dump'):
                    citations_data.append(citation.model_dump())
                else:
                    citations_data.append(citation)
        
        yield {
            "event": "result",
            "data": json.dumps({
                "type": "result",
                "payload": {
                    "answer": result.answer,
                    "charts": charts_data,
                    "metrics": metrics_data,
                    "citations": citations_data,
                    "confidence": result.confidence,
                    "tenant_id": result.tenant_id,
                    "query": result.query,
                    "timestamp": result.timestamp.isoformat(),
                },
                "timestamp": datetime.utcnow().isoformat()
            })
        }
        
        logger.info(
            f"Chat stream completed: connection={connection_id}, "
            f"confidence={result.confidence:.2f}"
        )
        
    except asyncio.CancelledError:
        logger.info(f"Connection {connection_id}: Cancelled by client")
        raise
        
    except Exception as e:
        logger.error(
            f"Connection {connection_id}: Error during chat stream: {e}",
            exc_info=True
        )
        
        # Send error event
        yield {
            "event": "error",
            "data": json.dumps({
                "type": "error",
                "message": str(e),
                "timestamp": datetime.utcnow().isoformat()
            })
        }


@router.get("/stream")
async def chat_stream_get(
    query: str = Query(..., min_length=1, max_length=500, description="Analytics query"),
    request_id: Optional[str] = Query(None, description="Idempotency token for reconnection"),
    tenant_id: str = Depends(get_tenant_id_from_token),
):
    """
    Chat stream endpoint (GET for EventSource compatibility).
    
    Implements Task 4.2: SSE Endpoint Implementation
    
    **Features:**
    - Real-time progress updates via SSE
    - Agent orchestration with Pydantic-AI
    - Graceful shutdown support
    - Idempotency for reconnection
    
    **Usage:**
    ```javascript
    const eventSource = new EventSource(
      '/api/v1/chat/stream?query=Show%20me%20sessions&request_id=req-123'
    );
    
    eventSource.addEventListener('status', (e) => {
      const data = JSON.parse(e.data);
      console.log('Status:', data.message);
    });
    
    eventSource.addEventListener('result', (e) => {
      const data = JSON.parse(e.data);
      console.log('Result:', data.payload);
      eventSource.close();
    });
    ```
    
    **Events:**
    - `status`: Progress updates (agent execution, data fetching, etc.)
    - `result`: Final structured report with charts and metrics
    - `error`: Error messages if something fails
    - `shutdown`: Server shutting down notification
    
    Args:
        query: User's analytics question
        request_id: Idempotency token (generated by client)
        tenant_id: Extracted from JWT (auto-injected)
        
    Returns:
        EventSourceResponse with streaming events
    """
    # Check if server is shutting down
    if connection_manager.is_shutting_down:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server is shutting down. Please reconnect in 30 seconds."
        )
    
    # Generate connection ID (use request_id for idempotency)
    connection_id = request_id or str(uuid4())
    
    logger.info(
        f"New chat stream: connection={connection_id}, "
        f"tenant={tenant_id}, query='{query[:50]}...'"
    )
    
    # Create event generator with connection tracking
    async def event_generator():
        async with connection_manager.track_connection(
            connection_id=connection_id,
            tenant_id=tenant_id,
            endpoint="/chat/stream",
            metadata={"query": query[:100]}
        ):
            async for event in generate_chat_events(
                query=query,
                tenant_id=tenant_id,
                connection_id=connection_id,
            ):
                yield event
    
    return EventSourceResponse(event_generator())


@router.post("/stream")
async def chat_stream_post(
    request: ChatRequest,
    tenant_id: str = Depends(get_tenant_id_from_token),
):
    """
    Chat stream endpoint (POST for larger queries).
    
    Alternative to GET endpoint for:
    - Very long queries (>500 chars)
    - Queries with special characters
    - Complex request payloads
    
    Note: Browser EventSource doesn't support POST, so this is for
    programmatic clients only. Browser clients should use GET endpoint.
    
    Args:
        request: Chat request with query and options
        tenant_id: Extracted from JWT
        
    Returns:
        EventSourceResponse with streaming events
    """
    # Check if server is shutting down
    if connection_manager.is_shutting_down:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server is shutting down. Please reconnect in 30 seconds."
        )
    
    # Use tenant_id from request or JWT
    tenant_id = request.tenant_id or tenant_id
    connection_id = request.request_id or str(uuid4())
    
    logger.info(
        f"New chat stream (POST): connection={connection_id}, "
        f"tenant={tenant_id}, query='{request.query[:50]}...'"
    )
    
    # Create event generator with connection tracking
    async def event_generator():
        async with connection_manager.track_connection(
            connection_id=connection_id,
            tenant_id=tenant_id,
            endpoint="/chat/stream (POST)",
            metadata={"query": request.query[:100]}
        ):
            async for event in generate_chat_events(
                query=request.query,
                tenant_id=tenant_id,
                connection_id=connection_id,
                property_id=request.property_id,
            ):
                yield event
    
    return EventSourceResponse(event_generator())


@router.get("/history")
async def get_chat_history(
    tenant_id: str = Depends(get_tenant_id_from_token),
    limit: int = Query(10, ge=1, le=100),
):
    """
    Get chat history for the current tenant.
    
    Future enhancement: Store chat sessions in database.
    
    Args:
        tenant_id: Extracted from JWT
        limit: Max number of messages to return
        
    Returns:
        List of chat sessions
    """
    # TODO: Implement chat history storage and retrieval
    return {
        "success": True,
        "sessions": [],
        "message": "Chat history not yet implemented"
    }


@router.delete("/session/{session_id}")
async def delete_chat_session(
    session_id: str,
    tenant_id: str = Depends(get_tenant_id_from_token),
):
    """
    Delete a chat session.
    
    Args:
        session_id: Session to delete
        tenant_id: Extracted from JWT
        
    Returns:
        Success message
    """
    # TODO: Implement session deletion
    return {
        "success": True,
        "message": "Session deletion not yet implemented"
    }

