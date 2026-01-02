"""
Chart Data Validation Middleware.

Implements Task P0-21: Chart Data Schema Specification & Validation

Provides FastAPI middleware to validate LLM-generated chart data before
sending to frontend, preventing runtime crashes from malformed data.

Features:
1. Automatic validation of all `/analytics/*` responses
2. Coerces common LLM errors (strings to floats)
3. Returns 500 with detailed error if validation fails
4. Logs validation errors for debugging

Usage:
    app.add_middleware(ChartValidationMiddleware)
    
    # Now all analytics responses are validated
    response = await client.post("/analytics/stream", ...)
    # ✓ Charts validated automatically
"""

import json
import logging
from typing import Any, Dict

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import ValidationError

from ...agents.schemas.charts import validate_chart_data

logger = logging.getLogger(__name__)


class ChartValidationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to validate chart data in analytics responses.
    
    Intercepts responses from `/analytics/*` endpoints and validates
    that chart data conforms to Pydantic schemas.
    
    This prevents:
    - Frontend crashes from malformed data
    - Type errors (strings instead of numbers)
    - Missing required fields
    - Invalid chart types
    """
    
    async def dispatch(self, request: Request, call_next):
        """Process request and validate response charts."""
        # Only validate analytics endpoints
        if not request.url.path.startswith("/analytics"):
            return await call_next(request)
        
        # Get response from endpoint
        response: Response = await call_next(request)
        
        # Only validate successful JSON responses
        if response.status_code != 200:
            return response
        
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            # SSE responses are not JSON - skip validation
            return response
        
        # Read response body
        try:
            body_bytes = b""
            async for chunk in response.body_iterator:
                body_bytes += chunk
            
            body_json = json.loads(body_bytes)
            
            # Validate charts if present
            if "charts" in body_json:
                validated_charts = []
                
                for idx, chart in enumerate(body_json["charts"]):
                    try:
                        # Validate chart using Pydantic schemas
                        validated_chart = validate_chart_data(chart)
                        validated_charts.append(validated_chart.model_dump())
                        
                    except ValidationError as e:
                        logger.error(
                            f"Chart validation failed for chart {idx}: {e}",
                            extra={
                                "chart_index": idx,
                                "chart_data": chart,
                                "validation_errors": e.errors(),
                            }
                        )
                        
                        # Return 500 with detailed error
                        return JSONResponse(
                            status_code=500,
                            content={
                                "error": "Chart validation failed",
                                "chart_index": idx,
                                "details": e.errors(),
                                "message": (
                                    "LLM generated invalid chart data. "
                                    "Please try again or contact support."
                                ),
                            }
                        )
                
                # Replace charts with validated versions
                body_json["charts"] = validated_charts
            
            # Return response with validated charts
            return Response(
                content=json.dumps(body_json),
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type="application/json",
            )
            
        except Exception as e:
            logger.error(f"Chart validation middleware error: {e}", exc_info=True)
            # Return original response on validation error
            return response


async def validate_sse_event_charts(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate charts in SSE events.
    
    Use this for SSE responses (text/event-stream) that contain charts.
    
    Args:
        event: SSE event data (e.g., {"type": "result", "payload": {...}})
        
    Returns:
        Event with validated charts
        
    Raises:
        ValidationError: If chart data is invalid
        
    Example:
        # In streaming endpoint
        event = {"type": "result", "payload": {...}}
        validated_event = await validate_sse_event_charts(event)
        yield f"data: {json.dumps(validated_event)}\\n\\n"
    """
    if event.get("type") != "result":
        return event
    
    payload = event.get("payload", {})
    if "charts" not in payload:
        return event
    
    # Validate each chart
    validated_charts = []
    for idx, chart in enumerate(payload["charts"]):
        try:
            validated_chart = validate_chart_data(chart)
            validated_charts.append(validated_chart.model_dump())
        except ValidationError as e:
            logger.error(
                f"SSE chart validation failed for chart {idx}: {e}",
                extra={
                    "chart_index": idx,
                    "chart_data": chart,
                    "validation_errors": e.errors(),
                }
            )
            raise
    
    # Replace with validated charts
    payload["charts"] = validated_charts
    event["payload"] = payload
    
    return event

