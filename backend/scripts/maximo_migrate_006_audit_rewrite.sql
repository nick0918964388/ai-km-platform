-- Migration 006: Add SQL rewrite history columns to query_audit_log
-- Run with: docker exec -i aikm-postgres psql -U aikm -d aikm < backend/scripts/maximo_migrate_006_audit_rewrite.sql

ALTER TABLE query_audit_log
    ADD COLUMN IF NOT EXISTS original_question TEXT,
    ADD COLUMN IF NOT EXISTS rewrite_history JSONB,
    ADD COLUMN IF NOT EXISTS recovery_path VARCHAR(32);

-- [{attempt: int, query: str, reason: str, success: bool, ms: int}]
-- recovery_path: 'direct' | 'sql_retry' | 'rag_fallback' | 'sql_failed' | 'clarification'
-- original_question: NULL means question == original (no rewrite occurred)
-- rewrite_history: NULL means no rewrite was attempted

CREATE INDEX IF NOT EXISTS idx_audit_recovery_path
    ON query_audit_log(recovery_path)
    WHERE recovery_path IS NOT NULL;
