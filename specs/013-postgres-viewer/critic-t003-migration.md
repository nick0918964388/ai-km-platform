# T-003 Migration Critic Review

**Reviewer**: critic (agent)
**Date**: 2026-04-20
**Files reviewed**:
- `backend/scripts/pg_viewer_migrate_001_role_and_grants.sql` (226 lines)
- `backend/scripts/pg_viewer_migrate_002_audit_table.sql` (248 lines)
- `specs/013-postgres-viewer/quickstart.md` §2 / §2a-c
- `specs/013-postgres-viewer/data-model.md` §4a / §4b (reference spec)
- `specs/013-postgres-viewer/tasks.md` T-003 acceptance (lines 55-68)

## Verdict: **BLOCK**

Migration 002 cannot complete as written. The `ALTER TABLE ... OWNER TO aikm_audit_purger` statement at line 173 will fail the very first run, and even if it somehow succeeded, every REVOKE/GRANT that follows (lines 182-199) would also fail because `aikm` is no longer the owner. The overall T-003 acceptance gate ("re-run twice on a fresh 16-alpine, both pass") cannot be satisfied.

---

## CRITICAL

### C1 — `ALTER TABLE ... OWNER TO aikm_audit_purger` violates PG role-membership rule
**File**: `pg_viewer_migrate_002_audit_table.sql:173-175` (also `:383-385` in the mirrored data-model.md copy)

**What's wrong**: PostgreSQL requires the executor of `ALTER TABLE ... OWNER TO target_role` to
(a) be a member of `target_role` AND
(b) the `target_role` must have `CREATE` privilege on the schema.

Migration 002 runs as `aikm` (per header line 5 + tasks.md:64 + quickstart.md:54). However:
- `aikm` is NEVER granted membership of `aikm_audit_purger` (there is no `GRANT aikm_audit_purger TO aikm` anywhere in 001 or 002).
- `aikm_audit_purger` has `CREATE` explicitly REVOKED from schema public by 001:180 (`REVOKE CREATE ON SCHEMA public FROM aikm_audit_purger`).

Both conditions fail. Postgres will emit `ERROR: must be member of role "aikm_audit_purger"` at line 173 and roll back the whole transaction (`BEGIN` at line 35 → `COMMIT` at line 215). Result: the parent table and seed partitions are rolled back, but any earlier autocommit DDL from 001 is already persisted. This aborts T-003 cleanly but means migration 002 is dead on arrival.

**Fix direction** — two acceptable paths, pick one:
1. **Run 002 as `postgres`** (superuser bypasses both checks). Change the header comment + quickstart.md §2c to `docker exec ... psql -U postgres -d aikm`. This is the simplest fix and matches what 001 already does. Recommended.
2. **Grant `aikm` membership of `aikm_audit_purger`** in 001 (`GRANT aikm_audit_purger TO aikm`) AND temporarily grant CREATE on schema public to `aikm_audit_purger` before the ALTER and revoke immediately after. Fragile and expands blast radius — not recommended.

### C2 — All REVOKE/GRANT after line 173 fail for the same reason
**File**: `pg_viewer_migrate_002_audit_table.sql:182-206`

**What's wrong**: Even if C1 were patched so the ALTER succeeded, after ownership transfer `aikm` no longer owns `pg_viewer_audit_log` and the partitions. Subsequent `REVOKE ALL ON pg_viewer_audit_log FROM aikm;` (line 182), `GRANT INSERT, SELECT ON pg_viewer_audit_log TO aikm;` (line 183), and the identical pair on both seed partitions (lines 194-199) all require the executor to be the table owner or superuser. Running as `aikm` (non-owner after line 173, non-superuser), these raise `ERROR: permission denied for table pg_viewer_audit_log`.

**Fix direction**: Same as C1 — switch the deploy identity for 002 to `postgres`. Alternatively, re-order: do all REVOKE/GRANT on the partitioned parent + seeds BEFORE `ALTER TABLE ... OWNER TO`. This works only if C1 is also fixed via path-2 (membership-based) and still leaves a window where a superuser path is simpler.

### C3 — Spillover table grants declared in data-model.md §4b are missing from the migration
**File**: `pg_viewer_migrate_002_audit_table.sql:202-206` vs. `data-model.md:348-350`

**What's wrong**: `data-model.md` §4b:348-350 specifies:
```
GRANT INSERT, SELECT ON pg_viewer_audit_log_spillover TO aikm;
REVOKE UPDATE, DELETE, TRUNCATE ON pg_viewer_audit_log_spillover FROM aikm;
REVOKE SELECT ON pg_viewer_audit_log_spillover FROM aikm_viewer;
```
Migration 002 line 204-206 implements only the blanket `REVOKE ALL ... FROM aikm`, then `GRANT INSERT, SELECT ... TO aikm`, then `REVOKE ALL ... FROM aikm_viewer`. The append-only REVOKE (`UPDATE, DELETE, TRUNCATE`) is NOT explicitly present on the spillover — it is implied by the blanket REVOKE ALL followed by selective GRANT, which in PG does achieve the same end state. Functionally equivalent. However, this collides with C2 at runtime since aikm is no longer the owner (the spillover is owned by aikm and is fine, but if ever mutated alongside the audit log it breaks the symmetry).

**Fix direction**: Once C1/C2 are patched, verify the spillover REVOKE/GRANT still runs (spillover is NOT transferred to purger, so aikm remains owner — these statements will work). No migration SQL change required once deploy identity is fixed.

---

## HIGH

### H1 — Status CHECK constraint drifts from spec (`'denied'` added silently)
**File**: `pg_viewer_migrate_002_audit_table.sql:60-61` vs. `data-model.md:306`

**What's wrong**: Migration 002 adds `'denied'` to the `status` CHECK:
```
CHECK (status IN ('ok','timeout','error','forbidden','rate_limited','denied'))
```
but `data-model.md:306` enumerates only `('ok','timeout','error','forbidden','rate_limited')`. The reviewer prompt notes `'denied'` was added per db-expert. Consequence: the source-of-truth spec (data-model.md) is out of sync with the migration. Downstream code reading the spec will use `forbidden` where the DB accepts both `forbidden` and `denied`, inviting semantic ambiguity ("what's the difference?"). If future code emits `denied` when the API actually returns 403, analytics queries counting `WHERE status='forbidden'` will under-count.

**Fix direction**: Either (a) remove `'denied'` from the migration (revert to spec), or (b) update `data-model.md:306` + FR references in spec.md to declare `'denied'` vs `'forbidden'` semantics (e.g., `forbidden` = authZ failure at API layer, `denied` = guardrail block before SQL reached DB). Decision needed before T-010 implements write_audit().

### H2 — 002 verification check does not reflect post-ownership state
**File**: `pg_viewer_migrate_002_audit_table.sql:223-226`

**What's wrong**: The final SELECT tests `has_table_privilege('aikm', 'pg_viewer_audit_log', 'INSERT')`. After C1/C2 are fixed and ownership is transferred, `aikm` is NOT the owner of the parent — so INSERT privilege depends on the explicit GRANT surviving. That check is correct. However, `aikm_update` is expected `f` — and that is also correct because REVOKE ALL + GRANT INSERT, SELECT leaves UPDATE ungranted. Good. But `purger_owns_parent` is MISSING from 002's verification block; data-model.md:414 includes it. Without this check, a future regression that silently leaves aikm as owner (bypassing ALTER TABLE ... OWNER TO) would not be caught.

**Fix direction**: Add to the verification SELECT:
```sql
EXISTS (SELECT 1 FROM pg_class c JOIN pg_roles r ON c.relowner=r.oid
        WHERE c.relname='pg_viewer_audit_log' AND r.rolname='aikm_audit_purger') AS purger_owns_parent
```

### H3 — `REVOKE ALL ON SCHEMA public FROM PUBLIC` (line 121) may break other roles
**File**: `pg_viewer_migrate_001_role_and_grants.sql:121-122`

**What's wrong**: Line 121 revokes ALL on schema public from PUBLIC. Postgres 15+ already defaults to this (CREATE is REVOKEd from PUBLIC on schema public), but this statement also revokes **USAGE** from PUBLIC in one sweep. Any existing role that relied on the default `GRANT USAGE ON SCHEMA public TO PUBLIC` (e.g., `aikm` itself, unless it was explicitly granted USAGE) may now lose schema access. `aikm` is a role created during container init — if it was not explicitly GRANTed USAGE on public, it may now be locked out.

Similarly line 122 `REVOKE ALL ON DATABASE aikm FROM PUBLIC` revokes CONNECT/TEMPORARY from PUBLIC — breaks anyone using the default CONNECT grant.

**Fix direction**: Before applying in production, run:
```sql
SELECT grantee, privilege_type FROM information_schema.usage_privileges
WHERE object_schema='public' AND grantee='PUBLIC';
SELECT r.rolname, has_schema_privilege(r.rolname, 'public', 'USAGE')
FROM pg_roles r WHERE r.rolname IN ('aikm','postgres','aikm_viewer','aikm_audit_purger');
```
If aikm does not have explicit USAGE grant, add `GRANT USAGE ON SCHEMA public TO aikm;` BEFORE line 121 to guarantee idempotency across container rebuilds.

### H4 — CREATE ROLE race / password-rotation-on-rerun silent behaviour
**File**: `pg_viewer_migrate_001_role_and_grants.sql:60-73`, `156-169`

**What's wrong**: On re-run, the DO block's ELSE branch executes `ALTER ROLE aikm_viewer WITH LOGIN PASSWORD %L`. This means that if an operator re-runs the migration after an out-of-band password rotation (e.g., secret rotation via vault), the migration will silently stomp the new password with whatever `:'pg_viewer_password'` is passed. If that psql var is empty (missing `-v`), the ALTER becomes `ALTER ROLE aikm_viewer WITH LOGIN PASSWORD ''` — valid SQL, locks out the role with an empty password.

**Fix direction**:
1. Guard against empty password: add at top of the DO block `IF :'pg_viewer_password' = '' THEN RAISE EXCEPTION 'pg_viewer_password is empty'; END IF;` (or check via a separate `\if`). This also needs to run for `pg_audit_purger_password`.
2. Document the "re-run rotates the password" behaviour explicitly in the header comment + quickstart §2a so operators don't accidentally wipe a vault-rotated secret by running the migration again.

---

## MEDIUM

### M1 — `LIKE pg_viewer_audit_log INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING IDENTITY` on a partitioned parent
**File**: `pg_viewer_migrate_002_audit_table.sql:121`

**What's wrong**: `LIKE <partitioned_parent>` copies columns + defaults + constraints + identity, which is fine. But note the PK `(id, created_at)` was declared as part of the parent CREATE. `INCLUDING IDENTITY` creates a **new** sequence for spillover's `id` column (BIGSERIAL). This means spillover IDs can collide with partition IDs because they are independent sequences. If spillover rows are later UNION'd with the partitioned data for forensic analysis, `id` is not globally unique — only `(id, created_at)` pair may be.

**Fix direction**: Either document clearly that spillover.id and audit_log.id are independent sequences (acceptable for forensics if (id, spilled_at) is the spillover key), or reuse the partitioned parent's sequence via `DEFAULT nextval('pg_viewer_audit_log_id_seq')` explicitly.

### M2 — `information_schema` / `pg_catalog` exposure — risk accepted but not documented inline
**File**: `pg_viewer_migrate_001_role_and_grants.sql:97-98`

**What's wrong**: Comment at line 97-98 says "explicit, normally PUBLIC" but doesn't link back to the spec decision (data-model.md / plan.md security model acknowledges this). If an auditor reads 001 standalone, they may flag this as a leak. Attack surface: `aikm_viewer` can SELECT from `information_schema.columns`, `pg_stat_activity` (own sessions), `pg_stat_database`, and enumerate user list via `pg_catalog.pg_roles`. None of these are sensitive for the admin-only feature, but add an inline comment pointer to plan.md L5 for future reviewers.

**Fix direction**: Prepend lines 97-98 with a `-- Risk-accepted per plan.md §"Security Model" L5 — aikm_viewer is admin-only, info_schema leak is low-risk` comment.

### M3 — Dangerous-extension denylist missing `pg_prewarm` was added but NOT `pg_stat_statements`
**File**: `pg_viewer_migrate_001_role_and_grants.sql:31-40`

**What's wrong**: Reviewer prompt asks to recommend adds/removes. The list covers filesystem + outbound + untrusted-PL. Notably absent:
- `pg_stat_statements` — exposes **every SQL statement** executed across the DB (including queries from aikm_maximo-extractor, aikm backend, etc.). A viewer with SELECT on `pg_stat_statements` view can scrape secrets from raw_sql. **Should be denylisted OR the view should be explicitly REVOKEd from aikm_viewer.**
- `pg_buffercache` — raw buffer introspection; low risk but marginal info leak.
- `pgstattuple` — invoke-cost high but can force buffer loads; minor DoS vector.

Low-risk / keep allowed: `pgcrypto`, `uuid-ossp`, `citext`, `hstore`, `btree_gin`, `btree_gist`, `pg_trgm`.

`plv8` / `plluau` / `pltclu` — should be in the denylist if ever installed on 16-alpine.

**Fix direction**: Add to the `IN (...)` list on line 31-40:
```
'pg_stat_statements', -- cross-DB SQL leak
'plv8',               -- JS execution
'plluau', 'pltclu',   -- untrusted PL variants
```
Or, if `pg_stat_statements` must stay (it's a common ops extension), add `REVOKE SELECT ON pg_stat_statements FROM aikm_viewer;` guarded by `IF EXISTS`.

### M4 — `ensure_next_audit_partition()` runs as INVOKER; ownership implications
**File**: `pg_viewer_migrate_002_audit_table.sql:136-166`

**What's wrong**: Function is declared without `SECURITY DEFINER`, so it runs as INVOKER (the role that calls it). The migration grants EXECUTE to both `aikm` and `aikm_audit_purger` (lines 212-213). But the function does:
- `CREATE TABLE ... PARTITION OF pg_viewer_audit_log` — requires CREATE on schema public AND ownership of pg_viewer_audit_log (the parent)
- `ALTER TABLE %I OWNER TO aikm_audit_purger` — requires membership in target role

If `aikm` calls it, neither condition holds (aikm has no CREATE on public per 001:118, and is not a member of aikm_audit_purger per C1). If `aikm_audit_purger` calls it, also no CREATE on public per 001:180. **Neither grantee can successfully invoke this function.**

**Fix direction**:
1. Declare `SECURITY DEFINER` and set the function owner to a role with the needed privileges (postgres superuser, or a purpose-built DDL role). Add `SET search_path = public, pg_temp` to the function to prevent search_path hijack (standard SECURITY DEFINER hygiene).
2. Alternatively, have the nightly cron call the function as `postgres` via docker exec (changes the operational model — documented in quickstart §10b as the simplest path).

### M5 — `chk_raw_sql_only_for_editor` blocks audit of denied SQL-editor attempts
**File**: `pg_viewer_migrate_002_audit_table.sql:67-69`

**What's wrong**: The CHECK requires `query_type='sql_editor' AND raw_sql IS NOT NULL` strictly OR `query_type <> 'sql_editor' AND raw_sql IS NULL`. If a SQL-editor request is denied BEFORE raw_sql is captured (e.g., rate-limit pre-flight, user unauthenticated), the audit row cannot be inserted with `query_type='sql_editor'` + `raw_sql=NULL`. Forensic completeness is broken: rate-limited SQL attempts must either silently drop or be miscategorised as `table_browse`.

**Fix direction**: Relax the CHECK to `(query_type='sql_editor' AND status='ok' AND raw_sql IS NOT NULL) OR (query_type='sql_editor' AND status<>'ok') OR (query_type<>'sql_editor' AND raw_sql IS NULL)` — allows denied/rate_limited sql_editor rows without raw_sql. OR, require raw_sql for every sql_editor row (even denied) and populate with the un-validated attempt — but that raises its own leak concerns for garbage input. First option preferred.

---

## LOW / NITS

### L1 — Unused variable in `ensure_next_audit_partition`
`pg_viewer_migrate_002_audit_table.sql:143` — `found_row RECORD` is declared; the function uses `IF NOT FOUND` instead of inspecting `found_row`. The `SELECT 1 INTO found_row` is a no-op wrapper. Simplify to `PERFORM 1 FROM pg_class WHERE ...; IF NOT FOUND THEN ...`.

### L2 — `NOINHERIT` clause added to both roles — not in spec
`pg_viewer_migrate_001_role_and_grants.sql:64, 69, 160, 165` — NOINHERIT is a conservative hardening (prevents automatic privilege inheritance if membership is ever granted later). Not mentioned in data-model.md §4a. No harm, but deviation from spec should be documented. Add comment: `-- NOINHERIT: future-proof — even if GRANT aikm_viewer TO other_role occurs, privileges are not auto-assumed.`

### L3 — `ALTER DEFAULT PRIVILEGES` for `aikm_maximo_extractor` role not declared
`pg_viewer_migrate_001_role_and_grants.sql:106-109` — Default privileges are set only for `postgres` and `aikm`. If `aikm-maximo-extractor` writes a new `maximo_*` table, that table will NOT auto-grant SELECT to aikm_viewer. Comment on line 110 says "if a new table-creating role is introduced, ADD a line here" — which is correct guidance but leaves maximo-extractor out. Verify if the extractor uses the `aikm` role or its own identity. If latter, add a line.

### L4 — `CONNECTION LIMIT 10` for aikm_viewer may be tight for parallel admin users
`pg_viewer_migrate_001_role_and_grants.sql:64, 69` — If multiple admins use the viewer concurrently with its 10s statement_timeout, 10 connections is ~1 req/sec per admin. T-010 pool size + this limit should be cross-checked. Non-blocking; flag to the T-010 implementer.

### L5 — `\echo` lines provide test markers but do not gate on failure
`pg_viewer_migrate_001_role_and_grants.sql:208, 226`, `pg_viewer_migrate_002_audit_table.sql:221, 248` — The final SELECT prints `t/f` columns, but the migration does not `DO $$ IF ... THEN RAISE EXCEPTION` when a value is `f`. CI that pipes output to a check must parse the output — brittle. Add a trailing `DO $$ BEGIN IF <each check> IS FALSE THEN RAISE EXCEPTION 'verification failed: ...'; END IF; END $$;` block so the exit code is the contract.

### L6 — quickstart.md §2 table (lines 36-41) is good but step 4 grep pattern fragile
`specs/013-postgres-viewer/quickstart.md:41` — `grep -cE '^(PG_VIEWER_PASSWORD|PG_AUDIT_PURGER_PASSWORD)=' /etc/aikm/.env` returns the count, but if either variable is defined with quotes or export-prefix, the count is wrong. Suggest `grep -cE '^(export\s+)?(PG_VIEWER_PASSWORD|PG_AUDIT_PURGER_PASSWORD)=["\x27]?[^"\x27]+["\x27]?$'` or use `set -a; source /etc/aikm/.env; [[ -n "$PG_VIEWER_PASSWORD" ]] && [[ -n "$PG_AUDIT_PURGER_PASSWORD" ]]`.

### L7 — `relispartition` check in verification is PG10+ correct, but partition_<date>_exists ignores parent drift
`pg_viewer_migrate_002_audit_table.sql:227-234` — If a partition exists but is NO LONGER attached to `pg_viewer_audit_log` (detached), `relispartition` is false. That's caught. But if a partition was renamed (very unlikely), the check passes a wrong table name. Non-issue in practice.

---

## Summary

Overall risk: **High** — migration 002 cannot complete on a fresh install as written (C1, C2). Must be patched before T-003 can be marked DONE.

Top 3 priorities:
1. **Fix C1 + C2**: change 002 to run as `postgres` (recommended), update header comment, quickstart.md §2c, tasks.md:64. This unblocks the whole migration. Then re-validate twice-run idempotency on a fresh `postgres:16-alpine` container.
2. **Fix M4**: declare `ensure_next_audit_partition()` as `SECURITY DEFINER` with postgres owner + explicit search_path, or change the cron to invoke as postgres. Otherwise the nightly partition-creation cron silently fails starting 2026-06.
3. **Fix H1 + M3 + M5**: reconcile `status IN (...)` with spec (delete `'denied'` or update spec), add `pg_stat_statements` + `plv8` to denylist, relax `chk_raw_sql_only_for_editor` to allow denied sql_editor rows without raw_sql.

Ready-to-deploy: **NO**.

Also add H4 password-empty guard + L5 verification-failure RAISE EXCEPTION before marking T-003 acceptance-complete.

---

## Resolution (db-expert, 2026-04-20)

Mapping each critic finding to the concrete fix location.

### CRITICAL

| Finding | Status | Fix location |
|---|---|---|
| **C1** — `ALTER TABLE ... OWNER TO` fails as aikm | FIXED | `backend/scripts/pg_viewer_migrate_002_audit_table.sql:4-13` (header says runs-as postgres); `specs/013-postgres-viewer/quickstart.md` §2 invocation block + §2c changed `-U aikm` → `-U postgres`; `specs/013-postgres-viewer/tasks.md:55-56, 64` T-003 acceptance updated. |
| **C2** — REVOKE/GRANT after ownership transfer fail | FIXED (same root cause as C1) | Running as postgres bypasses both the membership check (ALTER ... OWNER TO) and the owner-or-superuser check (REVOKE/GRANT). No other privileged statement was discovered after walking `pg_viewer_migrate_002_audit_table.sql` end-to-end. |
| **C3** — spillover grants — noted as functionally equivalent by critic | NO-CHANGE needed | With C1/C2 fixed, the existing REVOKE ALL + GRANT INSERT, SELECT + REVOKE ALL FROM aikm_viewer pattern on spillover runs cleanly (aikm remains spillover owner; postgres as executor has full authority regardless). |

### HIGH

| Finding | Status | Fix location |
|---|---|---|
| **H1** — status CHECK drifts from spec (`denied` missing) | FIXED | Decision per prompt: keep `denied` + `rate_limited` in 002 (runtime requirement for T-014.5 rate limiter / guardrail pre-DB block). Updated spec to match: `specs/013-postgres-viewer/data-model.md:306` CHECK enumeration now includes `'denied'`, with inline comment explaining `forbidden` = API-layer authZ failure vs `denied` = guardrail block before SQL reached DB. |
| **H2** — purger_owns_parent missing from verification | FIXED | Added to SELECT in `backend/scripts/pg_viewer_migrate_002_audit_table.sql:277-284` (verification SELECT) AND mirrored in the trailing DO $verify$ block at `:303, :326-328`. |
| **H3** — REVOKE ALL ... FROM PUBLIC may lock out aikm | FIXED (belt-and-suspenders) | `backend/scripts/pg_viewer_migrate_001_role_and_grants.sql:124-129` now GRANTs USAGE on schema public + CONNECT on database aikm TO aikm BEFORE the REVOKE FROM PUBLIC, guaranteeing aikm keeps schema access regardless of the default-USAGE situation on any given PG instance. |
| **H4** — password empty → silent lock-out on re-run | FIXED | `backend/scripts/pg_viewer_migrate_001_role_and_grants.sql:64-68` + `:175-178` — both DO blocks now RAISE EXCEPTION on null/empty psql var. Also documented "re-run rotates the password" warning inline. quickstart.md §9 already covers rotation runbook. |

### MEDIUM

| Finding | Status | Fix location |
|---|---|---|
| **M1** — spillover `INCLUDING IDENTITY` creates independent sequence | DOCUMENTED (not fixed — behaviour is acceptable) | Comment added at `backend/scripts/pg_viewer_migrate_002_audit_table.sql:123-130` explaining the independent-sequence tradeoff and why it is acceptable for a last-resort forensic table. |
| **M2** — information_schema / pg_catalog exposure | DOCUMENTED | `pg_viewer_migrate_001_role_and_grants.sql:97-99` now has an inline risk-accepted comment pointing to plan.md "Security Model" L5. |
| **M3** — pg_stat_statements, plv8, plluau, pltclu not denylisted | PARTIALLY FIXED | Added `plv8`, `plluau`, `pltclu` to the extension denylist at `pg_viewer_migrate_001_role_and_grants.sql:41-43`. `pg_stat_statements` intentionally left OFF the denylist (commonly required for ops on 16-alpine); the comment at line 44-46 documents the plan: selective REVOKE of its view from aikm_viewer is a future hardening (would require IF EXISTS wrapper since the extension may not be installed). Not gated on this review. |
| **M4** — ensure_next_audit_partition INVOKER cannot succeed | FIXED | `backend/scripts/pg_viewer_migrate_002_audit_table.sql:140-167` — function is now `SECURITY DEFINER` with `SET search_path = public, pg_temp` (CVE-2018-1058 hygiene); `ALTER FUNCTION ... OWNER TO postgres` at `:172`. EXECUTE grants to both aikm and aikm_audit_purger retained; as DEFINER-postgres the function has full privilege regardless of which invoker called it. |
| **M5** — chk_raw_sql_only_for_editor blocks audit of denied attempts | FIXED | Relaxed CHECK at `backend/scripts/pg_viewer_migrate_002_audit_table.sql:76-85` — `sql_editor` rows with `status<>'ok'` may now have `raw_sql IS NULL` (required for rate-limit-denied pre-capture cases). Inline comment explains the three-way rule. |

### LOW / NITS

| Finding | Status | Fix location |
|---|---|---|
| **L1** — unused `found_row RECORD` | FIXED | Replaced with `PERFORM 1 FROM pg_class ...` at `backend/scripts/pg_viewer_migrate_002_audit_table.sql:154-156`. |
| **L2** — NOINHERIT not in spec | DOCUMENTED | Inline comment added at `pg_viewer_migrate_001_role_and_grants.sql:58-60` explaining the deviation. |
| **L3** — aikm_maximo_extractor default privileges | NOT FIXED (requires ops decision) | The extractor currently writes with the `aikm` identity per `docker-compose.yml`, so `ALTER DEFAULT PRIVILEGES FOR ROLE aikm` already covers its new tables. If the extractor ever migrates to its own identity, one line must be added per the existing comment at `pg_viewer_migrate_001_role_and_grants.sql:110`. Not blocking for T-003. |
| **L4** — CONNECTION LIMIT 10 may be tight | ACKNOWLEDGED | Flagged to T-010 implementer per the critic note. No migration change. |
| **L5** — `\echo` verification does not gate on failure | FIXED | Trailing `DO $verify$` blocks added that RAISE EXCEPTION on any invariant violation: `pg_viewer_migrate_001_role_and_grants.sql:253-267` and `pg_viewer_migrate_002_audit_table.sql:290-329`. CI can now rely on psql exit code. |
| **L6** — quickstart grep pattern fragile | NOT FIXED | Minor; quickstart.md §pre-flight command already scoped to an exact line prefix `^(PG_VIEWER_PASSWORD|PG_AUDIT_PURGER_PASSWORD)=`. Export-prefix / quoted variants are an ops edge case; deferred. |
| **L7** — `relispartition` check | NO-CHANGE | Critic noted "non-issue in practice"; accepted. |

### Re-run-twice semantics

The prompt asked whether the re-run-twice-on-clean-PG instruction is unchanged. It is **unchanged in intent but re-asserted in new locations**:

- `pg_viewer_migrate_002_audit_table.sql:19-20` adds explicit "Rerun-twice" line in header.
- `tasks.md` T-003 acceptance now says "applied TWICE in a row **as postgres**" for both 001 and 002.
- `quickstart.md` §2 retains "Both migrations are idempotent — re-running them on a clean DB must produce the same verification output; re-running on an already-migrated DB re-asserts grants without error."

All idempotency guards (`CREATE TABLE IF NOT EXISTS`, `CREATE OR REPLACE FUNCTION`, `ALTER TABLE ... OWNER TO` = no-op if already owner, the DO-wrapped CREATE ROLE, IF EXISTS guards on REVOKEs of possibly-absent tables) remain intact.

### Not fixed — deferred to future tasks

- **L3** — default privileges for aikm_maximo_extractor (needs ops confirmation whether extractor writes as its own role).
- **L6** — quickstart grep pattern fragility (ops edge case, low impact).
- **M3 partial** — `pg_stat_statements` view REVOKE (optional ops hardening; requires IF EXISTS guard).

### Ready for critic re-review

Yes. The three CRITICAL findings are closed; the partition-cron silent-fail risk (M4) is eliminated; the status-enum divergence (H1) is reconciled in favor of the spec updating to match 002; exit-code contracts now exist for both migrations (L5).

---

## Round 2 verdict (critic, 2026-04-20)

Re-reviewed full files end-to-end: `pg_viewer_migrate_001_role_and_grants.sql` (278 lines), `pg_viewer_migrate_002_audit_table.sql` (351 lines), `quickstart.md` §pre-flight + §2b + §2c, `tasks.md` T-003, `data-model.md` §4b.

### Verification of Round 1 findings

| # | Finding | Status | Evidence |
|---|---------|--------|----------|
| **C1** | 002 executor changed to postgres | **VERIFIED_FIXED** | `002:4-11` header explicitly states "Runs as postgres (superuser) — REQUIRED"; `quickstart.md:53-62, 119-128` uses `-U postgres`; `tasks.md:55-64` T-003 acceptance rewritten to say "as postgres" for BOTH 001 and 002. |
| **C2** | All post-ownership REVOKE/GRANT run as superuser | **VERIFIED_FIXED** | Walked 002 §6→§10 (lines 215→255): every REVOKE/GRANT after `ALTER TABLE ... OWNER TO aikm_audit_purger` executes as postgres superuser, which bypasses the owner-or-superuser check. No ownership-dependent failure path remains. |
| **C3** | Spillover grants | **NO-CHANGE needed** | Spillover stays aikm-owned (002:219); as superuser the REVOKE/GRANT pattern at 002:246-248 runs cleanly. |
| **H1** | data-model.md §4b CHECK drift | **VERIFIED_FIXED** | `data-model.md:306` now includes `'rate_limited','denied'` with inline semantic distinction (forbidden=API-layer authZ vs denied=guardrail pre-DB). Matches 002:72. |
| **H2** | `purger_owns_parent` verification | **VERIFIED_FIXED** | Added to both the SELECT at 002:291-298 AND the DO $verify$ gate at 002:334-337, 348. |
| **H3** | USAGE + CONNECT to aikm before REVOKE FROM PUBLIC | **VERIFIED_FIXED** | 001:148-149 explicitly GRANTs before the PUBLIC revoke at 001:150-151. |
| **H4** | Password-empty guard | **VERIFIED_FIXED** | Guards at 001:75-77 (aikm_viewer) and 001:190-192 (aikm_audit_purger); both RAISE EXCEPTION on empty/null. |
| **M1** | Spillover independent sequence | DOCUMENTED at 002:140-146 (acceptable). |
| **M2** | info_schema leak | DOCUMENTED at 001:116-119 with plan.md pointer. |
| **M3** | Extension denylist | PARTIAL — `plv8, plluau, pltclu` added 001:40-42; `pg_stat_statements` deferred with explicit comment 001:43-46. Acceptable. |
| **M4** | `ensure_next_audit_partition()` SECURITY DEFINER | **VERIFIED_FIXED** | 002:174 `SECURITY DEFINER`, 002:175 `SET search_path = public, pg_temp`, 002:208 `ALTER FUNCTION ... OWNER TO postgres`. EXECUTE grants at 002:254-255. |
| **M5** | `chk_raw_sql_only_for_editor` relaxed | **VERIFIED_FIXED** | 002:86-89 three-way rule allows denied sql_editor rows without raw_sql. |
| **L1** | unused found_row RECORD | **VERIFIED_FIXED** | 002:183-184 uses `PERFORM` now. |
| **L2** | NOINHERIT documented | **VERIFIED_FIXED** | Comment at 001:65-67. |
| **L5** | verification exit-code contract | **VERIFIED_FIXED** | `DO $verify$` blocks at 001:267-277 + 002:304-350 RAISE EXCEPTION on each invariant. |

### Regression checks

1. **`current_user` semantic drift (002 runs as postgres)** — grepped 002: no `ALTER DEFAULT PRIVILEGES FOR ROLE current_user`, no `CURRENT_USER` references. Only explicit role names (`aikm`, `aikm_viewer`, `aikm_audit_purger`, `postgres`). **Safe.**
2. **aikm INSERT/SELECT on partitions after ownership transfer** — 002:225 (parent), 002:238-239 (seed partitions), 002:196 (new partitions via helper) all GRANT INSERT, SELECT TO aikm explicitly as postgres. Grants survive ownership transfer because they are role-level, not owner-derived. **Safe.**
3. **Purger can DROP partitions** — ownership transferred at 002:215-217 (seeds) and 002:197 (via helper for future partitions). DROP TABLE requires ownership → purger can drop. **Safe.**
4. **aikm_viewer blocked from audit_log** — 002:227 (parent REVOKE ALL), 002:240-241 (seed partitions), 002:195 (new partitions via helper), 002:248 (spillover). Gated by `v_viewer_denied` invariant at 002:342. **Safe.**
5. **Re-run idempotency** — `CREATE TABLE IF NOT EXISTS`, `CREATE OR REPLACE FUNCTION`, `ALTER ... OWNER TO` (no-op if same owner), `ALTER FUNCTION ... OWNER TO postgres` (no-op on second run), all GRANT/REVOKE are idempotent. **Safe.**
6. **`ensure_next_audit_partition()` creates partition then REVOKEs** — runs as DEFINER postgres with full authority; REVOKEs at 002:194-195 succeed. **Safe.**

### New adversarial angles (specific to the patch)

1. **SECURITY DEFINER abuse** — Function takes NO parameters (002:171); no user input. `SET search_path = public, pg_temp` present (002:175). Cannot be hijacked via search_path. Dynamic SQL uses `format(%I, pname)` where pname is server-computed from `to_char(NOW(), 'YYYY_MM')` — not user-controllable. **Safe.**
2. **`aikm` grant drift on helper-created partitions** — Verified 002:196 `GRANT INSERT, SELECT ... TO aikm` runs for every new partition. Without this, aikm would lose write access after ownership transfer. **Safe.**
3. **`aikm_viewer` default EXECUTE via PUBLIC on new function** — 001:142 `REVOKE EXECUTE ON ALL FUNCTIONS ... FROM aikm_viewer` runs BEFORE `ensure_next_audit_partition()` is created (002 runs later). 001:152 `ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM aikm_viewer` covers future functions. However — `ALTER DEFAULT PRIVILEGES` applies only to functions created by the role that ran it (postgres) unless `FOR ROLE` is specified. 001:152 has no FOR ROLE → defaults to current_user=postgres. **002 runs as postgres, creates the function → default-REVOKE DOES apply. Safe.** Additionally, since PG 15+ the default is no PUBLIC EXECUTE on new functions anyway. Belt-and-suspenders covered.

### New findings

None. No new CRITICAL / HIGH. Minor observations (non-blocking):
- **Nit** — `ensure_next_audit_partition()` does not grant EXECUTE on the newly created partition's sequence, but since the partition shares the parent's BIGSERIAL via partition inheritance, no separate sequence grant is needed. Confirmed safe.
- **Nit** — `quickstart.md` Pre-flight row 4 lists `pg_prewarm, plperlu, plpythonu, plsh, adminpack` but omits the newly denylisted `plv8, plluau, pltclu`. Minor — the DO block in 001 catches them regardless. Consider updating pre-flight SQL for operator clarity. Not blocking.

### Final verdict: **APPROVE**

### Ready to deploy: **YES**

All three Round-1 CRITICAL findings are VERIFIED_FIXED. Verification blocks gate exit code. Re-run-twice idempotency holds on a fresh `postgres:16-alpine`. T-003 acceptance gate satisfiable.
