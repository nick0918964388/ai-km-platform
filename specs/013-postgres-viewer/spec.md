# Feature Specification: PostgreSQL Online Viewer (Admin-only, Read-only)

**Feature Branch**: `013-postgres-viewer`
**Created**: 2026-04-20
**Status**: Clarifications RESOLVED 2026-04-20 — ready for Phase 2 execution
**Input**: User description (Discord 2026-04-20): 「可以直接預覽 postgres 資料庫的功能（線上）」— an online feature where an admin can browse the contents of the Postgres DB without SSH/psql.
**Related memory**: `project_pg_viewer_backlog.md` — admin-only, read-only, query timeout, row limit required; evaluate pgAdmin / Adminer / custom.

---

## Clarifications (RESOLVED 2026-04-20)

> All blocking clarifications were resolved by the user on 2026-04-20. Decisions are now binding contract.

- **C-1 Scope of tables exposed — RESOLVED**: Expose **every** table in the `public` schema that `aikm_viewer` has SELECT on. Sensitive tables (`users`, `sessions`, `api_keys`, `pg_viewer_audit_log`) are **not granted** to `aikm_viewer` at the role level (post-critic-round-1 decision: option-b view approach — see §FR-062). For user data, admins browse the curated `users_public` view. Exclude only `pg_catalog` / `information_schema` / `pg_toast`. Sensitive-column redaction (§FR-060) remains a second line of defense for any column whose name matches `/password|secret|token|api_key|credential|private_key|passphrase/i`. Access gate is purely `require_admin`.
- **C-2 Freeform SQL editor — RESOLVED, INCLUDED in v1**: A SELECT-only SQL editor ships in v1 alongside the table browser (see US5 below). All read-only layers still apply PLUS a new Layer-9 SQL static analysis (see §Security). Multi-statement input is rejected outright.
- **C-3 Export — RESOLVED**: Yes, CSV export up to row-limit (1,000 rows), gated by admin role + audited.
- **C-4 Deploy target — RESOLVED**: Self-built custom UI embedded in `aikm-backend` + `/admin/pg-viewer` Next.js page. No pgAdmin / Adminer.
- **C-5 Saved queries — DEFERRED (v1 out-of-scope)**. Add to backlog if requested.
- **C-6 Write-back upgrade path — RESOLVED: no writes, ever**. Dedicated `aikm_viewer` Postgres role with only `SELECT` GRANTs. Any future write feature must use a different codepath / role.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Browse a table's contents (Priority: P1) 🎯 MVP

An admin wants to inspect rows of a specific Postgres table (e.g. `maximo_mxwo`, `users`, `query_audit_log`) without SSH'ing into the server or opening psql.

**Why P1**: This is the direct user request; solves the pain of "需要看資料但要 docker exec 進 container 下 SQL". Unblocks debug workflows.

**Independent Test**: Admin logs in, opens `/admin/pg-viewer`, sees a searchable list of tables, clicks `maximo_mxwo`, sees the first 50 rows (paginated) with real column headers, clicks "next page" and gets the next 50 rows, total elapsed < 3s per action.

**Acceptance Scenarios**:
1. **Given** admin is on `/admin/pg-viewer`, **When** page loads, **Then** the left panel shows a tree/list of all user tables in `public` schema grouped by prefix (e.g. `maximo_*`, `auth/*`, system/*), with row-count badge per table fetched from `pg_class.reltuples` (approximate, cheap).
2. **Given** admin clicks table `maximo_mxwo`, **When** row fetch completes, **Then** UI shows column headers with type hints, first 50 rows, a pager, and total-row indicator ("Approximately 10,742 rows · showing 1-50").
3. **Given** admin is on a table view, **When** admin pages forward/backward, **Then** the viewer uses keyset or OFFSET pagination with stable ORDER BY (primary key desc by default), and each fetch < 2s for tables up to 1M rows.
4. **Given** admin has been idle, **When** admin switches back and clicks a table, **Then** expired JWT returns 401 and admin is bounced to login (no silent failure).

---

### User Story 2 — Inspect a table's schema (Priority: P1)

An admin needs to know a table's columns, types, indexes, and foreign keys — e.g. before writing a new NL2SQL few-shot example.

**Independent Test**: Admin clicks the "Schema" tab on a table view and sees a definition panel listing columns (name/type/nullable/default), PK, indexes, FKs, and approximate row count.

**Acceptance Scenarios**:
1. **Given** admin is on table view for `maximo_pm_workorders`, **When** admin clicks "Schema", **Then** system shows columns from `information_schema.columns`, indexes from `pg_indexes`, FKs from `information_schema.table_constraints`, all rendered in Carbon DataTable.
2. **Given** a table has 50+ columns, **When** admin views schema, **Then** panel is scrollable with a sticky header row.

---

### User Story 3 — Filter and sort a single table (Priority: P2)

An admin wants to filter rows by one or more column values (e.g. `status = 'OPEN'`, `changedate > '2026-04-01'`) and sort by a column, without writing SQL.

**Independent Test**: Admin picks a column, selects an operator (`=`, `>`, `<`, `LIKE`, `IN`), enters a value, applies; table re-queries with WHERE clause server-side; result count updates; admin adds a second filter combined with AND; both are respected.

**Acceptance Scenarios**:
1. **Given** admin is viewing `maximo_mxwo`, **When** admin adds filter `status = 'APPR'` and clicks Apply, **Then** backend issues `SELECT ... WHERE status = $1 ORDER BY wonum DESC LIMIT 50` with parameterized `$1`, returns matching rows.
2. **Given** admin sorts by `changedate DESC`, **When** query runs, **Then** ORDER BY is applied (column name validated against schema to prevent injection) and pager preserves sort.
3. **Given** admin enters a filter value with SQL metachars (e.g. `'; DROP TABLE users; --`), **When** query runs, **Then** value is bound as parameter, no SQL is executed from the value, and no error surfaced other than "no rows".

---

### User Story 4 — CSV export of current view (Priority: P2)

An admin wants to download the current filtered result set (capped at row-limit) as CSV for offline analysis.

**Independent Test**: Admin clicks "Export CSV" on a filtered table view; a file download of up to 1,000 rows matching current filters arrives; filename includes table name + timestamp.

**Acceptance Scenarios**:
1. **Given** admin has a filtered view with 380 matching rows, **When** admin clicks "Export CSV", **Then** response is `text/csv` with all 380 rows, Content-Disposition attachment, filename `{table}_{yyyyMMdd_HHmmss}.csv`.
2. **Given** filtered result would return > 1,000 rows, **When** admin clicks "Export CSV", **Then** CSV contains the first 1,000 rows (no fake comment row — CSV has no comment syntax). Response includes header `X-Truncated: true` and `X-Row-Count: 1000`; UI reads the header and shows a toast "Truncated at row-limit 1000".
3. **Given** admin lacks admin role, **When** admin calls export endpoint directly, **Then** 403.

---

### User Story 5 — SELECT-only SQL editor (Priority: P1)

An admin wants to run an ad-hoc SELECT (e.g. a JOIN across `maximo_mxwo` and `maximo_assets`, or an aggregation that the table browser UI cannot express) without leaving the browser.

**Why P1**: Explicitly requested by the user on 2026-04-20 as part of v1. The table browser alone cannot express JOINs or GROUP BY.

**Independent Test**: Admin opens `/admin/pg-viewer/query`, pastes `SELECT status, COUNT(*) FROM maximo_mxwo GROUP BY status ORDER BY 2 DESC`, clicks Run, sees a result grid with 2 columns + execution-time badge + row-count. Attempts to run `DROP TABLE users` → rejected inline with "forbidden keyword" before any DB round-trip.

**Acceptance Scenarios**:
1. **Given** admin is on the SQL editor tab, **When** admin submits a valid `SELECT ... LIMIT 10`, **Then** server parses it via `sqlparse`, confirms exactly 1 statement of type `SELECT` (or CTE-headed `WITH ... SELECT`), runs via `aikm_viewer` role with `SET LOCAL statement_timeout = '10s'`, auto-appends `LIMIT 1000` if absent, returns `{columns, rows, row_count, elapsed_ms, truncated}`.
2. **Given** admin submits any of `INSERT / UPDATE / DELETE / DROP / TRUNCATE / GRANT / CREATE / ALTER / COPY / CALL / \copy / VACUUM / ANALYZE / REINDEX / CLUSTER / SECURITY LABEL / COMMENT / LOCK`, **When** the request reaches the endpoint, **Then** the static-analysis layer rejects it with HTTP 400 `{detail: "forbidden keyword: DROP"}` before opening a DB connection; audit row status=`forbidden`.
3. **Given** admin submits two statements separated by `;` (e.g. `SELECT 1; SELECT 2;`), **When** parsed, **Then** rejected with 400 `{detail: "multi-statement input not allowed"}`.
4. **Given** admin submits a statement with an unknown table / column (e.g. `SELECT * FROM does_not_exist`), **When** executed, **Then** Postgres raises; server catches, returns 400 with sanitized error (no stack trace, no connection string leakage); audit row status=`error`.
5. **Given** admin submits `SELECT pg_sleep(30)`, **When** executed, **Then** Postgres aborts after 10s due to `statement_timeout`; server returns 408; audit row status=`timeout`.
6. **Given** query returns 5,000 rows, **When** server-side wrapper `SELECT * FROM (...) _limited LIMIT 1000` caps the result, **Then** response has `truncated: true`, `row_count: 1000`, `notice:"LIMIT 1000 server-wrap applied"`; UI shows a warning banner.
8. **Given** admin submits `SELECT ... LIMIT 5000`, **When** validator runs, **Then** rejected with 400 `row limit exceeded (server-side cap 1000)` (no clamp, decision 2026-04-20).
7. **Given** admin lacks admin role, **When** they POST to `/api/pg-viewer/sql`, **Then** 403.

---

### Edge Cases

- Table with no primary key → use `ctid` DESC as stable sort (or `xmin`); document in UI "No PK — using ctid".
- Very wide table (100+ columns) → horizontal scroll with sticky first column.
- `bytea` / large text columns → truncate to first 200 chars + "[show more]" affordance (do NOT stream full blobs to client).
- `timestamptz` → render as ISO 8601 with tz, user tz hint.
- NULL → render as italic grey `NULL`.
- Empty table → show empty state with "0 rows" (not an error).
- Backend query timeout (10s) → surface "Query timed out, try narrower filter" toast, audit log entry with `status=timeout`.
- User manually crafts URL to a nonexistent table → 404, no stack trace.
- DB connection pool exhausted → 503 with retry hint, circuit breaker engages (reuse `circuit_breaker.py`).
- Sensitive columns (e.g. `users.password_hash`, `system_settings.*_secret`) → always redacted as `***` server-side regardless of admin role.
- Admin role revoked mid-session → next request returns 401/403 (re-fetched `account_level` per request).
- `aikm_viewer` PG role disabled mid-query → Postgres holds the live connection until current query completes; the next reconnect fails and circuit breaker opens, endpoints return 503 until the role is re-enabled.
- Admin pastes a password or bearer token inside SQL literal → redactor (FR-017a) scrubs before audit insert; admin is still advised in UI banner not to paste secrets.
- `aikm_viewer` password rotated while backend is live → existing pool connections keep working until recycled (`pool_recycle=1800`); new connections after rotation fail until backend restart. Documented in quickstart §9 rotation runbook.

---

## Requirements *(mandatory)*

### Functional Requirements

**Access Control**
- **FR-001**: System MUST require JWT auth on every endpoint (`require_admin` dependency from `backend/app/auth.py`).
- **FR-002**: System MUST return HTTP 403 for any non-admin user (including `analyst` group).
- **FR-003**: System MUST re-check `account_level == 'admin'` on every call by re-fetching the row from `users` table (NOT trusting the JWT `role` claim). The `require_admin` dependency MUST read `account_level` directly from DB per request and compare against the literal string `'admin'`; any fall-through to `payload.get('role')` is forbidden for pg-viewer endpoints. If a dedicated `require_admin_strict` helper is needed to avoid regressing other endpoints, create one; reuse the post-012 fix in `backend/app/auth.py` which already refuses to start with the default `JWT_SECRET` in production (see `auth.py:19-39` on branch `012-maximo-query-tools` awaiting merge to main). **No JWT-role trust assumptions anywhere in pg-viewer code.**

**Read-only Enforcement (Defense in Depth)**
- **FR-010**: System MUST connect to Postgres as a **dedicated role `aikm_viewer`** whose GRANTs are only `USAGE` on `public` schema + `SELECT` on allowed tables. No INSERT/UPDATE/DELETE/TRUNCATE/DDL privilege exists at the role level.
- **FR-011**: System MUST construct queries via parameterized SQL using `psycopg`/`sqlalchemy` bind params; column/table names MUST be validated against an in-memory allow-list built from `information_schema` (no string concat of user input into identifier positions).
- **FR-012**: System MUST enforce a 10s statement timeout via THREE independent mechanisms (belt-and-suspenders, post-critic-round-1 decision): (a) role-level `ALTER ROLE aikm_viewer SET statement_timeout = '10s'` applied in migration (always active regardless of transaction mode); (b) per-transaction `SET LOCAL statement_timeout = '10s'` inside an explicit `async with engine.begin()` block; (c) asyncpg pool `command_timeout=10` set on the viewer engine. Additionally set role-level `idle_in_transaction_session_timeout = '30s'` and `lock_timeout = '2s'` to prevent a stuck admin query from holding locks against ETL.
- **FR-013**: System MUST cap every query at `LIMIT {row_limit}` where `row_limit ≤ 1000`. Browse-path: server-side injection. SQL-editor path: validator **rejects with HTTP 400** `row limit exceeded (server-side cap 1000)` if the user-supplied outer `LIMIT` exceeds 1000 (decision finalized 2026-04-20 post-critic: reject, do not clamp — least surprise). If the user omits LIMIT, validator **wraps** the statement as `SELECT * FROM ({user_sql}) _limited LIMIT 1000` (decision finalized 2026-04-20 post-critic: wrap, do not detect-and-append — sqlparse cannot reliably distinguish outer vs subquery LIMIT).
- **FR-014**: The SELECT-only SQL editor endpoint `POST /api/pg-viewer/sql` MUST subject user input to a **Layer-9 SQL static analysis** pipeline BEFORE any DB round-trip:
  1. **Normalize**: strip BOM, NFC-normalize unicode, `.strip()` input; reject empty. Reject if `len(sql) > PG_VIEWER_SQL_MAX_LEN` (default 8000) with 400 `input exceeds max length`.
  2. **Multi-statement check**: tolerate exactly one trailing `;` after whitespace; any other `;` (including `SELECT 1; SELECT 2`, `SELECT 1; /*x*/;`) → 400 `multi-statement input not allowed`.
  3. **Parse**: `sqlparse.parse(stripped)` MUST yield exactly 1 non-empty statement.
  4. **First-token gate**: first meaningful token (skip comments/whitespace) MUST be `SELECT` OR `WITH`. Any other keyword → 400 `forbidden keyword: <keyword>`.
  5. **Token-walk denylist (function + keyword)**: walk all tokens; if any matches `{INSERT, UPDATE, DELETE, DROP, TRUNCATE, GRANT, REVOKE, CREATE, ALTER, COPY, CALL, VACUUM, ANALYZE, REINDEX, CLUSTER, COMMENT, LOCK, SECURITY}` as keyword, **OR matches any of the forbidden FUNCTION names** `{dblink, dblink_exec, dblink_connect_u, pg_read_file, pg_read_server_files, pg_ls_dir, pg_stat_activity, pg_sleep, pg_terminate_backend, pg_cancel_backend, pg_reload_conf, lo_import, lo_export}` as identifier → 400. (Extensions `dblink`/`postgres_fdw`/`file_fdw` MUST additionally be blocked by the migration — see §FR-062.)
  6. **Outer-LIMIT enforcement (WRAP, not detect-and-append — post-critic decision)**: after passing steps 1-5, the sanitized SQL is ALWAYS wrapped as `SELECT * FROM ({user_sql}) _limited LIMIT 1000`. This removes the need to distinguish outer-LIMIT from subquery-LIMIT via sqlparse. If the user-supplied outer statement contains a top-level `LIMIT` whose integer literal exceeds 1000, reject with HTTP 400 `row limit exceeded (server-side cap 1000)` (post-critic decision: **reject, do not clamp** — least surprise).
  7. **Validator is a pure function**; no DB connection opened, no network call.
- **FR-015**: The SQL editor endpoint MUST execute using the `aikm_viewer` role (same engine / pool as table browser) inside a transaction with `SET LOCAL statement_timeout = '10s'`.
- **FR-016**: The SQL editor endpoint MUST audit EVERY call to `pg_viewer_audit_log` with `action='sql_editor'`, `raw_sql` = the submitted SQL **truncated to `PG_VIEWER_SQL_MAX_LEN` (8000 chars) BEFORE insertion** AND passed through the PII/secret redactor (see §FR-017a below), `rows_returned`, `execution_ms`, `status` ∈ {`ok`, `forbidden`, `timeout`, `error`}. INSERT MUST use SQLAlchemy `insert()` / bind-params; string concatenation of `raw_sql` into the INSERT SQL is forbidden. Audit write MUST run in an **independent transaction** (new connection or `session.begin_nested` committed before returning the HTTP response) so that a rollback of the outer request handler's tx does NOT erase the audit row.
- **FR-017**: The SQL editor endpoint MUST set `Content-Type: application/json` and return shape `{columns: [{name, data_type}], rows: [{…}], row_count, elapsed_ms, truncated: bool, notice?: string}`.
- **FR-018**: The SQL editor UI MUST surface validation errors inline without scrolling; MUST show execution time in ms; MUST disable the Run button while a query is in-flight.
- **FR-019**: If `PG_VIEWER_ENABLED=false`, the SQL editor endpoint MUST return 404 (same behavior as other pg-viewer endpoints).

**PII / Secret redaction on audit writes**
- **FR-017a**: Before inserting into `pg_viewer_audit_log.raw_sql`, the server MUST pass the SQL through a regex-based secret scrubber `redact_sql_for_audit(sql: str) -> str` that replaces:
  - Bearer tokens `Bearer\s+[A-Za-z0-9_\-\.]+` → `Bearer [REDACTED]`
  - GitHub PATs `ghp_[A-Za-z0-9]{20,}` → `[REDACTED_GHP]`
  - OpenAI-style keys `sk-[A-Za-z0-9]{20,}` → `[REDACTED_SK]`
  - Anthropic-style keys `sk-ant-[A-Za-z0-9_\-]{20,}` → `[REDACTED_SK_ANT]`
  - 20+ char hex strings (likely session tokens / HMACs) → `[REDACTED_HEX]`
  - Hard-quoted 8+ char strings adjacent to column refs matching `password|secret|token|api_key|hash|credential` → `'[REDACTED_STR]'`
  The same redactor applies to `error_message` before insert.

**Sensitive-table isolation (option-b view approach)**
- **FR-062**: The migration MUST ensure `aikm_viewer` has NO SELECT privilege on any of `users`, `sessions`, `api_keys`, `pg_viewer_audit_log`. For user data access, a curated view `public.users_public` exposing safe columns only (`id, email, display_name, account_level, created_at, last_login_at`) is created and `GRANT SELECT ON users_public TO aikm_viewer`. `EXECUTE` on ALL functions in schema `public` MUST be REVOKEd from `aikm_viewer`. The migration MUST hard-fail if any of the extensions `dblink`, `postgres_fdw`, `file_fdw`, `plperlu`, `plpythonu`, `plsh`, `adminpack` are installed. This closes the UNION/column-alias exfiltration vector (SQL editor cannot project `users.password_hash` because the role cannot SELECT from `users` at all).

**Rate limiting & DoS defense (post-critic H2)**
- **FR-063**: `POST /api/pg-viewer/sql` MUST be rate-limited to 30 requests/minute per `user_id` via Redis token-bucket using `backend/app/services/cache.py`. `/rows` and `/export.csv` MUST be rate-limited to 60 req/min per user. Exceeding → HTTP 429 `{detail:"rate limit: 30/min"}`; audit row `status='rate_limited'`.

**Audit retention (post-critic H1-ops)**
- **FR-052**: `pg_viewer_audit_log` rows are retained for 180 days by default (configurable via env `PG_VIEWER_AUDIT_RETENTION_DAYS`). Weekly purge runs via docker-exec cron on 192.168.1.11 (documented in quickstart §9). Table is partitioned by `created_at` monthly to keep VACUUM cost bounded.

**Error sanitization (post-critic H3-security)**
- **FR-064**: Every Postgres exception surfaced through a pg-viewer HTTP response MUST be passed through `sanitize_pg_error(exc) -> str`. Whitelist allowed error shapes: `column "X" does not exist`, `syntax error at or near "..."`, `relation "X" does not exist`. Anything else → return generic `query execution failed; see audit log for details`. NEVER leak role name (`aikm_viewer`), connection string, file path, or `DETAIL:` / `HINT:` lines. Error-to-HTTP mapping: SQLSTATE `57014` → 408, `42P01/42703` → 422, `42501` permission-denied → 403 with message "grant missing: contact operator", connection refused → 503.

**Browse & Schema**
- **FR-020**: System MUST provide `GET /api/pg-viewer/tables` returning a list of `{schema, name, approx_row_count, kind}` for all tables in `public` schema.
- **FR-021**: System MUST provide `GET /api/pg-viewer/tables/{table}/schema` returning columns / indexes / FKs / PK.
- **FR-022**: System MUST provide `GET /api/pg-viewer/tables/{table}/rows?limit=&offset=&order_by=&order_dir=&filters=` returning paginated rows.
- **FR-023**: System MUST default `ORDER BY` to primary key DESC; if no PK, use `ctid DESC`.
- **FR-024**: System MUST validate every `order_by` and every `filters[].column` against that table's columns pulled from `information_schema` (cached 5 min, reuse pattern from `maximo_schema_rag.py`).

**Filters**
- **FR-030**: System MUST support operators: `=`, `<>`, `<`, `<=`, `>`, `>=`, `LIKE`, `ILIKE`, `IN`, `IS NULL`, `IS NOT NULL`.
- **FR-031**: System MUST reject unknown operators with 400.
- **FR-032**: For `LIKE`/`ILIKE`, server MUST escape `%` and `_` unless the user explicitly opts in (checkbox "use wildcards").

**Export**
- **FR-040**: System MUST provide `GET /api/pg-viewer/tables/{table}/export.csv` with the same filter/sort params, capped at `row_limit` (1,000).
- **FR-041**: CSV export MUST stream via FastAPI `StreamingResponse` (no buffering full CSV in memory).

**Audit**
- **FR-050**: System MUST write one row to `pg_viewer_audit_log` for every browse, schema inspect, filter, and export, capturing: `user_id`, `user_email`, `action` (list_tables/browse/schema/filter/export), `table_name`, `filters_json`, `row_count`, `execution_ms`, `status` (ok/timeout/error), `created_at`.
- **FR-051**: Admin MUST be able to view the audit log via an existing admin page (reuse `/admin` query-audit tab or add a sub-tab — see plan.md).

**Sensitive-Column Redaction**
- **FR-060**: System MUST maintain a config `SENSITIVE_COLUMNS` = `[{table, column, strategy}]` where strategy is `redact` (→ `***`) or `hide` (→ not returned). Seed list: `users.password_hash` (hide), `system_settings` rows whose key contains `secret`/`token`/`api_key` (redact in `value`).
- **FR-061**: Redaction MUST be enforced in the backend response builder, never in frontend. The column-name pattern widens to `/password|secret|token|api_key|credential|private_key|passphrase/i`. (Note: for the SQL editor, column-name-alias redaction is a secondary defense only; the primary defense is §FR-062 role-level REVOKE on `users`/`sessions`/`api_keys`.)

### Non-Functional Requirements

- **NFR-001**: Table-list endpoint p95 < 500ms for 500 tables.
- **NFR-002**: Row-fetch endpoint p95 < 2s for a 1M-row table with a 50-row page.
- **NFR-003**: No superuser creds stored in frontend bundle or exposed via any API (verified via `critic` security audit at completion).
- **NFR-004**: Feature MUST be toggleable via env var `PG_VIEWER_ENABLED` (default `true` for admins; set `false` to disable entirely).
- **NFR-005**: Zero new external Docker services (reuse existing `aikm-backend` + `aikm-postgres`).
- **NFR-006**: Emit Prometheus histogram `pg_viewer_request_duration_seconds{endpoint, status}` on every request so NFR-001 / NFR-002 are measurable. If no Prometheus infra, log `ms=<n>` at INFO on every request so p95 can be reconstructed from logs.

### Out of Scope (v1)

- Saved queries / query history beyond audit log.
- Multi-DB support (only the `aikm` DB of the `aikm-postgres` container).
- ER diagram visualization.
- Cross-table join builder.
- Write operations (INSERT/UPDATE/DELETE) — forever.
- Editing column values inline.

---

## Success Criteria

- [ ] An admin can browse any `public` schema table end-to-end via `/admin/pg-viewer` without ever touching psql.
- [ ] An admin can run ad-hoc `SELECT` via `/admin/pg-viewer/query`; all 10+ forbidden keywords are rejected pre-DB; every attempt is audited.
- [ ] Attempting to issue a non-SELECT via any surface (URL tampering, direct API call, SQL editor keyword) returns 403/400 and is audited.
- [ ] `critic` security review returns no HIGH/CRITICAL findings.
- [ ] Audit log records every action with user + table + timing.
- [ ] Regression: existing `query_audit_log`, `permission_groups`, and NL2SQL flows are unaffected (orthogonal tables).

---

## Key Design Decisions (cross-reference)

- **Why custom embedded UI over pgAdmin/Adminer**: see `research.md`.
- **Why dedicated `aikm_viewer` PG role over app-level-only guard**: defense in depth; even a hypothetical app bug cannot write.
- **Why reuse `query_audit_log` vs new `pg_viewer_audit_log`**: we use a **separate** `pg_viewer_audit_log` — `query_audit_log` is NL2SQL-specific (`question`, `sql_generated`, `mode`), semantics differ. Details in `data-model.md`.
