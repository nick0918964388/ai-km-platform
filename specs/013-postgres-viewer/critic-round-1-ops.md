# Critic Round 1 — 013-postgres-viewer — OPS

**Reviewer angle**: deployment, migration, backward-compat, DB impact, operational runbook.
**Scope**: spec.md, research.md, plan.md, data-model.md, contracts/pg-viewer-api.yaml, tasks.md, quickstart.md.

## Verdict: CONDITIONAL_YES

Feature design is orthogonal to existing systems (good) and the defense-in-depth security model is solid. However, migration idempotency, role-grant drift, connection-pool contention, audit-log unboundedness, env/secret wiring, and the operator runbook all have concrete gaps that must be tightened before T-042 deploy on 192.168.1.11. Nothing here is a show-stopper conceptually — but the "deploy to prod via `git pull && docker exec psql`" path described in quickstart is fragile and will bite operationally.

## Resolution (appended by planner after round-1 review, 2026-04-20)

All CRITICAL and HIGH findings ADDRESSED. Migration split + grant drift audit + password rotation + retention purge fully wired.

### CRITICAL (3/3 ADDRESSED)
- **C1 Migration requires superuser but invoked as aikm**: ADDRESSED. Migration split into two files: `001_role_and_grants.sql` (runs as `postgres`) + `002_audit_table.sql` (runs as `aikm`). Pre-flight privilege check in quickstart §2a (`rolsuper` for postgres = t + `max_connections >= 200`). Both files idempotent (`ON_ERROR_STOP`, `CREATE TABLE IF NOT EXISTS`, `DO`-block role existence check). See data-model.md §4a/§4b, tasks.md T-003/T-042, quickstart.md §2.
- **C2 ALTER DEFAULT PRIVILEGES drift**: ADDRESSED. Migration 001 now runs `ALTER DEFAULT PRIVILEGES FOR ROLE postgres` AND `FOR ROLE aikm`. Browse endpoint catches 42501 and surfaces `grant_missing=true` on the table summary (post-critic C2 ops) — T-011 + T-020 acceptance. Nightly CI grant-audit job added in T-044. `TableSummary.grant_missing` field added to contracts yaml.
- **C3 SET LOCAL autocommit no-op**: ADDRESSED via three-layer belt-and-suspenders: (a) role-level `ALTER ROLE aikm_viewer SET statement_timeout='10s'` + `idle_in_transaction_session_timeout='30s'` + `lock_timeout='2s'` in migration 001; (b) asyncpg `command_timeout=10` on viewer engine; (c) per-tx `SET LOCAL` inside `engine.begin()`. Integration test `SELECT pg_sleep(30)` returns 408 in ≤ 11s (elevated from T-041 PoC to T-010 integration test). spec.md FR-012, research.md D-4, tasks.md T-010.

### HIGH (4/4 ADDRESSED)
- **H1 audit log unbounded growth**: ADDRESSED. `PG_VIEWER_AUDIT_RETENTION_DAYS=180` (env configurable). Table partitioned monthly by `created_at`. Weekly retention purge via host crontab — T-043 + quickstart §10. FR-052 added.
- **H2 pool sizing too tight**: ADDRESSED. Raised to `pool_size=3, max_overflow=7, pool_recycle=1800` (max 10 conn). Budget check `max_connections >= 200` pre-flight. research.md D-2 + tasks.md T-010.
- **H3 password rotation runbook**: ADDRESSED. Password generation changed to `openssl rand -hex 32` (URL-safe; no base64). Rotation runbook added as quickstart §9 with 4-step procedure. `CONNECTION LIMIT 10` on role.
- **H4 CI/CD integration gap**: ADDRESSED. T-044 adds `.github/workflows/pg-viewer-grant-audit.yml` (nightly) and updates `main-deploy.yml` to auto-apply migrations + post-deploy smoke. `PG_VIEWER_PASSWORD` stored on host `/etc/aikm/.env` (NOT in GH secrets) — `PG_VIEWER_CI_ADMIN_JWT` is the only GH secret needed.

### MEDIUM (6/6 ADDRESSED)
- **M1 AccessShareLock contention during GRANT**: ADDRESSED. Quickstart §2a + T-042 mandate `docker compose stop aikm-maximo-extractor` before migration. Migration 001 also sets `lock_timeout='5s'`.
- **M2 REVOKE ALL ... sequence missing**: ADDRESSED. Migration 001 now aligned with data-model §2; explicit `REVOKE CREATE ON SCHEMA public FROM PUBLIC` added for PG 14 safety.
- **M3 `\copy` in denylist misleading**: ADDRESSED. Dropped from keyword denylist (it's a client meta-command — will fail parse). Documented in T-016 acceptance test case.
- **M4 408 vs 422 error mapping**: ADDRESSED. T-022 + T-014.5 map SQLSTATE `57014` → 408, `42P01/42703` → 422, `42501` → 403 "grant missing". T-020 acceptance references the mapping.
- **M5 feature flag SSR**: ADDRESSED. `NEXT_PUBLIC_PG_VIEWER_ENABLED` env; T-031 acceptance requires SSR banner when false or API 404.
- **M6 observability**: ADDRESSED. T-045 new task emits `pg_viewer_request_duration_seconds{endpoint, status}` Prometheus histogram. NFR-006 added.

### LOW / NITS
- **L1** `ON_ERROR_STOP=1` in quickstart: ADDRESSED (§2b/§2c).
- **L2** port collision: verified none.
- **L3** backup of audit log: documented as subject to existing backup policy.
- **L4** redaction substrings widened: ADDRESSED (FR-061 pattern).
- **L5** CSV export of SQL-editor result: ADDRESSED as explicit v1.1 backlog entry (memory/project_pg_viewer_backlog.md referenced in T-036 boundary).
- **L6** sqlparse CVE / perf: accepted (`PG_VIEWER_SQL_MAX_LEN=8000` bounds pathological input).
- **L7** drop-and-recreate rollback warning: ADDRESSED in quickstart §8 with explicit "PERMANENT REMOVAL — LOSES AUDIT HISTORY" banner.
- **L8** aikm_viewer mid-query disabled: ADDRESSED as new edge case in spec.md.


---

## CRITICAL

### C1. Migration requires superuser privileges but is invoked as role `aikm` — `CREATE ROLE` will fail unless `aikm` is superuser or has `CREATEROLE`
- **Where**: `quickstart.md:36-37` (`docker exec -i aikm-postgres psql -U aikm -d aikm -v pg_viewer_password=...`) + `data-model.md:167-172` (DO block `CREATE ROLE aikm_viewer`) + `tasks.md:318` (T-042 deploy command).
- **Operational risk**: On first deploy, migration will raise `ERROR: permission denied to create role`. Deploy pipeline fails mid-way after `pg_viewer_audit_log` is already created, leaving DB in half-applied state. Worse, because `DO $$ ... EXECUTE format(...) $$` raises inside a `BEGIN/COMMIT` block (`data-model.md:132,180`), the table creation rolls back too — but the next run is not checked, so operator won't know which half succeeded.
- **Fix**:
  1. Document that `aikm` role must have `CREATEROLE` (and `CREATEROLE INHERIT` on PG 16+ to grant it membership/login attributes). Either run `ALTER ROLE aikm CREATEROLE;` as superuser once, or run the migration's role-creation block as `postgres` superuser inside the container.
  2. Split migration into two files: `001_role.sql` (run as postgres superuser, one-off) and `002_audit_table_and_grants.sql` (run as `aikm`, idempotent, re-runnable on every deploy).
  3. Add a pre-check in T-042 runbook: `docker exec aikm-postgres psql -U postgres -d aikm -tAc "SELECT rolcreaterole FROM pg_roles WHERE rolname='aikm'"` — if false, abort before attempting migration.

### C2. `ALTER DEFAULT PRIVILEGES` is set for role `aikm` — but existing + future tables may be created by other roles (ETL scripts, maximo ingester), producing a silent grant gap
- **Where**: `data-model.md:73,176` (`ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO aikm_viewer;`) and `research.md:82`.
- **Operational risk**: `ALTER DEFAULT PRIVILEGES` only applies to tables created **by the role that runs the ALTER** (i.e. the role whose session ran it, which will be `aikm` since the migration runs as `-U aikm`). Any table created later by `postgres` superuser, by a different app role, or by another migration engineer using `-U postgres` will NOT automatically grant SELECT to `aikm_viewer`. Admin opens `/admin/pg-viewer`, clicks the new table → 42501 `permission denied`. They'll blame the viewer, not the missing grant.
- **Fix**:
  1. Run `ALTER DEFAULT PRIVILEGES` **for every role that can create tables in `public`**. At minimum: `ALTER DEFAULT PRIVILEGES FOR ROLE aikm IN SCHEMA public GRANT SELECT ON TABLES TO aikm_viewer;` AND `ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT SELECT ON TABLES TO aikm_viewer;` (and document that any new ingester role must do the same).
  2. Add a nightly CI check (hinted at in `plan.md:140`) that enumerates tables in `public` where `aikm_viewer` lacks SELECT; alert if non-zero. This is the only reliable belt-and-suspenders.
  3. Add a hook in T-011 introspection: if `information_schema.tables` lists a table that `has_table_privilege('aikm_viewer', ..., 'SELECT')` is false, surface a clear "grant missing" status badge in the UI rather than a raw 42501.

### C3. `SET LOCAL statement_timeout` is a no-op when SQLAlchemy/asyncpg runs in autocommit mode — the 10s timeout contract (FR-012, FR-015, L4) may silently not apply
- **Where**: `plan.md:42` ("BEGIN; SET LOCAL statement_timeout = '10s';"), `research.md:112-114`, `spec.md:FR-012`, `tasks.md:148` (T-020 acceptance `Statement timeout enforced`).
- **Operational risk**: `SET LOCAL` only affects the current transaction. If the engine session is configured with `isolation_level="AUTOCOMMIT"` or if a bare `async with engine.connect()` is used (not `async with engine.begin()`), each `execute()` is its own implicit txn — `SET LOCAL` applied before the real query is flushed as a separate transaction and has no effect on the subsequent query. Then `SELECT pg_sleep(30)` runs to completion, occupies one of the 2+3=5 pool connections for 30s, and if 3 such queries come in concurrently the pool is exhausted → 503 (fine) or request hangs (bad). FR-012 contract is silently violated.
- **Fix**:
  1. Explicit unit test in T-010/T-020 acceptance: assert that `POST /sql` with `SELECT pg_sleep(30)` returns 408 in ≤ 11s. Currently only listed in T-041 PoC; elevate to T-010 integration test so a regression is caught at build time.
  2. Implementation note in T-010: enforce `async with engine.begin() as conn: await conn.execute(text("SET LOCAL ..."))` pattern — never `engine.connect()` and never `AUTOCOMMIT`. Alternative: set `statement_timeout` at the role level (`ALTER ROLE aikm_viewer SET statement_timeout = '10s'`) — this applies to every session regardless of transaction mode and is strictly safer for defense in depth. **Strongly recommend adding this to the migration**.
  3. Also set `idle_in_transaction_session_timeout = '30s'` and `lock_timeout = '2s'` at role level to prevent a hung transaction from holding locks against ETL.

---

## HIGH

### H1. `pg_viewer_audit_log` has no retention policy — unbounded growth on heavy SQL-editor use
- **Where**: `data-model.md:50` ("Retention: No TTL in v1. Add manual purge procedure in v1.1.") and spec has no §FR on retention.
- **Operational risk**: Each browse action writes one row. Each SQL-editor execution writes one row with up to 8KB `raw_sql` + full `filters_json`. With 5 concurrent admins and typical debugging sessions, easily 500-2000 rows/day. After 12 months: ~500K rows (~4GB). Since there are no partitions, `VACUUM` costs grow linearly. More urgently: the partial index `idx_pgva_sql_editor` on `(user_id, created_at DESC) WHERE query_type='sql_editor'` becomes a hot spot. pg_dump backup size inflates. No cleanup procedure documented.
- **Fix**:
  1. Add FR-052: retention = 180 days default, configurable via env `PG_VIEWER_AUDIT_RETENTION_DAYS`.
  2. Ship a purge cron as part of T-003 migration: either a pg_cron job (`aikm-postgres` doesn't have pg_cron by default — add extension or use external cron) or a documented `DELETE FROM pg_viewer_audit_log WHERE created_at < NOW() - INTERVAL '180 days'` snippet invokable via `docker exec`.
  3. Add to tasks.md a T-043 (operational) to document retention + add `DELETE` to a weekly cron on the host.

### H2. Connection-pool sizing (pool_size=2, max_overflow=3 — max 5) is too tight and shares port/creds risk with main pool
- **Where**: `research.md:94-98` (`pool_size=2, max_overflow=3`) and `tasks.md:61` (T-010 `Must NOT pool > 5 connections`).
- **Operational risk**:
  (a) Max 5 concurrent queries. `plan.md:19` says "Concurrent admins ≤ 5" — budget is exactly at cap with zero headroom. One admin exports 1000-row CSV (streaming, ~2s under load) → 4 slots left → a second admin runs schema introspect on a big table → 3 slots → a filter page load issues `SELECT COUNT` + `SELECT rows` → 2 slots. Easy to exhaust, and the symptom will be 503 or long wait on `pool_pre_ping`.
  (b) No mention of `pool_recycle` — long-lived connections in a containerized environment frequently hit `server closed connection` after idle periods. Without `pool_recycle=1800`, admins will see sporadic errors.
  (c) The main pool isn't protected — if `aikm_viewer` pool grows above its cap due to a bug, nothing prevents it from taking connections the main app needs; but since it's a separate engine, the two share the Postgres `max_connections` budget. `aikm-postgres` default is 100. Current services (main backend + ETL + migrations + admin tools) already consume 30-50. Need explicit `max_connections` accounting.
- **Fix**:
  1. Raise to `pool_size=3, max_overflow=7` (max 10) with `pool_recycle=1800, pool_pre_ping=True`.
  2. Document total PG connection budget in plan.md and verify `aikm-postgres` has `max_connections ≥ 200` via `docker exec aikm-postgres psql -U postgres -c "SHOW max_connections"`.
  3. Also document `idle_in_transaction_session_timeout` at the role level (see C3 fix #2) so a stuck admin query doesn't hold a pool slot.

### H3. No env-var rotation runbook for `PG_VIEWER_PASSWORD` — stored in `.env`, referenced by migration AND runtime
- **Where**: `data-model.md:189`, `quickstart.md:36,49`, `plan.md:16` (env vars list).
- **Operational risk**: The password is generated once by `openssl rand -base64 32` in the migration invocation and must match between (a) Postgres role, (b) `.env` on 192.168.1.11, (c) container runtime via `PG_VIEWER_DATABASE_URL`. If any leak or rotation is needed:
  - Changing it requires `ALTER ROLE aikm_viewer PASSWORD 'new'` AND updating `.env` AND restarting backend — no documented order. Race: if you update `.env` first and restart, backend fails to connect; if you ALTER first, existing in-flight queries continue (Postgres doesn't drop live connections on password change, which is fine) but new ones fail. OK, but not documented.
  - No warning that `base64` output contains `/` `+` `=` which must be URL-encoded if embedded in `PG_VIEWER_DATABASE_URL` (asyncpg will choke on bare `/` in password position). The runbook silently ignores this → deploy appears to succeed but backend fails to connect with opaque "invalid URL" at first request.
- **Fix**:
  1. Add a password-generation step that avoids URL-unsafe chars: `openssl rand -hex 32` (64 hex chars, always URL-safe).
  2. Add runbook section in quickstart.md §8 or new §9 "Rotating aikm_viewer password": 4-step procedure (ALTER ROLE → update .env → `docker compose up -d backend` → smoke test `curl /api/pg-viewer/tables`).
  3. Ensure secret is NOT accidentally committed — `.env` in .gitignore already; also add `.env.example` entry with placeholder `PG_VIEWER_PASSWORD=changeme`.

### H4. CI/CD integration gap: self-hosted runner on 192.168.1.11 needs new secret but no `main-deploy.yml` changes described
- **Where**: `CLAUDE.md` mentions `main-deploy.yml` does rolling deploy + health check. `tasks.md:316-323` (T-042) describes manual SSH + `git pull`. `spec.md` has no mention of updating CI workflow.
- **Operational risk**:
  (a) Deploy was originally described as manual SSH — diverges from the CLAUDE.md rule "push main → 自動部署". If operator follows manual path, main-deploy.yml fires anyway in parallel and may race with the migration step.
  (b) `main-deploy.yml` health-check script probably does `curl /api/health` — it will not catch pg-viewer-specific failures. Migration failure wouldn't block the rollout (since migration is run by hand in T-042, not by the workflow). Risk: backend restarts, `PG_VIEWER_DATABASE_URL` is unset → feature silently 404s.
  (c) No secret management for `PG_VIEWER_PASSWORD` in GitHub repo secrets — the self-hosted runner needs it, or the `.env` on disk needs it, unclear which.
- **Fix**:
  1. Add T-044: update `main-deploy.yml` to (a) check for pending migrations, (b) apply `backend/scripts/pg_viewer_migrate_001.sql` idempotently before `docker compose up`, (c) include a post-deploy smoke `curl` of `/api/pg-viewer/tables` with a test admin token (stored in GH secret).
  2. Document that `PG_VIEWER_PASSWORD` lives in `/etc/aikm/.env` on 192.168.1.11, is sourced by docker compose via `env_file:`, and is NOT stored in GH secrets (runner reads from host).
  3. Ensure `ci-test.yml` doesn't need `PG_VIEWER_PASSWORD` — tests should use an ephemeral PG container with its own fixture.

---

## MEDIUM

### M1. `REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES` + `GRANT SELECT ON ALL TABLES` takes AccessShare locks on every table — may briefly block ETL on large Maximo tables
- **Where**: `data-model.md:175-178`.
- **Operational risk**: `GRANT SELECT ON ALL TABLES IN SCHEMA public` iterates every table and takes an AccessShareLock on each. On a DB with 500+ tables including `maximo_mxwo` (10,742 rows) and `maximo_zz_maxattribute` (45,625 rows) and presumably more, this completes in seconds — but if run concurrently with an in-flight ETL `COPY` that holds AccessExclusive on one of those tables, GRANT blocks, blocking every subsequent GRANT in the set. Worst case: 30-60s freeze. Memory says ETL runs on `aikm-maximo-extractor` (port 8080) — could be active during deploy.
- **Fix**:
  1. Add to quickstart §2: "Run migration only when ETL is paused: `docker compose stop aikm-maximo-extractor` first, then restart after migration succeeds."
  2. OR: add `lock_timeout = '5s'` at the start of the migration so a blocking lock abort the migration cleanly rather than hanging prod for minutes.

### M2. `REVOKE ALL ON DATABASE aikm FROM aikm_viewer; GRANT CONNECT, TEMPORARY; REVOKE TEMPORARY` sequence in `data-model.md:83-86` is actually missing from the migration stub at lines 174-178
- **Where**: `data-model.md:83-86` lists the authoritative revokes; `data-model.md:167-180` shows the actual migration SQL, which is missing them.
- **Operational risk**: Migration as written doesn't revoke default `PUBLIC` grants. PG 14- defaults give every role `CREATE ON SCHEMA public`. Even with `REVOKE CREATE ON SCHEMA public FROM aikm_viewer` (line 178), `CREATE` may still be available via `PUBLIC` role inheritance (since `aikm_viewer` inherits PUBLIC grants). Need `REVOKE CREATE ON SCHEMA public FROM PUBLIC` if running on PG < 15 — but doing that changes a global default and could break other roles.
- **Fix**:
  1. Verify Postgres major version of `aikm-postgres` container (docker image tag in docker-compose.yml). If < 15, revoke from `aikm_viewer` directly doesn't help — must target `PUBLIC`. If 15+, safe.
  2. Add an assertion in the migration's verification block: `SELECT has_schema_privilege('aikm_viewer', 'public', 'CREATE') = false;` — already listed, good.
  3. Align `data-model.md:83-86` with `data-model.md:167-180` — they're authoritative in different directions. Pick one.

### M3. `\copy` in the forbidden-keyword list is a client meta-command, not a SQL keyword — sqlparse tokenization won't see it as `Keyword`
- **Where**: `research.md:176` and `spec.md:134` and `plan.md:65` all list `\copy` in the forbidden set.
- **Operational risk**: `\copy` is a psql client directive, never reaches the server. An attacker sending `\copy (SELECT * FROM users) TO '/tmp/steal.csv'` through `POST /sql` will be rejected by sqlparse as a syntax error (it's not valid SQL), not as a "forbidden keyword" — outcome is correct but the listed control is misleading. More importantly, including it in the denylist creates false confidence that the layer handles client meta-commands, when actually it can't differentiate them — a well-formed payload might slip through as a plain parse error with different HTTP status. Audit row will show `status='error'` not `forbidden`.
- **Fix**: Remove `\copy` from the forbidden keyword list in spec/plan/research. Replace with a note: "Client meta-commands like `\copy` are not valid SQL and will fail parse; not a dedicated layer." Keep `COPY` (server-side SQL command).

### M4. SQL editor endpoint returns 408 on timeout (contract) but Postgres error for statement_timeout surfaces as `QueryCanceledError` with SQLSTATE `57014` — need explicit mapping
- **Where**: `contracts/pg-viewer-api.yaml:192-196`, `spec.md:93` ("server returns 408"), `tasks.md:169`.
- **Operational risk**: No task explicitly spec's the error-to-HTTP mapping. A bare `except Exception` in the endpoint will leak the string "canceling statement due to statement timeout" — OK — but distinguishing 408 (timeout) vs 422 (execution error) vs 503 (connection failure) needs SQLSTATE-aware code. If the engineer implementing T-022 uses a broad try/except, all of them will coalesce to 500.
- **Fix**: Add to T-022 acceptance: "Timeout maps to 408 via SQLSTATE `57014` check. Other errors map to 422. Connection refused / pool exhaustion maps to 503."

### M5. Feature flag `PG_VIEWER_ENABLED=false` returns 404 from API but frontend route still rendered — no SSR guard described
- **Where**: `plan.md:123` ("`/admin/pg-viewer` route shows 'Disabled' banner if env flag off (server-rendered check)"), `tasks.md:147` (T-020 404 check), but no FR/task for frontend SSR flag read.
- **Operational risk**: If `PG_VIEWER_ENABLED=false` is toggled urgently (incident rollback), admins hitting `/admin/pg-viewer` see a blank Next.js page or JS errors from failed `/api/pg-viewer/tables` call — poor UX during a live incident.
- **Fix**: Add to T-031 acceptance: "If env `NEXT_PUBLIC_PG_VIEWER_ENABLED=false` or API returns 404 on `/tables`, page renders a clear 'Feature temporarily disabled' banner." Document the env in `.env.example`.

### M6. No observability beyond logs — NFR-001/NFR-002 have no measurement plan
- **Where**: `spec.md:169-170` (NFR-001 `p95 < 500ms`, NFR-002 `p95 < 2s`), `plan.md:127-132` (Observability: "Metrics: TBD").
- **Operational risk**: SLOs are asserted but no Prometheus metric, no grafana dashboard, no alert defined. First time anyone measures p95 will be when a user complains.
- **Fix**: Add T-045: emit prometheus histogram `pg_viewer_request_duration_seconds{endpoint, status}` from the router. Reuse existing metrics infra (memory mentions observability patterns exist via circuit_breaker). If no infra, at minimum log `ms` at INFO level so p95 can be reconstructed from logs.

---

## LOW / NITS

### L1. `quickstart.md:36` migration invocation uses `psql -v pg_viewer_password=...` but `data-model.md:170` uses `:'pg_viewer_password'` — backslash quoting nuance
- Migration is quoted as `%L` via `format()` in the DO block — good. Just document that the `-v` variable MUST be set or `psql` will prompt interactively and hang a CI run. Add `-v ON_ERROR_STOP=1` so failures abort the script.

### L2. No mention of `192.168.1.11` port collision with Drone CI (8090) / Maximo Liberty (9080/9443)
- **Where**: CLAUDE.md coexistence note; checked in this review.
- **Assessment**: no new ports used (reuses 8000 backend, 3000 frontend). **No collision. Checked, no issue.**

### L3. Backup implications of `pg_viewer_audit_log`
- Default `pg_dump` of the `aikm` DB will include this table. `raw_sql` may contain sensitive data an admin typed (e.g. pasted row with PII into a WHERE clause). Backup encryption at rest already handled by existing infra, presumably; worth a one-line explicit mention in plan.md that audit log is backed up and subject to same retention/encryption as main DB. **Not a blocker, document only.**

### L4. `system_settings` redaction substring list at `data-model.md:118` omits the substring `key` — but memory says admin audit UI already exists and has precedent
- Minor: substring list is `["secret", "token", "api_key", "password"]`. Common env vars also include `"credential"`, `"private_key"`, `"jwt_secret"`. Consider widening.

### L5. `exportCsvUrl` in T-030 — CSV export of SQL-editor result is OUT OF SCOPE per `tasks.md:262`, good — but admin workflow will ask for it day 1
- Predict: within 2 weeks of launch, admin will request "save SQL result as CSV". Plan response: direct them to use the table browser path with filters, or add `POST /api/pg-viewer/sql/export.csv` in v1.1. Put in backlog.

### L6. `sqlparse ≥ 0.4.4` is a new backend dep — check container image size + `pip-audit` for known CVEs
- Docs say "battle-tested in Airflow / Superset" — true, but sqlparse has had historical issues with pathological input causing O(n²) or O(n³) lex performance. With `PG_VIEWER_SQL_MAX_LEN=8000`, acceptable. No action needed, checked.

### L7. Drop-and-recreate rollback in `quickstart.md:231-237` will lose audit history — add warning
- The "nuclear option" literally says "DROP TABLE pg_viewer_audit_log". For an incident rollback this is acceptable; for an operational "let me just temporarily disable this" it destroys forensic history. Add a comment: "This loses audit history forever — prefer `PG_VIEWER_ENABLED=false` first."

### L8. Spec missing explicit rule on what happens when `aikm_viewer` session is revoked mid-query
- **Where**: spec.md edge cases at line 111 handle role revoked mid-session for JWT side (good). No case for PG role being disabled while a viewer connection pool still has live sessions to it. Likely harmless (Postgres holds the connection; next reconnect fails). Document in plan §Risks.

---

## Summary of operational risk

**Overall risk**: **Medium**. Design is correct; operational edges around migration mechanics, grant drift, and timeout semantics are the main sources of potential prod incidents. All findings have concrete fixes.

**Top 2 ops risks**:
1. **Migration permission failure on first deploy** (C1) — `CREATE ROLE` needs superuser or `CREATEROLE`; current runbook will half-apply and leave ops confused. Split migration into two files and verify privileges pre-deploy.
2. **Grant drift from future tables** (C2) — `ALTER DEFAULT PRIVILEGES` is per-creator-role; any table made by a different role silently lacks SELECT to `aikm_viewer`. Add nightly grant-audit check + extend ALTER to cover all creator roles.

**Secondary cluster**: `SET LOCAL statement_timeout` vs autocommit (C3), pool sizing (H2), audit-log unbounded growth (H1), and password rotation runbook (H3) are all fixable pre-T-042.

**Blockers for T-042 (prod deploy)**: C1, C2, C3, H4 must have resolutions in place. H1, H2, H3 can be punted to v1.1 but must be filed as explicit backlog tasks, not left informal.
