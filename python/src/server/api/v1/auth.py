"""
Authentication API endpoints.

Implements Task 2.3: FastAPI Credential Sync Endpoint

This module provides endpoints for OAuth credential synchronization
between NextAuth (frontend) and FastAPI (backend).
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import settings
from ...database import get_session
from ...models.user import User, GA4Credentials
from ...services.auth import AuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


class CredentialSyncRequest(BaseModel):
    """
    Request model for credential synchronization (Task 2.3).
    
    Sent from NextAuth JWT callback to FastAPI backend.
    """
    
    email: EmailStr = Field(description="User email from OAuth provider")
    access_token: str = Field(description="OAuth access token")
    refresh_token: str = Field(description="OAuth refresh token (will be encrypted)")
    expires_at: str = Field(description="Token expiry timestamp (ISO format)")
    property_id: Optional[str] = Field(
        default=None,
        description="GA4 property ID (optional, can be set later)"
    )
    property_name: Optional[str] = Field(default=None)


class CredentialSyncResponse(BaseModel):
    """Response model for credential sync."""
    
    success: bool
    message: str
    user_id: Optional[str] = None


def verify_api_secret(x_api_secret: str = Header(...)) -> bool:
    """
    Verify shared API secret for NextAuth → FastAPI communication.
    
    Task 2.3 requirement: Protect sync endpoint with shared secret.
    
    Args:
        x_api_secret: API secret from request header
        
    Returns:
        True if valid
        
    Raises:
        HTTPException: If secret is invalid
    """
    # In production, use environment variable or NextAuth JWT signature verification
    expected_secret = settings.API_SECRET if hasattr(settings, 'API_SECRET') else "development-secret"
    
    if x_api_secret != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API secret"
        )
    
    return True


@router.post(
    "/sync",
    response_model=CredentialSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Sync OAuth credentials from NextAuth",
    description="""
    Task 2.3: FastAPI Credential Sync Endpoint
    
    This endpoint receives OAuth tokens from NextAuth and stores them
    in the backend database with encryption.
    
    Flow:
    1. NextAuth JWT callback calls this endpoint
    2. Verify API secret for security
    3. Create or update User record
    4. UPSERT GA4Credentials (triggers pgsodium encryption)
    5. Return success status
    
    Security:
    - Protected by X-API-Secret header
    - Refresh token encrypted at database level (Task 1.4)
    - Only callable from NextAuth backend
    """
)
async def sync_credentials(
    request: CredentialSyncRequest,
    session: AsyncSession = Depends(get_session),
    _verified: bool = Depends(verify_api_secret),
) -> CredentialSyncResponse:
    """
    Sync OAuth credentials from NextAuth to FastAPI.
    
    Implements Task 2.3: Credential synchronization with encryption.
    
    Args:
        request: Credential sync request data
        session: Database session
        _verified: API secret verification result
        
    Returns:
        Success response with user ID
    """
    try:
        logger.info(f"Syncing credentials for user: {request.email}")
        
        # Parse expiry timestamp
        token_expiry = datetime.fromisoformat(request.expires_at.replace('Z', '+00:00'))
        
        # Check if user exists
        stmt = select(User).where(User.email == request.email)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        # Create user if doesn't exist
        if not user:
            user = User(
                email=request.email,
                name=request.email.split('@')[0],  # Default name from email
                provider="google",
                provider_user_id=request.email,  # Will be updated on first full OAuth
                last_login_at=datetime.now(timezone.utc),
            )
            session.add(user)
            await session.flush()  # Get user.id
            logger.info(f"Created new user: {user.id}")
        else:
            # Update last login
            user.last_login_at = datetime.now(timezone.utc)
            user.updated_at = datetime.now(timezone.utc)
            logger.info(f"Updated existing user: {user.id}")
        
        # Check if credentials exist for this user
        stmt = select(GA4Credentials).where(GA4Credentials.user_id == user.id)
        result = await session.execute(stmt)
        credentials = result.scalar_one_or_none()
        
        if credentials:
            # Update existing credentials
            credentials.access_token = request.access_token
            credentials.refresh_token = request.refresh_token  # Will be encrypted by trigger
            credentials.token_expiry = token_expiry
            credentials.updated_at = datetime.now(timezone.utc)
            
            if request.property_id:
                credentials.property_id = request.property_id
            if request.property_name:
                credentials.property_name = request.property_name
            
            logger.info(f"Updated credentials for user: {user.id}")
        else:
            # Create new credentials
            credentials = GA4Credentials(
                user_id=user.id,
                property_id=request.property_id or "default",  # Placeholder
                property_name=request.property_name,
                refresh_token=request.refresh_token,  # Encrypted by pgsodium trigger
                access_token=request.access_token,
                token_expiry=token_expiry,
            )
            session.add(credentials)
            logger.info(f"Created new credentials for user: {user.id}")
        
        # Bug Fix #2: Don't explicitly commit - let get_session() dependency handle it
        # The dependency will commit after the endpoint returns
        # await session.commit()  # REMOVED - dependency handles this
        
        return CredentialSyncResponse(
            success=True,
            message="Credentials synchronized successfully",
            user_id=str(user.id),
        )
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Error syncing credentials: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync credentials: {str(e)}"
        )


@router.get(
    "/status",
    summary="Check authentication status",
    description="Check if user has valid GA4 credentials"
)
async def auth_status(
    user_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Check authentication status for a user.
    
    Returns:
        Authentication status and credential info
    """
    # Bug Fix #3: Convert user_id string to UUID before querying
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid user_id format: {user_id}"
        )
    
    stmt = select(GA4Credentials).where(GA4Credentials.user_id == user_uuid)
    result = await session.execute(stmt)
    credentials = result.scalar_one_or_none()
    
    if not credentials:
        return {
            "authenticated": False,
            "message": "No GA4 credentials found"
        }
    
    # Bug Fix #1: Use timezone-aware datetime
    now = datetime.now(timezone.utc)
    is_expired = credentials.token_expiry < now
    
    return {
        "authenticated": not is_expired,
        "property_id": credentials.property_id,
        "property_name": credentials.property_name,
        "token_expires_at": credentials.token_expiry.isoformat(),
        "is_expired": is_expired,
    }


class GA4PropertyStatus(BaseModel):
    """GA4 property connection status."""
    
    property_id: str
    property_name: Optional[str]
    last_sync: Optional[str]
    is_active: bool
    token_expires_at: str


class GA4StatusResponse(BaseModel):
    """Response model for GA4 connection status."""
    
    authenticated: bool
    properties: list[GA4PropertyStatus]
    total_properties: int


@router.get(
    "/ga4/status",
    response_model=GA4StatusResponse,
    summary="Get GA4 connection status",
    description="""
    Task 10.3: OAuth Connection Status UI
    
    Returns all connected GA4 properties for a user, including:
    - Property ID and name
    - Last sync timestamp
    - Token expiry status
    - Active/inactive state
    """
)
async def ga4_status(
    user_id: str,
    session: AsyncSession = Depends(get_session),
) -> GA4StatusResponse:
    """
    Get GA4 connection status for a user.
    
    Implements Task 10.3: Display list of connected GA4 properties.
    
    Args:
        user_id: User UUID
        session: Database session
        
    Returns:
        GA4StatusResponse with all connected properties
    """
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid user_id format: {user_id}"
        )
    
    # Fetch all GA4 credentials for this user
    stmt = select(GA4Credentials).where(GA4Credentials.user_id == user_uuid)
    result = await session.execute(stmt)
    credentials_list = result.scalars().all()
    
    if not credentials_list:
        return GA4StatusResponse(
            authenticated=False,
            properties=[],
            total_properties=0
        )
    
    # Build property status list
    now = datetime.now(timezone.utc)
    properties = []
    
    for cred in credentials_list:
        is_active = cred.token_expiry > now
        
        properties.append(GA4PropertyStatus(
            property_id=cred.property_id,
            property_name=cred.property_name,
            last_sync=cred.last_used_at.isoformat() if cred.last_used_at else None,
            is_active=is_active,
            token_expires_at=cred.token_expiry.isoformat(),
        ))
    
    return GA4StatusResponse(
        authenticated=True,
        properties=properties,
        total_properties=len(properties)
    )
