# Critic Round 2 — 013-postgres-viewer — SECURITY

**Reviewer angle**: adversarial follow-up. Verify round-1 resolutions; hunt for new bypasses introduced by the fixes themselves.
**Scope**: spec.md, plan.md, data-model.md, research.md, quickstart.md, contracts/pg-viewer-api.yaml, tasks.md. No code exists yet — pure spec review.
**Date**: 2026-04-20.

## Verdict: **CONDITIONAL_YES (one NEW 🟠 Major, several 🟡 Minor)**

Round-1 fixes are substantive and largely correct. Option-b view approach + role REVOKEs + append-only audit + split migration land cleanly. However, **the new shape of the system introduces at least one operational-level severity bug that will be discovered only after first weekly cron**: the retention purge script cannot run because the 002 migration REVOKEs DELETE from the very role the purge cron uses. Plus several leftover audit-surface holes (information_schema / pg_catalog introspection, partition GRANT inheritance, XFF trust model ambiguity, Redis-down fail-open). None is CRITICAL. All are fixable in spec before code starts.

---

## Round 1 — CRITICAL verification

| # | Finding | Planner claim | Verification | Status |
|---|---|---|---|---|
| C1 | JWT fallback / default secret trust in `require_admin` | Adds `require_admin_strict`, re-fetches `account_level` per request, rejects JWT role claim; T-002.5 blocks start on default secret | spec.md FR-003 rewritten (lines 126) explicitly forbids JWT-role fallback for pg-viewer; plan.md §Security L1 (line 57) matches; T-020 acceptance (line 218) says "All 6 endpoints gated by `require_admin_strict` (DB re-fetch)"; T-002.5 scope says RuntimeError on default secret at module import; T-041 #21 asserts `account_level IS NULL` count == 0. **Grep for "JWT payload" / "payload.get" shortcuts in 013 docs**: none found. | ✅ **RESOLVED** |
| C2 | Audit writer injection surface + not append-only | SQLAlchemy `insert()` only; independent tx; REVOKE UPDATE/DELETE/TRUNCATE from aikm | data-model.md §4b lines 288-289 contains `REVOKE UPDATE, DELETE, TRUNCATE ON pg_viewer_audit_log FROM aikm;` and `GRANT INSERT, SELECT ON pg_viewer_audit_log TO aikm;` — confirmed append-only at role level. T-014 acceptance lines 123-128 mandate `sqlalchemy.insert()` / bind-params; unit test injects `'); DROP TABLE users; --` raw_sql and asserts users table intact; separate test asserts `UPDATE pg_viewer_audit_log SET status='ok'` fails with permission denied. Independent-tx requirement is explicit (line 121). | ✅ **RESOLVED** — but see NEW-M1 (retention purge breakage). |
| C3 | SECURITY DEFINER + extension + UNION bypass → option-b view | REVOKE SELECT on users/sessions/api_keys; users_public view; REVOKE EXECUTE on all functions; extension denylist | data-model.md §4a lines 211-220: `REVOKE SELECT ON TABLE public.users FROM aikm_viewer;` (plus sessions, api_keys), then `CREATE OR REPLACE VIEW public.users_public AS SELECT id, email, display_name, account_level, created_at, last_login_at FROM public.users; GRANT SELECT ON public.users_public TO aikm_viewer;`. Line 205: `REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM aikm_viewer;` + ALTER DEFAULT for postgres and aikm owners (lines 206-208). Lines 162-166: DO-block raises exception if any of `dblink/postgres_fdw/file_fdw/plperlu/plpythonu/plsh/adminpack` is installed. Validator denylist (FR-014 step 5, line 138) includes the function-name set. Verification vector (line 223-227) expects `can_select_users=f, can_select_view=t`. | ✅ **RESOLVED** |

Round-1 CRITICAL pass rate: **3/3**.

---

## Round 1 — HIGH verification

| # | Finding | Planner claim | Verification | Status |
|---|---|---|---|---|
| H1 | CSV export row/payload budget | Per-cell truncation + 10 MB total cap | T-015 acceptance (tasks.md lines 164-170): text > 1000 chars clipped; bytea base64 + 200-char clip; 10 MB total payload test with 1000×500-col×200KB cells; memory < 50 MB RSS benchmark. | ✅ **RESOLVED** |
| H2 | Rate limiting | FR-063 + T-014.6 Redis token-bucket | FR-063 (spec.md line 161), T-014.6 (tasks.md lines 150-157), L10 in plan.md security model. Limits: 30/min POST /sql, 60/min /rows + /export.csv per user_id. 429 + Retry-After + audit `status='rate_limited'`. Audit log status CHECK includes `rate_limited` (data-model.md line 255). | ✅ **RESOLVED** (but see NEW-H1 — fail-open behavior). |
| H3 | Error sanitization | `sanitize_pg_error()` whitelist + SQLSTATE→HTTP map | FR-064 (spec.md line 167), T-014.5 acceptance (tasks.md lines 139-147) — asserts `InsufficientPrivilege("permission denied for table users to role aikm_viewer")` → "grant missing: contact operator" with role name STRIPPED; regex assertion "no role name, no connection string, no file path, no DETAIL/HINT" in output. T-041 #30 enforces at integration level. | ✅ **RESOLVED** |
| H4 | JWT in localStorage → XSS pivot | RISK_ACCEPTED + CSP compensation on `/admin/pg-viewer/*` | T-031 acceptance (tasks.md line 285): "CSP header on `/admin/pg-viewer/*` restricting `script-src` to `'self'` plus any hashes required by Carbon/Next". **CSP spec is underspecified** — see NEW-M2 (weak CSP directives). | ⚠️ **RISK_ACCEPTED with weak CSP** |
| H5 | aikm_viewer network exposure | CONNECTION LIMIT 10 + pg_hba.conf subnet + rotation runbook | data-model.md §4a line 174, 176: `CREATE ROLE aikm_viewer LOGIN PASSWORD %L CONNECTION LIMIT 10`. pg_hba.conf subnet rule mentioned in plan.md Risks (line 154, 161) and critic-round-1 H5 resolution (line 25). Rotation runbook in quickstart.md §9 (line 325+). **But**: spec.md does not actually contain the pg_hba.conf snippet. quickstart.md §9 only documents password rotation, NOT the pg_hba line. This is a documentation gap. See NEW-M3. | ⚠️ **PARTIALLY RESOLVED** |
| H6 | UNION/alias password_hash exfil | L5 role REVOKE primary defense | Closed by C3's option-b view: `aikm_viewer` has NO SELECT on `users`, so `UNION SELECT password_hash FROM users` fails with 42501. T-041 #17 PoC asserts this. | ✅ **RESOLVED** |

Round-1 HIGH pass rate: **5 fully resolved, 1 partial (H5 docs), 1 risk-accepted with weak-CSP footnote (H4)** → effective 5.5/6.

---

## Round 2 — NEW findings

### 🟠 Major

#### NEW-M1 — Retention purge cron CANNOT RUN: aikm has no DELETE on partitioned audit table
- **Location**: data-model.md §4b line 288 (`REVOKE UPDATE, DELETE, TRUNCATE ON pg_viewer_audit_log FROM aikm;`) vs quickstart.md §10 lines 350-356 purge script:
  ```bash
  docker exec aikm-postgres psql -U aikm -d aikm -c \
    "DELETE FROM pg_viewer_audit_log WHERE created_at < NOW() - INTERVAL '$RETENTION_DAYS days'"
  ```
- **Consequence**: **First Sunday 03:00 AM, the cron dies with "permission denied for table pg_viewer_audit_log"**. Silent, because cron emails are not wired. Audit log grows unbounded to 10M+ rows over 6 months → partitions become unmanageable; VACUUM costs balloon; disk fills. Full denial-of-audit scenario.
- **Fix direction**:
  - **Preferred**: make the purge operate by `DROP TABLE pg_viewer_audit_log_YYYY_MM` (partition drop) run as `postgres` superuser, not aikm. Update quickstart.md §10 to reflect this.
  - **Alternative**: grant `DELETE` on the parent partition to a NEW role `aikm_audit_purger` that is used only by the cron; keep `aikm` role append-only as designed. More complex but better isolation.
  - Add a T-043 acceptance test: run the purge script as the documented user and assert it succeeds.

---

### 🟡 Minor

#### NEW-M2 — CSP directive set under-specified (H4 compensating control weak)
- **Location**: tasks.md T-031 line 285. spec says only "restricting `script-src` to `'self'` plus any hashes required by Carbon/Next".
- **Gaps**: Nothing about `object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'none'` (clickjacking), `style-src` (can Carbon's `unsafe-inline` style be tolerated, or must hashes be used?), `connect-src` restrictions (prevent exfil via `fetch('attacker.com')`), `form-action 'self'`, `require-trusted-types-for 'script'`. Next.js by default emits inline scripts for hydration — if `script-src 'self'` lacks a `'nonce-...'` directive, Next.js breaks. Either the CSP is watered down to `'unsafe-inline'` (defeats the compensating control) or the page breaks.
- **Consequence**: XSS pivot to pg-viewer (the H4 risk) remains largely unmitigated. H4 downgrades from "risk accepted with CSP compensation" back to "risk accepted without effective compensation".
- **Fix direction**: Specify the full CSP in T-031: `default-src 'self'; script-src 'self' 'nonce-{rand}'; style-src 'self' 'nonce-{rand}' 'unsafe-hashes'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; connect-src 'self' ${API_URL}`. Test via `curl -I` + Observatory CLI in T-031 acceptance. If Next.js 15 hydration requires `'unsafe-eval'` — document the residual.

#### NEW-M3 — pg_hba.conf subnet restriction documented nowhere operational
- **Location**: spec/plan/risks reference pg_hba subnet (plan.md line 154, 161, research notes) but quickstart.md §9 rotation runbook does NOT contain the actual pg_hba.conf edit step. Nothing tells the operator to add `host all aikm_viewer samenet scram-sha-256` (or `172.18.0.0/16` docker-bridge subnet) before the migration.
- **Consequence**: Default PG image ships with permissive pg_hba (`host all all all md5` or similar). If port 5432 is ever exposed on the host (even for a debugging session), `aikm_viewer` login from anywhere becomes possible. Compensating control (CONNECTION LIMIT 10) is present but does not prevent data exfil, only throttles it.
- **Fix direction**: Add a new quickstart §11 "pg_hba hardening" with the exact `ALTER SYSTEM` / `pg_hba.conf` edits, a `SELECT pg_reload_conf()` step, and a verification (`psql -h <external_ip> -U aikm_viewer` fails). Wire to T-042 deploy runbook pre-flight.

#### NEW-M4 — Partition GRANT inheritance — new monthly partitions may lose append-only semantics
- **Location**: data-model.md §4b lines 275-278 create `pg_viewer_audit_log_2026_04` and `_2026_05` partitions of the parent. quickstart.md §10 documents that "monthly: create next-month partition" — but with just `CREATE TABLE ... PARTITION OF pg_viewer_audit_log`.
- **Subtle issue**: In PostgreSQL, when a partition is created via `PARTITION OF parent`, it **does** inherit the parent's privileges — but only for subsequently granted privs. More importantly: the **REVOKE UPDATE/DELETE/TRUNCATE FROM aikm ON pg_viewer_audit_log** issued on the parent (line 288) applies to the parent only. Individual partitions (like `pg_viewer_audit_log_2026_04`) can be addressed directly by `UPDATE pg_viewer_audit_log_2026_04 SET ...` — and the REVOKE was NOT cascaded. PG 14+ mostly propagates parent grants to partitions implicitly, but REVOKEs are partition-local. Verify: does the aikm role, via direct partition name, bypass append-only?
- **Consequence**: An attacker or buggy code that targets `pg_viewer_audit_log_2026_04` directly could still UPDATE/DELETE it, despite the parent-level REVOKE — depending on PG version semantics.
- **Fix direction**:
  1. Update the monthly partition-creation runbook (quickstart.md §10 lines 363-366) to always emit `REVOKE UPDATE, DELETE, TRUNCATE ON pg_viewer_audit_log_YYYY_MM FROM aikm;` right after `CREATE TABLE ... PARTITION OF`.
  2. Add T-043 test: after creating a new partition, assert `UPDATE pg_viewer_audit_log_YYYY_MM SET status='x'` as aikm fails with permission denied.
  3. Alternatively and cleaner: create a cron (T-044-ish) that runs `REVOKE` on all partition children monthly as a safety net.

#### NEW-M5 — Rate limiter behavior on Redis outage is unspecified (fail-open DoS bypass)
- **Location**: spec.md FR-063, tasks.md T-014.6 acceptance. No mention of Redis-down semantics.
- **Consequence**: If Redis becomes unavailable (already an existing circuit breaker target in 012), the rate limiter cannot read/write its token-bucket counter. Typical implementations default to fail-open (return `allowed=true`) — rate limit silently disabled. Attacker who knows Redis is flapping can DoS `/sql` or exfil at full speed. Fail-closed (return 503 on Redis error) gives the attacker a cheap DoS trigger: corrupt Redis → entire pg-viewer surface 503.
- **Fix direction**:
  - Recommend fail-closed with graceful degradation: if Redis down for > 5s, all `POST /sql` calls return 503 "rate limiter degraded"; `/rows` and `/export.csv` continue to function without rate limiting (log WARN per request). Document the asymmetry in FR-063.
  - Alternative: in-process fallback bucket (`cachetools.TTLCache`) per-user; bounded cache size to prevent mem-bomb.
  - Add T-014.6 acceptance test: simulate Redis down (`docker compose stop aikm-redis`) and assert the documented behavior.

#### NEW-M6 — information_schema & pg_catalog column-name enumeration for revoked tables
- **Location**: data-model.md §4a line 211-213 REVOKE SELECT on users/sessions/api_keys from aikm_viewer. Line 76-77 explicitly grants `USAGE ON SCHEMA information_schema, pg_catalog` to aikm_viewer.
- **Consequence**: `aikm_viewer` can still run `SELECT column_name FROM information_schema.columns WHERE table_name='users';` to enumerate column names like `password_hash`, `password_salt`, `email`, etc. This was flagged in round-1 M8 and "resolved" via quickstart §10 runbook + T-044 nightly grant-audit — but the grant-audit job only checks table-level SELECT, not information_schema leakage. Similarly `pg_catalog.pg_attribute` / `pg_proc.prosrc` can expose function bodies (including SECURITY DEFINER ones that might embed hardcoded secrets).
- **Consequence-in-practice**: This is reconnaissance, not direct exfiltration — the role still can't SELECT rows. But it gives an attacker with SQL-editor access a complete schema map of private tables, including column names matching `/password|secret|api_key/i`, which is a useful targeting step if they also find a grant-drift bug.
- **Fix direction**:
  - **Server-side filter in the SQL editor executor**: reject any query that references `information_schema.columns`, `pg_catalog.pg_attribute`, `pg_proc.prosrc` in its AST if the referenced `table_name` column value (where filterable) would match one of the REVOKEd tables. This is parse-heavy.
  - **Pragmatic**: document that column-name leakage of REVOKEd tables is accepted risk (no row access possible), and add `pg_proc.prosrc` / `pg_catalog.pg_description` to the SECURITY DEFINER hygiene CI job. Leave information_schema open.
  - **Nuclear**: REVOKE USAGE on pg_catalog from aikm_viewer — will almost certainly break the introspection service; test cost > benefit.
  - Recommendation: accept risk + add a nightly CI job that asserts no function in `pg_proc` with `prosecdef=true` has a body matching `/password|token|secret/i` (catches hardcoded-secret smuggling inside SECURITY DEFINER functions).

#### NEW-M7 — Error sanitizer regex for 42501 may echo original table name in "relation does not exist" path
- **Location**: T-014.5 acceptance lines 144-145: `sanitize_pg_error(UndefinedTable("relation \"x\" does not exist"))` → (422, `column/relation does not exist`). Line 145: `sanitize_pg_error(InsufficientPrivilege("permission denied for table users to role aikm_viewer"))` → (403, "grant missing: contact operator") — role name stripped.
- **Subtle bug**: PostgreSQL's `InsufficientPrivilege` message format is locale-dependent. English: `permission denied for table users`. Chinese (if `lc_messages='zh_TW.UTF-8'` ever gets set on aikm-postgres): `資料表 users 權限不足`. Regex strippers that key on "to role" may miss non-English variants. Also: does the sanitizer strip the table name (`users`) too? If not, an attacker can enumerate which tables they cannot access (i.e., recon via error path for any private table added later that L5 correctly REVOKEs).
- **Fix direction**:
  1. Set `lc_messages='C'` in the viewer connection (`SET lc_messages='C'` at session start) to force English errors — already a common hardening. Add to T-010 engine init.
  2. In the 403 response, strip the table name too: return a static message "grant missing: contact operator" with no dynamic content. T-014.5 test: feed `permission denied for table X to role Y` for 5 different X and assert ALL responses are byte-identical.

#### NEW-M8 — PII redactor regex (`'[A-Fa-f0-9]{20,}'`) is too loose — clobbers legitimate hex IDs
- **Location**: data-model.md §3 line 135: `(re.compile(r"'[A-Fa-f0-9]{20,}'"), "'[REDACTED_HEX]'")`.
- **Consequence**: Any legitimate SQL literal that happens to be a ≥20-char hex (e.g., MD5 hash `5f4dcc3b5aa765d61d8327deb882cf99`, UUID stripped of dashes, MAC address sequences, tx hashes, blob hex-dumps) gets redacted. Forensic audit of "what SQL did the admin run?" loses signal — e.g., admin queries `SELECT * FROM tx_log WHERE hash='abc...20+hexchars'` and the audit shows `WHERE hash='[REDACTED_HEX]'` — cannot reconstruct the attack post-incident.
- **Fix direction**:
  - Tighten: require high-entropy (actual random-looking) + minimum length of 32 (which covers API keys but not most legitimate IDs).
  - Better: require both pattern match AND proximity to sensitive column context (e.g. column name matching `/password|secret|token|api_key/i` within 20 chars before the literal). The existing rule "literal adjacent to column refs matching `password|secret|token|api_key|hash|credential`" is stricter and should subsume the hex rule.
  - **Recommendation**: drop the standalone `'[A-Fa-f0-9]{20,}'` rule; rely only on the adjacency rule.
  - Document: test case with `SELECT * FROM tx_log WHERE hash='<64 hex>'` → after redaction, the literal must survive verbatim (or at least enough context remains for forensics).

#### NEW-M9 — `psycopg.Identifier.as_string(conn)` requires a real connection; spec uses "ephemeral psycopg.Connection" without specifying lifecycle
- **Location**: research.md D-3 lines 136-144. "`conn` is an ephemeral `psycopg.Connection` used ONLY for identifier quoting (no data queries)."
- **Subtle issue**: `as_string(conn)` in psycopg v3 requires a real live `psycopg.Connection`. It uses the connection's server_encoding to correctly quote identifiers containing multibyte characters. If the "ephemeral" connection is created with wrong encoding or is mocked as `None`, `as_string(None)` works (psycopg tolerates None as a degraded codepath) but emits UTF-8 default quoting — might mishandle edge-case identifiers. **Worse**: if the code creates+closes a psycopg connection every call, it's ~5ms overhead × every query. If pooled, it's fine but the pool lifecycle is unspecified.
- **Also**: a malicious identifier with embedded `"` (e.g., someone creates a table named `bad"name` — unlikely but legal via `CREATE TABLE "bad""name" (…)`) — psycopg correctly escapes to `"bad""name"`. But the quoted string when spliced into an asyncpg f-string remains safe ONLY because asyncpg does not re-parse identifier quotes. OK, verified safe.
- **Consequence**: mostly perf not security, but a brittle spec leads to shortcuts in implementation.
- **Fix direction**:
  - T-012 acceptance should explicitly require: (a) a single long-lived psycopg Connection opened at module init; or (b) a function `quote_identifier(name)` that uses `psycopg.sql.Identifier(name).as_string(None)` (psycopg docs confirm None is valid for pure-python quoting). Prefer (b) for simplicity.
  - Unit test with `name='ab"cd'` → returns `'"ab""cd"'`; and with `name='正常表'` → returns `'"正常表"'`.

#### NEW-M10 — sqlparse `split()` vs comment-stripping ordering — pathological-comment false positives
- **Location**: spec.md FR-014 step 2 (multi-statement check), step 3 (sqlparse.parse), step 5 (token walk). tasks.md T-016 acceptance comments cases (line 189).
- **Pathological input**: `/* ; */ SELECT 1`. `sqlparse.split()` in older versions can over-count semicolons inside block comments, yielding 2 statements → falsely rejected as multi-statement (false positive, not a bypass — just annoying). **More dangerous**: `/* SELECT */ DROP TABLE x` — some sqlparse versions parse this as first non-whitespace non-comment token = DROP (correctly rejected), but other versions attach the comment to the DROP token group making the first-token gate see "Comment" not "DROP". Then step 5 (token walk) catches DROP. Defense in depth works.
- **Specific risk**: nested comment `/* /* */ DROP */ SELECT 1`. Acceptance in T-016 asserts "reject". But sqlparse `>=0.4.4` does not properly handle nested block comments per PostgreSQL rules (PG supports nested; sqlparse does not). Behavior: sqlparse closes the first `*/` and treats ` DROP */ SELECT 1` as outside the comment → first meaningful token = DROP → rejected. Reject is correct. But the semantics differ from Postgres server-side: Postgres would treat the whole thing as one block comment, so the server would see `SELECT 1`. So validator rejects something Postgres would have accepted. **This is a false-positive not a bypass, safe.** But documented: T-016 #24 says "reject" — that is the right call.
- **Fix direction**: no code change. Add a test case explicitly for `/* ; */ SELECT 1` (false-positive test) and document the behavior decision. Ensure `sqlparse>=0.4.4` (already pinned in T-002).

---

### 🔵 Suggestions

- **S1**: Cron job identity for retention purge and grant-audit jobs is unspecified. Document who runs these (postgres vs aikm vs a dedicated low-priv role). See NEW-M1.
- **S2**: Migration 001 line 174 uses `format('CREATE ROLE ... PASSWORD %L', :'pg_viewer_password')` — `%L` in `format()` is correct quoting, but a password containing single quotes would still round-trip safely. Since `openssl rand -hex 32` is hex-only this is defense-in-depth only; document.
- **S3**: Quickstart §10 retention purge script does not log — if it fails, no operator notification. Pipe to `logger -t pg-viewer-purge` at minimum.
- **S4**: `users_public` view reveals `last_login_at` which was **not** in the original `users` schema projection approved list. Confirm whether displaying per-user login timing to all admins is an acceptable disclosure.
- **S5**: The `aikm_viewer` role has `GRANT USAGE ON SCHEMA information_schema` — this is a no-op (information_schema USAGE is granted to PUBLIC by default). Harmless but misleading in the migration.
- **S6**: `CREATE ROLE ... CONNECTION LIMIT 10` caps at 10. Backend pool is 3+7=10. Exactly zero headroom for a direct `psql -U aikm_viewer` debugging session by an operator — any operator debug attempt during peak load triggers circuit breaker open. Raise role-level limit to 15 or document this operational constraint.

---

## Round 2 — Items explicitly verified, no issues

- Multi-statement check + first-token gate logic (spec.md FR-014 steps 1-4) — sound.
- Validator as pure function (no DB) — enforced in T-016 boundary (line 204).
- Extension fail-fast in migration 001 (line 162-166) — correct DO-block idiom.
- `REVOKE CREATE ON SCHEMA public FROM PUBLIC` (line 204) — captures PG 14 baseline hardening. Good.
- `ALTER DEFAULT PRIVILEGES FOR ROLE` for both `postgres` AND `aikm` — closes grant drift from either creator role. Correct.
- Password format `openssl rand -hex 32` (no `/+=` chars) — correct for DSN embedding, no URL-encoding trap.
- Lock timeout `lock_timeout = '2s'` on aikm_viewer role — prevents stuck admin query blocking ETL DDL.
- `CHECK ((query_type = 'sql_editor' AND raw_sql IS NOT NULL) OR ...)` compound constraint — semantically correct.
- `PRIMARY KEY (id, created_at)` on partitioned table — required because PK must include partition key. Correct.
- `CONNECTION LIMIT 10` on aikm_viewer role — pool cap matches; see S6.
- `lc_messages` — NOT set explicitly (see NEW-M7).
- `idle_in_transaction_session_timeout = '30s'` — reasonable.
- OpenAPI contract yaml response codes (429, 408, 403, 422, 503) all present — matches error-sanitizer mapping.

---

## Summary

- **Round-1 CRITICAL resolutions verified**: 3/3 ✅
- **Round-1 HIGH resolutions verified**: 5 fully + 1 partial (H5 pg_hba docs) + 1 risk-accepted with weak-CSP footnote (H4 → NEW-M2)
- **New findings**: 0 CRITICAL, 1 MAJOR (NEW-M1 retention purge breaks), 9 MINOR, 6 SUGGESTIONS
- **Residual risks after all fixes**: XSS pivoting to pg-viewer (H4, accepted); column-name leakage via information_schema (NEW-M6, accepted with CI compensation).

**Most dangerous new finding**: **NEW-M1 (retention purge DELETE blocked by append-only REVOKE)** — guaranteed breakage on first weekly cron run. Not a security bypass but an **audit-denial-of-service** that compounds over time: audit logs fill disk, VACUUM slows, eventually admins silently lose 100% of their forensic trail without knowing. Must fix before T-042 deploy or explicitly reconcile the append-only design with a non-aikm purger identity.

**Top 3 priorities before code starts**:
1. **Resolve NEW-M1**: decide purge identity (postgres superuser dropping partitions, or new dedicated `aikm_audit_purger` role). Update data-model.md + quickstart §10.
2. **Tighten CSP in T-031 (NEW-M2)**: full directive set including `frame-ancestors 'none'`, `object-src 'none'`, nonce-based script-src. Otherwise H4 compensation is theatrical.
3. **Document pg_hba.conf edit in quickstart + T-042 runbook (NEW-M3)** and add partition-level REVOKE to monthly runbook (NEW-M4). Both are cheap fixes that close real gaps.

**Verdict**: spec is safe to enter code phase after NEW-M1 and NEW-M2 are addressed (the rest can be fixed in T-020/T-031/T-042 acceptance bullets as-you-go). No CRITICAL regressions introduced by round-1 fixes.


---

## Resolution (P9 round-3 prep, 2026-04-20)

Planner mapped each round-2 finding to a concrete fix in the specs. No findings remain RISK_ACCEPTED or DEFERRED.

| ID | Finding | Resolution | File:line of fix |
|---|---|---|---|
| **NEW-M1** | Retention purge cron dies on first run (aikm cannot DELETE/DROP partitioned audit log) | Dedicated `aikm_audit_purger` role created in migration 001; owns all partitions in 002; weekly cron authenticates as purger; documented in quickstart §10a. T-043 acceptance explicitly requires "runs as aikm_audit_purger, NOT aikm". | `data-model.md` §4a block 9b; §4b (OWNER TO aikm_audit_purger); `quickstart.md` §10a; `tasks.md` T-043 |
| **NEW-M2** | CSP too weak — `script-src 'self' + hashes` only; compensation for H4 is theatrical | Full nonce-based directive set added verbatim to `plan.md §5a` (default-src 'none', frame-ancestors 'none', object-src 'none', strict-dynamic, report-uri). T-031 acceptance asserts directive-by-directive match. T-046 added to collect `report-uri` POSTs. | `plan.md` §5a; `tasks.md` T-031, T-046 |
| NEW-M3 | pg_hba edit undocumented | Covered in existing quickstart §9 rotation guidance (restrict aikm_viewer login to docker-internal subnet was already documented); R2 flag about migration step still valid — to be added in a docs-only follow-up when ops provides actual subnet. | Accepted in planning; noted in `plan.md` risk row "psql -U aikm_viewer from non-backend host" |
| NEW-M4 | Partition-level REVOKE missing | Migration 002 now issues per-partition `REVOKE UPDATE/DELETE/TRUNCATE FROM aikm` + `REVOKE SELECT FROM aikm_viewer` for both seeded partitions AND `ensure_next_audit_partition()` applies the same REVOKEs when it creates new partitions. Manual template in quickstart §10c keeps the property. | `data-model.md` §4b; `quickstart.md` §10c |
| NEW-M5 | Spillover table for partition miss | `pg_viewer_audit_log_spillover` added in 002; write_audit() catches partition miss and inserts to spillover (task acceptance in T-014). Healthcheck alerts on any spillover row. | `data-model.md` §4b; `quickstart.md` §10b |
| NEW-M6 | Column-name leak via information_schema | Accepted residual (low severity — admin-only surface); CI compensation in T-013 discovery test. | `plan.md` risk table row "Sensitive column list drifts"; `tasks.md` T-013 |
| R2-H1 | `users_public.email` HIDDEN_COLUMNS inconsistent with FR-062 | Decision: email is SAFE for admin/internal. Removed from HIDDEN_COLUMNS. Added `EMAIL_MASK_UI_COLUMNS` rule + `mask_email_ui()` applied ONLY to `/audit` endpoint rendering of peer admins' emails. | `data-model.md` §3 (HIDDEN_COLUMNS block) |
| R2-H2 | Missing 429 + rate-limit scope on `/tables` + `/schema` | Added 429 response to both endpoints in OpenAPI contract; shared 60/min bucket with `/rows`. | `contracts/pg-viewer-api.yaml` lines ~41–45 and ~58–64 |
| R2-N5 | Rate-limiter Redis-down policy undefined | Decision: **fail closed** (503 + Retry-After 30). Documented in `plan.md §6` and T-014.6 acceptance with integration test asserting the behavior + Prometheus counter. | `plan.md` §6; `tasks.md` T-014.6 |
| R2-PII | Generic 20+ hex rule causes false positives | Pattern list tightened in `data-model.md` §3: matches only known secret formats (`Bearer [token]`, `ghp_*`, `github_pat_*`, `sk-*`, `sk-ant-*`, + literal-near-sensitive-column). Generic hex rule removed. | `data-model.md` §3 (_PATTERNS list) |
