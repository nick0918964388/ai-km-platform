-- =============================================================================
-- Feature       : 013-postgres-viewer
-- Migration     : 003 — CSP violation log table (T-046)
-- Runs as       : aikm (application user) — no superuser required.
-- Idempotency   : Re-runnable. All DDL guarded with IF NOT EXISTS.
-- Retention     : 30-day purge cron (T-043). See quickstart.md
--                 §"CSP violation log retention" for runbook details.
-- Reference     : specs/013-postgres-viewer / T-046
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. CSP violation log table.
--    Public browsers POST to /api/csp-violations (no auth, no cookies).
--    Only the enumerated CSP fields are stored — no full request bodies,
--    no referrer query-strings, no auth tokens.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS csp_violation_log (
    id                  BIGSERIAL PRIMARY KEY,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    blocked_uri         TEXT,
    effective_directive TEXT,
    original_policy     TEXT,
    document_uri        TEXT,
    violated_directive  TEXT,
    source_file         TEXT,
    line_number         INT,
    status_code         INT,
    user_agent          TEXT,
    ip_address          TEXT         -- trusted XFF or request.client.host
);

-- -----------------------------------------------------------------------------
-- 2. Index — descending on created_at for efficient retention purge and
--    time-based queries.
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_csp_violation_created
    ON csp_violation_log (created_at DESC);

COMMIT;

-- -----------------------------------------------------------------------------
-- 3. Verification.
-- -----------------------------------------------------------------------------
\echo '=== 003 verification ==='
SELECT
    EXISTS(
        SELECT 1 FROM information_schema.tables
         WHERE table_name = 'csp_violation_log'
    ) AS table_exists,
    EXISTS(
        SELECT 1 FROM pg_indexes
         WHERE indexname = 'idx_csp_violation_created'
    ) AS index_exists;
\echo '=== 003 done ==='
