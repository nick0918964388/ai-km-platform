-- AI-KM Platform Database Initialization
-- This script runs automatically on first database creation

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create default admin user (for reference only - actual auth handled by app)
-- Password: admin (should be changed in production)
