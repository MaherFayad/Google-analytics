"""
Integration Tests for Graceful SSE Connection Shutdown

Implements Task P0-20: Graceful SSE Connection Shutdown

Tests:
- Connection registration and tracking
- Shutdown notification delivery
- Grace period enforcement
- Zero-downtime deployments
- Connection draining
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.server.core.connection_manager import ConnectionManager, ConnectionInfo


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def connection_manager():
    """Fresh connection manager instance for each test."""
    return ConnectionManager()


@pytest.fixture
def mock_connections():
    """Mock connection data."""
    return [
        ("conn-1", "tenant-1", "/stream/analytics"),
        ("conn-2", "tenant-1", "/stream/reports"),
        ("conn-3", "tenant-2", "/stream/analytics"),
    ]


# ============================================================================
# Connection Registration Tests
# ============================================================================

def test_register_connection(connection_manager):
    """Test connection registration."""
    connection_id = "test-conn-1"
    tenant_id = "tenant-123"
    endpoint = "/stream/test"
    
    connection_manager.register_connection(connection_id, tenant_id, endpoint)
    
    assert connection_manager.active_connections == 1
    assert connection_id in connection_manager._connections
    
    conn = connection_manager.get_connection(connection_id)
    assert conn is not None
    assert conn.connection_id == connection_id
    assert conn.tenant_id == tenant_id
    assert conn.endpoint == endpoint


def test_unregister_connection(connection_manager):
    """Test connection unregistration."""
    connection_id = "test-conn-1"
    tenant_id = "tenant-123"
    endpoint = "/stream/test"
    
    connection_manager.register_connection(connection_id, tenant_id, endpoint)
    assert connection_manager.active_connections == 1
    
    connection_manager.unregister_connection(connection_id)
    assert connection_manager.active_connections == 0
    assert connection_manager.get_connection(connection_id) is None


def test_register_connection_during_shutdown(connection_manager):
    """Test that new connections are rejected during shutdown."""
    connection_manager._is_shutting_down = True
    
    with pytest.raises(RuntimeError, match="Server is shutting down"):
        connection_manager.register_connection("conn-1", "tenant-1", "/stream/test")


def test_multiple_connections(connection_manager, mock_connections):
    """Test registering multiple connections."""
    for conn_id, tenant_id, endpoint in mock_connections:
        connection_manager.register_connection(conn_id, tenant_id, endpoint)
    
    assert connection_manager.active_connections == len(mock_connections)


# ============================================================================
# Connection Tracking Tests
# ============================================================================

@pytest.mark.asyncio
async def test_track_connection_context_manager(connection_manager):
    """Test connection tracking with context manager."""
    connection_id = "test-conn-1"
    tenant_id = "tenant-123"
    endpoint = "/stream/test"
    
    assert connection_manager.active_connections == 0
    
    async with connection_manager.track_connection(connection_id, tenant_id, endpoint):
        assert connection_manager.active_connections == 1
        assert connection_manager.get_connection(connection_id) is not None
    
    assert connection_manager.active_connections == 0
    assert connection_manager.get_connection(connection_id) is None


@pytest.mark.asyncio
async def test_track_connection_with_exception(connection_manager):
    """Test that connections are cleaned up even if exception occurs."""
    connection_id = "test-conn-1"
    tenant_id = "tenant-123"
    endpoint = "/stream/test"
    
    try:
        async with connection_manager.track_connection(connection_id, tenant_id, endpoint):
            assert connection_manager.active_connections == 1
            raise ValueError("Test exception")
    except ValueError:
        pass
    
    # Connection should be cleaned up
    assert connection_manager.active_connections == 0


@pytest.mark.asyncio
async def test_track_connection_during_shutdown(connection_manager):
    """Test that tracking fails when server is shutting down."""
    connection_manager._is_shutting_down = True
    
    with pytest.raises(RuntimeError, match="Server is shutting down"):
        async with connection_manager.track_connection("conn-1", "tenant-1", "/stream/test"):
            pass


# ============================================================================
# Graceful Shutdown Tests
# ============================================================================

@pytest.mark.asyncio
async def test_initiate_shutdown_no_connections(connection_manager):
    """Test shutdown with no active connections."""
    start_time = asyncio.get_event_loop().time()
    
    await connection_manager.initiate_shutdown(grace_period=5)
    
    elapsed = asyncio.get_event_loop().time() - start_time
    
    assert connection_manager.is_shutting_down
    assert elapsed < 1  # Should complete immediately


@pytest.mark.asyncio
async def test_initiate_shutdown_with_connections(connection_manager, mock_connections):
    """Test shutdown waits for connections to close."""
    # Register connections
    for conn_id, tenant_id, endpoint in mock_connections:
        connection_manager.register_connection(conn_id, tenant_id, endpoint)
    
    assert connection_manager.active_connections == len(mock_connections)
    
    # Start shutdown in background
    shutdown_task = asyncio.create_task(
        connection_manager.initiate_shutdown(grace_period=5)
    )
    
    # Give shutdown time to start
    await asyncio.sleep(0.1)
    assert connection_manager.is_shutting_down
    
    # Close connections one by one
    for conn_id, _, _ in mock_connections:
        await asyncio.sleep(0.5)
        connection_manager.unregister_connection(conn_id)
    
    # Wait for shutdown to complete
    await shutdown_task
    
    assert connection_manager.active_connections == 0


@pytest.mark.asyncio
async def test_shutdown_grace_period_timeout(connection_manager, mock_connections):
    """Test shutdown times out if connections don't close."""
    # Register connections
    for conn_id, tenant_id, endpoint in mock_connections:
        connection_manager.register_connection(conn_id, tenant_id, endpoint)
    
    # Shutdown with short grace period
    start_time = asyncio.get_event_loop().time()
    await connection_manager.initiate_shutdown(grace_period=1)
    elapsed = asyncio.get_event_loop().time() - start_time
    
    # Should timeout after ~1 second
    assert 0.9 < elapsed < 1.5
    assert connection_manager.is_shutting_down
    # Connections still active (timeout occurred)
    assert connection_manager.active_connections > 0


@pytest.mark.asyncio
async def test_shutdown_idempotent(connection_manager):
    """Test that calling shutdown multiple times is safe."""
    await connection_manager.initiate_shutdown(grace_period=1)
    
    # Call again
    await connection_manager.initiate_shutdown(grace_period=1)
    
    assert connection_manager.is_shutting_down


# ============================================================================
# Shutdown Notification Tests
# ============================================================================

def test_get_shutdown_notification_event(connection_manager):
    """Test shutdown notification event format."""
    event = connection_manager.get_shutdown_notification_event(reconnect_delay=30)
    
    assert event["event"] == "shutdown"
    assert "data" in event
    
    import json
    data = json.loads(event["data"])
    
    assert data["type"] == "shutdown"
    assert "message" in data
    assert data["reconnect_delay_seconds"] == 30
    assert "timestamp" in data


# ============================================================================
# Connection Query Tests
# ============================================================================

def test_get_connections_by_tenant(connection_manager, mock_connections):
    """Test querying connections by tenant."""
    for conn_id, tenant_id, endpoint in mock_connections:
        connection_manager.register_connection(conn_id, tenant_id, endpoint)
    
    tenant1_conns = connection_manager.get_connections_by_tenant("tenant-1")
    tenant2_conns = connection_manager.get_connections_by_tenant("tenant-2")
    
    assert len(tenant1_conns) == 2  # conn-1, conn-2
    assert len(tenant2_conns) == 1  # conn-3
    assert "conn-1" in tenant1_conns
    assert "conn-2" in tenant1_conns
    assert "conn-3" in tenant2_conns


def test_get_connections_by_endpoint(connection_manager, mock_connections):
    """Test querying connections by endpoint."""
    for conn_id, tenant_id, endpoint in mock_connections:
        connection_manager.register_connection(conn_id, tenant_id, endpoint)
    
    analytics_conns = connection_manager.get_connections_by_endpoint("/stream/analytics")
    reports_conns = connection_manager.get_connections_by_endpoint("/stream/reports")
    
    assert len(analytics_conns) == 2  # conn-1, conn-3
    assert len(reports_conns) == 1    # conn-2


def test_get_stats(connection_manager, mock_connections):
    """Test connection statistics."""
    for conn_id, tenant_id, endpoint in mock_connections:
        connection_manager.register_connection(conn_id, tenant_id, endpoint)
    
    stats = connection_manager.get_stats()
    
    assert stats["total_connections"] == 3
    assert not stats["is_shutting_down"]
    assert "/stream/analytics" in stats["connections_by_endpoint"]
    assert "/stream/reports" in stats["connections_by_endpoint"]
    assert "tenant-1" in stats["connections_by_tenant"]
    assert "tenant-2" in stats["connections_by_tenant"]
    assert stats["oldest_connection_age_seconds"] >= 0


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_full_shutdown_workflow(connection_manager):
    """Test complete shutdown workflow."""
    # Step 1: Register multiple connections
    connections = [
        ("conn-1", "tenant-1", "/stream/analytics"),
        ("conn-2", "tenant-1", "/stream/reports"),
        ("conn-3", "tenant-2", "/stream/analytics"),
    ]
    
    for conn_id, tenant_id, endpoint in connections:
        connection_manager.register_connection(conn_id, tenant_id, endpoint)
    
    assert connection_manager.active_connections == 3
    
    # Step 2: Initiate shutdown
    shutdown_task = asyncio.create_task(
        connection_manager.initiate_shutdown(grace_period=5)
    )
    
    await asyncio.sleep(0.1)
    assert connection_manager.is_shutting_down
    
    # Step 3: Attempt to register new connection (should fail)
    with pytest.raises(RuntimeError):
        connection_manager.register_connection("conn-4", "tenant-1", "/stream/test")
    
    # Step 4: Close existing connections gracefully
    for conn_id, _, _ in connections:
        await asyncio.sleep(0.2)
        connection_manager.unregister_connection(conn_id)
    
    # Step 5: Wait for shutdown to complete
    await shutdown_task
    
    assert connection_manager.active_connections == 0


@pytest.mark.asyncio
async def test_zero_downtime_deployment_simulation(connection_manager):
    """Simulate zero-downtime rolling deployment."""
    # Phase 1: Server running with active connections
    active_connections = []
    for i in range(10):
        conn_id = f"conn-{i}"
        connection_manager.register_connection(
            conn_id, f"tenant-{i % 3}", "/stream/analytics"
        )
        active_connections.append(conn_id)
    
    assert connection_manager.active_connections == 10
    
    # Phase 2: Deployment starts - initiate shutdown
    shutdown_task = asyncio.create_task(
        connection_manager.initiate_shutdown(grace_period=3)
    )
    
    await asyncio.sleep(0.1)
    
    # Phase 3: New connections rejected
    with pytest.raises(RuntimeError):
        connection_manager.register_connection("new-conn", "tenant-1", "/stream/test")
    
    # Phase 4: Existing connections close over time
    for conn_id in active_connections[:5]:  # Close half immediately
        connection_manager.unregister_connection(conn_id)
    
    await asyncio.sleep(0.5)
    
    for conn_id in active_connections[5:]:  # Close rest
        connection_manager.unregister_connection(conn_id)
    
    # Phase 5: Shutdown completes
    await shutdown_task
    
    assert connection_manager.active_connections == 0
    assert connection_manager.is_shutting_down


# ============================================================================
# Performance Tests
# ============================================================================

@pytest.mark.asyncio
async def test_connection_registration_performance(connection_manager):
    """Test connection registration is fast."""
    import time
    
    start = time.time()
    
    for i in range(1000):
        connection_manager.register_connection(
            f"conn-{i}",
            f"tenant-{i % 10}",
            "/stream/test"
        )
    
    elapsed = time.time() - start
    
    assert elapsed < 1.0  # Should complete in < 1 second
    assert connection_manager.active_connections == 1000


@pytest.mark.asyncio
async def test_shutdown_with_many_connections(connection_manager):
    """Test shutdown handles many connections efficiently."""
    # Register 100 connections
    for i in range(100):
        connection_manager.register_connection(
            f"conn-{i}",
            f"tenant-{i % 10}",
            "/stream/test"
        )
    
    # Start shutdown
    shutdown_task = asyncio.create_task(
        connection_manager.initiate_shutdown(grace_period=2)
    )
    
    await asyncio.sleep(0.1)
    
    # Close all connections quickly
    for i in range(100):
        connection_manager.unregister_connection(f"conn-{i}")
    
    # Shutdown should complete quickly after last connection closes
    import time
    start = time.time()
    await shutdown_task
    elapsed = time.time() - start
    
    assert elapsed < 0.5  # Should complete within 0.5s after last connection closed


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
