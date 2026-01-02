"""
Tenant management API endpoints.

Provides endpoints for:
- Listing user's tenants
- Creating new tenants
- Managing tenant memberships
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_session
from ...middleware.auth import get_current_user_id
from ...models.tenant import Tenant, TenantMembership

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants", tags=["tenants"])


class TenantResponse(BaseModel):
    """Tenant information response."""
    
    id: str
    name: str
    slug: str
    role: str
    created_at: str


class TenantListResponse(BaseModel):
    """List of user's tenants."""
    
    tenants: List[TenantResponse]
    total: int


@router.get(
    "",
    response_model=TenantListResponse,
    summary="List user's tenants",
    description="Get all tenants the authenticated user belongs to"
)
async def list_user_tenants(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> TenantListResponse:
    """
    List all tenants user has access to.
    
    Returns list of tenants with user's role in each.
    """
    try:
        # Query user's memberships with tenant info
        stmt = (
            select(TenantMembership, Tenant)
            .join(Tenant, TenantMembership.tenant_id == Tenant.id)
            .where(
                TenantMembership.user_id == user_id,
                TenantMembership.accepted_at.isnot(None)
            )
        )
        
        result = await session.execute(stmt)
        memberships = result.all()
        
        tenants = [
            TenantResponse(
                id=str(tenant.id),
                name=tenant.name,
                slug=tenant.slug,
                role=membership.role,
                created_at=tenant.created_at.isoformat(),
            )
            for membership, tenant in memberships
        ]
        
        logger.info(f"User {user_id} has access to {len(tenants)} tenants")
        
        return TenantListResponse(
            tenants=tenants,
            total=len(tenants)
        )
        
    except Exception as e:
        logger.error(f"Error listing tenants: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list tenants"
        )





