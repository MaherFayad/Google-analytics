# ============================================
# GA4 Analytics SaaS - Test Environment Startup Script (PowerShell)
# ============================================
# This script sets up and starts the complete testing environment on Windows

$ErrorActionPreference = "Stop"

# Function to print colored messages
function Write-ColorMessage {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Write-Header {
    param([string]$Message)
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host $Message -ForegroundColor Cyan
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host ""
}

# Check if Docker is running
function Test-Docker {
    Write-Header "Checking Docker"
    try {
        docker info | Out-Null
        Write-ColorMessage "✅ Docker is running" "Green"
    } catch {
        Write-ColorMessage "❌ Docker is not running. Please start Docker Desktop and try again." "Red"
        exit 1
    }
}

# Check if .env file exists
function Test-EnvFile {
    Write-Header "Checking Environment Variables"
    if (-not (Test-Path .env)) {
        Write-ColorMessage "⚠️  .env file not found. Creating from .env.example..." "Yellow"
        Copy-Item .env.example .env
        Write-ColorMessage "✅ Created .env file. Please edit it with your credentials." "Green"
        Write-ColorMessage "📝 Required: OPENAI_API_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET" "Blue"
        Read-Host "Press Enter to continue after editing .env, or Ctrl+C to exit"
    } else {
        Write-ColorMessage "✅ .env file found" "Green"
    }
}

# Stop and remove existing containers
function Stop-Services {
    Write-Header "Cleaning Up Previous Containers"
    try {
        docker-compose -f docker-compose.test.yml down -v 2>$null
    } catch {
        # Ignore errors if containers don't exist
    }
    Write-ColorMessage "✅ Cleanup complete" "Green"
}

# Build and start services
function Start-Services {
    Write-Header "Building and Starting Services"
    Write-ColorMessage "⏳ This may take a few minutes on first run..." "Yellow"
    
    docker-compose -f docker-compose.test.yml up -d --build
    
    Write-ColorMessage "✅ Services started" "Green"
}

# Wait for a service to be ready
function Wait-ForService {
    param(
        [string]$Name,
        [scriptblock]$TestCommand,
        [int]$TimeoutSeconds = 60
    )
    
    Write-ColorMessage "⏳ Waiting for $Name..." "Yellow"
    $elapsed = 0
    $interval = 2
    
    while ($elapsed -lt $TimeoutSeconds) {
        try {
            & $TestCommand
            Write-ColorMessage "✅ $Name is ready" "Green"
            return
        } catch {
            Start-Sleep -Seconds $interval
            $elapsed += $interval
        }
    }
    
    Write-ColorMessage "❌ Timeout waiting for $Name" "Red"
    throw "Service $Name did not become ready in time"
}

# Wait for all services
function Wait-ForServices {
    Write-Header "Waiting for Services to be Healthy"
    
    Wait-ForService "PostgreSQL" {
        docker exec ga4-postgres-test pg_isready -U postgres | Out-Null
    }
    
    Wait-ForService "Redis" {
        docker exec ga4-redis-test redis-cli ping | Out-Null
    }
    
    Wait-ForService "API" {
        $response = Invoke-WebRequest -Uri http://localhost:8000/health -UseBasicParsing -TimeoutSec 5
        if ($response.StatusCode -ne 200) { throw "API not ready" }
    }
    
    Wait-ForService "Frontend" {
        $response = Invoke-WebRequest -Uri http://localhost:3000 -UseBasicParsing -TimeoutSec 5
        if ($response.StatusCode -ne 200) { throw "Frontend not ready" }
    } -TimeoutSeconds 90
}

# Run database migrations
function Invoke-Migrations {
    Write-Header "Running Database Migrations"
    
    # Wait a bit more to ensure DB is fully ready
    Start-Sleep -Seconds 5
    
    Write-ColorMessage "⏳ Running migrations..." "Yellow"
    try {
        docker exec ga4-api-test alembic upgrade head
        Write-ColorMessage "✅ Migrations complete" "Green"
    } catch {
        Write-ColorMessage "⚠️  Migrations failed or already applied" "Yellow"
    }
}

# Display service URLs
function Show-ServiceUrls {
    Write-Header "🎉 Test Environment Ready!"
    
    Write-Host ""
    Write-ColorMessage "📱 Frontend:          http://localhost:3000" "Blue"
    Write-ColorMessage "🔧 API Documentation: http://localhost:8000/docs" "Blue"
    Write-ColorMessage "📊 Grafana:           http://localhost:3001 (admin/admin)" "Blue"
    Write-ColorMessage "📈 Prometheus:        http://localhost:9090" "Blue"
    Write-Host ""
    Write-ColorMessage "🗄️  PostgreSQL:        localhost:5432" "Blue"
    Write-ColorMessage "🔴 Redis:             localhost:6379" "Blue"
    Write-ColorMessage "🔀 pgBouncer:         localhost:6432" "Blue"
    Write-Host ""
    Write-ColorMessage "📋 View logs:         docker-compose -f docker-compose.test.yml logs -f" "Yellow"
    Write-ColorMessage "🛑 Stop services:     docker-compose -f docker-compose.test.yml down" "Yellow"
    Write-ColorMessage "🗑️  Clean volumes:     docker-compose -f docker-compose.test.yml down -v" "Yellow"
    Write-Host ""
}

# Main execution
function Main {
    Write-Header "🚀 GA4 Analytics SaaS - Test Environment Setup"
    
    try {
        Test-Docker
        Test-EnvFile
        Stop-Services
        Start-Services
        Wait-ForServices
        Invoke-Migrations
        Show-ServiceUrls
        
        Write-ColorMessage "✨ Setup complete! Happy testing!" "Green"
        Write-Host ""
        
        # Ask if user wants to see logs
        $response = Read-Host "Would you like to view the logs? (y/N)"
        if ($response -eq "y" -or $response -eq "Y") {
            docker-compose -f docker-compose.test.yml logs -f
        }
    } catch {
        Write-ColorMessage "❌ Error: $_" "Red"
        Write-ColorMessage "💡 Try running: docker-compose -f docker-compose.test.yml logs" "Yellow"
        exit 1
    }
}

# Run main function
Main

