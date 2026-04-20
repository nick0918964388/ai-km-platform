-- =============================================================================
-- Feature       : 013-postgres-viewer
-- Migration     : 001 — Role creation, grants, curated view, extension denylist
-- Runs as       : postgres superuser (REQUIRED — creates roles, REVOKE from PUBLIC,
--                 blocks dangerous extensions)
-- Idempotency   : Re-runnable. All DDL guarded via:
--                   - DO $$ IF NOT EXISTS $$ blocks for CREATE ROLE
--                   - CREATE OR REPLACE VIEW
--                   - IF EXISTS on REVOKE for tables not yet present
--                 Re-running updates role passwords (ALTER ROLE) + reasserts grants.
-- psql vars     : -v pg_viewer_password='<hex>'  -v pg_audit_purger_password='<hex>'
-- Expected tail : The final SELECT must print exactly:
--                   can_select_users=f, can_insert_users=f, can_create_schema=f,
--                   can_select_view=t, role_aikm_viewer=t, role_aikm_audit_purger=t
-- Reference     : specs/013-postgres-viewer/data-model.md §4a
-- =============================================================================

\set ON_ERROR_STOP on

-- -----------------------------------------------------------------------------
-- 1. Fail fast if dangerous extensions are installed.
--    These expose filesystem / outbound-network / raw-memory primitives that
--    aikm_viewer must never be able to reach — even transitively via EXECUTE.
-- -----------------------------------------------------------------------------
DO $$
DECLARE
  ext_name TEXT;
BEGIN
  FOR ext_name IN
    SELECT extname FROM pg_extension
    WHERE extname IN (
      'dblink',         -- outbound connections
      'postgres_fdw',   -- outbound PG connections
      'file_fdw',       -- raw file reads
      'pg_prewarm',     -- raw memory / buffer pool access
      'plperlu',        -- untrusted PL
      'plpythonu',      -- untrusted PL
      'plsh',           -- shell execution
      'adminpack',      -- filesystem management
      'plv8',           -- untrusted JS (post-critic M3 2026-04-20)
      'plluau',         -- untrusted Lua (post-critic M3)
      'pltclu'          -- untrusted Tcl (post-critic M3)
      -- NOTE: pg_stat_statements is NOT denylisted here (it is commonly
      -- required for ops). Instead, we explicitly REVOKE SELECT on its
      -- view from aikm_viewer below if the extension exists (§8b).
    )
  LOOP
    RAISE EXCEPTION
      'pg_viewer migration aborted: dangerous extension % present. '
      'REVOKE EXECUTE on its functions from aikm_viewer, re-audit, '
      'then (if intentional) remove from this denylist.',
      ext_name;
  END LOOP;
END $$;

-- -----------------------------------------------------------------------------
-- 2. Short lock_timeout so a stuck ETL does not freeze this migration forever.
-- -----------------------------------------------------------------------------
SET lock_timeout = '5s';

-- -----------------------------------------------------------------------------
-- 3. Create / update the aikm_viewer role (idempotent).
--    PostgreSQL has no CREATE ROLE IF NOT EXISTS, so wrap in DO block.
--    format(%L) safely quotes the password even if it contains SQL meta-chars.
--    NOINHERIT (post-critic L2 documentation 2026-04-20): conservative hardening
--    not explicitly in data-model.md §4a — if `GRANT aikm_viewer TO other_role`
--    ever happens later, the privileges are not auto-assumed. Intentional.
-- -----------------------------------------------------------------------------
-- H4 guard (post-critic 2026-04-20): refuse to proceed if psql var is missing
-- or empty. Otherwise a re-run with no -v flag would silently blank the role's
-- password, locking out the backend. Also guards against accidental clobber of
-- an out-of-band vault rotation.
DO $$
BEGIN
  IF :'pg_viewer_password' IS NULL OR :'pg_viewer_password' = '' THEN
    RAISE EXCEPTION 'pg_viewer_password psql variable is empty — pass `-v pg_viewer_password=<hex>` explicitly';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aikm_viewer') THEN
    EXECUTE format(
      'CREATE ROLE aikm_viewer LOGIN PASSWORD %L CONNECTION LIMIT 10 NOINHERIT',
      :'pg_viewer_password'
    );
  ELSE
    -- WARNING: re-running this migration rotates the aikm_viewer password to
    -- whatever :'pg_viewer_password' is. If you rotated the password via vault
    -- without updating the -v var, DO NOT re-run 001 — see quickstart §9.
    EXECUTE format(
      'ALTER ROLE aikm_viewer WITH LOGIN PASSWORD %L CONNECTION LIMIT 10 NOINHERIT',
      :'pg_viewer_password'
    );
  END IF;
END $$;

-- -----------------------------------------------------------------------------
-- 4. Role-level session defaults (three-layer timeout fix).
--    statement_timeout               → hard cap on any single SELECT
--    idle_in_transaction_session_timeout → kills a client that BEGINs and walks away
--    lock_timeout                    → prevents a pg_viewer query from blocking ETL
-- -----------------------------------------------------------------------------
ALTER ROLE aikm_viewer SET statement_timeout = '10s';
ALTER ROLE aikm_viewer SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE aikm_viewer SET lock_timeout = '2s';

-- -----------------------------------------------------------------------------
-- 5. Minimal DB-level privilege envelope for aikm_viewer.
--    Drop every inherited grant first, then GRANT only what is needed.
-- -----------------------------------------------------------------------------
REVOKE ALL ON DATABASE aikm FROM aikm_viewer;
GRANT CONNECT ON DATABASE aikm TO aikm_viewer;
-- TEMPORARY privilege is NOT granted — pg-viewer never needs temp tables.

-- -----------------------------------------------------------------------------
-- 6. Schema-level grants + blanket SELECT on all current public tables.
-- -----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO aikm_viewer;
-- M2 (post-critic 2026-04-20): aikm_viewer seeing information_schema +
-- pg_catalog is a deliberate design choice, risk-accepted per plan.md
-- "Security Model" L5 (admin-only feature — info_schema leak is low-risk).
GRANT USAGE ON SCHEMA information_schema TO aikm_viewer; -- explicit, normally PUBLIC
GRANT USAGE ON SCHEMA pg_catalog           TO aikm_viewer; -- explicit, normally PUBLIC
GRANT SELECT ON ALL TABLES IN SCHEMA public TO aikm_viewer;

-- -----------------------------------------------------------------------------
-- 7. Default privileges for FUTURE tables — must be declared per creating-role.
--    Without these, tables created by postgres or aikm after this migration
--    are invisible to aikm_viewer until a grant sweep.
-- -----------------------------------------------------------------------------
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT SELECT ON TABLES TO aikm_viewer;
ALTER DEFAULT PRIVILEGES FOR ROLE aikm IN SCHEMA public
  GRANT SELECT ON TABLES TO aikm_viewer;
-- Operators: if a new table-creating role is introduced, ADD a line here.

-- -----------------------------------------------------------------------------
-- 8. Belt-and-suspenders REVOKEs + function lockout.
--    Even if a future grant drift gives aikm_viewer INSERT, these REVOKEs win.
-- -----------------------------------------------------------------------------
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON ALL TABLES IN SCHEMA public FROM aikm_viewer;
REVOKE CREATE   ON SCHEMA public FROM aikm_viewer;
REVOKE CREATE   ON SCHEMA public FROM PUBLIC;        -- PG 14+ default hardening
REVOKE EXECUTE  ON ALL FUNCTIONS IN SCHEMA public FROM aikm_viewer;
-- H3 fix (post-critic 2026-04-20): explicitly GRANT USAGE + CONNECT to existing
-- application roles BEFORE we REVOKE from PUBLIC. Without this, any role that
-- relied on the default `GRANT USAGE ON SCHEMA public TO PUBLIC` (pre-PG 15
-- default) loses schema access on re-run. Safe on PG 16 (these statements are
-- no-ops if the grants already exist).
GRANT USAGE ON SCHEMA public TO aikm;
GRANT CONNECT ON DATABASE aikm TO aikm;
REVOKE ALL      ON SCHEMA public   FROM PUBLIC;
REVOKE ALL      ON DATABASE aikm   FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA public                  REVOKE EXECUTE ON FUNCTIONS FROM aikm_viewer;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM aikm_viewer;
ALTER DEFAULT PRIVILEGES FOR ROLE aikm     IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM aikm_viewer;

-- -----------------------------------------------------------------------------
-- 9. Sensitive-table isolation.
--    These tables hold credentials / PII — aikm_viewer must never SELECT from
--    them directly. A curated users_public view is exposed instead (§10).
--    ALL REVOKEs here are IF-EXISTS-guarded — on a truly fresh 16-alpine, the
--    aikm application bootstrap may not have created `users` yet, and the
--    T-003 acceptance test requires this migration to be runnable in isolation.
-- -----------------------------------------------------------------------------
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='users') THEN
    EXECUTE 'REVOKE SELECT ON TABLE public.users FROM aikm_viewer';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='sessions') THEN
    EXECUTE 'REVOKE ALL ON TABLE public.sessions FROM aikm_viewer';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='api_keys') THEN
    EXECUTE 'REVOKE ALL ON TABLE public.api_keys FROM aikm_viewer';
  END IF;
  -- pg_viewer_audit_log REVOKE is re-asserted in 002 (after the table exists).
  IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='pg_viewer_audit_log') THEN
    EXECUTE 'REVOKE ALL ON TABLE public.pg_viewer_audit_log FROM aikm_viewer';
  END IF;
END $$;

-- -----------------------------------------------------------------------------
-- 9b. Dedicated audit-log purger role (R2 M1).
--     The weekly retention cron needs DROP TABLE on old partitions. aikm is
--     append-only; postgres is too high-privilege for a cron identity. Create
--     a minimal role whose sole purpose is partition DROP on the audit tree.
--     Ownership of the partitions is transferred in 002 (owner can DROP).
-- -----------------------------------------------------------------------------
DO $$
BEGIN
  IF :'pg_audit_purger_password' IS NULL OR :'pg_audit_purger_password' = '' THEN
    RAISE EXCEPTION 'pg_audit_purger_password psql variable is empty — pass `-v pg_audit_purger_password=<hex>` explicitly';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aikm_audit_purger') THEN
    EXECUTE format(
      'CREATE ROLE aikm_audit_purger LOGIN PASSWORD %L CONNECTION LIMIT 2 NOINHERIT',
      :'pg_audit_purger_password'
    );
  ELSE
    -- Same re-run password rotation warning as aikm_viewer above.
    EXECUTE format(
      'ALTER ROLE aikm_audit_purger WITH LOGIN PASSWORD %L CONNECTION LIMIT 2 NOINHERIT',
      :'pg_audit_purger_password'
    );
  END IF;
END $$;

ALTER ROLE aikm_audit_purger SET statement_timeout = '60s';  -- DROP TABLE is fast but allow headroom
ALTER ROLE aikm_audit_purger SET lock_timeout       = '5s';

REVOKE ALL ON DATABASE aikm FROM aikm_audit_purger;
GRANT  CONNECT ON DATABASE aikm TO aikm_audit_purger;
GRANT  USAGE   ON SCHEMA   public TO aikm_audit_purger;

-- Belt-and-suspenders: purger must not read or write anything in public
-- (ownership of partitions is granted in 002; DROP works via ownership, not grants).
REVOKE CREATE  ON SCHEMA public FROM aikm_audit_purger;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM aikm_audit_purger;
REVOKE SELECT, INSERT, UPDATE, DELETE, REFERENCES, TRIGGER
  ON ALL TABLES IN SCHEMA public FROM aikm_audit_purger;

-- -----------------------------------------------------------------------------
-- 10. Curated safe view — users_public.
--     Exposes exactly the columns FR-062 declares safe for admin internal use.
--     Note: email is SAFE at storage layer (FR-062); a separate UI-layer mask
--     (j***@domain.com) applies only in the audit-tab renderer, not here.
--     View is owned by postgres so aikm_viewer can SELECT (owner bypasses grants
--     on underlying users table — see "security definer via view" pattern).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.users_public AS
  SELECT id, email, display_name, account_level, created_at, last_login_at
  FROM public.users;

ALTER VIEW public.users_public OWNER TO postgres;
GRANT SELECT ON public.users_public TO aikm_viewer;

-- -----------------------------------------------------------------------------
-- 11. Verification (all of the first four columns describe aikm_viewer's REAL
--     privileges after this migration — they are the acceptance test).
--     Expected: can_select_users=f, can_insert_users=f, can_create_schema=f,
--               can_select_view=t, role_aikm_viewer=t, role_aikm_audit_purger=t,
--               view_users_public=t, aikm_viewer_denied_users=t,
--               aikm_viewer_granted_users_public=t.
-- -----------------------------------------------------------------------------
\echo '=== 001 verification ==='
SELECT
  has_table_privilege ('aikm_viewer', 'public.users',        'SELECT') AS can_select_users,
  has_table_privilege ('aikm_viewer', 'public.users',        'INSERT') AS can_insert_users,
  has_schema_privilege('aikm_viewer', 'public',              'CREATE') AS can_create_schema,
  has_table_privilege ('aikm_viewer', 'public.users_public', 'SELECT') AS can_select_view,
  EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aikm_viewer')           AS role_aikm_viewer,
  EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aikm_audit_purger')     AS role_aikm_audit_purger,
  EXISTS(SELECT 1 FROM pg_views WHERE schemaname='public' AND viewname='users_public') AS view_users_public,
  NOT EXISTS(
    SELECT 1 FROM information_schema.role_table_grants
    WHERE grantee='aikm_viewer' AND table_schema='public' AND table_name='users'
  ) AS aikm_viewer_denied_users,
  EXISTS(
    SELECT 1 FROM information_schema.role_table_grants
    WHERE grantee='aikm_viewer' AND table_schema='public' AND table_name='users_public'
      AND privilege_type='SELECT'
  ) AS aikm_viewer_granted_users_public;
\echo '=== 001 done ==='

-- L5 fix (post-critic 2026-04-20): exit-code contract. RAISE EXCEPTION on any
-- invariant violation so CI can rely on psql exit status rather than parsing
-- the \echo output.
DO $verify$
BEGIN
  IF     has_table_privilege ('aikm_viewer', 'public.users',        'SELECT') THEN RAISE EXCEPTION '001 verification failed: aikm_viewer can SELECT public.users (leak)'; END IF;
  IF     has_table_privilege ('aikm_viewer', 'public.users',        'INSERT') THEN RAISE EXCEPTION '001 verification failed: aikm_viewer has INSERT on public.users'; END IF;
  IF     has_schema_privilege('aikm_viewer', 'public',              'CREATE') THEN RAISE EXCEPTION '001 verification failed: aikm_viewer has CREATE on schema public'; END IF;
  IF NOT has_table_privilege ('aikm_viewer', 'public.users_public', 'SELECT') THEN RAISE EXCEPTION '001 verification failed: aikm_viewer missing SELECT on users_public view'; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aikm_viewer')         THEN RAISE EXCEPTION '001 verification failed: aikm_viewer role missing'; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aikm_audit_purger')   THEN RAISE EXCEPTION '001 verification failed: aikm_audit_purger role missing'; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_views WHERE schemaname='public' AND viewname='users_public') THEN RAISE EXCEPTION '001 verification failed: users_public view missing'; END IF;
END
$verify$;
