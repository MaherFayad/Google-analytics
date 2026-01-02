"""
Report Version History API

Implements Task P0-36: Report Version History & Diff Viewer

Provides REST endpoints for managing and comparing report versions.
"""

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/report-versions", tags=["report-versions"])


# ========== Request/Response Models ==========

class ReportVersionCreate(BaseModel):
    """Request model for creating a report version."""
    
    report_id: str = Field(description="Report UUID")
    tenant_id: str = Field(description="Tenant UUID")
    content_json: dict = Field(description="Full report content")
    query: str = Field(description="Query that generated the report")
    created_by: str = Field(description="User UUID")


class ReportVersionResponse(BaseModel):
    """Response model for report version."""
    
    id: str
    report_id: str
    tenant_id: str
    version_number: int
    content_json: dict
    query: str
    created_at: str
    created_by: Optional[str]


class ReportVersionListItem(BaseModel):
    """Simplified model for version lists."""
    
    id: str
    version_number: int
    query: str
    created_at: str
    preview: str = Field(description="Short content preview")


class ReportVersionDiff(BaseModel):
    """Diff between two report versions."""
    
    report_id: str
    version_1: int
    version_2: int
    version_1_content: dict
    version_2_content: dict
    differences: dict = Field(description="Structured differences")


# ========== Endpoints ==========

@router.post(
    "/",
    response_model=ReportVersionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new report version",
    description="""
    Task P0-36: Create a new version of a report.
    
    Automatically increments version number.
    Stores full report content as JSONB.
    """
)
async def create_version(
    request: ReportVersionCreate,
    session: AsyncSession = Depends(get_session),
) -> ReportVersionResponse:
    """
    Create a new report version.
    
    Args:
        request: Version creation data
        session: Database session
        
    Returns:
        Created version response
    """
    try:
        # Parse UUIDs
        report_uuid = UUID(request.report_id)
        tenant_uuid = UUID(request.tenant_id)
        user_uuid = UUID(request.created_by)
        
        # Call database function to create version
        query = text("""
            SELECT create_report_version(
                :report_id::uuid,
                :tenant_id::uuid,
                :content_json::jsonb,
                :query,
                :created_by::uuid
            ) AS version_id
        """)
        
        result = await session.execute(
            query,
            {
                "report_id": str(report_uuid),
                "tenant_id": str(tenant_uuid),
                "content_json": request.content_json,
                "query": request.query,
                "created_by": str(user_uuid)
            }
        )
        
        await session.commit()
        
        version_id = result.scalar_one()
        
        # Fetch the created version
        fetch_query = text("""
            SELECT id, report_id, tenant_id, version_number, content_json, query, created_at, created_by
            FROM report_versions
            WHERE id = :version_id::uuid
        """)
        
        fetch_result = await session.execute(
            fetch_query,
            {"version_id": str(version_id)}
        )
        
        row = fetch_result.fetchone()
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve created version"
            )
        
        return ReportVersionResponse(
            id=str(row.id),
            report_id=str(row.report_id),
            tenant_id=str(row.tenant_id),
            version_number=row.version_number,
            content_json=row.content_json,
            query=row.query,
            created_at=row.created_at.isoformat(),
            created_by=str(row.created_by) if row.created_by else None
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID format: {e}"
        )
    except Exception as e:
        await session.rollback()
        logger.error(f"Error creating report version: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create version: {str(e)}"
        )


@router.get(
    "/{report_id}",
    response_model=List[ReportVersionListItem],
    summary="List all versions of a report",
    description="Get all historical versions of a specific report"
)
async def list_versions(
    report_id: str,
    tenant_id: str = Query(..., description="Tenant UUID"),
    session: AsyncSession = Depends(get_session),
) -> List[ReportVersionListItem]:
    """
    List all versions of a report.
    
    Args:
        report_id: Report UUID
        tenant_id: Tenant UUID
        session: Database session
        
    Returns:
        List of report versions
    """
    try:
        report_uuid = UUID(report_id)
        tenant_uuid = UUID(tenant_id)
        
        query = text("""
            SELECT 
                id,
                version_number,
                query,
                created_at,
                content_json::text AS content_preview
            FROM report_versions
            WHERE report_id = :report_id::uuid
            AND tenant_id = :tenant_id::uuid
            ORDER BY version_number DESC
        """)
        
        result = await session.execute(
            query,
            {
                "report_id": str(report_uuid),
                "tenant_id": str(tenant_uuid)
            }
        )
        
        rows = result.fetchall()
        
        versions = []
        for row in rows:
            # Generate preview from content
            preview = row.content_preview[:200] + "..." if len(row.content_preview) > 200 else row.content_preview
            
            versions.append(ReportVersionListItem(
                id=str(row.id),
                version_number=row.version_number,
                query=row.query,
                created_at=row.created_at.isoformat(),
                preview=preview
            ))
        
        return versions
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID format: {e}"
        )
    except Exception as e:
        logger.error(f"Error listing report versions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list versions: {str(e)}"
        )


@router.get(
    "/{report_id}/{version_number}",
    response_model=ReportVersionResponse,
    summary="Get a specific report version",
    description="Retrieve full content of a specific report version"
)
async def get_version(
    report_id: str,
    version_number: int,
    tenant_id: str = Query(..., description="Tenant UUID"),
    session: AsyncSession = Depends(get_session),
) -> ReportVersionResponse:
    """
    Get a specific report version.
    
    Args:
        report_id: Report UUID
        version_number: Version number
        tenant_id: Tenant UUID
        session: Database session
        
    Returns:
        Full report version
    """
    try:
        report_uuid = UUID(report_id)
        tenant_uuid = UUID(tenant_id)
        
        query = text("""
            SELECT id, report_id, tenant_id, version_number, content_json, query, created_at, created_by
            FROM report_versions
            WHERE report_id = :report_id::uuid
            AND tenant_id = :tenant_id::uuid
            AND version_number = :version_number
        """)
        
        result = await session.execute(
            query,
            {
                "report_id": str(report_uuid),
                "tenant_id": str(tenant_uuid),
                "version_number": version_number
            }
        )
        
        row = result.fetchone()
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version {version_number} not found for report {report_id}"
            )
        
        return ReportVersionResponse(
            id=str(row.id),
            report_id=str(row.report_id),
            tenant_id=str(row.tenant_id),
            version_number=row.version_number,
            content_json=row.content_json,
            query=row.query,
            created_at=row.created_at.isoformat(),
            created_by=str(row.created_by) if row.created_by else None
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID format: {e}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting report version: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get version: {str(e)}"
        )


@router.get(
    "/{report_id}/compare",
    response_model=ReportVersionDiff,
    summary="Compare two report versions",
    description="Get structured diff between two versions of a report"
)
async def compare_versions(
    report_id: str,
    version_1: int = Query(..., description="First version number"),
    version_2: int = Query(..., description="Second version number"),
    tenant_id: str = Query(..., description="Tenant UUID"),
    session: AsyncSession = Depends(get_session),
) -> ReportVersionDiff:
    """
    Compare two versions of a report.
    
    Args:
        report_id: Report UUID
        version_1: First version number
        version_2: Second version number
        tenant_id: Tenant UUID
        session: Database session
        
    Returns:
        Diff between versions
    """
    try:
        report_uuid = UUID(report_id)
        tenant_uuid = UUID(tenant_id)
        
        # Fetch both versions
        query = text("""
            SELECT version_number, content_json
            FROM report_versions
            WHERE report_id = :report_id::uuid
            AND tenant_id = :tenant_id::uuid
            AND version_number IN (:v1, :v2)
        """)
        
        result = await session.execute(
            query,
            {
                "report_id": str(report_uuid),
                "tenant_id": str(tenant_uuid),
                "v1": version_1,
                "v2": version_2
            }
        )
        
        rows = result.fetchall()
        
        if len(rows) != 2:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="One or both versions not found"
            )
        
        # Extract contents
        v1_content = next((row.content_json for row in rows if row.version_number == version_1), None)
        v2_content = next((row.content_json for row in rows if row.version_number == version_2), None)
        
        # Calculate differences
        differences = calculate_json_diff(v1_content, v2_content)
        
        return ReportVersionDiff(
            report_id=report_id,
            version_1=version_1,
            version_2=version_2,
            version_1_content=v1_content,
            version_2_content=v2_content,
            differences=differences
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID format: {e}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing report versions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compare versions: {str(e)}"
        )


# ========== Helper Functions ==========

def calculate_json_diff(obj1: dict, obj2: dict) -> dict:
    """
    Calculate differences between two JSON objects.
    
    Args:
        obj1: First object
        obj2: Second object
        
    Returns:
        Dictionary describing differences
    """
    diff = {
        "added_keys": [],
        "removed_keys": [],
        "changed_values": [],
        "unchanged_keys": []
    }
    
    keys1 = set(obj1.keys())
    keys2 = set(obj2.keys())
    
    # Added and removed keys
    diff["added_keys"] = list(keys2 - keys1)
    diff["removed_keys"] = list(keys1 - keys2)
    
    # Changed values
    common_keys = keys1 & keys2
    for key in common_keys:
        if obj1[key] != obj2[key]:
            diff["changed_values"].append({
                "key": key,
                "old_value": obj1[key],
                "new_value": obj2[key]
            })
        else:
            diff["unchanged_keys"].append(key)
    
    return diff

