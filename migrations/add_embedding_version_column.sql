-- Add Embedding Model Version Tracking
-- Implements Task P0-26: Embedding Model Version Migration Pipeline
--
-- Purpose: Enable blue-green embedding migration for zero-downtime model upgrades
-- (e.g., text-embedding-3-small -> text-embedding-3-large)

SET search_path TO app, public;

-- ============================================================
-- Add Model Version Column
-- ============================================================

DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'ga4_embeddings' 
        AND column_name = 'model_version'
    ) THEN
        ALTER TABLE ga4_embeddings 
        ADD COLUMN model_version TEXT NOT NULL DEFAULT 'v1.0';
        
        COMMENT ON COLUMN ga4_embeddings.model_version IS 
        'Version identifier for embedding model (e.g., v1.0=text-embedding-3-small, v2.0=text-embedding-3-large)';
    END IF;
END $$;

-- Add migration status tracking
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'ga4_embeddings' 
        AND column_name = 'migration_status'
    ) THEN
        ALTER TABLE ga4_embeddings 
        ADD COLUMN migration_status TEXT DEFAULT 'active' CHECK (
            migration_status IN ('active', 'migrating', 'deprecated', 'archived')
        );
        
        COMMENT ON COLUMN ga4_embeddings.migration_status IS 
        'Lifecycle status: active (current), migrating (transition), deprecated (old), archived (historical)';
    END IF;
END $$;

-- Add quality score for A/B testing
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'ga4_embeddings' 
        AND column_name = 'quality_score'
    ) THEN
        ALTER TABLE ga4_embeddings 
        ADD COLUMN quality_score FLOAT DEFAULT 1.0 CHECK (quality_score >= 0.0 AND quality_score <= 1.0);
        
        COMMENT ON COLUMN ga4_embeddings.quality_score IS 
        'Quality score from Task P0-5 quality checker (0.0-1.0, higher is better)';
    END IF;
END $$;

-- Add retrieval performance metrics
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'ga4_embeddings' 
        AND column_name = 'retrieval_metrics'
    ) THEN
        ALTER TABLE ga4_embeddings 
        ADD COLUMN retrieval_metrics JSONB DEFAULT '{}'::jsonb;
        
        COMMENT ON COLUMN ga4_embeddings.retrieval_metrics IS 
        'Retrieval performance metrics for A/B testing: {avg_similarity, retrieval_count, last_retrieved}';
    END IF;
END $$;

-- ============================================================
-- Indexes for Version Management
-- ============================================================

-- Index for version filtering (most common query)
CREATE INDEX IF NOT EXISTS idx_ga4_embeddings_model_version 
ON ga4_embeddings(model_version, migration_status);

-- Index for finding active embeddings
CREATE INDEX IF NOT EXISTS idx_ga4_embeddings_active 
ON ga4_embeddings(tenant_id, model_version) 
WHERE migration_status = 'active';

-- Index for quality score queries (A/B testing)
CREATE INDEX IF NOT EXISTS idx_ga4_embeddings_quality 
ON ga4_embeddings(model_version, quality_score DESC);

-- ============================================================
-- Version Migration Tracking Table
-- ============================================================

CREATE TABLE IF NOT EXISTS embedding_model_versions (
    id SERIAL PRIMARY KEY,
    version_name TEXT NOT NULL UNIQUE,
    model_name TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('testing', 'active', 'deprecated', 'retired')
    ),
    activated_at TIMESTAMPTZ,
    deprecated_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE embedding_model_versions IS 
'Tracks all embedding model versions and their lifecycle';

COMMENT ON COLUMN embedding_model_versions.version_name IS 
'Version identifier (e.g., v1.0, v2.0, v2.1)';

COMMENT ON COLUMN embedding_model_versions.model_name IS 
'OpenAI model name (e.g., text-embedding-3-small, text-embedding-3-large)';

COMMENT ON COLUMN embedding_model_versions.dimensions IS 
'Embedding dimensionality (e.g., 1536, 3072)';

COMMENT ON COLUMN embedding_model_versions.status IS 
'Lifecycle: testing (A/B), active (production), deprecated (transitioning out), retired (historical)';

-- Insert default version (current production)
INSERT INTO embedding_model_versions (
    version_name, 
    model_name, 
    dimensions, 
    status,
    activated_at,
    metadata
) VALUES (
    'v1.0',
    'text-embedding-3-small',
    1536,
    'active',
    NOW(),
    '{"description": "Initial production embedding model"}'::jsonb
) ON CONFLICT (version_name) DO NOTHING;

-- ============================================================
-- Version Migration Audit Log
-- ============================================================

CREATE TABLE IF NOT EXISTS embedding_migration_audit (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    source_version TEXT NOT NULL,
    target_version TEXT NOT NULL,
    total_embeddings INTEGER NOT NULL DEFAULT 0,
    migrated_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    avg_quality_improvement FLOAT,
    avg_retrieval_improvement FLOAT,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'in_progress', 'completed', 'failed', 'rolled_back')
    ),
    metadata JSONB DEFAULT '{}'::jsonb
);

COMMENT ON TABLE embedding_migration_audit IS 
'Audit trail for all embedding model migrations';

CREATE INDEX IF NOT EXISTS idx_migration_audit_tenant 
ON embedding_migration_audit(tenant_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_migration_audit_status 
ON embedding_migration_audit(status, started_at DESC);

-- ============================================================
-- Functions for Version Management
-- ============================================================

-- Function: Get active model version for tenant
CREATE OR REPLACE FUNCTION get_active_model_version()
RETURNS TEXT AS $$
BEGIN
    RETURN (
        SELECT version_name 
        FROM embedding_model_versions 
        WHERE status = 'active' 
        ORDER BY activated_at DESC 
        LIMIT 1
    );
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_active_model_version IS 
'Returns the currently active embedding model version';

-- Function: Get version statistics
CREATE OR REPLACE FUNCTION get_version_statistics(p_version TEXT)
RETURNS TABLE(
    total_embeddings BIGINT,
    avg_quality_score FLOAT,
    tenants_count BIGINT,
    created_at_range TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(*)::BIGINT AS total_embeddings,
        AVG(quality_score)::FLOAT AS avg_quality_score,
        COUNT(DISTINCT tenant_id)::BIGINT AS tenants_count,
        MIN(created_at)::TEXT || ' to ' || MAX(created_at)::TEXT AS created_at_range
    FROM ga4_embeddings
    WHERE model_version = p_version;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_version_statistics IS 
'Get statistics for a specific embedding model version';

-- Function: Compare two versions
CREATE OR REPLACE FUNCTION compare_embedding_versions(
    p_tenant_id UUID,
    p_version_a TEXT,
    p_version_b TEXT
)
RETURNS TABLE(
    version TEXT,
    count BIGINT,
    avg_quality FLOAT,
    avg_similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        model_version AS version,
        COUNT(*)::BIGINT AS count,
        AVG(quality_score)::FLOAT AS avg_quality,
        AVG((retrieval_metrics->>'avg_similarity')::FLOAT)::FLOAT AS avg_similarity
    FROM ga4_embeddings
    WHERE tenant_id = p_tenant_id
    AND model_version IN (p_version_a, p_version_b)
    GROUP BY model_version
    ORDER BY model_version;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION compare_embedding_versions IS 
'Compare quality and performance metrics between two model versions';

-- ============================================================
-- View: Current Version Summary
-- ============================================================

CREATE OR REPLACE VIEW embedding_version_summary AS
SELECT 
    emv.version_name,
    emv.model_name,
    emv.dimensions,
    emv.status,
    emv.activated_at,
    COUNT(DISTINCT e.tenant_id) AS tenant_count,
    COUNT(e.id) AS embedding_count,
    AVG(e.quality_score) AS avg_quality_score,
    MIN(e.created_at) AS first_embedding,
    MAX(e.created_at) AS last_embedding
FROM embedding_model_versions emv
LEFT JOIN ga4_embeddings e ON e.model_version = emv.version_name
GROUP BY emv.version_name, emv.model_name, emv.dimensions, emv.status, emv.activated_at
ORDER BY emv.activated_at DESC;

COMMENT ON VIEW embedding_version_summary IS 
'Summary of all embedding model versions with usage statistics';

-- ============================================================
-- Trigger: Update timestamp on version updates
-- ============================================================

CREATE OR REPLACE FUNCTION update_embedding_version_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_update_embedding_version_timestamp ON embedding_model_versions;

CREATE TRIGGER trg_update_embedding_version_timestamp
    BEFORE UPDATE ON embedding_model_versions
    FOR EACH ROW
    EXECUTE FUNCTION update_embedding_version_timestamp();

-- ============================================================
-- Success Message
-- ============================================================

SELECT 'Embedding Model Version Tracking Added Successfully' AS status;
SELECT * FROM embedding_version_summary;

