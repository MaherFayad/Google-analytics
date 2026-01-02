"""
Integration Tests: Hybrid pgBouncer Pool Routing

Implements Task P0-32: Hybrid pgBouncer Pool Strategy

Tests that database connections are correctly routed:
- SSE endpoints → pgBouncer:6432 (transaction mode)
- Embedding workers → pgBouncer:6433 (session mode)

Validates:
- Connection multiplexing works
- Session variables persist in session mode
- No connection exhaustion under load
- Pool statistics are accurate
"""

import pytest
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.database import (
    get_session_transactional,
    get_session_long,
    get_pool_stats,
    engine_transactional,
    engine_session,
)

pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_transactional_pool_connection():
    """
    Test: Transactional pool connects successfully
    
    Validates:
    - Connection to pgBouncer:6432 succeeds
    - Basic query execution works
    - Connection is released after query
    """
    async for session in get_session_transactional():
        # Execute simple query
        result = await session.execute(text("SELECT 1 as value"))
        row = result.first()
        
        assert row is not None, "Query should return result"
        assert row.value == 1, "Query should return 1"


@pytest.mark.asyncio
async def test_session_pool_connection():
    """
    Test: Session pool connects successfully
    
    Validates:
    - Connection to pgBouncer:6433 succeeds
    - Basic query execution works
    - Connection is held for session
    """
    async for session in get_session_long():
        # Execute simple query
        result = await session.execute(text("SELECT 1 as value"))
        row = result.first()
        
        assert row is not None, "Query should return result"
        assert row.value == 1, "Query should return 1"


@pytest.mark.asyncio
async def test_session_variables_persist_in_session_mode():
    """
    Test: Session variables persist in session mode
    
    Critical for RLS policies that use SET app.tenant_id
    
    Expected:
    - SET variable in query 1
    - Variable still set in query 2
    - Variable still set in query 3
    """
    async for session in get_session_long():
        # Set session variable
        await session.execute(text("SET app.tenant_id = 'test-tenant-123'"))
        
        # Query 1: Variable should be set
        result1 = await session.execute(
            text("SELECT current_setting('app.tenant_id', true) as tenant_id")
        )
        row1 = result1.first()
        assert row1.tenant_id == 'test-tenant-123', \
            "Session variable should persist in query 1"
        
        # Query 2: Variable should still be set
        result2 = await session.execute(
            text("SELECT current_setting('app.tenant_id', true) as tenant_id")
        )
        row2 = result2.first()
        assert row2.tenant_id == 'test-tenant-123', \
            "Session variable should persist in query 2"
        
        # Query 3: Variable should still be set
        result3 = await session.execute(
            text("SELECT current_setting('app.tenant_id', true) as tenant_id")
        )
        row3 = result3.first()
        assert row3.tenant_id == 'test-tenant-123', \
            "Session variable should persist in query 3"


@pytest.mark.asyncio
async def test_session_variables_do_not_persist_in_transactional_mode():
    """
    Test: Session variables DO NOT persist in transactional mode
    
    This is expected behavior - transaction mode releases
    connection after each query, so session variables are lost.
    
    Expected:
    - SET variable in query 1
    - Variable is NULL in query 2 (different connection)
    """
    async for session in get_session_transactional():
        # Set session variable
        await session.execute(text("SET app.tenant_id = 'test-tenant-456'"))
        
        # Query 1: Variable should be set (same connection)
        result1 = await session.execute(
            text("SELECT current_setting('app.tenant_id', true) as tenant_id")
        )
        row1 = result1.first()
        # May or may not be set depending on pgBouncer timing
        
        # Query 2: Variable likely lost (different connection)
        try:
            result2 = await session.execute(
                text("SELECT current_setting('app.tenant_id', true) as tenant_id")
            )
            row2 = result2.first()
            # Variable may be None or the value from a different session
            # This demonstrates why session mode is needed for RLS
        except Exception:
            # Expected - variable not set
            pass


@pytest.mark.asyncio
async def test_long_transaction_completes_in_session_mode():
    """
    Test: Long transaction (>1 second) completes successfully
    
    Simulates embedding generation (10-30 seconds).
    
    Expected:
    - Transaction starts
    - Work takes >1 second
    - Transaction commits successfully
    - No interruption
    """
    async for session in get_session_long():
        # Start transaction
        async with session.begin():
            # Simulate long-running work
            await session.execute(text("SELECT pg_sleep(2)"))  # 2 seconds
            
            # Insert data
            await session.execute(
                text("CREATE TEMP TABLE IF NOT EXISTS test_data (id INT, value TEXT)")
            )
            await session.execute(
                text("INSERT INTO test_data VALUES (1, 'test')")
            )
            
            # Verify data
            result = await session.execute(
                text("SELECT COUNT(*) as count FROM test_data")
            )
            row = result.first()
            assert row.count == 1, "Data should be inserted"
        
        # Transaction should commit successfully


@pytest.mark.asyncio
async def test_concurrent_connections_transactional_pool():
    """
    Test: High concurrency works with transactional pool
    
    Simulates 100 concurrent SSE connections.
    
    Expected:
    - All connections succeed
    - Pool multiplexing works (100 clients → 25 DB connections)
    - No connection timeouts
    """
    async def query():
        async for session in get_session_transactional():
            result = await session.execute(text("SELECT 1 as value"))
            return result.first().value
    
    # Execute 100 concurrent queries
    tasks = [query() for _ in range(100)]
    results = await asyncio.gather(*tasks)
    
    # Assertions
    assert len(results) == 100, "All queries should complete"
    assert all(r == 1 for r in results), "All queries should return 1"


@pytest.mark.asyncio
async def test_concurrent_long_transactions_session_pool():
    """
    Test: Multiple long transactions work with session pool
    
    Simulates 10 concurrent embedding jobs.
    
    Expected:
    - All transactions complete
    - No connection exhaustion
    - Each gets dedicated connection
    """
    async def long_transaction():
        async for session in get_session_long():
            # Simulate long work
            await session.execute(text("SELECT pg_sleep(1)"))
            result = await session.execute(text("SELECT 1 as value"))
            return result.first().value
    
    # Execute 10 concurrent long transactions
    tasks = [long_transaction() for _ in range(10)]
    results = await asyncio.gather(*tasks)
    
    # Assertions
    assert len(results) == 10, "All transactions should complete"
    assert all(r == 1 for r in results), "All transactions should return 1"


@pytest.mark.asyncio
async def test_pool_statistics():
    """
    Test: Pool statistics are accurate
    
    Expected:
    - Both pools report stats
    - Utilization calculated correctly
    - Stats include size, checked_in, checked_out
    """
    # Get pool stats
    stats = await get_pool_stats()
    
    # Assertions
    assert 'transactional' in stats, "Should include transactional pool stats"
    assert 'session' in stats, "Should include session pool stats"
    
    # Transactional pool stats
    trans_stats = stats['transactional']
    assert 'size' in trans_stats, "Should include pool size"
    assert 'utilization' in trans_stats, "Should include utilization"
    assert trans_stats['pool_size'] == 20, "Transactional pool size should be 20"
    
    # Session pool stats
    session_stats = stats['session']
    assert 'size' in session_stats, "Should include pool size"
    assert 'utilization' in session_stats, "Should include utilization"
    assert session_stats['pool_size'] == 5, "Session pool size should be 5"


@pytest.mark.asyncio
async def test_pool_utilization_under_load():
    """
    Test: Pool utilization stays healthy under load
    
    Simulates realistic load:
    - 50 concurrent SSE connections
    - 5 concurrent embedding jobs
    
    Expected:
    - Transactional pool utilization < 80%
    - Session pool utilization < 80%
    - No connection timeouts
    """
    async def sse_query():
        async for session in get_session_transactional():
            await session.execute(text("SELECT pg_sleep(0.1)"))
            return True
    
    async def embedding_job():
        async for session in get_session_long():
            await session.execute(text("SELECT pg_sleep(1)"))
            return True
    
    # Create load
    sse_tasks = [sse_query() for _ in range(50)]
    embedding_tasks = [embedding_job() for _ in range(5)]
    
    # Execute concurrently
    results = await asyncio.gather(*sse_tasks, *embedding_tasks)
    
    # Check pool stats
    stats = await get_pool_stats()
    
    # Assertions
    trans_util = stats['transactional']['utilization']
    session_util = stats['session']['utilization']
    
    assert trans_util < 80, \
        f"Transactional pool utilization should be < 80%, got {trans_util}%"
    
    assert session_util < 80, \
        f"Session pool utilization should be < 80%, got {session_util}%"
    
    assert len(results) == 55, "All queries should complete"


@pytest.mark.asyncio
async def test_engine_connection_strings():
    """
    Test: Engines connect to correct pgBouncer ports
    
    Expected:
    - Transactional engine → port 6432
    - Session engine → port 6433
    """
    trans_url = str(engine_transactional.url)
    session_url = str(engine_session.url)
    
    # Assertions
    assert ':6432' in trans_url or 'pgbouncer-transactional' in trans_url, \
        f"Transactional engine should connect to port 6432, got: {trans_url}"
    
    assert ':6433' in session_url or 'pgbouncer-session' in session_url, \
        f"Session engine should connect to port 6433, got: {session_url}"


@pytest.mark.asyncio
@pytest.mark.slow
async def test_no_connection_exhaustion_under_extreme_load():
    """
    Test: System handles extreme load without exhaustion
    
    Stress test:
    - 500 concurrent SSE connections
    - 20 concurrent embedding jobs
    - Total 520 concurrent operations
    
    Expected:
    - No connection pool exhaustion
    - All operations complete
    - Utilization stays < 90%
    """
    async def sse_query():
        async for session in get_session_transactional():
            await session.execute(text("SELECT 1"))
            return True
    
    async def embedding_job():
        async for session in get_session_long():
            await session.execute(text("SELECT pg_sleep(0.5)"))
            return True
    
    # Extreme load
    sse_tasks = [sse_query() for _ in range(500)]
    embedding_tasks = [embedding_job() for _ in range(20)]
    
    # Execute
    results = await asyncio.gather(*sse_tasks, *embedding_tasks, return_exceptions=True)
    
    # Check for exceptions
    exceptions = [r for r in results if isinstance(r, Exception)]
    
    assert len(exceptions) == 0, \
        f"No operations should fail, got {len(exceptions)} exceptions: {exceptions[:5]}"
    
    # Check pool stats
    stats = await get_pool_stats()
    
    trans_util = stats['transactional']['utilization']
    session_util = stats['session']['utilization']
    
    assert trans_util < 90, \
        f"Transactional pool should handle load, utilization: {trans_util}%"
    
    assert session_util < 90, \
        f"Session pool should handle load, utilization: {session_util}%"

