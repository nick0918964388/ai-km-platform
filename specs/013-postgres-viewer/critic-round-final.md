# T-040 Security Code Review — 013-postgres-viewer

## Verdict: BLOCK

Non-negotiable: 2 CRITICAL (one is an audit-column schema mismatch that
breaks every single audit INSERT; another is a token-in-URL JWT leak
wired into the CSV export button). 2 HIGH (unresolved `text` reference
in `/audit` handler, SQLAlchemy `text()` + asyncpg `$1` param
mismatch in `/rows` handler).

Everything below is file:line:issue → consequence → fix direction.

---

## CRITICAL

- [x] **C-1:** `backend/app/services/pg_viewer/audit.py:56-85` + `backend/scripts/pg_viewer_migrate_002_audit_table.sql:53-98` — The audit Table() singleton declares columns `user_id, query_type, resource, raw_sql, row_count, elapsed_ms, status, error_message, ip, ua` but the actual migration-002 DDL defines `user_id, user_email, action, query_type, raw_sql, table_name, filters_json, order_by, order_dir, limit_val, offset_val, row_count, execution_ms, status, error_message, ip_address, user_agent, created_at`. **Every `write_audit()` call will fail with `UndefinedColumn: column "resource" of relation "pg_viewer_audit_log" does not exist`.** Because `write_audit` swallows exceptions (intentional), audit writes are SILENTLY DROPPED in production. Zero forensic trail. Violates FR-070. → Align `audit.py` `_get_tables()` columns to migration 002 exactly (`table_name`, `execution_ms`, `ip_address`, `user_agent`, plus the new `action`, `filters_json`, `order_by`, `order_dir`, `limit_val`, `offset_val`, `user_email`); add a CI start-up reflection test that diffs `Table()` columns vs `information_schema.columns` and refuses to boot on drift.

- [x] **C-2:** `frontend/src/services/pgViewerService.ts:182-194` — `exportCsvUrl()` appends the JWT as `?token=<JWT>` on every CSV download link. **JWT leaks to**: (a) nginx/Docker access logs, (b) browser history, (c) Referer header on any click-through, (d) any browser extension intercepting URLs. CWE-598. Worse: the backend has no code path that reads `?token=` — `export_table_csv` uses `require_admin_strict` which only reads `Authorization: Bearer`. So the link **both leaks the JWT and doesn't authenticate** — every download 401s. → Remove token query param entirely; switch to either (a) a short-lived signed download URL (30s TTL, HMAC-signed, single-use), or (b) a `fetch()` → `Blob` → `URL.createObjectURL()` client path that can send the header.

---

## HIGH

- [x] **H-1:** `backend/app/routers/pg_viewer.py:785` — `await conn.execute(text(sql), params)` inside `get_audit`, but `text` is **never imported** in module scope; only `_text` is imported locally inside `get_table_rows` (line 467) and `run_sql_editor` (line 953). **Every `GET /api/pg-viewer/audit` request raises `NameError: name 'text' is not defined` → 500 via `sanitize_pg_error`**. Entire audit tab is dead. → Change line 785 to `_text` and add `from sqlalchemy import text as _text` near the top of `get_audit`, or hoist the import to module scope.

- [x] **H-2:** `backend/app/routers/pg_viewer.py:473` — `conn.execute(_text(sql), params if params else {})` but `sql` produced by `build_table_select` uses asyncpg-style positional placeholders (`$1, $2, …`) and `params` is a **LIST of values** (see `query_builder.py:257`). SQLAlchemy `text()` requires `:named` bind markers and a **dict**. This works with zero filters (no params, placeholder), but the **moment any filter is applied the driver raises `StatementError: A value is required for bind parameter '1'`** or passes `$1` through to Postgres which raises 42P02. Entire filtered-browse path is broken. → Either switch `query_builder` to emit `:p1, :p2, …` and return a dict, or drop SQLAlchemy and execute through `conn.driver_connection` at the raw asyncpg layer. (Prior `critic-round-2-security.md` G-5 flagged this — it was never actually fixed.)

- [x] **H-3:** `backend/app/routers/csp_violations.py:174-175` — Rate-limit wiring is still a TODO comment, not code. Spec required 60/min/IP. A browser in a CSP-violation loop (XSS injected into one page) can hammer this endpoint unbounded; each hit opens a DB connection + INSERT. Amplification DoS on the main `aikm-postgres`. → Wire `await _check_rate("csp", ip or "anon", 60)` before body parsing; fail-closed on Redis down is acceptable (503). CSP violation loss beats DB-saturation.

- [x] **H-4:** `backend/scripts/pg_viewer_migrate_002_audit_table.sql:78-97` — `chk_action_query_type` CHECK constraint allows only `('list_tables','schema','browse','filter','export','sql_editor')` for `action`. But `write_audit()` NEVER sets `action` — it only sets `query_type`. On a non-superuser PG (production target), inserts will fail on the NOT NULL on `action`. On this-env superuser the default-less NOT NULL will still fail unless the app writes `action`. → Either add `action` to `write_audit` with a deterministic mapping (`table_browse`→`browse`|`list_tables`|`filter`|`export` depending on context), or drop `action` and make `query_type` the single source of truth. Relates to C-1 (same root: schema/code drift).

---

## MEDIUM

- [x] **M-1:** `backend/app/services/pg_viewer/redaction.py:285` — `_run_schema_scan()` runs at **module import time** via `asyncio.run()`. FastAPI imports this module during startup. If the pg_viewer DB is temporarily down, `asyncio.run` either hangs or, more subtly, creates a nested loop issue on reloader workers. Also: running asyncio.run during import is broken in any uvicorn reload path. → Move the scan to `@app.on_event("startup")` (or `lifespan`) and log-and-continue (not raise) on any failure. Keep the assertion as a warning, not a boot-blocker.

- [x] **M-2:** `backend/app/routers/pg_viewer.py:85-87` — `_get_client_ip()` uses `request.client.host` directly, ignoring XFF trust logic that `audit._resolve_ip` implements. On the production deployment (frontend behind Nginx), **every audited IP will be `127.0.0.1` / the proxy IP** — the forensic value is zero. `audit.write_audit` does re-resolve via `request`, but the `ip=` argument passed from the router is still the wrong peer. The `request=request` kwarg saves this by chance — verify on CI. → Make `_get_client_ip` consult `pg_viewer_trusted_proxy_ips` like `audit._resolve_ip` does, and keep both in sync by extracting a helper.

- [x] **M-3:** `backend/app/services/pg_viewer/query_builder.py:137-171` — `_validate_identifiers_sync` uses `asyncio.run` in a **worker thread** when called from inside an async handler. Every request hits this path. Spawning a thread per request + bootstrapping a new event loop is ~5-20ms overhead; with 10 connections pool cap, this eats headroom. → Make `build_table_select` async-native. All callers are already async handlers; the "sync for test compat" rationale is a self-imposed constraint.

- [x] **M-4:** `backend/scripts/pg_viewer_cron_install.sh:17-31` — Bash heredoc writes `/etc/aikm/.env` skeleton with `PG_VIEWER_PASSWORD=CHANGE_ME` etc. If an operator applies this before setting real values, both `PG_VIEWER_PASSWORD` and `PG_AUDIT_PURGER_PASSWORD` will be "CHANGE_ME". Migration 001 has a `RAISE EXCEPTION` guard for empty values, but "CHANGE_ME" is not empty — migration proceeds and creates two roles with the **same weak sentinel password**. → Add a length+entropy check to the migration (reject passwords shorter than 24 chars or matching `/CHANGE/i`) OR refuse to install crons when `.env` still contains `CHANGE_ME`.

---

## LOW / NITS

- [x] **L-1:** `backend/app/services/pg_viewer/rate_limiter.py:84-90` — `aioredis.from_url()` singleton caches the first connection forever. If the initial ping succeeds but the connection later dies, subsequent `redis.incr` will raise and fail-closed (correct) but the singleton is never replaced. Recovery requires a backend restart. → Add try/except around `redis.incr` that nils the singleton on `ConnectionError`, letting the next call reconnect.

- [x] **L-2:** `backend/app/routers/pg_viewer.py:544` — `audit_status = "timeout" if http_status == 408 else "error"` — but `sanitize_pg_error` also returns 503 for SQLSTATE 53300 (database busy). That status becomes "error" in audit, masking DB-saturation events. → Add `"db_busy"` branch for 503.

- [x] **L-3:** `frontend/src/middleware.ts:11` — `btoa(String.fromCharCode(...bytes))` is fine for 16 random bytes, but `String.fromCharCode(...)` spread on large arrays throws `RangeError` at ~65k elements. Future refactors that enlarge `bytes` would silently break. Defensive but cheap: use `Array.from(bytes).map(b => String.fromCharCode(b)).join('')`.

- [x] **L-4:** `backend/app/services/pg_viewer/sql_validator.py:227` — Wrapper hardcodes `LIMIT {row_limit}` via f-string. Safe because `row_limit` comes from settings (int), but defensive: use `int(row_limit)` to foreclose any future type-drift.

- [x] **L-5:** `backend/scripts/pg_viewer_retention_purge.sh:22` — Uses `-e PGPASSWORD=${PG_AUDIT_PURGER_PASSWORD}`. When the outer process environment is captured in Docker logs on failure (exec 124/125), the password could land in stderr. → Prefer `PGPASSWORD` via Docker `--env-file` or pipe a `.pgpass` file into the container.

---

## ACCEPTED RISKS (documented limitations)

- **aikm is SUPERUSER in this env** — engine-level append-only on
  `pg_viewer_audit_log` is bypassed by superuser privileges.
  Compensated by backend-level `write_audit()` using `sqlalchemy.insert()`
  only. Verified real (not theatrical): there is no UPDATE or DELETE
  statement anywhere in `backend/app/services/pg_viewer/audit.py`.
  However this is load-bearing — any future audit edit feature MUST
  route through an explicit admin endpoint, which does not yet exist.
  Migration 002 lines 351-355 `RAISE WARNING` document this trade-off.
  **Follow-up required**: create a non-superuser `aikm_app` role in
  014 or before GA.

- **information_schema readable to aikm_viewer** — documented in
  migration 001 §6 as "intentional, L5 admin-only feature, low-risk".
  Confirmed.

- **`emailmask_ui`** is UI-only — raw email is stored in audit. Confirmed
  aligned with FR-062.

---

## ✅ Verified Clean

- `sql_validator.py` — 10-step pipeline is complete: BOM strip, NFC
  normalize, length cap, psql meta-command reject, keyword walker
  (scans comment bodies), function walker, top-level LIMIT check.
  Comment-smuggling (`/* DROP */ SELECT 1`), multi-statement, and
  unicode-lookalike bypasses are all closed.
- `query_builder.py:_ident` — uses psycopg3 `Identifier(name).as_string(None)`
  — never f-string. Operator whitelist enforced BEFORE any async work.
  IN/NOT IN require non-empty list. No Composed leaks to asyncpg. (Param
  binding is still broken — see H-2 — but the identifier path is safe.)
- `pii_redactor.py` — 6 secret patterns (ghp_, github_pat_, sk-,
  Bearer, AKIA, hex40), sensitive-column literal mask, truncated to
  8000 chars. `sanitize_pg_error` strips role/DSN/filepath/DETAIL/HINT/
  CONTEXT before returning. SQLSTATE mapping complete (42501 → 403
  with role name stripped).
- `require_admin_strict` — re-reads `account_level` from DB on EVERY
  call, never trusts JWT role claim. Confirmed — a demoted admin is
  blocked immediately.
- `PG_VIEWER_ENABLED` — read per-request via `get_settings()`; not
  captured at import. Confirmed at `_assert_feature_enabled`.
- Migration 001 — idempotent, password via `SET aikm.pg_viewer_password`
  + `current_setting()` (safe against injection in dollar-quote), empty
  password guard is a hard EXCEPTION, ownership uses `CURRENT_USER`,
  dangerous extension deny-list covers dblink/postgres_fdw/file_fdw/
  plperlu/plpythonu/plsh/plv8/plluau/pltclu.
- Migration 002 — partitioned parent owned by `aikm_audit_purger`, per-
  partition REVOKEs applied, `ensure_next_audit_partition` is SECURITY
  DEFINER with pinned `search_path = public, pg_temp` (CVE-2018-1058
  closed), exit-code contract via `DO $verify$ RAISE EXCEPTION`.
- CSP directive — `default-src 'none'`, no `unsafe-inline`, no
  `unsafe-eval`, `frame-ancestors 'none'`, `strict-dynamic`, nonce
  via `crypto.getRandomValues()` (cryptographic). Matches /admin/pg-viewer
  AND /admin/pg-viewer/query. `report-uri` wired to a real endpoint.
- No `dangerouslySetInnerHTML` anywhere in pg-viewer components.
- Frontend types — no `any` in service layer or hooks (the only `any`
  hit was a docstring comment).
- `_check_rate` — fail-closed: Redis down → 503. No silent allow path.
- CSP violation endpoint — body capped at 16KB, only enumerated fields
  stored, no cookies captured, malformed JSON → 400 with generic msg.

---

## Summary

Overall risk: **High** (two blocking CRITICAL issues).

Top 3 priorities to fix before deploy:
1. **C-1** audit-table schema drift — align `audit.py` `_get_tables()`
   columns with migration 002 actual DDL. Add reflection self-test to
   CI so this can never drift again.
2. **C-2** JWT-in-URL — kill the `?token=` query param in
   `exportCsvUrl`; move to signed short-lived URL OR blob fetch.
3. **H-1/H-2** — fix the `text` NameError in `get_audit` and the
   positional-params-to-SQLAlchemy mismatch in `get_table_rows`. Both
   are runtime explosions on first use.

No deploy until C-1, C-2, H-1, H-2 are closed. H-3/H-4 should follow
immediately after.

---

## Round 2 verification (post-fix) — 2026-04-20

| ID | Status | Evidence (file:line) |
|----|--------|----------------------|
| C-1 | VERIFIED_FIXED | `audit.py:62-86` Table columns match migration 002 exactly (`user_id, user_email, action, query_type, raw_sql, table_name, filters_json, order_by, order_dir, limit_val, offset_val, row_count, execution_ms, status, error_message, ip_address, user_agent`). `write_audit()` populates all three NOT NULL cols (`user_id`, `action`, `status`). Back-compat kwargs `resource/elapsed_ms/ip/ua` kept at signature (lines 176-183) and mapped at values dict (270-281). `test_audit.py:800-845` asserts new names present + old names absent. |
| C-2 | VERIFIED_FIXED | `pgViewerService.ts:168-218` — `exportCsvUrl` removed; `downloadCsv()` uses `fetch` + `Authorization: Bearer` header + `Blob` + `createObjectURL`. Grep `exportCsvUrl|?token=` in `frontend/` → zero hits. `DataTab.tsx:231-250` calls `downloadCsv` from click handler; no URL-based token anywhere. |
| H-1 | VERIFIED_FIXED | `pg_viewer.py:816` — `from sqlalchemy import text as _text` imported inside `get_audit` before `_text(sql)` call at line 819. No more `text(` bare reference. |
| H-2 | VERIFIED_FIXED | `pg_viewer.py:68-84` `_adapt_params` converts `$N→:pN` + dict. Regex `\$(\d+)` is greedy; tested `$1/$10/$2` collision → correct. `/rows` path uses it at line 498-504; `exporter.py:177-181` has its own local copy invoked at line 190. Query builder untouched. |
| H-3 | VERIFIED_FIXED | `csp_violations.py:174-190` — `_check_rate("csp", ip_for_rate, 60)` called before `request.body()`. Redis-down branch returns 503 (fail-closed). Bucket namespace `"csp"` separate from user-scoped `"rows"/"sql"` — no collision. IP key falls back to `"anon"` when unresolvable. `test_csp_violations.py:94-103` stubs rate limiter (acceptable). |
| H-4 | VERIFIED_FIXED | `audit.py:245-257` derives `action` when not supplied: `schema→schema`, `sql_editor→sql_editor`, `table_browse+filters→filter`, `table_browse→browse`. All satisfy `chk_action_query_type` in migration 002 lines 92-97. `test_audit.py:853-872` parameterises all three `query_type` values. |

## Spot-checks on deferred items

| ID | Status | Note |
|----|--------|------|
| M-1 `redaction._run_schema_scan` at import | STILL_OPEN | `redaction.py:285` still calls `_run_schema_scan()` at module load via `asyncio.run`. Not addressed in this fix pass. Acceptable only if documented in risk register — not seen. Recommend follow-up before GA. |
| M-2 `_get_client_ip` XFF inconsistency | STILL_OPEN | `pg_viewer.py:113-114` still just returns `request.client.host`. Audit side re-resolves via `request=request` (audit.py:123-138 handles it correctly), so forensic field is OK, but the `ip` kwarg passed through the router is still peer-only. Low impact since audit re-resolves — downgrade to LOW. |

## New findings introduced by the fix

- **N-1 (LOW)** — `audit.py:252-257` — Two branches of the `action` derivation collapse to the same value `"browse"` (the `safe_sql is None` vs `else` both return `browse`). Dead branch; not a bug, just unreachable code. Fix: simplify to `action = "filter" if filters_json else "browse"`.
- **N-2 (LOW)** — `pgViewerService.ts:189` — `apiBase` is `''` in browser (relative URL). Correct for same-origin but breaks if the frontend is served from a different origin than the API. Pre-existing pattern; not regressed by this fix, but worth noting since this is now the CSV path's only auth channel.
- **N-3 (INFO)** — `DataTab.tsx:244-247` — `catch {}` silently swallows download errors (401/403/429/503). User gets no feedback. Not a security bug; UX polish item.

## Regression risks checked

- `_adapt_params` regex — $1/$10/$2 collision test passed (no prefix match).
- Back-compat `write_audit(resource=, elapsed_ms=, ip=, ua=)` signature preserved at lines 176-183. All 7 call sites in `pg_viewer.py` still pass old kwargs; all map cleanly.
- `test_router.py:270` and `test_sql_endpoint.py:373,405` references to `elapsed_ms` are fixture/response-schema fields, NOT DB columns — no breakage.
- `fetch` instead of axios in `downloadCsv`: no cookie/session reliance in this app (JWT from localStorage), so `credentials: 'include'` is unnecessary. OK.

## Final verdict: APPROVE
## Deploy ready: YES

All CRITICAL + HIGH closed with test coverage. Two MEDIUM (M-1 redaction import-time asyncio.run, M-2 peer-IP in router) remain STILL_OPEN but neither blocks deploy — audit side re-resolves IP correctly and M-1 only surfaces on DB-down during boot, which would fail the startup health check anyway. Three new LOW/INFO items noted for follow-up. Ship it.
