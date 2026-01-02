#!/bin/bash

# ============================================
# GA4 Analytics SaaS - Test Environment Startup Script
# ============================================
# This script sets up and starts the complete testing environment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored messages
print_message() {
    echo -e "${2}${1}${NC}"
}

print_header() {
    echo ""
    echo "============================================"
    echo "$1"
    echo "============================================"
    echo ""
}

# Check if Docker is running
check_docker() {
    print_header "Checking Docker"
    if ! docker info > /dev/null 2>&1; then
        print_message "❌ Docker is not running. Please start Docker and try again." "$RED"
        exit 1
    fi
    print_message "✅ Docker is running" "$GREEN"
}

# Check if .env file exists
check_env() {
    print_header "Checking Environment Variables"
    if [ ! -f .env ]; then
        print_message "⚠️  .env file not found. Creating from .env.example..." "$YELLOW"
        cp .env.example .env
        print_message "✅ Created .env file. Please edit it with your credentials." "$GREEN"
        print_message "📝 Required: OPENAI_API_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET" "$BLUE"
        read -p "Press Enter to continue after editing .env, or Ctrl+C to exit..."
    else
        print_message "✅ .env file found" "$GREEN"
    fi
}

# Stop and remove existing containers
cleanup() {
    print_header "Cleaning Up Previous Containers"
    docker-compose -f docker-compose.test.yml down -v 2>/dev/null || true
    print_message "✅ Cleanup complete" "$GREEN"
}

# Build and start services
start_services() {
    print_header "Building and Starting Services"
    print_message "⏳ This may take a few minutes on first run..." "$YELLOW"
    
    docker-compose -f docker-compose.test.yml up -d --build
    
    print_message "✅ Services started" "$GREEN"
}

# Wait for services to be healthy
wait_for_services() {
    print_header "Waiting for Services to be Healthy"
    
    print_message "⏳ Waiting for PostgreSQL..." "$YELLOW"
    timeout 60 bash -c 'until docker exec ga4-postgres-test pg_isready -U postgres > /dev/null 2>&1; do sleep 2; done'
    print_message "✅ PostgreSQL is ready" "$GREEN"
    
    print_message "⏳ Waiting for Redis..." "$YELLOW"
    timeout 30 bash -c 'until docker exec ga4-redis-test redis-cli ping > /dev/null 2>&1; do sleep 2; done'
    print_message "✅ Redis is ready" "$GREEN"
    
    print_message "⏳ Waiting for API..." "$YELLOW"
    timeout 60 bash -c 'until curl -f http://localhost:8000/health > /dev/null 2>&1; do sleep 2; done'
    print_message "✅ API is ready" "$GREEN"
    
    print_message "⏳ Waiting for Frontend..." "$YELLOW"
    timeout 90 bash -c 'until curl -f http://localhost:3000 > /dev/null 2>&1; do sleep 2; done'
    print_message "✅ Frontend is ready" "$GREEN"
}

# Run database migrations
run_migrations() {
    print_header "Running Database Migrations"
    
    # Wait a bit more to ensure DB is fully ready
    sleep 5
    
    print_message "⏳ Running migrations..." "$YELLOW"
    docker exec ga4-api-test alembic upgrade head || {
        print_message "⚠️  Migrations failed or already applied" "$YELLOW"
    }
    print_message "✅ Migrations complete" "$GREEN"
}

# Display service URLs
display_urls() {
    print_header "🎉 Test Environment Ready!"
    
    echo ""
    print_message "📱 Frontend:          http://localhost:3000" "$BLUE"
    print_message "🔧 API Documentation: http://localhost:8000/docs" "$BLUE"
    print_message "📊 Grafana:           http://localhost:3001 (admin/admin)" "$BLUE"
    print_message "📈 Prometheus:        http://localhost:9090" "$BLUE"
    echo ""
    print_message "🗄️  PostgreSQL:        localhost:5432" "$BLUE"
    print_message "🔴 Redis:             localhost:6379" "$BLUE"
    print_message "🔀 pgBouncer:         localhost:6432" "$BLUE"
    echo ""
    print_message "📋 View logs:         docker-compose -f docker-compose.test.yml logs -f" "$YELLOW"
    print_message "🛑 Stop services:     docker-compose -f docker-compose.test.yml down" "$YELLOW"
    print_message "🗑️  Clean volumes:     docker-compose -f docker-compose.test.yml down -v" "$YELLOW"
    echo ""
}

# Main execution
main() {
    print_header "🚀 GA4 Analytics SaaS - Test Environment Setup"
    
    check_docker
    check_env
    cleanup
    start_services
    wait_for_services
    run_migrations
    display_urls
    
    print_message "✨ Setup complete! Happy testing!" "$GREEN"
    echo ""
    
    # Ask if user wants to see logs
    read -p "Would you like to view the logs? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker-compose -f docker-compose.test.yml logs -f
    fi
}

# Run main function
main

