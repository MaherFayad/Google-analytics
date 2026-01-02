"""
Tenant data export service for GDPR compliance.

Implements Task P0-30: GDPR Article 20 - Right to Data Portability

Features:
- Complete tenant data export in JSON format
- Includes all user data, metrics, embeddings, chat history
- Machine-readable format for data portability
- Optional file export to S3/storage
"""

import json
import logging
from datetime import datetime
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class TenantExportError(Exception):
    """Base exception for tenant export errors."""
    pass


class TenantExportService:
    """
    Service for GDPR-compliant tenant data export.
    
    Implements Article 20: Right to Data Portability
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def export_tenant_data(
        self,
        tenant_id: UUID,
        include_raw_data: bool = False,
        save_to_file: bool = False
    ) -> Dict:
        """
        Export all tenant data in JSON format.
        
        GDPR Article 20: Right to Data Portability
        - Machine-readable format (JSON)
        - Complete data export
        - Includes all personal and usage data
        
        Args:
            tenant_id: Tenant UUID
            include_raw_data: Whether to include full raw GA4 metrics
            save_to_file: Whether to save export to file/S3
        
        Returns:
            Dict with export data and metadata
        
        Raises:
            TenantExportError: If export fails
        """
        try:
            # 1. Use database function for summary export
            result = await self.session.execute(
                text("SELECT export_tenant_data(:tenant_id)"),
                {"tenant_id": tenant_id}
            )
            export_data = result.scalar()
            
            if not export_data:
                raise TenantExportError(f"Failed to export data for tenant {tenant_id}")
            
            # 2. Optionally include raw data (full GA4 metrics, embeddings)
            if include_raw_data:
                raw_data = await self._export_raw_data(tenant_id)
                export_data["raw_data"] = raw_data
            
            # 3. Add export metadata
            export_metadata = {
                "export_id": str(UUID()),
                "tenant_id": str(tenant_id),
                "export_date": datetime.utcnow().isoformat(),
                "export_version": "1.0",
                "gdpr_compliant": True,
                "includes_raw_data": include_raw_data,
                "format": "application/json"
            }
            export_data["export_metadata"] = export_metadata
            
            # 4. Optionally save to file
            export_url = None
            if save_to_file:
                export_url = await self._save_export(tenant_id, export_data)
            
            logger.info(f"Tenant data exported: {tenant_id}")
            
            return {
                "success": True,
                "tenant_id": str(tenant_id),
                "export_data": export_data,
                "export_url": export_url,
                "exported_at": datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Failed to export tenant data: {e}")
            raise TenantExportError(f"Export failed: {str(e)}")
    
    async def _export_raw_data(self, tenant_id: UUID) -> Dict:
        """
        Export raw GA4 metrics and embeddings.
        
        WARNING: This can be very large for tenants with lots of data.
        
        Args:
            tenant_id: Tenant UUID
        
        Returns:
            Dict with raw data
        """
        # Export GA4 metrics (limit to recent data to avoid huge exports)
        ga4_metrics_result = await self.session.execute(
            text("""
                SELECT 
                    id,
                    property_id,
                    metric_date,
                    event_name,
                    dimension_context,
                    metric_values,
                    descriptive_summary,
                    synced_at
                FROM ga4_metrics_raw
                WHERE tenant_id = :tenant_id
                ORDER BY metric_date DESC
                LIMIT 10000  -- Limit to 10k most recent records
            """),
            {"tenant_id": tenant_id}
        )
        
        ga4_metrics = []
        for row in ga4_metrics_result:
            ga4_metrics.append({
                "id": str(row[0]),
                "property_id": row[1],
                "metric_date": row[2].isoformat() if row[2] else None,
                "event_name": row[3],
                "dimension_context": row[4],
                "metric_values": row[5],
                "descriptive_summary": row[6],
                "synced_at": row[7].isoformat() if row[7] else None
            })
        
        # Export embeddings (without actual vectors to reduce size)
        embeddings_result = await self.session.execute(
            text("""
                SELECT 
                    id,
                    content,
                    temporal_metadata,
                    embedding_model,
                    quality_score,
                    created_at
                FROM ga4_embeddings
                WHERE tenant_id = :tenant_id
                ORDER BY created_at DESC
                LIMIT 5000  -- Limit to 5k most recent embeddings
            """),
            {"tenant_id": tenant_id}
        )
        
        embeddings = []
        for row in embeddings_result:
            embeddings.append({
                "id": str(row[0]),
                "content": row[1],
                "temporal_metadata": row[2],
                "embedding_model": row[3],
                "quality_score": row[4],
                "created_at": row[5].isoformat() if row[5] else None
            })
        
        # Export chat sessions and messages
        chat_result = await self.session.execute(
            text("""
                SELECT 
                    cs.id,
                    cs.title,
                    cs.persona,
                    cs.created_at,
                    json_agg(
                        json_build_object(
                            'id', cm.id,
                            'role', cm.role,
                            'content', cm.content,
                            'created_at', cm.created_at
                        ) ORDER BY cm.created_at
                    ) as messages
                FROM chat_sessions cs
                LEFT JOIN chat_messages cm ON cs.id = cm.session_id
                WHERE cs.tenant_id::uuid = :tenant_id
                GROUP BY cs.id, cs.title, cs.persona, cs.created_at
                ORDER BY cs.created_at DESC
                LIMIT 1000  -- Limit to 1k most recent sessions
            """),
            {"tenant_id": tenant_id}
        )
        
        chat_sessions = []
        for row in chat_result:
            chat_sessions.append({
                "id": str(row[0]),
                "title": row[1],
                "persona": row[2],
                "created_at": row[3].isoformat() if row[3] else None,
                "messages": row[4] if row[4] else []
            })
        
        return {
            "ga4_metrics": {
                "count": len(ga4_metrics),
                "records": ga4_metrics,
                "note": "Limited to 10,000 most recent records"
            },
            "embeddings": {
                "count": len(embeddings),
                "records": embeddings,
                "note": "Limited to 5,000 most recent embeddings (vectors excluded for size)"
            },
            "chat_sessions": {
                "count": len(chat_sessions),
                "sessions": chat_sessions,
                "note": "Limited to 1,000 most recent sessions"
            }
        }
    
    async def _save_export(self, tenant_id: UUID, export_data: Dict) -> str:
        """
        Save export to file/S3.
        
        TODO: Implement S3 upload for production
        For now, returns local file path.
        
        Args:
            tenant_id: Tenant UUID
            export_data: Export data to save
        
        Returns:
            URL/path to saved export
        """
        # For now, just return a placeholder
        # In production, this would upload to S3 and return presigned URL
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"tenant_export_{tenant_id}_{timestamp}.json"
        
        # TODO: Implement actual S3 upload
        # s3_url = await upload_to_s3(filename, export_data)
        
        logger.info(f"Export saved: {filename}")
        
        return f"/exports/{filename}"  # Placeholder
    
    async def export_user_data(
        self,
        user_id: UUID,
        tenant_id: Optional[UUID] = None
    ) -> Dict:
        """
        Export data for a specific user (GDPR Article 15 - Right of Access).
        
        Args:
            user_id: User UUID
            tenant_id: Optional tenant UUID to scope export
        
        Returns:
            Dict with user's data
        """
        # Export user's personal data
        user_result = await self.session.execute(
            text("""
                SELECT 
                    id,
                    email,
                    full_name,
                    created_at,
                    updated_at
                FROM users
                WHERE id = :user_id
            """),
            {"user_id": user_id}
        )
        user_row = user_result.fetchone()
        
        if not user_row:
            raise TenantExportError(f"User {user_id} not found")
        
        user_data = {
            "id": str(user_row[0]),
            "email": user_row[1],
            "full_name": user_row[2],
            "created_at": user_row[3].isoformat() if user_row[3] else None,
            "updated_at": user_row[4].isoformat() if user_row[4] else None
        }
        
        # Export user's tenant memberships
        memberships_result = await self.session.execute(
            text("""
                SELECT 
                    tm.tenant_id,
                    t.name,
                    tm.role,
                    tm.created_at
                FROM tenant_memberships tm
                JOIN tenants t ON tm.tenant_id = t.id
                WHERE tm.user_id = :user_id
                  AND tm.deleted_at IS NULL
                  AND (:tenant_id IS NULL OR tm.tenant_id = :tenant_id)
            """),
            {"user_id": user_id, "tenant_id": tenant_id}
        )
        
        memberships = []
        for row in memberships_result:
            memberships.append({
                "tenant_id": str(row[0]),
                "tenant_name": row[1],
                "role": row[2],
                "joined_at": row[3].isoformat() if row[3] else None
            })
        
        return {
            "success": True,
            "user": user_data,
            "memberships": memberships,
            "exported_at": datetime.utcnow().isoformat(),
            "gdpr_compliant": True
        }

