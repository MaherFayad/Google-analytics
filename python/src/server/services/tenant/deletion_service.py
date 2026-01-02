"""
Tenant deletion service with GDPR compliance.

Implements Task P0-30: GDPR-Compliant Tenant Data Export & Deletion

Features:
- 30-day grace period for deletion cancellation
- Automatic data export before deletion
- Cascade deletion with audit trail
- Owner-only deletion authorization
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.models.tenant import Tenant, TenantMembership

logger = logging.getLogger(__name__)


class TenantDeletionError(Exception):
    """Base exception for tenant deletion errors."""
    pass


class UnauthorizedDeletionError(TenantDeletionError):
    """User is not authorized to delete tenant."""
    pass


class TenantNotFoundError(TenantDeletionError):
    """Tenant does not exist."""
    pass


class TenantDeletionService:
    """
    Service for GDPR-compliant tenant deletion.
    
    Implements Article 17: Right to Erasure
    """
    
    # GDPR grace period (30 days)
    GRACE_PERIOD_DAYS = 30
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def request_deletion(
        self,
        tenant_id: UUID,
        requesting_user_id: UUID,
        reason: Optional[str] = None
    ) -> Dict:
        """
        Request tenant deletion with 30-day grace period.
        
        GDPR Article 17: Right to Erasure
        - Only tenant owners can request deletion
        - 30-day grace period before permanent deletion
        - Data export automatically generated
        - Audit trail created
        
        Args:
            tenant_id: Tenant UUID
            requesting_user_id: User requesting deletion (must be owner)
            reason: Optional reason for deletion
        
        Returns:
            Dict with deletion request details
        
        Raises:
            UnauthorizedDeletionError: If user is not owner
            TenantNotFoundError: If tenant doesn't exist
        """
        # 1. Verify tenant exists
        tenant = await self._get_tenant(tenant_id)
        if not tenant:
            raise TenantNotFoundError(f"Tenant {tenant_id} not found")
        
        # 2. Verify user is owner
        is_owner = await self._verify_owner(tenant_id, requesting_user_id)
        if not is_owner:
            raise UnauthorizedDeletionError(
                f"User {requesting_user_id} is not owner of tenant {tenant_id}"
            )
        
        # 3. Calculate deletion schedule
        deletion_requested_at = datetime.utcnow()
        deletion_scheduled_at = deletion_requested_at + timedelta(days=self.GRACE_PERIOD_DAYS)
        
        # 4. Update tenant with deletion request
        await self.session.execute(
            text("""
                UPDATE tenants
                SET 
                    deletion_requested_at = :requested_at,
                    deletion_requested_by = :requested_by,
                    deletion_scheduled_at = :scheduled_at,
                    deletion_reason = :reason,
                    updated_at = NOW()
                WHERE id = :tenant_id
            """),
            {
                "tenant_id": tenant_id,
                "requested_at": deletion_requested_at,
                "requested_by": requesting_user_id,
                "scheduled_at": deletion_scheduled_at,
                "reason": reason or "User requested tenant deletion"
            }
        )
        await self.session.commit()
        
        logger.info(
            f"Tenant deletion requested: {tenant_id} by user {requesting_user_id}. "
            f"Scheduled for {deletion_scheduled_at}"
        )
        
        return {
            "tenant_id": str(tenant_id),
            "deletion_requested_at": deletion_requested_at.isoformat(),
            "deletion_scheduled_at": deletion_scheduled_at.isoformat(),
            "grace_period_days": self.GRACE_PERIOD_DAYS,
            "can_cancel_until": deletion_scheduled_at.isoformat(),
            "reason": reason
        }
    
    async def cancel_deletion(
        self,
        tenant_id: UUID,
        requesting_user_id: UUID
    ) -> Dict:
        """
        Cancel pending tenant deletion during grace period.
        
        Args:
            tenant_id: Tenant UUID
            requesting_user_id: User cancelling deletion (must be owner)
        
        Returns:
            Dict with cancellation confirmation
        
        Raises:
            UnauthorizedDeletionError: If user is not owner
            TenantDeletionError: If no pending deletion or grace period expired
        """
        # 1. Verify user is owner
        is_owner = await self._verify_owner(tenant_id, requesting_user_id)
        if not is_owner:
            raise UnauthorizedDeletionError(
                f"User {requesting_user_id} is not owner of tenant {tenant_id}"
            )
        
        # 2. Check if deletion is pending
        result = await self.session.execute(
            text("""
                SELECT deletion_requested_at, deletion_scheduled_at
                FROM tenants
                WHERE id = :tenant_id
            """),
            {"tenant_id": tenant_id}
        )
        row = result.fetchone()
        
        if not row or not row[0]:  # deletion_requested_at is NULL
            raise TenantDeletionError("No pending deletion request for this tenant")
        
        deletion_scheduled_at = row[1]
        if deletion_scheduled_at and datetime.utcnow() > deletion_scheduled_at:
            raise TenantDeletionError("Grace period has expired, cannot cancel deletion")
        
        # 3. Cancel deletion
        await self.session.execute(
            text("""
                UPDATE tenants
                SET 
                    deletion_requested_at = NULL,
                    deletion_requested_by = NULL,
                    deletion_scheduled_at = NULL,
                    deletion_reason = NULL,
                    updated_at = NOW()
                WHERE id = :tenant_id
            """),
            {"tenant_id": tenant_id}
        )
        await self.session.commit()
        
        logger.info(f"Tenant deletion cancelled: {tenant_id} by user {requesting_user_id}")
        
        return {
            "tenant_id": str(tenant_id),
            "deletion_cancelled": True,
            "cancelled_at": datetime.utcnow().isoformat()
        }
    
    async def execute_deletion(
        self,
        tenant_id: UUID,
        generate_export: bool = True
    ) -> Dict:
        """
        Execute permanent tenant deletion.
        
        WARNING: This is irreversible!
        
        Steps:
        1. Generate data export (if requested)
        2. Get deletion statistics
        3. Delete tenant (CASCADE to all related data)
        4. Audit log automatically created via trigger
        
        Args:
            tenant_id: Tenant UUID
            generate_export: Whether to generate data export before deletion
        
        Returns:
            Dict with deletion summary
        
        Raises:
            TenantNotFoundError: If tenant doesn't exist
        """
        # 1. Verify tenant exists
        tenant = await self._get_tenant(tenant_id)
        if not tenant:
            raise TenantNotFoundError(f"Tenant {tenant_id} not found")
        
        # 2. Get deletion statistics (before deletion)
        stats = await self._get_deletion_stats(tenant_id)
        
        # 3. Generate export if requested
        export_url = None
        if generate_export:
            from .export_service import TenantExportService
            export_service = TenantExportService(self.session)
            export_result = await export_service.export_tenant_data(tenant_id)
            export_url = export_result.get("export_url")
        
        # 4. Delete tenant (CASCADE will delete all related data)
        # Trigger will automatically create audit log entry
        await self.session.execute(
            text("DELETE FROM tenants WHERE id = :tenant_id"),
            {"tenant_id": tenant_id}
        )
        await self.session.commit()
        
        logger.warning(
            f"Tenant permanently deleted: {tenant_id}. "
            f"Deleted {stats.get('total_records', 0)} records."
        )
        
        return {
            "tenant_id": str(tenant_id),
            "deleted": True,
            "deleted_at": datetime.utcnow().isoformat(),
            "statistics": stats,
            "export_generated": generate_export,
            "export_url": export_url,
            "audit_logged": True
        }
    
    async def get_pending_deletions(self) -> list[Dict]:
        """
        Get all tenants with pending deletions.
        
        Used by scheduled job to process deletions.
        
        Returns:
            List of tenants scheduled for deletion
        """
        result = await self.session.execute(
            text("""
                SELECT 
                    id,
                    name,
                    deletion_requested_at,
                    deletion_scheduled_at,
                    deletion_reason
                FROM tenants
                WHERE 
                    deletion_scheduled_at IS NOT NULL
                    AND deletion_scheduled_at <= NOW()
                ORDER BY deletion_scheduled_at ASC
            """)
        )
        
        pending = []
        for row in result:
            pending.append({
                "tenant_id": str(row[0]),
                "tenant_name": row[1],
                "deletion_requested_at": row[2].isoformat() if row[2] else None,
                "deletion_scheduled_at": row[3].isoformat() if row[3] else None,
                "deletion_reason": row[4]
            })
        
        return pending
    
    async def _get_tenant(self, tenant_id: UUID) -> Optional[Tenant]:
        """Get tenant by ID."""
        result = await self.session.execute(
            text("SELECT * FROM tenants WHERE id = :tenant_id"),
            {"tenant_id": tenant_id}
        )
        row = result.fetchone()
        return row if row else None
    
    async def _verify_owner(self, tenant_id: UUID, user_id: UUID) -> bool:
        """Verify user is owner of tenant."""
        result = await self.session.execute(
            text("""
                SELECT role FROM tenant_memberships
                WHERE tenant_id = :tenant_id 
                  AND user_id = :user_id
                  AND deleted_at IS NULL
            """),
            {"tenant_id": tenant_id, "user_id": user_id}
        )
        row = result.fetchone()
        return row and row[0] == "owner"
    
    async def _get_deletion_stats(self, tenant_id: UUID) -> Dict:
        """Get deletion statistics using database function."""
        result = await self.session.execute(
            text("SELECT get_tenant_deletion_stats(:tenant_id)"),
            {"tenant_id": tenant_id}
        )
        stats = result.scalar()
        return stats if stats else {}

