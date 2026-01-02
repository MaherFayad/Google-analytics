# GA4 Analytics SaaS - Docker Quick Start Script (PowerShell)
# Starts the full stack including frontend in Docker

$ErrorActionPreference = "Stop"

Write-Host "🐳 GA4 Analytics SaaS - Docker Setup" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is installed
try {
    $dockerVersion = docker --version
    Write-Host "✅ Docker version: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker is not installed. Please install Docker Desktop first." -ForegroundColor Red
    exit 1
}

# Check if Docker Compose is installed
try {
    $composeVersion = docker-compose --version
    Write-Host "✅ Docker Compose version: $composeVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker Compose is not installed. Please install Docker Compose first." -ForegroundColor Red
    exit 1
}

Write-Host ""

# Check if .env exists
if (-not (Test-Path ".env")) {
    Write-Host "⚠️  .env file not found. Creating from example..." -ForegroundColor Yellow
    
    if (Test-Path "env.example") {
        Copy-Item "env.example" ".env"
        Write-Host "✅ Created .env from env.example" -ForegroundColor Green
        Write-Host ""
        Write-Host "⚠️  IMPORTANT: Edit .env and configure:" -ForegroundColor Yellow
        Write-Host "   - NEXTAUTH_SECRET (generate with: openssl rand -base64 32)" -ForegroundColor Yellow
        Write-Host "   - GOOGLE_CLIENT_ID (optional for initial testing)" -ForegroundColor Yellow
        Write-Host "   - GOOGLE_CLIENT_SECRET (optional for initial testing)" -ForegroundColor Yellow
        Write-Host "   - OPENAI_API_KEY (required for backend)" -ForegroundColor Yellow
        Write-Host ""
        Read-Host "Press Enter after configuring .env..."
    } else {
        Write-Host "❌ env.example not found. Please create .env manually." -ForegroundColor Red
        exit 1
    }
}

# Stop any running containers
Write-Host "🛑 Stopping any running containers..." -ForegroundColor Yellow
docker-compose down

Write-Host ""
Write-Host "🏗️  Building and starting services..." -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""

# Build and start all services
docker-compose up -d --build

Write-Host ""
Write-Host "⏳ Waiting for services to be ready..." -ForegroundColor Yellow
Write-Host ""

# Wait for services
Write-Host "Waiting for PostgreSQL..." -ForegroundColor Cyan
Start-Sleep -Seconds 5

Write-Host "Waiting for Redis..." -ForegroundColor Cyan
Start-Sleep -Seconds 2

Write-Host "Waiting for Backend API..." -ForegroundColor Cyan
$maxAttempts = 30
$attempt = 0
while ($attempt -lt $maxAttempts) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            Write-Host "✅ Backend API is ready" -ForegroundColor Green
            break
        }
    } catch {
        Start-Sleep -Seconds 1
        $attempt++
    }
}

Write-Host "Waiting for Frontend..." -ForegroundColor Cyan
Start-Sleep -Seconds 5
$attempt = 0
while ($attempt -lt $maxAttempts) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            Write-Host "✅ Frontend is ready" -ForegroundColor Green
            break
        }
    } catch {
        Start-Sleep -Seconds 1
        $attempt++
    }
}

Write-Host ""
Write-Host "🎉 All services are running!" -ForegroundColor Green
Write-Host "==========================" -ForegroundColor Green
Write-Host ""
Write-Host "📍 Service URLs:" -ForegroundColor Cyan
Write-Host "   Frontend:   http://localhost:3000" -ForegroundColor White
Write-Host "   Backend:    http://localhost:8000" -ForegroundColor White
Write-Host "   API Docs:   http://localhost:8000/docs" -ForegroundColor White
Write-Host "   Grafana:    http://localhost:3001 (admin/admin)" -ForegroundColor White
Write-Host "   Prometheus: http://localhost:9090" -ForegroundColor White
Write-Host ""
Write-Host "📊 View logs:" -ForegroundColor Cyan
Write-Host "   All:      docker-compose logs -f" -ForegroundColor White
Write-Host "   Frontend: docker-compose logs -f web" -ForegroundColor White
Write-Host "   Backend:  docker-compose logs -f api" -ForegroundColor White
Write-Host ""
Write-Host "🛑 Stop services:" -ForegroundColor Cyan
Write-Host "   docker-compose down" -ForegroundColor White
Write-Host ""
Write-Host "✨ Ready to test! Open http://localhost:3000 in your browser" -ForegroundColor Green
Write-Host ""

# Open browser automatically
$openBrowser = Read-Host "Open browser now? (y/n)"
if ($openBrowser -eq "y") {
    Start-Process "http://localhost:3000"
}

