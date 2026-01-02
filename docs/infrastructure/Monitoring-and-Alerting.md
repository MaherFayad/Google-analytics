# Monitoring & Alerting Infrastructure

**Task**: P0-7: Monitoring & Alerting Infrastructure [HIGH]  
**Status**: ✅ Complete  
**Priority**: P0-HIGH

## Overview

Comprehensive observability stack with Prometheus metrics, Grafana dashboards, and Sentry error tracking.

## Architecture

```
┌──────────────────┐
│   FastAPI App    │
│  (metrics.py)    │
└────────┬─────────┘
         │
         │ /metrics endpoint
         │ (Prometheus format)
         ▼
┌──────────────────┐         ┌──────────────────┐
│   Prometheus     │────────>│    Grafana       │
│ (Scrape + Alert) │         │  (Dashboards)    │
└──────────────────┘         └──────────────────┘
         │
         │ Alertmanager
         ▼
┌──────────────────┐
│   PagerDuty      │
│   Slack          │
└──────────────────┘

┌──────────────────┐
│   Sentry SDK     │
│ (Error Tracking) │
└────────┬─────────┘
         │
         │ Automatic capture
         ▼
┌──────────────────┐
│   Sentry.io      │
│  (Error Platform)│
└──────────────────┘
```

## Metrics Tracked

### GA4 API Health
- `ga4_api_calls_total{tenant_id, endpoint, status}` - API call counter
- `ga4_api_latency_seconds{endpoint}` - Request latency histogram
- `ga4_quota_usage_ratio{tenant_id, property_id}` - Quota usage (0.0-1.0)
- `ga4_quota_remaining{tenant_id, property_id}` - Remaining quota
- `ga4_api_errors_total{tenant_id, error_type}` - Error counter
- `ga4_cache_hit_rate{tenant_id}` - Cache effectiveness

### Vector Search Performance
- `vector_search_latency_seconds{tenant_id, search_type}` - Search latency
- `vector_search_results_count{tenant_id}` - Results per query
- `vector_search_cache_hit_rate{tenant_id}` - Cache effectiveness
- `vector_embedding_duration_seconds{model}` - Embedding generation time
- `vector_embedding_batch_size` - Batch size distribution

### SSE Connections
- `sse_active_connections{tenant_id, endpoint}` - Active connections
- `sse_connection_duration_seconds{tenant_id, endpoint}` - Connection lifetime
- `sse_events_sent_total{tenant_id, event_type}` - Events sent
- `sse_errors_total{tenant_id, error_type}` - SSE errors

### HTTP API
- `http_requests_total{method, endpoint, status_code}` - Request counter
- `http_request_duration_seconds{method, endpoint}` - Request latency
- `http_request_size_bytes{method, endpoint}` - Request size
- `http_response_size_bytes{method, endpoint}` - Response size

### Database
- `connection_pool_utilization_ratio{pool_type}` - Pool utilization
- `connection_pool_active_connections{pool_type}` - Active connections
- `database_query_duration_seconds{operation, pool_type}` - Query latency
- `database_queries_total{operation, pool_type, status}` - Query counter

### System Health
- `system_uptime_seconds` - Service uptime
- `system_cpu_usage_percent` - CPU usage
- `system_memory_usage_bytes{type}` - Memory usage (RSS, VMS)
- `active_tenants_count` - Active tenants

## Usage

### Instrumenting Code

#### GA4 API Calls
```python
from src.server.monitoring.metrics import (
    track_ga4_api_call,
    record_ga4_api_success,
    record_ga4_api_error,
    record_ga4_quota
)

# Track API call latency
with track_ga4_api_call("runReport", tenant_id):
    response = await ga4_client.run_report(property_id, request)

# Record success
record_ga4_api_success("runReport", tenant_id)

# Update quota
record_ga4_quota(tenant_id, property_id, used=850, total=1000)
```

#### Vector Search
```python
from src.server.monitoring.metrics import (
    track_vector_search,
    record_vector_search_results
)

with track_vector_search(tenant_id, "hybrid"):
    results = await vector_search(query, limit=10)

record_vector_search_results(tenant_id, len(results))
```

#### SSE Connections
```python
from src.server.monitoring.metrics import (
    track_sse_connection_start,
    track_sse_connection_end,
    record_sse_event
)

connection_id = str(uuid.uuid4())

# Start tracking
track_sse_connection_start(connection_id, tenant_id, "/analytics/stream")

try:
    async for event in generate_events():
        yield event
        record_sse_event(tenant_id, event["type"])
finally:
    track_sse_connection_end(connection_id, tenant_id, "/analytics/stream")
```

### Sentry Error Tracking

#### Initialization
```python
# In main.py
from src.server.monitoring.sentry_config import init_sentry

@app.on_event("startup")
async def startup():
    init_sentry()
```

#### Automatic Capture
```python
# Unhandled exceptions are automatically captured
async def process_analytics():
    result = await risky_operation()  # Errors auto-captured
    return result
```

#### Manual Capture
```python
from src.server.monitoring.sentry_config import (
    capture_exception,
    capture_message,
    add_breadcrumb,
    set_tenant_context
)

# Set context (in middleware)
set_tenant_context(tenant_id, user_id)

# Add breadcrumb for debugging
add_breadcrumb(
    "ga4",
    "Fetching analytics data",
    property_id="123",
    date_range="last_7_days"
)

# Manual exception capture
try:
    result = await fetch_data()
except APIError as e:
    capture_exception(
        e,
        operation="fetch_analytics",
        tenant_id=tenant_id
    )
    raise

# Message capture
capture_message(
    "GA4 quota threshold exceeded",
    level="warning",
    quota_usage=0.95
)
```

#### Performance Tracing
```python
from src.server.monitoring.sentry_config import start_transaction, start_span

with start_transaction("generate_embeddings", op="task"):
    with start_span("openai.embed", "Call OpenAI API"):
        embeddings = await openai_client.embed(texts)
    
    with start_span("db.insert", "Store embeddings"):
        await store_embeddings(embeddings)
```

## Accessing Dashboards

### Prometheus
- URL: `http://localhost:9090`
- Explore metrics: http://localhost:9090/graph
- Alert rules: http://localhost:9090/alerts

### Grafana
- URL: `http://localhost:3001`
- Username: `admin`
- Password: `admin` (change on first login)

### Pre-built Dashboards
1. **System Overview** - High-level health metrics
2. **GA4 Integration Health** - GA4 API performance
3. **Tenant Activity** - Per-tenant metrics
4. **Vector Search Performance** - Search latency and quality
5. **Database Health** - Connection pools and query performance

## Alert Rules

### Critical Alerts (PagerDuty)
- GA4 API error rate > 5% for 5 minutes
- GA4 quota > 95% for 2 minutes
- SSE connections > 950 for 2 minutes
- Connection pool utilization > 90% for 2 minutes
- Service down for 2 minutes
- HTTP 5xx error rate > 5% for 5 minutes
- CPU usage > 95% for 5 minutes

### Warning Alerts (Slack)
- GA4 API latency p95 > 5s for 10 minutes
- GA4 quota > 90% for 5 minutes
- Vector search latency p95 > 1s for 10 minutes
- SSE connections > 900 for 5 minutes
- Connection pool utilization > 80% for 5 minutes
- CPU usage > 80% for 10 minutes
- High memory usage for 10 minutes

## Configuration

### Environment Variables
```bash
# Sentry
SENTRY_DSN=https://...@sentry.io/...
SENTRY_TRACES_SAMPLE_RATE=0.1  # 10% of transactions
SENTRY_PROFILES_SAMPLE_RATE=0.1  # 10% of transactions
APP_VERSION=v1.2.3  # For release tracking

# Environment
ENVIRONMENT=production  # development, staging, or production
```

### Prometheus Configuration
Edit `prometheus/prometheus.yml`:
```yaml
global:
  scrape_interval: 15s  # Adjust scrape frequency
  evaluation_interval: 15s  # Adjust alert evaluation frequency

scrape_configs:
  - job_name: 'ga4-api'
    metrics_path: '/metrics'
    static_configs:
      - targets: ['api:8000']
```

### Alert Rules
Edit `prometheus/alert_rules/ga4_analytics_alerts.yml` to customize thresholds:
```yaml
- alert: GA4_API_HighErrorRate
  expr: |
    (sum(rate(ga4_api_calls_total{status="error"}[5m])) / sum(rate(ga4_api_calls_total[5m]))) > 0.05
  for: 5m  # Adjust duration
  labels:
    severity: critical  # critical, warning, info
```

## Deployment

### Start Monitoring Stack
```bash
# Start all services
docker-compose up -d

# Check Prometheus is scraping
curl http://localhost:9090/api/v1/targets

# Check metrics endpoint
curl http://localhost:8000/metrics

# Access Grafana
open http://localhost:3001
```

### Production Setup

1. **Deploy Alertmanager**:
```yaml
# docker-compose.yml
alertmanager:
  image: prom/alertmanager:latest
  ports:
    - "9093:9093"
  volumes:
    - ./alertmanager/config.yml:/etc/alertmanager/config.yml
```

2. **Configure PagerDuty**:
```yaml
# alertmanager/config.yml
receivers:
  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: '<PAGERDUTY_SERVICE_KEY>'
        description: '{{ .CommonAnnotations.summary }}'
```

3. **Configure Slack**:
```yaml
receivers:
  - name: 'slack'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/...'
        channel: '#alerts'
        title: '{{ .CommonAnnotations.summary }}'
```

## Troubleshooting

### Issue: Metrics not appearing in Prometheus
**Solution**:
1. Check metrics endpoint: `curl http://localhost:8000/metrics`
2. Verify Prometheus is scraping: http://localhost:9090/targets
3. Check Prometheus logs: `docker logs ga4-prometheus`

### Issue: Sentry not capturing errors
**Solution**:
1. Verify `SENTRY_DSN` is set
2. Check init_sentry() is called at startup
3. Test with manual capture: `capture_message("test")`

### Issue: High cardinality warnings
**Solution**:
- Avoid high-cardinality labels (user IDs, timestamps)
- Use aggregation for tenant-specific metrics
- Consider sampling for high-volume metrics

## Best Practices

1. **Label cardinality**: Keep label cardinality low (< 100 values per label)
2. **Sampling**: Use appropriate sample rates in production (10-20%)
3. **Alert fatigue**: Set thresholds to minimize false positives
4. **Context**: Always set tenant context in Sentry for multi-tenant apps
5. **Breadcrumbs**: Add breadcrumbs before risky operations for debugging
6. **Runbooks**: Link alerts to runbooks with resolution steps

## Future Enhancements

- [ ] Distributed tracing with Jaeger/Tempo
- [ ] Log aggregation with Loki
- [ ] Custom Grafana alerts (in addition to Prometheus)
- [ ] Anomaly detection with ML models
- [ ] Cost tracking dashboard
- [ ] SLA/SLO tracking

## References

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Sentry Python SDK](https://docs.sentry.io/platforms/python/)
- [FastAPI Metrics](https://github.com/trallnag/prometheus-fastapi-instrumentator)

## Contributors

- Archon AI Agent
- Implementation Date: 2026-01-02

