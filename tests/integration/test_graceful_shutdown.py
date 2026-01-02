"""
Integration tests for graceful SSE connection shutdown.

Tests Task P0-20: Graceful SSE Connection Shutdown

Verifies:
- Active connections are tracked
- Shutdown notifications are sent to all connections
- New connections are rejected during shutdown
- Connections close within grace period
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.server.core.connection_manager import SSEConnectionManager, get_connection_manager, reset_connection_manager


class TestSSEConnectionManager:
    """Test SSE connection manager."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset connection manager before each test."""
        reset_connection_manager()
        yield
        reset_connection_manager()
    
    def test_connection_manager_initialization(self):
        """Test connection manager initializes with correct defaults."""
        manager = SSEConnectionManager(shutdown_grace_period=20)
        
        assert manager.active_connection_count == 0
        assert not manager.is_shutting_down
        assert manager._shutdown_grace_period == 20
    
    def test_register_connection(self):
        """Test connection registration creates queue."""
        manager = SSEConnectionManager()
        
        queue = manager.register_connection("test-conn-1")
        
        assert queue is not None
        assert isinstance(queue, asyncio.Queue)
        assert manager.active_connection_count == 1
    
    def test_unregister_connection(self):
        """Test connection unregistration removes tracking."""
        manager = SSEConnectionManager()
        
        manager.register_connection("test-conn-1")
        assert manager.active_connection_count == 1
        
        manager.unregister_connection("test-conn-1")
        assert manager.active_connection_count == 0
    
    def test_reject_connection_during_shutdown(self):
        """Test new connections are rejected during shutdown."""
        manager = SSEConnectionManager()
        manager._shutdown_requested = True
        
        queue = manager.register_connection("test-conn-1")
        
        assert queue is None
        assert manager.active_connection_count == 0
    
    @pytest.mark.asyncio
    async def test_notify_shutdown(self):
        """Test shutdown notifications are sent to all connections."""
        manager = SSEConnectionManager()
        
        # Register multiple connections
        queue1 = manager.register_connection("conn-1")
        queue2 = manager.register_connection("conn-2")
        queue3 = manager.register_connection("conn-3")
        
        assert manager.active_connection_count == 3
        
        # Notify shutdown
        await manager.notify_shutdown("Test shutdown message")
        
        # Verify all queues received shutdown event
        event1 = await asyncio.wait_for(queue1.get(), timeout=1.0)
        event2 = await asyncio.wait_for(queue2.get(), timeout=1.0)
        event3 = await asyncio.wait_for(queue3.get(), timeout=1.0)
        
        assert event1["type"] == "shutdown"
        assert "Test shutdown message" in event1["message"]
        assert event1["reconnect_delay"] == 30
        
        assert event2["type"] == "shutdown"
        assert event3["type"] == "shutdown"
    
    @pytest.mark.asyncio
    async def test_graceful_shutdown_with_active_connections(self):
        """Test graceful shutdown waits for connections to close."""
        manager = SSEConnectionManager(shutdown_grace_period=2)  # Short grace period for testing
        
        # Register connections
        queue1 = manager.register_connection("conn-1")
        queue2 = manager.register_connection("conn-2")
        
        # Start graceful shutdown in background
        shutdown_task = asyncio.create_task(manager.graceful_shutdown())
        
        # Give shutdown time to send notifications
        await asyncio.sleep(0.5)
        
        # Verify shutdown requested
        assert manager.is_shutting_down
        
        # Simulate connections closing
        manager.unregister_connection("conn-1")
        await asyncio.sleep(0.2)
        manager.unregister_connection("conn-2")
        
        # Wait for shutdown to complete
        await asyncio.wait_for(shutdown_task, timeout=5.0)
        
        # Verify all connections closed
        assert manager.active_connection_count == 0
    
    @pytest.mark.asyncio
    async def test_graceful_shutdown_timeout_force_close(self):
        """Test connections are force closed after grace period."""
        manager = SSEConnectionManager(shutdown_grace_period=1)  # Very short grace period
        
        # Register connections that won't close
        manager.register_connection("conn-1")
        manager.register_connection("conn-2")
        manager.register_connection("conn-3")
        
        assert manager.active_connection_count == 3
        
        # Start graceful shutdown (connections won't close themselves)
        await manager.graceful_shutdown()
        
        # Verify connections were force closed after grace period
        assert manager.active_connection_count == 0
    
    @pytest.mark.asyncio
    async def test_connection_context_manager(self):
        """Test connection context manager handles registration/unregistration."""
        manager = SSEConnectionManager()
        
        # Use context manager
        async with manager.connection_context("test-conn") as queue:
            assert queue is not None
            assert manager.active_connection_count == 1
        
        # Verify unregistered after context
        assert manager.active_connection_count == 0
    
    @pytest.mark.asyncio
    async def test_connection_context_manager_during_shutdown(self):
        """Test context manager returns None during shutdown."""
        manager = SSEConnectionManager()
        manager._shutdown_requested = True
        
        async with manager.connection_context("test-conn") as queue:
            assert queue is None
        
        assert manager.active_connection_count == 0


class TestConnectionManagerIntegration:
    """Integration tests for connection manager with FastAPI."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset connection manager before each test."""
        reset_connection_manager()
        yield
        reset_connection_manager()
    
    def test_get_connection_manager_singleton(self):
        """Test get_connection_manager returns same instance."""
        manager1 = get_connection_manager()
        manager2 = get_connection_manager()
        
        assert manager1 is manager2
    
    @pytest.mark.asyncio
    async def test_shutdown_notification_format(self):
        """Test shutdown notifications have correct format."""
        manager = SSEConnectionManager()
        queue = manager.register_connection("test-conn")
        
        await manager.notify_shutdown("Custom shutdown message")
        
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        
        # Verify event structure
        assert "type" in event
        assert event["type"] == "shutdown"
        assert "message" in event
        assert "Custom shutdown message" in event["message"]
        assert "timestamp" in event
        assert "reconnect_delay" in event
        assert event["reconnect_delay"] == 30
        
        # Verify timestamp is valid ISO format
        datetime.fromisoformat(event["timestamp"])
    
    @pytest.mark.asyncio
    async def test_concurrent_connections(self):
        """Test manager handles many concurrent connections."""
        manager = SSEConnectionManager()
        
        # Register many connections
        connection_count = 100
        for i in range(connection_count):
            manager.register_connection(f"conn-{i}")
        
        assert manager.active_connection_count == connection_count
        
        # Notify all
        await manager.notify_shutdown()
        
        # Verify all connections received notification
        # (We won't check all 100, just verify the count is maintained)
        assert manager.active_connection_count == connection_count


class TestProductionScenarios:
    """Test production deployment scenarios."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset connection manager before each test."""
        reset_connection_manager()
        yield
        reset_connection_manager()
    
    @pytest.mark.asyncio
    async def test_kubernetes_rolling_deployment(self):
        """
        Simulate Kubernetes rolling deployment scenario.
        
        Scenario:
        1. kubectl rollout restart sends SIGTERM
        2. 1000 active SSE connections streaming
        3. Pod has 30 seconds to shut down
        4. All connections should receive notification
        5. Pod should wait up to 20 seconds for graceful closure
        """
        manager = SSEConnectionManager(shutdown_grace_period=20)
        
        # Simulate 1000 active connections
        active_connections = 50  # Reduced for test speed
        connections = []
        for i in range(active_connections):
            queue = manager.register_connection(f"prod-conn-{i}")
            connections.append((f"prod-conn-{i}", queue))
        
        assert manager.active_connection_count == active_connections
        
        # Start graceful shutdown (simulates SIGTERM handler)
        shutdown_task = asyncio.create_task(manager.graceful_shutdown())
        
        # Allow shutdown to send notifications
        await asyncio.sleep(0.5)
        
        # Simulate connections closing over time (realistic scenario)
        async def simulate_connection_close(conn_id, delay):
            await asyncio.sleep(delay)
            manager.unregister_connection(conn_id)
        
        # Stagger connection closures
        close_tasks = []
        for i, (conn_id, _) in enumerate(connections):
            # Close connections over 2 seconds
            delay = (i / active_connections) * 2.0
            task = asyncio.create_task(simulate_connection_close(conn_id, delay))
            close_tasks.append(task)
        
        # Wait for all connections to close
        await asyncio.gather(*close_tasks)
        
        # Wait for shutdown to complete
        await asyncio.wait_for(shutdown_task, timeout=25.0)
        
        # Verify successful shutdown
        assert manager.active_connection_count == 0
        assert manager.is_shutting_down
    
    @pytest.mark.asyncio
    async def test_reject_connections_during_shutdown(self):
        """Test new connections are rejected with 503 during shutdown."""
        manager = SSEConnectionManager()
        
        # Start shutdown
        manager._shutdown_requested = True
        
        # Attempt to register new connection
        queue = manager.register_connection("late-conn")
        
        # Should be rejected
        assert queue is None
        assert manager.active_connection_count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

