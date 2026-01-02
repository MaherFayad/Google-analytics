# 🚀 Quick Start - Docker Testing Environment

Get the GA4 Analytics SaaS application running in under 5 minutes!

## ⚡ Super Quick Start

### Windows Users

1. **Open PowerShell** (as Administrator)
2. **Run the script**:
   ```powershell
   .\start-test.ps1
   ```
3. **Done!** 🎉

### Linux/macOS Users

1. **Open Terminal**
2. **Run the script**:
   ```bash
   chmod +x start-test.sh
   ./start-test.sh
   ```
3. **Done!** 🎉

## 📋 What You Need

### Before You Start

1. **Docker Desktop** - [Download here](https://www.docker.com/products/docker-desktop)
   - Make sure it's running before you start!

2. **API Keys** (Get these ready):
   - **OpenAI API Key**: https://platform.openai.com/api-keys
   - **Google OAuth Credentials**: https://console.cloud.google.com/apis/credentials
     - Create OAuth 2.0 Client ID
     - Add redirect: `http://localhost:3000/api/auth/callback/google`
     - Enable Google Analytics API

3. **Generate NextAuth Secret**:
   ```bash
   # Windows PowerShell
   [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((New-Guid).ToString()))
   
   # Linux/macOS
   openssl rand -base64 32
   ```

## 🎯 What Gets Installed

The automated script will set up **7 services**:

| Service | URL | Description |
|---------|-----|-------------|
| 🌐 **Frontend** | http://localhost:3000 | Next.js web app |
| ⚙️ **API** | http://localhost:8000 | FastAPI backend |
| 📊 **Grafana** | http://localhost:3001 | Dashboards (admin/admin) |
| 📈 **Prometheus** | http://localhost:9090 | Metrics |
| 🗄️ **PostgreSQL** | localhost:5432 | Database |
| 🔴 **Redis** | localhost:6379 | Cache |
| 🔀 **pgBouncer** | localhost:6432 | Connection pool |

## 📝 Step-by-Step Manual Setup

If you prefer to do it manually:

### Step 1: Clone and Navigate

```bash
cd "Google analytics"
```

### Step 2: Configure Environment

```bash
# Copy the example file
cp env.example .env

# Edit .env with your favorite editor
notepad .env       # Windows
nano .env          # Linux
vim .env           # macOS
```

**Required values in .env**:
```env
OPENAI_API_KEY=sk-proj-YOUR_KEY_HERE
GOOGLE_CLIENT_ID=YOUR_CLIENT_ID.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=YOUR_CLIENT_SECRET
NEXTAUTH_SECRET=YOUR_GENERATED_SECRET_32_CHARS_MIN
```

### Step 3: Start Services

```bash
# Start all services
docker-compose -f docker-compose.test.yml up -d --build

# This will:
# ✅ Download Docker images (first time only)
# ✅ Build frontend and backend
# ✅ Start all 7 services
# ✅ Set up database with pgvector
# ✅ Configure connection pooling
```

### Step 4: Wait for Services (2-3 minutes)

```bash
# Check status
docker-compose -f docker-compose.test.yml ps

# All services should show "healthy" or "running"
```

### Step 5: Run Database Migrations

```bash
docker exec ga4-api-test alembic upgrade head
```

### Step 6: Open Your Browser

- **Frontend**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs

## ✅ Verify Everything Works

### 1. Check API Health

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected"
}
```

### 2. Check Frontend

Open http://localhost:3000 - you should see the login page.

### 3. Check Database

```bash
docker exec -it ga4-postgres-test psql -U postgres -d ga4_analytics -c "SELECT version();"
```

### 4. Check Redis

```bash
docker exec ga4-redis-test redis-cli ping
```

Expected: `PONG`

## 🎮 What Can You Test?

### Frontend Features
- ✅ User authentication (Google OAuth)
- ✅ Dashboard with real-time updates
- ✅ SSE streaming for reports
- ✅ Chart visualizations
- ✅ Responsive design
- ✅ Error handling

### Backend Features
- ✅ RESTful API endpoints
- ✅ SSE streaming
- ✅ GA4 data fetching
- ✅ Vector search (pgvector)
- ✅ Multi-tenant isolation
- ✅ Connection pooling
- ✅ Rate limiting
- ✅ Caching

### Infrastructure
- ✅ Database migrations
- ✅ Connection pooling (pgBouncer)
- ✅ Metrics collection (Prometheus)
- ✅ Dashboards (Grafana)
- ✅ Health checks

## 🔍 Viewing Logs

### All Services
```bash
docker-compose -f docker-compose.test.yml logs -f
```

### Specific Service
```bash
# Frontend
docker-compose -f docker-compose.test.yml logs -f web

# Backend
docker-compose -f docker-compose.test.yml logs -f api

# Database
docker-compose -f docker-compose.test.yml logs -f postgres
```

### Last 50 Lines
```bash
docker-compose -f docker-compose.test.yml logs --tail=50
```

## 🛑 Stopping Services

### Keep Data (Recommended)
```bash
docker-compose -f docker-compose.test.yml stop
```

### Remove Containers (Keep Data)
```bash
docker-compose -f docker-compose.test.yml down
```

### Remove Everything (Clean Slate)
```bash
docker-compose -f docker-compose.test.yml down -v
```

## 🔧 Common Issues & Solutions

### Issue: "Port already in use"

**Solution**: Another service is using the port.

```bash
# Windows - Find what's using port 3000
netstat -ano | findstr :3000

# Linux/macOS - Find what's using port 3000
lsof -i :3000

# Kill the process or change the port in docker-compose.test.yml
```

### Issue: "Docker is not running"

**Solution**: Start Docker Desktop and wait for it to fully start.

### Issue: "Cannot connect to database"

**Solution**: Wait longer, or check logs:

```bash
docker logs ga4-postgres-test
docker logs ga4-pgbouncer-test
```

### Issue: "Frontend shows connection error"

**Solution**: Make sure API is running:

```bash
curl http://localhost:8000/health
docker logs ga4-api-test
```

### Issue: "Build fails with memory error"

**Solution**: Increase Docker memory:
- Docker Desktop → Settings → Resources → Memory
- Increase to at least 4GB

## 🧪 Running Tests

### Backend Tests
```bash
# All tests
docker exec ga4-api-test pytest

# With coverage
docker exec ga4-api-test pytest --cov=src --cov-report=html

# Specific test
docker exec ga4-api-test pytest tests/integration/test_ga4_pipeline.py

# Security tests
docker exec ga4-api-test pytest tests/security/
```

### Frontend Tests
```bash
# Run tests
docker exec ga4-web-test npm test

# Run linter
docker exec ga4-web-test npm run lint
```

## 🔄 Hot Reload (Development)

Both frontend and backend support hot reload:

### Frontend
- Edit files in `archon-ui-main/src/`
- Browser auto-refreshes

### Backend
- Edit files in `python/src/`
- API auto-reloads

## 📊 Monitoring

### Grafana Dashboards

1. Open: http://localhost:3001
2. Login: `admin` / `admin`
3. View pre-configured dashboards:
   - System Overview
   - Database Health
   - Connection Pool Metrics
   - GA4 Analytics

### Prometheus Metrics

1. Open: http://localhost:9090
2. Try queries:
   ```promql
   # Request rate
   rate(http_requests_total[5m])
   
   # Database connections
   pg_stat_database_numbackends
   
   # Redis memory
   redis_memory_used_bytes
   ```

## 🎓 Next Steps

1. **Read the full guide**: [DOCKER_TESTING_GUIDE.md](./DOCKER_TESTING_GUIDE.md)
2. **Explore the API**: http://localhost:8000/docs
3. **Check the architecture**: [README.md](./README.md)
4. **Run tests**: See "Running Tests" section above
5. **Monitor metrics**: http://localhost:3001

## 🆘 Need Help?

1. **Check logs**: `docker-compose -f docker-compose.test.yml logs -f`
2. **Check service status**: `docker-compose -f docker-compose.test.yml ps`
3. **Read full guide**: [DOCKER_TESTING_GUIDE.md](./DOCKER_TESTING_GUIDE.md)
4. **Check troubleshooting**: See "Common Issues" section above

## 🎉 Success Checklist

- [ ] Docker Desktop is running
- [ ] All 7 services are up (green/healthy)
- [ ] Frontend loads at http://localhost:3000
- [ ] API responds at http://localhost:8000/health
- [ ] Database migrations completed
- [ ] Can view logs without errors
- [ ] Grafana dashboards visible at http://localhost:3001

**If all checked, you're ready to test! 🚀**

---

**Built with ❤️ using Docker, FastAPI, and Next.js**

