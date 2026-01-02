"""
SSE Connection Manager for Graceful Shutdown

Implements Task P0-20: Graceful SSE Connection Shutdown

Tracks active SSE connections and coordinates graceful shutdown during
server restarts or deployments.

Features:
- Connection registration and tracking
- Graceful shutdown notifications
- Connection draining with timeout
- Zero-downtime rolling deployments

Usage:
    from src.server.core.connection_manager import connection_manager
    
    # Register connection
    async with connection_manager.track_connection(connection_id, tenant_id, endpoint):
        async for event in generate_events():
            yield event
"""

import logging
import asyncio
from datetime import datetime
from typing import Dict, Set, Optional
from contextlib import asynccontextmanager
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)


@dataclass
class ConnectionInfo:
    """Information about an active SSE connection."""
    connection_id: str
    tenant_id: str
    endpoint: str
    started_at: datetime
    user_id: Optional[str] = None
    metadata: Optional[Dict] = None


class ConnectionManager:
    """
    Manages active SSE connections for graceful shutdown.
    
    Tracks all active connections and coordinates shutdown notifications
    when the server needs to restart or scale down.
    """
    
    def __init__(self):
        """Initialize connection manager."""
        self._connections: Dict[str, ConnectionInfo] = {}
        self._is_shutting_down = False
        self._shutdown_event = asyncio.Event()
        self._shutdown_grace_period = 20  # seconds
        logger.info("Connection manager initialized")
    
    @property
    def active_connections(self) -> int:
        """Get count of active connections."""
        return len(self._connections)
    
    @property
    def is_shutting_down(self) -> bool:
        """Check if server is shutting down."""
        return self._is_shutting_down
    
    def register_connection(
        self,
        connection_id: str,
        tenant_id: str,
        endpoint: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Register a new SSE connection.
        
        Args:
            connection_id: Unique connection identifier
            tenant_id: Tenant ID
            endpoint: SSE endpoint path
            user_id: Optional user ID
            metadata: Optional connection metadata
        """
        if self._is_shutting_down:
            raise RuntimeError("Server is shutting down, cannot accept new connections")
        
        self._connections[connection_id] = ConnectionInfo(
            connection_id=connection_id,
            tenant_id=tenant_id,
            endpoint=endpoint,
            started_at=datetime.now(),
            user_id=user_id,
            metadata=metadata
        )
        
        logger.info(
            f"Connection registered: {connection_id} "
            f"(tenant={tenant_id}, endpoint={endpoint}, total={self.active_connections})"
        )
    
    def unregister_connection(self, connection_id: str) -> None:
        """
        Unregister an SSE connection.
        
        Args:
            connection_id: Connection identifier
        """
        if connection_id in self._connections:
            conn = self._connections.pop(connection_id)
            duration = (datetime.now() - conn.started_at).total_seconds()
            
            logger.info(
                f"Connection unregistered: {connection_id} "
                f"(duration={duration:.1f}s, remaining={self.active_connections})"
            )
            
            # If shutting down and no connections left, signal completion
            if self._is_shutting_down and self.active_connections == 0:
                self._shutdown_event.set()
    
    def get_connection(self, connection_id: str) -> Optional[ConnectionInfo]:
        """
        Get connection information.
        
        Args:
            connection_id: Connection identifier
            
        Returns:
            ConnectionInfo if found, None otherwise
        """
        return self._connections.get(connection_id)
    
    def get_connections_by_tenant(self, tenant_id: str) -> Set[str]:
        """
        Get all connection IDs for a tenant.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            Set of connection IDs
        """
        return {
            conn_id
            for conn_id, conn in self._connections.items()
            if conn.tenant_id == tenant_id
        }
    
    def get_connections_by_endpoint(self, endpoint: str) -> Set[str]:
        """
        Get all connection IDs for an endpoint.
        
        Args:
            endpoint: Endpoint path
            
        Returns:
            Set of connection IDs
        """
        return {
            conn_id
            for conn_id, conn in self._connections.items()
            if conn.endpoint == endpoint
        }
    
    @asynccontextmanager
    async def track_connection(
        self,
        connection_id: str,
        tenant_id: str,
        endpoint: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ):
        """
        Context manager to track an SSE connection.
        
        Automatically registers on entry and unregisters on exit.
        
        Usage:
            async with connection_manager.track_connection(conn_id, tenant_id, endpoint):
                async for event in generate_events():
                    yield event
        
        Args:
            connection_id: Unique connection identifier
            tenant_id: Tenant ID
            endpoint: SSE endpoint path
            user_id: Optional user ID
            metadata: Optional connection metadata
        """
        # Check if shutting down before registering
        if self._is_shutting_down:
            raise RuntimeError(
                "Server is shutting down. "
                "Reconnect in 30 seconds."
            )
        
        # Register connection
        self.register_connection(
            connection_id,
            tenant_id,
            endpoint,
            user_id,
            metadata
        )
        
        try:
            yield
        finally:
            # Unregister on exit
            self.unregister_connection(connection_id)
    
    async def initiate_shutdown(self, grace_period: Optional[int] = None) -> None:
        """
        Initiate graceful shutdown of all connections.
        
        Notifies all active clients and waits for them to disconnect
        or until grace period expires.
        
        Args:
            grace_period: Grace period in seconds (default: 20s)
        """
        if self._is_shutting_down:
            logger.warning("Shutdown already in progress")
            return
        
        self._is_shutting_down = True
        grace_period = grace_period or self._shutdown_grace_period
        
        logger.warning(
            f"Initiating graceful shutdown: {self.active_connections} active connections, "
            f"grace period: {grace_period}s"
        )
        
        # If no active connections, return immediately
        if self.active_connections == 0:
            logger.info("No active connections, shutdown complete")
            return
        
        # Wait for connections to close or timeout
        try:
            await asyncio.wait_for(
                self._shutdown_event.wait(),
                timeout=grace_period
            )
            logger.info("All connections closed gracefully")
        
        except asyncio.TimeoutError:
            logger.warning(
                f"Shutdown grace period expired with {self.active_connections} "
                f"connections still active"
            )
    
    def get_shutdown_notification_event(self, reconnect_delay: int = 30) -> Dict:
        """
        Get SSE event to notify clients of shutdown.
        
        Args:
            reconnect_delay: Suggested reconnect delay in seconds
            
        Returns:
            SSE event dictionary
        """
        return {
            "event": "shutdown",
            "data": json.dumps({
                "type": "shutdown",
                "message": f"Server is restarting. Reconnect in {reconnect_delay} seconds.",
                "reconnect_delay_seconds": reconnect_delay,
                "timestamp": datetime.now().isoformat()
            })
        }
    
    def get_stats(self) -> Dict:
        """
        Get connection statistics.
        
        Returns:
            Statistics dictionary
        """
        connections_by_endpoint = {}
        connections_by_tenant = {}
        
        for conn in self._connections.values():
            # Count by endpoint
            connections_by_endpoint[conn.endpoint] = \
                connections_by_endpoint.get(conn.endpoint, 0) + 1
            
            # Count by tenant
            connections_by_tenant[conn.tenant_id] = \
                connections_by_tenant.get(conn.tenant_id, 0) + 1
        
        return {
            "total_connections": self.active_connections,
            "is_shutting_down": self._is_shutting_down,
            "connections_by_endpoint": connections_by_endpoint,
            "connections_by_tenant": connections_by_tenant,
            "oldest_connection_age_seconds": (
                min(
                    (datetime.now() - conn.started_at).total_seconds()
                    for conn in self._connections.values()
                )
                if self._connections else 0
            )
        }


# Global connection manager instance
connection_manager = ConnectionManager()
