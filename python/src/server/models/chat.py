"""
Chat session and message models.

Implements Task 1.5: Chat History Schema & RLS Policies

Features:
- JSONB content field for structured report data
- Tenant isolation via user_id filtering (service-layer RLS)
- Support for streaming status tracking
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel


class ChatSession(SQLModel, table=True):
    """
    Chat session model.
    
    Represents a conversation thread with the AI analytics assistant.
    Each session can contain multiple messages (user queries and AI responses).
    """
    
    __tablename__ = "chat_sessions"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    
    # Foreign key to User
    user_id: UUID = Field(foreign_key="users.id", index=True)
    
    # Session metadata
    title: Optional[str] = Field(default=None, max_length=255)
    persona: str = Field(default="general", max_length=50)  # po, ux, mgr, general
    
    # Multi-tenant isolation (Task 11)
    tenant_id: str = Field(default="default", index=True, max_length=100)
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_message_at: Optional[datetime] = None
    
    # Relationships
    user: "User" = Relationship(back_populates="chat_sessions")
    messages: list["ChatMessage"] = Relationship(back_populates="session")
    
    # Composite index for tenant isolation + user filtering
    __table_args__ = (
        Index("idx_chat_sessions_tenant_user", "tenant_id", "user_id"),
        Index("idx_chat_sessions_user_updated", "user_id", "updated_at"),
    )


class ChatMessage(SQLModel, table=True):
    """
    Chat message model with JSONB content storage.
    
    Implements Task 1.5: JSONB content field for structured reports
    
    The content field stores:
    - User messages: { "type": "user", "query": str }
    - AI responses: { "type": "ai", "answer": str, "charts": [...], "metrics": [...] }
    - System messages: { "type": "system", "message": str }
    
    This allows flexible storage of structured report data including:
    - Natural language answers
    - Chart configurations (for Recharts)
    - Metric cards
    - Source citations
    """
    
    __tablename__ = "chat_messages"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    
    # Foreign key to ChatSession
    session_id: UUID = Field(foreign_key="chat_sessions.id", index=True)
    
    # Message metadata
    role: str = Field(max_length=20)  # "user", "assistant", "system"
    
    # JSONB content field (Task 1.5 requirement)
    # Using SQLAlchemy Column for JSONB support
    content: Dict[str, Any] = Field(
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    )
    
    # Message status (for streaming)
    status: str = Field(default="completed", max_length=20)  # "pending", "streaming", "completed", "error"
    
    # Multi-tenant isolation
    tenant_id: str = Field(default="default", index=True, max_length=100)
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Relationships
    session: ChatSession = Relationship(back_populates="messages")
    
    # Composite indexes for efficient queries
    __table_args__ = (
        Index("idx_chat_messages_session_created", "session_id", "created_at"),
        Index("idx_chat_messages_tenant_session", "tenant_id", "session_id"),
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "role": "assistant",
                "content": {
                    "type": "ai",
                    "answer": "Mobile conversions increased 21.7% last week...",
                    "charts": [
                        {
                            "type": "line",
                            "title": "Sessions Over Time",
                            "data": [
                                {"x": "2025-01-01", "y": 1234}
                            ]
                        }
                    ],
                    "metrics": [
                        {
                            "label": "Sessions",
                            "value": "12,450",
                            "change": "+21.7%"
                        }
                    ]
                },
                "status": "completed"
            }
        }


# Import User for type hints (avoid circular import)
from .user import User  # noqa: E402

