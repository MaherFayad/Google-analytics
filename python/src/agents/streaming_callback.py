"""
Streaming Callback Handler for Pydantic-AI Agents

Implements Task 4.1: Custom Callback Handler (adapted for Pydantic-AI)

Features:
- Real-time progress updates via asyncio.Queue
- Agent execution status tracking
- Tool/function call tracking
- Structured event format for SSE streaming
- Async-first design for non-blocking operation

Note: Originally specified for CrewAI, adapted for our Pydantic-AI architecture.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Literal
from enum import Enum
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ========== Event Models ==========

class EventType(str, Enum):
    """Types of streaming events."""
    
    STATUS = "status"           # General status update
    THOUGHT = "thought"         # Agent reasoning/thinking
    TOOL_START = "tool_start"   # Tool execution started
    TOOL_END = "tool_end"       # Tool execution completed
    AGENT_START = "agent_start" # Agent started
    AGENT_END = "agent_end"     # Agent completed
    ERROR = "error"             # Error occurred
    WARNING = "warning"         # Warning message
    RESULT = "result"           # Final result


class StreamEvent(BaseModel):
    """
    Structured streaming event.
    
    Compatible with SSE format for real-time updates.
    """
    
    type: EventType = Field(description="Event type")
    message: str = Field(description="Human-readable message")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Optional fields
    agent_name: Optional[str] = Field(default=None, description="Agent that generated the event")
    tool_name: Optional[str] = Field(default=None, description="Tool being used (for tool events)")
    progress: Optional[float] = Field(default=None, description="Progress percentage (0.0-1.0)")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")
    content: Optional[Any] = Field(default=None, description="Event-specific content")
    
    def to_sse_format(self) -> str:
        """
        Convert to Server-Sent Events format.
        
        Returns:
            SSE-formatted string (data: {json})
        """
        return f"data: {self.model_dump_json()}\n\n"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return self.model_dump(exclude_none=True)


# ========== Callback Handler ==========

class StreamingCallbackHandler:
    """
    Callback handler for streaming agent progress updates.
    
    Pushes structured events to an asyncio.Queue for consumption
    by SSE endpoint or other streaming consumers.
    
    Usage:
        ```python
        queue = asyncio.Queue()
        handler = StreamingCallbackHandler(queue)
        
        # In agent execution
        await handler.on_agent_start("DataFetcherAgent", "Fetching GA4 data...")
        await handler.on_status("Processing 1000 rows")
        await handler.on_agent_end("DataFetcherAgent", result_summary)
        
        # In SSE endpoint
        async for event in handler.stream_events():
            yield event.to_sse_format()
        ```
    """
    
    def __init__(self, queue: asyncio.Queue, max_queue_size: int = 1000):
        """
        Initialize callback handler.
        
        Args:
            queue: Asyncio queue for pushing events
            max_queue_size: Maximum queue size (prevents memory overflow)
        """
        self.queue = queue
        self.max_queue_size = max_queue_size
        self._active = True
        logger.info(f"StreamingCallbackHandler initialized (queue size: {max_queue_size})")
    
    async def _push_event(self, event: StreamEvent) -> None:
        """
        Push event to queue (non-blocking).
        
        Args:
            event: Event to push
        """
        if not self._active:
            logger.warning("Handler is inactive, event dropped")
            return
        
        try:
            # Non-blocking put (drops event if queue is full)
            if self.queue.qsize() < self.max_queue_size:
                await self.queue.put(event)
            else:
                logger.warning(f"Queue full ({self.max_queue_size}), dropping event: {event.type}")
        except Exception as e:
            logger.error(f"Failed to push event: {e}", exc_info=True)
    
    # ========== Status Events ==========
    
    async def on_status(
        self,
        message: str,
        progress: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Emit general status update.
        
        Args:
            message: Status message
            progress: Optional progress percentage (0.0-1.0)
            metadata: Optional metadata
        """
        event = StreamEvent(
            type=EventType.STATUS,
            message=message,
            progress=progress,
            metadata=metadata
        )
        await self._push_event(event)
        logger.debug(f"Status: {message}")
    
    async def on_thought(
        self,
        content: str,
        agent_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Emit agent thought/reasoning.
        
        Args:
            content: Thought content
            agent_name: Agent that generated the thought
            metadata: Optional metadata
        """
        event = StreamEvent(
            type=EventType.THOUGHT,
            message=f"Thinking: {content[:100]}...",
            agent_name=agent_name,
            content=content,
            metadata=metadata
        )
        await self._push_event(event)
        logger.debug(f"Thought ({agent_name}): {content[:50]}")
    
    # ========== Agent Events ==========
    
    async def on_agent_start(
        self,
        agent_name: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Emit agent start event.
        
        Args:
            agent_name: Name of the agent starting
            message: Descriptive message
            metadata: Optional metadata
        """
        event = StreamEvent(
            type=EventType.AGENT_START,
            message=message,
            agent_name=agent_name,
            metadata=metadata
        )
        await self._push_event(event)
        logger.info(f"Agent started: {agent_name} - {message}")
    
    async def on_agent_end(
        self,
        agent_name: str,
        message: str,
        result_summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Emit agent completion event.
        
        Args:
            agent_name: Name of the agent completing
            message: Descriptive message
            result_summary: Summary of results
            metadata: Optional metadata
        """
        event = StreamEvent(
            type=EventType.AGENT_END,
            message=message,
            agent_name=agent_name,
            content=result_summary,
            metadata=metadata
        )
        await self._push_event(event)
        logger.info(f"Agent completed: {agent_name} - {message}")
    
    # ========== Tool Events ==========
    
    async def on_tool_start(
        self,
        tool_name: str,
        inputs: Optional[Dict[str, Any]] = None,
        agent_name: Optional[str] = None
    ) -> None:
        """
        Emit tool start event.
        
        Args:
            tool_name: Name of the tool being executed
            inputs: Tool input parameters
            agent_name: Agent executing the tool
        """
        event = StreamEvent(
            type=EventType.TOOL_START,
            message=f"Executing {tool_name}",
            agent_name=agent_name,
            tool_name=tool_name,
            metadata={"inputs": inputs} if inputs else None
        )
        await self._push_event(event)
        logger.debug(f"Tool started: {tool_name}")
    
    async def on_tool_end(
        self,
        tool_name: str,
        output_summary: Optional[str] = None,
        agent_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Emit tool completion event.
        
        Args:
            tool_name: Name of the tool that completed
            output_summary: Summary of tool output
            agent_name: Agent that executed the tool
            metadata: Optional metadata
        """
        event = StreamEvent(
            type=EventType.TOOL_END,
            message=f"Completed {tool_name}",
            agent_name=agent_name,
            tool_name=tool_name,
            content=output_summary,
            metadata=metadata
        )
        await self._push_event(event)
        logger.debug(f"Tool completed: {tool_name}")
    
    # ========== Error & Warning Events ==========
    
    async def on_error(
        self,
        message: str,
        error: Optional[Exception] = None,
        agent_name: Optional[str] = None
    ) -> None:
        """
        Emit error event.
        
        Args:
            message: Error message
            error: Optional exception object
            agent_name: Agent where error occurred
        """
        metadata = None
        if error:
            metadata = {
                "error_type": type(error).__name__,
                "error_details": str(error)
            }
        
        event = StreamEvent(
            type=EventType.ERROR,
            message=message,
            agent_name=agent_name,
            metadata=metadata
        )
        await self._push_event(event)
        logger.error(f"Error ({agent_name}): {message}")
    
    async def on_warning(
        self,
        message: str,
        agent_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Emit warning event.
        
        Args:
            message: Warning message
            agent_name: Agent where warning occurred
            metadata: Optional metadata
        """
        event = StreamEvent(
            type=EventType.WARNING,
            message=message,
            agent_name=agent_name,
            metadata=metadata
        )
        await self._push_event(event)
        logger.warning(f"Warning ({agent_name}): {message}")
    
    # ========== Result Event ==========
    
    async def on_result(
        self,
        payload: Any,
        message: str = "Pipeline completed successfully"
    ) -> None:
        """
        Emit final result event.
        
        Args:
            payload: Final result payload
            message: Success message
        """
        event = StreamEvent(
            type=EventType.RESULT,
            message=message,
            content=payload
        )
        await self._push_event(event)
        logger.info("Result emitted")
    
    # ========== Lifecycle ==========
    
    async def close(self) -> None:
        """Close the handler and stop accepting events."""
        self._active = False
        logger.info("StreamingCallbackHandler closed")
    
    # ========== Stream Iterator ==========
    
    async def stream_events(self) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream events from the queue.
        
        Yields:
            StreamEvent instances as they are available
            
        Example:
            ```python
            async for event in handler.stream_events():
                yield event.to_sse_format()
            ```
        """
        while self._active or not self.queue.empty():
            try:
                # Wait for event with timeout
                event = await asyncio.wait_for(
                    self.queue.get(),
                    timeout=0.1
                )
                yield event
                
                # Stop if result event (end of stream)
                if event.type == EventType.RESULT:
                    break
                    
            except asyncio.TimeoutError:
                # No event available, continue waiting
                continue
            except Exception as e:
                logger.error(f"Error streaming events: {e}", exc_info=True)
                break


# ========== Helper Functions ==========

def create_callback_handler(max_queue_size: int = 1000) -> tuple[StreamingCallbackHandler, asyncio.Queue]:
    """
    Create a callback handler and its queue.
    
    Args:
        max_queue_size: Maximum queue size
        
    Returns:
        Tuple of (handler, queue)
        
    Example:
        ```python
        handler, queue = create_callback_handler()
        
        # Use handler in agent execution
        await run_agent_with_callbacks(handler)
        
        # Stream events to SSE
        async for event in handler.stream_events():
            yield event.to_sse_format()
        ```
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
    handler = StreamingCallbackHandler(queue, max_queue_size=max_queue_size)
    return handler, queue

