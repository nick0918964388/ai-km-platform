-- Migration 002: Maximo domain values + attribute metadata tables
-- Run: docker exec -i aikm-postgres psql -U aikm -d aikm < backend/scripts/maximo_migrate_002_attr_schema.sql

-- Full domain value store (replaces value_mapping JSONB in maximo_field_metadata)
CREATE TABLE IF NOT EXISTS maximo_domains (
    domainid   VARCHAR(50)  NOT NULL,
    value      VARCHAR(200) NOT NULL,
    description TEXT,
    synced_at  TIMESTAMPTZ  DEFAULT NOW(),
    PRIMARY KEY (domainid, value)
);

-- Attribute metadata pulled from maxattribute OSLC API
-- object_name = ASSET / WORKORDER / SR
-- pg_table    = our PostgreSQL table name
CREATE TABLE IF NOT EXISTS maximo_attr_metadata (
    id             SERIAL PRIMARY KEY,
    object_name    VARCHAR(50)  NOT NULL,
    pg_table       VARCHAR(80)  NOT NULL,
    attribute_name VARCHAR(100) NOT NULL,
    pg_column      VARCHAR(100),          -- mapped PG column name (may differ)
    display_name   TEXT,
    domainid       VARCHAR(50),
    description    TEXT,
    synced_at      TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE(object_name, attribute_name)
);

-- Index for fast schema building
CREATE INDEX IF NOT EXISTS idx_attr_meta_table ON maximo_attr_metadata(pg_table);
CREATE INDEX IF NOT EXISTS idx_attr_meta_obj   ON maximo_attr_metadata(object_name);
CREATE INDEX IF NOT EXISTS idx_domains_id      ON maximo_domains(domainid);
