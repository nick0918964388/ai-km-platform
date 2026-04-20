# Critic Round 3 — 013-postgres-viewer — OPS

**Reviewer angle**: verify round-2 ops resolutions + fresh R3 angles (pg_partman availability, cron ownership, spillover growth, migration re-run safety, pg_hba, backup, alert destinations, auto-migration, maintenance window, rotation alerting).
**Scope**: spec.md, plan.md, data-model.md, quickstart.md, tasks.md, docker-compose.yml, critic-round-2-ops.md §Resolution.
**Verification date**: 2026-04-20.

## Verdict: **CONDITIONAL_YES — GO for Phase 5 Day 1**

All round-2 HIGH (H-N1/N2/N3) are substantively addressed. The single most important question going into R3 — **is `pg_partman` available on `aikm-postgres`?** — is explicitly answered: docker-compose.yml line 9 uses `postgres:16-alpine` (no pg_partman), and the design correctly ships a shell+SQL fallback (`ensure_next_audit_partition()`) as the default path. pg_partman is opt-in, not assumed. **No BLOCKER.**

Two MEDIUM R3 items and one LOW belong in the follow-up task list but do not block T-042 / Phase 5 Day 1.

---

## Round-2 Finding Verification

| ID | Severity | Status | Evidence |
|---|---|---|---|
| **H-N1** (role drop fails without REASSIGN/DROP OWNED) | HIGH | **RESOLVED** | `quickstart.md:326-347` §8 Nuclear rewritten with exact idiom: `REASSIGN OWNED BY aikm_viewer/aikm_audit_purger TO postgres` → `DROP OWNED BY …` → `DROP TABLE pg_viewer_audit_log(+spillover) CASCADE` → `DROP FUNCTION ensure_next_audit_partition` → `DROP VIEW users_public` → `REVOKE ALL … FROM aikm_viewer + aikm_audit_purger` → `DROP ROLE IF EXISTS …`. Single runbook, both roles, ordered correctly. |
| **H-N2** (monthly partition cron not installed = silent audit loss) | HIGH | **RESOLVED** | `data-model.md:357-380` ships `ensure_next_audit_partition()` plpgsql with per-partition REVOKE/OWNER propagation. `quickstart.md §10b:434-478` ships the shell script + `/etc/cron.d/pg-viewer-partition-ensure` install line (nightly 01:00). Healthcheck also verifies tomorrow+next month partition coverage AND alerts on spillover rows. `tasks.md:451-472` T-043 acceptance explicitly requires: (a) scripts dropped in `/usr/local/bin`, (b) cron files in `/etc/cron.d` mode 0644, (c) **one successful execution observed pre-merge** (done criteria tasks.md:572). Spillover fallback table schema (`pg_viewer_audit_log_spillover`) at data-model.md:342-350. |
| **H-N3** (env vars missing from .env.example / docker-compose.yml) | HIGH | **RESOLVED (spec-level)** | `quickstart.md §10e:513-533` enumerates all 10 vars: PG_VIEWER_{ENABLED,PASSWORD,DATABASE_URL,ROW_LIMIT,STMT_TIMEOUT_MS,SQL_MAX_LEN,AUDIT_RETENTION_DAYS,RATE_LIMIT_SQL,RATE_LIMIT_ROWS} + PG_AUDIT_PURGER_{PASSWORD,DATABASE_URL} + AIKM_VIEWER_DB_URL + NEXT_PUBLIC_PG_VIEWER_ENABLED. T-002 scope (`tasks.md:37-44`) still lists them as wiring targets. **Spec-level OK — code-level still owed in T-002 execution**, enforced by tasks.md §Done criteria. |
| M-N1 grant-audit runbook destination | MED | PARTIAL | Alerts via Discord webhook are mentioned but target channel not named; runbook §11 still absent. Follow-up, not blocker. |
| M-N2 pool budget accounting | MED | PARTIAL | Pre-flight `max_connections ≥ 200` in place; live `pg_stat_activity` metric not yet in T-045 spec. Follow-up. |
| M-N3 Prometheus label cardinality | MED | RESOLVED | Labels remain `endpoint, status` only (tasks.md:487). |
| M-N4 /pg-viewer/healthz endpoint | MED | NOT ADDED | Accepted as nice-to-have; T-042 smoke test path still via `/api/pg-viewer/tables`. |
| M-N5 backup/restore vs retention | MED | NOT DOCUMENTED | Not in plan.md §Risks. See R3-M3 below. |
| M-N6 maintenance window | MED | NOT DOCUMENTED | quickstart §2 still lacks time-of-day guidance. See R3-M2. |
| M-N7 engine graceful role-missing | LOW | NOT ADDED | Still accepted as operator awareness. Follow-up. |
| Per-partition REVOKE | (R2 add) | RESOLVED | `data-model.md:387-391` + `ensure_next_audit_partition()` lines 372-374 apply per-partition REVOKE + OWNER. |

**R2 HIGH: 3/3 resolved. R2 MED: 2 resolved, 5 deferred, 1 unchanged.**

---

## Round-3 NEW Findings

### R3-1. pg_partman availability — **ADDRESSED** (no BLOCKER) ✅
- `docker-compose.yml:9` uses `postgres:16-alpine` → no pg_partman shipped.
- `data-model.md:354` explicitly acknowledges: "on stock aikm-postgres (postgres:16-alpine) it is NOT available, so we ship a shell+SQL fallback."
- `quickstart.md:45-52` detects extension availability at pre-flight and branches: present → operator may opt-in via §10d; absent → default shell+SQL path via §10b nightly cron.
- Design picks **option (b) shell-cron + manual SQL function** per the R3 criteria — correct, no image change required. **No BLOCKER.**

### 🟠 R3-M1. Cron ownership — host vs container ambiguity documented but consistent
- **Where**: `quickstart.md §10a:408` (purge) + `§10b:443` (healthcheck) both invoke `docker exec aikm-postgres psql …` from a host cron on 192.168.1.11.
- **Assessment**: Consistent choice — cron is on **host machine** (192.168.1.11 crontab), not inside a container. `/etc/cron.d/pg-viewer-*` confirms host installation. Failure mode: if 192.168.1.11 reboots and cron fails to start, both crons silently stop — healthcheck spillover alert would eventually catch it, but only after an INSERT fails.
- **Fix (nice-to-have)**: Add a "cron liveness" sentinel — nightly cron writes a timestamp into a file or metric; external check (existing Drone CI self-hosted runner?) flags if file is > 48h stale. Not a blocker.

### 🟠 R3-M2. No maintenance-window guidance (carry-over M-N6)
- **Where**: `quickstart.md §2` assumes arbitrary start time.
- **Risk**: Running 001 during peak can hit `lock_timeout=5s` contention on `ALTER DEFAULT PRIVILEGES` iterating ~50 public tables while main backend holds AccessShareLocks. Migration aborts partially → operator flails.
- **Fix**: Add `quickstart.md §2.0` with (a) recommended off-peak window (≤ 10 AM weekday or weekend), (b) `pg_stat_activity` pre-check for active NL2SQL queries, (c) rollback psql terminal pre-opened. Blocker only if operator chooses peak-hour deploy.

### 🟡 R3-M3. Backup/restore semantics not in risk register
- **Where**: `plan.md §Risks` does not address `pg_dump` of partitioned audit + spillover.
- **Risk**: `pg_dump` includes all partitions + spillover; restoring a 1-year-old backup resurrects purged audit rows. For forensic use this is desirable; for "right to be forgotten" it is not. Also: roles `aikm_audit_purger` must exist at restore-time for `pg_restore` to reassign ownership (otherwise restore fails).
- **Fix**: Add one-line note to `plan.md §Risks`: "Audit-log retention is a live-database property only; backup restore resurrects purged rows. If restoring after nuclear rollback, apply 001 FIRST so roles exist before pg_restore attempts to set ownership."

### 🟡 R3-M4. Password rotation has no alerting — 90-day cadence will be forgotten
- **Where**: `quickstart.md §9:380` "Rotate at least every 90 days" is passive advice.
- **Risk**: Rotation not on any calendar → goes stale → shared secret drifts in ops knowledge.
- **Fix (post-Phase-5)**: Add a simple PG-side helper + cron check: a table `role_rotation_log(role_name, last_rotated TIMESTAMPTZ)` updated by the rotation SOP; nightly healthcheck warns if `NOW() - last_rotated > 90 days`. Can piggyback on the existing partition-ensure cron. Not a blocker for Day 1.

### 🟡 R3-M5. pg_hba.conf entries not in runbook
- **Where**: `plan.md:186` says `aikm_viewer` "should restrict login to docker-internal subnet". `plan.md:196` repeats "pg_hba.conf subnet restriction" for the `psql -U aikm_viewer from non-backend host` bypass risk. **Neither quickstart §2 nor T-003 instructs the operator to edit pg_hba.conf.**
- **Risk**: If pg_hba.conf still allows `host all all 0.0.0.0/0 md5` (common default), the `aikm_viewer` (and now `aikm_audit_purger`) DSN leaked from `/etc/aikm/.env` or CI logs can be used from any reachable host. L1-L4 defenses are bypassed.
- **Fix**: Add `quickstart.md §2a-bis`:
  ```
  host  aikm  aikm_viewer         172.18.0.0/16  scram-sha-256
  host  aikm  aikm_audit_purger   127.0.0.1/32   scram-sha-256   # local cron only
  host  aikm  aikm_viewer         0.0.0.0/0      reject
  host  aikm  aikm_audit_purger   0.0.0.0/0      reject
  ```
  Plus `docker exec aikm-postgres pg_ctl reload` after editing. **Should be added before Phase 5 Day 1 merges**, but can be a same-day patch to quickstart.

### 🔵 R3-L1. T-014 acceptance does not explicitly require the 23514 → spillover fallback
- **Where**: `plan.md:189` & `critic-round-2-security.md:189` claim "task acceptance in T-014" — but `tasks.md T-014` (lines 117-131) acceptance bullets do NOT mention partition-miss catch + spillover INSERT.
- **Consequence**: A literal P7 implementer reading T-014 might implement straight-INSERT without the `except asyncpg.CheckViolationError: INSERT INTO …_spillover` branch. The healthcheck cron would still eventually surface "missing partition" via tree verification, but the current-month audit row for that request would be lost.
- **Fix**: Append to `tasks.md T-014` 驗收 block:
  - "Integration test: temporarily drop the current month's partition → call `write_audit()` → row MUST appear in `pg_viewer_audit_log_spillover` (not lost). `spillover_reason` populated with SQLSTATE + month."
  - "Unit test: exception path does NOT bubble up to outer request handler."
  This is a **mechanical spec patch** (one paragraph) that tightens T-014 to match plan.md §Risks. Not a blocker — can land same-day as Phase 5 kickoff.

### 🔵 R3-L2. Auto-migration in main-deploy.yml — what if 001 fails partway?
- **Where**: `tasks.md:480` main-deploy detects migration diff and applies 001 as postgres + 002 as aikm BEFORE `docker compose up`.
- **Risk**: `\set ON_ERROR_STOP on` at top of 001 means partial failure aborts the whole file; main-deploy then fails, containers stay on old image. Recovery requires manual intervention (either re-run 001 — idempotent, should succeed — or revert). T-044 acceptance doesn't spec this failure mode.
- **Fix**: Add to T-044 acceptance: "If migration step fails, workflow exits non-zero, does NOT run `docker compose up`, posts a Discord alert with last 30 lines of psql stderr (secrets redacted — role names are OK to show, passwords never in the log since `-v` substitution expands before psql sees them)." Not a blocker.

---

## Verified Clean (R3 checklist)

- pg_partman availability explicitly addressed, fallback chosen consistent with `postgres:16-alpine` — **checked, OK**.
- Migration idempotency for `aikm_audit_purger` role (DO $$ IF NOT EXISTS / ALTER ROLE branch) — **checked, OK** (data-model.md:247-253).
- Three crons listed in §10 table match the actual install commands (§10a Sun 03:00, §10b nightly 01:00, §10c manual template) — **checked, OK**.
- Spillover table has INSERT grant to aikm + revoke UPDATE/DELETE/TRUNCATE + REVOKE SELECT from aikm_viewer — **checked, OK** (data-model.md:348-350).
- Rollback idiom uses REASSIGN OWNED before DROP OWNED before DROP ROLE, for BOTH roles — **checked, OK**.
- Env-var list in quickstart §10e matches T-002 scope — **checked, OK** (10 vars match).
- Per-partition REVOKE applied both to seeded partitions AND to new partitions created by `ensure_next_audit_partition()` — **checked, OK** (data-model.md:372-374 + 388-391).
- Purger role has CONNECTION LIMIT 2, no SELECT/INSERT on public tables — **checked, OK** (data-model.md:249 + 258).
- Retention cron authenticates as `aikm_audit_purger`, not aikm — **checked, OK** (`ps -ef | grep pg-viewer-purge` assertion in T-043 acceptance).
- Password rotation runbook covers BOTH roles on same 90-day cadence — **checked, OK** (quickstart.md §9 both blocks).
- pg_partman image assumption — **checked, not assumed; fallback is default**.

---

## Summary

**Overall operational risk**: **Low** (down from R2 Low-Medium).

**Top 3 pre-Day-1 patches (not blockers — can land as quickstart edits same-day)**:
1. **R3-M5** — add pg_hba.conf entries for both `aikm_viewer` and `aikm_audit_purger` (subnet allowlist + default reject). Without this, the CONNECTION LIMIT 10 + password rotation layer is incomplete.
2. **R3-L1** — tighten `tasks.md T-014` acceptance to include the 23514 → spillover fallback integration test (plan.md already commits to this behavior; only the task contract is thin).
3. **R3-M2** — add maintenance-window guidance to `quickstart.md §2`.

**Deferred to post-Phase-5 polish**: R3-M1 cron-liveness sentinel, R3-M3 backup semantics note, R3-M4 rotation alert, R3-L2 migration-fail handling in T-044.

**Blockers for Phase 5 Day 1**: **NONE**.

**Go/no-go for Phase 5 Day 1 implementation**: **GO**.

The pg_partman question that would have been a BLOCKER is explicitly addressed — the fallback path is the default, pg_partman is opt-in, and the migration + cron path does not assume the extension. Combined with all three R2 HIGH findings substantively resolved, the design is safe to begin execution.
