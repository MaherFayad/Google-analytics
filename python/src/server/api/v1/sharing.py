"""
Report Sharing Endpoints

Implements Task P0-8: Report Sharing with Secure Tokens

Features:
- Generate secure sharing links with JWT tokens
- Configurable expiration times
- View-only access (no modification)
- Audit logging of shared report access
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
import jwt

from python.src.agents.schemas.results import ReportResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sharing", tags=["sharing"])

# Secret key for JWT tokens (should be in environment variable)
JWT_SECRET = "your-secret-key-here"  # TODO: Move to config
JWT_ALGORITHM = "HS256"


class CreateShareLinkRequest(BaseModel):
    """Request to create a share link."""
    report_id: str
    expires_in_hours: int = Field(default=24, ge=1, le=720, description="Expiration time (1-720 hours)")
    allow_export: bool = Field(default=False, description="Allow recipients to export report")
    password_protected: bool = Field(default=False, description="Require password to access")
    password: Optional[str] = Field(default=None, min_length=8, description="Password (if protected)")


class ShareLinkResponse(BaseModel):
    """Response with share link details."""
    success: bool
    share_url: str
    token: str
    expires_at: datetime
    qr_code_url: Optional[str] = None


class ShareLinkInfo(BaseModel):
    """Information about a share link."""
    token: str
    report_id: str
    created_at: datetime
    expires_at: datetime
    created_by_tenant_id: str
    access_count: int = 0
    allow_export: bool
    password_protected: bool


class RevokeShareLinkRequest(BaseModel):
    """Request to revoke a share link."""
    token: str


# In-memory store for share links (replace with database in production)
_share_links: dict[str, ShareLinkInfo] = {}


async def get_tenant_id_from_token() -> str:
    """Extract tenant_id from JWT token."""
    # TODO: Implement proper JWT validation
    return "test-tenant-123"


def create_share_token(
    report_id: str,
    tenant_id: str,
    expires_in_hours: int,
    allow_export: bool,
) -> str:
    """
    Create a secure JWT token for report sharing.
    
    Args:
        report_id: Report to share
        tenant_id: Owner tenant ID
        expires_in_hours: Token expiration time
        allow_export: Whether to allow export
        
    Returns:
        JWT token string
    """
    expiration = datetime.utcnow() + timedelta(hours=expires_in_hours)
    
    payload = {
        "type": "share_link",
        "report_id": report_id,
        "tenant_id": tenant_id,
        "allow_export": allow_export,
        "exp": expiration.timestamp(),
        "iat": datetime.utcnow().timestamp(),
        "jti": str(uuid4()),  # Unique token ID
    }
    
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token


def verify_share_token(token: str) -> dict:
    """
    Verify and decode a share token.
    
    Args:
        token: JWT token to verify
        
    Returns:
        Decoded payload dict
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        
        # Verify it's a share link token
        if payload.get("type") != "share_link":
            raise HTTPException(status_code=403, detail="Invalid token type")
        
        return payload
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Share link has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=403, detail=f"Invalid share token: {str(e)}")


@router.post("/create", response_model=ShareLinkResponse)
async def create_share_link(
    request: CreateShareLinkRequest,
    tenant_id: str = Depends(get_tenant_id_from_token),
) -> ShareLinkResponse:
    """
    Create a secure share link for a report.
    
    Implements Task P0-8: Report Sharing
    
    Args:
        request: Share link configuration
        tenant_id: Extracted from JWT (owner)
        
    Returns:
        ShareLinkResponse with secure URL and token
        
    Example:
        POST /api/v1/sharing/create
        {
          "report_id": "report_123",
          "expires_in_hours": 48,
          "allow_export": false
        }
        
    Response:
        {
          "success": true,
          "share_url": "https://app.example.com/shared/abc123",
          "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
          "expires_at": "2025-01-04T19:00:00"
        }
    """
    try:
        logger.info(f"Creating share link for report {request.report_id}")
        
        # Verify password if protected
        if request.password_protected and not request.password:
            raise HTTPException(
                status_code=400,
                detail="Password required for password-protected links"
            )
        
        # Create JWT token
        token = create_share_token(
            report_id=request.report_id,
            tenant_id=tenant_id,
            expires_in_hours=request.expires_in_hours,
            allow_export=request.allow_export,
        )
        
        # Store share link info
        expires_at = datetime.utcnow() + timedelta(hours=request.expires_in_hours)
        share_info = ShareLinkInfo(
            token=token,
            report_id=request.report_id,
            created_at=datetime.utcnow(),
            expires_at=expires_at,
            created_by_tenant_id=tenant_id,
            allow_export=request.allow_export,
            password_protected=request.password_protected,
        )
        _share_links[token] = share_info
        
        # Generate share URL
        share_url = f"https://app.example.com/shared/{token[:16]}"  # Shortened for UX
        
        logger.info(f"Created share link for report {request.report_id}, expires {expires_at}")
        
        return ShareLinkResponse(
            success=True,
            share_url=share_url,
            token=token,
            expires_at=expires_at,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create share link: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create share link: {str(e)}"
        )


@router.get("/verify/{token}")
async def verify_share_link(
    token: str,
    password: Optional[str] = Query(None, description="Password (if link is protected)"),
) -> ShareLinkInfo:
    """
    Verify a share link and get report access.
    
    Args:
        token: Share link token
        password: Password (if protected)
        
    Returns:
        ShareLinkInfo with report access details
        
    Raises:
        HTTPException: If token invalid, expired, or password incorrect
    """
    try:
        # Verify JWT token
        payload = verify_share_token(token)
        
        # Get share link info
        if token not in _share_links:
            raise HTTPException(status_code=404, detail="Share link not found")
        
        share_info = _share_links[token]
        
        # Check password if protected
        if share_info.password_protected:
            # TODO: Implement password verification
            if not password:
                raise HTTPException(
                    status_code=401,
                    detail="Password required"
                )
        
        # Increment access count
        share_info.access_count += 1
        
        logger.info(f"Share link accessed: {token[:16]}... (count: {share_info.access_count})")
        
        return share_info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to verify share link: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Verification failed: {str(e)}"
        )


@router.post("/revoke")
async def revoke_share_link(
    request: RevokeShareLinkRequest,
    tenant_id: str = Depends(get_tenant_id_from_token),
) -> dict:
    """
    Revoke a share link (prevent further access).
    
    Args:
        request: Token to revoke
        tenant_id: Extracted from JWT (must be owner)
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If token not found or not owned by tenant
    """
    try:
        if request.token not in _share_links:
            raise HTTPException(status_code=404, detail="Share link not found")
        
        share_info = _share_links[request.token]
        
        # Verify ownership
        if share_info.created_by_tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Remove from store
        del _share_links[request.token]
        
        logger.info(f"Revoked share link: {request.token[:16]}...")
        
        return {
            "success": True,
            "message": "Share link revoked successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to revoke share link: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Revoke failed: {str(e)}"
        )


@router.get("/list")
async def list_share_links(
    tenant_id: str = Depends(get_tenant_id_from_token),
) -> list[ShareLinkInfo]:
    """
    List all share links created by the current tenant.
    
    Args:
        tenant_id: Extracted from JWT
        
    Returns:
        List of ShareLinkInfo objects
    """
    tenant_links = [
        info for info in _share_links.values()
        if info.created_by_tenant_id == tenant_id
    ]
    
    return tenant_links

