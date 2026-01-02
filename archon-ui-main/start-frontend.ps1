# GA4 Analytics SaaS - Frontend Quick Start Script (PowerShell)
# This script helps you quickly set up and start the frontend

$ErrorActionPreference = "Stop"

Write-Host "🚀 GA4 Analytics SaaS - Frontend Setup" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Check if Node.js is installed
try {
    $nodeVersion = node --version
    Write-Host "✅ Node.js version: $nodeVersion" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "❌ Node.js is not installed. Please install Node.js 18+ first." -ForegroundColor Red
    exit 1
}

# Check if .env.local exists
if (-not (Test-Path ".env.local")) {
    Write-Host "⚠️  .env.local not found. Creating from example..." -ForegroundColor Yellow
    
    if (Test-Path "env.example") {
        Copy-Item "env.example" ".env.local"
        Write-Host "✅ Created .env.local from env.example" -ForegroundColor Green
        Write-Host ""
        Write-Host "⚠️  IMPORTANT: Edit .env.local and configure:" -ForegroundColor Yellow
        Write-Host "   - NEXTAUTH_SECRET (generate with: openssl rand -base64 32)" -ForegroundColor Yellow
        Write-Host "   - GOOGLE_CLIENT_ID" -ForegroundColor Yellow
        Write-Host "   - GOOGLE_CLIENT_SECRET" -ForegroundColor Yellow
        Write-Host ""
        Read-Host "Press Enter after configuring .env.local..."
    } else {
        Write-Host "❌ env.example not found. Please create .env.local manually." -ForegroundColor Red
        exit 1
    }
}

# Check if node_modules exists
if (-not (Test-Path "node_modules")) {
    Write-Host "📦 Installing dependencies..." -ForegroundColor Cyan
    npm install
    Write-Host "✅ Dependencies installed" -ForegroundColor Green
    Write-Host ""
} else {
    Write-Host "✅ Dependencies already installed" -ForegroundColor Green
    Write-Host ""
}

# Check if backend is running
Write-Host "🔍 Checking backend API..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
    Write-Host "✅ Backend API is running" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Backend API not reachable at http://localhost:8000" -ForegroundColor Yellow
    Write-Host "   Make sure to start the backend first:" -ForegroundColor Yellow
    Write-Host "   cd .. && docker-compose up -d" -ForegroundColor Yellow
    Write-Host ""
    $continue = Read-Host "Continue anyway? (y/n)"
    if ($continue -ne "y") {
        exit 1
    }
}

Write-Host ""
Write-Host "🎉 Starting development server..." -ForegroundColor Green
Write-Host "==================================" -ForegroundColor Green
Write-Host ""
Write-Host "Frontend will be available at: http://localhost:3000" -ForegroundColor Cyan
Write-Host ""
Write-Host "Quick Links:" -ForegroundColor Cyan
Write-Host "  - Landing Page:  http://localhost:3000" -ForegroundColor White
Write-Host "  - Sign In:       http://localhost:3000/auth/signin" -ForegroundColor White
Write-Host "  - Dashboard:     http://localhost:3000/dashboard" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

# Start the development server
npm run dev

