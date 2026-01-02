# Google Analytics 4 SaaS Chat & Report Generator

> **Enterprise-grade AI-powered analytics platform** that transforms GA4 data into actionable insights through conversational AI and automated reporting.

## 🎯 Project Overview

This system bridges the gap between GA4's complexity and stakeholder needs by providing:

- **Conversational Analytics**: Natural language queries → Structured reports
- **Multi-Agent Architecture**: Specialized AI agents for data fetching, embedding, retrieval, and reporting
- **Real-time Streaming**: Server-Sent Events (SSE) for progressive report generation
- **Multi-Tenant SaaS**: Secure tenant isolation with Row-Level Security (RLS)
- **Vector Search**: Semantic pattern matching using pgvector for predictive analytics

## 🏗️ Architecture

### Agent Framework: Pydantic-AI (ADR-001)

**Decision**: Unified on Pydantic-AI for all agents (replacing CrewAI)

**Rationale**:
- ✅ Type-safe agent-to-agent communication with Pydantic V2
- ✅ Async-first architecture for SSE streaming
- ✅ Native FastAPI integration
- ✅ Future-proof with modern Python 3.11+ features

### Agent Pipeline

```
User Query
    ↓
OrchestratorAgent
    ↓
┌───────────────────┬──────────────────┬─────────────────┬──────────────────┐
│ DataFetcherAgent  │ EmbeddingAgent   │ RagAgent        │ ReportingAgent   │
│ (GA4 API)         │ (OpenAI)         │ (pgvector)      │ (LLM + Charts)   │
└───────────────────┴──────────────────┴─────────────────┴──────────────────┘
    ↓
Structured Report (JSON) → Frontend (React/Next.js)
```

### Tech Stack

**Backend**:
- **FastAPI** - Async web framework
- **Pydantic-AI** - Type-safe AI agent framework
- **SQLModel** - ORM with Pydantic integration
- **PostgreSQL + pgvector** - Vector database for semantic search
- **Redis** - Caching and rate limiting
- **Supabase Vault** - Encrypted credential storage

**Frontend**:
- **Next.js 14** - React framework with App Router
- **NextAuth.js** - OAuth2 authentication
- **Shadcn UI** - Component library
- **Recharts** - Data visualization
- **TanStack Query** - Server state management

**Infrastructure**:
- **Docker Compose** - Local development
- **Prometheus + Grafana** - Monitoring
- **Sentry** - Error tracking
- **pgBouncer** - Connection pooling

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- PostgreSQL 15+ (with pgvector extension)
- Google Cloud Project (for GA4 API access)

### 1. Clone and Setup

```bash
git clone <repository-url>
cd "Google analytics"

# Install Python dependencies
cd python
poetry install
poetry shell

# Install frontend dependencies
cd ../archon-ui-main
npm install
```

### 2. Environment Configuration

Create `.env` file in project root:

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ga4_analytics
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key

# Redis
REDIS_URL=redis://localhost:6379

# OpenAI
OPENAI_API_KEY=sk-...

# Google OAuth & GA4
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
NEXTAUTH_SECRET=your-nextauth-secret
NEXTAUTH_URL=http://localhost:3000

# Monitoring
SENTRY_DSN=https://...@sentry.io/...
```

### 3. Start Services

```bash
# Start infrastructure (Postgres, Redis, pgBouncer)
docker-compose up -d

# Run database migrations
cd python
alembic upgrade head

# Start backend API
uvicorn src.server.main:app --reload --port 8000

# Start frontend (in separate terminal)
cd archon-ui-main
npm run dev
```

### 4. Access Application

- **Frontend**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs
- **Grafana**: http://localhost:3001 (admin/admin)

## 📋 Project Status

### ✅ Completed Tasks

- [x] **P0-17**: Agent Framework Unification (Pydantic-AI)
  - ADR-001 documented
  - Base agent infrastructure
  - GA4 tool implementation
  - Typed result schemas

### 🚧 In Progress

- [ ] **Task 1.1a**: Git Repository & Directory Structure
- [ ] **Task 1.2a**: Poetry Project Setup
- [ ] **Task 1.1b**: Docker Compose Configuration

### 📝 Upcoming (Priority Order)

1. **P0-2**: Server-Side Tenant Derivation & Validation (CRITICAL-SECURITY)
2. **P0-3**: Vector Search Tenant Isolation Tests (CRITICAL-SECURITY)
3. **P0-1**: Agent Implementation (DataFetcher, Embedding, RAG, Reporting)
4. **P0-4**: GA4 API Resilience Layer (Circuit breaker, retry logic)
5. **P0-6**: Database Connection Pooling for SSE

See [Archon Project Dashboard](https://archon.example.com/projects/88227638-92f2-40e5-afb1-805767d35650) for full task list.

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test suite
pytest tests/unit/test_agents/
pytest tests/integration/test_ga4_pipeline.py

# Run security tests
pytest tests/security/test_tenant_isolation.py
```

## 📚 Documentation

- [Architecture Decision Records](docs/architecture/adr/)
  - [ADR-001: Agent Framework Unification](docs/architecture/adr/ADR-001-agent-framework-unification.md)
- [API Documentation](http://localhost:8000/docs) (when running)
- [Agent Schemas](python/src/agents/schemas/results.py)

## 🔒 Security

### Multi-Tenant Isolation

- **Row-Level Security (RLS)**: PostgreSQL policies enforce tenant isolation
- **JWT Validation**: Server-side tenant derivation from NextAuth JWT
- **Vector Search Isolation**: pgvector queries automatically filtered by tenant_id
- **Encrypted Credentials**: OAuth tokens stored in Supabase Vault with pgsodium

### Compliance

- **GDPR**: Tenant data export and deletion APIs
- **SOC 2**: Audit trail for all data transformations
- **WCAG 2.1 AA**: Accessible chart visualizations

## 🤝 Contributing

1. Create feature branch from `main`
2. Follow code style (Black, Ruff, MyPy)
3. Add tests (minimum 80% coverage)
4. Update documentation
5. Submit PR with Archon task reference

## 📄 License

Proprietary - All rights reserved

## 🙋 Support

- **Archon OS**: Task tracking and project management
- **Documentation**: See `/docs` directory
- **Issues**: Create task in Archon project

---

**Built with ❤️ using Pydantic-AI, FastAPI, and Next.js**

