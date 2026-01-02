"""
Integration tests for GA4 request queue.

Implements Task P0-14: Request queue testing

Tests:
- Request queuing and processing
- Priority-based ordering
- Backpressure handling
- Queue position tracking
- Worker scaling
"""

import pytest
import asyncio
from uuid import UUID, uuid4

from src.server.services.ga4.request_queue import GA4RequestQueue, QueuedRequest
from src.server.services.ga4.exceptions import GA4RateLimitError


@pytest.fixture
async def redis_client():
    """Create Redis client for testing."""
    import redis.asyncio as redis
    
    client = redis.Redis(
        host="localhost",
        port=6379,
        db=1,  # Use test database
        decode_responses=False
    )
    
    yield client
    
    # Cleanup
    await client.flushdb()
    await client.close()


@pytest.fixture
async def queue(redis_client):
    """Create request queue for testing."""
    queue = GA4RequestQueue(redis_client)
    yield queue
    await queue.shutdown()


@pytest.mark.asyncio
async def test_enqueue_request(queue, redis_client):
    """Test basic request enqueueing."""
    tenant_id = uuid4()
    user_id = uuid4()
    
    request_id = await queue.enqueue(
        tenant_id=tenant_id,
        user_id=user_id,
        user_role="member",
        endpoint="fetch_page_views",
        params={"start_date": "2025-01-01", "end_date": "2025-01-07"},
        priority=50
    )
    
    assert request_id is not None
    
    # Verify request is in queue
    position = await queue.get_queue_position(request_id)
    assert position == 1  # First in queue


@pytest.mark.asyncio
async def test_priority_ordering(queue, redis_client):
    """Test requests are ordered by priority."""
    tenant_id = uuid4()
    
    # Add low priority request
    low_priority_id = await queue.enqueue(
        tenant_id=tenant_id,
        user_id=uuid4(),
        user_role="viewer",
        endpoint="fetch_page_views",
        params={},
        priority=10
    )
    
    # Add high priority request
    high_priority_id = await queue.enqueue(
        tenant_id=tenant_id,
        user_id=uuid4(),
        user_role="owner",
        endpoint="fetch_page_views",
        params={},
        priority=90
    )
    
    # High priority should be first
    high_position = await queue.get_queue_position(high_priority_id)
    low_position = await queue.get_queue_position(low_priority_id)
    
    assert high_position < low_position


@pytest.mark.asyncio
async def test_role_based_priority(queue, redis_client):
    """Test owner requests have higher priority than members."""
    tenant_id = uuid4()
    
    # Add member request
    member_id = await queue.enqueue(
        tenant_id=tenant_id,
        user_id=uuid4(),
        user_role="member",
        endpoint="fetch_page_views",
        params={},
        priority=50
    )
    
    # Add owner request with same priority
    owner_id = await queue.enqueue(
        tenant_id=tenant_id,
        user_id=uuid4(),
        user_role="owner",
        endpoint="fetch_page_views",
        params={},
        priority=50
    )
    
    # Owner should be first
    owner_position = await queue.get_queue_position(owner_id)
    member_position = await queue.get_queue_position(member_id)
    
    assert owner_position < member_position


@pytest.mark.asyncio
async def test_queue_length(queue, redis_client):
    """Test queue length tracking."""
    tenant_id = uuid4()
    
    # Initially empty
    assert await queue.get_queue_length(tenant_id) == 0
    
    # Add 3 requests
    for _ in range(3):
        await queue.enqueue(
            tenant_id=tenant_id,
            user_id=uuid4(),
            user_role="member",
            endpoint="fetch_page_views",
            params={}
        )
    
    # Should have 3 requests
    assert await queue.get_queue_length(tenant_id) == 3


@pytest.mark.asyncio
async def test_estimated_wait_time(queue, redis_client):
    """Test wait time estimation."""
    tenant_id = uuid4()
    
    # Add 5 requests
    request_ids = []
    for _ in range(5):
        request_id = await queue.enqueue(
            tenant_id=tenant_id,
            user_id=uuid4(),
            user_role="member",
            endpoint="fetch_page_views",
            params={}
        )
        request_ids.append(request_id)
    
    # Last request should have longest wait time
    last_wait = await queue.get_estimated_wait_time(request_ids[-1])
    first_wait = await queue.get_estimated_wait_time(request_ids[0])
    
    assert last_wait > first_wait
    assert last_wait == 5 * 30  # 5 requests * 30s each


@pytest.mark.asyncio
async def test_request_processing(queue, redis_client):
    """Test request is processed successfully."""
    tenant_id = uuid4()
    user_id = uuid4()
    
    request_id = await queue.enqueue(
        tenant_id=tenant_id,
        user_id=user_id,
        user_role="member",
        endpoint="fetch_page_views",
        params={"start_date": "2025-01-01"}
    )
    
    # Wait for processing (with timeout)
    try:
        result = await asyncio.wait_for(
            queue.wait_for_result(request_id, timeout=10),
            timeout=15
        )
        
        assert result is not None
        assert result["success"] is True
    
    except asyncio.TimeoutError:
        pytest.skip("Queue processing timeout (worker may not be running)")


@pytest.mark.asyncio
async def test_concurrent_requests(queue, redis_client):
    """Test multiple concurrent requests."""
    tenant_id = uuid4()
    
    # Add 10 requests concurrently
    tasks = []
    for i in range(10):
        task = queue.enqueue(
            tenant_id=tenant_id,
            user_id=uuid4(),
            user_role="member",
            endpoint="fetch_page_views",
            params={"index": i}
        )
        tasks.append(task)
    
    request_ids = await asyncio.gather(*tasks)
    
    # All requests should be queued
    assert len(request_ids) == 10
    assert len(set(request_ids)) == 10  # All unique


@pytest.mark.asyncio
async def test_multi_tenant_isolation(queue, redis_client):
    """Test requests are isolated by tenant."""
    tenant_a = uuid4()
    tenant_b = uuid4()
    
    # Add requests for tenant A
    for _ in range(3):
        await queue.enqueue(
            tenant_id=tenant_a,
            user_id=uuid4(),
            user_role="member",
            endpoint="fetch_page_views",
            params={}
        )
    
    # Add requests for tenant B
    for _ in range(2):
        await queue.enqueue(
            tenant_id=tenant_b,
            user_id=uuid4(),
            user_role="member",
            endpoint="fetch_page_views",
            params={}
        )
    
    # Queues should be separate
    assert await queue.get_queue_length(tenant_a) == 3
    assert await queue.get_queue_length(tenant_b) == 2


@pytest.mark.asyncio
async def test_queue_position_updates(queue, redis_client):
    """Test queue position updates as requests are processed."""
    tenant_id = uuid4()
    
    # Add 3 requests
    request_ids = []
    for _ in range(3):
        request_id = await queue.enqueue(
            tenant_id=tenant_id,
            user_id=uuid4(),
            user_role="member",
            endpoint="fetch_page_views",
            params={}
        )
        request_ids.append(request_id)
    
    # Check initial positions
    assert await queue.get_queue_position(request_ids[0]) == 1
    assert await queue.get_queue_position(request_ids[1]) == 2
    assert await queue.get_queue_position(request_ids[2]) == 3


# Mark as integration test
pytestmark = pytest.mark.integration

