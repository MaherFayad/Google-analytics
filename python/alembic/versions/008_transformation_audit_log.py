"""Add GA4 transformation audit logging

Implements Task P0-25: GA4 Transformation Audit Log

This migration creates audit trail for GA4 JSON → text transformations:
- Tracks input JSON and output text for every transformation
- Enables debugging "why did the LLM get this data?" questions
- Version tracking for transformation logic changes
- Tenant-isolated audit logs

Implements Task P0-49: Transformation Trigger Implementation
- Database-level enforcement via AFTER INSERT trigger
- Automatic logging within same transaction
- Cannot be bypassed by application code

Revision ID: 008_transformation_audit_log
Revises: 007_hnsw_vector_indexes
Create Date: 2026-01-02 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '008_transformation_audit_log'
down_revision = '007_hnsw_vector_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create transformation audit log table and trigger.
    
    Task P0-25 & P0-49 Implementation:
    - Audit table for transformation tracking
    - Automatic trigger for database-level enforcement
    - Version tracking for transformation logic changes
    """
    
    # 1. Create transformation audit table
    op.create_table(
        'ga4_transformation_audit',
        
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        
        # Multi-tenant isolation
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        
        # Link to source metric
        sa.Column(
            'source_metric_id',
            sa.BigInteger(),
            nullable=False,
            index=True,
            comment='FK to ga4_metrics_raw.id (logical, not enforced due to partitioning)'
        ),
        
        # Transformation data
        sa.Column(
            'input_json',
            postgresql.JSONB(),
            nullable=False,
            comment='Original GA4 JSON (dimension_context + metric_values merged)'
        ),
        
        sa.Column(
            'output_text',
            sa.Text(),
            nullable=False,
            comment='Generated descriptive summary text'
        ),
        
        # Version tracking
        sa.Column(
            'transformation_version',
            sa.String(50),
            nullable=False,
            server_default='v1.0.0',
            comment='Transformation logic version for debugging'
        ),
        
        # Metadata
        sa.Column(
            'property_id',
            sa.String(100),
            nullable=True,
            comment='GA4 property ID'
        ),
        
        sa.Column(
            'metric_date',
            sa.Date(),
            nullable=True,
            index=True,
            comment='Date of metric for temporal queries'
        ),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        
        # Foreign keys
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    )
    
    # 2. Create indexes for efficient queries
    
    # Composite index for tenant + source metric lookups
    op.create_index(
        'idx_audit_tenant_metric',
        'ga4_transformation_audit',
        ['tenant_id', 'source_metric_id']
    )
    
    # Index for version queries
    op.create_index(
        'idx_audit_version',
        'ga4_transformation_audit',
        ['transformation_version', 'created_at']
    )
    
    # Index for temporal queries
    op.create_index(
        'idx_audit_date',
        'ga4_transformation_audit',
        ['tenant_id', 'metric_date']
    )
    
    # Full-text search on output_text
    op.execute("""
        CREATE INDEX idx_audit_output_fulltext 
        ON ga4_transformation_audit USING GIN (to_tsvector('english', output_text));
    """)
    
    # 3. Enable Row Level Security
    op.execute("ALTER TABLE ga4_transformation_audit ENABLE ROW LEVEL SECURITY;")
    
    # 4. Create RLS policy
    op.execute("""
        CREATE POLICY ga4_audit_tenant_isolation ON ga4_transformation_audit
        FOR ALL
        USING (tenant_id = current_tenant_id());
    """)
    
    # 5. Create trigger function for automatic audit logging (Task P0-49)
    op.execute("""
        CREATE OR REPLACE FUNCTION log_ga4_transformation_audit()
        RETURNS TRIGGER AS $$
        DECLARE
            transformation_version TEXT;
        BEGIN
            -- Get transformation version from session variable (default v1.0.0)
            BEGIN
                transformation_version := current_setting('app.transformation_version', true);
                IF transformation_version IS NULL OR transformation_version = '' THEN
                    transformation_version := 'v1.0.0';
                END IF;
            EXCEPTION
                WHEN OTHERS THEN
                    transformation_version := 'v1.0.0';
            END;
            
            -- Insert audit record
            INSERT INTO ga4_transformation_audit (
                tenant_id,
                source_metric_id,
                input_json,
                output_text,
                transformation_version,
                property_id,
                metric_date
            ) VALUES (
                NEW.tenant_id,
                NEW.id,
                -- Merge dimension_context and metric_values
                NEW.dimension_context || NEW.metric_values,
                NEW.descriptive_summary,
                transformation_version,
                NEW.property_id,
                NEW.metric_date
            );
            
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        COMMENT ON FUNCTION log_ga4_transformation_audit() IS 
        'Automatically log GA4 transformations to audit table.
        Triggered AFTER INSERT on ga4_metrics_raw.
        Ensures complete audit trail for all transformations.
        
        Task P0-49 Implementation:
        - Database-level enforcement (cannot be bypassed)
        - Transaction-level atomicity
        - Automatic version tracking';
    """)
    
    # 6. Create AFTER INSERT trigger on ga4_metrics_raw
    op.execute("""
        CREATE TRIGGER log_transformation_audit_trigger
        AFTER INSERT ON ga4_metrics_raw
        FOR EACH ROW
        EXECUTE FUNCTION log_ga4_transformation_audit();
    """)
    
    op.execute("""
        COMMENT ON TRIGGER log_transformation_audit_trigger ON ga4_metrics_raw IS 
        'Automatically logs every GA4 transformation to audit table.
        Task P0-49: Database-level enforcement prevents bypass.';
    """)
    
    # 7. Add table comments
    op.execute("""
        COMMENT ON TABLE ga4_transformation_audit IS 
        'Audit log for GA4 JSON → text transformations.
        
        Task P0-25 & P0-49 Implementation:
        - Complete audit trail for debugging data quality issues
        - Version tracking for transformation logic changes
        - Enables answering "why did the LLM get this data?" questions
        
        Example query:
        SELECT * FROM ga4_transformation_audit 
        WHERE source_metric_id = 12345;
        
        This shows the exact transformation that produced the text
        used for embedding generation.';
    """)
    
    # 8. Create helper function to get transformation history
    op.execute("""
        CREATE OR REPLACE FUNCTION get_transformation_history(
            p_source_metric_id bigint,
            p_tenant_id uuid
        ) RETURNS TABLE (
            audit_id bigint,
            input_json jsonb,
            output_text text,
            transformation_version text,
            created_at timestamptz
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT 
                a.id,
                a.input_json,
                a.output_text,
                a.transformation_version,
                a.created_at
            FROM ga4_transformation_audit a
            WHERE 
                a.source_metric_id = p_source_metric_id
                AND a.tenant_id = p_tenant_id
            ORDER BY a.created_at DESC;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)
    
    op.execute("""
        COMMENT ON FUNCTION get_transformation_history IS 
        'Get transformation history for a specific metric.
        
        Usage:
        SELECT * FROM get_transformation_history(
            p_source_metric_id := 12345,
            p_tenant_id := ''123e4567-e89b-12d3-a456-426614174000''::uuid
        );
        
        Shows all transformations for a metric (useful if logic changes over time).';
    """)
    
    # 9. Create stats function for monitoring
    op.execute("""
        CREATE OR REPLACE FUNCTION ga4_transformation_audit_stats(
            p_tenant_id uuid DEFAULT NULL
        ) RETURNS TABLE (
            total_transformations bigint,
            transformations_by_version jsonb,
            earliest_transformation timestamptz,
            latest_transformation timestamptz
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT 
                COUNT(*)::bigint AS total_transformations,
                jsonb_object_agg(
                    transformation_version,
                    version_count
                ) AS transformations_by_version,
                MIN(created_at) AS earliest_transformation,
                MAX(created_at) AS latest_transformation
            FROM (
                SELECT 
                    transformation_version,
                    COUNT(*)::int AS version_count,
                    MIN(created_at) AS created_at
                FROM ga4_transformation_audit
                WHERE p_tenant_id IS NULL OR tenant_id = p_tenant_id
                GROUP BY transformation_version
            ) version_counts;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)
    
    op.execute("""
        COMMENT ON FUNCTION ga4_transformation_audit_stats IS 
        'Get transformation audit statistics.
        
        Usage:
        SELECT * FROM ga4_transformation_audit_stats(); -- All tenants
        SELECT * FROM ga4_transformation_audit_stats(''123e4567-e89b-12d3-a456-426614174000''::uuid); -- Specific tenant
        
        Returns version distribution and date ranges.';
    """)


def downgrade() -> None:
    """Drop transformation audit infrastructure."""
    
    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS ga4_transformation_audit_stats(uuid);")
    op.execute("DROP FUNCTION IF EXISTS get_transformation_history(bigint, uuid);")
    
    # Drop trigger
    op.execute("DROP TRIGGER IF EXISTS log_transformation_audit_trigger ON ga4_metrics_raw;")
    
    # Drop trigger function
    op.execute("DROP FUNCTION IF EXISTS log_ga4_transformation_audit();")
    
    # Drop RLS policy
    op.execute("DROP POLICY IF EXISTS ga4_audit_tenant_isolation ON ga4_transformation_audit;")
    
    # Disable RLS
    op.execute("ALTER TABLE ga4_transformation_audit DISABLE ROW LEVEL SECURITY;")
    
    # Drop table
    op.drop_table('ga4_transformation_audit')

