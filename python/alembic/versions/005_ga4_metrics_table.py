"""Create GA4 Raw Metrics Table with partitioning

Implements Task 7.2: Create GA4 Raw Metrics Table (Descriptive Analytics)

This migration:
- Creates partitioned table for GA4 metrics storage
- Supports dual-mode analytics: SQL queries + embeddings
- Includes descriptive_summary for natural language vectorization
- Implements monthly partitioning for efficient time-series queries
- Tenant isolation via RLS policies

Revision ID: 005_ga4_metrics_table
Revises: 004_add_tenant_columns
Create Date: 2026-01-02 13:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '005_ga4_metrics_table'
down_revision = '004_add_tenant_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create GA4 raw metrics table with monthly partitioning.
    
    Task 7.2 Implementation:
    - Stores raw GA4 API responses with JSONB flexibility
    - descriptive_summary field for embedding generation
    - Monthly partitions for efficient queries
    - Composite indexes for multi-tenant time-series analytics
    """
    
    # 1. Create main partitioned table
    op.execute("""
        CREATE TABLE ga4_metrics_raw (
            id BIGSERIAL,
            tenant_id UUID NOT NULL,
            user_id UUID NOT NULL,
            property_id TEXT NOT NULL,
            metric_date DATE NOT NULL,
            event_name TEXT,
            
            -- JSONB fields for flexible metric storage
            dimension_context JSONB NOT NULL DEFAULT '{}'::jsonb,
            metric_values JSONB NOT NULL DEFAULT '{}'::jsonb,
            
            -- Natural language summary for embedding generation (Task 8.2)
            -- Example: "On Jan 5, 2025, mobile users had 1,234 sessions with 56 conversions and 42.3% bounce rate for event page_view"
            descriptive_summary TEXT NOT NULL,
            
            -- Metadata
            synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            
            -- Foreign keys
            CONSTRAINT fk_ga4_metrics_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_ga4_metrics_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
            
            -- Primary key includes partition key
            PRIMARY KEY (id, metric_date)
        ) PARTITION BY RANGE (metric_date);
    """)
    
    # 2. Create partitions for current and next 12 months
    # Starting from January 2025
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    # Generate partitions for current year
    for month in range(1, 13):
        partition_name = f"ga4_metrics_{current_year}_{month:02d}"
        start_date = f"{current_year}-{month:02d}-01"
        
        # Calculate next month for partition boundary
        if month == 12:
            end_year = current_year + 1
            end_month = 1
        else:
            end_year = current_year
            end_month = month + 1
        
        end_date = f"{end_year}-{end_month:02d}-01"
        
        op.execute(f"""
            CREATE TABLE IF NOT EXISTS {partition_name}
            PARTITION OF ga4_metrics_raw
            FOR VALUES FROM ('{start_date}') TO ('{end_date}');
        """)
    
    # 3. Create indexes on main table (will be inherited by partitions)
    
    # Composite index for tenant + user + time-series queries
    op.execute("""
        CREATE INDEX idx_ga4_metrics_tenant_user_date 
        ON ga4_metrics_raw (tenant_id, user_id, metric_date DESC);
    """)
    
    # Index for tenant + property + date (GA4 property-specific queries)
    op.execute("""
        CREATE INDEX idx_ga4_metrics_tenant_property_date 
        ON ga4_metrics_raw (tenant_id, property_id, metric_date DESC);
    """)
    
    # GIN index for JSONB dimension_context searches
    op.execute("""
        CREATE INDEX idx_ga4_metrics_dimension_context 
        ON ga4_metrics_raw USING GIN (dimension_context);
    """)
    
    # GIN index for JSONB metric_values searches
    op.execute("""
        CREATE INDEX idx_ga4_metrics_values 
        ON ga4_metrics_raw USING GIN (metric_values);
    """)
    
    # Full-text search index on descriptive_summary for text queries
    op.execute("""
        CREATE INDEX idx_ga4_metrics_summary_fulltext 
        ON ga4_metrics_raw USING GIN (to_tsvector('english', descriptive_summary));
    """)
    
    # Event name index for filtering by GA4 event types
    op.execute("""
        CREATE INDEX idx_ga4_metrics_event_name 
        ON ga4_metrics_raw (tenant_id, event_name, metric_date DESC);
    """)
    
    # 4. Enable Row Level Security
    op.execute("ALTER TABLE ga4_metrics_raw ENABLE ROW LEVEL SECURITY;")
    
    # 5. Create RLS policy for tenant isolation
    op.execute("""
        CREATE POLICY ga4_metrics_tenant_isolation ON ga4_metrics_raw
        FOR ALL
        USING (
            tenant_id = current_tenant_id()
            AND
            user_id = current_user_id()
        );
    """)
    
    # 6. Create updated_at trigger
    op.execute("""
        CREATE TRIGGER update_ga4_metrics_updated_at 
        BEFORE UPDATE ON ga4_metrics_raw
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    
    # 7. Add comments for documentation
    op.execute("""
        COMMENT ON TABLE ga4_metrics_raw IS 
        'Stores raw GA4 metrics with descriptive summaries for dual-mode analytics.
        Partitioned by metric_date for efficient time-series queries.
        descriptive_summary field is used for embedding generation (Task 8.2).';
    """)
    
    op.execute("""
        COMMENT ON COLUMN ga4_metrics_raw.descriptive_summary IS 
        'Natural language transformation of metric data for embedding generation.
        Example: "On Jan 5, 2025, mobile users had 1,234 sessions with 56 conversions."
        This text is vectorized by Task 8.2 for semantic search.';
    """)
    
    op.execute("""
        COMMENT ON COLUMN ga4_metrics_raw.dimension_context IS 
        'JSONB storage for GA4 dimensions like device, location, source, etc.
        Example: {"device": "mobile", "country": "US", "source": "google"}';
    """)
    
    op.execute("""
        COMMENT ON COLUMN ga4_metrics_raw.metric_values IS 
        'JSONB storage for GA4 metrics like sessions, conversions, bounce_rate, etc.
        Example: {"sessions": 1234, "conversions": 56, "bounce_rate": 0.423}';
    """)
    
    # 8. Create helper function for automatic partition creation
    op.execute("""
        CREATE OR REPLACE FUNCTION create_ga4_metrics_partition(
            p_year INT,
            p_month INT
        ) RETURNS void AS $$
        DECLARE
            partition_name TEXT;
            start_date TEXT;
            end_date TEXT;
            end_year INT;
            end_month INT;
        BEGIN
            partition_name := 'ga4_metrics_' || p_year || '_' || LPAD(p_month::TEXT, 2, '0');
            start_date := p_year || '-' || LPAD(p_month::TEXT, 2, '0') || '-01';
            
            -- Calculate next month for end boundary
            IF p_month = 12 THEN
                end_year := p_year + 1;
                end_month := 1;
            ELSE
                end_year := p_year;
                end_month := p_month + 1;
            END IF;
            
            end_date := end_year || '-' || LPAD(end_month::TEXT, 2, '0') || '-01';
            
            -- Create partition if it doesn't exist
            EXECUTE format('
                CREATE TABLE IF NOT EXISTS %I
                PARTITION OF ga4_metrics_raw
                FOR VALUES FROM (%L) TO (%L)
            ', partition_name, start_date, end_date);
            
            RAISE NOTICE 'Created partition % for date range % to %', partition_name, start_date, end_date;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        COMMENT ON FUNCTION create_ga4_metrics_partition(INT, INT) IS 
        'Helper function to create new monthly partitions for ga4_metrics_raw table.
        Usage: SELECT create_ga4_metrics_partition(2026, 1); -- Creates partition for January 2026';
    """)


def downgrade() -> None:
    """Drop GA4 metrics table and related objects."""
    
    # Drop helper function
    op.execute("DROP FUNCTION IF EXISTS create_ga4_metrics_partition(INT, INT);")
    
    # Drop RLS policy
    op.execute("DROP POLICY IF EXISTS ga4_metrics_tenant_isolation ON ga4_metrics_raw;")
    
    # Drop trigger
    op.execute("DROP TRIGGER IF EXISTS update_ga4_metrics_updated_at ON ga4_metrics_raw;")
    
    # Disable RLS
    op.execute("ALTER TABLE ga4_metrics_raw DISABLE ROW LEVEL SECURITY;")
    
    # Drop main table (will cascade to all partitions)
    op.execute("DROP TABLE IF EXISTS ga4_metrics_raw CASCADE;")

