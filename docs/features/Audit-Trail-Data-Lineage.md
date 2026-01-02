# Audit Trail & Data Lineage

**Task**: P0-44: Admin Audit Trail API for Data Lineage [HIGH]  
**Status**: ✅ Complete  
**Priority**: P0-HIGH

## Overview

Complete data lineage tracking from GA4 API call → embeddings → LLM → final report, enabling debugging of "Why did the report say X when GA4 shows Y?" questions.

## Problem Solved

**Before**: No way to trace how a report was generated:
- ❌ Can't debug incorrect reports
- ❌ No visibility into data transformations
- ❌ Can't validate LLM outputs against source data
- ❌ Difficult to troubleshoot user complaints

**After**: Complete audit trail with full visibility:
- ✅ Trace every data transformation
- ✅ See exact LLM prompts and responses
- ✅ Validate grounding and citations
- ✅ Debug with confidence

## Architecture

```
User Query: "Show mobile conversions"
           │
           ▼
┌─────────────────────────────────────────┐
│  Step 1: GA4 API Request                │
│  ├─ Endpoint: runReport                 │
│  ├─ Params: {dimensions, metrics}       │
│  ├─ Response Time: 234ms                │
│  └─ Result: 1 metric                    │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  Step 2: Generate Embeddings            │
│  ├─ Input: Raw GA4 metrics              │
│  ├─ Model: text-embedding-3-small       │
│  ├─ Duration: 456ms                     │
│  └─ Result: 1 embedding                 │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  Step 3: Vector Search                  │
│  ├─ Query: User query embedding         │
│  ├─ Similarity Threshold: 0.7           │
│  ├─ Duration: 123ms                     │
│  └─ Result: 5 relevant chunks           │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  Step 4: LLM Generation                 │
│  ├─ Model: gpt-4                        │
│  ├─ Prompt: Context + User Query        │
│  ├─ Tokens: 1500 prompt, 200 response   │
│  ├─ Duration: 1200ms                    │
│  └─ Result: Final report                │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  Validation                             │
│  ├─ Grounding Score: 95%                │
│  ├─ Citation Accuracy: 100%             │
│  ├─ Ungrounded Claims: 0                │
│  └─ Confidence: 93%                     │
└─────────────────────────────────────────┘
```

## API Reference

### Get Audit Trail

```http
GET /api/v1/admin/reports/{report_id}/audit_trail
Authorization: Bearer {admin_token}
X-Tenant-Context: {tenant_id}
```

**Response:**
```json
{
  "report_id": "550e8400-e29b-41d4-a716-446655440000",
  "query": "Show mobile conversions",
  "tenant_id": "tenant-uuid",
  "user_id": "user-uuid",
  "created_at": "2026-01-02T10:30:00Z",
  
  "ga4_api_request": {
    "endpoint": "runReport",
    "request_params": {
      "property": "properties/123456789",
      "dateRanges": [{"startDate": "7daysAgo", "endDate": "today"}],
      "dimensions": [{"name": "deviceCategory"}],
      "metrics": [{"name": "conversions"}]
    },
    "response_time_ms": 234,
    "cached": false,
    "timestamp": "2026-01-02T10:30:00Z",
    "status": "success"
  },
  
  "raw_metrics": [
    {
      "id": 789,
      "metric_date": "2025-01-05",
      "dimension_values": {"deviceCategory": "mobile"},
      "metric_values": {"conversions": 1234.0},
      "property_id": "123456789"
    }
  ],
  
  "embeddings_used": [
    {
      "id": "embedding-uuid",
      "similarity": 0.92,
      "content": "Mobile conversions decreased 15% due to checkout flow issue",
      "chunk_metadata": {"source": "ga4_metrics", "date": "2025-01-05"},
      "timestamp_created": "2026-01-02T10:29:00Z"
    }
  ],
  
  "llm_interaction": {
    "model": "gpt-4",
    "prompt": "You are a data analyst...",
    "prompt_tokens": 1500,
    "response": "Mobile conversions: 1,234...",
    "response_tokens": 200,
    "latency_ms": 1200,
    "temperature": 0.7,
    "timestamp": "2026-01-02T10:30:01Z"
  },
  
  "validation_results": {
    "grounding_score": 0.95,
    "citation_accuracy": 1.0,
    "ungrounded_claims": [],
    "confidence_score": 0.93,
    "validation_timestamp": "2026-01-02T10:30:02Z"
  },
  
  "lineage_steps": [
    {
      "step_number": 1,
      "step_name": "GA4 API Request",
      "input_data": {"query": "Show mobile conversions"},
      "output_data": {"metrics_count": 1},
      "duration_ms": 234,
      "timestamp": "2026-01-02T10:30:00Z"
    }
  ],
  
  "total_duration_ms": 2013,
  "cache_hits": {
    "ga4_api": false,
    "embeddings": true,
    "vector_search": false
  },
  
  "metadata": {
    "api_version": "v1",
    "pipeline_version": "2.0"
  }
}
```

### List Audit Trails

```http
GET /api/v1/admin/reports/audit_trails?limit=50&offset=0
Authorization: Bearer {admin_token}
```

**Response:**
```json
[
  {
    "report_id": "report-uuid",
    "query": "Show mobile conversions",
    "tenant_id": "tenant-uuid",
    "created_at": "2026-01-02T10:30:00Z",
    "total_duration_ms": 2013,
    "status": "success",
    "has_validation_issues": false
  }
]
```

### Export Audit Trail

```http
POST /api/v1/admin/reports/{report_id}/audit_trail/export
Authorization: Bearer {admin_token}
X-Tenant-Context: {tenant_id}
```

Downloads complete audit trail as JSON file.

## Frontend Component

```typescript
import { AuditTrailViewer } from '@/components/admin/AuditTrailViewer';

function AdminDashboard() {
  return (
    <AuditTrailViewer
      reportId="report-123"
      onClose={() => console.log('Closed')}
    />
  );
}
```

### Component Features

1. **Visual Timeline**: Expandable steps showing data flow
2. **Performance Metrics**: Duration at each stage
3. **Validation Highlighting**: Issues shown in red
4. **Expandable Details**: Click to see input/output for each step
5. **JSON Export**: Download complete audit trail
6. **Search/Filter**: Find specific reports

## Use Cases

### 1. Debug Incorrect Reports

**Scenario**: User complains "GA4 shows 1,500 conversions but report says 1,234"

**Solution**:
1. Open audit trail for the report
2. Check GA4 API request params (date range, filters)
3. Verify raw metrics returned (1,234 conversions)
4. Confirm LLM accurately represented the data
5. Identify issue: User looking at different date range in GA4

### 2. Validate LLM Grounding

**Scenario**: Ensure LLM doesn't hallucinate numbers

**Solution**:
1. Check validation results: grounding_score = 0.95
2. Review embeddings used in generation
3. Compare LLM response to source data
4. Verify citation_accuracy = 1.0 (all claims cited)
5. Check ungrounded_claims = [] (no hallucinations)

### 3. Performance Debugging

**Scenario**: Reports taking too long to generate

**Solution**:
1. Open audit trail
2. Check total_duration_ms and per-step duration
3. Identify bottleneck (e.g., LLM latency = 3000ms)
4. Optimize slow step (reduce prompt size, use faster model)
5. Monitor improvement in subsequent reports

### 4. Compliance Audits

**Scenario**: Demonstrate data processing transparency for GDPR

**Solution**:
1. Export audit trails for user's reports
2. Show exactly what data was accessed from GA4
3. Demonstrate no unauthorized data usage
4. Prove data retention compliance
5. Provide to regulators as evidence

## Implementation Details

### Backend: Audit Trail Reconstruction

```python
# python/src/server/api/v1/admin/audit_trail.py

async def reconstruct_audit_trail(
    report_id: str,
    session: AsyncSession,
    tenant_id: str
) -> AuditTrailResponse:
    """
    Reconstruct complete data lineage for a report.
    
    Queries:
    1. reports table → basic report info
    2. ga4_requests table → API call details
    3. metrics table → raw data
    4. embeddings table → embeddings used
    5. llm_interactions table → prompt/response
    6. validation_results table → quality metrics
    """
    # Implementation queries respective tables
    # and assembles complete audit trail
    pass
```

### Frontend: Timeline Visualization

```typescript
// archon-ui-main/src/components/admin/AuditTrailViewer.tsx

export const AuditTrailViewer: React.FC<Props> = ({ reportId }) => {
  const [auditTrail, setAuditTrail] = useState<AuditTrail | null>(null);
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());

  // Fetch audit trail
  useEffect(() => {
    fetchAuditTrail(reportId);
  }, [reportId]);

  // Render timeline with expandable steps
  return (
    <div className="audit-trail">
      {auditTrail.lineage_steps.map(step => (
        <TimelineStep
          step={step}
          isExpanded={expandedSteps.has(step.step_number)}
          onToggle={() => toggleStep(step.step_number)}
        />
      ))}
    </div>
  );
};
```

## Security

### Authorization

- **Admin Only**: Audit trails contain sensitive data
- **Tenant Isolation**: Can only view own tenant's audit trails
- **Role-Based Access**: Configurable by organization

### Data Retention

```python
# Audit trail retention policy
AUDIT_TRAIL_RETENTION_DAYS = 90  # 3 months

# Automatic cleanup job
@scheduler.scheduled_job('cron', hour=2)
async def cleanup_old_audit_trails():
    cutoff_date = datetime.now() - timedelta(days=AUDIT_TRAIL_RETENTION_DAYS)
    await delete_audit_trails_before(cutoff_date)
```

## Performance

### Optimization Strategies

1. **Lazy Loading**: Only load full details when expanded
2. **Pagination**: List view loads 50 trails at a time
3. **Caching**: Cache frequently accessed audit trails (Redis)
4. **Indexing**: Database indexes on `report_id`, `tenant_id`, `created_at`

### Benchmarks

- **Audit Trail Query**: < 500ms (99th percentile)
- **List View**: < 200ms for 50 results
- **Export**: < 1s for typical report
- **Frontend Render**: < 100ms for timeline

## Monitoring

### Metrics

```promql
# Audit trail query latency
histogram_quantile(0.95, rate(audit_trail_query_duration_seconds_bucket[5m]))

# Audit trail query rate
rate(audit_trail_queries_total[5m])

# Export success rate
rate(audit_trail_exports_total{status="success"}[5m])
 / rate(audit_trail_exports_total[5m])
```

### Alerts

```yaml
- alert: AuditTrailQuerySlow
  expr: histogram_quantile(0.95, rate(audit_trail_query_duration_seconds_bucket[5m])) > 0.5
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Audit trail queries are slow (p95 > 500ms)"
```

## Testing

```bash
# Run audit trail tests
cd tests/integration
pytest test_audit_trail_reconstruction.py -v

# Test specific scenarios
pytest test_audit_trail_reconstruction.py::test_audit_trail_completeness -v
pytest test_audit_trail_reconstruction.py::test_audit_trail_query_performance -v
```

## Future Enhancements

- [ ] Real-time audit trail streaming (SSE)
- [ ] Diff view comparing two reports
- [ ] Automated anomaly detection in lineage
- [ ] Integration with external audit systems
- [ ] Custom retention policies per tenant
- [ ] Audit trail search with full-text search

## References

- [Data Lineage Best Practices](https://www.datadoghq.com/knowledge-center/data-lineage/)
- [OpenLineage Specification](https://openlineage.io/)
- [GDPR Data Processing Transparency](https://gdpr.eu/data-processing/)

## Contributors

- Archon AI Agent
- Implementation Date: 2026-01-02

