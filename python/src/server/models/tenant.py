"""
Tenant and membership models.

Implements Task P0-2 & P0-28: Multi-tenant membership system
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel


class Tenant(SQLModel, table=True):
    """
    Tenant (Organization) model.
    
    Represents an organization that can have multiple users.
    Users can belong to multiple tenants.
    """
    
    __tablename__ = "tenants"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=255)
    slug: str = Field(max_length=100, unique=True, index=True)
    description: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    memberships: list["TenantMembership"] = Relationship(back_populates="tenant")


class TenantMembership(SQLModel, table=True):
    """
    Tenant membership model with RBAC.
    
    Implements Task P0-28: Multi-tenant membership with roles
    
    Roles:
    - owner: Full access, can delete tenant
    - admin: Can manage members and settings
    - member: Can access and use tenant resources
    - viewer: Read-only access
    """
    
    __tablename__ = "tenant_memberships"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    
    user_id: UUID = Field(foreign_key="users.id", index=True)
    tenant_id: UUID = Field(foreign_key="tenants.id", index=True)
    
    role: str = Field(default="member", max_length=50)
    
    # Invitation tracking
    invited_by: Optional[UUID] = Field(default=None, foreign_key="users.id")
    invitation_token: Optional[str] = Field(default=None, max_length=255, unique=True)
    accepted_at: Optional[datetime] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    tenant: Tenant = Relationship(back_populates="memberships")
    
    def is_owner(self) -> bool:
        """Check if user is tenant owner."""
        return self.role == "owner"
    
    def is_admin(self) -> bool:
        """Check if user is admin or owner."""
        return self.role in ("owner", "admin")
    
    def can_manage_members(self) -> bool:
        """Check if user can manage tenant members."""
        return self.is_admin()
    
    def can_write(self) -> bool:
        """Check if user has write access."""
        return self.role in ("owner", "admin", "member")
    
    def can_read(self) -> bool:
        """Check if user has read access."""
        return self.role in ("owner", "admin", "member", "viewer")



