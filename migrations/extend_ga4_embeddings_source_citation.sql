-- Extend GA4 Embeddings with Source Citation Tracking
-- Implements Task P0-42: Source Citation Tracking for RAG Provenance

SET search_path TO app, public;

-- ============================================================
-- Add Source Citation Columns
-- ============================================================

-- Note: This assumes ga4_embeddings table exists from Task 7.3
-- If not, this migration will fail and should be run after that task

-- Add source_metric_id column (single source reference)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'ga4_embeddings' 
        AND column_name = 'source_metric_id'
    ) THEN
        ALTER TABLE ga4_embeddings 
        ADD COLUMN source_metric_id BIGINT;
        
        COMMENT ON COLUMN ga4_embeddings.source_metric_id IS 
        'Foreign key to ga4_metrics_raw.id - tracks which raw metric this embedding came from';
    END IF;
END $$;

-- Add source_metric_ids array (for embeddings derived from multiple metrics)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'ga4_embeddings' 
        AND column_name = 'source_metric_ids'
    ) THEN
        ALTER TABLE ga4_embeddings 
        ADD COLUMN source_metric_ids BIGINT[] NOT NULL DEFAULT '{}';
        
        COMMENT ON COLUMN ga4_embeddings.source_metric_ids IS 
        'Array of ga4_metrics_raw.id values - for embeddings derived from multiple metrics';
    END IF;
END $$;

-- Add transformation metadata
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'ga4_embeddings' 
        AND column_name = 'transformation_version'
    ) THEN
        ALTER TABLE ga4_embeddings 
        ADD COLUMN transformation_version TEXT NOT NULL DEFAULT 'v1.0.0';
        
        COMMENT ON COLUMN ga4_embeddings.transformation_version IS 
        'Version of transformation logic used to generate descriptive text';
    END IF;
END $$;

-- Add source metadata JSONB
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'ga4_embeddings' 
        AND column_name = 'source_metadata'
    ) THEN
        ALTER TABLE ga4_embeddings 
        ADD COLUMN source_metadata JSONB DEFAULT '{}'::jsonb;
        
        COMMENT ON COLUMN ga4_embeddings.source_metadata IS 
        'Additional metadata about source metrics (property_id, date_range, device, etc.)';
    END IF;
END $$;

-- ============================================================
-- Foreign Key Constraints
-- ============================================================

-- Note: Foreign key to ga4_metrics_raw requires that table to exist
-- This is created in Task 7.2

-- Add foreign key for source_metric_id (if ga4_metrics_raw exists)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'ga4_metrics_raw') THEN
        -- Check if constraint doesn't already exist
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE constraint_name = 'fk_ga4_embeddings_source_metric'
        ) THEN
            ALTER TABLE ga4_embeddings
            ADD CONSTRAINT fk_ga4_embeddings_source_metric
            FOREIGN KEY (source_metric_id) 
            REFERENCES ga4_metrics_raw(id)
            ON DELETE SET NULL;  -- Don't cascade delete embeddings if metric deleted
        END IF;
    ELSE
        RAISE NOTICE 'Table ga4_metrics_raw does not exist yet. Run migration 005_ga4_metrics_table.py first.';
    END IF;
END $$;

-- ============================================================
-- Indexes for Performance
-- ============================================================

-- Index on source_metric_id for fast lookups
CREATE INDEX IF NOT EXISTS idx_ga4_embeddings_source_metric 
ON ga4_embeddings(source_metric_id) 
WHERE source_metric_id IS NOT NULL;

-- Index on source_metric_ids array for "contains" queries
CREATE INDEX IF NOT EXISTS idx_ga4_embeddings_source_metric_ids 
ON ga4_embeddings USING GIN (source_metric_ids);

-- Index on transformation_version for A/B testing
CREATE INDEX IF NOT EXISTS idx_ga4_embeddings_transformation_version 
ON ga4_embeddings(transformation_version);

-- Composite index for source metadata queries
CREATE INDEX IF NOT EXISTS idx_ga4_embeddings_source_metadata 
ON ga4_embeddings USING GIN (source_metadata jsonb_path_ops);

-- ============================================================
-- View: Embeddings with Source Metrics (for easy querying)
-- ============================================================

CREATE OR REPLACE VIEW embeddings_with_sources AS
SELECT 
    e.id AS embedding_id,
    e.tenant_id,
    e.content AS embedding_content,
    e.embedding,
    e.temporal_metadata,
    e.transformation_version,
    e.source_metric_id,
    e.source_metric_ids,
    e.source_metadata,
    e.created_at AS embedding_created_at,
    -- Join with source metric (if exists)
    m.id AS metric_id,
    m.property_id,
    m.metric_date,
    m.event_name,
    m.dimension_context AS metric_dimensions,
    m.metric_values,
    m.descriptive_summary AS metric_summary,
    m.created_at AS metric_created_at
FROM ga4_embeddings e
LEFT JOIN ga4_metrics_raw m ON e.source_metric_id = m.id;

COMMENT ON VIEW embeddings_with_sources IS 
'Convenient view joining embeddings with their source metrics for citation tracking';

-- ============================================================
-- Function: Get Source Citations for Embedding
-- ============================================================

CREATE OR REPLACE FUNCTION get_embedding_source_citations(
    p_embedding_id UUID
)
RETURNS TABLE(
    metric_id BIGINT,
    property_id TEXT,
    metric_date DATE,
    event_name TEXT,
    dimensions JSONB,
    metrics JSONB,
    descriptive_summary TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        m.id AS metric_id,
        m.property_id,
        m.metric_date,
        m.event_name,
        m.dimension_context AS dimensions,
        m.metric_values AS metrics,
        m.descriptive_summary
    FROM ga4_embeddings e
    JOIN ga4_metrics_raw m ON m.id = ANY(e.source_metric_ids)
    WHERE e.id = p_embedding_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_embedding_source_citations IS 
'Retrieve all source citations for a given embedding ID';

-- ============================================================
-- Function: Validate Citation Integrity
-- ============================================================

CREATE OR REPLACE FUNCTION validate_citation_integrity()
RETURNS TABLE(
    embedding_id UUID,
    issue TEXT
) AS $$
BEGIN
    -- Find embeddings without source citations
    RETURN QUERY
    SELECT 
        id AS embedding_id,
        'No source citations' AS issue
    FROM ga4_embeddings
    WHERE source_metric_id IS NULL 
    AND (source_metric_ids IS NULL OR array_length(source_metric_ids, 1) IS NULL)
    AND created_at > NOW() - INTERVAL '7 days';  -- Only check recent embeddings
    
    -- Find embeddings with broken foreign keys
    RETURN QUERY
    SELECT 
        e.id AS embedding_id,
        'Broken source reference: ' || e.source_metric_id AS issue
    FROM ga4_embeddings e
    LEFT JOIN ga4_metrics_raw m ON e.source_metric_id = m.id
    WHERE e.source_metric_id IS NOT NULL
    AND m.id IS NULL;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION validate_citation_integrity IS 
'Check for embeddings with missing or broken source citations';

-- ============================================================
-- Constraint: Enforce Citation Requirement (Optional)
-- ============================================================

-- Note: This constraint ensures every new embedding has a source citation
-- Uncomment if you want strict enforcement

-- ALTER TABLE ga4_embeddings 
-- ADD CONSTRAINT check_has_source_citation
-- CHECK (
--     source_metric_id IS NOT NULL 
--     OR (source_metric_ids IS NOT NULL AND array_length(source_metric_ids, 1) > 0)
-- );

-- ============================================================
-- Success Message
-- ============================================================

SELECT 'GA4 Embeddings Source Citation Tracking Extended Successfully' AS status;

