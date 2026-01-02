"""
Database connection and session management.

Implements async database access with SQLModel and asyncpg.
Supports connection pooling via pgBouncer for high-concurrency SSE.
"""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from .core.config import settings

logger = logging.getLogger(__name__)

# Create async engine with connection pooling
# Connects via pgBouncer (transaction mode) for SSE endpoints
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENVIRONMENT == "development",
    future=True,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=20,        # Max connections from this instance
    max_overflow=10,     # Allow burst connections
    pool_recycle=3600,   # Recycle connections after 1 hour
)

# Create async session factory
async_session_maker = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI endpoints to get database session.
    
    Usage:
        @app.get("/users")
        async def get_users(session: AsyncSession = Depends(get_session)):
            ...
    
    Yields:
        AsyncSession: Database session with automatic commit/rollback
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database tables.
    
    NOTE: In production, use Alembic migrations instead.
    This is only for development/testing.
    """
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    logger.info("Database tables created successfully")


async def close_db() -> None:
    """Close database connections on shutdown."""
    await engine.dispose()
    logger.info("Database connections closed")

