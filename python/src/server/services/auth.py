"""
Authentication and token management service.

Implements Task 2.4: Token Refresh Service

Handles:
- OAuth token validation
- Token refresh with Google OAuth
- User session management
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import User, GA4Credentials

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when authentication fails (user needs to re-login)."""
    pass


class AuthService:
    """
    Authentication service for OAuth token management.
    
    Implements Task 2.4: Token Refresh Service
    """
    
    GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
    TOKEN_EXPIRY_BUFFER = timedelta(minutes=5)  # Refresh 5 min before expiry
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_valid_token(self, user_id: str) -> str:
        """
        Get a valid OAuth access token for the user.
        
        If the current token is expired or near expiry, automatically
        refreshes it using the refresh_token.
        
        Args:
            user_id: User UUID
            
        Returns:
            Valid OAuth access token
            
        Raises:
            AuthenticationError: If token refresh fails (user revoked access)
        """
        # Get user's credentials
        stmt = select(GA4Credentials).where(
            GA4Credentials.user_id == user_id
        ).limit(1)
        
        result = await self.session.execute(stmt)
        credentials = result.scalar_one_or_none()
        
        if not credentials:
            raise AuthenticationError("No GA4 credentials found for user")
        
        # Check if token needs refresh
        now = datetime.utcnow()
        expires_soon = credentials.token_expiry - self.TOKEN_EXPIRY_BUFFER
        
        if now >= expires_soon:
            logger.info(f"Refreshing token for user {user_id}")
            await self._refresh_token(credentials)
        
        return credentials.access_token
    
    async def _refresh_token(self, credentials: GA4Credentials) -> None:
        """
        Refresh the OAuth access token using refresh_token.
        
        Args:
            credentials: GA4Credentials object to update
            
        Raises:
            AuthenticationError: If refresh fails
        """
        # Decrypt refresh token from database
        # Note: In production, this calls the decrypt_refresh_token() SQL function
        stmt = select(credentials.__class__).where(
            credentials.__class__.id == credentials.id
        )
        result = await self.session.execute(stmt)
        creds = result.scalar_one()
        
        # Call Google token endpoint
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.GOOGLE_TOKEN_URL,
                    data={
                        "client_id": "YOUR_CLIENT_ID",  # From settings
                        "client_secret": "YOUR_CLIENT_SECRET",
                        "refresh_token": creds.refresh_token,
                        "grant_type": "refresh_token",
                    },
                    timeout=10.0,
                )
                
                response.raise_for_status()
                token_data = response.json()
                
                # Update credentials
                credentials.access_token = token_data["access_token"]
                credentials.token_expiry = datetime.utcnow() + timedelta(
                    seconds=token_data.get("expires_in", 3600)
                )
                credentials.updated_at = datetime.utcnow()
                
                self.session.add(credentials)
                await self.session.commit()
                
                logger.info(f"Successfully refreshed token for credential {credentials.id}")
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 400:
                    # Refresh token invalid - user needs to re-authenticate
                    raise AuthenticationError(
                        "Refresh token invalid. User must re-authenticate."
                    )
                raise
            except Exception as e:
                logger.error(f"Token refresh failed: {e}", exc_info=True)
                raise AuthenticationError(f"Token refresh failed: {e}")
    
    async def create_or_update_user(
        self,
        email: str,
        name: str,
        provider: str,
        provider_user_id: str,
        avatar_url: Optional[str] = None
    ) -> User:
        """
        Create or update user from OAuth provider data.
        
        Args:
            email: User email
            name: User display name
            provider: OAuth provider (e.g., "google")
            provider_user_id: Provider's user ID
            avatar_url: Optional avatar URL
            
        Returns:
            User object
        """
        # Check if user exists
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            # Update existing user
            user.name = name
            user.avatar_url = avatar_url
            user.last_login_at = datetime.utcnow()
            user.updated_at = datetime.utcnow()
        else:
            # Create new user
            user = User(
                email=email,
                name=name,
                provider=provider,
                provider_user_id=provider_user_id,
                avatar_url=avatar_url,
                last_login_at=datetime.utcnow(),
            )
            self.session.add(user)
        
        await self.session.commit()
        await self.session.refresh(user)
        
        logger.info(f"Created/updated user: {user.email}")
        return user

