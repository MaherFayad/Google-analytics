"""
Row Level Security (RLS) enforcement.

Implements Task P0-2: Sets PostgreSQL app.tenant_id session variable

This module provides utilities to set PostgreSQL session variables
that RLS policies use for filtering queries.

CRITICAL: These session variables MUST be set for every database
transaction to ensure tenant isolation.
"""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def set_rls_context(
    session: AsyncSession,
    user_id: str,
    tenant_id: str
) -> None:
    """
    Set PostgreSQL session variables for RLS policies.
    
    These variables are used by RLS policies to automatically filter
    queries to only include data for the current tenant and user.
    
    Args:
        session: Database session
        user_id: Current user UUID
        tenant_id: Current tenant UUID
        
    Example:
        await set_rls_context(session, "user-uuid", "tenant-uuid")
        
        # All subsequent queries in this session are automatically filtered
        results = await session.execute(select(ChatSession))
        # Returns only chat sessions for this tenant
    """
    try:
        # Set tenant context
        await session.execute(
            text("SET LOCAL app.tenant_id = :tenant_id"),
            {"tenant_id": str(tenant_id)}
        )
        
        # Set user context
        await session.execute(
            text("SET LOCAL app.user_id = :user_id"),
            {"user_id": str(user_id)}
        )
        
        logger.debug(f"RLS context set: user={user_id}, tenant={tenant_id}")
        
    except Exception as e:
        logger.error(f"Failed to set RLS context: {e}", exc_info=True)
        raise


async def clear_rls_context(session: AsyncSession) -> None:
    """
    Clear RLS session variables.
    
    Useful for admin operations or testing.
    
    Args:
        session: Database session
    """
    try:
        await session.execute(text("RESET app.tenant_id"))
        await session.execute(text("RESET app.user_id"))
        logger.debug("RLS context cleared")
    except Exception as e:
        logger.warning(f"Failed to clear RLS context: {e}")


async def get_current_rls_context(
    session: AsyncSession
) -> dict:
    """
    Get current RLS context from session variables.
    
    Useful for debugging and logging.
    
    Args:
        session: Database session
        
    Returns:
        Dict with tenant_id and user_id (if set)
    """
    try:
        result = await session.execute(
            text("SELECT current_setting('app.tenant_id', true) as tenant_id, current_setting('app.user_id', true) as user_id")
        )
        row = result.fetchone()
        
        return {
            "tenant_id": row[0] if row and row[0] else None,
            "user_id": row[1] if row and row[1] else None,
        }
    except Exception as e:
        logger.warning(f"Failed to get RLS context: {e}")
        return {"tenant_id": None, "user_id": None}


class RLSSession:
    """
    Context manager for RLS-aware database sessions.
    
    Automatically sets and clears RLS context.
    
    Usage:
        async with RLSSession(user_id, tenant_id) as session:
            # All queries in this session are tenant-filtered
            results = await session.execute(select(ChatSession))
    """
    
    def __init__(
        self,
        user_id: str,
        tenant_id: str,
        session_maker=None
    ):
        """
        Initialize RLS session.
        
        Args:
            user_id: User UUID
            tenant_id: Tenant UUID
            session_maker: SQLAlchemy session maker
        """
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.session_maker = session_maker
        self.session: Optional[AsyncSession] = None
    
    async def __aenter__(self) -> AsyncSession:
        """Enter context and set RLS variables."""
        from ..database import async_session_maker
        
        maker = self.session_maker or async_session_maker
        self.session = maker()
        
        # Set RLS context
        await set_rls_context(self.session, self.user_id, self.tenant_id)
        
        return self.session
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit context and close session."""
        if self.session:
            if exc_type:
                await self.session.rollback()
            else:
                await self.session.commit()
            
            await self.session.close()

