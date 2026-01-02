"""
Integration tests for queue position streaming.

Tests Task P0-31: Real-Time Queue Position Streaming via SSE

Verifies:
- Queue position tracking accuracy
- ETA calculations
- SSE streaming updates
- User-friendly status messages
- Integration with GA4RequestQueue
"""

import asyncio
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.server.services.ga4.queue_tracker import (
    QueueTracker,
    QueueStatus,
    format_queue_status_sse,
    stream_queue_position_to_sse
)
from src.server.services.ga4.request_queue import QueuedRequest


class TestQueueStatusModel:
    """Test QueueStatus data model."""
    
    def test_queue_status_creation(self):
        """Test creating QueueStatus instance."""
        status = QueueStatus(
            request_id="test-123",
            position=12,
            total_queue=47,
            eta_seconds=360,
            status="queued",
            message="Position 12 in queue • Estimated wait: 6 minutes"
        )
        
        assert status.request_id == "test-123"
        assert status.position == 12
        assert status.total_queue == 47
        assert status.eta_seconds == 360
        assert status.status == "queued"
        assert "Position 12" in status.message
    
    def test_queue_status_json_serialization(self):
        """Test QueueStatus can be serialized to JSON."""
        status = QueueStatus(
            request_id="test-123",
            position=5,
            total_queue=20,
            eta_seconds=150,
            status="queued",
            message="Position 5 in queue"
        )
        
        json_str = status.json()
        assert isinstance(json_str, str)
        
        # Verify can be parsed back
        parsed = json.loads(json_str)
        assert parsed["request_id"] == "test-123"
        assert parsed["position"] == 5


class TestQueueTrackerStatusMessages:
    """Test queue tracker status message generation."""
    
    def test_completed_message(self):
        """Test message for completed request."""
        tracker = QueueTracker(
            redis_client=MagicMock(),
            request_queue=MagicMock()
        )
        
        message = tracker._generate_status_message("completed", 0, 0)
        assert message == "Request completed successfully"
    
    def test_failed_message(self):
        """Test message for failed request."""
        tracker = QueueTracker(
            redis_client=MagicMock(),
            request_queue=MagicMock()
        )
        
        message = tracker._generate_status_message("failed", 0, 0)
        assert message == "Request failed"
    
    def test_processing_message(self):
        """Test message for processing request."""
        tracker = QueueTracker(
            redis_client=MagicMock(),
            request_queue=MagicMock()
        )
        
        message = tracker._generate_status_message("processing", 1, 0)
        assert message == "Processing your request..."
    
    def test_next_in_queue_message(self):
        """Test message for request next in queue."""
        tracker = QueueTracker(
            redis_client=MagicMock(),
            request_queue=MagicMock()
        )
        
        message = tracker._generate_status_message("queued", 1, 30)
        assert "Next in queue" in message
    
    def test_queued_with_seconds_eta(self):
        """Test message with ETA in seconds."""
        tracker = QueueTracker(
            redis_client=MagicMock(),
            request_queue=MagicMock()
        )
        
        message = tracker._generate_status_message("queued", 5, 45)
        assert "Position 5" in message
        assert "45 seconds" in message
    
    def test_queued_with_minutes_eta(self):
        """Test message with ETA in minutes."""
        tracker = QueueTracker(
            redis_client=MagicMock(),
            request_queue=MagicMock()
        )
        
        message = tracker._generate_status_message("queued", 12, 360)
        assert "Position 12" in message
        assert "6 minute" in message
    
    def test_queued_with_hours_eta(self):
        """Test message with ETA in hours."""
        tracker = QueueTracker(
            redis_client=MagicMock(),
            request_queue=MagicMock()
        )
        
        message = tracker._generate_status_message("queued", 50, 7200)
        assert "Position 50" in message
        assert "2 hour" in message


class TestQueueTrackerETACalculation:
    """Test ETA calculation logic."""
    
    @pytest.mark.asyncio
    async def test_eta_for_position_zero(self):
        """Test ETA is 0 for position 0."""
        tracker = QueueTracker(
            redis_client=MagicMock(),
            request_queue=MagicMock()
        )
        
        eta = await tracker._calculate_eta("test-123", 0)
        assert eta == 0
    
    @pytest.mark.asyncio
    async def test_eta_calculation_formula(self):
        """Test ETA calculation uses correct formula."""
        tracker = QueueTracker(
            redis_client=MagicMock(),
            request_queue=MagicMock()
        )
        
        # Position 5 should be 5 * 30 = 150 seconds
        eta = await tracker._calculate_eta("test-123", 5)
        assert eta == 150
        
        # Position 20 should be 20 * 30 = 600 seconds (10 minutes)
        eta = await tracker._calculate_eta("test-123", 20)
        assert eta == 600


class TestQueueTrackerIntegration:
    """Integration tests for QueueTracker with GA4RequestQueue."""
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock()
        return redis_mock
    
    @pytest.fixture
    def mock_queue(self):
        """Mock GA4RequestQueue."""
        queue_mock = MagicMock()
        queue_mock.RESULT_KEY_PREFIX = "ga4:result:"
        queue_mock.get_queue_position = AsyncMock()
        queue_mock.get_queue_length = AsyncMock()
        return queue_mock
    
    @pytest.mark.asyncio
    async def test_get_queue_status_not_found(self, mock_redis, mock_queue):
        """Test get_queue_status when request not found."""
        mock_redis.get.return_value = None
        
        tracker = QueueTracker(mock_redis, mock_queue)
        status = await tracker.get_queue_status("test-123")
        
        assert status.status == "not_found"
        assert status.position == 0
        assert status.message == "Request not found"
    
    @pytest.mark.asyncio
    async def test_get_queue_status_queued(self, mock_redis, mock_queue):
        """Test get_queue_status for queued request."""
        # Mock request data
        request = QueuedRequest(
            request_id="test-123",
            tenant_id="tenant-1",
            user_id="user-1",
            endpoint="fetch_page_views",
            params={},
            status="queued"
        )
        mock_redis.get.return_value = request.json()
        
        # Mock queue methods
        mock_queue.get_queue_position.return_value = 12
        mock_queue.get_queue_length.return_value = 47
        
        tracker = QueueTracker(mock_redis, mock_queue)
        status = await tracker.get_queue_status("test-123")
        
        assert status.status == "queued"
        assert status.position == 12
        assert status.total_queue == 47
        assert status.eta_seconds == 360  # 12 * 30
        assert "Position 12" in status.message
    
    @pytest.mark.asyncio
    async def test_get_queue_status_processing(self, mock_redis, mock_queue):
        """Test get_queue_status for processing request."""
        request = QueuedRequest(
            request_id="test-123",
            tenant_id="tenant-1",
            user_id="user-1",
            endpoint="fetch_page_views",
            params={},
            status="processing"
        )
        mock_redis.get.return_value = request.json()
        mock_queue.get_queue_position.return_value = 0
        mock_queue.get_queue_length.return_value = 47
        
        tracker = QueueTracker(mock_redis, mock_queue)
        status = await tracker.get_queue_status("test-123")
        
        assert status.status == "processing"
        assert status.position == 0
        assert "Processing" in status.message
    
    @pytest.mark.asyncio
    async def test_stream_queue_updates(self, mock_redis, mock_queue):
        """Test streaming queue updates."""
        # Mock changing positions over time
        positions = [10, 8, 5, 2, 0]
        statuses = ["queued", "queued", "queued", "queued", "processing"]
        
        async def mock_get_status(request_id):
            if not positions:
                # Return completed status
                return QueueStatus(
                    request_id=request_id,
                    position=0,
                    total_queue=50,
                    eta_seconds=0,
                    status="completed",
                    message="Request completed successfully"
                )
            
            position = positions.pop(0)
            status = statuses.pop(0)
            
            return QueueStatus(
                request_id=request_id,
                position=position,
                total_queue=50,
                eta_seconds=position * 30,
                status=status,
                message=f"Position {position}" if position > 0 else "Processing"
            )
        
        tracker = QueueTracker(mock_redis, mock_queue)
        
        # Override get_queue_status for testing
        tracker.get_queue_status = mock_get_status
        
        # Override update interval for faster test
        tracker.UPDATE_INTERVAL_SECONDS = 0.1
        
        updates = []
        async for status in tracker.stream_queue_updates("test-123", max_duration=2):
            updates.append(status)
        
        # Should receive updates for decreasing positions
        assert len(updates) >= 1
        assert updates[-1].status in ("completed", "processing")
    
    @pytest.mark.asyncio
    async def test_stream_stops_on_completion(self, mock_redis, mock_queue):
        """Test stream stops when request completes."""
        call_count = 0
        
        async def mock_get_status(request_id):
            nonlocal call_count
            call_count += 1
            
            if call_count <= 2:
                return QueueStatus(
                    request_id=request_id,
                    position=5,
                    total_queue=10,
                    eta_seconds=150,
                    status="queued",
                    message="Position 5"
                )
            else:
                return QueueStatus(
                    request_id=request_id,
                    position=0,
                    total_queue=10,
                    eta_seconds=0,
                    status="completed",
                    message="Completed"
                )
        
        tracker = QueueTracker(mock_redis, mock_queue)
        tracker.get_queue_status = mock_get_status
        tracker.UPDATE_INTERVAL_SECONDS = 0.1
        
        updates = []
        async for status in tracker.stream_queue_updates("test-123"):
            updates.append(status)
        
        # Should stop after completion
        assert updates[-1].status == "completed"


class TestSSEFormatting:
    """Test SSE event formatting."""
    
    def test_format_queue_status_sse(self):
        """Test formatting QueueStatus as SSE event."""
        status = QueueStatus(
            request_id="test-123",
            position=12,
            total_queue=47,
            eta_seconds=360,
            status="queued",
            message="Position 12 in queue"
        )
        
        sse_event = format_queue_status_sse(status)
        
        assert "event: queue_status" in sse_event
        assert "data:" in sse_event
        assert "test-123" in sse_event
        assert sse_event.endswith("\n\n")
    
    @pytest.mark.asyncio
    async def test_stream_queue_position_to_sse(self):
        """Test convenience function for SSE streaming."""
        mock_tracker = MagicMock()
        
        async def mock_stream():
            for i in range(3, 0, -1):
                yield QueueStatus(
                    request_id="test-123",
                    position=i,
                    total_queue=10,
                    eta_seconds=i * 30,
                    status="queued",
                    message=f"Position {i}"
                )
        
        mock_tracker.stream_queue_updates = mock_stream
        
        events = []
        async for sse_event in stream_queue_position_to_sse("test-123", mock_tracker):
            events.append(sse_event)
        
        assert len(events) == 3
        assert all("event: queue_status" in event for event in events)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

