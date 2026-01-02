# 🐳 Docker Frontend Setup Guide

Complete guide to run the GA4 Analytics SaaS frontend in Docker.

## 🚀 Quick Start

### Option 1: Run Frontend Only

```bash
# From project root
docker-compose up web
```

### Option 2: Run Full Stack (Backend + Frontend)

```bash
# From project root
docker-compose up -d
```

The frontend will be available at: **http://localhost:3000**

## 📋 Prerequisites

Before starting:

1. ✅ Docker and Docker Compose installed
2. ✅ Environment variables configured (see below)
3. ✅ Backend services running (postgres, redis)

## ⚙️ Configuration

### Step 1: Create `.env` File

Create a `.env` file in the **project root** (not in archon-ui-main):

```bash
# Copy from example
cp env.example .env

# Or create manually
touch .env
```

### Step 2: Configure Environment Variables

Edit `.env` with your settings:

```env
# NextAuth Secret (required)
NEXTAUTH_SECRET=your-secret-here

# Google OAuth (optional for initial testing)
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret

# OpenAI (for backend)
OPENAI_API_KEY=your-openai-api-key

# Sentry (optional)
SENTRY_DSN=
```

**Generate NextAuth Secret:**
```bash
openssl rand -base64 32
```

## 🎯 Docker Compose Services

The `docker-compose.yml` includes:

- **postgres** - Database with pgvector (Port 5432)
- **redis** - Caching and rate limiting (Port 6379)
- **pgbouncer-transactional** - Connection pooling (Port 6432)
- **pgbouncer-session** - Session pooling (Port 6433)
- **api** - FastAPI backend (Port 8000)
- **web** - Next.js frontend (Port 3000)
- **prometheus** - Metrics collection (Port 9090)
- **grafana** - Dashboards (Port 3001)

## 📦 Running the Frontend

### Start All Services

```bash
# From project root
docker-compose up -d
```

This will:
1. Build the frontend image (if not built)
2. Start all containers
3. Set up networking between services

### View Logs

```bash
# All services
docker-compose logs -f

# Frontend only
docker-compose logs -f web

# Backend only
docker-compose logs -f api
```

### Check Status

```bash
docker-compose ps
```

Expected output:
```
NAME                  STATUS              PORTS
ga4-web               Up                  0.0.0.0:3000->3000/tcp
ga4-api               Up                  0.0.0.0:8000->8000/tcp
ga4-postgres          Up (healthy)        0.0.0.0:5432->5432/tcp
ga4-redis             Up (healthy)        0.0.0.0:6379->6379/tcp
...
```

## 🔄 Development Workflow

### Hot Reload

The development Dockerfile (`Dockerfile.dev`) is configured for hot reload:

1. Edit files in `archon-ui-main/`
2. Changes are automatically detected
3. Browser refreshes automatically

**Note**: Changes to `package.json` require rebuild:
```bash
docker-compose up -d --build web
```

### Rebuild Frontend

```bash
# Rebuild without cache
docker-compose build --no-cache web

# Rebuild and restart
docker-compose up -d --build web
```

### Access Container Shell

```bash
# Access frontend container
docker exec -it ga4-web sh

# Inside container
npm run build        # Build production
npm run lint        # Run linter
npm run type-check  # Type checking
```

## 🧪 Testing in Docker

### 1. Health Check

```bash
# Check if frontend is responding
curl http://localhost:3000

# Check backend API
curl http://localhost:8000/health
```

### 2. Test Pages

Open in browser:
- Landing: http://localhost:3000
- Sign In: http://localhost:3000/auth/signin
- Dashboard: http://localhost:3000/dashboard

### 3. Check Logs for Errors

```bash
docker-compose logs -f web | grep -i error
```

## 🐛 Troubleshooting

### Issue: "Cannot connect to backend"

**Symptom**: Frontend shows connection errors

**Solution**:
```bash
# Check if backend is running
docker-compose ps api

# View backend logs
docker-compose logs api

# Restart backend
docker-compose restart api
```

### Issue: "Hot reload not working"

**Symptom**: File changes don't trigger reload

**Solution**:
```bash
# Stop and rebuild
docker-compose down
docker-compose up -d --build web

# Check WATCHPACK_POLLING is set
docker exec -it ga4-web env | grep WATCHPACK
```

### Issue: "Port 3000 already in use"

**Symptom**: Cannot start frontend container

**Solution**:
```bash
# Find process using port 3000
lsof -i :3000  # Mac/Linux
netstat -ano | findstr :3000  # Windows

# Kill the process or change port in docker-compose.yml:
# ports:
#   - "3001:3000"  # Use 3001 instead
```

### Issue: "Module not found" errors

**Symptom**: Import errors in logs

**Solution**:
```bash
# Reinstall dependencies
docker-compose exec web npm install

# Or rebuild
docker-compose build --no-cache web
docker-compose up -d web
```

### Issue: "Environment variables not loaded"

**Symptom**: App can't find API_BASE_URL

**Solution**:
```bash
# Check .env file exists in project root
ls -la .env

# View environment in container
docker-compose exec web env | grep NEXT_PUBLIC

# Restart to load new .env
docker-compose down
docker-compose up -d
```

## 📊 Monitoring

### View Container Stats

```bash
docker stats ga4-web
```

### Check Logs in Real-Time

```bash
# All logs
docker-compose logs -f web

# Only errors
docker-compose logs -f web 2>&1 | grep -i error

# Last 100 lines
docker-compose logs --tail=100 web
```

### Access Grafana Dashboard

1. Open http://localhost:3001
2. Login: `admin` / `admin`
3. View frontend metrics (if configured)

## 🚀 Production Deployment

### Build Production Image

```bash
# Use production Dockerfile
docker-compose -f docker-compose.prod.yml build web
```

### Production Configuration

Create `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  web:
    build:
      context: ./archon-ui-main
      dockerfile: Dockerfile  # Production Dockerfile
    container_name: ga4-web-prod
    environment:
      NEXT_PUBLIC_API_BASE_URL: https://api.yourdomain.com/api/v1
      NEXT_PUBLIC_API_URL: https://api.yourdomain.com
      NEXTAUTH_URL: https://yourdomain.com
      NEXTAUTH_SECRET: ${NEXTAUTH_SECRET}
      GOOGLE_CLIENT_ID: ${GOOGLE_CLIENT_ID}
      GOOGLE_CLIENT_SECRET: ${GOOGLE_CLIENT_SECRET}
      NODE_ENV: production
    ports:
      - "3000:3000"
    depends_on:
      - api
    restart: unless-stopped
    networks:
      - ga4-network
```

## 🔧 Docker Commands Reference

### Basic Commands

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# Restart frontend
docker-compose restart web

# View logs
docker-compose logs -f web

# Rebuild
docker-compose build web

# Remove all containers and volumes
docker-compose down -v
```

### Advanced Commands

```bash
# Scale frontend (multiple instances)
docker-compose up -d --scale web=3

# Update environment variables
docker-compose up -d --force-recreate web

# Export logs
docker-compose logs web > frontend-logs.txt

# Clean up unused images
docker system prune -a
```

## 📁 Volume Mounts

The development setup mounts these directories:

```yaml
volumes:
  - ./archon-ui-main:/app          # Full app directory
  - /app/node_modules              # Exclude node_modules
  - /app/.next                     # Exclude .next build
```

This allows:
- ✅ Hot reload on file changes
- ✅ Fast startup (no rebuild needed)
- ✅ Isolated node_modules (container-specific)

## 🌐 Network Configuration

Services communicate via Docker network:

- **Frontend** (web) → **Backend** (api) via `http://api:8000`
- **Backend** (api) → **Postgres** (postgres) via `postgres:5432`
- **Backend** (api) → **Redis** (redis) via `redis:6379`

External access:
- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- Grafana: `http://localhost:3001`
- Prometheus: `http://localhost:9090`

## ✅ Verification Checklist

After starting with Docker:

- [ ] All containers running: `docker-compose ps`
- [ ] Frontend accessible: http://localhost:3000
- [ ] Backend accessible: http://localhost:8000/docs
- [ ] No errors in logs: `docker-compose logs web`
- [ ] Hot reload working (edit a file and check)
- [ ] Can sign in (if OAuth configured)
- [ ] Chat interface loads
- [ ] Can send messages

## 🎉 Success!

If all containers are running and accessible:

1. ✅ Frontend: http://localhost:3000
2. ✅ Backend API: http://localhost:8000
3. ✅ API Docs: http://localhost:8000/docs
4. ✅ Grafana: http://localhost:3001
5. ✅ Prometheus: http://localhost:9090

You're ready to test! 🚀

---

**Next Steps:**
1. Open http://localhost:3000
2. Click "Get Started"
3. Test the chat interface
4. Check the documentation for testing guide

**Need help?** Check logs with `docker-compose logs -f`

