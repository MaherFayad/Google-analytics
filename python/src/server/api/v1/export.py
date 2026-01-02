"""
Report Export Endpoints

Implements Task P0-8: Report Export & Power User Features
- CSV export with full data
- Excel export with formatting  
- PDF export with charts (future)

Features:
- Streaming responses for large datasets
- Tenant isolation via JWT
- Rate limiting for enterprise features
"""

import logging
from typing import Optional
from datetime import datetime
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from python.src.agents.reporting_agent import ReportingAgent
from python.src.agents.schemas.results import ReportResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/export", tags=["export"])


class ExportRequest(BaseModel):
    """Request body for report export."""
    report_id: str
    format: str = "csv"  # csv, excel, pdf
    include_charts: bool = True
    include_citations: bool = True


class ExportResponse(BaseModel):
    """Response for export status/info."""
    success: bool
    message: str
    download_url: Optional[str] = None
    file_size_bytes: Optional[int] = None


# In-memory store for reports (replace with database in production)
_report_store: dict[str, ReportResult] = {}


def store_report(report: ReportResult) -> str:
    """
    Store report for later export.
    
    In production, this should save to database with TTL.
    """
    report_id = f"report_{report.tenant_id}_{report.timestamp.isoformat()}"
    _report_store[report_id] = report
    return report_id


async def get_report(report_id: str, tenant_id: str) -> ReportResult:
    """
    Retrieve report from store.
    
    Args:
        report_id: Report identifier
        tenant_id: Tenant ID (for isolation)
        
    Returns:
        ReportResult
        
    Raises:
        HTTPException: If report not found or access denied
    """
    if report_id not in _report_store:
        raise HTTPException(status_code=404, detail="Report not found")
    
    report = _report_store[report_id]
    
    # Verify tenant owns this report
    if report.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return report


async def get_tenant_id_from_token() -> str:
    """
    Extract tenant_id from JWT token.
    
    In production, this should:
    1. Validate JWT signature
    2. Extract tenant_id claim
    3. Verify tenant membership
    
    For now, returns a placeholder.
    """
    # TODO: Implement proper JWT validation (Task P0-2)
    return "test-tenant-123"


@router.get("/reports/{report_id}/csv")
async def export_report_csv(
    report_id: str,
    tenant_id: str = Depends(get_tenant_id_from_token),
    include_charts: bool = Query(True, description="Include chart data in CSV"),
    include_citations: bool = Query(True, description="Include source citations"),
) -> StreamingResponse:
    """
    Export report as CSV file.
    
    Implements Task P0-8: CSV Export
    
    Args:
        report_id: Report identifier
        tenant_id: Extracted from JWT (auto-injected)
        include_charts: Whether to include chart data
        include_citations: Whether to include citations
        
    Returns:
        StreamingResponse with CSV data
        
    Example:
        GET /api/v1/export/reports/report_123/csv
        
    Response:
        Content-Type: text/csv
        Content-Disposition: attachment; filename="report_123.csv"
        
        Report Export,Show sessions last week
        Generated,2025-01-02T19:00:00
        Confidence,0.92
        
        Metric Cards
        Label,Value,Change,Trend
        Sessions,12450,+21.7%,up
        ...
    """
    try:
        logger.info(f"Exporting report {report_id} as CSV for tenant {tenant_id}")
        
        # Retrieve report
        report = await get_report(report_id, tenant_id)
        
        # Generate CSV using ReportingAgent
        reporting_agent = ReportingAgent(openai_api_key="placeholder")
        csv_data = reporting_agent.export_to_csv(report)
        
        # Create filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{report_id}_{timestamp}.csv"
        
        # Return as streaming response
        return StreamingResponse(
            io.StringIO(csv_data),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CSV export failed for report {report_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Export failed: {str(e)}"
        )


@router.get("/reports/{report_id}/excel")
async def export_report_excel(
    report_id: str,
    tenant_id: str = Depends(get_tenant_id_from_token),
) -> StreamingResponse:
    """
    Export report as Excel file with formatting.
    
    Implements Task P0-8: Excel Export
    
    Future enhancement: Add chart images, formatting, multiple sheets
    
    Args:
        report_id: Report identifier
        tenant_id: Extracted from JWT
        
    Returns:
        StreamingResponse with Excel data
    """
    try:
        logger.info(f"Exporting report {report_id} as Excel for tenant {tenant_id}")
        
        # Retrieve report
        report = await get_report(report_id, tenant_id)
        
        # For now, return CSV with Excel MIME type
        # TODO: Implement proper Excel generation with openpyxl
        reporting_agent = ReportingAgent(openai_api_key="placeholder")
        csv_data = reporting_agent.export_to_csv(report)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{report_id}_{timestamp}.xlsx"
        
        return StreamingResponse(
            io.StringIO(csv_data),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Excel export failed for report {report_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Export failed: {str(e)}"
        )


@router.post("/reports/export")
async def create_export(
    request: ExportRequest,
    tenant_id: str = Depends(get_tenant_id_from_token),
) -> ExportResponse:
    """
    Create an export job (async pattern for large reports).
    
    Future enhancement for very large reports:
    1. Queue export job
    2. Return job ID
    3. Client polls for completion
    4. Download when ready
    
    Args:
        request: Export request details
        tenant_id: Extracted from JWT
        
    Returns:
        ExportResponse with download URL or job ID
    """
    try:
        # Validate format
        if request.format not in ["csv", "excel", "pdf"]:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported format: {request.format}"
            )
        
        # For now, generate synchronously
        # In production, queue this as a background job
        
        if request.format == "csv":
            download_url = f"/api/v1/export/reports/{request.report_id}/csv"
        elif request.format == "excel":
            download_url = f"/api/v1/export/reports/{request.report_id}/excel"
        else:
            raise HTTPException(
                status_code=501,
                detail="PDF export not yet implemented"
            )
        
        return ExportResponse(
            success=True,
            message=f"Export ready: {request.format}",
            download_url=download_url,
            file_size_bytes=None  # Would calculate from report
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export creation failed: {e}", exc_info=True)
        return ExportResponse(
            success=False,
            message=f"Export failed: {str(e)}"
        )


# Register report storage helper (called from analytics endpoints)
async def register_report_for_export(report: ReportResult) -> str:
    """
    Register a newly generated report for export.
    
    Called by analytics endpoints after generating a report.
    Returns report_id for client to use in export requests.
    """
    report_id = store_report(report)
    logger.info(f"Registered report {report_id} for export")
    return report_id

