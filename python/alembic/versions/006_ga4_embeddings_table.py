"""Create GA4 Embeddings Table for vector similarity search

Implements Task 7.3: Create GA4 Embeddings Table (Predictive Analytics)

This migration:
- Creates table for storing 1536-dim embeddings from OpenAI text-embedding-3-small
- Supports time-series RAG pattern matching
- Includes temporal_metadata for context-aware retrieval
- Links back to source ga4_metrics_raw records
- Tenant isolation via RLS policies

Revision ID: 006_ga4_embeddings_table
Revises: 005_ga4_metrics_table
Create Date: 2026-01-02 13:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '006_ga4_embeddings_table'
down_revision = '005_ga4_metrics_table'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create GA4 embeddings table for vector similarity search.
    
    Task 7.3 Implementation:
    - Stores 1536-dim embeddings for semantic search
    - temporal_metadata enables time-aware RAG queries
    - Links to source_metric_id for data lineage
    - Prepares foundation for HNSW index (Task 7.4)
    """
    
    # 1. Create ga4_embeddings table
    op.create_table(
        'ga4_embeddings',
        
        # Primary key
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        
        # Multi-tenant isolation
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        
        # Content and embedding
        sa.Column('content', sa.Text(), nullable=False, comment='Original descriptive text from ga4_metrics_raw.descriptive_summary'),
        sa.Column('embedding', postgresql.ARRAY(sa.Float()), nullable=False, comment='1536-dim vector from OpenAI text-embedding-3-small'),
        
        # Temporal metadata for time-series RAG
        # Example: {"date_range": {"start": "2025-01-05", "end": "2025-01-05"}, "metric_type": "conversion_rate", "dimension_context": {"device": "mobile"}}
        sa.Column('temporal_metadata', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb"),
                 comment='Time-series context: date_range, metric_type, dimension_context'),
        
        # Link back to source metric for data lineage (Task P0-42)
        sa.Column('source_metric_id', sa.BigInteger(), nullable=True, comment='FK to ga4_metrics_raw.id for data provenance'),
        
        # Embedding metadata
        sa.Column('embedding_model', sa.String(100), nullable=False, server_default='text-embedding-3-small',
                 comment='OpenAI model used for embedding generation'),
        sa.Column('embedding_dimensions', sa.Integer(), nullable=False, server_default='1536',
                 comment='Vector dimensions (1536 for text-embedding-3-small)'),
        
        # Quality metrics (Task P0-5: Embedding Quality Assurance)
        sa.Column('quality_score', sa.Float(), nullable=True, comment='Embedding quality validation score (0.0-1.0)'),
        sa.Column('validation_errors', postgresql.JSONB(), nullable=True, server_default=sa.text("'[]'::jsonb"),
                 comment='Validation errors from quality checks'),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        
        # Foreign keys
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        # Note: source_metric_id FK is not enforced due to partitioned table complexity
        # Data lineage is tracked logically, not via database constraint
    )
    
    # 2. Create indexes for efficient queries
    
    # Composite index for tenant + user filtering
    op.create_index(
        'idx_ga4_embeddings_tenant_user',
        'ga4_embeddings',
        ['tenant_id', 'user_id']
    )
    
    # GIN index for temporal_metadata JSONB queries
    # Enables fast filtering by date_range, metric_type, dimension_context
    op.execute("""
        CREATE INDEX idx_ga4_embeddings_temporal_metadata 
        ON ga4_embeddings USING GIN (temporal_metadata);
    """)
    
    # Index on source_metric_id for data lineage queries
    op.create_index(
        'idx_ga4_embeddings_source_metric',
        'ga4_embeddings',
        ['source_metric_id']
    )
    
    # Index on created_at for temporal queries
    op.create_index(
        'idx_ga4_embeddings_created_at',
        'ga4_embeddings',
        ['tenant_id', 'created_at'],
        postgresql_using='btree'
    )
    
    # Full-text search on content for hybrid search (vector + keyword)
    op.execute("""
        CREATE INDEX idx_ga4_embeddings_content_fulltext 
        ON ga4_embeddings USING GIN (to_tsvector('english', content));
    """)
    
    # 3. Enable Row Level Security
    op.execute("ALTER TABLE ga4_embeddings ENABLE ROW LEVEL SECURITY;")
    
    # 4. Create RLS policy for tenant isolation
    # CRITICAL: This ensures vector searches respect tenant boundaries (Task P0-3)
    op.execute("""
        CREATE POLICY ga4_embeddings_tenant_isolation ON ga4_embeddings
        FOR ALL
        USING (
            tenant_id = current_tenant_id()
            AND
            user_id = current_user_id()
        );
    """)
    
    # 5. Create updated_at trigger
    op.execute("""
        CREATE TRIGGER update_ga4_embeddings_updated_at 
        BEFORE UPDATE ON ga4_embeddings
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    
    # 6. Add table and column comments for documentation
    op.execute("""
        COMMENT ON TABLE ga4_embeddings IS 
        'Stores 1536-dim embeddings for time-series RAG pattern matching.
        Embeddings generated from ga4_metrics_raw.descriptive_summary using OpenAI text-embedding-3-small.
        Enables queries like: "Is this pattern similar to last year?" or "Find similar conversion drops in Q1 2024"';
    """)
    
    op.execute("""
        COMMENT ON COLUMN ga4_embeddings.embedding IS 
        'Float array (1536 dimensions) from OpenAI text-embedding-3-small model.
        NOTE: Will be converted to pgvector VECTOR(1536) type in Task 7.4 with HNSW index for faster similarity search.';
    """)
    
    op.execute("""
        COMMENT ON COLUMN ga4_embeddings.temporal_metadata IS 
        'JSONB structure for time-series context:
        {
            "date_range": {"start": "2025-01-05", "end": "2025-01-05"},
            "metric_type": "conversion_rate",
            "dimension_context": {"device": "mobile", "country": "US"}
        }
        Enables time-aware RAG queries with date filtering.';
    """)
    
    op.execute("""
        COMMENT ON COLUMN ga4_embeddings.source_metric_id IS 
        'Logical FK to ga4_metrics_raw.id for data lineage.
        Enables tracing: embedding -> descriptive text -> raw GA4 metrics.
        Used by Task P0-42 (Source Citation Tracking).';
    """)
    
    # 7. Create helper function for semantic similarity search (basic version)
    # This will be replaced with HNSW-optimized version in Task 7.4
    op.execute("""
        CREATE OR REPLACE FUNCTION search_similar_ga4_patterns(
            p_query_embedding float[],
            p_tenant_id uuid,
            p_user_id uuid,
            p_match_count int DEFAULT 5,
            p_temporal_filter jsonb DEFAULT NULL
        ) RETURNS TABLE (
            id uuid,
            content text,
            similarity float,
            temporal_metadata jsonb,
            created_at timestamptz
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT 
                e.id,
                e.content,
                -- Cosine similarity calculation (temporary, will use <=> operator in Task 7.4)
                1 - (
                    (SELECT SUM((e.embedding[i] - p_query_embedding[i]) * (e.embedding[i] - p_query_embedding[i]))
                     FROM generate_series(1, array_length(e.embedding, 1)) AS i)
                    / (
                        SQRT((SELECT SUM(e.embedding[i] * e.embedding[i]) FROM generate_series(1, array_length(e.embedding, 1)) AS i)) *
                        SQRT((SELECT SUM(p_query_embedding[i] * p_query_embedding[i]) FROM generate_series(1, array_length(p_query_embedding, 1)) AS i))
                    )
                )::float AS similarity,
                e.temporal_metadata,
                e.created_at
            FROM ga4_embeddings e
            WHERE 
                e.tenant_id = p_tenant_id
                AND e.user_id = p_user_id
                AND (p_temporal_filter IS NULL OR e.temporal_metadata @> p_temporal_filter)
            ORDER BY similarity DESC
            LIMIT p_match_count;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)
    
    op.execute("""
        COMMENT ON FUNCTION search_similar_ga4_patterns IS 
        'Basic semantic similarity search for GA4 embeddings.
        This is a temporary implementation using float[] arrays.
        Task 7.4 will:
        1. Convert embedding column to pgvector VECTOR(1536) type
        2. Create HNSW index for 10x faster search
        3. Use <=> cosine distance operator instead of manual calculation
        
        Usage:
        SELECT * FROM search_similar_ga4_patterns(
            p_query_embedding := ARRAY[0.123, 0.456, ...], -- 1536 dims
            p_tenant_id := ''123e4567-e89b-12d3-a456-426614174000''::uuid,
            p_user_id := ''123e4567-e89b-12d3-a456-426614174001''::uuid,
            p_match_count := 10,
            p_temporal_filter := ''{"metric_type": "conversion_rate"}''::jsonb
        );';
    """)


def downgrade() -> None:
    """Drop GA4 embeddings table and related objects."""
    
    # Drop search function
    op.execute("DROP FUNCTION IF EXISTS search_similar_ga4_patterns(float[], uuid, uuid, int, jsonb);")
    
    # Drop trigger
    op.execute("DROP TRIGGER IF EXISTS update_ga4_embeddings_updated_at ON ga4_embeddings;")
    
    # Drop RLS policy
    op.execute("DROP POLICY IF EXISTS ga4_embeddings_tenant_isolation ON ga4_embeddings;")
    
    # Disable RLS
    op.execute("ALTER TABLE ga4_embeddings DISABLE ROW LEVEL SECURITY;")
    
    # Drop table
    op.drop_table('ga4_embeddings')

