#!/bin/bash

# GA4 Analytics SaaS - Frontend Quick Start Script
# This script helps you quickly set up and start the frontend

set -e

echo "🚀 GA4 Analytics SaaS - Frontend Setup"
echo "======================================"
echo ""

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 18+ first."
    exit 1
fi

echo "✅ Node.js version: $(node --version)"
echo ""

# Check if .env.local exists
if [ ! -f ".env.local" ]; then
    echo "⚠️  .env.local not found. Creating from example..."
    
    if [ -f "env.example" ]; then
        cp env.example .env.local
        echo "✅ Created .env.local from env.example"
        echo ""
        echo "⚠️  IMPORTANT: Edit .env.local and configure:"
        echo "   - NEXTAUTH_SECRET (generate with: openssl rand -base64 32)"
        echo "   - GOOGLE_CLIENT_ID"
        echo "   - GOOGLE_CLIENT_SECRET"
        echo ""
        read -p "Press Enter after configuring .env.local..."
    else
        echo "❌ env.example not found. Please create .env.local manually."
        exit 1
    fi
fi

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
    echo "✅ Dependencies installed"
    echo ""
else
    echo "✅ Dependencies already installed"
    echo ""
fi

# Check if backend is running
echo "🔍 Checking backend API..."
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ Backend API is running"
else
    echo "⚠️  Backend API not reachable at http://localhost:8000"
    echo "   Make sure to start the backend first:"
    echo "   cd .. && docker-compose up -d"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "🎉 Starting development server..."
echo "=================================="
echo ""
echo "Frontend will be available at: http://localhost:3000"
echo ""
echo "Quick Links:"
echo "  - Landing Page:  http://localhost:3000"
echo "  - Sign In:       http://localhost:3000/auth/signin"
echo "  - Dashboard:     http://localhost:3000/dashboard"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start the development server
npm run dev

