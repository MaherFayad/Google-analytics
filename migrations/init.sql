-- Initial database setup for GA4 Analytics SaaS
-- This script runs on first container startup

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgvector";
CREATE EXTENSION IF NOT EXISTS "pgsodium";

-- Create app schema
CREATE SCHEMA IF NOT EXISTS app;

-- Set search path
SET search_path TO app, public;

-- Initial placeholder (Alembic will manage actual migrations)
-- This file just ensures extensions are enabled

SELECT 'Database initialized successfully' AS status;

