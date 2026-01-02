"""
Circuit Breaker implementation for GA4 API.

Implements Task P0-4: GA4 API Resilience Layer

Circuit breaker prevents cascading failures by:
1. Opening after N consecutive failures (prevents overwhelming failing service)
2. Half-opening after timeout (allow test requests through)
3. Closing when service recovers (normal operation resumes)

States:
- CLOSED: Normal operation, all requests allowed
- OPEN: Service failing, all requests blocked
- HALF_OPEN: Testing recovery, limited requests allowed
"""

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Callable, Any
import asyncio

from .exceptions import GA4CircuitBreakerError

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """
    Circuit breaker for GA4 API calls.
    
    Task P0-4 Implementation:
    - Opens after 5 consecutive failures
    - Stays open for 60 seconds
    - Half-opens to test recovery
    - Closes when service recovers
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        success_threshold: int = 2,
        name: str = "GA4CircuitBreaker"
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            success_threshold: Successful calls needed to close circuit from half-open
            name: Circuit breaker name for logging
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.name = name
        
        # State
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.opened_at: Optional[datetime] = None
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
        
        logger.info(
            f"Circuit breaker '{name}' initialized: "
            f"failure_threshold={failure_threshold}, "
            f"recovery_timeout={recovery_timeout}s"
        )
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Async function to call
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Function result
            
        Raises:
            GA4CircuitBreakerError: If circuit is open
            Exception: Any exception from the function
            
        Example:
            breaker = CircuitBreaker()
            result = await breaker.call(fetch_ga4_data, property_id="123")
        """
        async with self._lock:
            # Check if we should attempt the call
            if self.state == CircuitState.OPEN:
                # Check if recovery timeout has elapsed
                if self._should_attempt_reset():
                    logger.info(f"Circuit breaker '{self.name}' entering HALF_OPEN state")
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                else:
                    time_until_reset = self._time_until_reset()
                    raise GA4CircuitBreakerError(
                        f"Circuit breaker '{self.name}' is OPEN. "
                        f"Retry in {time_until_reset}s",
                        failure_count=self.failure_count
                    )
        
        # Attempt the call (outside lock to allow concurrent requests)
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        
        except Exception as e:
            await self._on_failure()
            raise
    
    async def _on_success(self) -> None:
        """Handle successful call."""
        async with self._lock:
            self.failure_count = 0
            
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                
                if self.success_count >= self.success_threshold:
                    logger.info(
                        f"Circuit breaker '{self.name}' CLOSING "
                        f"(recovered after {self.success_count} successful calls)"
                    )
                    self.state = CircuitState.CLOSED
                    self.success_count = 0
                    self.opened_at = None
                    self.last_failure_time = None
    
    async def _on_failure(self) -> None:
        """Handle failed call."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.utcnow()
            
            if self.state == CircuitState.HALF_OPEN:
                # Failed during recovery attempt, reopen circuit
                logger.warning(
                    f"Circuit breaker '{self.name}' REOPENING "
                    f"(recovery attempt failed)"
                )
                self.state = CircuitState.OPEN
                self.opened_at = datetime.utcnow()
                self.success_count = 0
            
            elif self.state == CircuitState.CLOSED:
                if self.failure_count >= self.failure_threshold:
                    logger.error(
                        f"Circuit breaker '{self.name}' OPENING "
                        f"(failure threshold reached: {self.failure_count})"
                    )
                    self.state = CircuitState.OPEN
                    self.opened_at = datetime.utcnow()
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if self.opened_at is None:
            return False
        
        elapsed = (datetime.utcnow() - self.opened_at).total_seconds()
        return elapsed >= self.recovery_timeout
    
    def _time_until_reset(self) -> int:
        """Get seconds until recovery attempt."""
        if self.opened_at is None:
            return 0
        
        elapsed = (datetime.utcnow() - self.opened_at).total_seconds()
        remaining = max(0, self.recovery_timeout - elapsed)
        return int(remaining)
    
    def get_state(self) -> dict:
        """
        Get circuit breaker state for monitoring.
        
        Returns:
            State dict with metrics
        """
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": (
                self.last_failure_time.isoformat()
                if self.last_failure_time else None
            ),
            "opened_at": (
                self.opened_at.isoformat()
                if self.opened_at else None
            ),
            "time_until_reset": self._time_until_reset() if self.state == CircuitState.OPEN else 0
        }
    
    async def reset(self) -> None:
        """Manually reset circuit breaker (admin operation)."""
        async with self._lock:
            logger.warning(f"Circuit breaker '{self.name}' manually RESET")
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = None
            self.opened_at = None

