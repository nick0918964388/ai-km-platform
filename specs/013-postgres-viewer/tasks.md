---
description: "Task list for PostgreSQL Online Viewer (013-postgres-viewer)"
---

# Tasks: PostgreSQL Online Viewer (admin-only, read-only)

**Input**: Design documents in `/specs/013-postgres-viewer/`
**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/pg-viewer-api.yaml

**Gate**: Clarifications RESOLVED 2026-04-20. SQL editor (US5) now in v1 scope — see T-016, T-022, T-036, T-037.

## Format

Each task uses **P9 six-element format**:
- **目標 (Goal)**
- **範圍 (Scope — exact paths)**
- **輸入 (Input — upstream dependencies)**
- **輸出 (Output — deliverables)**
- **驗收標準 (Acceptance)**
- **邊界 (Boundaries — must NOT touch)**

`[P]` = can run in parallel with other `[P]` tasks in same phase.

---

## Phase 1: Setup & Migration (Sequential core, then parallel)

### T-001 — Branch + spec review kickoff
- **目標**: Confirm branch `013-postgres-viewer` is ready and specs reviewed by critic.
- **範圍**: none (meta-task).
- **輸入**: specs/013-postgres-viewer/*
- **輸出**: critic report on specs (no code).
- **驗收**: critic report surfaced; HIGH findings patched in spec before proceeding.
- **邊界**: No code changes.
- **Dispatch to**: `critic` (spec review).

### T-002 [P] — Env & config wiring
- **目標**: Introduce feature-flag and viewer-DB env vars.
- **範圍**: `backend/app/config.py` (add `PG_VIEWER_ENABLED`, `PG_VIEWER_DATABASE_URL`, `PG_VIEWER_ROW_LIMIT=1000`, `PG_VIEWER_STMT_TIMEOUT_MS=10000`, `PG_VIEWER_SQL_MAX_LEN=8000`, `PG_VIEWER_AUDIT_RETENTION_DAYS=180`, `PG_VIEWER_RATE_LIMIT_SQL=30`, `PG_VIEWER_RATE_LIMIT_ROWS=60`, `PG_VIEWER_PASSWORD`); `backend/requirements.txt` (add `sqlparse>=0.4.4` AND `psycopg[binary]>=3.1` — see plan.md tech stack, post-critic C1 consistency); `docker-compose.yml` (pass env through to backend service); `.env.example` (placeholder `PG_VIEWER_PASSWORD=changeme`); frontend `.env.example` (add `NEXT_PUBLIC_PG_VIEWER_ENABLED`).
- **輸入**: data-model.md §2 and §4.
- **輸出**: env vars read by backend; `docker compose config` still valid.
- **驗收**: `docker compose config` shows backend receives new env vars; `PG_VIEWER_ENABLED` defaults true; absence of `PG_VIEWER_DATABASE_URL` is logged warning (not crash) so upgrade is safe. Settings read via `get_settings()` (cached) — changes pick up on process restart per plan.md feature-flag discipline.
- **邊界**: Do NOT change existing `DATABASE_URL`; do NOT alter `aikm` role.
- **Dispatch to**: `fullstack-engineer`.

### T-002.5 [P] — JWT_SECRET production assertion (post-critic C1 security)
- **目標**: Confirm the 012 JWT fix (auth.py refuses to start in production with default/missing JWT_SECRET) is in effect for the 013 deploy; add a pg-viewer-specific guard that also refuses to start if `PG_VIEWER_ENABLED=true` and `JWT_SECRET` matches the insecure default literal.
- **範圍**: `backend/app/services/pg_viewer/__init__.py` — on import, if `settings.PG_VIEWER_ENABLED` and `JWT_SECRET == "aikm-secret-key-change-in-production"`, raise `RuntimeError`.
- **輸入**: Reference existing fix in `backend/app/auth.py:19-39` (on branch `012-maximo-query-tools` awaiting merge). Spec FR-003.
- **輸出**: startup check; unit test that simulates the bad-secret case.
- **驗收**: `PG_VIEWER_ENABLED=true` + default secret → backend fails to start with clear error message; clean secret → starts fine. Separately: `SELECT count(*) FROM users WHERE account_level IS NULL` returns 0 (documented pre-flight in T-040 checklist).
- **邊界**: Do NOT change `backend/app/auth.py` — rely on the 012 fix.
- **Dispatch to**: `fullstack-engineer`.

### T-003 — Migration for role + audit table (SPLIT into 2 files, post-critic C1/C2 ops)
- **目標**: Author TWO idempotent SQL migrations: 001 (role + grants + users_public view + extension-denylist, runs as `postgres` superuser) and 002 (audit table partitioned + append-only grants, **also runs as `postgres` superuser** — post-critic C1/C2 fix 2026-04-20: 002 transfers ownership to `aikm_audit_purger` and issues REVOKE/GRANT on tables that aikm does not own and cannot manage).
- **範圍**: two new files:
  - `backend/scripts/pg_viewer_migrate_001_role_and_grants.sql` (per data-model.md §4a)
  - `backend/scripts/pg_viewer_migrate_002_audit_table.sql`      (per data-model.md §4b)
- **輸入**: data-model.md §1 §2 §3 §4.
- **輸出**: two migration SQL files + pre-flight doc in quickstart.md §2.
- **驗收**:
  - 001 applied TWICE in a row on a fresh 16-alpine Postgres (**as `postgres`**) → no errors; `users_public` view exists; `aikm_viewer` has SELECT on `users_public` but NOT on `users`; `REVOKE EXECUTE ON ALL FUNCTIONS` takes effect; dangerous-extension DO-block raises if `dblink` etc. are installed.
  - 002 applied TWICE in a row (**as `postgres`** — changed from `aikm` per critic C1/C2 2026-04-20) → no errors; `pg_viewer_audit_log` exists as PARTITIONED table with 2 month partitions, owned by `aikm_audit_purger`; `aikm` has INSERT+SELECT but NOT UPDATE/DELETE/TRUNCATE on `pg_viewer_audit_log`; `aikm_viewer` has NO SELECT on `pg_viewer_audit_log`; `ensure_next_audit_partition()` is `SECURITY DEFINER` owned by `postgres`.
  - Verification queries at end of each file print expected t/f vector; 002 also runs a `DO $verify$` block that RAISEs EXCEPTION on any invariant violation (CI gates on psql exit code, not output parsing — critic L5).
  - Privilege pre-flight (`rolsuper` for postgres, `max_connections >= 200`) documented in quickstart.
- **邊界**: Do NOT touch existing `query_audit_log`, `permission_groups`, `users` (beyond the view), `maximo_*` tables.
- **Dispatch to**: `db-expert` (author) → `critic` (review).

---

## Phase 2: Backend Foundation (Blocking)

### T-010 — Viewer engine + session dep (post-critic C3/H2 ops)
- **目標**: Lazy singleton `asyncpg/sqlalchemy` engine bound to `PG_VIEWER_DATABASE_URL` with `pool_size=3, max_overflow=7, pool_pre_ping=True, pool_recycle=1800, connect_args={"command_timeout": 10}`; `get_viewer_db()` dependency that always runs inside `engine.begin()` (never `engine.connect()`; never AUTOCOMMIT).
- **範圍**: new `backend/app/services/pg_viewer/__init__.py`, `backend/app/services/pg_viewer/engine.py`.
- **輸入**: T-002 env vars; plan.md §"Data Flow"; research.md D-2/D-4.
- **輸出**: importable `from app.services.pg_viewer.engine import get_viewer_db`.
- **驗收**:
  - Integration test: `SELECT 1` via `get_viewer_db` succeeds.
  - Integration test: `CREATE TABLE foo()` via that session raises PG permission error (proves L5 role is RO).
  - Integration test (three-layer timeout): `SELECT pg_sleep(30)` returns cancelled in ≤ 11s wall-clock (role-level + SET LOCAL + command_timeout). Elevated from T-041 (post-critic C3 ops).
  - Integration test: `SELECT * FROM users` raises permission denied (role has NO SELECT on users — L5 option-b).
  - Integration test: `SELECT * FROM users_public` succeeds.
- **邊界**: Must NOT reuse the main `get_db` engine; pool cap = 10 connections (3 + 7 overflow).
- **Dispatch to**: `fullstack-engineer`.

### T-011 — Introspection service (blocking for T-012; see M-3 consistency)
- **目標**: `list_tables()`, `get_schema(table)`, `resolve_identifier(table, column)` with 5-min LRU cache. Returns composite-PK column list (ordered). Surfaces `grant_missing: true` when information_schema lists a table that `aikm_viewer` lacks SELECT on (post-critic C2 ops).
- **範圍**: new `backend/app/services/pg_viewer/introspect.py`.
- **輸入**: T-010 (viewer engine), contracts `TableSummary` / `TableSchema`.
- **輸出**: typed service functions returning Pydantic models. `get_schema` returns ordered `primary_key: list[str]` (composite PK safe).
- **驗收**: Unit test against a seeded dev DB returns `users_public`, `maximo_*` etc. (NOT `users`, `sessions`, `api_keys` — L5 REVOKE); `resolve_identifier("users_public", "bogus")` raises ValueError → 400 at router layer; `list_tables` returns `grant_missing=true` for any table with a missing SELECT grant; composite-PK tables (e.g. `user_permissions`) return `primary_key=["user_id","section"]` in order — T-012 uses this for default `ORDER BY pk1 DESC, pk2 DESC`.
- **邊界**: Do NOT execute any data SELECT here (only `information_schema` / `pg_catalog`). Drop `[P]` — T-012 depends on `resolve_identifier`.
- **Dispatch to**: `fullstack-engineer`.

### T-012 — Query builder (depends on T-011)
- **目標**: Given validated (table, columns, filters, order_by, order_dir, limit, offset), build a safe rendered-string SELECT suitable for asyncpg. Identifier rendering goes through `psycopg.sql.Identifier(name).as_string(conn)`; values are bound as asyncpg positional `$1, $2, …`. **psycopg.sql.Composed objects MUST NEVER be passed to asyncpg** (post-critic C1 consistency).
- **範圍**: new `backend/app/services/pg_viewer/query_builder.py`.
- **輸入**: T-011 introspect results (composite PK, `resolve_identifier`); operator whitelist from spec FR-030; research.md D-3 bridge rule.
- **輸出**: `(sql_str, params_list)` tuple; plus `build_count_sql` if needed.
- **驗收**: Unit tests for: equality filter, IN, IS NULL, LIKE with wildcard flag, rejection of unknown operator, rejection of non-existent column, rejection of `limit > PG_VIEWER_ROW_LIMIT` (HTTP 400 `row limit exceeded`), composite-PK default ORDER BY covers all PK columns, identifier rendering is via psycopg `as_string(conn)` (not f-string). Unit test: attempting to pass a Composed to an asyncpg `.execute()` raises (guardrail).
- **邊界**: Must NOT accept raw SQL strings; must NOT inject values via % formatting; never touches network; NO Composed to asyncpg.
- **Dispatch to**: `fullstack-engineer`.

### T-013 [P] — Redaction module (secondary defense; L5 is primary)
- **目標**: Apply `HIDDEN_COLUMNS` and `REDACTED_BY_ROW_RULE` to result rows as a SECONDARY defense. Primary defense is L5 role-level REVOKE on `users`/`sessions`/`api_keys` + `users_public` view (post-critic C3 security).
- **範圍**: new `backend/app/services/pg_viewer/redaction.py`.
- **輸入**: data-model.md §3.
- **輸出**: `apply_redaction(rows, table) -> (rows, columns_meta)` returning sanitized rows + flagged columns.
- **驗收**:
  - Unit test — rows from `users_public` never contain `password_hash` key (never projected); `system_settings` row with key=`openai_api_key` has `value='***'`; other rows untouched.
  - Concretization: on first import, run a schema scan as `aikm_viewer` and assert every column matching `/password|secret|token|api_key|credential|private_key|passphrase/i` is in `HIDDEN_COLUMNS` or `REDACTED_BY_ROW_RULE` — fail import (and CI test) otherwise (post-critic L-5 consistency, wires discovery test into CI — addresses "Out-of-scope observations" note).
- **邊界**: Must run server-side before JSON; must NOT mutate input list in place.
- **Dispatch to**: `fullstack-engineer`.

### T-014 [P] — Audit writer (independent tx + bind-params + PII redaction)
- **目標**: Insert `pg_viewer_audit_log` rows using the **main** `aikm` session in an **independent transaction** so audit is committed even if the outer request-handler tx rolls back (post-critic H7 consistency). INSERTs use SQLAlchemy `insert()` / bind-params only — string concatenation of `raw_sql` into INSERT SQL is forbidden (post-critic C2 security). `raw_sql` and `error_message` go through `redact_sql_for_audit()` BEFORE insert (post-critic C4 consistency).
- **範圍**: new `backend/app/services/pg_viewer/audit.py`.
- **輸入**: T-003 table schema; T-XXX-PII `redact_sql_for_audit`; `fastapi.Request` for IP/UA.
- **輸出**: `write_audit(db, user, action, table, filters, order_by, order_dir, limit, offset, row_count, execution_ms, status, error_message, ip, ua, raw_sql=None)` — opens a new session/connection, inserts, commits, closes; logs any error without blocking the outer request.
- **驗收**:
  - Unit test — inserts row with expected fields, commits in its own tx (verify by forcing the outer handler to raise after `write_audit` returns — row must persist).
  - Unit test — INSERT SQL is built via `sqlalchemy.insert()` (or `text()` + bind-params); never via f-string.
  - Unit test — passing `raw_sql="SELECT '; DROP TABLE users; --"` leaves the users table intact (parameterization proof).
  - Unit test — `redact_sql_for_audit("SELECT 'ghp_ABC...' ")` → stored `raw_sql` contains `[REDACTED_GHP]`.
  - Unit test — audit failure triggers `logger.error(sanitized_message)` where sanitized excludes role name / connection string.
  - Unit test — `UPDATE pg_viewer_audit_log SET status='ok'` via aikm session fails with permission denied (append-only grant proof).
  - `X-Forwarded-For` accepted ONLY from trusted proxy IP allowlist (frontend container IP); otherwise use `request.client.host` (post-critic M1 security).
- **邊界**: Must NOT run inside the viewer session (viewer can't INSERT); must NOT skip audit on `status='forbidden'` / `rate_limited` (post-critic N4 security).
- **Dispatch to**: `fullstack-engineer` → `critic` (security-sensitive).

### T-014.5 [P] — PII redactor + PG error sanitizer utility (post-critic C4/H3)
- **目標**: Implement `backend/app/services/pg_viewer/pii_redactor.py` with two pure functions: `redact_sql_for_audit(sql: str) -> str` (regex-based scrubber for bearer tokens, `ghp_*`, `sk-*`, 20+ hex strings, literals adjacent to sensitive-column refs) and `sanitize_pg_error(exc: Exception) -> str` (whitelist-safe error shapes; strip role name / DSN / file path / DETAIL/HINT). Maps SQLSTATE → (HTTP status, safe message).
- **範圍**: new `backend/app/services/pg_viewer/pii_redactor.py`; unit tests `backend/tests/pg_viewer/test_pii_redactor.py`.
- **輸入**: FR-017a, FR-064, data-model.md §3 (regex patterns).
- **輸出**: two pure functions + SQLSTATE→HTTP map.
- **驗收**:
  - `redact_sql_for_audit("SELECT 'ghp_ABCDEFGHIJKLMNOPQRSTUV' AS tok")` → `"SELECT '[REDACTED_GHP]' AS tok"`.
  - `redact_sql_for_audit("SELECT * WHERE Authorization = 'Bearer abc123.def'")` → Bearer redacted.
  - `redact_sql_for_audit("SELECT password_hash = 'bcrypt$2b$12$...' FROM x")` → literal redacted.
  - Output truncated to 8000 chars AFTER redaction.
  - `sanitize_pg_error(QueryCanceledError(...))` → (408, "query timed out after 10 seconds").
  - `sanitize_pg_error(UndefinedTable("relation \"x\" does not exist"))` → (422, `column/relation does not exist`).
  - `sanitize_pg_error(InsufficientPrivilege("permission denied for table users to role aikm_viewer"))` → (403, "grant missing: contact operator") — role name STRIPPED.
  - No role name, no connection string, no file path, no DETAIL/HINT ever appears in output (assert via regex).
- **邊界**: Pure functions; no DB/network.
- **Dispatch to**: `fullstack-engineer` → `critic` (security).

### T-014.6 [P] — Rate limiter (post-critic H2 security + R2 Redis-down fail-closed)
- **目標**: Implement Redis token-bucket rate limit for `/sql` (30/min/user) and `/rows` + `/export.csv` (60/min/user). Emits HTTP 429 + audit row `status='rate_limited'`. If Redis is unreachable, **fail closed** → HTTP 503 `Retry-After: 30` + audit `status='error'` (R2 decision 2026-04-20, see plan.md §6).
- **範圍**: new `backend/app/services/pg_viewer/rate_limiter.py`; reuse existing `backend/app/services/cache.py` Redis client.
- **輸入**: FR-063, env `PG_VIEWER_RATE_LIMIT_SQL`, `PG_VIEWER_RATE_LIMIT_ROWS`.
- **輸出**: FastAPI dep `require_rate_budget(bucket_name, limit_per_min)`.
- **驗收**:
  - Unit test: 30 POSTs in 60s → 30 × 200, 31st → 429; after 60s window → allowed again.
  - Integration test: 429 response includes `Retry-After` header.
  - Integration test (R2 Redis-down): kill Redis mid-request → dep raises → response is HTTP 503 with `Retry-After: 30`, body `{"detail":"rate limiter backend unavailable"}`; audit row `status='error'` recorded; NOT HTTP 200 (fail-closed proof).
  - Prometheus counter `pg_viewer_rate_limiter_redis_down_total` increments on each Redis failure.
- **邊界**: Must use existing Redis client; must NOT add a new cache backend; MUST NOT fall back to "no limit" on Redis failure (fail-open is forbidden per plan.md §6).
- **Dispatch to**: `fullstack-engineer`.

### T-015 — CSV exporter (post-critic H1 security + M5 consistency)
- **目標**: StreamingResponse CSV with proper escaping; obeys row limit; **per-cell truncation** on export path (text > 1000 chars clipped; bytea base64+clipped at 200 chars); total payload ≤ 10 MB.
- **範圍**: new `backend/app/services/pg_viewer/exporter.py`.
- **輸入**: T-012 query builder, T-013 redaction.
- **輸出**: `async def export_csv(...) -> StreamingResponse`.
- **驗收**:
  - Integration test — 50-row export produces valid CSV (parseable by Python `csv` with no surprise rows).
  - 1,500-row source → only 1,000 rows emitted; response headers include `X-Truncated: true` and `X-Row-Count: 1000`; CSV body contains NO fake `-- truncated at row-limit` comment row (post-critic M5 consistency).
  - Sensitive cols absent/masked; `bytea` columns base64-encoded THEN clipped to 200 chars; text columns clipped to 1000 chars on export.
  - Total payload size ≤ 10 MB regardless of input (assert via test with 1000 × 500-col × 200KB-cell).
  - Content-Disposition filename uses whitelisted table name + timestamp; defensive quoting applied (post-critic N7 security).
  - Streaming: memory usage during a 1000-row export stays < 50 MB RSS (benchmarked).
- **邊界**: Must NOT buffer entire CSV in memory; must NOT add BOM.
- **Dispatch to**: `fullstack-engineer`.

### T-016 [P] — SQL validator (Layer-9 static analysis) — post-critic C2/H3/H6
- **目標**: Implement `validate_select_sql(raw: str) -> WrappedSql` that rejects every non-SELECT input pre-DB and returns a **wrapped** SQL: `SELECT * FROM ({sanitized}) _limited LIMIT 1000` (post-critic 2026-04-20 decision: **wrap, not detect-and-append**). User-supplied outer `LIMIT > 1000` → reject 400 (post-critic 2026-04-20 decision: **reject, not clamp**).
- **範圍**: new `backend/app/services/pg_viewer/sql_validator.py`; unit tests `backend/tests/pg_viewer/test_sql_validator.py`.
- **輸入**: research.md "SQL Static Analysis Library" section (updated); spec FR-014.
- **輸出**:
  - Public API: `validate_select_sql(raw: str, *, max_len: int = 8000) -> WrappedSql` where `WrappedSql = namedtuple("WrappedSql", "wrapped_sql, original_sql, wrap_applied")`.
  - Raises typed exceptions: `EmptyInputError`, `TooLongError`, `MultiStatementError`, `NotSelectError`, `ForbiddenKeywordError(keyword)`, `ForbiddenFunctionError(name)`, `LimitExceededError`, `ParseError(msg)`.
  - Forbidden KEYWORD set (case-insensitive token match): `{INSERT, UPDATE, DELETE, DROP, TRUNCATE, GRANT, REVOKE, CREATE, ALTER, COPY, CALL, VACUUM, ANALYZE, REINDEX, CLUSTER, COMMENT, LOCK, SECURITY}`. Note: `\copy` removed from keyword list (it's a psql meta-command — will fail parse anyway, post-critic M3 ops).
  - Forbidden FUNCTION-NAME set (case-insensitive identifier token match): `{dblink, dblink_exec, dblink_connect_u, pg_read_file, pg_read_server_files, pg_ls_dir, pg_stat_activity, pg_sleep, pg_terminate_backend, pg_cancel_backend, pg_reload_conf, lo_import, lo_export}`.
  - Normalize: strip BOM + NFC-normalize unicode + `.strip()` + tolerate one trailing `;`.
- **驗收**: unit tests (all must pass):
  - **Positive**: `SELECT 1`, `select * from users_public limit 5`, `WITH cte AS (SELECT 1) SELECT * FROM cte`, `SELECT 1;` (trailing `;` tolerated) → all return `wrap_applied=true`, `wrapped_sql = "SELECT * FROM (<sanitized>) _limited LIMIT 1000"`.
  - **Multi-statement**: `SELECT 1; SELECT 2`, `SELECT 1; DROP TABLE users`, `SELECT 1; /*x*/;` → all reject `MultiStatementError`.
  - **Keyword denylist**: `DROP TABLE users`, `INSERT INTO ...`, `UPDATE users SET ...`, `DELETE FROM ...`, `TRUNCATE users`, `GRANT ALL`, `COPY users FROM ...`, `CREATE TABLE ...`, `ALTER TABLE ...`, `VACUUM`, `CALL proc()`, `SECURITY LABEL ...` → all reject.
  - **CTE-headed write**: `WITH foo AS (DELETE FROM users RETURNING *) SELECT * FROM foo` → reject `ForbiddenKeywordError('DELETE')`.
  - **Comment tricks**: `/* hidden */ DROP TABLE users`, `-- DROP\nSELECT 1`, `/* /* */ DROP */ SELECT 1` (nested), `/*! DROP */ SELECT 1` (MySQL hint comment — test sqlparse behavior) → all reject.
  - **Case-insensitive**: `DrOp tAbLe users` → reject.
  - **UNION + password column**: `SELECT id FROM users_public UNION SELECT password_hash FROM users` → reject at 422 layer (users has no SELECT grant for aikm_viewer — L5); validator itself does NOT require column-provenance analysis because L5 blocks this path. Assert fail at DB role level (test against real DB in T-041).
  - **DoS functions**: `SELECT pg_sleep(30)`, `SELECT pg_terminate_backend(1)`, `SELECT dblink_exec(…)`, `SELECT lo_import('/etc/passwd')`, `SELECT pg_read_file('/etc/passwd')`, `SELECT pg_ls_dir('.')`, `SELECT pg_stat_activity` → all reject `ForbiddenFunctionError`.
  - **COPY TO PROGRAM**: `COPY (SELECT 1) TO PROGRAM 'nc …'` → reject (COPY in keyword list).
  - **Quoted-string value NOT flagged**: `SELECT 'DROP TABLE users' AS x` → ACCEPT (literal string, not keyword token). Documented test.
  - **`\copy` meta-command**: `\copy (SELECT 1) TO '/tmp/x'` → reject as `ParseError` (not valid SQL). No longer in keyword denylist (post-critic M3 ops).
  - **Empty / whitespace / oversize**: reject `''`, `'   '`, `'a'*9000` → respective typed errors.
  - **BOM + NFC**: `'\ufeffSELECT 1'` → BOM stripped, accepted; unicode lookalike "SELECT" using Cyrillic Ѕ → sqlparse treats as identifier → first-token check fails → reject.
  - **LIMIT logic**:
    - `SELECT * FROM t LIMIT 50` → wrap applied, wrapped_sql = `SELECT * FROM (SELECT * FROM t LIMIT 50) _limited LIMIT 1000`; `wrap_applied=true`.
    - `SELECT * FROM t LIMIT 5000` → reject `LimitExceededError` (post-critic H5 decision: reject not clamp).
    - `SELECT * FROM t` → wrap applied.
    - `SELECT * FROM (SELECT * FROM t LIMIT 5) s` → ACCEPT (subquery LIMIT, not top-level); wrap applied.
    - `SELECT * FROM t LIMIT 10 OFFSET 20` → ACCEPT, wrap applied.
- **邊界**: MUST NOT open any DB connection. MUST NOT call any network. Pure function.
- **Dispatch to**: `fullstack-engineer` → `critic` (security-sensitive).

---

## Phase 3: Router (Sequential — depends on Phase 2)

### T-020 — FastAPI router wiring (post-critic C3 ops + multiple)
- **目標**: Implement all endpoints per `contracts/pg-viewer-api.yaml`, with `require_admin_strict` (re-reads `account_level` from DB per request — post-critic C1 security), rate-limit deps on `/sql` and `/rows`, sanitized error responses, feature flag via `get_settings()` (not import-time — post-critic M6 security).
- **範圍**: new `backend/app/routers/pg_viewer.py`; register in `backend/app/main.py`; add `require_admin_strict` helper if missing (reuses 012 fix pattern).
- **輸入**: T-010…T-016, T-014.5 (sanitizer), T-014.6 (rate limiter); contract yaml.
- **輸出**: 6 endpoints (list / schema / rows / export / audit / **sql**) + `GET /audit` wired to the Pydantic `AuditEntry` model.
- **驗收**:
  - All 6 endpoints gated by `require_admin_strict` (DB re-fetch).
  - Feature-flag `PG_VIEWER_ENABLED=false` → 404 on every endpoint (including `POST /sql`). Flag read via `get_settings()` on every request (not import-time).
  - Each successful call produces one audit row (browse paths populate `query_type ∈ {table_browse, schema}`, SQL editor populates `query_type='sql_editor'` + redacted `raw_sql`). FORBIDDEN / ERROR / TIMEOUT / RATE_LIMITED paths also audited.
  - Three-layer statement_timeout enforced; integration test asserts `SELECT pg_sleep(30)` → 408 in ≤ 11s.
  - Rate limit: 31st POST /sql in 60s → 429 with `Retry-After`; audit `status='rate_limited'`.
  - Error mapping: SQLSTATE 57014 → 408, 42P01/42703 → 422, 42501 → 403 "grant missing", others → 500 via `sanitize_pg_error` generic path (post-critic M4 ops + H3 security). Integration test asserts role name / DSN / file path / DETAIL / HINT never appear in any error body.
  - `GET /audit` returns paginated Pydantic `AuditEntry` list matching contract exactly (post-critic H-1 consistency — was previously missing).
  - Response shapes validated via `openapi-spec-validator` OR `schemathesis` fuzz.
  - Browse endpoint catches 42501 → returns HTTP 200 with `grant_missing=true` on the affected table summary (surfaces drift instead of raw 42501, post-critic C2 ops).
- **邊界**: Do NOT change any other router; do NOT alter `app/auth.py` beyond adding `require_admin_strict` if needed (prefer reusing post-012 fix).
- **Dispatch to**: `fullstack-engineer` → `critic`.

### T-022 — SQL editor endpoint wiring (depends on T-016 + T-020)
- **目標**: Wire `POST /api/pg-viewer/sql` through rate_limit → validator → executor → audit. Executor runs the WRAPPED SQL (validator output) via viewer engine inside `engine.begin()` with `SET LOCAL statement_timeout`; applies redaction post-fetch; sanitizes any PG error via `sanitize_pg_error`.
- **範圍**: `backend/app/routers/pg_viewer.py` (add `sql_endpoint`); new `backend/app/services/pg_viewer/sql_executor.py`.
- **輸入**: T-013 redaction, T-014.5 sanitizer, T-014.6 rate limiter, T-016 validator, T-020 router scaffold, contract `POST /pg-viewer/sql` + `SqlResult` schema.
- **輸出**: endpoint responds per contract; `raw_sql` is redacted THEN truncated to `PG_VIEWER_SQL_MAX_LEN` before audit INSERT (independent tx).
- **驗收**:
  - Positive: `{"sql":"SELECT 1"}` → `{columns:[{name:'?column?',data_type:'integer'}], rows:[{'?column?':1}], row_count:1, elapsed_ms:<n>, truncated:true, notice:"LIMIT 1000 server-wrap applied"}` (wrap always applied per FR-014.6).
  - Positive: `SELECT status, COUNT(*) c FROM maximo_mxwo GROUP BY status` → returns grouped rows.
  - Positive auto-LIMIT: `SELECT * FROM maximo_mxwo` → `truncated:true`, `row_count:1000`, `notice:"LIMIT 1000 server-wrap applied"`.
  - Negative: `DROP TABLE users` → 400 `{detail:"forbidden keyword: DROP"}`, audit `status='forbidden', query_type='sql_editor'`, raw_sql stored (redacted).
  - Negative: multi-statement → 400.
  - Negative: LIMIT > 1000 → 400 `row limit exceeded (server-side cap 1000)` (post-critic H5 reject-not-clamp decision).
  - Negative: `SELECT pg_sleep(30)` → 408 (three-layer timeout), audit `status='timeout'`; integration test asserts wall-clock ≤ 11s.
  - Negative: unknown table → 422 with sanitized message (role name stripped); audit `status='error'`.
  - Negative: `SELECT * FROM users` → 42501 from DB → 403 "grant missing" (L5 primary defense blocks; post-critic C3 security).
  - Negative: non-admin → 403.
  - Negative: feature flag off → 404.
  - Negative: 31st request in 60s → 429 + `Retry-After`; audit `status='rate_limited'`.
  - Redaction path: `SELECT * FROM users_public LIMIT 1` → returns safe columns only; no `password_hash` in projection because table is not granted.
  - PII scrub: `POST /sql` with `SELECT 'ghp_ABCDEFGHIJKLMNOPQRSTUV' AS tok` → audit row `raw_sql` contains `[REDACTED_GHP]`, never the real token.
- **邊界**: Do NOT expose raw Postgres error text (sanitize: strip DETAIL:, HINT:, connection info, role name, file paths). Run executor inside `engine.begin()` (never `engine.connect()`).
- **Dispatch to**: `fullstack-engineer` → `critic` (security).

### T-021 — Circuit-breaker integration
- **目標**: Register `pg_viewer` circuit; open on 5 failures in 60s; half-open at 30s.
- **範圍**: edit `backend/app/services/circuit_breaker.py` to add breaker key; edit `backend/app/routers/pg_viewer.py` to wrap DB calls.
- **輸入**: existing `circuit_breaker.py` pattern.
- **輸出**: breaker visible in `/health/circuits`.
- **驗收**: Forcing 5 consecutive DB errors (e.g. bad DB URL) opens breaker; endpoints return 503; half-open after 30s succeeds once DB restored.
- **邊界**: Do NOT modify other circuits.
- **Dispatch to**: `fullstack-engineer`.

---

## Phase 4: Frontend (Parallel-safe within itself)

### T-030 [P] — API client + Pydantic / TS type parity (post-critic H2 consistency)
- **目標**: Type-safe client functions for all endpoints. TS types in `frontend/src/types/pgViewer.ts` MUST match the backend Pydantic models 1:1 (backend Pydantic defined in T-020's new `backend/app/schemas/pg_viewer.py` — see §T-020 scope addition below).
- **範圍**: new `frontend/src/services/pgViewerService.ts`, `frontend/src/types/pgViewer.ts`; ALSO new `backend/app/schemas/pg_viewer.py` containing Pydantic models for every OpenAPI component schema (`TableSummary`, `TableSchema`, `Column`, `Index`, `ForeignKey`, `RowPage`, `SqlResult`, `AuditEntry`, `Error`).
- **輸入**: `contracts/pg-viewer-api.yaml`.
- **輸出**: `listTables()`, `getTableSchema(name)`, `getTableRows({table, limit, offset, order_by, order_dir, filters})`, `exportCsvUrl(...)`, `runSql(sql)`, `getAudit(...)`. Also Pydantic module with 9 models.
- **驗收**:
  - TS strict, no `any`; 401/403 handled by redirect to login via existing interceptor pattern.
  - 429 → show toast "rate limit: wait 60s" and disable Run button for the `Retry-After` duration.
  - Pydantic schema parity test: a Python script diffs each Pydantic model against the OpenAPI yaml schema; failing keys / types / required flags cause CI fail.
- **邊界**: Do NOT introduce new npm deps.
- **Dispatch to**: `fullstack-engineer`.

### T-031 [P] — Page shell + routing + CSP + SSR feature-flag (post-critic H4 security + M5 ops + R2 M2 CSP hardening)
- **目標**: Admin-only page at `/admin/pg-viewer` with layout (left table-list, right detail) + **full nonce-based CSP** (per plan.md §5a) + SSR disabled-banner when feature is off. Weak CSP previously flagged as theatrical by R2 critic; this task enforces the authoritative directive set.
- **範圍**: new `frontend/src/app/(main)/admin/pg-viewer/page.tsx` + `layout.tsx` if needed; new or extended `frontend/src/middleware.ts` to (a) generate per-request nonce via `crypto.randomBytes(16).toString('base64')` and (b) emit the CSP header on `/admin/pg-viewer/:path*`.
- **輸入**: existing `/admin` layout pattern; env `NEXT_PUBLIC_PG_VIEWER_ENABLED`; plan.md §5a directive set (verbatim).
- **輸出**: page renders, gated by existing admin-route guard, shows "Loading…" state; middleware emits CSP.
- **驗收**:
  - Non-admin user visiting URL is redirected / shown 403 view consistent with other `/admin/*` pages.
  - If `NEXT_PUBLIC_PG_VIEWER_ENABLED=false` OR API `/tables` returns 404, page SSR-renders a clean "Feature temporarily disabled" banner (not an error splash).
  - **CSP header MUST match plan.md §5a verbatim** (modulo the per-request nonce substitution). Unit test: regex each directive from the spec against the rendered header; a missing directive fails the build.
  - Nonce is generated via `crypto.randomBytes(16).toString('base64')` (cryptographic); two consecutive requests have different nonces (test: fetch twice, assert distinct); `Math.random` never appears in the nonce path (grep lint).
  - Every `<Script>` and inline `<style>` tag on the page carries the `nonce` prop; Playwright asserts `document.querySelectorAll('script:not([nonce])')` is empty on `/admin/pg-viewer`.
  - `frame-ancestors 'none'` honored: curl with `-H 'sec-fetch-dest: iframe'` from a foreign origin is blocked at browser (documented + Playwright test that embedding the page in an iframe fails to render).
  - `object-src 'none'` + `base-uri 'self'` verified via the response header regex test.
  - `report-uri /api/csp-violations` present in the header; a crafted inline-script violation POSTs to that endpoint (wired in T-046).
  - Playwright screenshot matches Carbon style.
- **邊界**: Do NOT touch other `/admin` pages. Do NOT add `'unsafe-inline'` or `'unsafe-eval'` to any directive.
- **Dispatch to**: `frontend-designer` (layout) → `fullstack-engineer` (middleware + CSP wiring) → `critic` (security).

### T-032 [P] — Table list component
- **目標**: Left panel: searchable / grouped list of tables with approx row-count badge.
- **範圍**: `frontend/src/components/admin/pg-viewer/TableList.tsx` + `hooks/useTables.ts`.
- **輸入**: T-030 client.
- **輸出**: clickable list, group by name-prefix.
- **驗收**: Clicking a table sets URL query `?table=foo`; debounced search filters in <100ms; empty state handled.
- **邊界**: Keep logic in hook; component is presentational.
- **Dispatch to**: `fullstack-engineer`.

### T-033 — Data tab (table browser)
- **目標**: Right panel "Data" tab: Carbon DataTable + Pagination + FilterBar + ExportCSV.
- **範圍**: `frontend/src/components/admin/pg-viewer/DataTab.tsx`, `FilterBar.tsx`, `hooks/useTableRows.ts`.
- **輸入**: T-030, T-032.
- **輸出**: full browse UX.
- **驗收**:
  - Pagination server-driven.
  - Sort click toggles ASC/DESC on a column.
  - FilterBar supports add/remove filter with op dropdown.
  - Long strings truncated at 200 chars with "show more" modal.
  - NULL rendered italic grey.
  - ExportCSV button downloads file.
  - Playwright: browse `maximo_mxwo`, filter `status = 'APPR'`, sort by `changedate DESC`, export CSV — all visible.
- **邊界**: Do NOT implement inline editing.
- **Dispatch to**: `fullstack-engineer`.

### T-034 [P] — Schema tab
- **目標**: Right panel "Schema" tab: columns / PK / indexes / FKs.
- **範圍**: `frontend/src/components/admin/pg-viewer/SchemaTab.tsx`, `hooks/useTableSchema.ts`.
- **輸入**: T-030.
- **輸出**: schema view.
- **驗收**: Renders 50-column table without layout break; PK highlighted; FK clickable to jump to referenced table.
- **邊界**: No editing.
- **Dispatch to**: `fullstack-engineer`.

### T-035 [P] — Audit tab (optional sub-feature)
- **目標**: Small admin audit view for pg_viewer actions.
- **範圍**: `frontend/src/components/admin/pg-viewer/AuditTab.tsx` or extend existing admin audit page with a new sub-tab.
- **輸入**: T-030 getAudit.
- **輸出**: paginated audit table + filters.
- **驗收**: Admin can filter by user / table / status; failed queries visible; date column sortable.
- **邊界**: Do NOT modify existing `query_audit_log` admin views.
- **Dispatch to**: `fullstack-engineer`.

### T-036 — SQL editor page + component
- **目標**: Dedicated admin route `/admin/pg-viewer/query` with a textarea-based SQL editor, Run button, result grid, elapsed-ms badge, inline error banner, and truncation warning.
- **範圍**:
  - new `frontend/src/app/(main)/admin/pg-viewer/query/page.tsx`
  - new `frontend/src/components/admin/pg-viewer/SqlEditor.tsx`
  - new `frontend/src/components/admin/pg-viewer/hooks/useSqlQuery.ts`
  - update `frontend/src/services/pgViewerService.ts` (add `runSql(sql: string)` → POST /api/pg-viewer/sql with auth header)
  - update the pg-viewer landing page (from T-031) to show a tab link "SQL" → `/admin/pg-viewer/query`
- **輸入**: T-030 client, T-022 endpoint, contract yaml.
- **輸出**: Functional editor page.
- **驗收**:
  - Monaco NOT introduced (use plain Carbon `<TextArea>` — simpler); sqlparse-level parsing happens server-side only.
  - Ctrl/Cmd+Enter keybind runs the query (nice-to-have, not blocker).
  - Run button disabled while in-flight; shows Carbon `InlineLoading`.
  - On 400: shows error banner inline with the exact `detail` text from server (no alert dialog).
  - On 200: renders Carbon `DataTable` with columns from response.columns (respecting `redacted: true` flag with a shield icon in the header), elapsed-ms badge, row-count badge; if `truncated:true`, shows amber banner "LIMIT 1000 auto-appended — refine your query for more".
  - Non-admin user hitting the URL is redirected / shown 403 view consistent with other `/admin/*` pages.
  - On 429: banner "Rate limit: 30 SQL/min. Wait {Retry-After}s"; Run button disabled for that duration.
  - On 408 timeout: banner "Query timed out (10s). Refine your query with narrower filters."
  - Export CSV of the SQL-editor result is OUT OF SCOPE for v1 (backlog entry in project_pg_viewer_backlog.md).
- **邊界**: MUST NOT introduce `@monaco-editor/react` or any new npm dep. MUST NOT add saved-query persistence (out-of-scope per C-5). MUST NOT auto-run queries on page load.
- **Dispatch to**: `frontend-designer` (layout) → `fullstack-engineer` (wiring).

### T-037 [P] — SQL editor E2E + unit coverage
- **目標**: End-to-end Playwright test + additional backend integration test specifically for the SQL editor path.
- **範圍**:
  - new `tests/e2e/pg-viewer-sql-editor.spec.ts` (Playwright)
  - new `backend/tests/pg_viewer/test_sql_endpoint.py` (FastAPI TestClient)
- **輸入**: T-022, T-036.
- **輸出**:
  - Playwright: admin logs in → `/admin/pg-viewer/query` → pastes `SELECT 1` → sees result; pastes `DROP TABLE users` → sees inline error banner; pastes `SELECT 1; SELECT 2` → sees multi-statement error.
  - Backend integration: same matrix as T-022 acceptance, plus bypass attempts (comment-hidden keywords, unicode escape, CTE-headed DELETE) — all rejected.
- **驗收**: All tests green in CI on 192.168.1.11 self-hosted runner.
- **邊界**: PoC-style attacks beyond this list belong to T-041 (vuln-verifier).
- **Dispatch to**: `fullstack-engineer`.

---

## Phase 5: Review, PoC, Deploy (Sequential)

### T-040 — Security code review
- **目標**: Find any SQL-injection, auth-bypass, or info-disclosure bugs before deploy.
- **範圍**: all files under `backend/app/services/pg_viewer/`, `backend/app/routers/pg_viewer.py`, `frontend/src/**/pg-viewer/**`, migration SQL.
- **輸入**: diff of branch.
- **輸出**: critic report with HIGH/MEDIUM/LOW findings.
- **驗收**: No HIGH/CRITICAL open.
- **邊界**: Review scope limited to feature diff.
- **Dispatch to**: `critic`.

### T-041 — PoC-driven vulnerability verification
- **目標**: Actually attempt attacks; produce red/green outcome.
- **範圍**: scripts under `backend/tests/pg_viewer/poc_*.py` (throwaway ok).
- **輸入**: T-040 findings.
- **輸出**: test suite attempting:
  1. `DROP TABLE users` via any endpoint or crafted filter → expect 400/403, audit=`error|forbidden`.
  2. `UPDATE users SET role='admin'` via filter injection → expect bind-param, 0 rows, no side effect.
  3. Non-admin token → 403 on all endpoints including `POST /sql`.
  4. Table not in whitelist → 404.
  5. Column not in schema as `order_by` → 400.
  6. `limit=100000` → clamped to 1000, audit shows 1000.
  7. Query that times out (`POST /sql` with `SELECT pg_sleep(30)`) → 408, audit=`timeout`.
  8. Confirm `has_table_privilege('aikm_viewer',…,'INSERT')` = false post-deploy.
  9. `POST /sql` with `DROP TABLE users` → 400, audit=`forbidden`, raw_sql stored.
  10. `POST /sql` with `SELECT 1; DROP TABLE users` → 400 multi-statement.
  11. `POST /sql` with `WITH t AS (DELETE FROM users RETURNING *) SELECT * FROM t` → 400 forbidden keyword (DELETE).
  12. `POST /sql` with comment-hidden DDL (`/* SELECT */ DROP TABLE users` variants) → 400.
  13. `POST /sql` with unicode whitespace + DROP → 400.
  14. `POST /sql` with `SELECT * FROM maximo_mxwo` (no LIMIT) → `truncated: true`, `row_count: 1000`.
  15. Attempt `psql -U aikm_viewer -c "INSERT ..."` directly against DB → permission denied (proves L5 role-level defense).
  16. `SELECT * FROM users` as aikm_viewer → permission denied (L5 option-b view approach — post-critic C3 security).
  17. `SELECT id FROM users_public UNION SELECT password_hash FROM users` → 403/42501 (users not granted; proves the UNION-alias exfil vector is closed at L5 — post-critic H6 security).
  18. `SELECT pg_read_file('/etc/passwd')` → validator rejects `forbidden function: pg_read_file`.
  19. `SELECT dblink_exec('host=... dbname=... user=postgres', 'DROP TABLE users')` → migration either blocked `dblink` extension OR validator rejects; both paths covered.
  20. SECURITY DEFINER function check: enumerate `pg_proc` for `prosecdef=true`; confirm `aikm_viewer` has no EXECUTE on any of them (post-critic C3 security).
  21. `SELECT count(*) FROM users WHERE account_level IS NULL` → 0 (no NULL-role admin-impersonation via JWT fallback — post-critic C1 security).
  22. UPDATE on `pg_viewer_audit_log` as aikm → permission denied (append-only proof — post-critic C2 security).
  23. 31st `POST /sql` in 60s → 429 `Retry-After` (rate limit proof — post-critic H2 security).
  24. Nested-comment `/* /* */ DROP */ SELECT 1` → validator rejects.
  25. Mixed-case `DrOp tAbLe users` → validator rejects.
  26. Unicode BOM + SELECT → validator accepts after BOM strip.
  27. Unicode Cyrillic Ѕ-ELECT → validator rejects (not real SELECT token).
  28. CSV export of 1500-row source → body has 1000 rows, `X-Truncated: true` header, NO fake comment row (post-critic M5 consistency).
  29. `SELECT 'DROP TABLE users' AS x` → ACCEPT (string literal is not a keyword token — documented).
  30. Error sanitization: trigger `SELECT bogus_col FROM maximo_mxwo` → response body does NOT contain "aikm_viewer", DSN, file path, DETAIL, or HINT.
  31. Bypass via `\copy` meta-command in POST /sql → rejected as parse error (documented behavior; not in keyword denylist anymore — post-critic M3 ops).
  32. Grant-audit test: enumerate tables with `has_table_privilege('aikm_viewer', t, 'SELECT')=false`; assert `grant_missing=true` surfaces in `/tables` response instead of raw 42501 (post-critic C2 ops).
- **驗收**: All 32 PoC tests pass (correct rejection / expected behavior observed).
- **邊界**: PoC tests run against deployed staging DB, never production-write.
- **Dispatch to**: `vuln-verifier`.

### T-042 — Deploy to 192.168.1.11 (SPLIT migration, post-critic C1 ops)
- **目標**: SSH, pull, run pre-flight, pause ETL, run 001 as postgres, run 002 as aikm, rebuild backend+frontend, verify health, restart ETL.
- **範圍**: deploy runbook (operator doc in quickstart.md §2 + §10). Migration invocation MUST be split:
  - `docker exec -i aikm-postgres psql -U postgres -d aikm -v pg_viewer_password="$PG_VIEWER_PASSWORD" -v ON_ERROR_STOP=1 < backend/scripts/pg_viewer_migrate_001_role_and_grants.sql`
  - `docker exec -i aikm-postgres psql -U aikm -d aikm -v ON_ERROR_STOP=1 < backend/scripts/pg_viewer_migrate_002_audit_table.sql`
- **輸入**: merged PR + `PG_VIEWER_PASSWORD` in `/etc/aikm/.env`.
- **輸出**: running feature on production host.
- **驗收**:
  - Pre-flight: `rolsuper` for postgres = t; `max_connections ≥ 200`; no dangerous extensions.
  - `docker compose stop aikm-maximo-extractor` before migration (avoid AccessShareLock contention — post-critic M1 ops).
  - 001 applied as postgres — verification vector (f, f, f, t).
  - 002 applied as aikm — verification vector (t, t, f, f).
  - `docker compose up -d --build backend frontend`.
  - `docker compose start aikm-maximo-extractor`.
  - Health: `curl http://192.168.1.11:8000/api/health` = 200.
  - Smoke: `curl -H "Authorization: Bearer $ADMIN_JWT" http://192.168.1.11:8000/api/pg-viewer/tables` returns 200 with tables (includes `users_public` but NOT `users`); admin browser can browse `maximo_mxwo` end-to-end; audit row present with redacted raw_sql.
- **邊界**: Do NOT touch Drone CI, Maximo Liberty, or other containers. Do NOT skip pause-ETL step.
- **Dispatch to**: (user executes; agent produces the runbook).

### T-043 — Retention purge + partition healthcheck cron — ACTUALLY INSTALLED (post-critic H1 ops + R2 M1/N2)
- **目標**: Install TWO crons on 192.168.1.11 and verify they run. Not "document and hope" — actually drop files in `/usr/local/bin` + `/etc/cron.d` and watch at least one execution succeed. Purge runs as `aikm_audit_purger` (R2 M1). Healthcheck ensures next partition exists + alerts on spillover (R2 N2).
- **範圍**:
  - new `backend/scripts/pg_viewer_retention_purge.sh` (shell — identical to quickstart §10a)
  - new `backend/scripts/pg_viewer_partition_ensure.sh` (shell — identical to quickstart §10b)
  - new `backend/scripts/pg_viewer_retention_purge.sql` (pure SQL fallback for manual runs)
  - update `quickstart.md §10` (already done in R2 pass — this task VERIFIES the content matches the shipped scripts)
  - deployment step: `scp` both shell scripts to `/usr/local/bin/` on 192.168.1.11 + install `/etc/cron.d/pg-viewer-purge` + `/etc/cron.d/pg-viewer-partition-ensure`
- **輸入**: `PG_VIEWER_AUDIT_RETENTION_DAYS` env (default 180); `PG_AUDIT_PURGER_PASSWORD` in `/etc/aikm/.env`; `ALERT_WEBHOOK_URL` (Discord or Drone).
- **輸出**: two shell scripts + two cron files + one SQL file + verified post-install behavior.
- **驗收**:
  - **Purge cron runs as `aikm_audit_purger`, NOT aikm** (R2 M1 explicit requirement). `ps -ef | grep pg-viewer-purge` during execution shows the purger DSN in use.
  - Dry-run on a freshly deployed DB (no partitions older than 180d) → exit 0, no DROP issued, log line "[NOTICE] no partitions to drop".
  - Seed test: manually `CREATE TABLE pg_viewer_audit_log_2020_01 PARTITION OF … FOR VALUES FROM ('2020-01-01') TO ('2020-02-01'); ALTER OWNER TO aikm_audit_purger;` → run purge → partition dropped → `\dt pg_viewer_audit_log_*` no longer lists it.
  - Authorization test: attempt the same DROP as aikm → `ERROR: must be owner of table …` (proves append-only on aikm is intact).
  - Healthcheck cron creates next month's partition when missing: delete `pg_viewer_audit_log_YYYY_MM` for next month → run healthcheck → partition re-created + row in log.
  - Healthcheck alert on spillover: `INSERT INTO pg_viewer_audit_log_spillover (…)` one row → run healthcheck → alert fires (check webhook mock / log).
  - `/etc/cron.d/pg-viewer-purge` contents match quickstart §10a verbatim; file owner root:root, mode 0644.
  - `/etc/cron.d/pg-viewer-partition-ensure` analogous.
  - Post-install `systemctl list-timers | grep cron` or `cat /var/log/cron` after first 24h shows both crons fired without error.
- **邊界**: No app-level changes. MUST NOT use `psql -U aikm …` in the purge path — R2 M1 explicit ban. MUST NOT grant DROP to aikm on the audit table.
- **Dispatch to**: `db-expert` (SQL + script review) → `fullstack-engineer` (cron install + smoke test) → `critic` (verify purger identity).

### T-044 — CI pipeline update (post-critic H4 ops)
- **目標**: Update `.github/workflows/main-deploy.yml` to apply migrations automatically on deploy + add a post-deploy smoke test for `/api/pg-viewer/tables`; add nightly grant-audit workflow that alerts on missing SELECT grants to `aikm_viewer`.
- **範圍**: `.github/workflows/main-deploy.yml` (edit); new `.github/workflows/pg-viewer-grant-audit.yml` (nightly cron).
- **輸入**: T-042 runbook; existing self-hosted runner on 192.168.1.11.
- **輸出**: two workflow YAMLs.
- **驗收**:
  - main-deploy: detects `backend/scripts/pg_viewer_migrate_*.sql` change → pre-flight + apply 001 as postgres + apply 002 as aikm BEFORE `docker compose up`.
  - Post-deploy smoke: `curl /api/pg-viewer/tables` with admin token (stored as GH secret `PG_VIEWER_CI_ADMIN_JWT`) returns 200.
  - pg-viewer-grant-audit: nightly enumerates public tables where `has_table_privilege('aikm_viewer', t, 'SELECT')=false`; alerts via GitHub issue comment or Discord webhook if non-zero.
- **邊界**: Do NOT remove existing workflow steps; do NOT store `PG_VIEWER_PASSWORD` in GH secrets (reads from host `/etc/aikm/.env`).
- **Dispatch to**: `fullstack-engineer` (pipeline code) → `critic` (security review of secret handling).

### T-045 — Observability (post-critic M6 ops)
- **目標**: Emit Prometheus histogram `pg_viewer_request_duration_seconds{endpoint, status}` + counter `pg_viewer_requests_total{endpoint, status}`.
- **範圍**: `backend/app/routers/pg_viewer.py` (add middleware / decorator); reuse existing metrics infra if present, else add a simple `prometheus_client` histogram behind a `try: import prometheus_client`.
- **輸入**: NFR-001/NFR-002/NFR-006.
- **輸出**: metrics endpoint scrape exposes the histogram.
- **驗收**: `curl http://192.168.1.11:8000/metrics | grep pg_viewer` returns non-empty.
- **邊界**: If no Prometheus infra present, log `ms=<n>` at INFO level on every request — do NOT add a new container.
- **Dispatch to**: `fullstack-engineer`.

### T-046 — CSP violation reporter endpoint (R2 M2)
- **目標**: Implement `POST /api/csp-violations` to accept browser CSP violation reports from `/admin/pg-viewer/*` and log them for 30 days. Referenced by the `report-uri` directive in plan.md §5a.
- **範圍**: new `backend/app/routers/csp_violations.py`; register in `backend/app/main.py`. New table `csp_violation_log` with 30-day retention (or log-to-file if table is rejected by reviewer — document both options, pick one in P7).
- **輸入**: plan.md §5a CSP directive set.
- **輸出**: endpoint accepts JSON CSP-report payloads (both legacy `csp-report` wrapper and modern `application/reports+json` array formats), stores each, returns 204.
- **驗收**:
  - Endpoint is PUBLIC (no auth) — browsers cannot attach JWT to CSP reports. MUST accept anonymous POSTs.
  - Rate-limited to 60 req/min/IP (reuse existing rate limiter) to avoid log-flooding DoS.
  - Stored fields: `blocked_uri`, `effective_directive`, `original_policy`, `document_uri`, `violated_directive`, `source_file`, `line_number`, `status_code`, `user_agent` (from request), `ip_address` (from trusted XFF). NO PII: do NOT store full request bodies beyond the CSP fields; do NOT store auth cookies; do NOT store referrer query-strings.
  - Retention: 30 days. Nightly purge via existing retention cron framework (can piggyback on T-043 healthcheck or run a separate mini-cron).
  - Integration test: crafted report POST → 204; GET same endpoint → 405.
  - Integration test: oversize body (>16 KB) → 413 reject.
  - Integration test: malformed JSON → 400 safely (no stack trace leak).
- **邊界**: Do NOT require auth; do NOT widen the CSP. Do NOT store raw request bodies (data-minimization per GDPR good-hygiene).
- **Dispatch to**: `fullstack-engineer` → `critic` (privacy).

---

## Dependency Graph

```
T-001 ─┐
       ├──► T-010 ──► T-011 [P]
T-002  ┤            ├► T-012 [P]
T-002.5┤            ├► T-013 [P]
T-003 ─┘            ├► T-014 [P]
                    ├► T-014.5 [P] (PII redactor + sanitizer — feeds T-014 + T-022)
                    ├► T-014.6 [P] (rate limiter — feeds T-020 + T-022)
                    ├► T-015
                    └► T-016 [P]  (SQL validator)
                                └►─┐
                                    ▼
                                T-020 ──► T-021
                                    │
                                    └► T-022 (SQL endpoint, needs T-016 + T-020)
                                    │
                                    └► T-030 [P] ─┬► T-032 [P]
                                                  ├► T-033
                                                  ├► T-034 [P]
                                                  ├► T-035 [P]
                                                  ├► T-036   (SQL editor page, needs T-022 + T-031)
                                                  └► T-037 [P] (SQL editor E2E, needs T-036)
                                              T-031 [P]  ──► T-046 [P] (CSP violation endpoint — R2 M2)
                                      ──► T-040 ──► T-041 ──► T-042 ──┬─► T-043 (purge+healthcheck crons — R2 M1/N2)
                                                                       ├─► T-044 (CI migrations + grant-audit)
                                                                       └─► T-045 (observability)
```

**Critical path**: T-001/002/002.5/003 → T-010 → T-015 → T-016 → T-020 → T-022 → T-036 → T-040 → T-041 → T-042 → T-043.

**Parallelizable batches**:
- After T-010: T-011, T-012, T-013, T-014, T-014.5, T-014.6, T-016 can all run in parallel (7-way).
- After T-020: T-030, T-031 in parallel; T-022 starts (depends on T-016 + T-020).
- After T-030 + T-022: T-032, T-034, T-035 in parallel; T-033 heavier single-owner; T-036 starts after T-031+T-022.
- After T-036: T-037 [P] alongside late frontend polish.
- After T-031: T-046 [P] (CSP violation endpoint — independent of data-path work).
- After T-042: T-043, T-044, T-045 all [P] (post-deploy polish, independent).

## Parallel-safe Task Count

Tasks marked `[P]`: T-002, T-002.5, T-011, T-012, T-013, T-014, **T-014.5**, **T-014.6**, **T-016**, T-030, T-031, T-032, T-034, T-035, **T-037**, **T-046** = **16 parallel-safe**.
Total tasks: **31** (T-001, T-002, T-002.5, T-003, T-010, T-011, T-012, T-013, T-014, T-014.5, T-014.6, T-015, T-016, T-020, T-021, T-022, T-030, T-031, T-032, T-033, T-034, T-035, T-036, T-037, T-040, T-041, T-042, T-043, T-044, T-045, T-046). Growth since round-2 critic pass: **+1 new task (T-046 CSP violation endpoint)**. Updated acceptance criteria: T-014.6 (Redis-down fail-closed), T-031 (full CSP directive set), T-043 (purger-role + healthcheck cron actually installed).

## Rollback Procedure (if deploy fails)

1. `export PG_VIEWER_ENABLED=false` in `.env` on 192.168.1.11.
2. `docker compose up -d backend` to pick up env change.
3. If migration partial: `psql -c "DROP TABLE IF EXISTS pg_viewer_audit_log; DROP ROLE IF EXISTS aikm_viewer;"`.
4. Revert commits (branch `013-postgres-viewer` never squash-merged until green).
5. Existing features unaffected — orthogonal design.

## Done Criteria (feature)

- [ ] All T-001 … T-046 closed (31 tasks; includes R2 additions T-014.5 / T-014.6 / T-043 / T-044 / T-045 / T-046).
- [ ] critic round-3 clean (no HIGH / CRITICAL) on browse path, SQL editor path, CSP, and audit-purge runbook.
- [ ] vuln-verifier all 32 PoC scenarios green (see T-041).
- [ ] Playwright screenshots of `/admin/pg-viewer` AND `/admin/pg-viewer/query` committed to `specs/013-postgres-viewer/`.
- [ ] Both crons (`pg-viewer-purge` weekly + `pg-viewer-partition-ensure` nightly) installed on 192.168.1.11 and observed running for at least one cycle before merge to main.
- [ ] `memory/MEMORY.md` updated with feature summary (mentions SQL editor + purger role + CSP).
