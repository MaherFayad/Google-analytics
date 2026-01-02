"""
Sentry Error Tracking Configuration

Implements Task P0-7: Monitoring & Alerting Infrastructure

Features:
- Automatic error capture with full stack traces
- Performance monitoring with distributed tracing
- User context tracking (tenant_id, user_id)
- Custom tags and breadcrumbs
- Release tracking
- Environment separation (dev/staging/prod)

Usage:
    from src.server.monitoring.sentry_config import init_sentry
    
    # At application startup
    init_sentry()
"""

import logging
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.asyncio import AsyncioIntegration

from ..core.config import settings

logger = logging.getLogger(__name__)


def init_sentry():
    """
    Initialize Sentry error tracking.
    
    Should be called at application startup, before any request handling.
    
    Configuration via environment variables:
    - SENTRY_DSN: Sentry project DSN
    - ENVIRONMENT: Environment name (development, staging, production)
    - SENTRY_TRACES_SAMPLE_RATE: Performance monitoring sample rate (0.0-1.0)
    - SENTRY_PROFILES_SAMPLE_RATE: Profiling sample rate (0.0-1.0)
    
    Usage:
        @app.on_event("startup")
        async def startup():
            init_sentry()
    """
    # Skip initialization if no DSN provided (local development)
    if not hasattr(settings, 'SENTRY_DSN') or not settings.SENTRY_DSN:
        logger.info("Sentry DSN not configured, skipping initialization")
        return
    
    # Determine sample rates based on environment
    environment = getattr(settings, 'ENVIRONMENT', 'development')
    
    if environment == 'production':
        traces_sample_rate = 0.1  # 10% of transactions
        profiles_sample_rate = 0.1  # 10% of transactions
    elif environment == 'staging':
        traces_sample_rate = 0.5  # 50% of transactions
        profiles_sample_rate = 0.5  # 50% of transactions
    else:  # development
        traces_sample_rate = 1.0  # 100% of transactions
        profiles_sample_rate = 1.0  # 100% of transactions
    
    # Override with environment variable if provided
    if hasattr(settings, 'SENTRY_TRACES_SAMPLE_RATE'):
        traces_sample_rate = float(settings.SENTRY_TRACES_SAMPLE_RATE)
    if hasattr(settings, 'SENTRY_PROFILES_SAMPLE_RATE'):
        profiles_sample_rate = float(settings.SENTRY_PROFILES_SAMPLE_RATE)
    
    # Configure logging integration
    logging_integration = LoggingIntegration(
        level=logging.INFO,  # Capture info and above as breadcrumbs
        event_level=logging.ERROR  # Capture error and above as events
    )
    
    # Initialize Sentry
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=environment,
        traces_sample_rate=traces_sample_rate,
        profiles_sample_rate=profiles_sample_rate,
        
        # Release tracking
        release=getattr(settings, 'APP_VERSION', None),
        
        # Integrations
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            StarletteIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
            RedisIntegration(),
            AsyncioIntegration(),
            logging_integration,
        ],
        
        # Performance monitoring
        enable_tracing=True,
        
        # Error filtering
        before_send=before_send_filter,
        before_send_transaction=before_send_transaction_filter,
        
        # Additional options
        attach_stacktrace=True,
        send_default_pii=False,  # Don't send PII by default
        max_breadcrumbs=50,
        debug=environment == 'development',
    )
    
    logger.info(
        f"Sentry initialized: environment={environment}, "
        f"traces_sample_rate={traces_sample_rate}, "
        f"profiles_sample_rate={profiles_sample_rate}"
    )


def before_send_filter(event, hint):
    """
    Filter events before sending to Sentry.
    
    Use this to:
    - Drop sensitive data
    - Filter out noise (health checks, expected errors)
    - Add custom context
    
    Args:
        event: Sentry event dictionary
        hint: Additional context about the event
        
    Returns:
        Modified event or None to drop the event
    """
    # Drop health check errors
    if event.get('request'):
        url = event['request'].get('url', '')
        if '/health' in url or '/metrics' in url:
            return None
    
    # Drop expected errors
    if 'exception' in event:
        for exception in event['exception'].get('values', []):
            exc_type = exception.get('type', '')
            
            # Drop HTTP 404 errors (expected)
            if exc_type == 'HTTPException' and '404' in exception.get('value', ''):
                return None
            
            # Drop validation errors (expected)
            if exc_type in ('ValidationError', 'RequestValidationError'):
                return None
    
    # Add custom tags
    event.setdefault('tags', {})
    event['tags']['source'] = 'ga4-analytics-api'
    
    return event


def before_send_transaction_filter(event, hint):
    """
    Filter transactions before sending to Sentry.
    
    Args:
        event: Sentry transaction event
        hint: Additional context
        
    Returns:
        Modified event or None to drop
    """
    # Drop health check transactions
    transaction_name = event.get('transaction', '')
    if '/health' in transaction_name or '/metrics' in transaction_name:
        return None
    
    return event


def set_tenant_context(tenant_id: str, user_id: str | None = None):
    """
    Set tenant context for Sentry events.
    
    Call this in middleware after tenant is identified.
    
    Args:
        tenant_id: Tenant ID
        user_id: Optional user ID
        
    Usage:
        # In tenant isolation middleware
        set_tenant_context(tenant_id, user_id)
    """
    with sentry_sdk.configure_scope() as scope:
        scope.set_tag("tenant_id", tenant_id)
        scope.set_context("tenant", {
            "id": tenant_id,
        })
        
        if user_id:
            scope.set_user({
                "id": user_id,
                "tenant_id": tenant_id,
            })


def add_breadcrumb(category: str, message: str, level: str = "info", **data):
    """
    Add breadcrumb for debugging context.
    
    Breadcrumbs provide a trail of events leading up to an error.
    
    Args:
        category: Breadcrumb category (e.g., "ga4", "vector_search", "cache")
        message: Breadcrumb message
        level: Severity level ("debug", "info", "warning", "error")
        **data: Additional structured data
        
    Usage:
        add_breadcrumb(
            "ga4",
            "Fetching analytics data",
            property_id="123",
            date_range="last_7_days"
        )
    """
    sentry_sdk.add_breadcrumb(
        category=category,
        message=message,
        level=level,
        data=data,
    )


def capture_exception(error: Exception, **context):
    """
    Manually capture an exception to Sentry.
    
    Args:
        error: Exception to capture
        **context: Additional context to attach
        
    Usage:
        try:
            result = await risky_operation()
        except SomeError as e:
            capture_exception(
                e,
                operation="fetch_analytics",
                tenant_id=tenant_id
            )
            raise
    """
    with sentry_sdk.configure_scope() as scope:
        for key, value in context.items():
            scope.set_extra(key, value)
        
        sentry_sdk.capture_exception(error)


def capture_message(message: str, level: str = "info", **context):
    """
    Manually capture a message to Sentry.
    
    Args:
        message: Message to capture
        level: Severity level ("debug", "info", "warning", "error", "fatal")
        **context: Additional context
        
    Usage:
        capture_message(
            "GA4 quota threshold exceeded",
            level="warning",
            tenant_id=tenant_id,
            quota_usage=0.95
        )
    """
    with sentry_sdk.configure_scope() as scope:
        for key, value in context.items():
            scope.set_extra(key, value)
        
        sentry_sdk.capture_message(message, level=level)


def start_transaction(name: str, op: str = "function"):
    """
    Start a performance transaction for tracing.
    
    Args:
        name: Transaction name
        op: Operation type ("http", "db", "function", "task")
        
    Returns:
        Transaction context manager
        
    Usage:
        with start_transaction("generate_embeddings", op="task"):
            embeddings = await generate_embeddings(texts)
    """
    return sentry_sdk.start_transaction(name=name, op=op)


def start_span(operation: str, description: str | None = None):
    """
    Start a span within a transaction for detailed tracing.
    
    Args:
        operation: Span operation (e.g., "db.query", "http.request", "cache.get")
        description: Optional span description
        
    Returns:
        Span context manager
        
    Usage:
        with start_transaction("process_analytics"):
            with start_span("db.query", "fetch_ga4_metrics"):
                metrics = await fetch_metrics()
            
            with start_span("vector.search", "similarity_search"):
                similar = await vector_search(query)
    """
    return sentry_sdk.start_span(op=operation, description=description)


# ============================================================================
# Error Classification
# ============================================================================

class SentryErrorLevel:
    """Sentry error severity levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


class ErrorCategory:
    """Common error categories for tagging."""
    GA4_API = "ga4_api"
    VECTOR_SEARCH = "vector_search"
    DATABASE = "database"
    CACHE = "cache"
    AUTH = "authentication"
    VALIDATION = "validation"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    NETWORK = "network"
    UNKNOWN = "unknown"


def classify_error(error: Exception) -> str:
    """
    Classify an error into a category.
    
    Args:
        error: Exception to classify
        
    Returns:
        Error category string
    """
    error_type = type(error).__name__
    error_msg = str(error).lower()
    
    if "ga4" in error_msg or "google analytics" in error_msg:
        return ErrorCategory.GA4_API
    elif "vector" in error_msg or "embedding" in error_msg:
        return ErrorCategory.VECTOR_SEARCH
    elif "database" in error_msg or "sql" in error_msg or "postgres" in error_msg:
        return ErrorCategory.DATABASE
    elif "redis" in error_msg or "cache" in error_msg:
        return ErrorCategory.CACHE
    elif "auth" in error_msg or "token" in error_msg or "permission" in error_msg:
        return ErrorCategory.AUTH
    elif "validation" in error_msg or error_type in ("ValidationError", "ValueError"):
        return ErrorCategory.VALIDATION
    elif "rate limit" in error_msg or "quota" in error_msg:
        return ErrorCategory.RATE_LIMIT
    elif "timeout" in error_msg or error_type == "TimeoutError":
        return ErrorCategory.TIMEOUT
    elif "network" in error_msg or "connection" in error_msg:
        return ErrorCategory.NETWORK
    else:
        return ErrorCategory.UNKNOWN

