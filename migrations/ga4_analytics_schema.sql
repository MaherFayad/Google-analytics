-- GA4 Analytics Events Schema Migration
-- Creates partitioned tables for high-cardinality GA4 event data with tenant isolation

-- Set search path
SET search_path TO app, public;

-- ============================================================
-- Main GA4 Events Table (Partitioned by event_timestamp)
-- ============================================================
CREATE TABLE IF NOT EXISTS archon_ga4_events (
    id BIGSERIAL,
    tenant_id UUID NOT NULL,
    property_id TEXT NOT NULL,
    event_name TEXT NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL,
    page_path TEXT,
    page_title TEXT,
    user_pseudo_id TEXT,
    session_id TEXT,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    dimensions JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding_768 VECTOR(768),
    embedding_model TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (id, event_timestamp)
) PARTITION BY RANGE (event_timestamp);

-- Create comment for documentation
COMMENT ON TABLE archon_ga4_events IS 'Stores raw GA4 event data with time-series partitioning for performance. Partitioned monthly by event_timestamp.';
COMMENT ON COLUMN archon_ga4_events.metrics IS 'JSONB field containing GA4 metrics (sessions, conversions, bounce_rate, etc.)';
COMMENT ON COLUMN archon_ga4_events.dimensions IS 'JSONB field containing GA4 dimensions (device, source, campaign, etc.)';
COMMENT ON COLUMN archon_ga4_events.embedding_768 IS 'Vector embedding (768D) for semantic search using pgvector';

-- ============================================================
-- Create Initial Partitions (Current Month + Next 3 Months)
-- ============================================================

-- January 2026
CREATE TABLE IF NOT EXISTS archon_ga4_events_2026_01 PARTITION OF archon_ga4_events
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

-- February 2026
CREATE TABLE IF NOT EXISTS archon_ga4_events_2026_02 PARTITION OF archon_ga4_events
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

-- March 2026
CREATE TABLE IF NOT EXISTS archon_ga4_events_2026_03 PARTITION OF archon_ga4_events
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

-- April 2026
CREATE TABLE IF NOT EXISTS archon_ga4_events_2026_04 PARTITION OF archon_ga4_events
FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');

-- ============================================================
-- Indexes for Performance
-- ============================================================

-- Composite index for tenant + time filtering (most common query pattern)
CREATE INDEX IF NOT EXISTS idx_ga4_events_tenant_time 
ON archon_ga4_events(tenant_id, event_timestamp DESC);

-- Index for property filtering
CREATE INDEX IF NOT EXISTS idx_ga4_events_property 
ON archon_ga4_events(property_id, event_timestamp DESC);

-- Index for event name filtering (e.g., page_view, conversion events)
CREATE INDEX IF NOT EXISTS idx_ga4_events_name 
ON archon_ga4_events(event_name, event_timestamp DESC);

-- GIN index for JSONB metrics queries
CREATE INDEX IF NOT EXISTS idx_ga4_events_metrics 
ON archon_ga4_events USING GIN (metrics jsonb_path_ops);

-- GIN index for JSONB dimensions queries
CREATE INDEX IF NOT EXISTS idx_ga4_events_dimensions 
ON archon_ga4_events USING GIN (dimensions jsonb_path_ops);

-- ============================================================
-- Vector Indexes on Partitions (IVFFlat for 768D embeddings)
-- ============================================================

-- Vector index on January 2026 partition
CREATE INDEX IF NOT EXISTS idx_ga4_events_2026_01_embedding 
ON archon_ga4_events_2026_01 
USING ivfflat (embedding_768 vector_cosine_ops) WITH (lists = 100);

-- Vector index on February 2026 partition
CREATE INDEX IF NOT EXISTS idx_ga4_events_2026_02_embedding 
ON archon_ga4_events_2026_02 
USING ivfflat (embedding_768 vector_cosine_ops) WITH (lists = 100);

-- Vector index on March 2026 partition
CREATE INDEX IF NOT EXISTS idx_ga4_events_2026_03_embedding 
ON archon_ga4_events_2026_03 
USING ivfflat (embedding_768 vector_cosine_ops) WITH (lists = 100);

-- Vector index on April 2026 partition
CREATE INDEX IF NOT EXISTS idx_ga4_events_2026_04_embedding 
ON archon_ga4_events_2026_04 
USING ivfflat (embedding_768 vector_cosine_ops) WITH (lists = 100);

-- ============================================================
-- Row Level Security (RLS) for Tenant Isolation
-- ============================================================

ALTER TABLE archon_ga4_events ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only access events from their own tenant
CREATE POLICY IF NOT EXISTS "Tenant isolation for GA4 events"
  ON archon_ga4_events FOR ALL
  USING (tenant_id = (current_setting('app.current_tenant_id', true))::uuid);

-- ============================================================
-- Daily Summaries Table (Pre-aggregated for Fast Dashboards)
-- ============================================================

CREATE TABLE IF NOT EXISTS archon_ga4_daily_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    property_id TEXT NOT NULL,
    date DATE NOT NULL,
    total_sessions INT DEFAULT 0,
    total_page_views INT DEFAULT 0,
    unique_users INT DEFAULT 0,
    avg_session_duration_seconds FLOAT DEFAULT 0,
    bounce_rate FLOAT DEFAULT 0,
    conversion_rate FLOAT DEFAULT 0,
    total_conversions INT DEFAULT 0,
    top_pages JSONB DEFAULT '[]'::jsonb,
    top_sources JSONB DEFAULT '[]'::jsonb,
    device_breakdown JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, property_id, date)
);

-- Indexes for daily summaries
CREATE INDEX IF NOT EXISTS idx_ga4_daily_summaries_tenant_date 
ON archon_ga4_daily_summaries(tenant_id, date DESC);

CREATE INDEX IF NOT EXISTS idx_ga4_daily_summaries_property 
ON archon_ga4_daily_summaries(property_id, date DESC);

-- RLS for daily summaries
ALTER TABLE archon_ga4_daily_summaries ENABLE ROW LEVEL SECURITY;

CREATE POLICY IF NOT EXISTS "Tenant isolation for GA4 daily summaries"
  ON archon_ga4_daily_summaries FOR ALL
  USING (tenant_id = (current_setting('app.current_tenant_id', true))::uuid);

-- ============================================================
-- Trigger for Updated At Timestamp
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_ga4_daily_summaries_updated_at
    BEFORE UPDATE ON archon_ga4_daily_summaries
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- Success Message
-- ============================================================

SELECT 'GA4 Analytics Schema Migration Completed Successfully' AS status;

