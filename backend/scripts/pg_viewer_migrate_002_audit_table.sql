-- =============================================================================
-- Feature       : 013-postgres-viewer
-- Migration     : 002 — Audit log (partitioned) + spillover + partition helper
-- Runs as       : postgres (superuser) — REQUIRED (post-critic C1/C2 fix 2026-04-20).
--                 Rationale: this file issues `ALTER TABLE ... OWNER TO aikm_audit_purger`
--                 which requires the executor to (a) be a member of the target role AND
--                 (b) target role have CREATE on schema public. `aikm` is not a member
--                 of aikm_audit_purger, and aikm_audit_purger has CREATE REVOKED on
--                 public (by 001), so running as `aikm` would fail at the ALTER step.
--                 Subsequent REVOKE/GRANT on the parent + partitions also require
--                 ownership or superuser — only postgres can do both cleanly.
--                 Migration 001 MUST have run first — this migration references the
--                 aikm_viewer and aikm_audit_purger roles and will error otherwise.
-- Idempotency   : Re-runnable. Guards:
--                   - CREATE TABLE IF NOT EXISTS for parent, partitions, spillover
--                   - CREATE INDEX IF NOT EXISTS for all indexes
--                   - CREATE OR REPLACE FUNCTION for partition helper
--                   - ALTER TABLE ... OWNER TO is idempotent (no-op if already owner)
-- Rerun-twice   : On a fresh postgres:16-alpine, running 001 then 002 TWICE produces
--                 identical verification output on both iterations (T-003 acceptance).
-- Expected tail : The final SELECT must print exactly:
--                   aikm_insert=t, aikm_select=t, aikm_update=f, viewer_select=f,
--                   partition_2026_04_exists=t, partition_2026_05_exists=t,
--                   spillover_exists=t, aikm_append_only=t,
--                   aikm_viewer_denied_audit=t, purger_owns_parent=t.
--                 Followed by a DO $verify$ block that RAISEs EXCEPTION on
--                 any invariant violation (exit-code contract for CI).
-- Reference     : specs/013-postgres-viewer/data-model.md §4b
-- =============================================================================

\set ON_ERROR_STOP on

-- -----------------------------------------------------------------------------
-- Pre-flight: ensure 001 has run. Fails fast with a clear message otherwise.
-- -----------------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aikm_viewer') THEN
    RAISE EXCEPTION 'aikm_viewer role missing — run migration 001 first';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aikm_audit_purger') THEN
    RAISE EXCEPTION 'aikm_audit_purger role missing — run migration 001 first';
  END IF;
END $$;

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. Partitioned parent — pg_viewer_audit_log (monthly range on created_at).
--    PRIMARY KEY spans (id, created_at) because PG requires the partition key
--    to be part of every UNIQUE constraint on a partitioned table.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pg_viewer_audit_log (
    id              BIGSERIAL,
    user_id         VARCHAR(36)  NOT NULL,
    user_email      VARCHAR(255),
    action          VARCHAR(32)  NOT NULL
      CHECK (action IN ('list_tables','schema','browse','filter','export','sql_editor')),
    query_type      VARCHAR(16)  NOT NULL DEFAULT 'table_browse'
      CHECK (query_type IN ('table_browse','schema','sql_editor')),
    raw_sql         TEXT,
    table_name      VARCHAR(128),
    filters_json    JSONB,
    order_by        VARCHAR(128),
    order_dir       VARCHAR(4)
      CHECK (order_dir IN ('ASC','DESC') OR order_dir IS NULL),
    limit_val       INTEGER,
    offset_val      INTEGER,
    row_count       INTEGER      NOT NULL DEFAULT 0,
    execution_ms    REAL,
    status          VARCHAR(16)  NOT NULL DEFAULT 'ok'
      CHECK (status IN ('ok','timeout','error','forbidden','rate_limited','denied')),
    error_message   TEXT,
    ip_address      INET,
    user_agent      TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at),
    -- M5 fix (post-critic 2026-04-20): original CHECK required raw_sql IS NOT NULL
    -- for ALL sql_editor rows. That blocked audit of denied/rate_limited SQL
    -- editor attempts where the request was rejected before raw_sql was captured
    -- (e.g., rate-limit pre-flight, unauthenticated). Forensic completeness
    -- requires those rows still be insertable. New rule:
    --   - sql_editor + status='ok'  → raw_sql MUST be present
    --   - sql_editor + status<>'ok' → raw_sql MAY be NULL (denied pre-capture)
    --   - not sql_editor             → raw_sql MUST be NULL
    CONSTRAINT chk_raw_sql_only_for_editor
      CHECK ((query_type =  'sql_editor' AND status =  'ok' AND raw_sql IS NOT NULL)
          OR (query_type =  'sql_editor' AND status <> 'ok')
          OR (query_type <> 'sql_editor' AND raw_sql IS NULL)),
    CONSTRAINT chk_raw_sql_length
      CHECK (raw_sql IS NULL OR octet_length(raw_sql) <= 8192),
    CONSTRAINT chk_action_query_type
      CHECK (
        (action IN ('list_tables','browse','filter','export') AND query_type = 'table_browse')
        OR (action = 'schema'     AND query_type = 'schema')
        OR (action = 'sql_editor' AND query_type = 'sql_editor')
      )
) PARTITION BY RANGE (created_at);

-- -----------------------------------------------------------------------------
-- 2. Seed partitions for the current and next calendar month.
--    Cron `/usr/local/bin/pg-viewer-partition-ensure.sh` (quickstart §10b)
--    calls ensure_next_audit_partition() nightly to pre-create future months.
--    Hardcoded 2026-04 + 2026-05 here is the minimum seed for the 013 launch;
--    T-043 cron will rotate months forward automatically.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pg_viewer_audit_log_2026_04
  PARTITION OF pg_viewer_audit_log
  FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');

CREATE TABLE IF NOT EXISTS pg_viewer_audit_log_2026_05
  PARTITION OF pg_viewer_audit_log
  FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

-- -----------------------------------------------------------------------------
-- 3. Indexes — all IF NOT EXISTS-guarded. Partial indexes on status and on
--    sql_editor keep the hot path narrow (99% of rows are status='ok' and
--    query_type='table_browse').
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_pgva_user
  ON pg_viewer_audit_log (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pgva_table
  ON pg_viewer_audit_log (table_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pgva_created
  ON pg_viewer_audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pgva_status
  ON pg_viewer_audit_log (status)
  WHERE status <> 'ok';
CREATE INDEX IF NOT EXISTS idx_pgva_sql_editor
  ON pg_viewer_audit_log (user_id, created_at DESC)
  WHERE query_type = 'sql_editor';

-- -----------------------------------------------------------------------------
-- 4. Spillover table (R2 N2).
--    If write_audit() INSERTs a row whose created_at has no matching partition,
--    the parent INSERT raises 23514. The application catches that and redirects
--    the row here so forensic data is never silently lost. The nightly cron
--    alerts whenever this table receives rows within the past 24h.
--
--    M1 (post-critic 2026-04-20): `LIKE ... INCLUDING IDENTITY` creates an
--    INDEPENDENT sequence for spillover.id. Spillover IDs may collide with
--    partition IDs if the two sets are UNIONed. The primary key on spillover
--    (inherited via INCLUDING CONSTRAINTS) is (id, created_at) — still unique
--    within the spillover table; the pair (id, spilled_at) is unique across
--    forensic joins. Acceptable: spillover is a last-resort table, not a hot
--    forensic source of truth.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pg_viewer_audit_log_spillover (
    LIKE pg_viewer_audit_log INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING IDENTITY,
    spillover_reason TEXT,
    spilled_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pgva_spill_time
  ON pg_viewer_audit_log_spillover (spilled_at DESC);

-- -----------------------------------------------------------------------------
-- 5. Partition-maintenance helper.
--    Called nightly by pg-viewer-partition-ensure.sh. Idempotent: returns the
--    target partition name and whether it was newly created.
--
--    SECURITY DEFINER (post-critic M4 fix 2026-04-20): the body creates a new
--    partition of pg_viewer_audit_log (which is owned by aikm_audit_purger
--    after §6 below), transfers ownership, and issues REVOKE/GRANT. Neither
--    aikm nor aikm_audit_purger holds enough privilege to do this as INVOKER:
--      - aikm is not a member of aikm_audit_purger (cannot ALTER ... OWNER TO)
--      - aikm_audit_purger has CREATE REVOKED on schema public (cannot CREATE)
--    Running as DEFINER (postgres superuser, set by ALTER FUNCTION below)
--    bypasses both checks. search_path is pinned per the SECURITY DEFINER
--    hygiene rule (CVE-2018-1058-style search_path hijack prevention).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION ensure_next_audit_partition()
RETURNS TABLE(partition_name TEXT, created BOOL)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $func$
DECLARE
  nm    TIMESTAMPTZ := date_trunc('month', NOW() + INTERVAL '1 month');
  nm2   TIMESTAMPTZ := nm + INTERVAL '1 month';
  pname TEXT        := 'pg_viewer_audit_log_' || to_char(nm, 'YYYY_MM');
BEGIN
  -- L1 fix: use PERFORM (no dummy RECORD) — `IF NOT FOUND` reads cleaner.
  PERFORM 1 FROM pg_class
   WHERE relname = pname AND relkind IN ('r','p');

  IF NOT FOUND THEN
    EXECUTE format(
      'CREATE TABLE %I PARTITION OF pg_viewer_audit_log FOR VALUES FROM (%L) TO (%L)',
      pname, nm, nm2
    );
    -- Append-only + purger ownership per new partition.
    -- NOTE: these four EXECUTEs must stay in sync with the per-partition
    -- REVOKE block in §8 and with the manual template in quickstart §10c.
    EXECUTE format('REVOKE UPDATE, DELETE, TRUNCATE ON %I FROM aikm',         pname);
    EXECUTE format('REVOKE SELECT               ON %I FROM aikm_viewer',      pname);
    EXECUTE format('GRANT  INSERT, SELECT       ON %I TO   aikm',             pname);
    EXECUTE format('ALTER TABLE %I OWNER TO aikm_audit_purger',               pname);
    RETURN QUERY SELECT pname, TRUE;
  ELSE
    RETURN QUERY SELECT pname, FALSE;
  END IF;
END;
$func$;

-- SECURITY DEFINER: function must be owned by a role that has the required
-- privileges (postgres = superuser, bypasses all checks). Set explicitly so a
-- re-run from a different executor does not silently re-own it to the executor.
-- Function ownership: use CURRENT_USER so the superuser executing this migration
-- (postgres on canonical installs, aikm on this deployment) becomes the owner.
ALTER FUNCTION ensure_next_audit_partition() OWNER TO CURRENT_USER;

-- -----------------------------------------------------------------------------
-- 6. Ownership transfer — partitioned parent + seeded partitions.
--    aikm_audit_purger must own these to issue DROP TABLE during weekly purge.
--    ALTER TABLE ... OWNER TO is idempotent.
-- -----------------------------------------------------------------------------
ALTER TABLE pg_viewer_audit_log         OWNER TO aikm_audit_purger;
ALTER TABLE pg_viewer_audit_log_2026_04 OWNER TO aikm_audit_purger;
ALTER TABLE pg_viewer_audit_log_2026_05 OWNER TO aikm_audit_purger;

-- Spillover is NOT partitioned and not rotated — aikm retains ownership.

-- -----------------------------------------------------------------------------
-- 7. Append-only grants on the PARENT — propagate via partition inheritance.
-- -----------------------------------------------------------------------------
REVOKE ALL    ON pg_viewer_audit_log FROM aikm;
GRANT  INSERT, SELECT ON pg_viewer_audit_log TO aikm;
-- aikm_viewer must NOT see the audit log (M4 security).
REVOKE ALL    ON pg_viewer_audit_log FROM aikm_viewer;

-- -----------------------------------------------------------------------------
-- 8. Per-partition grants — partition-level REVOKEs are required because
--    partition children do NOT automatically inherit parent REVOKEs
--    (only GRANTs propagate via the partition attach in some PG versions).
--    Template documented in quickstart §10c for new manual partitions; the
--    ensure_next_audit_partition() helper applies the same template for cron.
-- -----------------------------------------------------------------------------
REVOKE ALL    ON pg_viewer_audit_log_2026_04 FROM aikm;
REVOKE ALL    ON pg_viewer_audit_log_2026_05 FROM aikm;
GRANT  INSERT, SELECT ON pg_viewer_audit_log_2026_04 TO aikm;
GRANT  INSERT, SELECT ON pg_viewer_audit_log_2026_05 TO aikm;
REVOKE ALL    ON pg_viewer_audit_log_2026_04 FROM aikm_viewer;
REVOKE ALL    ON pg_viewer_audit_log_2026_05 FROM aikm_viewer;

-- -----------------------------------------------------------------------------
-- 9. Spillover grants — aikm writes into it when a partition miss occurs.
-- -----------------------------------------------------------------------------
REVOKE ALL    ON pg_viewer_audit_log_spillover FROM aikm;
GRANT  INSERT, SELECT ON pg_viewer_audit_log_spillover TO aikm;
REVOKE ALL    ON pg_viewer_audit_log_spillover FROM aikm_viewer;

-- -----------------------------------------------------------------------------
-- 10. Helper function access — purger runs it in cron; aikm runs it in the
--     nightly partition healthcheck (see quickstart §10b).
-- -----------------------------------------------------------------------------
GRANT EXECUTE ON FUNCTION ensure_next_audit_partition() TO aikm;
GRANT EXECUTE ON FUNCTION ensure_next_audit_partition() TO aikm_audit_purger;

COMMIT;

-- -----------------------------------------------------------------------------
-- 11. Verification — acceptance check for T-003.
--     Expected: t, t, f, f, t, t, t, t, t, t
--     (includes purger_owns_parent per post-critic H2 fix 2026-04-20)
-- -----------------------------------------------------------------------------
\echo '=== 002 verification ==='
SELECT
  has_table_privilege('aikm',        'pg_viewer_audit_log', 'INSERT') AS aikm_insert,
  has_table_privilege('aikm',        'pg_viewer_audit_log', 'SELECT') AS aikm_select,
  has_table_privilege('aikm',        'pg_viewer_audit_log', 'UPDATE') AS aikm_update,
  has_table_privilege('aikm_viewer', 'pg_viewer_audit_log', 'SELECT') AS viewer_select,
  EXISTS(
    SELECT 1 FROM pg_class
     WHERE relname = 'pg_viewer_audit_log_2026_04' AND relispartition
  ) AS partition_2026_04_exists,
  EXISTS(
    SELECT 1 FROM pg_class
     WHERE relname = 'pg_viewer_audit_log_2026_05' AND relispartition
  ) AS partition_2026_05_exists,
  EXISTS(
    SELECT 1 FROM pg_tables
     WHERE tablename = 'pg_viewer_audit_log_spillover'
  ) AS spillover_exists,
  NOT EXISTS(
    SELECT 1 FROM information_schema.role_table_grants
     WHERE grantee='aikm' AND table_name='pg_viewer_audit_log'
       AND privilege_type IN ('UPDATE','DELETE','TRUNCATE')
  ) AS aikm_append_only,
  NOT EXISTS(
    SELECT 1 FROM information_schema.role_table_grants
     WHERE grantee='aikm_viewer' AND table_name='pg_viewer_audit_log'
  ) AS aikm_viewer_denied_audit,
  -- H2 fix: explicit ownership assertion — regressions that leave aikm as
  -- owner would silently pass all other checks but break the weekly purge.
  EXISTS(
    SELECT 1 FROM pg_class c
      JOIN pg_roles r ON r.oid = c.relowner
     WHERE c.relname = 'pg_viewer_audit_log'
       AND r.rolname = 'aikm_audit_purger'
  ) AS purger_owns_parent;
\echo '=== 002 done ==='

-- L5 fix: exit-code contract. CI / psql --set ON_ERROR_STOP=1 users rely on
-- the migration's exit status, not on parsing the \echo output. This DO block
-- re-runs each invariant and RAISEs EXCEPTION (nonzero exit) on any failure.
DO $verify$
DECLARE
  v_aikm_insert      BOOL;
  v_aikm_select      BOOL;
  v_aikm_update      BOOL;
  v_viewer_select    BOOL;
  v_part_04          BOOL;
  v_part_05          BOOL;
  v_spill_exists     BOOL;
  v_append_only      BOOL;
  v_viewer_denied    BOOL;
  v_purger_owns      BOOL;
BEGIN
  v_aikm_insert   := has_table_privilege('aikm',        'pg_viewer_audit_log', 'INSERT');
  v_aikm_select   := has_table_privilege('aikm',        'pg_viewer_audit_log', 'SELECT');
  v_aikm_update   := has_table_privilege('aikm',        'pg_viewer_audit_log', 'UPDATE');
  v_viewer_select := has_table_privilege('aikm_viewer', 'pg_viewer_audit_log', 'SELECT');

  SELECT EXISTS (SELECT 1 FROM pg_class WHERE relname='pg_viewer_audit_log_2026_04' AND relispartition) INTO v_part_04;
  SELECT EXISTS (SELECT 1 FROM pg_class WHERE relname='pg_viewer_audit_log_2026_05' AND relispartition) INTO v_part_05;
  SELECT EXISTS (SELECT 1 FROM pg_tables WHERE tablename='pg_viewer_audit_log_spillover') INTO v_spill_exists;
  SELECT NOT EXISTS (
    SELECT 1 FROM information_schema.role_table_grants
     WHERE grantee='aikm' AND table_name='pg_viewer_audit_log'
       AND privilege_type IN ('UPDATE','DELETE','TRUNCATE')
  ) INTO v_append_only;
  SELECT NOT EXISTS (
    SELECT 1 FROM information_schema.role_table_grants
     WHERE grantee='aikm_viewer' AND table_name='pg_viewer_audit_log'
  ) INTO v_viewer_denied;
  SELECT EXISTS (
    SELECT 1 FROM pg_class c JOIN pg_roles r ON r.oid=c.relowner
     WHERE c.relname='pg_viewer_audit_log' AND r.rolname='aikm_audit_purger'
  ) INTO v_purger_owns;

  IF NOT v_aikm_insert   THEN RAISE EXCEPTION '002 verification failed: aikm missing INSERT on pg_viewer_audit_log'; END IF;
  IF NOT v_aikm_select   THEN RAISE EXCEPTION '002 verification failed: aikm missing SELECT on pg_viewer_audit_log'; END IF;
  IF     v_aikm_update   THEN RAISE EXCEPTION '002 verification failed: aikm has UPDATE on pg_viewer_audit_log (append-only violated)'; END IF;
  IF     v_viewer_select THEN RAISE EXCEPTION '002 verification failed: aikm_viewer has SELECT on pg_viewer_audit_log (leak)'; END IF;
  IF NOT v_part_04       THEN RAISE EXCEPTION '002 verification failed: partition 2026_04 missing or detached'; END IF;
  IF NOT v_part_05       THEN RAISE EXCEPTION '002 verification failed: partition 2026_05 missing or detached'; END IF;
  IF NOT v_spill_exists  THEN RAISE EXCEPTION '002 verification failed: spillover table missing'; END IF;
  IF NOT v_append_only   THEN RAISE EXCEPTION '002 verification failed: aikm has mutation grants (append-only violated)'; END IF;
  IF NOT v_viewer_denied THEN RAISE EXCEPTION '002 verification failed: aikm_viewer has audit_log grants (leak)'; END IF;
  IF NOT v_purger_owns   THEN RAISE EXCEPTION '002 verification failed: pg_viewer_audit_log not owned by aikm_audit_purger (purge will break)'; END IF;
END
$verify$;
