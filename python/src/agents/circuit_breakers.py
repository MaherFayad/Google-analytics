"""
Per-Agent Circuit Breakers for Failure Isolation.

Implements Task P0-41: Parallel Agent Executor with Circuit Breakers

Provides:
- Circuit breaker pattern for each agent
- Failure counting and threshold detection
- Automatic recovery after cooldown period
- Prometheus metrics for monitoring

Circuit breaker states:
- CLOSED: Normal operation, requests pass through
- OPEN: Too many failures, requests blocked
- HALF_OPEN: Testing if service recovered

Usage:
    breaker = CircuitBreaker(
        agent_name="EmbeddingAgent",
        failure_threshold=3,
        recovery_timeout=60
    )
    
    async with breaker:
        result = await agent.execute()
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Callable, Any
from enum import Enum
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failures exceeded, blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""
    
    def __init__(self, agent_name: str, failure_count: int, recovery_time: datetime):
        self.agent_name = agent_name
        self.failure_count = failure_count
        self.recovery_time = recovery_time
        
        message = (
            f"Circuit breaker OPEN for {agent_name}. "
            f"Failures: {failure_count}. "
            f"Recovery at: {recovery_time.isoformat()}"
        )
        super().__init__(message)


class CircuitBreaker:
    """
    Circuit breaker for agent failure isolation.
    
    Implements Task P0-41: Per-agent circuit breakers
    
    Features:
    - Tracks failures per agent
    - Opens circuit after threshold
    - Automatic recovery after timeout
    - Half-open state for testing recovery
    
    Example:
        breaker = CircuitBreaker("EmbeddingAgent", failure_threshold=3)
        
        async with breaker:
            result = await embedding_agent.execute()
    """
    
    def __init__(
        self,
        agent_name: str,
        failure_threshold: int = 3,
        recovery_timeout: int = 60,
        half_open_max_requests: int = 1
    ):
        """
        Initialize circuit breaker.
        
        Args:
            agent_name: Name of agent to protect
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds before attempting recovery
            half_open_max_requests: Number of requests to test in half-open state
        """
        self.agent_name = agent_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_requests = half_open_max_requests
        
        # State tracking
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._opened_at: Optional[float] = None
        self._half_open_requests = 0
        
        # Metrics
        self._total_requests = 0
        self._total_failures = 0
        self._total_successes = 0
        
        logger.info(
            f"Circuit breaker initialized for {agent_name} "
            f"(threshold: {failure_threshold}, recovery: {recovery_timeout}s)"
        )
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state
    
    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking requests)."""
        return self._state == CircuitState.OPEN
    
    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self._state == CircuitState.CLOSED
    
    @property
    def failure_rate(self) -> float:
        """Calculate failure rate (0.0 to 1.0)."""
        if self._total_requests == 0:
            return 0.0
        return self._total_failures / self._total_requests
    
    def _should_attempt_recovery(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if not self._opened_at:
            return False
        
        elapsed = time.time() - self._opened_at
        return elapsed >= self.recovery_timeout
    
    async def _check_state(self):
        """Check and update circuit state."""
        if self._state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if self._should_attempt_recovery():
                logger.info(
                    f"Circuit breaker for {self.agent_name} moving to HALF_OPEN "
                    f"(recovery timeout passed)"
                )
                self._state = CircuitState.HALF_OPEN
                self._half_open_requests = 0
    
    def _record_success(self):
        """Record successful execution."""
        self._total_requests += 1
        self._total_successes += 1
        
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_requests += 1
            
            # If enough test requests succeeded, close circuit
            if self._half_open_requests >= self.half_open_max_requests:
                logger.info(
                    f"Circuit breaker for {self.agent_name} closing "
                    f"(recovery successful)"
                )
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._last_failure_time = None
                self._opened_at = None
        
        elif self._state == CircuitState.CLOSED:
            # Reset failure count on success
            self._failure_count = 0
    
    def _record_failure(self, error: Exception):
        """Record failed execution."""
        self._total_requests += 1
        self._total_failures += 1
        self._failure_count += 1
        self._last_failure_time = time.time()
        
        logger.warning(
            f"Circuit breaker for {self.agent_name}: failure #{self._failure_count} "
            f"(threshold: {self.failure_threshold}). Error: {error}"
        )
        
        # Check if threshold exceeded
        if self._failure_count >= self.failure_threshold:
            if self._state == CircuitState.CLOSED:
                logger.error(
                    f"Circuit breaker for {self.agent_name} OPENING "
                    f"(failures: {self._failure_count}/{self.failure_threshold})"
                )
                self._state = CircuitState.OPEN
                self._opened_at = time.time()
            
            elif self._state == CircuitState.HALF_OPEN:
                # Recovery test failed, reopen circuit
                logger.error(
                    f"Circuit breaker for {self.agent_name} reopening "
                    f"(recovery test failed)"
                )
                self._state = CircuitState.OPEN
                self._opened_at = time.time()
                self._half_open_requests = 0
    
    @asynccontextmanager
    async def __call__(self):
        """
        Context manager for circuit breaker.
        
        Usage:
            async with circuit_breaker:
                result = await agent.execute()
        
        Raises:
            CircuitBreakerError: If circuit is open
        """
        # Check state before allowing execution
        await self._check_state()
        
        if self._state == CircuitState.OPEN:
            recovery_time = datetime.fromtimestamp(
                self._opened_at + self.recovery_timeout
            )
            raise CircuitBreakerError(
                self.agent_name,
                self._failure_count,
                recovery_time
            )
        
        # Execute with failure tracking
        try:
            yield
            self._record_success()
        except Exception as e:
            self._record_failure(e)
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "agent_name": self.agent_name,
            "state": self._state.value,
            "total_requests": self._total_requests,
            "total_failures": self._total_failures,
            "total_successes": self._total_successes,
            "failure_rate": round(self.failure_rate, 4),
            "current_failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
        }
    
    def reset(self):
        """Reset circuit breaker (for testing)."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
        self._opened_at = None
        self._half_open_requests = 0
        
        logger.info(f"Circuit breaker for {self.agent_name} reset")


class CircuitBreakerRegistry:
    """
    Registry for managing multiple circuit breakers.
    
    Provides centralized management of circuit breakers for all agents.
    """
    
    def __init__(self):
        """Initialize circuit breaker registry."""
        self._breakers: Dict[str, CircuitBreaker] = {}
    
    def get_or_create(
        self,
        agent_name: str,
        failure_threshold: int = 3,
        recovery_timeout: int = 60
    ) -> CircuitBreaker:
        """
        Get existing circuit breaker or create new one.
        
        Args:
            agent_name: Agent name
            failure_threshold: Failure threshold
            recovery_timeout: Recovery timeout in seconds
        
        Returns:
            CircuitBreaker instance
        """
        if agent_name not in self._breakers:
            self._breakers[agent_name] = CircuitBreaker(
                agent_name=agent_name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout
            )
        
        return self._breakers[agent_name]
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all circuit breakers."""
        return {
            name: breaker.get_stats()
            for name, breaker in self._breakers.items()
        }
    
    def reset_all(self):
        """Reset all circuit breakers (for testing)."""
        for breaker in self._breakers.values():
            breaker.reset()


# Global registry instance
_global_registry: Optional[CircuitBreakerRegistry] = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Get global circuit breaker registry."""
    global _global_registry
    
    if _global_registry is None:
        _global_registry = CircuitBreakerRegistry()
    
    return _global_registry


def reset_circuit_breakers():
    """Reset all circuit breakers (for testing)."""
    global _global_registry
    if _global_registry:
        _global_registry.reset_all()

