"""
Integration tests for parallel agent execution with circuit breakers.

Tests Task P0-41: Parallel Agent Executor with Circuit Breakers

Verifies:
- Safe concurrent agent execution
- Circuit breaker failure isolation
- Timeout enforcement
- Rollback strategies
- Execution audit logging
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from src.agents.circuit_breakers import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerError,
    CircuitBreakerRegistry,
    reset_circuit_breakers,
)
from src.agents.parallel_executor import (
    ParallelAgentExecutor,
    AgentExecutionResult,
)


class TestCircuitBreakerBasics:
    """Test basic circuit breaker functionality."""
    
    @pytest.fixture(autouse=True)
    def reset(self):
        """Reset circuit breakers before each test."""
        reset_circuit_breakers()
        yield
        reset_circuit_breakers()
    
    def test_circuit_breaker_initialization(self):
        """Test circuit breaker initializes in CLOSED state."""
        breaker = CircuitBreaker(
            agent_name="TestAgent",
            failure_threshold=3,
            recovery_timeout=60
        )
        
        assert breaker.state == CircuitState.CLOSED
        assert breaker.is_closed
        assert not breaker.is_open
        assert breaker.failure_rate == 0.0
    
    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold(self):
        """Test circuit opens after failure threshold exceeded."""
        breaker = CircuitBreaker(
            agent_name="TestAgent",
            failure_threshold=3,
            recovery_timeout=60
        )
        
        # Simulate 3 failures
        for i in range(3):
            try:
                async with breaker():
                    raise ValueError(f"Simulated failure {i+1}")
            except ValueError:
                pass
        
        # Circuit should be open
        assert breaker.state == CircuitState.OPEN
        assert breaker.is_open
    
    @pytest.mark.asyncio
    async def test_circuit_blocks_requests_when_open(self):
        """Test circuit breaker blocks requests when open."""
        breaker = CircuitBreaker(
            agent_name="TestAgent",
            failure_threshold=2,
            recovery_timeout=60
        )
        
        # Cause circuit to open
        for i in range(2):
            try:
                async with breaker():
                    raise ValueError("Failure")
            except ValueError:
                pass
        
        assert breaker.is_open
        
        # Next request should be blocked
        with pytest.raises(CircuitBreakerError) as exc_info:
            async with breaker():
                pass
        
        error = exc_info.value
        assert error.agent_name == "TestAgent"
        assert error.failure_count >= 2
    
    @pytest.mark.asyncio
    async def test_circuit_recovers_after_timeout(self):
        """Test circuit moves to HALF_OPEN after recovery timeout."""
        breaker = CircuitBreaker(
            agent_name="TestAgent",
            failure_threshold=2,
            recovery_timeout=1  # 1 second for testing
        )
        
        # Cause circuit to open
        for i in range(2):
            try:
                async with breaker():
                    raise ValueError("Failure")
            except ValueError:
                pass
        
        assert breaker.is_open
        
        # Wait for recovery timeout
        await asyncio.sleep(1.1)
        
        # Next check should move to HALF_OPEN
        await breaker._check_state()
        assert breaker.state == CircuitState.HALF_OPEN
    
    @pytest.mark.asyncio
    async def test_circuit_closes_after_successful_recovery(self):
        """Test circuit closes after successful test in HALF_OPEN."""
        breaker = CircuitBreaker(
            agent_name="TestAgent",
            failure_threshold=2,
            recovery_timeout=1,
            half_open_max_requests=1
        )
        
        # Open circuit
        for i in range(2):
            try:
                async with breaker():
                    raise ValueError("Failure")
            except ValueError:
                pass
        
        # Wait for recovery
        await asyncio.sleep(1.1)
        await breaker._check_state()
        assert breaker.state == CircuitState.HALF_OPEN
        
        # Successful test request
        async with breaker():
            pass  # Success
        
        # Circuit should close
        assert breaker.state == CircuitState.CLOSED
        assert breaker.is_closed
    
    def test_circuit_breaker_statistics(self):
        """Test circuit breaker tracks statistics."""
        breaker = CircuitBreaker(
            agent_name="TestAgent",
            failure_threshold=3
        )
        
        # Record some operations
        breaker._record_success()
        breaker._record_success()
        breaker._record_failure(ValueError("Test"))
        
        stats = breaker.get_stats()
        
        assert stats["total_requests"] == 3
        assert stats["total_successes"] == 2
        assert stats["total_failures"] == 1
        assert stats["failure_rate"] == pytest.approx(0.3333, rel=0.01)


class TestCircuitBreakerRegistry:
    """Test circuit breaker registry."""
    
    @pytest.fixture(autouse=True)
    def reset(self):
        """Reset circuit breakers before each test."""
        reset_circuit_breakers()
        yield
        reset_circuit_breakers()
    
    def test_registry_get_or_create(self):
        """Test registry creates breaker on first access."""
        registry = CircuitBreakerRegistry()
        
        breaker1 = registry.get_or_create("Agent1")
        breaker2 = registry.get_or_create("Agent1")
        
        # Should return same instance
        assert breaker1 is breaker2
    
    def test_registry_multiple_breakers(self):
        """Test registry manages multiple breakers."""
        registry = CircuitBreakerRegistry()
        
        breaker1 = registry.get_or_create("Agent1")
        breaker2 = registry.get_or_create("Agent2")
        
        assert breaker1 is not breaker2
        assert breaker1.agent_name == "Agent1"
        assert breaker2.agent_name == "Agent2"
    
    def test_registry_get_all_stats(self):
        """Test getting statistics for all breakers."""
        registry = CircuitBreakerRegistry()
        
        registry.get_or_create("Agent1")
        registry.get_or_create("Agent2")
        
        stats = registry.get_all_stats()
        
        assert "Agent1" in stats
        assert "Agent2" in stats


class TestParallelExecutor:
    """Test parallel agent executor."""
    
    @pytest.fixture(autouse=True)
    def reset(self):
        """Reset circuit breakers before each test."""
        reset_circuit_breakers()
        yield
        reset_circuit_breakers()
    
    @pytest.fixture
    def mock_agent(self):
        """Create mock agent."""
        agent = MagicMock()
        agent.__class__.__name__ = "MockAgent"
        agent.execute = AsyncMock(return_value={"success": True})
        return agent
    
    @pytest.mark.asyncio
    async def test_execute_single_agent_success(self, mock_agent):
        """Test executing single agent successfully."""
        executor = ParallelAgentExecutor()
        
        results = await executor.execute_parallel_safe(
            agents=[mock_agent],
            timeout_ms=5000,
            tenant_id="tenant-123"
        )
        
        assert "MockAgent" in results
        assert results["MockAgent"].status == "success"
        assert results["MockAgent"].result == {"success": True}
    
    @pytest.mark.asyncio
    async def test_execute_multiple_agents_parallel(self):
        """Test executing multiple agents in parallel."""
        agent1 = MagicMock()
        agent1.__class__.__name__ = "Agent1"
        agent1.execute = AsyncMock(return_value={"agent": "1"})
        
        agent2 = MagicMock()
        agent2.__class__.__name__ = "Agent2"
        agent2.execute = AsyncMock(return_value={"agent": "2"})
        
        executor = ParallelAgentExecutor()
        
        start = time.time()
        results = await executor.execute_parallel_safe(
            agents=[agent1, agent2],
            timeout_ms=5000,
            tenant_id="tenant-123"
        )
        duration = time.time() - start
        
        # Both should succeed
        assert results["Agent1"].status == "success"
        assert results["Agent2"].status == "success"
        
        # Verify both were called
        agent1.execute.assert_called_once()
        agent2.execute.assert_called_once()
        
        # Should execute concurrently (faster than sequential)
        # This is hard to test precisely, but duration should be reasonable
        assert duration < 1.0  # Should complete quickly
    
    @pytest.mark.asyncio
    async def test_agent_timeout_handling(self):
        """Test agent timeout is enforced."""
        slow_agent = MagicMock()
        slow_agent.__class__.__name__ = "SlowAgent"
        
        async def slow_execute():
            await asyncio.sleep(10)  # Very slow
            return {"result": "done"}
        
        slow_agent.execute = slow_execute
        
        executor = ParallelAgentExecutor()
        
        results = await executor.execute_parallel_safe(
            agents=[slow_agent],
            timeout_ms=100,  # 100ms timeout
            tenant_id="tenant-123"
        )
        
        # Should timeout
        assert results["SlowAgent"].status == "timeout"
        assert "timed out" in results["SlowAgent"].error.lower()
    
    @pytest.mark.asyncio
    async def test_failure_isolation(self):
        """Test one agent failure doesn't affect others."""
        failing_agent = MagicMock()
        failing_agent.__class__.__name__ = "FailingAgent"
        failing_agent.execute = AsyncMock(side_effect=ValueError("Agent failed"))
        
        success_agent = MagicMock()
        success_agent.__class__.__name__ = "SuccessAgent"
        success_agent.execute = AsyncMock(return_value={"success": True})
        
        executor = ParallelAgentExecutor()
        
        results = await executor.execute_parallel_safe(
            agents=[failing_agent, success_agent],
            timeout_ms=5000,
            tenant_id="tenant-123",
            rollback_on_any_failure=False  # Don't cancel on failure
        )
        
        # Failing agent should fail
        assert results["FailingAgent"].status == "failed"
        
        # Success agent should still succeed
        assert results["SuccessAgent"].status == "success"
    
    @pytest.mark.asyncio
    async def test_rollback_on_failure(self):
        """Test rollback_on_any_failure cancels all on first failure."""
        failing_agent = MagicMock()
        failing_agent.__class__.__name__ = "FailingAgent"
        failing_agent.execute = AsyncMock(side_effect=ValueError("Agent failed"))
        
        slow_agent = MagicMock()
        slow_agent.__class__.__name__ = "SlowAgent"
        
        async def slow_execute():
            await asyncio.sleep(5)
            return {"result": "done"}
        
        slow_agent.execute = slow_execute
        
        executor = ParallelAgentExecutor()
        
        # Should raise exception due to rollback mode
        with pytest.raises(ValueError):
            await executor.execute_parallel_safe(
                agents=[failing_agent, slow_agent],
                timeout_ms=10000,
                tenant_id="tenant-123",
                rollback_on_any_failure=True
            )
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self):
        """Test parallel executor integrates with circuit breakers."""
        failing_agent = MagicMock()
        failing_agent.__class__.__name__ = "TestAgent"
        failing_agent.execute = AsyncMock(side_effect=ValueError("Failure"))
        
        executor = ParallelAgentExecutor()
        
        # Execute multiple times to trigger circuit breaker
        for i in range(5):
            results = await executor.execute_parallel_safe(
                agents=[failing_agent],
                timeout_ms=5000,
                tenant_id="tenant-123",
                circuit_breaker_enabled=True
            )
            
            # First 3 should fail, then circuit should open
            if i < 3:
                assert results["TestAgent"].status == "failed"
            else:
                # Circuit should be open, blocking requests
                assert results["TestAgent"].status == "circuit_open"


class TestExecutionLogging:
    """Test execution audit logging."""
    
    @pytest.fixture(autouse=True)
    def reset(self):
        """Reset circuit breakers."""
        reset_circuit_breakers()
        yield
        reset_circuit_breakers()
    
    @pytest.mark.asyncio
    async def test_execution_logged(self):
        """Test executions are logged."""
        agent = MagicMock()
        agent.__class__.__name__ = "TestAgent"
        agent.execute = AsyncMock(return_value={"data": "test"})
        
        executor = ParallelAgentExecutor()
        
        await executor.execute_parallel_safe(
            agents=[agent],
            timeout_ms=5000,
            tenant_id="tenant-123"
        )
        
        logs = executor.get_execution_logs()
        assert len(logs) == 1
        
        log = logs[0]
        assert log.tenant_id == "tenant-123"
        assert "TestAgent" in log.agents_executed
        assert log.success_count == 1
        assert log.failure_count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

