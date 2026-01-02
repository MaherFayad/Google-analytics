-- Migration: Add Agent Parallel Execution Log
-- Implements Task P0-41: Parallel Agent Executor with Circuit Breakers
--
-- Purpose: Track parallel agent executions for monitoring, debugging,
-- and performance optimization
--
-- Dependencies: None (standalone table)

-- Create table for parallel execution audit
CREATE TABLE IF NOT EXISTS agent_parallel_execution_log (
    id BIGSERIAL PRIMARY KEY,
    
    -- Execution identification
    execution_id UUID NOT NULL UNIQUE,
    tenant_id UUID NOT NULL,
    
    -- Agents and execution groups
    agents_executed TEXT[] NOT NULL,
    parallel_groups JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    -- Performance metrics
    total_duration_ms INTEGER NOT NULL,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    circuit_breaker_blocks INTEGER NOT NULL DEFAULT 0,
    
    -- Timing
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common queries

-- Query by tenant
CREATE INDEX idx_parallel_exec_tenant 
    ON agent_parallel_execution_log(tenant_id);

-- Query by execution ID
CREATE INDEX idx_parallel_exec_id 
    ON agent_parallel_execution_log(execution_id);

-- Query by timestamp for time-based analysis
CREATE INDEX idx_parallel_exec_timestamp 
    ON agent_parallel_execution_log(timestamp DESC);

-- Query executions with failures
CREATE INDEX idx_parallel_exec_failures 
    ON agent_parallel_execution_log(tenant_id, failure_count) 
    WHERE failure_count > 0;

-- GIN index for agents array queries
CREATE INDEX idx_parallel_exec_agents 
    ON agent_parallel_execution_log USING GIN(agents_executed);

-- Comments for documentation
COMMENT ON TABLE agent_parallel_execution_log IS 
    'Audit trail for parallel agent executions (Task P0-41)';

COMMENT ON COLUMN agent_parallel_execution_log.execution_id IS 
    'Unique ID for this parallel execution';

COMMENT ON COLUMN agent_parallel_execution_log.agents_executed IS 
    'Array of agent names that were executed';

COMMENT ON COLUMN agent_parallel_execution_log.parallel_groups IS 
    'Array of arrays showing which agents ran concurrently';

COMMENT ON COLUMN agent_parallel_execution_log.circuit_breaker_blocks IS 
    'Number of agents blocked by open circuit breakers';

-- Create view for execution statistics
CREATE OR REPLACE VIEW agent_execution_statistics AS
SELECT 
    tenant_id,
    DATE_TRUNC('hour', timestamp) as hour,
    COUNT(*) as total_executions,
    AVG(total_duration_ms) as avg_duration_ms,
    AVG(success_count) as avg_success_count,
    AVG(failure_count) as avg_failure_count,
    SUM(circuit_breaker_blocks) as total_circuit_blocks
FROM agent_parallel_execution_log
GROUP BY tenant_id, DATE_TRUNC('hour', timestamp)
ORDER BY hour DESC;

COMMENT ON VIEW agent_execution_statistics IS 
    'Hourly statistics for agent execution performance';

-- Create function to get recent failures
CREATE OR REPLACE FUNCTION get_recent_agent_failures(
    p_tenant_id UUID,
    p_hours INTEGER DEFAULT 24
)
RETURNS TABLE (
    execution_id UUID,
    agents_executed TEXT[],
    failure_count INTEGER,
    duration_ms INTEGER,
    timestamp TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        log.execution_id,
        log.agents_executed,
        log.failure_count,
        log.total_duration_ms as duration_ms,
        log.timestamp
    FROM agent_parallel_execution_log log
    WHERE log.tenant_id = p_tenant_id
      AND log.failure_count > 0
      AND log.timestamp > NOW() - (p_hours || ' hours')::INTERVAL
    ORDER BY log.timestamp DESC;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_recent_agent_failures IS 
    'Get recent parallel executions with failures for debugging';

-- Example monitoring queries

-- Average execution time by tenant
-- SELECT tenant_id, AVG(total_duration_ms) as avg_duration_ms
-- FROM agent_parallel_execution_log
-- WHERE timestamp > NOW() - INTERVAL '24 hours'
-- GROUP BY tenant_id;

-- Circuit breaker effectiveness
-- SELECT 
--     SUM(circuit_breaker_blocks) as total_blocks,
--     COUNT(*) as total_executions,
--     ROUND(SUM(circuit_breaker_blocks)::NUMERIC / COUNT(*) * 100, 2) as block_rate_percent
-- FROM agent_parallel_execution_log
-- WHERE timestamp > NOW() - INTERVAL '1 hour';

-- Most common agent failures
-- SELECT 
--     UNNEST(agents_executed) as agent_name,
--     COUNT(*) as execution_count,
--     SUM(failure_count) as total_failures
-- FROM agent_parallel_execution_log
-- WHERE failure_count > 0
-- GROUP BY agent_name
-- ORDER BY total_failures DESC;

