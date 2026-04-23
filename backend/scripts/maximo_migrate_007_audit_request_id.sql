-- Migration 007: Add request_id column to query_audit_log
-- Run on 192.168.1.11: docker exec -i aikm-postgres psql -U aikm -d aikm < backend/scripts/maximo_migrate_007_audit_request_id.sql

ALTER TABLE query_audit_log ADD COLUMN IF NOT EXISTS request_id VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_audit_request_id ON query_audit_log(request_id) WHERE request_id IS NOT NULL;
