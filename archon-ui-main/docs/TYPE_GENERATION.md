# Type Generation Documentation

## Overview

This project implements **Task P0-35: Enforce Chart Schema with Pydantic → OpenAPI → TypeScript** to ensure compile-time type safety between backend and frontend.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Backend (Python)                         │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Pydantic Schemas (python/src/agents/schemas/charts.py) │ │
│  │                                                          │ │
│  │  class LineChartConfig(BaseModel):                      │ │
│  │      type: Literal["line"]                              │ │
│  │      title: str                                         │ │
│  │      data: List[ChartDataPoint]                         │ │
│  └────────────────────────────────────────────────────────┘ │
│                           ↓                                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  FastAPI OpenAPI Spec                                   │ │
│  │  GET /openapi.json                                      │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              Type Generation Script (Node.js)                │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  scripts/generate-types.js                             │ │
│  │                                                          │ │
│  │  1. Fetch OpenAPI spec                                  │ │
│  │  2. Generate TypeScript types (openapi-typescript)      │ │
│  │  3. Extract chart types                                 │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   Frontend (TypeScript)                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Generated Types (src/types/charts.generated.ts)       │ │
│  │                                                          │ │
│  │  export type LineChartConfig = {                        │ │
│  │    type: 'line';                                        │ │
│  │    title: string;                                       │ │
│  │    data: ChartDataPoint[];                              │ │
│  │  };                                                     │ │
│  └────────────────────────────────────────────────────────┘ │
│                           ↓                                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  TypeSafeChartRenderer Component                        │ │
│  │                                                          │ │
│  │  function render(config: ChartConfig) {                 │ │
│  │    switch (config.type) {                               │ │
│  │      case 'line': // TypeScript knows exact fields!     │ │
│  │        return <LineChart data={config.data} />;         │ │
│  │    }                                                    │ │
│  │  }                                                      │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Benefits

### 1. Compile-Time Safety

**Before (Runtime Crash):**
```typescript
// Backend sends: { "type": "line", "data": [...] }
// Frontend expects: { "chart_type": "line", "data": [...] }

function render(config: any) {
  return <LineChart type={config.chart_type} />; // ❌ undefined at runtime
}
```

**After (Compile-Time Error):**
```typescript
import { ChartConfig } from '@/types/charts.generated';

function render(config: ChartConfig) {
  return <LineChart type={config.chart_type} />; 
  // ❌ TypeScript error: Property 'chart_type' does not exist. Did you mean 'type'?
}
```

### 2. Automatic Synchronization

When backend schema changes:
```python
# Backend: Add new field to LineChartConfig
class LineChartConfig(BaseModel):
    type: Literal["line"]
    title: str
    data: List[ChartDataPoint]
    show_legend: bool = True  # New field!
```

Frontend types automatically update after running `npm run generate:types`:
```typescript
// TypeScript now knows about show_legend
config.show_legend  // ✅ Type-safe
```

### 3. LLM Error Prevention

Pydantic validates LLM-generated data before it reaches frontend:
```python
# LLM generates invalid data
llm_output = {
    "type": "line",
    "data": [{"x": "2025-01-01", "y": "1234"}]  # y is string!
}

# Pydantic coerces and validates
validated = LineChartConfig(**llm_output)
# ✅ validated.data[0].y == 1234.0 (now a float)
```

## Usage

### Setup

1. **Install dependencies:**
   ```bash
   npm install -D openapi-typescript
   ```

2. **Start backend server:**
   ```bash
   cd ../python
   uvicorn src.server.main:app --reload
   ```

3. **Generate types:**
   ```bash
   npm run generate:types
   ```

### Development Workflow

```bash
# Terminal 1: Backend server
cd python
uvicorn src.server.main:app --reload

# Terminal 2: Frontend dev server
cd archon-ui-main
npm run dev

# Terminal 3: Watch mode for type generation (optional)
cd archon-ui-main
npm run generate:types --watch
```

### Using Generated Types

#### Import Types
```typescript
import { 
  ChartConfig, 
  LineChartConfig,
  isLineChart 
} from '@/types/charts.generated';
```

#### Type-Safe Component
```typescript
import { TypeSafeChartRenderer } from '@/components/charts/TypeSafeChartRenderer';

function MyDashboard() {
  const [chartData, setChartData] = useState<ChartConfig[]>([]);

  useEffect(() => {
    // Fetch chart data from API
    fetch('/api/v1/analytics/charts')
      .then(res => res.json())
      .then(data => setChartData(data.charts));
  }, []);

  return (
    <div>
      {chartData.map((chart, i) => (
        <TypeSafeChartRenderer key={i} config={chart} />
      ))}
    </div>
  );
}
```

#### Type Guards
```typescript
function processChart(config: ChartConfig) {
  if (isLineChart(config)) {
    // TypeScript knows: config is LineChartConfig
    console.log(config.x_label);  // ✅ Type-safe
  } else if (isBarChart(config)) {
    // TypeScript knows: config is BarChartConfig
    console.log(config.horizontal);  // ✅ Type-safe
  }
}
```

## Troubleshooting

### "Cannot find module '@/types/charts.generated'"

**Cause:** Types haven't been generated yet.

**Solution:**
```bash
npm run generate:types
```

### "Backend not available"

**Cause:** Backend server isn't running.

**Solution:**
```bash
cd ../python
uvicorn src.server.main:app --reload
```

### "Failed to generate TypeScript types"

**Cause:** `openapi-typescript` not installed.

**Solution:**
```bash
npm install -D openapi-typescript
```

### Types are outdated

**Cause:** Backend schemas changed but types weren't regenerated.

**Solution:**
```bash
npm run generate:types
```

## CI/CD Integration

Add type generation to your CI pipeline:

```yaml
# .github/workflows/ci.yml
name: CI

on: [push, pull_request]

jobs:
  type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      # Start backend
      - name: Start backend
        run: |
          cd python
          pip install -r requirements.txt
          uvicorn src.server.main:app &
          sleep 5
      
      # Generate types
      - name: Generate types
        run: |
          cd archon-ui-main
          npm install
          npm run generate:types
      
      # Type check
      - name: TypeScript type check
        run: |
          cd archon-ui-main
          npm run type-check
```

## Related Documentation

- [Task P0-35: Chart Schema Enforcement](../docs/tasks/P0-35.md)
- [Pydantic Chart Schemas](../../python/src/agents/schemas/charts.py)
- [Backend API Documentation](http://localhost:8000/docs)

## FAQ

**Q: Do I need to regenerate types every time I change backend schemas?**  
A: Yes. Run `npm run generate:types` after any Pydantic schema change.

**Q: Can I edit the generated types?**  
A: No. Generated files are overwritten on each run. If you need custom types, create them in a separate file.

**Q: What if the backend returns data that doesn't match the schema?**  
A: Pydantic validates on the backend, so invalid data never reaches the frontend. If validation fails, the API returns 422 error.

**Q: Can I use these types for API request bodies too?**  
A: Yes! The generated `api.generated.ts` includes all request/response types from your OpenAPI spec.

