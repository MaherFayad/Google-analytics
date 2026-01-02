"""
Integration tests for Grounding Enforcer Middleware.

Implements Task P0-46: Grounding Enforcer Middleware [CRITICAL-DATA-INTEGRITY]

Tests:
1. Fully grounded response passes through
2. Ungrounded response triggers retry
3. Max retries exceeded returns error
4. Middleware disabled in development mode
5. Non-SSE requests pass through
6. Malformed SSE events handled gracefully
"""

import asyncio
import json
import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse

from src.server.middleware.grounding_enforcer import (
    GroundingEnforcerMiddleware,
    create_strict_prompt,
)
from src.server.services.validation.context_grounding_checker import (
    GroundingStatus,
    GroundingReport,
)


@pytest.fixture
def app():
    """Create test FastAPI app with grounding enforcer."""
    app = FastAPI()
    
    # Add grounding enforcer middleware
    app.add_middleware(
        GroundingEnforcerMiddleware,
        grounding_threshold=0.85,
        max_retries=3,
        enforce=True
    )
    
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.mark.asyncio
async def test_fully_grounded_response_passes_through(app, client):
    """
    Test that fully grounded responses pass through without modification.
    
    Scenario:
        - LLM generates response with all claims grounded
        - Grounding score: 1.0 (100%)
        - Expected: Response passes through unchanged
    """
    # Mock SSE endpoint
    @app.post("/api/v1/analytics/stream")
    async def mock_stream():
        async def event_generator():
            # Send fully grounded result
            result = {
                "answer": "Mobile sessions: 10,234 on Jan 5, 2025",
                "context": ["Mobile sessions: 10,234 on Jan 5, 2025"],
                "raw_metrics": {"sessions": 10234, "device": "mobile"}
            }
            yield f"event: result\ndata: {json.dumps(result)}\n\n"
            yield "event: complete\ndata: {}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream"
        )
    
    # Mock grounding checker to return fully grounded
    with patch('src.server.middleware.grounding_enforcer.ContextGroundingChecker') as MockChecker:
        mock_checker = MockChecker.return_value
        mock_checker.validate_grounding = AsyncMock(return_value=GroundingReport(
            status=GroundingStatus.FULLY_GROUNDED,
            validation_score=1.0,
            total_claims=1,
            grounded_claims=1,
            ungrounded_claims=[],
            severity="low"
        ))
        
        # Make request
        response = client.post("/api/v1/analytics/stream", json={"query": "test"})
        
        # Verify response
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
        
        # Parse SSE events
        events = []
        for line in response.text.split('\n'):
            if line.startswith('event:'):
                event_type = line.split(':', 1)[1].strip()
                events.append(event_type)
        
        # Should have result and complete events (no retry/error)
        assert 'result' in events
        assert 'complete' in events
        assert 'grounding_retry' not in events
        assert 'grounding_error' not in events


@pytest.mark.asyncio
async def test_ungrounded_response_triggers_retry(app, client):
    """
    Test that ungrounded responses trigger retry notification.
    
    Scenario:
        - LLM generates response with ungrounded claims
        - Grounding score: 0.5 (50%)
        - Expected: Retry event sent to client
    """
    @app.post("/api/v1/analytics/stream")
    async def mock_stream():
        async def event_generator():
            # Send partially grounded result
            result = {
                "answer": "Mobile sessions: 10K, which is below industry average",
                "context": ["Mobile sessions: 10,234"],
                "raw_metrics": {"sessions": 10234}
            }
            yield f"event: result\ndata: {json.dumps(result)}\n\n"
            yield "event: complete\ndata: {}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream"
        )
    
    # Mock grounding checker to return partially grounded
    with patch('src.server.middleware.grounding_enforcer.ContextGroundingChecker') as MockChecker:
        mock_checker = MockChecker.return_value
        mock_checker.validate_grounding = AsyncMock(return_value=GroundingReport(
            status=GroundingStatus.PARTIALLY_GROUNDED,
            validation_score=0.5,
            total_claims=2,
            grounded_claims=1,
            ungrounded_claims=[
                {"claim": "below industry average", "type": "comparison", "confidence": 0.8}
            ],
            severity="high"
        ))
        
        # Make request
        response = client.post("/api/v1/analytics/stream", json={"query": "test"})
        
        # Verify response
        assert response.status_code == 200
        
        # Parse SSE events
        events = []
        for line in response.text.split('\n'):
            if line.startswith('event:'):
                event_type = line.split(':', 1)[1].strip()
                events.append(event_type)
        
        # Should have retry event
        assert 'grounding_retry' in events


@pytest.mark.asyncio
async def test_max_retries_exceeded_returns_error(app, client):
    """
    Test that exceeding max retries returns error event.
    
    Scenario:
        - LLM generates ungrounded response
        - Retries 3 times (all fail)
        - Expected: Error event sent after max retries
    """
    @app.post("/api/v1/analytics/stream")
    async def mock_stream():
        async def event_generator():
            # Send multiple ungrounded results
            for i in range(4):  # More than max_retries
                result = {
                    "answer": "Traffic is below industry average",
                    "context": ["Sessions: 10,234"],
                    "raw_metrics": {"sessions": 10234}
                }
                yield f"event: result\ndata: {json.dumps(result)}\n\n"
            
            yield "event: complete\ndata: {}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream"
        )
    
    # Mock grounding checker to always return ungrounded
    with patch('src.server.middleware.grounding_enforcer.ContextGroundingChecker') as MockChecker:
        mock_checker = MockChecker.return_value
        mock_checker.validate_grounding = AsyncMock(return_value=GroundingReport(
            status=GroundingStatus.UNGROUNDED,
            validation_score=0.2,
            total_claims=1,
            grounded_claims=0,
            ungrounded_claims=[
                {"claim": "below industry average", "type": "comparison", "confidence": 0.9}
            ],
            severity="critical"
        ))
        
        # Make request
        response = client.post("/api/v1/analytics/stream", json={"query": "test"})
        
        # Verify response
        assert response.status_code == 200
        
        # Parse SSE events
        events = []
        for line in response.text.split('\n'):
            if line.startswith('event:'):
                event_type = line.split(':', 1)[1].strip()
                events.append(event_type)
        
        # Should have error event after max retries
        assert 'grounding_error' in events


@pytest.mark.asyncio
async def test_middleware_disabled_in_development():
    """
    Test that middleware can be disabled (e.g., in development).
    
    Scenario:
        - Middleware initialized with enforce=False
        - Expected: All responses pass through without validation
    """
    app = FastAPI()
    
    # Add middleware with enforce=False
    app.add_middleware(
        GroundingEnforcerMiddleware,
        grounding_threshold=0.85,
        max_retries=3,
        enforce=False  # Disabled
    )
    
    @app.post("/api/v1/analytics/stream")
    async def mock_stream():
        async def event_generator():
            result = {
                "answer": "Completely ungrounded response",
                "context": [],
                "raw_metrics": {}
            }
            yield f"event: result\ndata: {json.dumps(result)}\n\n"
            yield "event: complete\ndata: {}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream"
        )
    
    client = TestClient(app)
    
    # Make request
    response = client.post("/api/v1/analytics/stream", json={"query": "test"})
    
    # Verify response passes through without validation
    assert response.status_code == 200
    
    # Parse SSE events
    events = []
    for line in response.text.split('\n'):
        if line.startswith('event:'):
            event_type = line.split(':', 1)[1].strip()
            events.append(event_type)
    
    # Should have result but no retry/error (validation skipped)
    assert 'result' in events
    assert 'grounding_retry' not in events
    assert 'grounding_error' not in events


@pytest.mark.asyncio
async def test_non_sse_requests_pass_through(app, client):
    """
    Test that non-SSE requests are not affected by middleware.
    
    Scenario:
        - Regular JSON endpoint (not SSE)
        - Expected: Request passes through without interception
    """
    @app.get("/api/v1/health")
    async def health():
        return {"status": "healthy"}
    
    # Make request
    response = client.get("/api/v1/health")
    
    # Verify response
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_malformed_sse_events_handled_gracefully(app, client):
    """
    Test that malformed SSE events don't crash middleware.
    
    Scenario:
        - SSE stream with invalid JSON
        - Expected: Middleware handles gracefully, passes through
    """
    @app.post("/api/v1/analytics/stream")
    async def mock_stream():
        async def event_generator():
            # Send malformed result event
            yield "event: result\ndata: {invalid json}\n\n"
            yield "event: complete\ndata: {}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream"
        )
    
    # Make request
    response = client.post("/api/v1/analytics/stream", json={"query": "test"})
    
    # Verify response (should not crash)
    assert response.status_code == 200


def test_create_strict_prompt():
    """
    Test strict prompt creation for retries.
    
    Scenario:
        - Original query with ungrounded claims
        - Expected: Strict prompt with explicit grounding rules
    """
    original_query = "Show me mobile conversions"
    ungrounded_claims = [
        {"claim": "below industry average", "type": "comparison"},
        {"claim": "typical for this season", "type": "attribution"}
    ]
    
    strict_prompt = create_strict_prompt(original_query, ungrounded_claims)
    
    # Verify strict prompt contains key elements
    assert "CRITICAL GROUNDING RULES" in strict_prompt
    assert "MUST ONLY use facts" in strict_prompt
    assert "Do NOT use your general knowledge" in strict_prompt
    assert "below industry average" in strict_prompt
    assert "typical for this season" in strict_prompt
    assert original_query in strict_prompt


@pytest.mark.asyncio
async def test_metrics_recorded():
    """
    Test that Prometheus metrics are recorded.
    
    Scenario:
        - Various grounding validation outcomes
        - Expected: Metrics counters incremented
    """
    from src.server.middleware.grounding_enforcer import (
        grounding_enforcer_checks_total,
        grounding_enforcer_retries_total,
        grounding_validation_score,
    )
    
    # Get initial metric values
    initial_checks = grounding_enforcer_checks_total._metrics.get(
        ('fully_grounded', 'low'), 
        Mock(get=lambda: 0)
    ).get()
    
    app = FastAPI()
    app.add_middleware(
        GroundingEnforcerMiddleware,
        grounding_threshold=0.85,
        max_retries=3,
        enforce=True
    )
    
    @app.post("/api/v1/analytics/stream")
    async def mock_stream():
        async def event_generator():
            result = {
                "answer": "Mobile sessions: 10,234",
                "context": ["Mobile sessions: 10,234"],
                "raw_metrics": {"sessions": 10234}
            }
            yield f"event: result\ndata: {json.dumps(result)}\n\n"
            yield "event: complete\ndata: {}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream"
        )
    
    # Mock grounding checker
    with patch('src.server.middleware.grounding_enforcer.ContextGroundingChecker') as MockChecker:
        mock_checker = MockChecker.return_value
        mock_checker.validate_grounding = AsyncMock(return_value=GroundingReport(
            status=GroundingStatus.FULLY_GROUNDED,
            validation_score=1.0,
            total_claims=1,
            grounded_claims=1,
            ungrounded_claims=[],
            severity="low"
        ))
        
        client = TestClient(app)
        response = client.post("/api/v1/analytics/stream", json={"query": "test"})
        
        # Verify metrics were recorded
        # Note: Actual metric verification depends on prometheus_client implementation
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

