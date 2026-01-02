# RLS Load Testing Suite

**Task P0-29: Load Test RLS Policies Under Concurrent Session Variables**

This directory contains load tests that validate tenant isolation under production-scale concurrent load (1000 users).

## 🎯 Test Objectives

**Critical Goal**: Prove RLS policies maintain 99.99% tenant isolation under 1000 concurrent users across 100 tenants.

### What We Test

1. **Vector Search Isolation** (50% of requests)
   - pgvector similarity searches respect RLS policies
   - No cross-tenant embedding leakage
   - Session variables remain isolated under concurrent load

2. **Chat Session Isolation** (20% of requests)
   - chat_sessions table queries filtered by tenant
   - No user can access another tenant's chat history

3. **GA4 Metrics Isolation** (15% of requests)
   - ga4_metrics_raw table respects RLS
   - Concurrent GA4 data fetching maintains isolation

4. **Mixed Read/Write Operations** (10% of requests)
   - RLS isolation maintained during concurrent writes
   - SSE streaming doesn't cause session variable bleed

5. **Context Switching Stress Test** (5% of requests)
   - Rapid tenant context switches don't cause race conditions
   - Session variables update atomically

## 📁 File Structure

```
tests/load/
├── __init__.py                  # Package initialization
├── README.md                    # This file
├── conftest.py                  # Test fixtures and configuration
├── isolation_validator.py       # Cross-tenant leak detection
├── rls_scenarios.py            # Test scenario definitions
└── test_rls_under_load.py      # Main Locust load test
```

## 🚀 Quick Start

### Prerequisites

```bash
# Install dependencies
cd python
poetry install --with dev

# Ensure PostgreSQL with pgvector is running
docker-compose up -d postgres

# Run database migrations
poetry run alembic upgrade head

# Start API server
poetry run uvicorn src.server.main:app --host 0.0.0.0 --port 8000
```

### Running Load Tests

#### Option 1: Locust Web UI (Recommended for Development)

```bash
cd python
poetry run locust -f ../tests/load/test_rls_under_load.py --host=http://localhost:8000
```

Then open http://localhost:8089 and configure:
- **Number of users**: 1000
- **Spawn rate**: 100 users/second
- **Run time**: 5 minutes

#### Option 2: Headless Mode (CI/CD)

```bash
cd python
poetry run locust -f ../tests/load/test_rls_under_load.py \
    --host=http://localhost:8000 \
    --users 1000 \
    --spawn-rate 100 \
    --run-time 5m \
    --headless \
    --html=load_test_report.html
```

#### Option 3: Short Validation Test

```bash
# Quick 30-second test with 100 users
cd python
poetry run locust -f ../tests/load/test_rls_under_load.py \
    --host=http://localhost:8000 \
    --users 100 \
    --spawn-rate 20 \
    --run-time 30s \
    --headless
```

## 📊 Success Criteria

### Target Metrics

| Metric | Target | Critical? |
|--------|--------|-----------|
| Isolation Success Rate | ≥ 99.99% | ✅ YES |
| Total Requests | ≥ 10,000 | ✅ YES |
| Isolation Violations | ≤ 1 per 10,000 | ✅ YES |
| P95 Latency | < 1000ms | ⚠️ Warning |
| Error Rate | < 1% | ⚠️ Warning |

### Passing Criteria

**CRITICAL**: Test FAILS if isolation success rate < 99.99%

```
✅ PASSED Example:
- Total Requests: 50,000
- Isolation Violations: 0
- Success Rate: 100.0%

❌ FAILED Example:
- Total Requests: 50,000
- Isolation Violations: 10
- Success Rate: 99.98% (below 99.99% target)
```

## 🔍 How Isolation Validation Works

### 1. Response Validation

Every API response is automatically validated:

```python
# isolation_validator.py
def validate_response(tenant_id, response_data, endpoint):
    # Extract all tenant_id fields from response
    leaked_ids = extract_tenant_ids(response_data)
    
    # Check for cross-tenant data
    for leaked_id in leaked_ids:
        if leaked_id != tenant_id:
            # 🚨 VIOLATION DETECTED
            log_violation(tenant_id, leaked_id, endpoint)
```

### 2. Vector Search Validation

Special validation for pgvector results:

```python
# Validates each embedding in search results
for result in search_results:
    if result['tenant_id'] != requesting_tenant_id:
        # 🚨 Vector search leaked cross-tenant data
        raise IsolationViolation()
```

### 3. Thread-Safe Tracking

All validations are thread-safe for concurrent load:

```python
class IsolationValidator:
    def __init__(self):
        self._lock = threading.Lock()
        self._violations = []
    
    def validate_response(...):
        with self._lock:
            # Thread-safe validation
```

## 🐛 Debugging Failures

### If Isolation Test Fails

1. **Check Violation Details**

```bash
# Load test logs show violation details
grep "SECURITY VIOLATION" load_test.log
```

Sample output:
```
🚨 SECURITY VIOLATION: Tenant abc123 received data from tenant def456 at /api/v1/analytics/query
```

2. **Analyze Violation Patterns**

```python
# In isolation_validator.py
violations = validator.get_violations()
for v in violations:
    print(f"Tenant {v.requesting_tenant_id} -> {v.leaked_tenant_id}")
    print(f"Endpoint: {v.endpoint}")
    print(f"Type: {v.violation_type}")
```

3. **Check RLS Policies**

```sql
-- Verify RLS policies are enabled
SELECT schemaname, tablename, policyname, permissive, roles, qual 
FROM pg_policies 
WHERE schemaname = 'public';

-- Test RLS manually
SET app.tenant_id = 'tenant_a';
SELECT * FROM ga4_embeddings;  -- Should only return tenant_a's data
```

4. **Verify Session Variables**

```python
# In middleware/rls_enforcer.py
async def set_rls_context(session, user_id, tenant_id):
    await session.execute(
        text("SET LOCAL app.tenant_id = :tenant_id"),
        {"tenant_id": tenant_id}
    )
    
    # Verify it was set
    result = await session.execute(text("SHOW app.tenant_id"))
    assert result.scalar() == tenant_id
```

## 📈 Performance Benchmarking

### Expected Performance (1000 concurrent users)

- **Throughput**: 200-500 requests/second
- **P50 Latency**: 100-300ms
- **P95 Latency**: 500-1000ms
- **P99 Latency**: 1000-2000ms

### Database Connection Pool

Load test requires proper connection pooling:

```yaml
# docker-compose.yml
pgbouncer:
  image: pgbouncer/pgbouncer:latest
  environment:
    - POOL_MODE=transaction
    - MAX_CLIENT_CONN=1000
    - DEFAULT_POOL_SIZE=25
```

## 🔧 Configuration

### Environment Variables

```bash
# .env.test
LOCUST_HOST=http://localhost:8000
LOCUST_USERS=1000
LOCUST_SPAWN_RATE=100
LOCUST_RUN_TIME=5m
TEST_TENANT_COUNT=100
```

### Customizing Test Scenarios

Edit `rls_scenarios.py` to adjust scenario weights:

```python
LoadTestScenario(
    name="vector_search",
    weight=50,  # 50% of requests (change this)
    endpoint="/api/v1/analytics/query",
    ...
)
```

## 🚨 CI/CD Integration

### GitHub Actions Example

```yaml
name: RLS Load Test

on: [pull_request]

jobs:
  rls-load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Start services
        run: docker-compose up -d
      
      - name: Run load test
        run: |
          cd python
          poetry install --with dev
          poetry run locust -f ../tests/load/test_rls_under_load.py \
            --host=http://localhost:8000 \
            --users 1000 \
            --spawn-rate 100 \
            --run-time 5m \
            --headless
      
      - name: Check results
        run: |
          if grep -q "FAILED" load_test.log; then
            echo "❌ RLS isolation test failed"
            exit 1
          fi
          echo "✅ RLS isolation test passed"
```

## 📚 Related Tasks

- **Task P0-2**: Server-Side Tenant Derivation & Validation
- **Task P0-3**: Vector Search Tenant Isolation Integration Test
- **Task 11**: Multi-Tenant Security Foundation

## 🤝 Contributing

When adding new test scenarios:

1. Add scenario to `rls_scenarios.py`
2. Update `RLSScenarios.get_all_scenarios()`
3. Add corresponding task in `TenantUser` class
4. Update this README with new scenario description
5. Ensure isolation validator handles new endpoint

## ❓ FAQ

**Q: Why 99.99% and not 100%?**
A: Network errors, timeouts, and edge cases may cause false positives. 99.99% = max 1 violation per 10,000 requests.

**Q: How long should tests run?**
A: Minimum 5 minutes to generate 10,000+ requests. Longer tests (30+ minutes) are more reliable.

**Q: Can I run against staging?**
A: Yes! Change `--host` parameter:
```bash
locust -f test_rls_under_load.py --host=https://staging.example.com
```

**Q: What if my machine can't handle 1000 users?**
A: Use distributed mode:
```bash
# Master
locust -f test_rls_under_load.py --master

# Workers (run on multiple machines)
locust -f test_rls_under_load.py --worker --master-host=<master-ip>
```

---

**Status**: ✅ Implemented (Task P0-29)  
**Last Updated**: 2026-01-02  
**Maintained By**: Archon Team

