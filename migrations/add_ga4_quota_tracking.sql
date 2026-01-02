-- GA4 API Quota Tracking Schema
-- Implements Task 15: Tenant-Aware Quota Management System

SET search_path TO app, public;

-- ============================================================
-- GA4 API Quota Usage Table
-- ============================================================

CREATE TABLE IF NOT EXISTS ga4_api_quota_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    property_id TEXT NOT NULL,
    quota_window_start TIMESTAMPTZ NOT NULL,
    quota_window_end TIMESTAMPTZ NOT NULL,
    window_type TEXT NOT NULL CHECK (window_type IN ('hourly', 'daily')),
    requests_made INT DEFAULT 0,
    requests_limit INT NOT NULL,
    last_request_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, property_id, quota_window_start, window_type)
);

COMMENT ON TABLE ga4_api_quota_usage IS 'Tracks GA4 API quota usage per tenant with hourly and daily windows';
COMMENT ON COLUMN ga4_api_quota_usage.window_type IS 'Type of quota window: hourly (50 requests) or daily (200 requests)';
COMMENT ON COLUMN ga4_api_quota_usage.requests_made IS 'Number of GA4 API requests made in this window';
COMMENT ON COLUMN ga4_api_quota_usage.requests_limit IS 'Maximum requests allowed in this window';

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_ga4_quota_tenant_window 
ON ga4_api_quota_usage(tenant_id, quota_window_start DESC, window_type);

CREATE INDEX IF NOT EXISTS idx_ga4_quota_property 
ON ga4_api_quota_usage(property_id, quota_window_start DESC);

CREATE INDEX IF NOT EXISTS idx_ga4_quota_window_end 
ON ga4_api_quota_usage(quota_window_end) 
WHERE quota_window_end > NOW();

-- ============================================================
-- GA4 API Request Log (for audit and analytics)
-- ============================================================

CREATE TABLE IF NOT EXISTS ga4_api_request_log (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    property_id TEXT NOT NULL,
    user_id UUID,
    request_type TEXT NOT NULL,  -- 'runReport', 'batchRunReports', etc.
    dimensions JSONB DEFAULT '[]'::jsonb,
    metrics JSONB DEFAULT '[]'::jsonb,
    date_range JSONB,
    status TEXT NOT NULL CHECK (status IN ('success', 'error', 'rate_limited', 'quota_exceeded')),
    response_time_ms INT,
    error_message TEXT,
    requested_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE ga4_api_request_log IS 'Audit log of all GA4 API requests for monitoring and debugging';

-- Partition by month for performance
-- Note: This is a simplified version. In production, use time-series partitioning like ga4_events
CREATE INDEX IF NOT EXISTS idx_ga4_request_log_tenant_time 
ON ga4_api_request_log(tenant_id, requested_at DESC);

CREATE INDEX IF NOT EXISTS idx_ga4_request_log_status 
ON ga4_api_request_log(status, requested_at DESC);

-- ============================================================
-- Row Level Security (RLS)
-- ============================================================

ALTER TABLE ga4_api_quota_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY IF NOT EXISTS "Tenant isolation for GA4 quota usage"
  ON ga4_api_quota_usage FOR ALL
  USING (tenant_id = (current_setting('app.current_tenant_id', true))::uuid);

ALTER TABLE ga4_api_request_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY IF NOT EXISTS "Tenant isolation for GA4 request log"
  ON ga4_api_request_log FOR ALL
  USING (tenant_id = (current_setting('app.current_tenant_id', true))::uuid);

-- ============================================================
-- Function: Get Current Quota Usage
-- ============================================================

CREATE OR REPLACE FUNCTION get_current_quota_usage(
    p_tenant_id UUID,
    p_property_id TEXT,
    p_window_type TEXT DEFAULT 'hourly'
)
RETURNS TABLE(
    requests_made INT,
    requests_limit INT,
    requests_remaining INT,
    window_start TIMESTAMPTZ,
    window_end TIMESTAMPTZ,
    utilization_percent FLOAT
) AS $$
DECLARE
    v_window_start TIMESTAMPTZ;
    v_window_end TIMESTAMPTZ;
BEGIN
    -- Calculate window boundaries
    IF p_window_type = 'hourly' THEN
        v_window_start := DATE_TRUNC('hour', NOW());
        v_window_end := v_window_start + INTERVAL '1 hour';
    ELSE  -- daily
        v_window_start := DATE_TRUNC('day', NOW());
        v_window_end := v_window_start + INTERVAL '1 day';
    END IF;
    
    RETURN QUERY
    SELECT 
        COALESCE(q.requests_made, 0) AS requests_made,
        COALESCE(q.requests_limit, CASE WHEN p_window_type = 'hourly' THEN 50 ELSE 200 END) AS requests_limit,
        COALESCE(q.requests_limit, CASE WHEN p_window_type = 'hourly' THEN 50 ELSE 200 END) - COALESCE(q.requests_made, 0) AS requests_remaining,
        v_window_start AS window_start,
        v_window_end AS window_end,
        CASE 
            WHEN COALESCE(q.requests_limit, 1) > 0 
            THEN (COALESCE(q.requests_made, 0)::FLOAT / q.requests_limit::FLOAT) * 100
            ELSE 0.0
        END AS utilization_percent
    FROM (
        SELECT * FROM ga4_api_quota_usage
        WHERE tenant_id = p_tenant_id
        AND property_id = p_property_id
        AND quota_window_start = v_window_start
        AND window_type = p_window_type
    ) q;
    
    -- If no row exists, return defaults
    IF NOT FOUND THEN
        RETURN QUERY
        SELECT 
            0 AS requests_made,
            CASE WHEN p_window_type = 'hourly' THEN 50 ELSE 200 END AS requests_limit,
            CASE WHEN p_window_type = 'hourly' THEN 50 ELSE 200 END AS requests_remaining,
            v_window_start AS window_start,
            v_window_end AS window_end,
            0.0 AS utilization_percent;
    END IF;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_current_quota_usage IS 'Get current quota usage for a tenant and property';

-- ============================================================
-- Function: Cleanup Old Quota Records
-- ============================================================

CREATE OR REPLACE FUNCTION cleanup_old_quota_records(
    retention_days INT DEFAULT 30
)
RETURNS INT AS $$
DECLARE
    deleted_count INT;
BEGIN
    DELETE FROM ga4_api_quota_usage
    WHERE quota_window_end < NOW() - (retention_days || ' days')::INTERVAL;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_old_quota_records IS 'Delete quota records older than retention period. Run daily via cron.';

-- ============================================================
-- Trigger: Update updated_at Timestamp
-- ============================================================

CREATE TRIGGER update_ga4_quota_usage_updated_at
    BEFORE UPDATE ON ga4_api_quota_usage
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- Initial Data: Set Default Quotas
-- ============================================================

-- Note: In production, quotas should be configurable per tenant
-- This is just a default setup

-- ============================================================
-- Success Message
-- ============================================================

SELECT 'GA4 API Quota Tracking Schema Created Successfully' AS status;

