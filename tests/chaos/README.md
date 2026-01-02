# Chaos Engineering Test Suite

## Overview

This directory implements **Task P0-33: Chaos Engineering Test Suite** to validate system resilience under various failure scenarios.

## Purpose

Traditional testing validates "happy path" behavior. Chaos engineering validates that the system **degrades gracefully** under real-world failure conditions:

- Malformed API responses
- Network partitions
- Service failures
- Resource exhaustion

## Test Coverage

### 1. GA4 API Failures (`test_ga4_malformed_responses.py`)

**Scenarios:**
- ✅ Invalid UTF-8 encoding
- ✅ Malformed JSON
- ✅ Missing required fields
- ✅ Unexpected data types
- ✅ Circuit breaker behavior
- ✅ Recovery after fault removal

**Expected Behavior:**
- System falls back to cached data
- Errors logged for monitoring
- Circuit breaker opens after threshold
- No unhandled exceptions

### 2. OpenAI Embedding Failures (`test_embedding_failures.py`)

**Scenarios:**
- ✅ Wrong embedding dimensions (1535 vs 1536)
- ✅ NaN/Inf values in embeddings
- ✅ Zero vectors
- ✅ Abnormal magnitude
- ✅ API rate limits (429 errors)
- ✅ Timeouts
- ✅ Partial batch failures

**Expected Behavior:**
- Validation catches invalid embeddings (Task P0-16)
- No corrupt data in database
- Requests queued on rate limit
- Partial success handled gracefully

### 3. Database Failures (`test_database_partition.py`)

**Scenarios:**
- ✅ Network delays (5+ seconds)
- ✅ Connection timeouts
- ✅ Transaction rollbacks
- ✅ Connection pool exhaustion
- ✅ Recovery detection
- ✅ Read replica failover

**Expected Behavior:**
- Circuit breaker opens on slow queries
- Falls back to cache
- Transactions rollback cleanly
- pgBouncer handles connection pooling

### 4. Redis Cache Failures (`test_redis_failure.py`)

**Scenarios:**
- ✅ Complete Redis failure
- ✅ Connection timeouts
- ✅ Cache miss storm (100 concurrent)
- ✅ Memory exhaustion (OOM)
- ✅ Network partition
- ✅ Cache inconsistency
- ✅ Cluster failover

**Expected Behavior:**
- System continues without cache (slower)
- No crashes
- Database queries succeed
- Performance monitoring alerts

## Running Tests

### Run all chaos tests

```bash
pytest -m chaos tests/chaos/
```

### Run specific test file

```bash
pytest tests/chaos/test_ga4_malformed_responses.py
```

### Run with verbose output

```bash
pytest -m chaos tests/chaos/ -v
```

### Run specific scenario

```bash
pytest tests/chaos/test_ga4_malformed_responses.py::test_ga4_malformed_json -v
```

### Run in parallel

```bash
pytest -m chaos tests/chaos/ -n auto
```

## Fault Injection Framework

### Using `inject_fault`

```python
@pytest.mark.chaos
async def test_my_chaos_scenario(inject_fault):
    # Inject fault
    with inject_fault("ga4_client", response=b"malformed"):
        # System under test
        result = await service.call()
        
        # Assertions
        assert result['status'] == 'degraded'
```

### Using `inject_network_delay`

```python
@pytest.mark.chaos
async def test_network_delay(inject_network_delay):
    async with inject_network_delay("postgres", delay_ms=5000):
        # Database queries will have 5s delay
        result = await db.query("SELECT 1")
        
        assert result['latency'] > 5000
```

### Using `kill_service`

```python
@pytest.mark.chaos
async def test_service_down(kill_service):
    with kill_service("redis"):
        # Redis operations will fail
        result = await cache.get("key")
        
        # System should handle gracefully
        assert result['status'] != 'crashed'
```

## Custom Fault Handlers

Register custom fault handlers in `conftest.py`:

```python
def _my_custom_fault(**kwargs):
    @contextlib.contextmanager
    def _context():
        # Fault injection logic
        yield
    return _context()

register_fault_handler('my_service', _my_custom_fault)
```

## Acceptance Criteria

For all chaos tests:

✅ **Graceful Degradation** - System continues functioning (degraded mode OK)

✅ **No Unhandled Exceptions** - All errors caught and handled

✅ **Circuit Breaker Behavior** - Opens/closes correctly

✅ **Recovery Within 60s** - System auto-recovers when fault removed

✅ **Monitoring Alerts** - Prometheus metrics track failures

✅ **Fallback Mechanisms Work** - Cache, retry, circuit breaker

## Interpreting Results

### ✅ Success

```
test_ga4_malformed_json PASSED
```

System handled fault gracefully. No action needed.

### ❌ Failure

```
test_ga4_malformed_json FAILED
AssertionError: Expected degraded status, got: failed
```

System did not degrade gracefully. Investigation required:

1. Check if circuit breaker opened
2. Verify fallback mechanism exists
3. Check error handling code
4. Review monitoring alerts

### ⚠️ Timeout

```
test_database_recovery_timeout TIMEOUT (60s)
```

System did not recover within expected time:

1. Check if fault was actually removed
2. Verify health check implementation
3. Increase timeout if legitimate
4. Investigate recovery logic

## Integration with CI/CD

Add chaos tests to your pipeline:

```yaml
# .github/workflows/chaos-tests.yml
name: Chaos Engineering Tests

on:
  schedule:
    - cron: '0 0 * * 1'  # Weekly

jobs:
  chaos-tests:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r python/requirements.txt
          pip install pytest pytest-asyncio pytest-mock
      
      - name: Run chaos tests
        run: |
          pytest -m chaos tests/chaos/ --junit-xml=chaos-results.xml
      
      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: chaos-test-results
          path: chaos-results.xml
```

## Production Chaos Testing

⚠️ **WARNING:** Never run chaos tests against production!

For production resilience validation:

1. **Use Staging Environment** - Mirrors production setup
2. **Chaos Engineering Tools** - Use tools like Chaos Mesh, Gremlin
3. **Game Days** - Scheduled chaos exercises
4. **Gradual Rollout** - Start with low-impact failures
5. **Monitoring Ready** - Ensure alerts configured before testing

## Monitoring Integration

Chaos tests validate that monitoring alerts trigger:

```python
@pytest.mark.chaos
async def test_monitoring_alert(inject_fault):
    with inject_fault("ga4_client", response=b"error"):
        # Trigger failure
        await service.call()
        
        # Verify alert triggered
        assert prometheus_alert_fired("ga4_api_error_rate_high")
        assert pagerduty_incident_created()
```

## Related Documentation

- [Task P0-4: GA4 API Resilience Layer](../../docs/infrastructure/P0-04-ga4-resilience.md)
- [Task P0-6: Connection Pooling](../../docs/infrastructure/P0-06-connection-pooling.md)
- [Task P0-7: Monitoring & Alerting](../../docs/observability/P0-07-monitoring.md)
- [Task P0-16: Embedding Validation](../../docs/data-quality/P0-16-embedding-validation.md)
- [Circuit Breakers](../../python/src/agents/circuit_breakers.py)

## Troubleshooting

### Tests hang indefinitely

**Cause:** Fault not properly cleaned up, service still blocked.

**Solution:**
```python
# Use try/finally in conftest.py
try:
    yield
finally:
    # Always clean up fault
```

### Tests fail inconsistently

**Cause:** Race conditions or async timing issues.

**Solution:**
```python
# Add explicit waits
await asyncio.sleep(0.1)  # Let circuit breaker update

# Or use retry logic
for _ in range(3):
    if condition_met():
        break
    await asyncio.sleep(0.5)
```

### Mock not taking effect

**Cause:** Import happens before mock is applied.

**Solution:**
```python
# Import inside test or fixture
with patch(...):
    from src.service import Service  # Import after patch
```

## Best Practices

1. **Isolate Tests** - Each test should be independent
2. **Clean Up** - Always restore state after test
3. **Explicit Timeouts** - Don't wait indefinitely
4. **Document Expected Behavior** - Clear assertions
5. **Monitor Test Duration** - Flag slow tests

## Contributing

When adding new chaos tests:

1. Follow naming convention: `test_{service}_{failure_mode}`
2. Add clear docstring with scenario description
3. Include expected behavior in assertions
4. Register any new fault handlers in `conftest.py`
5. Update this README with new scenarios

## Performance Impact

Chaos tests may be slower than unit tests:

- Network delays: +5-10 seconds per test
- Retry logic: +3-5 seconds per test
- Recovery validation: +10-60 seconds per test

**Total suite runtime:** ~5-10 minutes

Run in parallel with `pytest -n auto` to reduce wall-clock time.

