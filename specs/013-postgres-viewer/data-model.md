# Data Model: PostgreSQL Online Viewer

**Feature**: 013-postgres-viewer
**Date**: 2026-04-20

## Overview

One new table and one new Postgres role. No changes to existing tables.

---

## 1. `pg_viewer_audit_log`

**Purpose**: Record every admin action in the PG viewer for security audit and debugging.

**Storage**: PostgreSQL `aikm` database.

**Fields**:

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | BIGSERIAL PK | NO | auto | Surrogate key |
| `user_id` | VARCHAR(36) | NO | — | FK to `users.id` (no constraint, soft ref — user may be deleted later) |
| `user_email` | VARCHAR(255) | YES | NULL | Snapshot of user email at query time |
| `action` | VARCHAR(32) | NO | — | One of: `list_tables`, `schema`, `browse`, `filter`, `export`, `sql_editor` |
| `query_type` | VARCHAR(16) | NO | `'table_browse'` | One of: `table_browse`, `schema`, `sql_editor` — coarse classification for analytics / retention filter |
| `raw_sql` | TEXT | YES | NULL | Present only when `query_type='sql_editor'`. Truncated to `PG_VIEWER_SQL_MAX_LEN` (8000). NULL for browse/schema rows. |
| `table_name` | VARCHAR(128) | YES | NULL | Target table (NULL for `list_tables`) |
| `filters_json` | JSONB | YES | NULL | Applied filters as a JSON array `[{col, op, value}]` |
| `order_by` | VARCHAR(128) | YES | NULL | ORDER BY column, if any |
| `order_dir` | VARCHAR(4) | YES | NULL | `ASC` or `DESC` |
| `limit_val` | INTEGER | YES | NULL | LIMIT applied |
| `offset_val` | INTEGER | YES | NULL | OFFSET applied |
| `row_count` | INTEGER | NO | 0 | Rows returned (a.k.a. `rows_returned` in API-level docs) |
| `execution_ms` | REAL | YES | NULL | Time to execute the SELECT |
| `status` | VARCHAR(16) | NO | `'ok'` | `ok`, `timeout`, `error`, `forbidden` |
| `error_message` | TEXT | YES | NULL | Populated if status != ok |
| `ip_address` | INET | YES | NULL | Client IP (from `X-Forwarded-For` if behind proxy) |
| `user_agent` | TEXT | YES | NULL | Browser UA |
| `created_at` | TIMESTAMPTZ | NO | NOW() | Row timestamp |

**Indexes**:

- `idx_pgva_user` on `(user_id, created_at DESC)`
- `idx_pgva_table` on `(table_name, created_at DESC)`
- `idx_pgva_created` on `(created_at DESC)`
- `idx_pgva_status` on `(status)` WHERE `status <> 'ok'` (partial, small)
- `idx_pgva_sql_editor` on `(user_id, created_at DESC)` WHERE `query_type = 'sql_editor'` (partial — for SQL-editor-specific audit review)

**Retention**: 180 days default (configurable via `PG_VIEWER_AUDIT_RETENTION_DAYS`). Weekly purge runbook in `quickstart.md §9`. Table is MONTHLY partitioned (`created_at`) when row count exceeds 1M — see `002_audit_table.sql` in §4.

**Why not reuse `query_audit_log`**: Existing table has NL2SQL-specific fields (`question`, `sql_generated`, `mode`, `cached`) whose semantics don't apply here. Separating keeps queries clean and makes retention policies independent.

---

## 2. Postgres Role `aikm_viewer`

**Purpose**: The connection identity used by the PG-viewer backend module. Has only `SELECT` privileges so write is impossible at the engine level.

**Grants (authoritative set; migration must match)**:

```sql
-- Role creation
CREATE ROLE aikm_viewer LOGIN PASSWORD :'pg_viewer_password';

-- Schema access
GRANT USAGE ON SCHEMA public TO aikm_viewer;

-- SELECT on all existing tables
GRANT SELECT ON ALL TABLES IN SCHEMA public TO aikm_viewer;

-- SELECT on future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO aikm_viewer;

-- Needed for introspection (already default-granted to PUBLIC, but be explicit)
GRANT USAGE ON SCHEMA information_schema TO aikm_viewer;
GRANT USAGE ON SCHEMA pg_catalog TO aikm_viewer;

-- Explicit REVOKEs as belt-and-suspenders against any prior grant drift
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON ALL TABLES IN SCHEMA public FROM aikm_viewer;
REVOKE CREATE ON SCHEMA public FROM aikm_viewer;
REVOKE ALL ON DATABASE aikm FROM aikm_viewer;
GRANT CONNECT, TEMPORARY ON DATABASE aikm TO aikm_viewer;  -- minimal DB-level
-- (TEMPORARY needed? no — revoke it too)
REVOKE TEMPORARY ON DATABASE aikm FROM aikm_viewer;
```

**Verification query (used by migration acceptance and CI check)**:

```sql
-- All of these must return false
SELECT has_table_privilege('aikm_viewer', 'public.users', 'INSERT') AS can_insert,
       has_table_privilege('aikm_viewer', 'public.users', 'UPDATE') AS can_update,
       has_table_privilege('aikm_viewer', 'public.users', 'DELETE') AS can_delete,
       has_schema_privilege('aikm_viewer', 'public', 'CREATE')      AS can_create;
```

---

## 3. Sensitive-column Config (code, not table)

Declared at `backend/app/services/pg_viewer/redaction.py`:

```python
# NOTE (post-critic): sensitive TABLES (users, sessions, api_keys, pg_viewer_audit_log)
# are REVOKEd at role level — aikm_viewer cannot SELECT them at all.
# This dict is a SECONDARY defense for tables that remain visible.
HIDDEN_COLUMNS: set[tuple[str, str]] = {
    # Concretized from a schema scan on 192.168.1.11 at review time (L-5 consistency).
    # NOTE (R2-H1 decision 2026-04-20): `email` is SAFE for admin/internal purposes — FR-062
    # declares email in the curated `users_public` projection. Email is NOT in HIDDEN_COLUMNS.
    # A separate UI-layer email mask (j***@domain.com) applies ONLY to the audit-log viewer —
    # see FR-062a + EMAIL_MASK_UI_COLUMNS below.
    ("system_settings", "value"),     # redacted per ROW_RULE below
}

REDACTED_BY_ROW_RULE = {
    "system_settings": {
        "column_to_mask": "value",
        "key_column": "key",
        "key_substrings": ["secret", "token", "api_key", "password", "credential", "private_key", "passphrase"],
        "mask": "***",
    },
}

# UI-layer email mask — applied ONLY to the audit-tab rendering so that an admin reading
# the audit log sees `j***@domain.com` instead of peer admins' raw emails. Does NOT alter
# the stored `user_email` column in `pg_viewer_audit_log` (kept raw for forensics). The
# mask is applied server-side in the `/audit` response serializer. (R2-H1 resolution.)
EMAIL_MASK_UI_COLUMNS: set[tuple[str, str]] = {
    ("pg_viewer_audit_log", "user_email"),
}

def mask_email_ui(email: str | None) -> str | None:
    if not email or "@" not in email: return email
    local, _, domain = email.partition("@")
    if len(local) <= 1: return f"*@{domain}"
    return f"{local[0]}***@{domain}"
```

**Policy**: Adding a new table requires a code-review pass against this file (enforced by `critic`). A discovery test iterates `information_schema.columns` FROM THE `aikm_viewer` ROLE'S PERSPECTIVE and fails if a column name matches `/password|secret|token|api_key|credential|private_key|passphrase/i` and isn't in `HIDDEN_COLUMNS` or `REDACTED_BY_ROW_RULE`. The discovery test MUST be wired to CI (see T-041 grant-audit).

**PII redactor for audit raw_sql** (post-critic C4, FR-017a):

```python
# backend/app/services/pg_viewer/pii_redactor.py
# R2 tightening (2026-04-20): generic hex rule removed — too many false positives on
# legitimate UUIDs, bcrypt tokens, and session-id-looking analytics values. Match only
# known secret prefixes + bearer tokens + literals near sensitive column names.
_PATTERNS = [
    # Bearer tokens (HTTP header style, ≥20 chars, base64url alphabet only)
    (re.compile(r'Bearer\s+[0-9a-zA-Z._\-]{20,}', re.I),  'Bearer [REDACTED]'),
    # GitHub PAT classic
    (re.compile(r'ghp_[A-Za-z0-9]{20,}'),                '[REDACTED_GHP]'),
    # GitHub fine-grained PAT (2026 format)
    (re.compile(r'github_pat_[A-Za-z0-9_]{20,}'),        '[REDACTED_GH_PAT]'),
    # Anthropic keys
    (re.compile(r'sk-ant-[A-Za-z0-9_\-]{20,}'),         '[REDACTED_SK_ANT]'),
    # OpenAI + other sk-* keys
    (re.compile(r'sk-[A-Za-z0-9]{20,}'),                 '[REDACTED_SK]'),
    # quoted-literal adjacent to sensitive column refs
    (re.compile(r"(password|secret|token|api_key|hash|credential)\s*[=<>]\s*'[^']{8,}'", re.I),
                r"\1 = '[REDACTED_STR]'"),
]
def redact_sql_for_audit(sql: str) -> str:
    for pat, repl in _PATTERNS:
        sql = pat.sub(repl, sql)
    return sql[:8000]  # truncate AFTER redaction
```

---

## 4. Migration SQL — split into two files (post-critic C1 ops)

Two files, two roles. Both idempotent. Run order: 001 → 002.

### 4a. `backend/scripts/pg_viewer_migrate_001_role_and_grants.sql`

**Runs as**: `postgres` superuser (one-off; re-runnable).
**Purpose**: Create role, install grants, install `users_public` view, REVOKE sensitive tables, block dangerous extensions. No `BEGIN/COMMIT` wrapping role creation (some PG versions disallow `CREATE ROLE` in some tx modes — keep as implicit autocommit).

```sql
\set ON_ERROR_STOP on

-- 1. Fail fast if dangerous extensions installed
DO $$ DECLARE ext_name TEXT; BEGIN
  FOR ext_name IN SELECT extname FROM pg_extension
    WHERE extname IN ('dblink','postgres_fdw','file_fdw','plperlu','plpythonu','plsh','adminpack') LOOP
    RAISE EXCEPTION 'pg_viewer migration aborted: dangerous extension % present. REVOKE EXECUTE on its functions from aikm_viewer first, then remove from this denylist if vetted.', ext_name;
  END LOOP; END $$;

-- 2. Short lock timeout to avoid freezing ETL
SET lock_timeout = '5s';

-- 3. Create or update role (idempotent)
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aikm_viewer') THEN
    EXECUTE format('CREATE ROLE aikm_viewer LOGIN PASSWORD %L CONNECTION LIMIT 10', :'pg_viewer_password');
  ELSE
    EXECUTE format('ALTER ROLE aikm_viewer WITH LOGIN PASSWORD %L CONNECTION LIMIT 10', :'pg_viewer_password');
  END IF;
END $$;

-- 4. Role-level session settings (three-layer timeout fix — critic C3 consistency)
ALTER ROLE aikm_viewer SET statement_timeout = '10s';
ALTER ROLE aikm_viewer SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE aikm_viewer SET lock_timeout = '2s';

-- 5. Minimal DB-level privileges
REVOKE ALL ON DATABASE aikm FROM aikm_viewer;
GRANT CONNECT ON DATABASE aikm TO aikm_viewer;

-- 6. Schema + SELECT on all CURRENT tables in public
GRANT USAGE ON SCHEMA public TO aikm_viewer;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO aikm_viewer;

-- 7. Default-privileges for EVERY role that can create tables in public (critic C2 ops)
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT SELECT ON TABLES TO aikm_viewer;
ALTER DEFAULT PRIVILEGES FOR ROLE aikm     IN SCHEMA public
  GRANT SELECT ON TABLES TO aikm_viewer;
-- Operators: if a new role is added that creates tables in public, add a line here.

-- 8. Explicit REVOKEs (belt-and-suspenders)
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON ALL TABLES IN SCHEMA public FROM aikm_viewer;
REVOKE CREATE ON SCHEMA public FROM aikm_viewer;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;        -- PG 14 safety
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM aikm_viewer;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM aikm_viewer;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM aikm_viewer;
ALTER DEFAULT PRIVILEGES FOR ROLE aikm     IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM aikm_viewer;

-- 9. Sensitive-table isolation (option-b view approach — critic C3 security)
REVOKE SELECT ON TABLE public.users            FROM aikm_viewer;
REVOKE SELECT ON TABLE public.sessions         FROM aikm_viewer;
REVOKE SELECT ON TABLE public.api_keys         FROM aikm_viewer;
-- pg_viewer_audit_log — REVOKE is re-asserted in 002 after the table exists

-- 9b. Dedicated purger role (R2 M1 resolution 2026-04-20)
-- The weekly retention cron needs to DROP month-old partitions of pg_viewer_audit_log.
-- The aikm role is append-only on that table (REVOKE UPDATE, DELETE, TRUNCATE in 002),
-- so DROP TABLE on a partition would fail for aikm too (not table owner). Using postgres
-- superuser in cron is high-privilege and easy to misuse. Solution: a dedicated role
-- `aikm_audit_purger` whose ONLY capability is DROP on pg_viewer_audit_log_* partitions.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aikm_audit_purger') THEN
    EXECUTE format('CREATE ROLE aikm_audit_purger LOGIN PASSWORD %L CONNECTION LIMIT 2', :'pg_audit_purger_password');
  ELSE
    EXECUTE format('ALTER ROLE aikm_audit_purger WITH LOGIN PASSWORD %L CONNECTION LIMIT 2', :'pg_audit_purger_password');
  END IF;
END $$;

REVOKE ALL ON DATABASE aikm FROM aikm_audit_purger;
GRANT CONNECT ON DATABASE aikm TO aikm_audit_purger;
GRANT USAGE  ON SCHEMA   public TO aikm_audit_purger;
-- NO SELECT, NO INSERT on anything in public. Purger only detaches + drops partitions.

-- Ownership transfer of the partitioned parent + all partition children happens in 002
-- (which runs as aikm and can issue ALTER TABLE … OWNER TO aikm_audit_purger).

-- Belt-and-suspenders lock-down
REVOKE CREATE ON SCHEMA public FROM aikm_audit_purger;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM aikm_audit_purger;

-- 10. Curated safe view for user browsing
CREATE OR REPLACE VIEW public.users_public AS
  SELECT id, email, display_name, account_level, created_at, last_login_at
  FROM public.users;
GRANT SELECT ON public.users_public TO aikm_viewer;

-- 11. Verification (all must be false)
SELECT has_table_privilege('aikm_viewer', 'public.users',     'SELECT') AS can_select_users,
       has_table_privilege('aikm_viewer', 'public.users',     'INSERT') AS can_insert_users,
       has_schema_privilege('aikm_viewer','public',            'CREATE') AS can_create_schema,
       has_table_privilege('aikm_viewer', 'public.users_public','SELECT') AS can_select_view;
-- Expect: f, f, f, t
```

### 4b. `backend/scripts/pg_viewer_migrate_002_audit_table.sql`

**Runs as**: `aikm` role (normal deploy identity). Idempotent; re-runnable every deploy.

```sql
\set ON_ERROR_STOP on

BEGIN;

-- Partitioned audit log table (monthly range by created_at)
CREATE TABLE IF NOT EXISTS pg_viewer_audit_log (
    id              BIGSERIAL,
    user_id         VARCHAR(36)  NOT NULL,
    user_email      VARCHAR(255),
    action          VARCHAR(32)  NOT NULL CHECK (action IN ('list_tables','schema','browse','filter','export','sql_editor')),
    query_type      VARCHAR(16)  NOT NULL DEFAULT 'table_browse' CHECK (query_type IN ('table_browse','schema','sql_editor')),
    raw_sql         TEXT,
    table_name      VARCHAR(128),
    filters_json    JSONB,
    order_by        VARCHAR(128),
    order_dir       VARCHAR(4)   CHECK (order_dir IN ('ASC','DESC') OR order_dir IS NULL),
    limit_val       INTEGER,
    offset_val      INTEGER,
    row_count       INTEGER      NOT NULL DEFAULT 0,
    execution_ms    REAL,
    status          VARCHAR(16)  NOT NULL DEFAULT 'ok' CHECK (status IN ('ok','timeout','error','forbidden','rate_limited','denied')),  -- 'denied' added 2026-04-20 post-critic H1: required by T-014.5 rate limiter + guardrail callsite. Semantics: 'forbidden'=authZ failure at API layer (admin check); 'denied'=guardrail block before SQL reached DB (keyword/function denylist, LIMIT>cap).
    error_message   TEXT,
    ip_address      INET,
    user_agent      TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at),
    CONSTRAINT chk_raw_sql_only_for_editor
      CHECK ((query_type = 'sql_editor' AND raw_sql IS NOT NULL)
          OR (query_type <> 'sql_editor' AND raw_sql IS NULL)),
    CONSTRAINT chk_raw_sql_length
      CHECK (raw_sql IS NULL OR octet_length(raw_sql) <= 8192),
    CONSTRAINT chk_action_query_type
      CHECK (
        (action IN ('list_tables','browse','filter','export') AND query_type='table_browse')
        OR (action = 'schema'      AND query_type='schema')
        OR (action = 'sql_editor'  AND query_type='sql_editor')
      )
) PARTITION BY RANGE (created_at);

-- Create first partitions (operator runbook must create new ones monthly; see quickstart §9)
CREATE TABLE IF NOT EXISTS pg_viewer_audit_log_2026_04
  PARTITION OF pg_viewer_audit_log FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE IF NOT EXISTS pg_viewer_audit_log_2026_05
  PARTITION OF pg_viewer_audit_log FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
-- NOTE: each month a new partition is created by a cron on 192.168.1.11.

CREATE INDEX IF NOT EXISTS idx_pgva_user       ON pg_viewer_audit_log (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pgva_table      ON pg_viewer_audit_log (table_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pgva_created    ON pg_viewer_audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pgva_status     ON pg_viewer_audit_log (status) WHERE status <> 'ok';
CREATE INDEX IF NOT EXISTS idx_pgva_sql_editor ON pg_viewer_audit_log (user_id, created_at DESC) WHERE query_type = 'sql_editor';

-- Spillover table (R2 N2 resolution 2026-04-20)
-- If a future write hits a date for which no partition exists, the parent insert raises
-- 23514 check_violation. write_audit() catches that and INSERTs into this plain table
-- so forensic data is never lost. An operator alert triggers on every row inserted here.
CREATE TABLE IF NOT EXISTS pg_viewer_audit_log_spillover (
    LIKE pg_viewer_audit_log INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING IDENTITY,
    spillover_reason TEXT,
    spilled_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pgva_spill_time ON pg_viewer_audit_log_spillover (spilled_at DESC);
GRANT INSERT, SELECT ON pg_viewer_audit_log_spillover TO aikm;
REVOKE UPDATE, DELETE, TRUNCATE ON pg_viewer_audit_log_spillover FROM aikm;
REVOKE SELECT ON pg_viewer_audit_log_spillover FROM aikm_viewer;

-- Partition-maintenance function (R2 N2 resolution)
-- pg_partman is preferred on environments where the extension is installed; on stock
-- aikm-postgres (postgres:16-alpine) it is NOT available, so we ship a shell+SQL fallback.
-- The function below creates next month's partition idempotently. Called by nightly
-- healthcheck cron (see quickstart §10). Runs as aikm (owner of partitioned parent).
CREATE OR REPLACE FUNCTION ensure_next_audit_partition()
RETURNS TABLE(partition_name TEXT, created BOOL) LANGUAGE plpgsql AS $func$
DECLARE
    nm TIMESTAMPTZ := date_trunc('month', NOW() + INTERVAL '1 month');
    nm2 TIMESTAMPTZ := nm + INTERVAL '1 month';
    pname TEXT := 'pg_viewer_audit_log_' || to_char(nm, 'YYYY_MM');
    exists_row RECORD;
BEGIN
    SELECT 1 INTO exists_row FROM pg_class
        WHERE relname = pname AND relkind IN ('r','p');
    IF NOT FOUND THEN
        EXECUTE format(
            'CREATE TABLE %I PARTITION OF pg_viewer_audit_log FOR VALUES FROM (%L) TO (%L)',
            pname, nm, nm2);
        -- per-partition lock-down: append-only + purger ownership
        EXECUTE format('REVOKE UPDATE, DELETE, TRUNCATE ON %I FROM aikm', pname);
        EXECUTE format('REVOKE SELECT ON %I FROM aikm_viewer', pname);
        EXECUTE format('ALTER TABLE %I OWNER TO aikm_audit_purger', pname);
        RETURN QUERY SELECT pname, TRUE;
    ELSE
        RETURN QUERY SELECT pname, FALSE;
    END IF;
END;
$func$;

-- Make partitioned-parent + existing partitions owned by purger so DROP works without superuser.
ALTER TABLE pg_viewer_audit_log            OWNER TO aikm_audit_purger;
ALTER TABLE pg_viewer_audit_log_2026_04    OWNER TO aikm_audit_purger;
ALTER TABLE pg_viewer_audit_log_2026_05    OWNER TO aikm_audit_purger;

-- per-partition REVOKE — each partition inherits append-only semantics (R2 N-partition-REVOKE)
REVOKE UPDATE, DELETE, TRUNCATE ON pg_viewer_audit_log_2026_04 FROM aikm;
REVOKE UPDATE, DELETE, TRUNCATE ON pg_viewer_audit_log_2026_05 FROM aikm;
REVOKE SELECT ON pg_viewer_audit_log_2026_04 FROM aikm_viewer;
REVOKE SELECT ON pg_viewer_audit_log_2026_05 FROM aikm_viewer;

-- aikm role must INSERT + SELECT but NOT UPDATE/DELETE on the partitioned parent
-- (append-only — critic C2 security). Grants flow to existing + future partitions.
REVOKE UPDATE, DELETE, TRUNCATE ON pg_viewer_audit_log FROM aikm;
GRANT INSERT, SELECT ON pg_viewer_audit_log TO aikm;
GRANT INSERT, SELECT ON pg_viewer_audit_log_2026_04 TO aikm;
GRANT INSERT, SELECT ON pg_viewer_audit_log_2026_05 TO aikm;

-- aikm_viewer must NOT see the audit log (critic M4 security)
REVOKE SELECT ON pg_viewer_audit_log FROM aikm_viewer;

-- aikm_audit_purger needs EXECUTE on the healthcheck function (for nightly cron)
GRANT EXECUTE ON FUNCTION ensure_next_audit_partition() TO aikm_audit_purger;
GRANT EXECUTE ON FUNCTION ensure_next_audit_partition() TO aikm;

COMMIT;

-- Verification (must be true/true/false/false/true)
SELECT has_table_privilege('aikm',              'pg_viewer_audit_log','INSERT') AS aikm_insert,
       has_table_privilege('aikm',              'pg_viewer_audit_log','SELECT') AS aikm_select,
       has_table_privilege('aikm',              'pg_viewer_audit_log','UPDATE') AS aikm_update,
       has_table_privilege('aikm_viewer',       'pg_viewer_audit_log','SELECT') AS viewer_select,
       pg_has_role('aikm_audit_purger', pg_class.relowner, 'USAGE') AS purger_owns_parent
  FROM pg_class WHERE relname = 'pg_viewer_audit_log';
-- Expect: t, t, f, f, t
```

### 4c. Password format

Generate once on first deploy:

```bash
openssl rand -hex 32   # for PG_VIEWER_PASSWORD (aikm_viewer)
openssl rand -hex 32   # for PG_AUDIT_PURGER_PASSWORD (aikm_audit_purger, R2 M1)
```

Both are 64-char URL-safe hex; NOT base64 which contains `/+=` that break DSNs. Store in `/etc/aikm/.env` on 192.168.1.11:

```
PG_VIEWER_PASSWORD=<hex>
PG_AUDIT_PURGER_PASSWORD=<hex>
PG_VIEWER_DATABASE_URL=postgresql+asyncpg://aikm_viewer:${PG_VIEWER_PASSWORD}@postgres:5432/aikm
```

The purger password is passed to migration 001 via `-v pg_audit_purger_password=...` and is used by the weekly purge cron (quickstart §10). Purger password is rotated on the same 90-day schedule as `aikm_viewer`; runbook entry in quickstart §9.

### 4d. Pre-flight check (runbook)

Before running 001:
```bash
docker exec aikm-postgres psql -U postgres -d aikm -tAc   "SELECT rolsuper FROM pg_roles WHERE rolname='postgres'"
# Must return t. If running as a non-superuser, abort.

docker exec aikm-postgres psql -U postgres -c "SHOW max_connections"
# Must be >= 200 (viewer pool needs headroom on top of existing pools).

# Detect pg_partman availability (R2 N2). Optional — if present, use it instead of the shell+SQL fallback.
docker exec aikm-postgres psql -U postgres -d aikm -tAc   "SELECT 1 FROM pg_available_extensions WHERE name='pg_partman'"
# If returns 1 → preferred path: CREATE EXTENSION pg_partman; + create_parent(...) — document in quickstart §10.
# If empty       → fallback path: ensure_next_audit_partition() shell cron (shipped in 002).

# Generate both passwords
export PG_VIEWER_PASSWORD=$(openssl rand -hex 32)
export PG_AUDIT_PURGER_PASSWORD=$(openssl rand -hex 32)

docker compose stop aikm-maximo-extractor
# Pause ETL to avoid AccessShareLock contention during GRANT ALL iteration (critic M1 ops).
```

After 002 succeeds, re-start the ETL: `docker compose start aikm-maximo-extractor`.

---

## 5. Entity Relationship

```
users (existing)
  │
  │ (soft ref — no FK constraint; audit rows survive user deletion)
  ▼
pg_viewer_audit_log  (NEW, PARTITIONED BY RANGE created_at, owned by aikm_audit_purger)
  ├─ pg_viewer_audit_log_2026_04  (partition child)
  ├─ pg_viewer_audit_log_2026_05
  └─ … new partitions created by nightly `ensure_next_audit_partition()` cron

pg_viewer_audit_log_spillover  (NEW, plain table — fallback if a write hits a missing partition)
```

Three roles interact with this tree:

| Role | DB capability on pg_viewer_audit_log* |
|---|---|
| `aikm` | INSERT + SELECT on parent + all partitions + spillover (append-only) |
| `aikm_viewer` | NO access (REVOKE SELECT — L5 defense) |
| `aikm_audit_purger` | TABLE OWNER — DROP PARTITION (weekly), EXECUTE ensure_next_audit_partition() (nightly) |

No other references. `pg_viewer_audit_log` is orthogonal to `query_audit_log`, `permission_groups`, `user_permissions`.
