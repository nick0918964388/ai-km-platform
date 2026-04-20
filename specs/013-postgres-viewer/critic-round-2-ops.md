# Critic Round 2 — 013-postgres-viewer — OPS

**Reviewer angle**: verify round-1 ops resolutions + fresh ops angles (partitioning, rollback, pool budget, env wiring, cron alerts, metrics labels, backup, change freeze, grant drift).
**Scope**: spec.md, plan.md, research.md, data-model.md, quickstart.md, tasks.md, contracts yaml, critic-round-1-ops.md resolution block.
**Verification date**: 2026-04-20.

## Verdict: CONDITIONAL_YES (stronger than round-1)

All round-1 CRITICAL + HIGH are substantively addressed in the design docs. Three new ops findings need attention before T-042. None are blockers but H-N2 (partition creation cron) is a latent time-bomb and MUST be wired before the first month-boundary crossing after deploy.

---

## Round-1 CRITICAL verification

| ID | Title | Status | Evidence |
|---|---|---|---|
| C1 | Migration split (superuser vs aikm) | **VERIFIED** | `data-model.md:149-322` ships `001_role_and_grants.sql` (run as `postgres`) + `002_audit_table.sql` (run as `aikm`). `001` uses `DO $$ IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aikm_viewer')` (PG-correct idempotent role creation). `002` uses `CREATE TABLE IF NOT EXISTS` throughout. Pre-flight check at `quickstart.md:32-54` explicitly asserts `rolsuper=t` for postgres AND `max_connections>=200`. `tasks.md:56-68` (T-003) + `tasks.md:423-440` (T-042) split the invocation. Both files begin with `\set ON_ERROR_STOP on`. No half-apply risk. |
| C2 | ALTER DEFAULT PRIVILEGES drift | **VERIFIED** | `data-model.md:193-198` enumerates both `FOR ROLE postgres` AND `FOR ROLE aikm`. Also `ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM aikm_viewer` (line 207) + same for aikm. Grant-drift catch added at router layer per `tasks.md:225` (browse returns 200 with `grant_missing=true` rather than raw 42501). Nightly grant-audit in `tasks.md:451-461` (T-044). |
| C3 | statement_timeout triple-layer | **VERIFIED** | Layer (a): `data-model.md:181-183` `ALTER ROLE aikm_viewer SET statement_timeout='10s'` + `idle_in_transaction_session_timeout='30s'` + `lock_timeout='2s'`. Layer (b): `tasks.md:75` engine `connect_args={"command_timeout":10}`. Layer (c): T-010 acceptance `async with engine.begin()` with `SET LOCAL`. Integration test elevated from PoC (T-041) to T-010 (`tasks.md:82`): `SELECT pg_sleep(30)` must return in ≤11s. Good. |

**Round-1 CRITICAL: 3/3 resolved.**

---

## Round-1 HIGH verification

| ID | Title | Status | Evidence |
|---|---|---|---|
| H1 | Audit log retention | **VERIFIED (with latent risk — see H-N2)** | `PG_VIEWER_AUDIT_RETENTION_DAYS=180` wired in `tasks.md:39`. Table partitioned BY RANGE (`created_at`) monthly per `data-model.md:272-278`. Weekly purge cron documented `quickstart.md:348-359`. T-043 exists (`tasks.md:442-449`). FR-052 added. |
| H2 | Pool sizing | **VERIFIED** | `pool_size=3, max_overflow=7, pool_recycle=1800, pool_pre_ping=True, command_timeout=10` at `tasks.md:75` (T-010). `research.md D-2` + `plan.md:157` document `max_connections ≥ 200` pre-flight. Max 10 conn ≤ reasonable headroom vs default 100 after accounting for main aikm pool. |
| H3 | Password rotation runbook | **VERIFIED** | `quickstart.md §9:325-344` ships the full 5-step procedure (ALTER → update .env → recycle → smoke test). `openssl rand -hex 32` (URL-safe) explicitly — not base64. `CONNECTION LIMIT 10` on role at `data-model.md:174` prevents credential reuse storms. 90-day rotation cadence documented. |
| H4 | CI auto-migrate + grant-audit | **VERIFIED** | T-044 (`tasks.md:451-461`) adds `.github/workflows/pg-viewer-grant-audit.yml` (nightly) + updates `main-deploy.yml` to detect migration-file diff and apply 001 (as postgres) + 002 (as aikm) pre-`docker compose up`. Post-deploy smoke curls `/api/pg-viewer/tables` with `PG_VIEWER_CI_ADMIN_JWT` GH secret. `PG_VIEWER_PASSWORD` lives on host `/etc/aikm/.env`, NOT in GH secrets. |

**Round-1 HIGH: 4/4 resolved.**

---

## Round-2 NEW findings

### 🟠 H-N1. Migration rollback does not REASSIGN/DROP OWNED — `DROP ROLE aikm_viewer` will fail if any dependent object exists
- **Where**: `quickstart.md:307-319` "Nuclear" rollback runs `DROP TABLE pg_viewer_audit_log CASCADE; DROP VIEW users_public; REVOKE ALL; DROP ROLE aikm_viewer;`
- **Operational risk**: `DROP ROLE` fails if the role owns any objects OR has any remaining grants in any database. Postgres will emit `ERROR: role "aikm_viewer" cannot be dropped because some objects depend on it` with a listing of every grant (can be dozens if the role has SELECT on every public.* table). Operator trying to rollback in an incident hits this error, flails at REVOKEs in unknown order, possibly gives up with the role half-removed. Standard Postgres idiom is:
  ```sql
  REASSIGN OWNED BY aikm_viewer TO postgres;
  DROP OWNED BY aikm_viewer CASCADE;   -- drops privileges + any owned objects
  DROP ROLE aikm_viewer;
  ```
- **Fix**: update `quickstart.md §8 Nuclear` to prepend `REASSIGN OWNED BY aikm_viewer TO postgres;` + `DROP OWNED BY aikm_viewer;` before `DROP ROLE`. Also note that `REVOKE ALL ON ALL TABLES IN SCHEMA public FROM aikm_viewer` is a superset of `DROP OWNED` for the privileges case, but `DROP OWNED` also cleans up the per-database-level grants (`GRANT CONNECT`) that plain REVOKE-on-tables misses.

### 🔴 H-N2. Monthly partition creation is a manual cron — if it fails or is forgotten, INSERTs fail at month boundary
- **Where**: `data-model.md:279` "each month a new partition is created by a cron on 192.168.1.11" + `quickstart.md:362-367` "Run on the 25th of each month" (advisory, not installed).
- **Operational risk**: Postgres partitioned tables with no matching range partition reject INSERTs with `ERROR: no partition of relation "pg_viewer_audit_log" found for row`. Every admin action on/after the 1st of the uncovered month → audit INSERT fails → `write_audit()` logs the error but since audit uses an independent tx (good), the request itself still succeeds. Result: **silent loss of audit rows for the entire month** until someone notices the logged errors. Migration ships only two partitions (`2026_04`, `2026_05`) at `data-model.md:275-278`. If deploy happens 2026-04-21 and nobody installs the cron, everything works until 2026-06-01 00:00 UTC. Then audit history gaps. This is forensically disastrous — the whole point of the audit log is regulatory/incident use.
- **Fix**:
  1. Ship a host-side cron in T-043 that runs on the 25th of every month and creates the next month's partition idempotently (`CREATE TABLE IF NOT EXISTS pg_viewer_audit_log_YYYY_MM PARTITION OF ...`). Same shell script that owns weekly purge is fine.
  2. OR (cleaner) install `pg_partman` extension in `aikm-postgres` and let it manage partitions automatically. Adds one row to the extension-denylist bypass list in `001` migration.
  3. Either way: add a daily healthcheck that `SELECT relname FROM pg_inherits JOIN pg_class c ON c.oid=inhrelid WHERE inhparent='pg_viewer_audit_log'::regclass AND relname ~ to_char(NOW()+INTERVAL '1 month','"pg_viewer_audit_log_"YYYY_MM')` returns ≥1 row; alert if missing.
  4. Also-also: add a fallback to T-014 (audit writer) — if partition INSERT fails with SQLSTATE `23514` (check violation) or partition-not-found, fall back to INSERT into an unpartitioned "spillover" table `pg_viewer_audit_log_spillover` so no audit row is ever lost. This is defense in depth; recommended regardless of (1-3).
- **Severity**: H (silent data-loss, not outage).

### 🟠 H-N3. No `PG_VIEWER_*` env vars in `.env.example` or `docker-compose.yml` — deployment-time config drift
- **Where**: tasks.md:39 (T-002) says "docker-compose.yml pass env through to backend service" and "frontend .env.example (add NEXT_PUBLIC_PG_VIEWER_ENABLED)" — but backend `.env.example` is only cited as `PG_VIEWER_PASSWORD=changeme`. The other 8 new env vars are not listed as requiring `.env.example` placeholders.
- **Operational risk**: `PG_VIEWER_ROW_LIMIT`, `PG_VIEWER_STMT_TIMEOUT_MS`, `PG_VIEWER_SQL_MAX_LEN`, `PG_VIEWER_AUDIT_RETENTION_DAYS`, `PG_VIEWER_RATE_LIMIT_SQL`, `PG_VIEWER_RATE_LIMIT_ROWS` all have sensible defaults in code but are invisible to ops. When ops wants to tune (e.g. cut timeout to 5s after a noisy-admin incident), they need to grep code rather than `.env.example`. Also — if `docker-compose.yml` doesn't explicitly pass them through, a change to `/etc/aikm/.env` has no effect and the tuning is silently ignored.
- **Fix**: T-002 scope needs to explicitly include:
  1. All 9 env vars (8 PG_VIEWER_* + PG_VIEWER_PASSWORD) listed in `.env.example` with commented defaults.
  2. `docker-compose.yml` `services.backend.environment:` block must enumerate each (`${PG_VIEWER_ROW_LIMIT:-1000}` syntax).
  3. `NEXT_PUBLIC_PG_VIEWER_ENABLED` similarly in frontend service block.
  4. Acceptance test: `docker compose config | grep PG_VIEWER | wc -l` returns ≥9 on the backend service.

### 🟡 M-N1. Grant-audit cron's action on detection is ambiguous — auto-fix risks role drift
- **Where**: `tasks.md:459` — "nightly enumerates public tables where has_table_privilege('aikm_viewer', t, 'SELECT')=false; alerts via GitHub issue comment or Discord webhook if non-zero".
- **Operational risk**: Good that it's alert-only (NOT auto-fix — correct choice). But the spec doesn't say who the alert goes to, or what the runbook response is. When ops sees "2 new tables without aikm_viewer SELECT", is the action to (a) run `GRANT SELECT ON tablename TO aikm_viewer` manually (correct, but requires judgment — is the new table one the admin should be able to browse?), or (b) ignore until next deploy (bad — the `grant_missing=true` UI badge appears for admins, confusing them), or (c) update the ETL script that created the table to run the GRANT itself (best long-term). No runbook.
- **Fix**: Add `quickstart.md §11 "Responding to grant-audit alerts"` with:
  1. Short check: is the new table intended for admin browse? If no (e.g. internal temp table), ignore + add to a denylist.
  2. If yes: run `GRANT SELECT ON public.<table> TO aikm_viewer;` on `aikm-postgres` via `docker exec`.
  3. Then open a PR to the ETL / migration that creates the table, adding the GRANT to it so the drift doesn't recur next rebuild.
  4. Document who the Discord webhook posts to (which channel).

### 🟡 M-N2. Pool budget accounting not documented — total PG `max_connections` consumption opaque
- **Where**: `plan.md:157` says "document `max_connections ≥ 200` pre-flight" but no actual accounting of current consumption exists anywhere in specs.
- **Operational risk**: Main aikm backend pool + ETL (aikm-maximo-extractor) + migrations tool + admin tools + psql sessions + **new viewer pool (10)** all share PG `max_connections`. Existing usage isn't documented. If real usage is 80/100, adding 10 more brings it to 90 — fine; if real usage is already 95/100, adding 10 makes next connection fail with `FATAL: remaining connection slots are reserved for non-replication superuser connections`. Pre-flight asks for ≥200, which is safe, but the pre-flight is a one-time check — no ongoing monitoring that `pg_stat_activity` active count stays below max.
- **Fix**: 
  1. Add to T-045 observability: Prometheus metric `pg_connections_active{db}` via a scheduled `SELECT count(*) FROM pg_stat_activity WHERE datname='aikm'`. Alert at 80% of max_connections.
  2. Add to `quickstart.md` pre-flight (2a): print current usage: `docker exec aikm-postgres psql -U postgres -c "SELECT count(*) FROM pg_stat_activity WHERE datname='aikm'"` and require result + 10 ≤ 0.8 × max_connections before proceeding.
  3. Document current steady-state consumption in `plan.md` § Scale after the first deploy (expected baseline).

### 🟡 M-N3. Prometheus metric labels risk PII leak
- **Where**: `tasks.md:464` T-045 proposes `pg_viewer_request_duration_seconds{endpoint, status}` + `pg_viewer_requests_total{endpoint, status}`.
- **Assessment**: labels are `endpoint` + `status` only — NO `user_id`, `table`, or `ip`. This is the correct choice and does NOT leak PII. Verified. No action needed.
- **Ops note to flag**: if a future change adds `table` as a label, it becomes unbounded-cardinality (50-500 tables) and will OOM Prometheus. Add a constraint in T-045 acceptance: "Labels MUST be bounded-cardinality; adding `table` or `user_id` labels is forbidden." **Checked, no issue — add guard clause.**

### 🟡 M-N4. `/admin/pg-viewer/health` not in the spec — deploy healthcheck relies on generic `/api/health`
- **Where**: `tasks.md:437` (T-042) smoke test is `curl /api/health` + `curl /api/pg-viewer/tables`. No dedicated health endpoint for pg-viewer subsystem.
- **Operational risk**: Generic `/api/health` won't catch: (a) viewer engine pool exhausted, (b) `aikm_viewer` role inadvertently dropped, (c) circuit breaker open. `/api/pg-viewer/tables` would catch these but requires a valid admin JWT — awkward for a passive healthcheck scraper. In the short term, the T-042 smoke curl is OK (one-shot post-deploy), but continuous monitoring (e.g. via Uptime Kuma) has no unauthenticated endpoint to poll.
- **Fix**: consider adding unauthenticated `GET /api/pg-viewer/healthz` (returns 200 if viewer engine can `SELECT 1` + circuit closed + feature flag on; 503 otherwise; no data exposure — just boolean status). Nice-to-have; not a blocker for T-042.

### 🟡 M-N5. `pg_viewer_audit_log` backup/restore intersection with retention
- **Where**: critic-round-1-ops `L3` accepted as "subject to existing backup policy". Not re-examined in round-1 resolution.
- **Operational risk**: `pg_dump` of aikm DB will include `pg_viewer_audit_log` and its partitions. Default backup retention (unknown — not documented) may exceed 180 days; restoring a 1-year-old backup brings back purged audit rows. For forensic purposes this is usually desirable (old rows are evidence). For compliance-driven retention (GDPR-style "right to be forgotten" on audit logs), not desirable. 
- **Assessment**: **Accept + document**. This is consistent behavior with `query_audit_log` (existing table, same policy). Add a one-liner to `plan.md §Risks`: "Backup restore of pre-purge state will resurrect old audit rows; operationally acceptable for forensic use."

### 🟡 M-N6. Production DDL change freeze / maintenance window not prescribed
- **Where**: `quickstart.md §2` assumes operator can run the migration at any time after `docker compose stop aikm-maximo-extractor`. No mention of: (a) user-facing announcement, (b) time-of-day preference, (c) rollback-readiness checklist.
- **Operational risk**: Running migration during peak hours → 5-second lock_timeout may hit contention with main backend holding AccessShareLocks on `users`/`maximo_mxwo` → migration aborts partially, operator must clean up. Low risk but avoidable.
- **Fix**: Add to `quickstart.md §2a`:
  - "Recommended: run during off-peak (weekday ≤ 10 AM or weekend)."
  - "Before starting: verify no active NL2SQL query via `SELECT query, state FROM pg_stat_activity WHERE datname='aikm' AND state='active' AND query_start < NOW() - INTERVAL '10s'`."
  - "Keep a rollback terminal ready with `psql -U postgres -d aikm` open."
- **Severity**: low — design is OK, just operational polish.

### 🟡 M-N7. `aikm_viewer` pool shares PG `max_connections` with main pool — no docker `depends_on` ordering for migration
- **Where**: `tasks.md:75` viewer engine created lazily on first request. If backend starts before migration has run, first request → asyncpg connect → `FATAL: role "aikm_viewer" does not exist` → 500 → circuit breaker opens → feature appears broken until next deploy.
- **Operational risk**: Deploy ordering edge case. T-042 runbook has the correct order (migration FIRST, then `docker compose up -d --build backend`), but if anyone ever runs `docker compose restart backend` before a planned migration (e.g. for an unrelated backend fix), the lazy singleton may initialize against a non-existent role. First admin request then fails until backend is restarted AFTER migration.
- **Fix**: T-010 engine.py should catch `InvalidAuthorizationSpecificationError` / `InvalidPassword` on pool init and mark the subsystem unavailable (circuit-open) with a clear log message "pg_viewer disabled: aikm_viewer role missing — did you run the migration?" rather than a bare 500. Self-healing: subsequent admin request retries connection after backoff.
- **Severity**: low — operator awareness + graceful degradation, not a correctness issue.

---

## Verified Clean (round-2 checklist)

- Migration idempotency (`\set ON_ERROR_STOP on`, `IF NOT EXISTS` everywhere, `DO` block for role existence) — **checked, OK**.
- Three-layer timeout (role ALTER + asyncpg command_timeout + SET LOCAL) — **checked, OK**.
- ALTER DEFAULT PRIVILEGES covers both creator roles — **checked, OK**.
- Password URL-safety (hex not base64) — **checked, OK**.
- GH secrets hygiene (password stays on host, only CI JWT in GH secrets) — **checked, OK**.
- Rollback preserves audit history when using feature flag path — **checked, OK**.
- Circuit breaker integration — **checked, OK** (T-021).
- Feature flag read path (runtime `get_settings()` not import-time) — **checked, OK** (T-020).
- Rate limiter uses existing Redis client — **checked, no new container** (T-014.6).
- CSV payload cap (10 MB total) — **checked, OK** (T-015).
- Prometheus label cardinality — **checked, bounded** (M-N3).
- Port collision — **checked, no new ports**.
- ETL-pause before migration (M1 from round-1) — **checked, still in quickstart §2a**.

---

## Summary

**Overall operational risk**: **Low-Medium**. All round-1 findings resolved substantively; three new findings identified. H-N2 (partition cron) is the **only latent time-bomb** and must be wired in T-043 before the first month boundary post-deploy. H-N1 (rollback role drop) and H-N3 (env-var wiring completeness) are mechanical fixes to specs. The five M-level findings are operational polish.

**Top 3 ops priorities before T-042**:
1. **H-N2** — install the monthly partition-create cron in T-043 (or adopt pg_partman). Without this, silent loss of audit rows at the first month boundary. Optional but recommended: audit-writer fallback to spillover table on partition-miss.
2. **H-N3** — T-002 must explicitly list all 9 PG_VIEWER_* env vars in `.env.example` AND `docker-compose.yml` environment block with defaults, not just `PG_VIEWER_PASSWORD`. Otherwise runtime tuning is silently ineffective.
3. **H-N1** — update `quickstart.md §8` nuclear rollback to use `REASSIGN OWNED + DROP OWNED + DROP ROLE` idiom so it actually works during an incident.

**Blockers for T-042 merge**: H-N2 + H-N3. H-N1 can be patched post-deploy but before first rollback attempt.

**Non-blocker but strongly recommended**: M-N1 (grant-audit runbook), M-N2 (connection count metric + pre-flight usage check), M-N7 (graceful role-missing handling in engine init).


---

## Resolution (P9 round-3 prep, 2026-04-20)

| ID | Finding | Resolution | File:line of fix |
|---|---|---|---|
| **H-N2 (= NEW-M1/N2)** | Partition auto-create cron not actually installed | T-043 rewritten to require BOTH (a) install the actual crons (purge + partition-healthcheck) on 192.168.1.11 + (b) observe one successful execution before merge. Healthcheck calls `ensure_next_audit_partition()` (data-model §4b) + alerts on spillover. pg_partman preferred path documented in quickstart §10d as optional opt-in. | `data-model.md` §4b; `quickstart.md` §10b/§10c/§10d; `tasks.md` T-043 |
| H-N1 | Rollback role drop fails | Quickstart §8 nuclear rollback rewritten to use `REASSIGN OWNED BY … TO postgres; DROP OWNED BY …; DROP ROLE …` idiom for both `aikm_viewer` and `aikm_audit_purger`. | `quickstart.md` §8 |
| H-N3 | Env-var wiring incomplete | Quickstart §10e enumerates all 10 `PG_VIEWER_*` + `PG_AUDIT_PURGER_*` + `AIKM_VIEWER_DB_URL` + `NEXT_PUBLIC_PG_VIEWER_ENABLED` env vars with explicit note that ops must add them to the main repo's `.env.example` and `docker-compose.yml` during the merge of 013 into main. T-002 already required this; reinforced in T-042 runbook acceptance via cross-ref to §10e. | `quickstart.md` §10e; `tasks.md` T-002 |
| (partition-level REVOKE) | Per-partition REVOKE missing | Migration 002 issues explicit per-partition REVOKEs; `ensure_next_audit_partition()` applies same REVOKEs on each new child; template in quickstart §10c repeats the REVOKE commands. | `data-model.md` §4b; `quickstart.md` §10c |
