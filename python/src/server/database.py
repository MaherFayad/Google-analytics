"""
Database connection and session management.

Implements Task P0-6: Database Connection Pooling for SSE
Implements Task P0-32: Hybrid pgBouncer Pool Strategy

Provides dual-engine architecture:
1. Transactional Engine: For SSE endpoints (1000 concurrent connections)
2. Session Engine: For embedding workers (long-running transactions)

Architecture:
    FastAPI SSE (1000) → Transactional Engine (pool_size=20) → pgBouncer:6432 (25) → PostgreSQL
    Embedding Workers (10) → Session Engine (pool_size=5) → pgBouncer:6433 (10) → PostgreSQL
"""

import logging
from typing import AsyncGenerator, Literal

from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

from .core.config import settings

logger = logging.getLogger(__name__)

# ============================================================================
# ENGINE 1: Transactional Mode (for SSE endpoints)
# ============================================================================
# Connects to pgBouncer port 6432 (transaction mode)
# Optimized for high concurrency with short-lived transactions
#
# Performance characteristics:
# - Supports 1000 concurrent SSE connections
# - Each SSE event is a separate transaction
# - Connections released immediately after query
# - 40x connection multiplexing (1000 client → 25 DB connections)
# ============================================================================

_transactional_database_url = settings.DATABASE_URL  # Default to transactional pgBouncer

engine_transactional = create_async_engine(
    _transactional_database_url,
    echo=settings.ENVIRONMENT == "development",
    future=True,
    pool_pre_ping=True,      # Verify connections before using
    pool_size=20,            # Connections per FastAPI instance
    max_overflow=10,         # Burst capacity for spikes
    pool_recycle=3600,       # Recycle after 1 hour
    pool_timeout=30,         # Wait 30s for connection from pool
    pool_use_lifo=True,      # Use LIFO for better connection reuse
)

# Async session factory for transactional queries
async_session_maker_transactional = sessionmaker(
    engine_transactional,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ============================================================================
# ENGINE 2: Session Mode (for embedding workers)
# ============================================================================
# Connects to pgBouncer port 6433 (session mode)
# Optimized for long-running transactions (10-30 seconds)
#
# Performance characteristics:
# - Supports 10-20 concurrent embedding workers
# - Connection held for entire session
# - PostgreSQL session variables persist
# - Supports temporary tables and cursors
# ============================================================================

_session_database_url = settings.DATABASE_URL.replace(":6432", ":6433")  # Switch to session pgBouncer

engine_session = create_async_engine(
    _session_database_url,
    echo=settings.ENVIRONMENT == "development",
    future=True,
    pool_pre_ping=True,      # Verify connections before using
    pool_size=5,             # Fewer connections for workers
    max_overflow=2,          # Limited overflow for embedding jobs
    pool_recycle=7200,       # Recycle after 2 hours (longer for session mode)
    pool_timeout=60,         # Wait longer for embedding jobs
    pool_use_lifo=False,     # Use FIFO for session mode
)

# Async session factory for long transactions
async_session_maker_session = sessionmaker(
    engine_session,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ============================================================================
# Legacy default engine (for backwards compatibility)
# ============================================================================
engine = engine_transactional
async_session_maker = async_session_maker_transactional


async def get_session(
    mode: Literal["transactional", "session"] = "transactional"
) -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI endpoints to get database session.
    
    Implements Task P0-6: Dual-engine support for different workloads
    
    Args:
        mode: Connection pool mode
            - "transactional": For SSE/API endpoints (default, via pgBouncer:6432)
            - "session": For embedding workers (via pgBouncer:6433)
    
    Usage:
        # For SSE endpoints (transactional mode)
        @app.post("/analytics/stream")
        async def stream(session: AsyncSession = Depends(get_session)):
            ...
        
        # For embedding workers (session mode)
        @app.post("/embeddings/generate")
        async def generate(
            session: AsyncSession = Depends(lambda: get_session(mode="session"))
        ):
            ...
    
    Yields:
        AsyncSession: Database session with automatic commit/rollback
    """
    # Select appropriate session maker
    session_maker = (
        async_session_maker_session
        if mode == "session"
        else async_session_maker_transactional
    )
    
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_session_transactional() -> AsyncGenerator[AsyncSession, None]:
    """
    Convenience dependency for transactional sessions (SSE/API endpoints).
    
    This is the default mode for most endpoints.
    """
    async for session in get_session(mode="transactional"):
        yield session


async def get_session_long() -> AsyncGenerator[AsyncSession, None]:
    """
    Convenience dependency for session-mode (long transactions).
    
    Use this for:
    - Embedding generation (10-30 second transactions)
    - Batch processing jobs
    - Operations requiring PostgreSQL session variables
    - Operations with temporary tables
    """
    async for session in get_session(mode="session"):
        yield session


async def init_db() -> None:
    """
    Initialize database tables.
    
    NOTE: In production, use Alembic migrations instead.
    This is only for development/testing.
    """
    async with engine_transactional.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    logger.info("Database tables created successfully")


async def close_db() -> None:
    """
    Close database connections on shutdown.
    
    Closes both transactional and session engines gracefully.
    """
    logger.info("Closing database connections...")
    
    # Close both engines
    await engine_transactional.dispose()
    await engine_session.dispose()
    
    logger.info("Database connections closed successfully")


async def get_pool_stats() -> dict:
    """
    Get connection pool statistics for monitoring.
    
    Returns:
        Dictionary with pool stats for both engines
        
    Usage:
        @app.get("/health/db")
        async def db_health():
            stats = await get_pool_stats()
            return stats
    """
    trans_pool = engine_transactional.pool
    session_pool = engine_session.pool
    
    return {
        "transactional": {
            "size": trans_pool.size(),
            "checked_in": trans_pool.checkedin(),
            "checked_out": trans_pool.checkedout(),
            "overflow": trans_pool.overflow(),
            "max_overflow": engine_transactional.pool._max_overflow,
            "pool_size": engine_transactional.pool._pool_size,
            "utilization": round(
                (trans_pool.checkedout() / trans_pool.size() * 100), 2
            ) if trans_pool.size() > 0 else 0,
        },
        "session": {
            "size": session_pool.size(),
            "checked_in": session_pool.checkedin(),
            "checked_out": session_pool.checkedout(),
            "overflow": session_pool.overflow(),
            "max_overflow": engine_session.pool._max_overflow,
            "pool_size": engine_session.pool._pool_size,
            "utilization": round(
                (session_pool.checkedout() / session_pool.size() * 100), 2
            ) if session_pool.size() > 0 else 0,
        },
    }

