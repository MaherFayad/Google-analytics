# 🐳 Docker Testing Guide

Complete guide for testing the GA4 Analytics SaaS application using Docker.

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Prerequisites](#prerequisites)
- [Setup Instructions](#setup-instructions)
- [Service Architecture](#service-architecture)
- [Testing Scenarios](#testing-scenarios)
- [Troubleshooting](#troubleshooting)
- [Advanced Usage](#advanced-usage)

## 🚀 Quick Start

### Windows (PowerShell)

```powershell
# Run the automated setup script
.\start-test.ps1
```

### Linux/macOS (Bash)

```bash
# Make script executable
chmod +x start-test.sh

# Run the automated setup script
./start-test.sh
```

### Manual Start

```bash
# 1. Copy environment file
cp .env.example .env

# 2. Edit .env with your credentials
# Required: OPENAI_API_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

# 3. Start all services
docker-compose -f docker-compose.test.yml up -d --build

# 4. Wait for services to be ready (check health)
docker-compose -f docker-compose.test.yml ps

# 5. Run migrations
docker exec ga4-api-test alembic upgrade head

# 6. View logs
docker-compose -f docker-compose.test.yml logs -f
```

## 📦 Prerequisites

### Required Software

- **Docker Desktop** (v20.10+)
  - Windows: [Download](https://www.docker.com/products/docker-desktop)
  - macOS: [Download](https://www.docker.com/products/docker-desktop)
  - Linux: [Install Docker Engine](https://docs.docker.com/engine/install/)
- **Docker Compose** (v2.0+) - Included with Docker Desktop

### Required API Keys

1. **OpenAI API Key**
   - Get from: https://platform.openai.com/api-keys
   - Required for: LLM-powered report generation

2. **Google OAuth Credentials**
   - Get from: https://console.cloud.google.com/apis/credentials
   - Required for: User authentication and GA4 API access
   - Setup:
     1. Create OAuth 2.0 Client ID
     2. Add authorized redirect: `http://localhost:3000/api/auth/callback/google`
     3. Enable Google Analytics API

3. **NextAuth Secret**
   - Generate with: `openssl rand -base64 32`
   - Or use: `test-secret-min-32-chars-long-for-jwt` for testing

## 🏗️ Service Architecture

The test environment includes 7 services:

### Core Services

| Service | Port | Description | Health Check |
|---------|------|-------------|--------------|
| **postgres** | 5432 | PostgreSQL 15 + pgvector | `pg_isready -U postgres` |
| **redis** | 6379 | Redis 7 for caching | `redis-cli ping` |
| **pgbouncer** | 6432 | Connection pooling | Auto-start |
| **api** | 8000 | FastAPI backend | `GET /health` |
| **web** | 3000 | Next.js frontend | `GET /` |

### Monitoring Services

| Service | Port | Credentials | Description |
|---------|------|-------------|-------------|
| **prometheus** | 9090 | - | Metrics collection |
| **grafana** | 3001 | admin/admin | Dashboards |

### Service Dependencies

```
web (Frontend)
  ↓ depends on
api (Backend)
  ↓ depends on
pgbouncer (Connection Pool)
  ↓ depends on
postgres (Database)

api also depends on:
  → redis (Cache)
```

## 🧪 Testing Scenarios

### 1. Frontend Testing

**Access**: http://localhost:3000

**Test Cases**:
- ✅ User authentication (Google OAuth)
- ✅ Dashboard rendering
- ✅ Real-time SSE streaming
- ✅ Chart visualizations
- ✅ Error boundaries

**Hot Reload**: Enabled
- Edit files in `archon-ui-main/src/`
- Changes auto-reload in browser

### 2. Backend API Testing

**Access**: http://localhost:8000/docs (Swagger UI)

**Test Cases**:
- ✅ Health check: `GET /health`
- ✅ Authentication endpoints
- ✅ GA4 data fetching
- ✅ Report generation (SSE)
- ✅ Vector search queries

**Example API Calls**:

```bash
# Health check
curl http://localhost:8000/health

# Get API documentation
curl http://localhost:8000/openapi.json

# Test SSE streaming (requires auth)
curl -N -H "Authorization: Bearer YOUR_JWT" \
  http://localhost:8000/api/v1/reports/stream
```

### 3. Database Testing

**Connection Strings**:

```bash
# Direct connection (for migrations)
postgresql://postgres:postgres@localhost:5432/ga4_analytics

# Via pgBouncer (for application)
postgresql://postgres:postgres@localhost:6432/ga4_analytics
```

**Test Cases**:

```bash
# Connect to database
docker exec -it ga4-postgres-test psql -U postgres -d ga4_analytics

# Check pgvector extension
SELECT * FROM pg_extension WHERE extname = 'vector';

# Check RLS policies
SELECT * FROM pg_policies;

# View tables
\dt

# Check tenant isolation
SELECT tenant_id, COUNT(*) FROM ga4_metrics_raw GROUP BY tenant_id;
```

### 4. Cache Testing

**Test Redis**:

```bash
# Connect to Redis
docker exec -it ga4-redis-test redis-cli

# Check cache keys
KEYS *

# Get cache stats
INFO stats

# Monitor cache operations
MONITOR
```

### 5. Performance Testing

**Connection Pool Monitoring**:

```bash
# Check pgBouncer stats
docker exec -it ga4-pgbouncer-test psql -p 5432 -U postgres pgbouncer -c "SHOW POOLS;"

# Check active connections
docker exec -it ga4-pgbouncer-test psql -p 5432 -U postgres pgbouncer -c "SHOW CLIENTS;"
```

**Grafana Dashboards**: http://localhost:3001
- Login: admin/admin
- Pre-configured dashboards:
  - Database Health
  - Connection Pool Health
  - GA4 Analytics Metrics

### 6. SSE Streaming Testing

**Test graceful shutdown** (Task P0-20):

```bash
# Start streaming in one terminal
curl -N http://localhost:8000/api/v1/reports/stream

# In another terminal, send SIGTERM
docker kill --signal=SIGTERM ga4-api-test

# Expected: Client receives shutdown message and auto-reconnects
```

### 7. Multi-Tenant Testing

**Test tenant isolation**:

```bash
# Create test data for multiple tenants
docker exec -it ga4-postgres-test psql -U postgres -d ga4_analytics

# Insert test data
INSERT INTO users (id, email, tenant_id) VALUES 
  ('user1', 'user1@example.com', 'tenant-1'),
  ('user2', 'user2@example.com', 'tenant-2');

# Test RLS policies
SET app.tenant_id = 'tenant-1';
SELECT * FROM ga4_metrics_raw; -- Should only see tenant-1 data
```

## 🔧 Troubleshooting

### Common Issues

#### 1. Services Won't Start

```bash
# Check Docker is running
docker info

# Check for port conflicts
netstat -an | findstr "3000 8000 5432 6379"  # Windows
lsof -i :3000,8000,5432,6379                 # Linux/macOS

# Clean up and restart
docker-compose -f docker-compose.test.yml down -v
docker-compose -f docker-compose.test.yml up -d --build
```

#### 2. Database Connection Errors

```bash
# Check PostgreSQL logs
docker logs ga4-postgres-test

# Test connection
docker exec ga4-postgres-test pg_isready -U postgres

# Check pgBouncer
docker logs ga4-pgbouncer-test
```

#### 3. Frontend Build Errors

```bash
# Check frontend logs
docker logs ga4-web-test

# Rebuild frontend
docker-compose -f docker-compose.test.yml up -d --build web

# Check Node modules
docker exec ga4-web-test ls -la node_modules
```

#### 4. API Errors

```bash
# Check API logs
docker logs ga4-api-test -f

# Check environment variables
docker exec ga4-api-test env | grep DATABASE_URL

# Test health endpoint
curl http://localhost:8000/health
```

#### 5. Migration Errors

```bash
# Check migration status
docker exec ga4-api-test alembic current

# View migration history
docker exec ga4-api-test alembic history

# Rollback one migration
docker exec ga4-api-test alembic downgrade -1

# Re-run migrations
docker exec ga4-api-test alembic upgrade head
```

### Debug Mode

Enable debug logging:

```bash
# Edit .env
LOG_LEVEL=DEBUG
SQL_ECHO=true

# Restart services
docker-compose -f docker-compose.test.yml restart api
```

### View All Logs

```bash
# All services
docker-compose -f docker-compose.test.yml logs -f

# Specific service
docker-compose -f docker-compose.test.yml logs -f api

# Last 100 lines
docker-compose -f docker-compose.test.yml logs --tail=100
```

## 🎯 Advanced Usage

### Running Tests Inside Containers

```bash
# Run backend tests
docker exec ga4-api-test pytest

# Run with coverage
docker exec ga4-api-test pytest --cov=src --cov-report=html

# Run specific test file
docker exec ga4-api-test pytest tests/integration/test_ga4_pipeline.py

# Run security tests
docker exec ga4-api-test pytest tests/security/
```

### Database Backup and Restore

```bash
# Backup database
docker exec ga4-postgres-test pg_dump -U postgres ga4_analytics > backup.sql

# Restore database
cat backup.sql | docker exec -i ga4-postgres-test psql -U postgres ga4_analytics
```

### Custom Configuration

Create `docker-compose.override.yml` for local customizations:

```yaml
version: '3.8'

services:
  api:
    environment:
      LOG_LEVEL: DEBUG
      ENABLE_MOCK_GA4: true
    volumes:
      - ./custom-config:/app/config
```

### Scaling Services

```bash
# Scale API instances (requires load balancer)
docker-compose -f docker-compose.test.yml up -d --scale api=3
```

### Resource Limits

Add to `docker-compose.test.yml`:

```yaml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

## 🧹 Cleanup

### Stop Services

```bash
# Stop all services (keep data)
docker-compose -f docker-compose.test.yml stop

# Stop and remove containers (keep volumes)
docker-compose -f docker-compose.test.yml down

# Remove everything including volumes
docker-compose -f docker-compose.test.yml down -v
```

### Clean Docker System

```bash
# Remove unused images
docker image prune -a

# Remove unused volumes
docker volume prune

# Remove everything (careful!)
docker system prune -a --volumes
```

## 📊 Monitoring

### Prometheus Queries

Access: http://localhost:9090

**Useful Queries**:

```promql
# API request rate
rate(http_requests_total[5m])

# Database connections
pg_stat_database_numbackends

# Redis memory usage
redis_memory_used_bytes

# SSE active connections
sse_active_connections
```

### Grafana Dashboards

Access: http://localhost:3001 (admin/admin)

**Pre-configured Dashboards**:
1. **System Overview**: CPU, memory, network
2. **Database Health**: Connections, queries, locks
3. **Connection Pool**: pgBouncer metrics
4. **GA4 Analytics**: API calls, quotas, errors

## 🔐 Security Notes

### For Testing Only

⚠️ **This configuration is for TESTING only**:
- Default passwords (postgres/postgres)
- Debug logging enabled
- CORS wide open
- No TLS/SSL
- Mock GA4 data enabled

### Production Checklist

Before deploying to production:
- [ ] Change all default passwords
- [ ] Enable TLS/SSL certificates
- [ ] Restrict CORS origins
- [ ] Disable debug logging
- [ ] Enable rate limiting
- [ ] Configure proper secrets management
- [ ] Set up proper monitoring/alerting
- [ ] Enable backup strategies
- [ ] Configure firewall rules
- [ ] Review RLS policies

## 📚 Additional Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Next.js Documentation](https://nextjs.org/docs)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [pgvector Documentation](https://github.com/pgvector/pgvector)

## 🆘 Getting Help

If you encounter issues:

1. Check logs: `docker-compose -f docker-compose.test.yml logs -f`
2. Check service health: `docker-compose -f docker-compose.test.yml ps`
3. Review this guide's troubleshooting section
4. Create a task in Archon project with error details

---

**Happy Testing! 🚀**

