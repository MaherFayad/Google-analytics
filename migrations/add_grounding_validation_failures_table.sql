-- Context Grounding Validation Failures Tracking
-- Implements Task P0-45: Context Grounding Checker

SET search_path TO app, public;

-- ============================================================
-- Grounding Validation Failures Table
-- ============================================================

CREATE TABLE IF NOT EXISTS grounding_validation_failures (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    query_id UUID NOT NULL,
    query_text TEXT NOT NULL,
    llm_response TEXT NOT NULL,
    retrieval_context JSONB NOT NULL,
    ungrounded_claims JSONB NOT NULL DEFAULT '[]'::jsonb,
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    validation_score FLOAT,  -- 0.0 = completely ungrounded, 1.0 = fully grounded
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolution_action TEXT,  -- 'retry', 'manual_review', 'false_positive'
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE grounding_validation_failures IS 
'Tracks instances where LLM responses contained ungrounded claims (hallucinations)';

COMMENT ON COLUMN grounding_validation_failures.ungrounded_claims IS 
'JSON array of claims not supported by retrieval context: [{"claim": "...", "confidence": 0.0}]';

COMMENT ON COLUMN grounding_validation_failures.validation_score IS 
'Percentage of claims that were grounded (0-1): 0.8 means 80% of claims had supporting evidence';

-- Indexes
CREATE INDEX IF NOT EXISTS idx_grounding_failures_tenant_time 
ON grounding_validation_failures(tenant_id, detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_grounding_failures_severity 
ON grounding_validation_failures(severity, detected_at DESC)
WHERE resolved_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_grounding_failures_query 
ON grounding_validation_failures(query_id);

-- GIN index for searching ungrounded claims
CREATE INDEX IF NOT EXISTS idx_grounding_failures_claims 
ON grounding_validation_failures USING GIN (ungrounded_claims jsonb_path_ops);

-- Row Level Security
ALTER TABLE grounding_validation_failures ENABLE ROW LEVEL SECURITY;

CREATE POLICY IF NOT EXISTS "Tenant isolation for grounding failures"
  ON grounding_validation_failures FOR ALL
  USING (tenant_id = (current_setting('app.current_tenant_id', true))::uuid);

-- ============================================================
-- View: Recent Unresolved Grounding Failures
-- ============================================================

CREATE OR REPLACE VIEW recent_grounding_failures AS
SELECT 
    id,
    tenant_id,
    query_id,
    query_text,
    SUBSTRING(llm_response FROM 1 FOR 200) AS llm_response_preview,
    jsonb_array_length(ungrounded_claims) AS ungrounded_claim_count,
    severity,
    validation_score,
    detected_at,
    EXTRACT(EPOCH FROM (NOW() - detected_at)) / 3600 AS hours_since_detection
FROM grounding_validation_failures
WHERE resolved_at IS NULL
AND detected_at > NOW() - INTERVAL '7 days'
ORDER BY detected_at DESC;

COMMENT ON VIEW recent_grounding_failures IS 
'Shows unresolved grounding failures from the past 7 days for admin monitoring';

-- ============================================================
-- Function: Get Grounding Failure Stats
-- ============================================================

CREATE OR REPLACE FUNCTION get_grounding_failure_stats(
    p_tenant_id UUID,
    p_days INT DEFAULT 7
)
RETURNS TABLE(
    total_failures INT,
    critical_failures INT,
    avg_validation_score FLOAT,
    resolution_rate FLOAT,
    most_common_failure_type TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(*)::INT AS total_failures,
        COUNT(*) FILTER (WHERE severity = 'critical')::INT AS critical_failures,
        AVG(validation_score) AS avg_validation_score,
        (COUNT(*) FILTER (WHERE resolved_at IS NOT NULL)::FLOAT / NULLIF(COUNT(*), 0)) * 100 AS resolution_rate,
        (
            SELECT jsonb_object_keys(ungrounded_claims->0)
            FROM grounding_validation_failures
            WHERE tenant_id = p_tenant_id
            AND detected_at > NOW() - (p_days || ' days')::INTERVAL
            LIMIT 1
        ) AS most_common_failure_type
    FROM grounding_validation_failures
    WHERE tenant_id = p_tenant_id
    AND detected_at > NOW() - (p_days || ' days')::INTERVAL;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_grounding_failure_stats IS 
'Get grounding failure statistics for a tenant over the past N days';

-- ============================================================
-- Success Message
-- ============================================================

SELECT 'Grounding Validation Failures Tracking Created Successfully' AS status;


