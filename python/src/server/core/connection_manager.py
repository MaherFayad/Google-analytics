"""
Connection manager for tracking active SSE connections.

Implements Task P0-20: Graceful SSE Connection Shutdown

Provides:
- Active connection tracking
- Graceful shutdown coordination
- Client notification before restart
- Connection rejection during shutdown
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Set
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class SSEConnectionManager:
    """
    Manages active SSE connections for graceful shutdown.
    
    Features:
    - Track active connections by ID
    - Notify all connections before shutdown
    - Reject new connections during shutdown
    - Wait for in-flight requests to complete
    """
    
    def __init__(self, shutdown_grace_period: int = 20):
        """
        Initialize connection manager.
        
        Args:
            shutdown_grace_period: Seconds to wait for connections to close (default: 20)
        """
        self._connections: Dict[str, asyncio.Queue] = {}
        self._shutdown_requested = False
        self._shutdown_grace_period = shutdown_grace_period
        self._shutdown_event = asyncio.Event()
        logger.info(f"SSE Connection Manager initialized (grace period: {shutdown_grace_period}s)")
    
    @property
    def active_connection_count(self) -> int:
        """Return number of active connections."""
        return len(self._connections)
    
    @property
    def is_shutting_down(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown_requested
    
    def register_connection(self, connection_id: str) -> Optional[asyncio.Queue]:
        """
        Register a new SSE connection.
        
        Args:
            connection_id: Unique connection identifier
            
        Returns:
            asyncio.Queue for sending events, or None if shutdown in progress
        """
        if self._shutdown_requested:
            logger.warning(f"Connection {connection_id} rejected - shutdown in progress")
            return None
        
        event_queue = asyncio.Queue()
        self._connections[connection_id] = event_queue
        logger.info(f"Connection registered: {connection_id} (total: {self.active_connection_count})")
        return event_queue
    
    def unregister_connection(self, connection_id: str):
        """
        Unregister an SSE connection.
        
        Args:
            connection_id: Unique connection identifier
        """
        if connection_id in self._connections:
            del self._connections[connection_id]
            logger.info(f"Connection unregistered: {connection_id} (remaining: {self.active_connection_count})")
    
    async def notify_shutdown(self, message: str = "Server restarting, please reconnect in 30s"):
        """
        Notify all active connections about shutdown.
        
        Args:
            message: Shutdown notification message
        """
        logger.info(f"Notifying {self.active_connection_count} active connections of shutdown")
        
        shutdown_event = {
            "type": "shutdown",
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
            "reconnect_delay": 30
        }
        
        # Send shutdown notification to all connections
        for connection_id, queue in list(self._connections.items()):
            try:
                await asyncio.wait_for(
                    queue.put(shutdown_event),
                    timeout=2.0  # Don't wait too long per connection
                )
                logger.debug(f"Shutdown notification sent to {connection_id}")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout sending shutdown notification to {connection_id}")
            except Exception as e:
                logger.error(f"Error notifying connection {connection_id}: {e}")
    
    async def graceful_shutdown(self):
        """
        Perform graceful shutdown of all connections.
        
        Process:
        1. Mark as shutting down (reject new connections)
        2. Notify all active connections
        3. Wait up to grace_period for connections to close
        4. Force close remaining connections
        """
        logger.info(f"Starting graceful shutdown (grace period: {self._shutdown_grace_period}s)")
        self._shutdown_requested = True
        
        # Notify all connections
        await self.notify_shutdown()
        
        # Wait for connections to close gracefully
        start_time = asyncio.get_event_loop().time()
        while self.active_connection_count > 0:
            elapsed = asyncio.get_event_loop().time() - start_time
            
            if elapsed >= self._shutdown_grace_period:
                logger.warning(
                    f"Grace period expired with {self.active_connection_count} "
                    f"connections still active. Force closing."
                )
                break
            
            # Check every 0.5 seconds
            await asyncio.sleep(0.5)
            
            if self.active_connection_count > 0:
                logger.debug(
                    f"Waiting for {self.active_connection_count} connections to close "
                    f"({elapsed:.1f}s elapsed)"
                )
        
        # Force close remaining connections
        if self.active_connection_count > 0:
            logger.warning(f"Force closing {self.active_connection_count} remaining connections")
            self._connections.clear()
        
        logger.info("Graceful shutdown complete")
        self._shutdown_event.set()
    
    async def wait_for_shutdown(self):
        """Wait for shutdown to complete."""
        await self._shutdown_event.wait()
    
    @asynccontextmanager
    async def connection_context(self, connection_id: str):
        """
        Context manager for SSE connection lifecycle.
        
        Usage:
            async with connection_manager.connection_context("conn-123") as queue:
                if queue is None:
                    # Shutdown in progress, reject connection
                    return 503
                # Use queue to send events
        
        Args:
            connection_id: Unique connection identifier
            
        Yields:
            asyncio.Queue for sending events, or None if shutdown in progress
        """
        queue = self.register_connection(connection_id)
        
        try:
            yield queue
        finally:
            self.unregister_connection(connection_id)


# Global connection manager instance
_connection_manager: Optional[SSEConnectionManager] = None


def get_connection_manager(grace_period: int = 20) -> SSEConnectionManager:
    """
    Get or create global connection manager instance.
    
    Args:
        grace_period: Shutdown grace period in seconds
        
    Returns:
        SSEConnectionManager instance
    """
    global _connection_manager
    
    if _connection_manager is None:
        _connection_manager = SSEConnectionManager(shutdown_grace_period=grace_period)
    
    return _connection_manager


def reset_connection_manager():
    """Reset global connection manager (for testing)."""
    global _connection_manager
    _connection_manager = None

