# Implementation Plan: PostgreSQL Online Viewer

**Branch**: `013-postgres-viewer` | **Date**: 2026-04-20 | **Spec**: [spec.md](./spec.md)
**Status**: Phase 1 (design) complete. Clarifications RESOLVED 2026-04-20. Phase 2 unblocked. Now includes a SELECT-only SQL editor (US5).

## Summary

Build an admin-only, read-only online PostgreSQL browser **plus a SELECT-only SQL editor** integrated into the existing `aikm-backend` FastAPI app and `/admin` Next.js surface. Access is gated by existing JWT `require_admin`. At the data layer, a dedicated `aikm_viewer` Postgres role with only SELECT grants provides defense in depth. Every action is audited to a new `pg_viewer_audit_log` table.

## Technical Context

- **Language / Frameworks**: Python 3.10+, FastAPI, SQLAlchemy async + asyncpg (data path), `psycopg[binary]>=3.1` (identifier-quoting helper only — see research.md D-3 bridge rule), `sqlparse>=0.4.4` (Layer-9 static analysis). TypeScript 5.x strict, Next.js 15.5, React 19, IBM Carbon v1.100, Zustand, Tailwind v4 (frontend).
- **Storage**: PostgreSQL (`aikm-postgres`). New tables: `pg_viewer_audit_log`. New DB role: `aikm_viewer`.
- **Auth**: reuse `backend/app/auth.py` `require_admin`.
- **Deployment**: `docker compose up -d --build backend frontend` on 192.168.1.11. No new containers.
- **Env vars added**: `PG_VIEWER_DATABASE_URL`, `PG_VIEWER_ENABLED` (default `true`), `PG_VIEWER_ROW_LIMIT` (default 1000), `PG_VIEWER_STMT_TIMEOUT_MS` (default 10000), `PG_VIEWER_SQL_MAX_LEN` (default 8000), `PG_VIEWER_AUDIT_RETENTION_DAYS` (default 180), `PG_VIEWER_RATE_LIMIT_SQL` (default 30/min), `PG_VIEWER_RATE_LIMIT_ROWS` (default 60/min), `PG_VIEWER_PASSWORD` (hex, via `openssl rand -hex 32`; URL-safe, NOT base64). Frontend: `NEXT_PUBLIC_PG_VIEWER_ENABLED` (SSR disable banner).
- **Constraints**: Admin-only, read-only, row-limit ≤ 1000, 10s statement timeout, full audit, zero new containers.
- **Scale**: ~20-500 tables, up to ~10M rows per largest table. Concurrent admins ≤ 5.

## Data Flow

```
Browser (admin)
  │  JWT (localStorage) + API call
  ▼
Next.js /admin/pg-viewer page
  │  fetch /api/pg-viewer/...
  ▼
FastAPI backend (aikm-backend)
  │  require_admin (JWT) — 403 if not admin
  │  load viewer engine (aikm_viewer role) — lazy singleton
  │  ── Path A: table browser (GET /tables /schema /rows /export.csv) ──
  │     BEGIN; SET LOCAL statement_timeout = '10s';
  │     build SQL: validated identifiers + parameterized values + LIMIT 1000
  │     execute → fetch → redact sensitive columns
  │     COMMIT (read-only, effectively no-op)
  │  ── Path B: SQL editor (POST /sql) ──
  │     Layer-9 static analysis (sqlparse): statement-count == 1,
  │                                         first token ∈ {SELECT, WITH},
  │                                         no forbidden keyword,
  │                                         auto LIMIT 1000 if absent
  │     BEGIN; SET LOCAL statement_timeout = '10s';
  │     execute raw validated SELECT via viewer engine
  │     shape result → {columns, rows, row_count, elapsed_ms, truncated}
  │  ── common ──
  │  audit row → pg_viewer_audit_log (via main aikm session, action ∈
  │              {list_tables, schema, browse, filter, export, sql_editor})
  ▼
Postgres (aikm-postgres)
  │  aikm_viewer role can ONLY SELECT
```

## Security Model

| Layer | Control |
|---|---|
| L1 App-level auth | JWT bearer + `require_admin_strict` on every endpoint — re-fetches `account_level` from DB per request, NEVER trusts JWT `role` claim (post-critic C1-security) |
| L2 App-level SQL shape | Identifier whitelist (information_schema via `aikm_viewer` visibility), operator whitelist, bind-params only |
| L3 App-level limits | Server-side SQL wrap `SELECT * FROM (…) _limited LIMIT 1000`; user-supplied LIMIT > 1000 → HTTP 400 reject (post-critic H5 decision: reject not clamp); no offset > 10000 without keyset |
| L4 Session-level | **Three-layer** 10s timeout: (a) role-level `ALTER ROLE aikm_viewer SET statement_timeout='10s'` in migration; (b) asyncpg `command_timeout=10`; (c) per-tx `SET LOCAL` inside `engine.begin()`. Circuit breaker wraps endpoint calls. |
| L5 DB role | `aikm_viewer` has only `SELECT` GRANTs; sensitive tables (`users`, `sessions`, `api_keys`, `pg_viewer_audit_log`) have SELECT explicitly REVOKEd (users browsed via `users_public` view only); `EXECUTE` REVOKEd on ALL functions; dangerous extensions fail-migration (post-critic C3 security: option-b view approach) |
| L6 Redaction | Backend removes/masks sensitive columns before JSON serialize; acts as secondary defense to L5 — the primary user-hash-exfil vector is closed at L5 |
| L7 Audit | Every call writes `pg_viewer_audit_log` in an **independent transaction**; `raw_sql` passes through `redact_sql_for_audit()` (PII scrubber) before INSERT; table is append-only at role level (INSERT+SELECT only, REVOKE UPDATE/DELETE) |
| L8 Feature flag | `PG_VIEWER_ENABLED=false` kills the entire feature (checked via `get_settings()` per request, not import time); SSR also renders a disabled banner (`NEXT_PUBLIC_PG_VIEWER_ENABLED`) |
| L9 SQL static analysis (editor only) | `sqlparse`-based pre-flight: multi-statement rejection, first token ∈ `{SELECT, WITH}`, token-walk KEYWORD + FUNCTION-NAME denylist (adds `dblink, pg_read_file, pg_sleep, pg_terminate_backend, lo_import, lo_export, …`); BOM strip + NFC normalize; `PG_VIEWER_SQL_MAX_LEN` cap; **wrap with `LIMIT 1000`** (not detect-and-append — post-critic C2); `pg_sleep` blocked defensively despite timeout |
| L10 Rate limiting | `POST /sql` 30/min/user; `/rows` + `/export.csv` 60/min/user via Redis token-bucket. 429 on exceed (post-critic H2 security) |
| L11 Error sanitization | `sanitize_pg_error(exc)` whitelist — never leak role name, connection string, file path, DETAIL/HINT lines. SQLSTATE→HTTP mapping: `57014`→408, `42P01/42703`→422, `42501`→403 "grant missing", else generic 500 (post-critic H3 security) |

Even if L1-L4 or L9 had a bug, L5 (the PG role + sensitive-table REVOKE + users_public view) makes a write literally impossible AND makes `users.password_hash` exfiltration impossible regardless of SQL editor input.

### Security Model — §5a Content-Security-Policy (authoritative directive set — R2 M2)

The compensating control for the accepted JWT-in-localStorage risk (H4) is a **strict nonce-based CSP** on every `/admin/pg-viewer/*` response. Round-2 critic flagged the previous `script-src 'self' + hashes` as theatrical. The directive set below is mandatory — T-031 acceptance references it verbatim.

```
Content-Security-Policy:
  default-src 'none';
  script-src 'self' 'nonce-{RANDOM_PER_REQUEST}' 'strict-dynamic';
  style-src 'self' 'nonce-{RANDOM_PER_REQUEST}';
  img-src 'self' data:;
  font-src 'self';
  connect-src 'self';
  frame-ancestors 'none';
  form-action 'self';
  base-uri 'self';
  object-src 'none';
  upgrade-insecure-requests;
  report-uri /api/csp-violations;
```

**Next.js wiring**:
- Nonce generated in `middleware.ts` matching `/admin/pg-viewer/:path*`: `crypto.randomBytes(16).toString('base64')`. One nonce per request; cryptographically random (MUST use `crypto.randomBytes`, not `Math.random`).
- Nonce is forwarded via the `x-nonce` header into the React tree and injected onto every `<Script>` / `<style>` tag via Next.js `nonce` prop (CSP helper pattern — officially supported in Next 15 App Router).
- `strict-dynamic` relaxes script-src for scripts loaded by an already-trusted (nonce-bearing) script — so Carbon's chunk-loader keeps working without weakening the policy.
- `report-uri` posts JSON to `POST /api/csp-violations` (backend endpoint — see T-046) which logs for 30 days.

**Note**: `frame-ancestors 'none'` and `object-src 'none'` plug click-jacking + legacy plugin vectors that the old policy missed. `base-uri 'self'` blocks injected `<base>` tag attacks. `connect-src 'self'` ensures XHR/fetch only goes to our origin.

### Security Model — §6 Rate limiter Redis-down policy (R2 decision 2026-04-20)

If Redis is unreachable or returns an error, the rate limiter **fails closed**: return **HTTP 503** with `Retry-After: 30` and audit `status='error'`, error_message='rate limiter backend unavailable'. Reference: FR-063. Rationale: the alternative (fail-open → allow unlimited) defeats the defense during the exact window an attacker would probe. Downstream circuit-breaker `/health/circuits` surfaces Redis status; ops paged via existing AIKM alerting. Documented in T-014.6 acceptance.

## Backend Architecture

New module `backend/app/services/pg_viewer/`:

```
pg_viewer/
├── __init__.py
├── engine.py        # lazy viewer-role engine (pool 3/7, recycle 1800, command_timeout 10) + get_viewer_db dep
├── introspect.py    # list_tables, get_schema, resolve_identifier (psycopg.sql.Identifier.as_string → asyncpg bridge, 5-min LRU)
├── query_builder.py # build SELECT from (table, filters, order_by, limit, offset) — returns (rendered_sql_str, params)
├── redaction.py     # HIDDEN / REDACTED_BY_KEY_SUBSTR + apply_redaction(rows, table) — secondary defense
├── audit.py         # write_audit() — independent tx, INSERT via SQLAlchemy insert() / bind-params; uses redact_sql_for_audit()
├── pii_redactor.py  # NEW — redact_sql_for_audit(sql) + sanitize_pg_error(exc) (post-critic C4)
├── rate_limiter.py  # NEW — Redis token-bucket; 30/min POST /sql, 60/min others (post-critic H2)
├── sql_validator.py # NEW — Layer-9 static analysis: validate_select_sql(sql) -> str | raises; BOM+NFC normalize; WRAP with LIMIT 1000
├── sql_executor.py  # NEW — run wrapped SQL via viewer engine; shape {columns, rows, row_count, elapsed_ms, truncated}
└── exporter.py      # streaming CSV writer (per-cell truncation, X-Truncated header)
```

New router `backend/app/routers/pg_viewer.py`.
Register in `backend/app/main.py`.

## Frontend Architecture

New page `frontend/src/app/(main)/admin/pg-viewer/page.tsx` (tabs: Browser / SQL), plus child route `frontend/src/app/(main)/admin/pg-viewer/query/page.tsx` (dedicated SQL editor page); child components in `frontend/src/components/admin/pg-viewer/`:

```
pg-viewer/
├── TableList.tsx        # left panel — grouped list with search
├── TableView.tsx        # right panel — tabs: Data | Schema
├── DataTab.tsx          # Carbon DataTable + Pagination + FilterBar + ExportCSV button
├── SchemaTab.tsx        # columns / indexes / FKs
├── FilterBar.tsx        # add/remove filters (column/op/value)
├── SqlEditor.tsx        # NEW — simple <textarea> (no Monaco; repo doesn't already ship it) + Run button + result grid + elapsed-ms badge + error banner
└── hooks/
    ├── useTables.ts
    ├── useTableSchema.ts
    ├── useTableRows.ts
    └── useSqlQuery.ts   # NEW — POST /api/pg-viewer/sql with in-flight state

```

Reuse existing `frontend/src/services/` pattern — add `pgViewerService.ts`.
No new npm deps. Carbon `DataTable` + `Pagination` cover all UI needs.

## Phase Gating

- **Phase 0 (done)**: spec + research + plan.
- **Phase 1 (design, this doc)**: data-model + contracts + plan (this doc).
- **Phase 2 (tasks)**: unblocked 2026-04-20 — C-1..C-6 resolved; SQL editor in scope.
- **Phase 3-5 (execute)**: P9 dispatches fullstack-engineer per Task Prompt in tasks.md, critic reviews each.
- **Phase 6 (verify)**: `critic` security audit + `vuln-verifier` writes a PoC attempting DDL / DML / injection / path traversal via all endpoints.

## Rollback Plan

- Backend: feature-flag off (`PG_VIEWER_ENABLED=false`), restart backend. Endpoints return 404.
- Frontend: `NEXT_PUBLIC_PG_VIEWER_ENABLED=false` — `/admin/pg-viewer` route shows "Disabled" banner.
- DB (preferred rollback): keep role + audit table; flip feature flag only. NO data loss.
- DB (nuclear — LOSES AUDIT HISTORY): `DROP TABLE pg_viewer_audit_log; DROP VIEW users_public; DROP ROLE aikm_viewer;` — ONLY if feature is being permanently removed. Prefer flag-flip first.
- Nothing in this feature touches existing user-facing tables, so rollback is orthogonal to main app.

## Observability

- Structured logs: `logger.info("pg_viewer.query", extra={"user_id","table","ms","rows"})`.
- Audit rows: queryable via admin UI.
- Circuit breaker status in existing `/health/circuits`.
- Metrics: Prometheus histogram `pg_viewer_request_duration_seconds{endpoint, status}` + counter `pg_viewer_requests_total{endpoint, status}` (post-critic M6 ops). Reuse existing metrics infra; if none, log `ms=<n>` at INFO so p95 can be reconstructed.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Identifier whitelist bypass via crafted column in filter | M | H | Use `psycopg.sql.Identifier` + allow-list only from `information_schema`; critic + vuln-verifier test |
| OFFSET blowup on 10M row table with order by non-indexed col | M | M | Require `order_by` to be an indexed column (check `pg_indexes`); fallback to ctid; row-budget |
| `aikm_viewer` role accidentally granted on migration rerun (GRANT drift) | L | H | Migration idempotent; add nightly check in CI that `has_table_privilege('aikm_viewer', …, 'INSERT')` is false |
| Sensitive column list drifts as schema grows | M | M | Declare in code (reviewed by critic on every schema addition); add a schema-discovery test that fails if `password` or `secret` substring appears in any new column not in the list |
| pgAdmin/Adminer added later by a second engineer, bypassing our controls | L | H | Documented in CLAUDE.md + research.md that only this viewer is allowed |
| Large result set causes frontend OOM on column-heavy tables | L | M | Server-side truncate string cols > 200 chars; "show more" fetches single cell |
| Feature flag not checked on UI, showing empty admin page | L | L | Server-side check via layout; 404 when disabled |
| sqlparse bypass (crafted unicode / dialect edge case gets a write keyword past the walker) | L | H | Defense in depth: `aikm_viewer` role cannot write regardless; vuln-verifier writes bypass attempts (UNION, stacked statements with tab/newline, comment-embedded keywords, CTE-headed DELETE, unicode escape) |
| SQL editor used to exfiltrate secrets via cross-table JOIN to `users.password_hash` | M | H | Redaction layer applies to SQL editor output too — projected columns matching redaction policy are replaced before serialization (validator computes projected columns, redaction applied post-fetch) |
| Editor query returns huge rows (one cell is 10MB bytea) | L | M | Per-cell truncation (200 chars for text, base64 + 200-char ellipsis for bytea) applied in result shaper — same rule as browse path |
| **XSS anywhere in the app pivots to pg-viewer** (JWT in localStorage) | M | H | Accepted residual — cannot be fixed in this feature without whole-app auth refactor. Mitigations: strong CSP on `/admin/pg-viewer/*` restricting `script-src`; document in risk register; re-auth prompt a future enhancement if any XSS finding filed. (post-critic H4 security) |
| **`aikm_viewer` password leak → direct PG access bypasses redaction** | L | H | `CONNECTION LIMIT 10` on role; pg_hba.conf should restrict `aikm_viewer` login to docker-internal subnet; password rotation runbook in quickstart §9. (post-critic H5 security) |
| **Grant drift from future tables** (non-aikm role creates table → no SELECT to aikm_viewer) | M | M | `ALTER DEFAULT PRIVILEGES FOR ROLE` applied for `postgres` AND `aikm`; nightly CI grant-audit check; browse endpoint catches 42501 and surfaces "grant missing" status badge (post-critic C2 ops) |
| **Audit log unbounded growth** | M | M | 180-day retention via weekly cron (runs as `aikm_audit_purger` — R2 M1; was previously wrongly as aikm with REVOKE DELETE → cron would fail); `PG_VIEWER_AUDIT_RETENTION_DAYS` env override (post-critic H1 ops) |
| **Partition miss (next month's partition not pre-created)** | M | H | **Two safety nets (R2 N2)**: (1) nightly healthcheck cron calls `ensure_next_audit_partition()` + alerts on spillover rows; (2) `write_audit()` catches 23514 check_violation and falls back to `pg_viewer_audit_log_spillover` so forensic data is never lost. pg_partman preferred if available. |
| **Retention cron fails silently (cannot DROP partition)** | H | H | **R2 M1 fix**: dedicated `aikm_audit_purger` role owns all partitions; cron authenticates as that role and can issue DROP without superuser. Verified in T-043 acceptance; alert fires if no partitions dropped in 30 days on a saturated install. |
| **CSP too weak to compensate for JWT-in-localStorage (XSS pivot)** | M | H | **R2 M2 fix**: full nonce-based CSP (`default-src 'none'` + `frame-ancestors 'none'` + `strict-dynamic` + report-uri). Documented in plan §5a. T-031 acceptance asserts each directive via curl/Playwright. T-046 collects report-uri POSTs for 30 days. |
| **pool exhaustion under concurrent admin load** | M | M | Raised pool to 3/7 (max 10) with `pool_recycle=1800`; document `max_connections ≥ 200` pre-flight check (post-critic H2 ops) |
| **`X-Forwarded-For` spoofing poisons audit IP** | L | L | Accept XFF only from trusted proxy allowlist (frontend container IP); documented in plan §Security (post-critic M1 security) |
| **Timing-attack: 403-vs-404 response-time delta leaks table existence** | L | L | Accepted residual — admin-only surface; log only, no code change (post-critic M3 security) |
| **Admin pastes secret in SQL → raw_sql leaks to other admin via /audit** | M | H | `redact_sql_for_audit()` scrubs bearer tokens, `ghp_*`, `sk-*`, 20+ hex, quoted-literal-near-sensitive-column; applied BEFORE insert (post-critic C4 consistency) |
| **psql -U aikm_viewer from non-backend host bypasses L1-L4** | L | H | `CONNECTION LIMIT 10` + pg_hba.conf subnet restriction + password rotation runbook |
| **Migration run as non-superuser fails mid-way** | H | M | Split into `001_role_and_grants.sql` (run as postgres) + `002_audit_table.sql` (run as aikm, idempotent); pre-flight privilege check in quickstart (post-critic C1 ops) |

## Constitution Check

- TypeScript strict — pass (standard).
- FastAPI standard architecture — pass (router + service layer).
- Carbon component library consistency — pass.
- API contract consistency — pass; see `contracts/pg-viewer-api.yaml`.
- New runtime deps: `psycopg[binary]>=3.1` (identifier quoting only) + `sqlparse>=0.4.4` (Layer-9). Acceptable — both vetted & pinned.

## Definition of Done

- [ ] All FR-001 … FR-064 satisfied (including FR-017a, FR-052, FR-062, FR-063, FR-064 added post-critic).
- [ ] Three-layer statement_timeout verified: `SELECT pg_sleep(30)` returns 408 in ≤ 11s via integration test (T-010 + T-020).
- [ ] Rate limit verified: 31st POST /sql in 60s returns 429.
- [ ] Grant-audit query `has_table_privilege('aikm_viewer','public.users','SELECT')` returns `false` (L5 users-table isolation).
- [ ] `users_public` view exists + `aikm_viewer` can SELECT it.
- [ ] `redact_sql_for_audit('SELECT ... \'ghp_XXXX...\'')` returns string with `[REDACTED_GHP]`.
- [ ] No HIGH/CRITICAL findings in critic-round-2.
- [ ] Migration for `aikm_viewer` role + `pg_viewer_audit_log` table applied on 192.168.1.11.
- [ ] `critic` security audit: no HIGH/CRITICAL.
- [ ] `vuln-verifier` PoC attempts (DDL, DML, OR 1=1 filter injection, PK-less table, oversize LIMIT override, role-escalation URL hack, timeout) all return 403/400 with audit entries.
- [ ] Playwright visual test of `/admin/pg-viewer` AND `/admin/pg-viewer/query` passes on 192.168.1.11 frontend.
- [ ] Admin smoke test on 192.168.1.11: open `maximo_mxwo`, paginate, filter, export — all succeed within SLOs.
- [ ] Admin smoke test on 192.168.1.11: SQL editor runs `SELECT status, COUNT(*) FROM maximo_mxwo GROUP BY status`; rejects `DROP TABLE users`; rejects `SELECT 1; SELECT 2;`; audit rows present for both success + rejection cases.
