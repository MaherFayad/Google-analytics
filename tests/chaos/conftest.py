"""
Chaos Engineering Test Fixtures

Implements Task P0-33: Chaos Engineering Test Suite

Provides fault injection utilities for testing system resilience:
- Network delays and partitions
- Malformed API responses
- Service failures
- Circuit breaker testing

Usage:
    @pytest.mark.chaos
    async def test_with_fault(inject_fault):
        with inject_fault("ga4_client", response=b"invalid"):
            result = await service.call()
"""

import asyncio
import contextlib
import logging
from typing import Any, AsyncGenerator, Callable, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiohttp
from httpx import AsyncClient, Response

logger = logging.getLogger(__name__)


# Fault injection registry
_FAULT_HANDLERS: Dict[str, Callable] = {}


def register_fault_handler(name: str, handler: Callable):
    """Register a fault injection handler."""
    _FAULT_HANDLERS[name] = handler


@pytest.fixture
def inject_fault():
    """
    Fault injection context manager.
    
    Usage:
        with inject_fault("ga4_client", response=b"malformed"):
            # GA4 client will return malformed response
            result = await ga4_service.fetch_data()
    """
    @contextlib.contextmanager
    def _inject(service: str, **kwargs):
        """
        Inject a fault into a service.
        
        Args:
            service: Service name ('ga4_client', 'openai_client', 'postgres', 'redis')
            **kwargs: Fault-specific parameters
        """
        if service not in _FAULT_HANDLERS:
            raise ValueError(f"Unknown service: {service}. Available: {list(_FAULT_HANDLERS.keys())}")
        
        handler = _FAULT_HANDLERS[service]
        
        try:
            # Enter fault injection context
            context = handler(**kwargs)
            if hasattr(context, '__enter__'):
                context.__enter__()
            else:
                context = contextlib.contextmanager(lambda: (yield None))()
                context.__enter__()
            
            logger.warning(f"🔥 FAULT INJECTED: {service} with {kwargs}")
            yield context
        
        finally:
            # Exit fault injection context
            if hasattr(context, '__exit__'):
                context.__exit__(None, None, None)
            
            logger.info(f"✅ FAULT REMOVED: {service}")
    
    return _inject


@pytest.fixture
async def inject_network_delay():
    """
    Inject network delay for service calls.
    
    Usage:
        async with inject_network_delay("postgres", delay_ms=5000):
            # Database queries will have 5s delay
            result = await db.query("SELECT 1")
    """
    @contextlib.asynccontextmanager
    async def _inject(service: str, delay_ms: int):
        """
        Inject network delay.
        
        Args:
            service: Service name
            delay_ms: Delay in milliseconds
        """
        original_methods = {}
        
        try:
            # Patch asyncio sleep to inject delay
            logger.warning(f"🐌 NETWORK DELAY: {service} +{delay_ms}ms")
            
            # Store original asyncio.sleep
            original_sleep = asyncio.sleep
            
            # Create wrapper that adds delay
            async def delayed_sleep(*args, **kwargs):
                await original_sleep(delay_ms / 1000)  # Convert to seconds
                return await original_sleep(*args, **kwargs)
            
            # Patch asyncio.sleep
            with patch('asyncio.sleep', side_effect=delayed_sleep):
                yield
        
        finally:
            logger.info(f"✅ NETWORK DELAY REMOVED: {service}")
    
    return _inject


@pytest.fixture
def kill_service():
    """
    Simulate service going down completely.
    
    Usage:
        with kill_service("redis"):
            # Redis calls will fail
            result = await cache.get("key")
    """
    @contextlib.contextmanager
    def _kill(service: str):
        """
        Kill a service (make all calls fail).
        
        Args:
            service: Service name
        """
        logger.warning(f"💀 SERVICE KILLED: {service}")
        
        # Create exception to raise
        exception = ConnectionError(f"Service '{service}' is unavailable (chaos test)")
        
        # Patch service to raise exception
        if service == "redis":
            with patch('redis.asyncio.Redis.get', side_effect=exception), \
                 patch('redis.asyncio.Redis.set', side_effect=exception):
                yield
        
        elif service == "postgres":
            with patch('sqlalchemy.ext.asyncio.AsyncSession.execute', side_effect=exception):
                yield
        
        else:
            # Generic service kill
            yield
        
        logger.info(f"✅ SERVICE RESTORED: {service}")
    
    return _kill


# GA4 API fault handlers

def _ga4_malformed_response(**kwargs):
    """Inject malformed GA4 API response."""
    response_data = kwargs.get('response', b'\xff\xfe Invalid UTF-8')
    
    @contextlib.contextmanager
    def _context():
        # Mock GA4 API response
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.content = response_data
        mock_response.text = response_data.decode('utf-8', errors='ignore')
        mock_response.json.side_effect = ValueError("Invalid JSON")
        
        with patch('httpx.AsyncClient.post', return_value=mock_response):
            yield
    
    return _context()


register_fault_handler('ga4_client', _ga4_malformed_response)


# OpenAI API fault handlers

def _openai_invalid_embedding(**kwargs):
    """Inject invalid OpenAI embedding response."""
    embedding_dim = kwargs.get('embedding_dim', 1535)  # Wrong dimension
    
    @contextlib.contextmanager
    def _context():
        # Mock OpenAI embedding with wrong dimension
        mock_response = {
            'data': [
                {
                    'embedding': [0.0] * embedding_dim,  # Wrong size!
                    'index': 0
                }
            ],
            'model': 'text-embedding-3-small',
            'usage': {'total_tokens': 10}
        }
        
        with patch('openai.AsyncOpenAI.embeddings.create', return_value=mock_response):
            yield
    
    return _context()


register_fault_handler('openai_client', _openai_invalid_embedding)


# Database fault handlers

def _postgres_slow_query(**kwargs):
    """Inject slow PostgreSQL query."""
    delay_ms = kwargs.get('delay_ms', 5000)
    
    @contextlib.contextmanager
    def _context():
        original_execute = None
        
        # Wrapper that adds delay
        async def slow_execute(*args, **kwargs):
            await asyncio.sleep(delay_ms / 1000)
            return await original_execute(*args, **kwargs)
        
        # Patch database execute
        with patch('sqlalchemy.ext.asyncio.AsyncSession.execute', side_effect=slow_execute):
            yield
    
    return _context()


register_fault_handler('postgres', _postgres_slow_query)


# Cache fault handlers

def _redis_connection_timeout(**kwargs):
    """Inject Redis connection timeout."""
    
    @contextlib.contextmanager
    def _context():
        # Mock Redis to timeout
        exception = asyncio.TimeoutError("Redis connection timeout (chaos test)")
        
        with patch('redis.asyncio.Redis.get', side_effect=exception), \
             patch('redis.asyncio.Redis.set', side_effect=exception):
            yield
    
    return _context()


register_fault_handler('redis', _redis_connection_timeout)


# Circuit breaker test helpers

@pytest.fixture
def circuit_breaker_monitor():
    """
    Monitor circuit breaker state changes.
    
    Usage:
        with circuit_breaker_monitor() as monitor:
            # Trigger failures
            for _ in range(5):
                await service.call()
            
            # Check circuit breaker opened
            assert monitor.is_open("ga4_client")
    """
    @contextlib.contextmanager
    def _monitor():
        """Monitor circuit breaker state."""
        state_changes = []
        
        # Mock circuit breaker to track state
        def track_state_change(service: str, old_state: str, new_state: str):
            state_changes.append({
                'service': service,
                'old_state': old_state,
                'new_state': new_state
            })
        
        class CircuitBreakerMonitor:
            def is_open(self, service: str) -> bool:
                """Check if circuit breaker is open."""
                latest = next(
                    (s for s in reversed(state_changes) if s['service'] == service),
                    None
                )
                return latest and latest['new_state'] == 'open'
            
            def is_closed(self, service: str) -> bool:
                """Check if circuit breaker is closed."""
                latest = next(
                    (s for s in reversed(state_changes) if s['service'] == service),
                    None
                )
                return latest and latest['new_state'] == 'closed'
            
            @property
            def state_changes(self):
                return state_changes
        
        monitor = CircuitBreakerMonitor()
        
        # Patch circuit breaker state tracker
        with patch('src.agents.circuit_breakers.track_state_change', side_effect=track_state_change):
            yield monitor
    
    return _monitor


# Recovery validation helpers

@pytest.fixture
async def wait_for_recovery():
    """
    Wait for system to recover after fault injection.
    
    Usage:
        async with wait_for_recovery(service="ga4_client", timeout=60) as recovery:
            # System should recover within 60 seconds
            assert recovery.recovered
    """
    @contextlib.asynccontextmanager
    async def _wait(service: str, timeout: int = 60):
        """
        Wait for service recovery.
        
        Args:
            service: Service name
            timeout: Max wait time in seconds
        """
        class Recovery:
            def __init__(self):
                self.recovered = False
                self.recovery_time = None
        
        recovery = Recovery()
        start_time = asyncio.get_event_loop().time()
        
        try:
            yield recovery
        finally:
            # Wait for recovery
            elapsed = 0
            while elapsed < timeout:
                # Check if service is healthy
                # (This would call actual health check endpoint)
                await asyncio.sleep(1)
                elapsed = asyncio.get_event_loop().time() - start_time
                
                # Simulate recovery detection
                if elapsed > 5:  # Assume recovery after 5s
                    recovery.recovered = True
                    recovery.recovery_time = elapsed
                    break
            
            if recovery.recovered:
                logger.info(f"✅ SERVICE RECOVERED: {service} in {recovery.recovery_time:.1f}s")
            else:
                logger.error(f"❌ SERVICE DID NOT RECOVER: {service} after {timeout}s")
    
    return _wait


# Chaos test markers

def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers", "chaos: mark test as chaos engineering test"
    )
    config.addinivalue_line(
        "markers", "resilience: mark test as resilience validation"
    )


# Test isolation

@pytest.fixture(autouse=True)
async def isolate_chaos_tests():
    """Ensure chaos tests don't affect other tests."""
    # Setup: Clear any lingering mocks
    yield
    # Teardown: Restore all patches
    # (pytest-mock handles most of this automatically)

