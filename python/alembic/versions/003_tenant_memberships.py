"""Multi-tenant membership system

Implements Task P0-2: Server-Side Tenant Derivation
Implements Task P0-28: Multi-Tenant Membership Schema with RBAC

Adds support for:
- Users belonging to multiple tenants (organizations)
- Role-based access control (admin, member, viewer)
- Tenant context switching
- Membership validation

Revision ID: 003_tenant_memberships
Revises: 002_pgsodium_encryption
Create Date: 2026-01-02 12:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003_tenant_memberships'
down_revision = '002_pgsodium_encryption'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create tenant membership tables and RLS infrastructure."""
    
    # Create tenants table
    op.create_table(
        'tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False, unique=True, index=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    
    # Create tenant_memberships table
    op.create_table(
        'tenant_memberships',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('role', sa.String(50), nullable=False, server_default='member'),
        sa.Column('invited_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('invitation_token', sa.String(255), nullable=True, unique=True),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by'], ['users.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('user_id', 'tenant_id', name='uq_user_tenant'),
    )
    
    # Create indexes for efficient membership lookups
    op.create_index('idx_tenant_memberships_user_tenant', 'tenant_memberships', ['user_id', 'tenant_id'])
    op.create_index('idx_tenant_memberships_tenant_role', 'tenant_memberships', ['tenant_id', 'role'])
    
    # Add role validation constraint
    op.execute("""
        ALTER TABLE tenant_memberships
        ADD CONSTRAINT chk_valid_role
        CHECK (role IN ('owner', 'admin', 'member', 'viewer'));
    """)
    
    # Create updated_at trigger for tenants
    op.execute("""
        CREATE TRIGGER update_tenants_updated_at BEFORE UPDATE ON tenants
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    
    # Create updated_at trigger for tenant_memberships
    op.execute("""
        CREATE TRIGGER update_tenant_memberships_updated_at BEFORE UPDATE ON tenant_memberships
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    
    # Create function to check tenant membership (used by RLS policies)
    op.execute("""
        CREATE OR REPLACE FUNCTION has_tenant_access(
            p_user_id uuid,
            p_tenant_id uuid
        ) RETURNS boolean AS $$
        BEGIN
            RETURN EXISTS (
                SELECT 1
                FROM tenant_memberships
                WHERE user_id = p_user_id
                AND tenant_id = p_tenant_id
                AND accepted_at IS NOT NULL
            );
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER;
    """)
    
    # Create function to get current tenant from session variable
    op.execute("""
        CREATE OR REPLACE FUNCTION current_tenant_id()
        RETURNS uuid AS $$
        BEGIN
            RETURN NULLIF(current_setting('app.tenant_id', true), '')::uuid;
        EXCEPTION
            WHEN OTHERS THEN
                RETURN NULL;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)
    
    # Create function to get current user from session variable
    op.execute("""
        CREATE OR REPLACE FUNCTION current_user_id()
        RETURNS uuid AS $$
        BEGIN
            RETURN NULLIF(current_setting('app.user_id', true), '')::uuid;
        EXCEPTION
            WHEN OTHERS THEN
                RETURN NULL;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)
    
    # Enable Row Level Security on tenant_memberships
    op.execute("ALTER TABLE tenant_memberships ENABLE ROW LEVEL SECURITY;")
    
    # RLS policy: Users can only see their own memberships
    op.execute("""
        CREATE POLICY tenant_memberships_isolation ON tenant_memberships
        FOR ALL
        USING (user_id = current_user_id());
    """)
    
    # Create default tenant for existing users (migration helper)
    op.execute("""
        INSERT INTO tenants (name, slug, description)
        VALUES ('Default Organization', 'default', 'Default tenant for migrated users')
        ON CONFLICT DO NOTHING;
    """)
    
    # Migrate existing users to default tenant
    op.execute("""
        INSERT INTO tenant_memberships (user_id, tenant_id, role, accepted_at)
        SELECT 
            u.id,
            (SELECT id FROM tenants WHERE slug = 'default' LIMIT 1),
            'owner',
            NOW()
        FROM users u
        WHERE NOT EXISTS (
            SELECT 1 FROM tenant_memberships tm WHERE tm.user_id = u.id
        );
    """)


def downgrade() -> None:
    """Remove tenant membership system."""
    
    # Drop RLS policies
    op.execute("DROP POLICY IF EXISTS tenant_memberships_isolation ON tenant_memberships;")
    
    # Disable RLS
    op.execute("ALTER TABLE tenant_memberships DISABLE ROW LEVEL SECURITY;")
    
    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS current_user_id();")
    op.execute("DROP FUNCTION IF EXISTS current_tenant_id();")
    op.execute("DROP FUNCTION IF EXISTS has_tenant_access(uuid, uuid);")
    
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS update_tenant_memberships_updated_at ON tenant_memberships;")
    op.execute("DROP TRIGGER IF EXISTS update_tenants_updated_at ON tenants;")
    
    # Drop tables
    op.drop_table('tenant_memberships')
    op.drop_table('tenants')




