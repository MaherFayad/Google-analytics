# ADR-001: Agent Framework Unification (Pydantic-AI)

## Status
**ACCEPTED** - 2026-01-02

## Context
Task 3.1 implements `GoogleAnalyticsTool` using CrewAI framework, while Task 13 designs orchestration using Pydantic-AI framework. These are **INCOMPATIBLE** and will cause runtime failures when agents attempt to communicate.

### The Problem
- **CrewAI**: Class-based agents with `BaseTool` subclassing, synchronous execution model
- **Pydantic-AI**: Function-based tools with async-first design, native Pydantic V2 integration
- **Conflict**: Cannot mix CrewAI agents with Pydantic-AI orchestrator without complex adapter layers

### Impact
- All agent implementation work (P0-1, Task 13) is **BLOCKED** until framework decision is made
- Choosing wrong framework risks technical debt and refactoring costs

## Decision
**Adopt Pydantic-AI as the unified agent framework** across all agents (DataFetcherAgent, EmbeddingAgent, RagAgent, ReportingAgent, OrchestratorAgent).

## Rationale

### 1. Type Safety (CRITICAL for Production)
```python
# Pydantic-AI: Compile-time type checking
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel

class GA4Response(BaseModel):
    sessions: int
    conversions: int
    
agent = Agent[GA4Response](...)  # Type-safe result contract

# CrewAI: Runtime-only validation
class GoogleAnalyticsTool(BaseTool):
    def _run(self, **kwargs) -> str:  # Untyped string return
        return json.dumps(result)
```

### 2. Async-First Architecture (CRITICAL for SSE Streaming)
```python
# Pydantic-AI: Native async support
async def fetch_ga4_data(ctx: RunContext) -> GA4Response:
    async with httpx.AsyncClient() as client:
        response = await client.post(...)
    return GA4Response(**response.json())

# CrewAI: Synchronous execution blocks SSE
def _run(self, **kwargs) -> str:
    response = requests.post(...)  # Blocks event loop
    return response.text
```

### 3. FastAPI Integration
Both FastAPI and Pydantic-AI use Pydantic V2 models, enabling:
- Shared schemas between API endpoints and agents
- OpenAPI spec generation from agent contracts
- Zero-copy data passing (no serialization overhead)

### 4. Community Momentum (2025+)
- **Pydantic-AI**: Active development, async-first, modern Python 3.11+ features
- **CrewAI**: Primarily synchronous, slower iteration cycle

## Implementation Plan

### Phase 1: Base Agent Infrastructure (Task P0-17)
1. Create `python/src/agents/base_agent.py` with Pydantic-AI `Agent` wrapper
2. Define typed result contracts in `python/src/agents/schemas/results.py`
3. Implement GA4 tool as Pydantic-AI function in `python/src/agents/tools/ga4_tool.py`

### Phase 2: Agent Implementations (Task P0-1)
1. DataFetcherAgent - Fetches GA4 data with retry logic
2. EmbeddingAgent - Generates embeddings with quality validation
3. RagAgent - Retrieves context with tenant enforcement
4. ReportingAgent - Generates structured reports

### Phase 3: Orchestration (Task 13, Task P0-18)
1. OrchestratorAgent coordinates multi-agent workflow
2. Async execution with SSE streaming (Task P0-12)
3. Circuit breakers and error recovery

## Consequences

### Positive
✅ Type-safe agent-to-agent communication  
✅ Native async/await support for SSE streaming  
✅ Cleaner FastAPI integration  
✅ Future-proof architecture  

### Negative
⚠️ Deprecates existing CrewAI `GoogleAnalyticsTool` from Task 3.1  
⚠️ Team must learn Pydantic-AI patterns (estimated 2-4 hours)  

### Migration Path
- Task 3.1 (`GoogleAnalyticsTool`) will be **deprecated** and replaced by `python/src/agents/tools/ga4_tool.py`
- No backward compatibility layer needed (greenfield project)

## References
- [Pydantic-AI Documentation](https://ai.pydantic.dev/)
- Task P0-1: Agent Implementation & Orchestrator Integration
- Task 13: Agent Orchestration Layer
- Task P0-12: Async Agent Execution with Streaming

## Approval
- **Architect**: Approved
- **Lead Engineer**: Approved
- **Date**: 2026-01-02

