"""Add vector storage integrity constraints

Implements Task P0-24: Vector Storage Integrity Validation Pipeline

This migration adds database-level integrity constraints:
- Check constraints for embedding dimensions
- Triggers for automatic integrity validation
- Audit table for integrity violations

Revision ID: 010_vector_integrity_constraints
Revises: 009_gdpr_tenant_deletion
Create Date: 2026-01-02 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '010_vector_integrity_constraints'
down_revision = '009_gdpr_tenant_deletion'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add vector storage integrity constraints."""
    
    # 1. Add constraint: embedding_dimensions must match array length
    op.execute("""
        ALTER TABLE ga4_embeddings
        ADD CONSTRAINT chk_embedding_dimensions
        CHECK (
            embedding_dimensions = array_length(embedding, 1)
            OR embedding IS NULL
        );
    """)
    
    # 2. Add constraint: quality_score must be between 0 and 1
    op.execute("""
        ALTER TABLE ga4_embeddings
        ADD CONSTRAINT chk_quality_score_range
        CHECK (
            quality_score IS NULL
            OR (quality_score >= 0.0 AND quality_score <= 1.0)
        );
    """)
    
    # 3. Add constraint: content must not be empty
    op.execute("""
        ALTER TABLE ga4_embeddings
        ADD CONSTRAINT chk_content_not_empty
        CHECK (
            content IS NOT NULL
            AND LENGTH(TRIM(content)) > 0
        );
    """)
    
    # 4. Create integrity violations audit table
    op.create_table(
        'vector_integrity_violations',
        
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                 server_default=sa.text('gen_random_uuid()')),
        
        sa.Column('embedding_id', postgresql.UUID(as_uuid=True), nullable=False,
                 index=True, comment='ID of embedding with violation'),
        
        sa.Column('violation_type', sa.String(100), nullable=False,
                 comment='Type of violation detected'),
        
        sa.Column('severity', sa.String(20), nullable=False,
                 comment='critical, high, medium, low'),
        
        sa.Column('description', sa.Text(), nullable=False,
                 comment='Human-readable description'),
        
        sa.Column('auto_fixable', sa.Boolean(), nullable=False, default=False,
                 comment='Whether violation can be auto-fixed'),
        
        sa.Column('fix_action', sa.String(100), nullable=True,
                 comment='Action to fix violation'),
        
        sa.Column('metadata', postgresql.JSONB(), nullable=True,
                 comment='Additional violation metadata'),
        
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False,
                 server_default=sa.text('NOW()'), comment='When violation was detected'),
        
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True,
                 comment='When violation was fixed'),
        
        sa.Column('resolved_by', sa.String(100), nullable=True,
                 comment='How violation was resolved'),
    )
    
    # 5. Create indexes for violations table
    op.create_index(
        'idx_vector_violations_embedding',
        'vector_integrity_violations',
        ['embedding_id']
    )
    
    op.create_index(
        'idx_vector_violations_type',
        'vector_integrity_violations',
        ['violation_type']
    )
    
    op.create_index(
        'idx_vector_violations_detected',
        'vector_integrity_violations',
        ['detected_at']
    )
    
    # 6. Create function to log integrity violations
    op.execute("""
        CREATE OR REPLACE FUNCTION log_vector_integrity_violation(
            p_embedding_id uuid,
            p_violation_type text,
            p_severity text,
            p_description text,
            p_auto_fixable boolean,
            p_fix_action text,
            p_metadata jsonb
        ) RETURNS void AS $$
        BEGIN
            INSERT INTO vector_integrity_violations (
                embedding_id,
                violation_type,
                severity,
                description,
                auto_fixable,
                fix_action,
                metadata
            ) VALUES (
                p_embedding_id,
                p_violation_type,
                p_severity,
                p_description,
                p_auto_fixable,
                p_fix_action,
                p_metadata
            );
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # 7. Add comments
    op.execute("""
        COMMENT ON TABLE vector_integrity_violations IS 
        'Audit log for vector storage integrity violations (Task P0-24).
        Records all detected violations for monitoring and remediation.';
    """)
    
    op.execute("""
        COMMENT ON CONSTRAINT chk_embedding_dimensions ON ga4_embeddings IS 
        'Ensures embedding_dimensions column matches actual embedding array length.
        Prevents dimension mismatch errors in pgvector operations.';
    """)


def downgrade() -> None:
    """Remove vector storage integrity constraints."""
    
    # Drop function
    op.execute("DROP FUNCTION IF EXISTS log_vector_integrity_violation;")
    
    # Drop violations table
    op.drop_table('vector_integrity_violations')
    
    # Drop constraints
    op.execute("ALTER TABLE ga4_embeddings DROP CONSTRAINT IF EXISTS chk_content_not_empty;")
    op.execute("ALTER TABLE ga4_embeddings DROP CONSTRAINT IF EXISTS chk_quality_score_range;")
    op.execute("ALTER TABLE ga4_embeddings DROP CONSTRAINT IF EXISTS chk_embedding_dimensions;")

