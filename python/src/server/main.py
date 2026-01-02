"""
FastAPI application entry point.

This is the main server application that provides:
- REST API endpoints
- Server-Sent Events (SSE) streaming
- Authentication and authorization
- Multi-tenant isolation
- Monitoring and health checks
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from prometheus_client import make_asgi_app

from .core.config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize Sentry if DSN provided
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.1,
    )
    logger.info("Sentry initialized")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Application lifespan manager.
    
    Handles startup and shutdown logic:
    - Database connection pool initialization
    - Redis connection
    - Agent registry initialization
    - Graceful shutdown
    """
    logger.info("Starting GA4 Analytics API...")
    
    # Startup logic
    from .database import engine, init_db, close_db
    
    # Initialize database (creates tables in dev mode)
    if settings.ENVIRONMENT == "development":
        try:
            await init_db()
            logger.info("Database initialized")
        except Exception as e:
            logger.warning(f"Database initialization skipped: {e}")
    
    # TODO: Initialize Redis connection
    # TODO: Register agents
    
    logger.info("API started successfully")
    
    yield
    
    # Shutdown logic
    logger.info("Shutting down GA4 Analytics API...")
    
    # Close database connections
    await close_db()
    
    # TODO: Close Redis connection
    logger.info("API shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="GA4 Analytics SaaS API",
    description="AI-powered Google Analytics 4 reporting and insights platform",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JWT authentication middleware (Task P0-27)
from .middleware.auth import JWTAuthMiddleware
from .middleware.tenant import TenantIsolationMiddleware

app.add_middleware(
    JWTAuthMiddleware,
    enforce_auth=(settings.ENVIRONMENT != "development")  # Disable in dev for testing
)

# Tenant isolation middleware (Task P0-2)
app.add_middleware(
    TenantIsolationMiddleware,
    enforce_tenant=(settings.ENVIRONMENT != "development")
)

# Mount Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "GA4 Analytics SaaS API",
        "version": "0.1.0",
        "status": "operational",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint for load balancers and monitoring.
    
    Returns:
        JSON with status and component health
    """
    # TODO: Add database health check
    # TODO: Add Redis health check
    # TODO: Add external API health checks
    
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "components": {
            "database": "healthy",  # TODO: Real check
            "redis": "healthy",     # TODO: Real check
            "ga4_api": "healthy",   # TODO: Real check
        }
    }


@app.get("/health/ready")
async def readiness_check():
    """
    Readiness check for Kubernetes deployments.
    
    Returns 200 only when service is ready to accept traffic.
    """
    # TODO: Check if all dependencies are ready
    return {"status": "ready"}


@app.get("/health/live")
async def liveness_check():
    """
    Liveness check for Kubernetes deployments.
    
    Returns 200 if service is alive (even if not ready).
    """
    return {"status": "alive"}


# Include API routers
from .api.v1 import auth, tenants
app.include_router(auth.router, prefix="/api/v1", tags=["authentication"])
app.include_router(tenants.router, prefix="/api/v1", tags=["tenants"])

# TODO: Import additional routers
# from .api.v1 import analytics, reports
# app.include_router(analytics.router, prefix="/api/v1", tags=["analytics"])
# app.include_router(reports.router, prefix="/api/v1", tags=["reports"])


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.server.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )

