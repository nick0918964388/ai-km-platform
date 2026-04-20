# Technical Research: PostgreSQL Online Viewer

**Feature**: 013-postgres-viewer
**Date**: 2026-04-20
**Status**: Complete — recommendation below

## Executive Summary

**Recommendation: Custom embedded UI (FastAPI endpoints + Next.js admin page)**, powered at the data layer by a dedicated read-only Postgres role `aikm_viewer`. Not pgAdmin, not Adminer.

Two reasons outweigh everything else:
1. **Auth integration**: Our existing JWT + `require_admin` cannot be grafted onto pgAdmin/Adminer without a fragile reverse-proxy ACL. A single admin-bypass in the proxy = full DB exposure.
2. **Read-only enforcement depth**: pgAdmin and Adminer are full-featured admin tools; their "read-only" modes are UI hints, not engine-enforced. A dedicated PG role + parameterized-identifier validation in our backend is strictly safer.

Secondary reasons: UX consistency with IBM Carbon, audit-log uniformity, and we already have every primitive needed (`require_admin`, `sql_guard.py`, `circuit_breaker.py`, `result_budget.py`, `query_audit_log` migration pattern).

---

## Option Evaluation

### Option A — pgAdmin 4 (Docker)

- **Pros**: Mature, feature-rich (ER diagram, query profiler, backup/restore), free.
- **Cons**:
  - **Auth integration**: pgAdmin maintains its own user store. Our JWT cannot drive it. Options are (1) single shared pgAdmin account whose creds we embed in reverse proxy — fragile and violates audit; (2) OAuth2 plugin — needs extra identity provider. Neither matches our NextAuth + JWT setup.
  - **Read-only enforcement**: pgAdmin always connects with whatever PG creds are configured. If the configured role has write privileges, pgAdmin will happily DROP TABLE. A RO-only PG role mitigates this but then loses half of pgAdmin's advertised value (backups, etc.).
  - **UX**: Completely different design language (Bootstrap), breaks our Carbon admin layout. Users have to mentally switch.
  - **Audit**: Native audit is minimal; we'd have to sniff Postgres logs or run `pgaudit` extension (extra ops burden).
  - **Deploy**: +1 container (aikm-pgadmin), +1 volume, +reverse-proxy rules. Shipping another ~200MB image for a feature with ~8 endpoints is disproportionate.
- **Verdict**: Reject.

### Option B — Adminer (Docker)

- **Pros**: Tiny (~1 PHP file), boot in seconds, decent read-only-ish UX.
- **Cons**:
  - **Auth**: Same as pgAdmin — needs its own login or shared creds embedded. No JWT integration.
  - **Read-only**: Adminer has NO read-only mode. Any DB user who connects through it can write.
  - **UX**: PHP-era UI, does not match Carbon; opening it inside our admin page needs an iframe (CSP/cookie headaches).
  - **Audit**: None.
- **Verdict**: Reject (weaker than pgAdmin on read-only, same auth problem).

### Option C — Custom embedded UI (CHOSEN)

- **Pros**:
  - **Auth**: `require_admin` dep already exists, one-line.
  - **Read-only**: Defense in depth — (i) dedicated `aikm_viewer` PG role with only SELECT grants, (ii) `SET LOCAL statement_timeout = '10s'`, (iii) identifier whitelist from `information_schema`, (iv) parameterized values, (v) auto `LIMIT 1000`.
  - **UX**: Matches existing Carbon `/admin/*` pages, uses existing `DataTable` / `Pagination`.
  - **Audit**: Natively write to `pg_viewer_audit_log` in same transaction shape as `query_audit_log`.
  - **Deploy**: Zero new containers. Just a new router + migration.
  - **Extensibility**: If C-2 green-lights a SQL editor later, we wrap it in existing `sql_guard.scan_sql()` with one LOC.
- **Cons**:
  - Build time: ~3-5 engineer-days for v1 (vs. ~1 day to stand up pgAdmin). Offset by avoided ongoing auth/ops friction.
  - We have to build schema introspection ourselves. But Postgres `information_schema` is flat SQL — a dozen lines of boilerplate, not a real cost.
- **Verdict**: **Adopt.**

---

## Evaluation Matrix

| Criterion                            | pgAdmin | Adminer | Custom UI |
|---                                   |---      |---      |---        |
| (a) JWT auth integration             | ⨯       | ⨯       | ✓ (trivial)|
| (b) Read-only enforcement strength   | weak    | none    | strong (role + guard + timeout) |
| (c) UX consistency with Carbon       | ⨯       | ⨯       | ✓         |
| (d) Deployment complexity            | +container, +proxy | +container, +proxy | none |
| (e) Audit logging capability         | weak (pgaudit) | none | native    |
| Time to v1                           | ~1d     | ~0.5d   | ~3-5d     |
| Long-term ops burden                 | medium  | low     | low       |

The custom route loses only on initial build time and wins on every dimension that matters for an **admin-only tool in a zero-trust-ish enterprise DB**.

---

## Key Technical Decisions

### D-1: Dedicated Postgres role `aikm_viewer`

```sql
-- Run as postgres superuser (see 001_role_and_grants.sql in data-model.md §4)
CREATE ROLE aikm_viewer LOGIN PASSWORD '<pwgen>'
    CONNECTION LIMIT 10;
ALTER ROLE aikm_viewer SET statement_timeout = '10s';
ALTER ROLE aikm_viewer SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE aikm_viewer SET lock_timeout = '2s';

GRANT CONNECT ON DATABASE aikm TO aikm_viewer;
GRANT USAGE ON SCHEMA public TO aikm_viewer;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO aikm_viewer;

-- Default-privileges for every role that creates tables in public
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT SELECT ON TABLES TO aikm_viewer;
ALTER DEFAULT PRIVILEGES FOR ROLE aikm     IN SCHEMA public GRANT SELECT ON TABLES TO aikm_viewer;
-- (Add any ETL role here too — see quickstart §9 drift audit.)

-- Sensitive tables: REVOKE SELECT entirely (option-b view approach per critic C3 security)
REVOKE SELECT ON public.users, public.sessions, public.api_keys, public.pg_viewer_audit_log FROM aikm_viewer;

-- Curated safe view for user browsing
CREATE OR REPLACE VIEW public.users_public AS
  SELECT id, email, display_name, account_level, created_at, last_login_at FROM public.users;
GRANT SELECT ON public.users_public TO aikm_viewer;

-- Explicit belt-and-suspenders REVOKEs
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON ALL TABLES IN SCHEMA public FROM aikm_viewer;
REVOKE CREATE ON SCHEMA public FROM aikm_viewer;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;   -- PG 14 safety
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM aikm_viewer;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM aikm_viewer;

-- Fail migration if any dangerous extension is installed
DO $$ DECLARE ext_name TEXT; BEGIN
  FOR ext_name IN SELECT extname FROM pg_extension
    WHERE extname IN ('dblink','postgres_fdw','file_fdw','plperlu','plpythonu','plsh','adminpack') LOOP
    RAISE EXCEPTION 'pg_viewer migration aborted: dangerous extension % present. Revoke EXECUTE from aikm_viewer on its functions first.', ext_name;
  END LOOP; END $$;
```

Env var `PG_VIEWER_DATABASE_URL` = `postgresql+asyncpg://aikm_viewer:<pw>@postgres:5432/aikm`.
Main backend continues to use `DATABASE_URL` with the `aikm` role.

**Password format**: generate via `openssl rand -hex 32` (NOT base64 — base64 emits `/+=` which require URL-escaping in a DSN; hex is always URL-safe).

### D-2: Separate connection pool

Use a second SQLAlchemy engine built lazily on first pg-viewer request:

- `pool_size=3, max_overflow=7, pool_pre_ping=True, pool_recycle=1800` — max 10 connections (post-critic H2 decision: raised from 5 to 10 to give headroom for the 5-concurrent-admin budget).
- asyncpg `connect_args={'command_timeout': 10}` as belt-and-suspenders for statement_timeout.
- Hand out sessions via a new dep `get_viewer_db`.
- Do NOT share with `get_db`; we do NOT want any code path ever to reach `aikm_viewer` from `aikm` session or vice versa.
- Budget check on deploy: `docker exec aikm-postgres psql -U postgres -c "SHOW max_connections"` MUST be ≥ 200 before this feature ships (documented in quickstart §2 pre-flight).

### D-3: Identifier validation  (post-critic C1: psycopg v3 + asyncpg bridge)

**Dep decision**: add `psycopg[binary]>=3.1` to `backend/requirements.txt` alongside the existing `asyncpg`. psycopg v3 is used ONLY for its `psycopg.sql.Identifier().as_string(conn)` helper to produce a pre-rendered quoted-identifier string; asyncpg remains the actual driver for the viewer engine. Rationale: asyncpg does not accept `psycopg.sql.Composed` objects — Composed cannot be handed to asyncpg, only rendered-to-string and interpolated alongside positional bind params.

Every table/column name used in SQL goes through `resolve_identifier(conn, table, column) -> str | raises`. It:
1. Checks against `information_schema.columns` (5-min LRU cache, keyed by `aikm_viewer`'s SELECT-visible columns).
2. Renders via `psycopg.sql.Identifier(name).as_string(conn)` — where `conn` is an ephemeral `psycopg.Connection` used ONLY for identifier quoting (no data queries).
3. Returns the quoted string for interpolation into the asyncpg query text. Values are ALWAYS bound via asyncpg's positional `$1, $2, ...` — never interpolated.
4. Raises 400 on miss.

**Explicit bridge rule**: `psycopg.sql.Composed` objects MUST NOT be passed to asyncpg. Only rendered strings. Composed → `.as_string(conn)` → asyncpg. Violating this rule is a code-review red-line enforced by `critic` in T-040.

**Alternative rejected**: writing a custom `QUOTE_IDENT` helper (`'"' + name.replace('"','""') + '"'` after whitelist) — safe but duplicates logic psycopg already ships. Keep the psycopg dep; benefit outweighs the ~2MB image growth.

Rationale: PG drivers will NOT parameterize identifiers (only values). Whitelist-then-quote is the only safe path.

### D-4: statement_timeout  (three layers, post-critic C3)

```python
# Layer (a) role-level — ALWAYS active regardless of transaction mode (migration)
ALTER ROLE aikm_viewer SET statement_timeout = '10s';
ALTER ROLE aikm_viewer SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE aikm_viewer SET lock_timeout = '2s';

# Layer (b) asyncpg pool-level — belt-and-suspenders in the driver
engine = create_async_engine(url, connect_args={"command_timeout": 10}, ...)

# Layer (c) per-transaction — explicit BEGIN (required)
async with engine.begin() as conn:
    await conn.execute(text("SET LOCAL statement_timeout = '10s'"))
    result = await conn.execute(query)
# Never `engine.connect()`, never AUTOCOMMIT.
```

**Why all three**: `SET LOCAL` is a no-op in AUTOCOMMIT mode. `command_timeout` cancels on driver side but may leave an orphan PG process. Role-level `statement_timeout` is the only defense that survives autocommit bugs and driver short-circuits. Defense in depth.

Test: T-010 + T-020 must include an integration test asserting `SELECT pg_sleep(30)` returns 408 in ≤ 11s.

### D-5: Sensitive-column redaction

Hard-coded allow/deny list in `backend/app/services/pg_viewer/redaction.py`:

```python
HIDDEN = {("users", "password_hash"), ("users", "password_salt")}
REDACTED_BY_KEY_SUBSTR = {
    "system_settings": {"column": "value", "key_col": "key", "substrings": ["secret", "token", "api_key"]}
}
```

Applied on every row before JSON serialization.

### D-6: Pagination strategy

- Default: **OFFSET/LIMIT** for simplicity. Fine up to ~1M rows with ORDER BY on indexed PK.
- If a table has `id` or a BIGSERIAL PK, allow keyset pagination (`WHERE id < $last_id`) as an opt-in future enhancement. Defer to v1.1.

### D-7: Circuit breaker

Reuse `app/services/circuit_breaker.py` — add a `pg_viewer` circuit. Open after 5 consecutive failures in 60s, half-open after 30s.

### D-8: Frontend data layer

New admin page `/admin/pg-viewer` using Carbon `DataTable`, `Pagination`, `SideNav` for the table list, `CodeSnippet` for the schema view. No new npm dependencies.

---

## Explicitly Rejected Alternatives

- **Hasura / PostgREST auto-generated API**: overkill, brings GraphQL or REST surface we don't want; still needs a UI; adds complexity to our auth model.
- **Metabase**: BI-focused, not DB admin; would conflict with our Dashboard page.
- **psql in a browser iframe**: security nightmare.
- **Relax main `aikm` role instead of new `aikm_viewer` role**: violates principle of least privilege and we CANNOT relax it (it needs writes for the rest of the app). So a second role is structurally necessary anyway.

---

## SQL Static Analysis Library (for the SELECT-only SQL editor — US5)

Added 2026-04-20 after user clarification C-2 promoted the SQL editor into v1 scope. We need to reject every non-SELECT statement **before** any DB round-trip, so the engine role is only a last-line defense, not the primary one.

### Options

| Library | Kind | Pros | Cons | Verdict |
|---|---|---|---|---|
| **`sqlparse`** | Pure-Python tokenizer (lexer, not a real parser) | Zero C deps; already transitively in backend via psycopg ecosystem; cheap; exposes `Keyword.DML/DDL/CTE` token classes; battle-tested in Airflow / Superset for exactly this "is it a SELECT" check | Not a full grammar — can be fooled by pathological input. Mitigation: combine with a strict keyword denylist AND statement-count check AND rely on `aikm_viewer` role as last line. | **ADOPT** |
| `pglast` | libpg_query bindings — Postgres' actual parser | Most accurate: parses like PG itself; returns real AST with node types (`SelectStmt` vs `DeleteStmt`) | Requires compiled C extension (libpg_query); wheel availability varies by Python version; container image size +; adds a build-time dep. | Reject for v1; revisit if sqlparse bypass is ever demonstrated. |
| Simple regex allow-list on first keyword | `re.match(r'^\s*(select\|with)\b', sql, re.I)` | Zero deps. | Can be bypassed by comments (`/* */ DROP …`), by CTE-shaped `WITH … DELETE` (valid PG but a write), and by any trailing semicolon-separated statement. Regex alone does not give us statement-count. | Reject — provably inadequate. |

### Decision

Use **`sqlparse` (≥ 0.4.4)** with a layered check:

1. `stripped = sql.strip().rstrip(';')` — single trailing semicolon tolerated.
2. If `';' in stripped:` → 400 multi-statement.
3. `statements = [s for s in sqlparse.parse(stripped) if s.tokens]` — MUST have `len == 1`.
4. `first = statements[0].token_first(skip_cm=True, skip_ws=True)` — MUST have `ttype in (Keyword.DML, Keyword.CTE)` AND `value.upper() in {"SELECT", "WITH"}`.
5. Walk `statements[0].flatten()`; if any token value (upper) appears in the forbidden KEYWORD set `{INSERT,UPDATE,DELETE,DROP,TRUNCATE,GRANT,REVOKE,CREATE,ALTER,COPY,CALL,VACUUM,ANALYZE,REINDEX,CLUSTER,COMMENT,LOCK,SECURITY}` OR in the forbidden FUNCTION-NAME set `{dblink,dblink_exec,dblink_connect_u,pg_read_file,pg_read_server_files,pg_ls_dir,pg_stat_activity,pg_sleep,pg_terminate_backend,pg_cancel_backend,pg_reload_conf,lo_import,lo_export}` → 400. Note: `\copy` is a psql client meta-command, not valid SQL; sqlparse will emit a parse error naturally (it is NOT listed as a keyword denylist entry — post-critic M3 ops cleanup).
6. **Wrap, not detect-and-append (post-critic C2 decision)**: sanitized SQL is ALWAYS wrapped: `wrapped = f"SELECT * FROM ({sanitized}) _limited LIMIT 1000"`. This removes the need to walk tokens and distinguish outer-LIMIT from subquery-LIMIT (which sqlparse cannot do reliably via `flatten()`). If the user's SQL contains a top-level integer-literal LIMIT > 1000 (detected by walking the first statement's last token group — NOT flatten), reject 400. Same outcome for `FOR UPDATE` / `FOR SHARE` — these are rejected pre-wrap since `aikm_viewer` is RO.
7. Optional `notice` string: if wrap applied, return `notice:"LIMIT 1000 server-wrap applied"`.

### Why both sqlparse AND the role

`sqlparse` can in theory be bypassed by a crafted unicode or dialect-specific input (there are known historical edge cases). We therefore do not rely on it alone — the `aikm_viewer` PG role (Layer 5) cannot execute a write regardless of what string the SQL editor is tricked into passing. Defense in depth.

### New dep

Add `sqlparse>=0.4.4` to `backend/requirements.txt`. No change to frontend deps.

### Rationale for C-2 inclusion

User explicitly requested during the 2026-04-20 clarification pass that v1 ship with the SQL editor — not deferred. The original P9 plan had deferred it to "014-pg-viewer-sql-editor" for scope control; that backlog is now retired and folded into this feature.

---

## Open Research Items (track but not blockers)

- **OR-1**: If/when C-2 green-lights a SQL editor, benchmark `pg_catalog.pg_stat_statements` for a "recent slow queries" panel.
- **OR-2**: Decide whether `aikm_viewer` should also be barred from `pg_catalog` (probably no — it's read-only by design and we use it for schema introspection).
- **OR-3** (post-critic): partition `pg_viewer_audit_log` by month when row count > 1M; add pg_cron extension or external cron for retention purge.
- **OR-4** (post-critic): evaluate whether `redact_sql_for_audit` regex patterns need to be dynamic (loaded from a config table) so ops can add new secret shapes without a deploy. Default v1: static regex in `backend/app/services/pg_viewer/pii_redactor.py`.
