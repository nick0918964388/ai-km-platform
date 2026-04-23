-- Migration 008: Add request_id column to rag_search_log
-- Deploy: docker exec -i aikm-postgres psql -U aikm -d aikm < backend/scripts/maximo_migrate_008_rag_search_log_request_id.sql

ALTER TABLE rag_search_log ADD COLUMN IF NOT EXISTS request_id VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_rag_search_request_id ON rag_search_log(request_id) WHERE request_id IS NOT NULL;
