-- Initial database setup for GA4 Analytics SaaS
-- This script runs on first container startup

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Try to create pgvector extension (may not be available in all images)
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS "vector";
EXCEPTION
    WHEN undefined_file THEN
        RAISE NOTICE 'pgvector extension not available, skipping';
END
$$;

-- Try to create pgsodium extension (may not be available)
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS "pgsodium";
EXCEPTION
    WHEN undefined_file THEN
        RAISE NOTICE 'pgsodium extension not available, skipping';
END
$$;

-- Create app schema
CREATE SCHEMA IF NOT EXISTS app;

-- Set search path
SET search_path TO app, public;

-- Initial placeholder (Alembic will manage actual migrations)
-- This file just ensures extensions are enabled

SELECT 'Database initialized successfully' AS status;

