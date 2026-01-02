/**
 * Report Version History Schema
 * 
 * Implements Task P0-36: Report Version History & Diff Viewer
 * 
 * Features:
 * - Store historical report versions
 * - Track changes over time
 * - Enable report comparison
 * - Audit trail for reports
 */

-- ========== Report Versions Table ==========

CREATE TABLE IF NOT EXISTS report_versions (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Report identification
    report_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    version_number INT NOT NULL,
    
    -- Content and metadata
    content_json JSONB NOT NULL,
    query TEXT NOT NULL,
    
    -- Timestamps and audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    
    -- Ensure unique versions per report
    UNIQUE(report_id, version_number)
);

-- ========== Indexes ==========

-- Lookup by report_id and tenant_id (most common query)
CREATE INDEX IF NOT EXISTS idx_report_versions_lookup 
ON report_versions(report_id, tenant_id, version_number DESC);

-- Lookup by tenant (for listing all reports)
CREATE INDEX IF NOT EXISTS idx_report_versions_tenant 
ON report_versions(tenant_id, created_at DESC);

-- Full-text search on query
CREATE INDEX IF NOT EXISTS idx_report_versions_query 
ON report_versions USING gin(to_tsvector('english', query));

-- GIN index on content_json for JSONB queries
CREATE INDEX IF NOT EXISTS idx_report_versions_content 
ON report_versions USING gin(content_json);

-- ========== Row-Level Security ==========

-- Enable RLS
ALTER TABLE report_versions ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only access reports from their tenant
CREATE POLICY report_versions_tenant_isolation ON report_versions
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Policy: Users can only view their own reports
CREATE POLICY report_versions_user_access ON report_versions
    FOR SELECT
    USING (created_by = current_setting('app.current_user_id')::uuid);

-- ========== Helper Functions ==========

-- Function to get latest version number for a report
CREATE OR REPLACE FUNCTION get_latest_report_version(p_report_id UUID)
RETURNS INT
LANGUAGE SQL
STABLE
AS $$
    SELECT COALESCE(MAX(version_number), 0)
    FROM report_versions
    WHERE report_id = p_report_id;
$$;

-- Function to create a new report version
CREATE OR REPLACE FUNCTION create_report_version(
    p_report_id UUID,
    p_tenant_id UUID,
    p_content_json JSONB,
    p_query TEXT,
    p_created_by UUID
)
RETURNS UUID
LANGUAGE PLPGSQL
AS $$
DECLARE
    v_version_number INT;
    v_new_id UUID;
BEGIN
    -- Get next version number
    v_version_number := get_latest_report_version(p_report_id) + 1;
    
    -- Insert new version
    INSERT INTO report_versions (
        report_id,
        tenant_id,
        version_number,
        content_json,
        query,
        created_by
    )
    VALUES (
        p_report_id,
        p_tenant_id,
        v_version_number,
        p_content_json,
        p_query,
        p_created_by
    )
    RETURNING id INTO v_new_id;
    
    RETURN v_new_id;
END;
$$;

-- Function to compare two report versions
CREATE OR REPLACE FUNCTION compare_report_versions(
    p_report_id UUID,
    p_version_1 INT,
    p_version_2 INT
)
RETURNS JSONB
LANGUAGE PLPGSQL
STABLE
AS $$
DECLARE
    v_content_1 JSONB;
    v_content_2 JSONB;
    v_diff JSONB;
BEGIN
    -- Get content for both versions
    SELECT content_json INTO v_content_1
    FROM report_versions
    WHERE report_id = p_report_id AND version_number = p_version_1;
    
    SELECT content_json INTO v_content_2
    FROM report_versions
    WHERE report_id = p_report_id AND version_number = p_version_2;
    
    -- Return both versions for comparison
    v_diff := jsonb_build_object(
        'version_1', v_content_1,
        'version_2', v_content_2,
        'keys_in_v1_only', (SELECT jsonb_object_keys(v_content_1) EXCEPT SELECT jsonb_object_keys(v_content_2)),
        'keys_in_v2_only', (SELECT jsonb_object_keys(v_content_2) EXCEPT SELECT jsonb_object_keys(v_content_1))
    );
    
    RETURN v_diff;
END;
$$;

-- ========== Automatic Cleanup ==========

-- Function to clean up old versions (keep last N versions per report)
CREATE OR REPLACE FUNCTION cleanup_old_report_versions(
    p_keep_count INT DEFAULT 10
)
RETURNS INT
LANGUAGE PLPGSQL
AS $$
DECLARE
    v_deleted_count INT := 0;
BEGIN
    -- Delete old versions, keeping the most recent N versions per report
    WITH versions_to_keep AS (
        SELECT id
        FROM (
            SELECT id, 
                   ROW_NUMBER() OVER (PARTITION BY report_id ORDER BY version_number DESC) as rn
            FROM report_versions
        ) ranked
        WHERE rn <= p_keep_count
    )
    DELETE FROM report_versions
    WHERE id NOT IN (SELECT id FROM versions_to_keep);
    
    GET DIAGNOSTICS v_deleted_count = ROW_COUNT;
    
    RETURN v_deleted_count;
END;
$$;

-- ========== Comments ==========

COMMENT ON TABLE report_versions IS 'Historical versions of generated reports for diff viewing and audit trail';
COMMENT ON COLUMN report_versions.report_id IS 'UUID identifying the logical report (multiple versions share same report_id)';
COMMENT ON COLUMN report_versions.version_number IS 'Incremental version number (1, 2, 3, ...)';
COMMENT ON COLUMN report_versions.content_json IS 'Full report content (charts, metrics, insights) in JSONB format';
COMMENT ON COLUMN report_versions.query IS 'User query that generated this report';

