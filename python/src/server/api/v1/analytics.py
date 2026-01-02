"""
Analytics API endpoints with SSE streaming.

Implements Task 4.2: SSE Endpoint Implementation
Implements Task P0-12: Async Agent Execution with Streaming

Provides:
- POST /analytics/query - Submit analytics query
- GET /analytics/stream - SSE streaming for real-time updates
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_session
from ...middleware.auth import get_current_user_id
from ...middleware.tenant import get_current_tenant_id, get_tenant_role
from ...services.auth import AuthService
from ...agents.orchestrator_agent import OrchestratorAgent
from ...core.config import settings

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
    
    Args:
        request: FastAPI request
        query_request: Query parameters
        user_id: Current user ID
        tenant_id: Current tenant ID
        session: Database session
        
    Returns:
        StreamingResponse with SSE events
    """
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
    
    # Create orchestrator
    orchestrator = OrchestratorAgent(
        openai_api_key=settings.OPENAI_API_KEY,
        redis_client=None,  # TODO: Inject Redis client
        db_session=session,
    )
    
    async def event_generator():
        """Generate SSE events."""
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
            logger.error(f"Streaming error: {e}", exc_info=True)
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

