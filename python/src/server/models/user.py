"""
User and GA4 Credentials models.

Implements Task 1.3: Database Schema Definition (User & Credentials)

Critical: Encryption is NOT implemented in Python. The refresh_token
encryption is handled via pgsodium at the database level (Task 1.4).
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel


class User(SQLModel, table=True):
    """
    User model for authentication and authorization.
    
    Stores basic user information from OAuth providers (Google).
    Links to GA4Credentials for analytics access.
    """
    
    __tablename__ = "users"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(index=True, unique=True, max_length=255)
    name: Optional[str] = Field(default=None, max_length=255)
    avatar_url: Optional[str] = Field(default=None, max_length=500)
    
    # OAuth provider information
    provider: str = Field(default="google", max_length=50)
    provider_user_id: str = Field(index=True, max_length=255)
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: Optional[datetime] = None
    
    # Relationships
    credentials: list["GA4Credentials"] = Relationship(back_populates="user")
    chat_sessions: list["ChatSession"] = Relationship(back_populates="user")
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "name": "John Doe",
                "provider": "google",
                "provider_user_id": "google_123456"
            }
        }


class GA4Credentials(SQLModel, table=True):
    """
    Google Analytics 4 OAuth credentials storage.
    
    Implements Task 1.3: Credentials schema
    
    CRITICAL SECURITY NOTE:
    - The refresh_token field is stored in plaintext at the application level
    - Database-level encryption is handled by pgsodium (Task 1.4)
    - A PL/pgSQL trigger automatically encrypts refresh_token on INSERT/UPDATE
    - Access tokens are short-lived and rotated frequently
    
    Fields:
    - property_id: GA4 property ID (e.g., "123456789")
    - refresh_token: OAuth2 refresh token (encrypted at DB level)
    - access_token: Short-lived OAuth2 access token
    - token_expiry: When the access_token expires (UTC)
    """
    
    __tablename__ = "ga4_credentials"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    
    # Foreign key to User
    user_id: UUID = Field(foreign_key="users.id", index=True)
    
    # GA4 property information
    property_id: str = Field(index=True, max_length=100)
    property_name: Optional[str] = Field(default=None, max_length=255)
    
    # OAuth tokens (refresh_token encrypted at DB level via pgsodium)
    refresh_token: str = Field(max_length=1000)  # Encrypted by database trigger
    access_token: str = Field(max_length=1000)   # Short-lived, rotated frequently
    token_expiry: datetime = Field()
    
    # Token metadata
    scope: str = Field(default="https://www.googleapis.com/auth/analytics.readonly")
    token_type: str = Field(default="Bearer")
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: Optional[datetime] = None
    
    # Relationships
    user: User = Relationship(back_populates="credentials")
    
    class Config:
        json_schema_extra = {
            "example": {
                "property_id": "123456789",
                "property_name": "My Website",
                "scope": "https://www.googleapis.com/auth/analytics.readonly",
                "token_type": "Bearer"
            }
        }


# Import ChatSession for type hints (avoid circular import)
from .chat import ChatSession  # noqa: E402

