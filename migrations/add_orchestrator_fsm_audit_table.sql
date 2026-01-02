-- Migration: Add Orchestrator FSM Audit Table
-- Implements Task P0-39: Formal Agent State Machine Implementation
--
-- Purpose: Track all state transitions in agent orchestration workflow
-- for debugging, monitoring, and compliance
--
-- Dependencies: None (standalone table)

-- Create audit table for state machine transitions
CREATE TABLE IF NOT EXISTS orchestrator_fsm_audit (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    query_id UUID NOT NULL,
    
    -- State transition details
    state_from TEXT NOT NULL,
    state_to TEXT NOT NULL,
    trigger TEXT NOT NULL,
    
    -- Transition data (stores agent results, parameters, etc.)
    transition_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    transition_data_hash TEXT NOT NULL,
    
    -- Timing and performance
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duration_ms INTEGER,
    
    -- Error tracking
    error_message TEXT,
    
    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common queries

-- Query by tenant and query ID
CREATE INDEX idx_fsm_audit_tenant_query 
    ON orchestrator_fsm_audit(tenant_id, query_id);

-- Query by timestamp for time-based analysis
CREATE INDEX idx_fsm_audit_timestamp 
    ON orchestrator_fsm_audit(timestamp DESC);

-- Query by state transitions for debugging
CREATE INDEX idx_fsm_audit_states 
    ON orchestrator_fsm_audit(state_from, state_to);

-- Query error transitions
CREATE INDEX idx_fsm_audit_errors 
    ON orchestrator_fsm_audit(tenant_id) 
    WHERE error_message IS NOT NULL;

-- GIN index for JSONB queries on transition data
CREATE INDEX idx_fsm_audit_transition_data 
    ON orchestrator_fsm_audit USING GIN(transition_data);

-- Comments for documentation
COMMENT ON TABLE orchestrator_fsm_audit IS 
    'Audit trail for agent orchestration state machine transitions (Task P0-39)';

COMMENT ON COLUMN orchestrator_fsm_audit.tenant_id IS 
    'Tenant ID for multi-tenant isolation';

COMMENT ON COLUMN orchestrator_fsm_audit.query_id IS 
    'Unique ID for this workflow execution';

COMMENT ON COLUMN orchestrator_fsm_audit.state_from IS 
    'Source state before transition';

COMMENT ON COLUMN orchestrator_fsm_audit.state_to IS 
    'Destination state after transition';

COMMENT ON COLUMN orchestrator_fsm_audit.trigger IS 
    'Event that triggered the state transition';

COMMENT ON COLUMN orchestrator_fsm_audit.transition_data IS 
    'JSONB data associated with transition (agent results, parameters)';

COMMENT ON COLUMN orchestrator_fsm_audit.transition_data_hash IS 
    'SHA256 hash of transition_data for integrity verification';

COMMENT ON COLUMN orchestrator_fsm_audit.duration_ms IS 
    'Duration of this state in milliseconds';

COMMENT ON COLUMN orchestrator_fsm_audit.error_message IS 
    'Error message if transition failed (NULL for successful transitions)';

-- Create helper function to query workflow by query_id
CREATE OR REPLACE FUNCTION get_workflow_audit_trail(p_query_id UUID)
RETURNS TABLE (
    state_from TEXT,
    state_to TEXT,
    trigger TEXT,
    duration_ms INTEGER,
    timestamp TIMESTAMPTZ,
    error_message TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        fsm.state_from,
        fsm.state_to,
        fsm.trigger,
        fsm.duration_ms,
        fsm.timestamp,
        fsm.error_message
    FROM orchestrator_fsm_audit fsm
    WHERE fsm.query_id = p_query_id
    ORDER BY fsm.timestamp ASC;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_workflow_audit_trail IS 
    'Retrieve complete audit trail for a workflow execution';

-- Create view for workflow summaries
CREATE OR REPLACE VIEW orchestrator_workflow_summary AS
SELECT 
    tenant_id,
    query_id,
    COUNT(*) as total_transitions,
    SUM(duration_ms) as total_duration_ms,
    MIN(timestamp) as started_at,
    MAX(timestamp) as completed_at,
    COUNT(*) FILTER (WHERE error_message IS NOT NULL) as error_count,
    ARRAY_AGG(state_to ORDER BY timestamp) as states_visited,
    CASE 
        WHEN MAX(state_to) = 'complete' THEN 'complete'
        WHEN MAX(state_to) = 'error_fallback' THEN 'error'
        ELSE 'in_progress'
    END as status
FROM orchestrator_fsm_audit
GROUP BY tenant_id, query_id;

COMMENT ON VIEW orchestrator_workflow_summary IS 
    'Summary statistics for each workflow execution';

-- Example queries for monitoring

-- Get workflows that took longer than 30 seconds
-- SELECT * FROM orchestrator_workflow_summary 
-- WHERE total_duration_ms > 30000;

-- Find workflows that encountered errors
-- SELECT * FROM orchestrator_workflow_summary 
-- WHERE error_count > 0;

-- Analyze most common state transition failures
-- SELECT state_from, state_to, COUNT(*) as failure_count
-- FROM orchestrator_fsm_audit
-- WHERE error_message IS NOT NULL
-- GROUP BY state_from, state_to
-- ORDER BY failure_count DESC;

