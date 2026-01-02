"""Initial schema with User, GA4Credentials, ChatSession, ChatMessage

Implements:
- Task 1.3: Database Schema Definition (User & Credentials)
- Task 1.5: Chat History Schema & RLS Policies

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-01-02 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from uuid import uuid4

# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial database schema."""
    
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4),
        sa.Column('email', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('avatar_url', sa.String(500), nullable=True),
        sa.Column('provider', sa.String(50), nullable=False, server_default='google'),
        sa.Column('provider_user_id', sa.String(255), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    )
    
    # Create index on email for fast lookups
    op.create_index('idx_users_email', 'users', ['email'])
    
    # Create ga4_credentials table
    op.create_table(
        'ga4_credentials',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('property_id', sa.String(100), nullable=False, index=True),
        sa.Column('property_name', sa.String(255), nullable=True),
        sa.Column('refresh_token', sa.Text(), nullable=False),  # Will be encrypted by pgsodium
        sa.Column('access_token', sa.Text(), nullable=False),
        sa.Column('token_expiry', sa.DateTime(timezone=True), nullable=False),
        sa.Column('scope', sa.Text(), nullable=False, server_default='https://www.googleapis.com/auth/analytics.readonly'),
        sa.Column('token_type', sa.String(50), nullable=False, server_default='Bearer'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    
    # Create composite index for user + property lookups
    op.create_index('idx_ga4_credentials_user_property', 'ga4_credentials', ['user_id', 'property_id'])
    
    # Create chat_sessions table
    op.create_table(
        'chat_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('title', sa.String(255), nullable=True),
        sa.Column('persona', sa.String(50), nullable=False, server_default='general'),
        sa.Column('tenant_id', sa.String(100), nullable=False, server_default='default', index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    
    # Create composite indexes for tenant isolation and efficient queries
    op.create_index('idx_chat_sessions_tenant_user', 'chat_sessions', ['tenant_id', 'user_id'])
    op.create_index('idx_chat_sessions_user_updated', 'chat_sessions', ['user_id', 'updated_at'])
    
    # Create chat_messages table with JSONB content
    op.create_table(
        'chat_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('status', sa.String(20), nullable=False, server_default='completed'),
        sa.Column('tenant_id', sa.String(100), nullable=False, server_default='default', index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ondelete='CASCADE'),
    )
    
    # Create composite indexes for efficient message queries
    op.create_index('idx_chat_messages_session_created', 'chat_messages', ['session_id', 'created_at'])
    op.create_index('idx_chat_messages_tenant_session', 'chat_messages', ['tenant_id', 'session_id'])
    
    # Create updated_at trigger function
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Apply updated_at triggers
    op.execute("""
        CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    
    op.execute("""
        CREATE TRIGGER update_ga4_credentials_updated_at BEFORE UPDATE ON ga4_credentials
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    
    op.execute("""
        CREATE TRIGGER update_chat_sessions_updated_at BEFORE UPDATE ON chat_sessions
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)


def downgrade() -> None:
    """Drop all tables and functions."""
    
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS update_chat_sessions_updated_at ON chat_sessions;")
    op.execute("DROP TRIGGER IF EXISTS update_ga4_credentials_updated_at ON ga4_credentials;")
    op.execute("DROP TRIGGER IF EXISTS update_users_updated_at ON users;")
    
    # Drop trigger function
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column();")
    
    # Drop tables (in reverse order due to foreign keys)
    op.drop_table('chat_messages')
    op.drop_table('chat_sessions')
    op.drop_table('ga4_credentials')
    op.drop_table('users')

