#!/bin/bash

# GA4 Analytics SaaS - Docker Quick Start Script
# Starts the full stack including frontend in Docker

set -e

echo "🐳 GA4 Analytics SaaS - Docker Setup"
echo "====================================="
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

echo "✅ Docker version: $(docker --version)"
echo "✅ Docker Compose version: $(docker-compose --version)"
echo ""

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found. Creating from example..."
    
    if [ -f "env.example" ]; then
        cp env.example .env
        echo "✅ Created .env from env.example"
        echo ""
        echo "⚠️  IMPORTANT: Edit .env and configure:"
        echo "   - NEXTAUTH_SECRET (generate with: openssl rand -base64 32)"
        echo "   - GOOGLE_CLIENT_ID (optional for initial testing)"
        echo "   - GOOGLE_CLIENT_SECRET (optional for initial testing)"
        echo "   - OPENAI_API_KEY (required for backend)"
        echo ""
        read -p "Press Enter after configuring .env..."
    else
        echo "❌ env.example not found. Please create .env manually."
        exit 1
    fi
fi

# Stop any running containers
echo "🛑 Stopping any running containers..."
docker-compose down

echo ""
echo "🏗️  Building and starting services..."
echo "===================================="
echo ""

# Build and start all services
docker-compose up -d --build

echo ""
echo "⏳ Waiting for services to be ready..."
echo ""

# Wait for postgres
echo "Waiting for PostgreSQL..."
until docker-compose exec -T postgres pg_isready -U postgres > /dev/null 2>&1; do
    sleep 1
done
echo "✅ PostgreSQL is ready"

# Wait for redis
echo "Waiting for Redis..."
until docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; do
    sleep 1
done
echo "✅ Redis is ready"

# Wait for backend
echo "Waiting for Backend API..."
until curl -s http://localhost:8000/health > /dev/null 2>&1; do
    sleep 1
done
echo "✅ Backend API is ready"

# Wait for frontend
echo "Waiting for Frontend..."
sleep 5
until curl -s http://localhost:3000 > /dev/null 2>&1; do
    sleep 1
done
echo "✅ Frontend is ready"

echo ""
echo "🎉 All services are running!"
echo "=========================="
echo ""
echo "📍 Service URLs:"
echo "   Frontend:   http://localhost:3000"
echo "   Backend:    http://localhost:8000"
echo "   API Docs:   http://localhost:8000/docs"
echo "   Grafana:    http://localhost:3001 (admin/admin)"
echo "   Prometheus: http://localhost:9090"
echo ""
echo "📊 View logs:"
echo "   All:      docker-compose logs -f"
echo "   Frontend: docker-compose logs -f web"
echo "   Backend:  docker-compose logs -f api"
echo ""
echo "🛑 Stop services:"
echo "   docker-compose down"
echo ""
echo "✨ Ready to test! Open http://localhost:3000 in your browser"
echo ""

