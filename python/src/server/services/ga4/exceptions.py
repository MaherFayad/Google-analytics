"""
Custom exception hierarchy for GA4 service.

Implements Task P0-4: GA4 API Resilience Layer

This module defines exceptions for different GA4 failure scenarios,
enabling proper error handling and retry logic.
"""


class GA4BaseException(Exception):
    """Base exception for all GA4-related errors."""
    pass


class GA4APIError(GA4BaseException):
    """Raised when GA4 API call fails."""
    
    def __init__(self, message: str, status_code: int = None, response_body: str = None):
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(message)


class GA4RateLimitError(GA4APIError):
    """
    Raised when GA4 API rate limit is exceeded (429).
    
    Should be handled by request queue (Task P0-14).
    """
    
    def __init__(self, message: str = "GA4 API rate limit exceeded", retry_after: int = None):
        self.retry_after = retry_after  # Seconds until rate limit resets
        super().__init__(message, status_code=429)


class GA4QuotaExceededError(GA4APIError):
    """
    Raised when GA4 API quota is exhausted for the day.
    
    Cannot retry until next day.
    """
    
    def __init__(self, message: str = "GA4 API daily quota exceeded"):
        super().__init__(message, status_code=429)


class GA4AuthenticationError(GA4APIError):
    """
    Raised when OAuth credentials are invalid or expired.
    
    User must re-authenticate.
    """
    
    def __init__(self, message: str = "GA4 authentication failed"):
        super().__init__(message, status_code=401)


class GA4NetworkError(GA4BaseException):
    """
    Raised when network connectivity issues occur.
    
    Retryable error.
    """
    pass


class GA4TimeoutError(GA4BaseException):
    """
    Raised when GA4 API call times out.
    
    Retryable error.
    """
    pass


class GA4CircuitBreakerError(GA4BaseException):
    """
    Raised when circuit breaker is open.
    
    Should fall back to cache or return cached data.
    """
    
    def __init__(self, message: str = "GA4 circuit breaker is open", failure_count: int = 0):
        self.failure_count = failure_count
        super().__init__(message)


class GA4CacheStaleError(GA4BaseException):
    """
    Warning: Returned data is from cache and may be stale.
    
    Not a failure, but indicates degraded service.
    """
    
    def __init__(self, message: str = "Returning stale cached data", age_seconds: int = 0):
        self.age_seconds = age_seconds
        super().__init__(message)

