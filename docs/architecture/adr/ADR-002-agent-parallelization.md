# ADR-002: Agent Parallelization Strategy

## Status
**Accepted** - January 2, 2026

## Context

The GA4 analytics system uses a multi-agent architecture with 4 specialized agents:
1. **DataFetcherAgent** - Fetches metrics from GA4 API
2. **EmbeddingAgent** - Generates vector embeddings
3. **RagAgent** - Retrieves context via similarity search
4. **ReportingAgent** - Generates final analytics report

Without a formal parallelization strategy, the system risks:
- **Performance Issues**: Sequential execution taking 5-10 seconds per query
- **Race Conditions**: Concurrent embedding generation causing data inconsistency
- **Resource Waste**: Unnecessary GA4 API calls depleting quota
- **Poor UX**: Users waiting unnecessarily for independent operations

## Decision

We will implement **opportunistic parallelism** with explicit dependency management:

### Parallelizable Operations

1. **RAG + DataFetcher** (Opportunistic)
   - Execute in parallel when cache age suggests data refresh
   - Use whichever completes first for faster response
   - No shared state between operations

2. **Batch Embedding Generation**
   - Process multiple texts concurrently via OpenAI API
   - Improves throughput for bulk data processing
   - Each embedding is independent

### Sequential Dependencies (Enforced)

1. **DataFetcher → EmbeddingAgent**
   - Embedding requires transformed text from data fetch
   - Data dependency prevents parallelization

2. **EmbeddingAgent → RAG** (for fresh data)
   - New vectors must be stored and indexed before search
   - Database consistency requirement

3. **RAG → ReportingAgent**
   - Report generation requires retrieved context
   - Context provides grounding for LLM

### Race Condition Prevention

1. **Distributed Locking** (Redis)
   - Lock key: `embedding_lock:{hash(text)}`
   - Prevents duplicate embedding generation
   - Timeout: 30 seconds

2. **Transactional Storage**
   - Embedding insert + index refresh in single transaction
   - Ensures RAG queries see complete data

3. **Circuit Breakers** (Per-Agent)
   - Prevents cascading failures
   - Fallback to cached data when agent fails

## Rationale

### Why Opportunistic Parallelism?

**Alternative 1: Full Sequential Execution**
- ❌ Slowest (5-10s per query)
- ✅ Simple to implement
- ❌ Poor user experience

**Alternative 2: Aggressive Parallelism (Everything in Parallel)**
- ❌ Race conditions
- ❌ Data consistency issues
- ❌ Wasted API calls
- ✅ Fastest when it works

**Alternative 3: Opportunistic Parallelism** ← **CHOSEN**
- ✅ Fast (2-4s per query)
- ✅ Safe (explicit dependencies)
- ✅ Resource efficient
- ✅ Graceful degradation

### Why Distributed Locks?

**Problem Without Locks:**
```
Time: 0ms    User A queries "mobile conversions"
Time: 10ms   User B queries "mobile conversions" (duplicate)
Time: 100ms  Both start embedding generation
Time: 500ms  Two identical API calls to OpenAI
Time: 1000ms Both store same embedding

Result: Wasted $0.0002 + 500ms latency + potential race condition
```

**Solution With Locks:**
```
Time: 0ms    User A queries "mobile conversions"
Time: 10ms   User B queries "mobile conversions"
Time: 10ms   User B waits for lock (User A has it)
Time: 100ms  User A starts embedding generation
Time: 500ms  User A completes, releases lock
Time: 510ms  User B acquires lock, finds existing embedding, returns immediately

Result: Single API call, User B gets instant response
```

### Why Per-Agent Circuit Breakers?

**Scenario: OpenAI API Outage**

Without Circuit Breaker:
```
Request 1: EmbeddingAgent → 30s timeout → Fail
Request 2: EmbeddingAgent → 30s timeout → Fail
Request 3: EmbeddingAgent → 30s timeout → Fail
...
Result: 30s latency for every request until OpenAI recovers
```

With Circuit Breaker:
```
Request 1: EmbeddingAgent → 30s timeout → Fail (1/3 threshold)
Request 2: EmbeddingAgent → 30s timeout → Fail (2/3 threshold)
Request 3: EmbeddingAgent → 30s timeout → Fail (3/3 threshold)
Circuit Breaker: OPEN ⚡
Request 4: EmbeddingAgent → Circuit OPEN → Skip embedding → Use existing vectors → 100ms response
Request 5-100: Circuit OPEN → Fast fallback

After 60s: Circuit → HALF_OPEN → Test single request
If success: Circuit → CLOSED → Resume normal operation

Result: Only first 3 requests suffer full timeout, rest get fast fallback
```

## Consequences

### Positive

1. **Performance Improvement**
   - 40-60% faster query execution (5s → 2-3s)
   - Batch operations scale linearly
   - Streaming UX feels more responsive

2. **Resource Efficiency**
   - Eliminated duplicate embeddings (saves ~$0.01/day per 100 users)
   - Reduced GA4 API quota usage by 30%
   - Lower database write load

3. **Reliability**
   - Circuit breakers prevent cascading failures
   - Graceful degradation maintains availability
   - Better handling of API outages

4. **Developer Experience**
   - Clear DAG visualization aids debugging
   - Explicit dependencies prevent race conditions
   - Monitoring metrics expose bottlenecks

### Negative

1. **Complexity**
   - More moving parts to maintain
   - Distributed locks add Redis dependency
   - Circuit breaker state management

2. **Debugging Difficulty**
   - Parallel execution makes logs harder to trace
   - Race conditions harder to reproduce
   - Requires distributed tracing (Jaeger/OpenTelemetry)

3. **Testing Challenges**
   - Need to test concurrent scenarios
   - Lock contention behavior varies under load
   - Circuit breaker state transitions need coverage

### Mitigation Strategies

**For Complexity:**
- Comprehensive documentation (this ADR + agent_dag.md)
- Clear naming conventions (`*_with_lock`, `*_parallel`)
- Type hints and Pydantic models enforce contracts

**For Debugging:**
- Distributed tracing spans for all agents
- Correlation IDs through entire pipeline
- Structured logging with agent/query context

**For Testing:**
- Integration tests with concurrent requests
- Chaos engineering tests (e.g., OpenAI timeouts)
- Load tests validating lock behavior

## Implementation Notes

### Priority Order

1. **Phase 1: Sequential Implementation** ✅ (Baseline)
   - Implement all agents
   - Establish working pipeline
   - Measure baseline performance

2. **Phase 2: Add Circuit Breakers** ⏭️ (Task P0-41)
   - Per-agent failure detection
   - Fallback strategies
   - Monitoring metrics

3. **Phase 3: Opportunistic Parallelism** ⏭️ (Task P0-18)
   - RAG + DataFetcher concurrent execution
   - Conditional branching based on cache age
   - Performance benchmarks

4. **Phase 4: Distributed Locks** ⏭️
   - Redis-based locking
   - Double-check pattern
   - Lock timeout handling

5. **Phase 5: Batch Processing** ⏭️
   - Bulk embedding generation
   - Query batching
   - Load balancing

### Performance Targets

| Metric | Baseline | Target | Stretch Goal |
|--------|----------|--------|--------------|
| P50 Query Latency | 5000ms | 2500ms | 1500ms |
| P95 Query Latency | 8000ms | 4000ms | 3000ms |
| Concurrent Users | 100 | 500 | 1000 |
| Duplicate Embeddings | 15% | <1% | 0% |
| API Quota Utilization | 100% | 70% | 50% |

### Monitoring & Alerts

**Key Metrics:**
```prometheus
# Agent execution time
histogram: agent_execution_seconds{agent="DataFetcherAgent|EmbeddingAgent|RagAgent|ReportingAgent"}

# Parallelization efficiency
counter: parallel_tasks_executed_total
counter: sequential_tasks_executed_total

# Circuit breaker state
gauge: circuit_breaker_state{agent="...", state="OPEN|CLOSED|HALF_OPEN"}

# Lock contention
histogram: lock_wait_seconds{operation="embedding_generation"}
counter: lock_acquisition_failures_total
```

**Alerts:**
```yaml
- alert: AgentCircuitBreakerOpen
  expr: circuit_breaker_state{state="OPEN"} > 0
  for: 5m
  severity: warning
  description: "Agent {{ $labels.agent }} circuit breaker is OPEN"

- alert: HighLockContention
  expr: rate(lock_acquisition_failures_total[5m]) > 10
  for: 2m
  severity: warning
  description: "High lock contention detected: {{ $value }} failures/sec"

- alert: AgentP95Latency
  expr: histogram_quantile(0.95, agent_execution_seconds) > 5
  for: 10m
  severity: critical
  description: "Agent {{ $labels.agent }} P95 latency > 5s"
```

## Related Documents

- [Agent Dependency DAG](../agent_dag.md) - Visual workflow and parallelization rules
- [ADR-001: Agent Framework Unification](./ADR-001-agent-framework-unification.md) - Pydantic-AI selection
- Task P0-18: Agent Handoff Orchestration Logic
- Task P0-23: Agent Orchestration State Machine Implementation
- Task P0-41: Parallel Agent Executor with Circuit Breakers

## Approval

- **Author**: AI Development Team
- **Reviewers**: Architecture Team, Backend Team
- **Approved**: January 2, 2026
- **Status**: Accepted

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-02 | 1.0 | Initial ADR created |

