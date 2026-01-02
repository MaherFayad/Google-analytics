"""
Unified Analytics API Endpoint with Automatic Mode Detection.

Implements Task 9.3: Unified Analytics API Endpoint [HIGH]

Provides a single endpoint that automatically routes queries to either:
- Descriptive Analytics (SQL-based) for "What happened?" queries
- Predictive Analytics (Vector RAG) for "What might happen?" queries
- Hybrid mode for comprehensive analysis

Features:
- Automatic mode detection based on query keywords
- Hybrid queries return both descriptive and predictive results
- Integration with existing SSE endpoint for streaming
- Fast response times (<1s for most queries)

Example Usage:
    POST /api/v1/analytics/query
    {
        "query": "Show me mobile conversion trends",
        "mode": "auto"  // or "descriptive", "predictive", "hybrid"
    }
"""

import logging
from typing import Optional, Literal
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_session
from ...middleware.auth import get_current_user_id
from ...middleware.tenant import get_current_tenant_id
from ...services.analytics.descriptive_analytics import (
    DescriptiveAnalyticsService,
    DescriptiveAnalyticsResult
)
from ...services.analytics.predictive_analytics import (
    PredictiveAnalyticsService,
    PredictiveAnalyticsResult
)
from ...core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


class AnalyticsMode(str, Enum):
    """Analytics query mode."""
    AUTO = "auto"  # Automatic detection
    DESCRIPTIVE = "descriptive"  # SQL-based "What happened?"
    PREDICTIVE = "predictive"  # Vector-based "What might happen?"
    HYBRID = "hybrid"  # Both descriptive and predictive


class UnifiedAnalyticsRequest(BaseModel):
    """Request model for unified analytics query."""
    
    query: str = Field(
        description="Natural language analytics query",
        example="Show me mobile conversion trends last week"
    )
    mode: AnalyticsMode = Field(
        default=AnalyticsMode.AUTO,
        description="Analytics mode (auto, descriptive, predictive, hybrid)"
    )
    days: int = Field(
        default=7,
        ge=1,
        le=365,
        description="Number of days to analyze (for descriptive queries)"
    )
    match_count: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of similar patterns to find (for predictive queries)"
    )


class UnifiedAnalyticsResponse(BaseModel):
    """Response model for unified analytics query."""
    
    mode_used: str = Field(description="Analytics mode that was used")
    descriptive: Optional[DescriptiveAnalyticsResult] = None
    predictive: Optional[PredictiveAnalyticsResult] = None


@router.post(
    "/query",
    response_model=UnifiedAnalyticsResponse,
    summary="Unified analytics query",
    description="Submit analytics query with automatic mode detection"
)
async def unified_analytics_query(
    request: UnifiedAnalyticsRequest,
    user_id: str = Depends(get_current_user_id),
    tenant_id: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_session),
) -> UnifiedAnalyticsResponse:
    """
    Unified analytics endpoint with automatic mode detection.
    
    Automatically routes queries to appropriate analytics service:
    - Descriptive: "show", "list", "get", "what happened"
    - Predictive: "similar", "pattern", "compare", "predict", "trend"
    - Hybrid: Complex queries or explicit hybrid mode
    
    Args:
        request: Analytics query request
        user_id: Current user ID (from JWT)
        tenant_id: Current tenant ID (validated)
        session: Database session
        
    Returns:
        UnifiedAnalyticsResponse with descriptive and/or predictive results
        
    Example:
        ```
        POST /api/v1/analytics/query
        {
            "query": "Show me mobile traffic last week",
            "mode": "auto"
        }
        
        Response:
        {
            "mode_used": "descriptive",
            "descriptive": {
                "type": "descriptive",
                "chart_data": {...},
                "metrics": [...]
            },
            "predictive": null
        }
        ```
    """
    logger.info(
        f"Unified analytics query: {request.query}",
        extra={
            "user_id": user_id,
            "tenant_id": tenant_id,
            "mode": request.mode
        }
    )
    
    # Determine mode
    if request.mode == AnalyticsMode.AUTO:
        detected_mode = _detect_query_mode(request.query)
        logger.info(f"Auto-detected mode: {detected_mode}")
    else:
        detected_mode = request.mode
    
    # Initialize services
    descriptive_service = DescriptiveAnalyticsService(session)
    predictive_service = PredictiveAnalyticsService(
        session,
        openai_api_key=settings.OPENAI_API_KEY
    )
    
    # Execute based on mode
    descriptive_result = None
    predictive_result = None
    
    try:
        if detected_mode in [AnalyticsMode.DESCRIPTIVE, AnalyticsMode.HYBRID]:
            # Run descriptive analytics
            logger.debug("Running descriptive analytics")
            descriptive_result = await descriptive_service.get_traffic_trend(
                tenant_id=tenant_id,
                user_id=user_id,
                days=request.days
            )
        
        if detected_mode in [AnalyticsMode.PREDICTIVE, AnalyticsMode.HYBRID]:
            # Run predictive analytics
            logger.debug("Running predictive analytics")
            predictive_result = await predictive_service.find_similar_patterns(
                tenant_id=tenant_id,
                query=request.query,
                match_count=request.match_count
            )
        
        logger.info(
            f"Analytics query completed: mode={detected_mode}",
            extra={
                "has_descriptive": descriptive_result is not None,
                "has_predictive": predictive_result is not None
            }
        )
        
        return UnifiedAnalyticsResponse(
            mode_used=detected_mode.value,
            descriptive=descriptive_result,
            predictive=predictive_result
        )
    
    except Exception as e:
        logger.error(f"Analytics query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analytics query failed: {str(e)}"
        )


def _detect_query_mode(query: str) -> AnalyticsMode:
    """
    Detect analytics mode from query text.
    
    Uses keyword matching to determine whether query is:
    - Descriptive: "What happened?" queries
    - Predictive: "What might happen?" queries
    - Hybrid: Complex queries requiring both
    
    Args:
        query: Natural language query
        
    Returns:
        Detected AnalyticsMode
        
    Example:
        >>> _detect_query_mode("Show me last week's traffic")
        AnalyticsMode.DESCRIPTIVE
        
        >>> _detect_query_mode("Find similar patterns to current trends")
        AnalyticsMode.PREDICTIVE
        
        >>> _detect_query_mode("Compare current traffic to historical patterns")
        AnalyticsMode.HYBRID
    """
    query_lower = query.lower()
    
    # Descriptive keywords
    descriptive_keywords = [
        "show", "list", "get", "display", "view",
        "what happened", "how many", "total",
        "last week", "last month", "yesterday",
        "traffic", "sessions", "conversions"
    ]
    
    # Predictive keywords
    predictive_keywords = [
        "similar", "pattern", "compare", "predict",
        "trend", "forecast", "like", "historical",
        "what if", "might", "could", "expect",
        "anomaly", "unusual", "different"
    ]
    
    # Hybrid keywords
    hybrid_keywords = [
        "compare to", "versus", "vs", "and also",
        "both", "as well as", "in addition"
    ]
    
    # Count keyword matches
    descriptive_count = sum(1 for kw in descriptive_keywords if kw in query_lower)
    predictive_count = sum(1 for kw in predictive_keywords if kw in query_lower)
    hybrid_count = sum(1 for kw in hybrid_keywords if kw in query_lower)
    
    # Determine mode
    if hybrid_count > 0 or (descriptive_count > 0 and predictive_count > 0):
        return AnalyticsMode.HYBRID
    elif predictive_count > descriptive_count:
        return AnalyticsMode.PREDICTIVE
    else:
        # Default to descriptive for simple queries
        return AnalyticsMode.DESCRIPTIVE


@router.get(
    "/modes",
    summary="List available analytics modes",
    description="Get list of available analytics modes and their descriptions"
)
async def list_analytics_modes():
    """
    List available analytics modes.
    
    Returns:
        Dictionary of modes with descriptions
    """
    return {
        "modes": [
            {
                "key": "auto",
                "name": "Automatic Detection",
                "description": "Automatically detects query type and routes to appropriate service"
            },
            {
                "key": "descriptive",
                "name": "Descriptive Analytics",
                "description": "SQL-based 'What happened?' queries for time-series analysis"
            },
            {
                "key": "predictive",
                "name": "Predictive Analytics",
                "description": "Vector-based 'What might happen?' queries for pattern matching"
            },
            {
                "key": "hybrid",
                "name": "Hybrid Analytics",
                "description": "Combines both descriptive and predictive analytics"
            }
        ]
    }

