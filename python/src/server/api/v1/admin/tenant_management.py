"""
Admin API for tenant management (GDPR compliance).

Implements Task P0-30: GDPR-Compliant Tenant Data Export & Deletion

Endpoints:
- POST /api/v1/admin/tenants/{tenant_id}/request-deletion
- POST /api/v1/admin/tenants/{tenant_id}/cancel-deletion
- DELETE /api/v1/admin/tenants/{tenant_id}
- GET /api/v1/admin/tenants/{tenant_id}/export
- GET /api/v1/admin/users/{user_id}/export
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.database import get_session
from src.server.services.tenant.deletion_service import (
    TenantDeletionService,
    TenantDeletionError,
    UnauthorizedDeletionError,
    TenantNotFoundError
)
from src.server.services.tenant.export_service import (
    TenantExportService,
    TenantExportError
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin", "gdpr"])


# Request/Response Models

class TenantDeletionRequest(BaseModel):
    """Request model for tenant deletion."""
    
    reason: Optional[str] = Field(
        None,
        description="Reason for tenant deletion",
        max_length=1000
    )


class TenantDeletionResponse(BaseModel):
    """Response model for tenant deletion request."""
    
    tenant_id: str
    deletion_requested_at: str
    deletion_scheduled_at: str
    grace_period_days: int
    can_cancel_until: str
    reason: Optional[str]


class TenantDeletionCancellationResponse(BaseModel):
    """Response model for deletion cancellation."""
    
    tenant_id: str
    deletion_cancelled: bool
    cancelled_at: str


class TenantExportResponse(BaseModel):
    """Response model for tenant data export."""
    
    success: bool
    tenant_id: str
    export_url: Optional[str]
    exported_at: str


class UserExportResponse(BaseModel):
    """Response model for user data export."""
    
    success: bool
    user: dict
    memberships: list
    exported_at: str


# Helper function to get current user (placeholder)
async def get_current_user_id() -> UUID:
    """
    Get current authenticated user ID.
    
    TODO: Implement actual JWT authentication
    For now, returns placeholder UUID
    """
    # This should be replaced with actual JWT authentication
    # from src.server.middleware.auth import get_current_user
    return UUID("00000000-0000-0000-0000-000000000000")


# Endpoints

@router.post(
    "/tenants/{tenant_id}/request-deletion",
    response_model=TenantDeletionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request tenant deletion (GDPR Article 17)",
    description="""
    Request tenant deletion with 30-day grace period.
    
    **GDPR Article 17: Right to Erasure**
    
    - Only tenant owners can request deletion
    - 30-day grace period before permanent deletion
    - Data export automatically generated
    - Audit trail created
    - Can be cancelled during grace period
    
    **Process:**
    1. Deletion request recorded
    2. Deletion scheduled for 30 days from now
    3. Data export generated (available immediately)
    4. Email notification sent to all tenant members
    5. After 30 days, tenant is permanently deleted
    
    **What gets deleted:**
    - Tenant record
    - All tenant memberships
    - All GA4 metrics and embeddings
    - All chat sessions and messages
    - All associated data (CASCADE)
    """
)
async def request_tenant_deletion(
    tenant_id: UUID,
    request: TenantDeletionRequest,
    session: AsyncSession = Depends(get_session),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """Request tenant deletion with 30-day grace period."""
    try:
        service = TenantDeletionService(session)
        result = await service.request_deletion(
            tenant_id=tenant_id,
            requesting_user_id=current_user_id,
            reason=request.reason
        )
        return result
    
    except UnauthorizedDeletionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    
    except TenantNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    
    except TenantDeletionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post(
    "/tenants/{tenant_id}/cancel-deletion",
    response_model=TenantDeletionCancellationResponse,
    summary="Cancel pending tenant deletion",
    description="""
    Cancel tenant deletion during 30-day grace period.
    
    - Only tenant owners can cancel deletion
    - Must be within 30-day grace period
    - Restores tenant to normal operation
    - Audit trail updated
    """
)
async def cancel_tenant_deletion(
    tenant_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """Cancel pending tenant deletion."""
    try:
        service = TenantDeletionService(session)
        result = await service.cancel_deletion(
            tenant_id=tenant_id,
            requesting_user_id=current_user_id
        )
        return result
    
    except UnauthorizedDeletionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    
    except TenantDeletionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete(
    "/tenants/{tenant_id}",
    status_code=status.HTTP_200_OK,
    summary="Permanently delete tenant (ADMIN ONLY)",
    description="""
    **⚠️ WARNING: This is irreversible!**
    
    Immediately and permanently delete tenant and all associated data.
    
    **Use Cases:**
    - Manual deletion by system administrator
    - Processing scheduled deletions after grace period
    - Emergency deletion for legal/compliance reasons
    
    **What happens:**
    1. Data export generated (if not already exists)
    2. Tenant and ALL related data deleted (CASCADE)
    3. Audit log entry created
    4. Cannot be undone
    
    **Recommended:** Use `/request-deletion` endpoint instead for safer deletion with grace period.
    """
)
async def delete_tenant_immediately(
    tenant_id: UUID,
    generate_export: bool = True,
    session: AsyncSession = Depends(get_session),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """Permanently delete tenant (ADMIN ONLY)."""
    try:
        service = TenantDeletionService(session)
        result = await service.execute_deletion(
            tenant_id=tenant_id,
            generate_export=generate_export
        )
        return result
    
    except TenantNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    
    except TenantDeletionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/tenants/{tenant_id}/export",
    response_model=TenantExportResponse,
    summary="Export tenant data (GDPR Article 20)",
    description="""
    Export all tenant data in machine-readable JSON format.
    
    **GDPR Article 20: Right to Data Portability**
    
    **Includes:**
    - Tenant information
    - All memberships
    - GA4 metrics summary
    - Embeddings metadata
    - Chat sessions and messages
    
    **Options:**
    - `include_raw_data`: Include full raw GA4 metrics (can be large)
    - `save_to_file`: Save export to S3 and return download URL
    
    **Use Cases:**
    - User requests data export
    - Tenant migration to another system
    - Compliance audit
    - Backup before deletion
    """
)
async def export_tenant_data(
    tenant_id: UUID,
    include_raw_data: bool = False,
    save_to_file: bool = False,
    session: AsyncSession = Depends(get_session),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """Export all tenant data."""
    try:
        service = TenantExportService(session)
        result = await service.export_tenant_data(
            tenant_id=tenant_id,
            include_raw_data=include_raw_data,
            save_to_file=save_to_file
        )
        return result
    
    except TenantExportError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/users/{user_id}/export",
    response_model=UserExportResponse,
    summary="Export user data (GDPR Article 15)",
    description="""
    Export data for a specific user.
    
    **GDPR Article 15: Right of Access**
    
    **Includes:**
    - User profile information
    - Tenant memberships
    - Roles and permissions
    
    **Options:**
    - `tenant_id`: Scope export to specific tenant
    """
)
async def export_user_data(
    user_id: UUID,
    tenant_id: Optional[UUID] = None,
    session: AsyncSession = Depends(get_session),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """Export user data."""
    try:
        service = TenantExportService(session)
        result = await service.export_user_data(
            user_id=user_id,
            tenant_id=tenant_id
        )
        return result
    
    except TenantExportError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/tenants/pending-deletions",
    summary="List pending tenant deletions (ADMIN ONLY)",
    description="""
    Get all tenants scheduled for deletion.
    
    Used by scheduled job to process deletions after grace period.
    
    **Returns:**
    - List of tenants with deletion scheduled
    - Deletion dates
    - Reasons for deletion
    """
)
async def list_pending_deletions(
    session: AsyncSession = Depends(get_session),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """List all pending tenant deletions."""
    try:
        service = TenantDeletionService(session)
        pending = await service.get_pending_deletions()
        return {
            "success": True,
            "pending_deletions": pending,
            "count": len(pending)
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list pending deletions: {str(e)}"
        )

