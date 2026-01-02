"""
Unit Tests for Streaming Callback Handler

Tests Task 4.1: Custom Callback Handler
"""

import pytest
import asyncio
from datetime import datetime

from python.src.agents.streaming_callback import (
    StreamingCallbackHandler,
    StreamEvent,
    EventType,
    create_callback_handler,
)


class TestStreamEvent:
    """Test StreamEvent model."""
    
    def test_stream_event_creation(self):
        """Test basic event creation."""
        event = StreamEvent(
            type=EventType.STATUS,
            message="Test message"
        )
        
        assert event.type == EventType.STATUS
        assert event.message == "Test message"
        assert isinstance(event.timestamp, datetime)
    
    def test_stream_event_with_metadata(self):
        """Test event with metadata."""
        event = StreamEvent(
            type=EventType.TOOL_START,
            message="Fetching data",
            agent_name="DataFetcher",
            tool_name="fetch_ga4_data",
            metadata={"property_id": "123"}
        )
        
        assert event.agent_name == "DataFetcher"
        assert event.tool_name == "fetch_ga4_data"
        assert event.metadata["property_id"] == "123"
    
    def test_to_sse_format(self):
        """Test SSE format conversion."""
        event = StreamEvent(
            type=EventType.STATUS,
            message="Progress update",
            progress=0.5
        )
        
        sse_output = event.to_sse_format()
        
        assert sse_output.startswith("data: {")
        assert "\"type\":\"status\"" in sse_output
        assert "\"message\":\"Progress update\"" in sse_output
        assert sse_output.endswith("\n\n")
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        event = StreamEvent(
            type=EventType.AGENT_START,
            message="Starting agent",
            agent_name="TestAgent",
            progress=0.0
        )
        
        event_dict = event.to_dict()
        
        assert event_dict["type"] == "agent_start"
        assert event_dict["message"] == "Starting agent"
        assert event_dict["agent_name"] == "TestAgent"
        assert event_dict["progress"] == 0.0


class TestStreamingCallbackHandler:
    """Test StreamingCallbackHandler."""
    
    @pytest.mark.asyncio
    async def test_handler_initialization(self):
        """Test handler initialization."""
        handler, queue = create_callback_handler(max_queue_size=100)
        
        assert isinstance(handler, StreamingCallbackHandler)
        assert isinstance(queue, asyncio.Queue)
        assert handler.max_queue_size == 100
        assert handler._active is True
    
    @pytest.mark.asyncio
    async def test_on_status(self):
        """Test status event emission."""
        handler, queue = create_callback_handler()
        
        await handler.on_status("Processing data", progress=0.5)
        
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event.type == EventType.STATUS
        assert event.message == "Processing data"
        assert event.progress == 0.5
    
    @pytest.mark.asyncio
    async def test_on_thought(self):
        """Test thought event emission."""
        handler, queue = create_callback_handler()
        
        await handler.on_thought(
            "Analyzing the query to determine dimensions",
            agent_name="Orchestrator"
        )
        
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event.type == EventType.THOUGHT
        assert event.agent_name == "Orchestrator"
        assert "Analyzing the query" in event.content
    
    @pytest.mark.asyncio
    async def test_on_agent_start(self):
        """Test agent start event."""
        handler, queue = create_callback_handler()
        
        await handler.on_agent_start(
            "DataFetcherAgent",
            "Fetching GA4 metrics"
        )
        
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event.type == EventType.AGENT_START
        assert event.agent_name == "DataFetcherAgent"
        assert event.message == "Fetching GA4 metrics"
    
    @pytest.mark.asyncio
    async def test_on_agent_end(self):
        """Test agent end event."""
        handler, queue = create_callback_handler()
        
        await handler.on_agent_end(
            "DataFetcherAgent",
            "Successfully fetched 1000 rows",
            result_summary="1000 rows from 2025-01-01 to 2025-01-07"
        )
        
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event.type == EventType.AGENT_END
        assert event.agent_name == "DataFetcherAgent"
        assert event.message == "Successfully fetched 1000 rows"
        assert "1000 rows" in event.content
    
    @pytest.mark.asyncio
    async def test_on_tool_start(self):
        """Test tool start event."""
        handler, queue = create_callback_handler()
        
        await handler.on_tool_start(
            "fetch_ga4_data",
            inputs={"property_id": "123", "start_date": "2025-01-01"},
            agent_name="DataFetcherAgent"
        )
        
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event.type == EventType.TOOL_START
        assert event.tool_name == "fetch_ga4_data"
        assert event.agent_name == "DataFetcherAgent"
        assert event.metadata["inputs"]["property_id"] == "123"
    
    @pytest.mark.asyncio
    async def test_on_tool_end(self):
        """Test tool end event."""
        handler, queue = create_callback_handler()
        
        await handler.on_tool_end(
            "fetch_ga4_data",
            output_summary="Retrieved 500 metrics",
            agent_name="DataFetcherAgent"
        )
        
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event.type == EventType.TOOL_END
        assert event.tool_name == "fetch_ga4_data"
        assert event.content == "Retrieved 500 metrics"
    
    @pytest.mark.asyncio
    async def test_on_error(self):
        """Test error event."""
        handler, queue = create_callback_handler()
        
        error = ValueError("Invalid property ID")
        await handler.on_error(
            "Failed to fetch data",
            error=error,
            agent_name="DataFetcherAgent"
        )
        
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event.type == EventType.ERROR
        assert event.message == "Failed to fetch data"
        assert event.metadata["error_type"] == "ValueError"
    
    @pytest.mark.asyncio
    async def test_on_warning(self):
        """Test warning event."""
        handler, queue = create_callback_handler()
        
        await handler.on_warning(
            "Cache miss, fetching from API",
            agent_name="DataFetcherAgent"
        )
        
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event.type == EventType.WARNING
        assert event.message == "Cache miss, fetching from API"
    
    @pytest.mark.asyncio
    async def test_on_result(self):
        """Test result event."""
        handler, queue = create_callback_handler()
        
        result_payload = {"report_id": "123", "charts": []}
        await handler.on_result(result_payload, "Report generated")
        
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event.type == EventType.RESULT
        assert event.message == "Report generated"
        assert event.content["report_id"] == "123"
    
    @pytest.mark.asyncio
    async def test_close_handler(self):
        """Test handler closure."""
        handler, queue = create_callback_handler()
        
        assert handler._active is True
        await handler.close()
        assert handler._active is False
    
    @pytest.mark.asyncio
    async def test_stream_events(self):
        """Test event streaming."""
        handler, queue = create_callback_handler()
        
        # Emit several events
        await handler.on_status("Step 1")
        await handler.on_status("Step 2")
        await handler.on_result({"data": "final"})
        
        # Stream events
        events = []
        async for event in handler.stream_events():
            events.append(event)
        
        assert len(events) == 3
        assert events[0].message == "Step 1"
        assert events[1].message == "Step 2"
        assert events[2].type == EventType.RESULT
    
    @pytest.mark.asyncio
    async def test_queue_overflow_handling(self):
        """Test behavior when queue is full."""
        handler, queue = create_callback_handler(max_queue_size=2)
        
        # Fill the queue
        await handler.on_status("Event 1")
        await handler.on_status("Event 2")
        
        # This should not block or crash
        await handler.on_status("Event 3 (should be dropped)")
        
        # Verify only first 2 events are in queue
        events = []
        try:
            while True:
                event = queue.get_nowait()
                events.append(event)
        except asyncio.QueueEmpty:
            pass
        
        assert len(events) == 2
    
    @pytest.mark.asyncio
    async def test_multiple_events_in_sequence(self):
        """Test realistic agent execution sequence."""
        handler, queue = create_callback_handler()
        
        # Simulate agent workflow
        await handler.on_agent_start("DataFetcher", "Starting data fetch")
        await handler.on_tool_start("fetch_ga4_data", {"property_id": "123"})
        await handler.on_status("Fetching metrics", progress=0.5)
        await handler.on_tool_end("fetch_ga4_data", "Retrieved 100 rows")
        await handler.on_agent_end("DataFetcher", "Data fetch complete")
        
        # Collect events
        events = []
        for _ in range(5):
            event = await asyncio.wait_for(queue.get(), timeout=1.0)
            events.append(event)
        
        assert events[0].type == EventType.AGENT_START
        assert events[1].type == EventType.TOOL_START
        assert events[2].type == EventType.STATUS
        assert events[3].type == EventType.TOOL_END
        assert events[4].type == EventType.AGENT_END
    
    @pytest.mark.asyncio
    async def test_concurrent_event_emission(self):
        """Test concurrent event emission from multiple sources."""
        handler, queue = create_callback_handler()
        
        # Simulate concurrent agents
        async def agent1():
            await handler.on_agent_start("Agent1", "Starting")
            await asyncio.sleep(0.01)
            await handler.on_agent_end("Agent1", "Done")
        
        async def agent2():
            await handler.on_agent_start("Agent2", "Starting")
            await asyncio.sleep(0.01)
            await handler.on_agent_end("Agent2", "Done")
        
        # Run concurrently
        await asyncio.gather(agent1(), agent2())
        
        # Collect events
        events = []
        try:
            while True:
                event = queue.get_nowait()
                events.append(event)
        except asyncio.QueueEmpty:
            pass
        
        assert len(events) == 4
        agent_names = [e.agent_name for e in events]
        assert "Agent1" in agent_names
        assert "Agent2" in agent_names

