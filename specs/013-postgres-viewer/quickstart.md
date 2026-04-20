# Quickstart — PostgreSQL Online Viewer

Audience: engineer picking up a Task Prompt from `tasks.md`.
Reminder: all runtime services live on **192.168.1.11**. Mac Mini is code-only.

---

## 0. Before you start

- Read **`spec.md`** (esp. the "Open Clarifications" block and FRs).
- Read **`plan.md`** §"Security Model".
- Confirm with user whether C-1 … C-6 have been resolved. If not, **STOP** — the task set depends on those answers.

---

## 1. Worktree & branch

```bash
cd /Volumes/kingston/Projects/ai-km-platform-013-postgres-viewer
git status   # must show branch 013-postgres-viewer, clean
git fetch origin && git rebase origin/main   # keep current with main
```

Do not work in `/Volumes/kingston/Projects/ai-km-platform` — that's 012.

---

## 2. Local verification of the migration (on 192.168.1.11)

> Do not run on Mac Mini. The aikm-postgres container only exists on 192.168.1.11.

### Pre-flight checklist — T-003 acceptance gate (2026-04-20)

Before running either migration, verify ALL four conditions. Any `f` / empty / wrong value means **STOP and fix the environment first**.

| # | Check | Command | Required output |
|---|---|---|---|
| 1 | Superuser identity for 001 | `docker exec aikm-postgres psql -U postgres -d aikm -tAc "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"` | `t` |
| 2 | Connection budget | `docker exec aikm-postgres psql -U postgres -c "SHOW max_connections"` | `>= 200` |
| 3 | Dangerous extensions absent | `docker exec aikm-postgres psql -U postgres -d aikm -tAc "SELECT string_agg(extname, ',') FROM pg_extension WHERE extname IN ('dblink','postgres_fdw','file_fdw','pg_prewarm','plperlu','plpythonu','plsh','adminpack')"` | empty line (if non-empty, 001 aborts with RAISE EXCEPTION) |
| 4 | Two passwords in env | `grep -cE '^(PG_VIEWER_PASSWORD|PG_AUDIT_PURGER_PASSWORD)=' /etc/aikm/.env` | `2` |

Migration invocations (copy-paste):

```bash
# 001 — as postgres superuser, BOTH -v vars required
docker exec -i aikm-postgres psql -U postgres -d aikm \
  -v ON_ERROR_STOP=1 \
  -v pg_viewer_password="$PG_VIEWER_PASSWORD" \
  -v pg_audit_purger_password="$PG_AUDIT_PURGER_PASSWORD" \
  < backend/scripts/pg_viewer_migrate_001_role_and_grants.sql

# 002 — ALSO as postgres superuser (post-critic C1/C2 fix 2026-04-20).
#       Rationale: 002 issues ALTER TABLE ... OWNER TO aikm_audit_purger plus
#       REVOKE/GRANT on tables owned by aikm_audit_purger; aikm is neither a
#       member of that role nor the owner after the transfer, so would fail.
docker exec -i aikm-postgres psql -U postgres -d aikm \
  -v ON_ERROR_STOP=1 \
  < backend/scripts/pg_viewer_migrate_002_audit_table.sql
```

Both migrations are idempotent — re-running them on a clean DB must produce the same verification output; re-running on an already-migrated DB re-asserts grants without error. T-003 acceptance: execute the pair twice against a fresh `postgres:16-alpine` + `aikm` database and confirm both verification SELECTs report all-pass on both runs.

### 2a. Pre-flight (MANDATORY before first run — post-critic C1 ops)

```bash
ssh user@192.168.1.11
# 1. Confirm superuser is available for 001
docker exec aikm-postgres psql -U postgres -d aikm -tAc \
  "SELECT rolsuper FROM pg_roles WHERE rolname='postgres'"
# Must print: t — otherwise abort, you lack privileges to CREATE ROLE.

# 2. Confirm connection budget
docker exec aikm-postgres psql -U postgres -c "SHOW max_connections"
# Must be >= 200. If lower, add a max_connections bump to postgresql.conf before deploying.

# 3. Detect pg_partman availability (R2 N2 resolution 2026-04-20)
docker exec aikm-postgres psql -U postgres -d aikm -tAc \
  "SELECT 1 FROM pg_available_extensions WHERE name='pg_partman'"
# If prints 1 → postgres:16-alpine has pg_partman — operator may opt in by running
#               CREATE EXTENSION pg_partman + pg_partman.create_parent(...) post-002.
# If empty     → postgres:16-alpine has NO pg_partman (the default today) — the shell+SQL
#               fallback ensure_next_audit_partition() installed by 002 handles it;
#               install the nightly cron in §10 below. Document which path you chose.

# 4. Generate TWO passwords ONCE — URL-safe hex (post-critic H3 ops + R2 M1)
openssl rand -hex 32       # → put in /etc/aikm/.env as PG_VIEWER_PASSWORD
openssl rand -hex 32       # → put in /etc/aikm/.env as PG_AUDIT_PURGER_PASSWORD

# 5. Wire the DSNs (note: hex is always URL-safe; base64 is NOT — avoid base64)
cat >> /etc/aikm/.env <<'EOF'
PG_VIEWER_PASSWORD=<hex-from-step-4-first>
PG_AUDIT_PURGER_PASSWORD=<hex-from-step-4-second>
PG_VIEWER_DATABASE_URL=postgresql+asyncpg://aikm_viewer:${PG_VIEWER_PASSWORD}@postgres:5432/aikm
PG_AUDIT_PURGER_DATABASE_URL=postgresql://aikm_audit_purger:${PG_AUDIT_PURGER_PASSWORD}@postgres:5432/aikm
EOF

# 6. Pause ETL to avoid AccessShareLock contention during GRANT iteration (critic M1 ops)
docker compose stop aikm-maximo-extractor
```

### 2b. Apply 001 (run as postgres superuser)

```bash
cd /path/to/ai-km-platform-013-postgres-viewer
source /etc/aikm/.env

docker exec -i aikm-postgres psql -U postgres -d aikm \
  -v pg_viewer_password="$PG_VIEWER_PASSWORD" \
  -v pg_audit_purger_password="$PG_AUDIT_PURGER_PASSWORD" \
  -v ON_ERROR_STOP=1 \
  < backend/scripts/pg_viewer_migrate_001_role_and_grants.sql
# Expected final row:
#   can_select_users=f, can_insert_users=f, can_create_schema=f, can_select_view=t,
#   role_aikm_viewer=t, role_aikm_audit_purger=t, view_users_public=t,
#   aikm_viewer_denied_users=t, aikm_viewer_granted_users_public=t
```

### 2c. Apply 002 (run as postgres superuser — post-critic C1/C2 fix)

> **Changed from `-U aikm` to `-U postgres` on 2026-04-20.** 002 transfers
> ownership of the partitioned audit log to `aikm_audit_purger`, then issues
> REVOKE/GRANT against it. Both operations require superuser (`aikm` is not
> a member of `aikm_audit_purger`, and after the transfer is not the owner).

```bash
docker exec -i aikm-postgres psql -U postgres -d aikm \
  -v ON_ERROR_STOP=1 \
  < backend/scripts/pg_viewer_migrate_002_audit_table.sql
# Expected final row:
#   aikm_insert=t, aikm_select=t, aikm_update=f, viewer_select=f,
#   partition_2026_04_exists=t, partition_2026_05_exists=t,
#   spillover_exists=t, aikm_append_only=t, aikm_viewer_denied_audit=t,
#   purger_owns_parent=t
# Plus: trailing DO $verify$ block raises EXCEPTION (nonzero exit) on any
# invariant violation — CI can rely on psql exit code directly.
```

### 2d. Re-check grants + restart ETL

```bash
docker exec aikm-postgres psql -U postgres -d aikm -c "
  SELECT has_table_privilege('aikm_viewer', 'public.users',         'SELECT') AS can_select_users,
         has_table_privilege('aikm_viewer', 'public.users_public',  'SELECT') AS can_select_view,
         has_table_privilege('aikm_viewer', 'public.maximo_mxwo',   'INSERT') AS can_insert_mxwo,
         has_schema_privilege('aikm_viewer','public', 'CREATE')                AS can_create;
"
# Must print: f, t, f, f

docker compose start aikm-maximo-extractor
```

---

## 3. Backend picking up a task (T-01x / T-02x)

```bash
# On Mac Mini — edit code only
code backend/app/services/pg_viewer/
# Do NOT run uvicorn locally. DOCKER ONLY.
# To sanity-check imports / types without services:
cd backend && python -c "from app.services.pg_viewer.engine import get_viewer_db"  # should not raise
```

To actually run the feature:

```bash
# SSH to deployment host
ssh user@192.168.1.11
cd /path/to/repo
git pull origin 013-postgres-viewer
docker compose up -d --build backend
docker compose logs -f backend
```

---

## 4. Frontend picking up a task (T-03x)

```bash
# Mac Mini — edits only
code frontend/src/app/\(main\)/admin/pg-viewer/
# Do NOT `npm run dev`. DOCKER ONLY.
```

Deploy same way:

```bash
ssh user@192.168.1.11 && cd /path/to/repo && git pull && docker compose up -d --build frontend
```

Verify at `http://192.168.1.11:3000/admin/pg-viewer` after logging in as an admin account.

---

## 5. Testing a browse flow end-to-end

After deploy:

```bash
# Get a JWT for an admin user (assumes /api/auth/login exists)
TOKEN=$(curl -s -X POST http://192.168.1.11:8000/api/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"admin@example.com","password":"..."}' | jq -r .access_token)

# List tables
curl -s http://192.168.1.11:8000/api/pg-viewer/tables -H "authorization: Bearer $TOKEN" | jq '.tables | length'

# Fetch schema
curl -s 'http://192.168.1.11:8000/api/pg-viewer/tables/maximo_mxwo/schema' -H "authorization: Bearer $TOKEN" | jq '.columns | length'

# First page of rows
curl -s 'http://192.168.1.11:8000/api/pg-viewer/tables/maximo_mxwo/rows?limit=50&order_by=wonum&order_dir=DESC' \
  -H "authorization: Bearer $TOKEN" | jq '.rows | length'

# Filtered
curl -sG 'http://192.168.1.11:8000/api/pg-viewer/tables/maximo_mxwo/rows' \
  --data-urlencode 'limit=20' \
  --data-urlencode 'filters=[{"column":"status","op":"=","value":"APPR"}]' \
  -H "authorization: Bearer $TOKEN" | jq '.rows[0]'

# Audit
curl -s 'http://192.168.1.11:8000/api/pg-viewer/audit?limit=10' -H "authorization: Bearer $TOKEN" | jq
```

---

## 5b. Testing the SQL editor (US5)

```bash
# Positive: simple SELECT — should succeed
curl -s -X POST http://192.168.1.11:8000/api/pg-viewer/sql \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"sql":"SELECT * FROM users LIMIT 5"}' | jq
# Expect: {columns:[...], rows:[...], row_count:5, elapsed_ms:<n>, truncated:false}

# Positive: aggregation
curl -s -X POST http://192.168.1.11:8000/api/pg-viewer/sql \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"sql":"SELECT status, COUNT(*) AS c FROM maximo_mxwo GROUP BY status ORDER BY c DESC"}' | jq

# Positive: no LIMIT — server auto-injects LIMIT 1000
curl -s -X POST http://192.168.1.11:8000/api/pg-viewer/sql \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"sql":"SELECT * FROM maximo_mxwo"}' | jq '{row_count, truncated, notice}'
# Expect: row_count=1000, truncated=true, notice≈"LIMIT 1000 auto-appended"

# Negative: DDL — must be rejected BEFORE hitting the DB
curl -i -X POST http://192.168.1.11:8000/api/pg-viewer/sql \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"sql":"DROP TABLE users"}'
# Expect: HTTP/1.1 400 Bad Request
#         {"detail":"forbidden keyword: DROP"}

# Positive: single trailing semicolon is tolerated
curl -i -X POST http://192.168.1.11:8000/api/pg-viewer/sql \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"sql":"SELECT 1;"}'
# Expect: HTTP/1.1 200 — one trailing `;` is fine (post-critic M-8 consistency positive example)

# Negative: TWO statements, each with `;`
curl -i -X POST http://192.168.1.11:8000/api/pg-viewer/sql \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"sql":"SELECT 1; SELECT 2;"}'
# Expect: 400 {"detail":"multi-statement input not allowed"}

# Negative: LIMIT > 1000 (post-critic H5 reject-not-clamp)
curl -i -X POST http://192.168.1.11:8000/api/pg-viewer/sql \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"sql":"SELECT * FROM maximo_mxwo LIMIT 5000"}'
# Expect: 400 {"detail":"row limit exceeded (server-side cap 1000)"}

# Negative: forbidden FUNCTION (pg_sleep)
curl -i -X POST http://192.168.1.11:8000/api/pg-viewer/sql \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"sql":"SELECT pg_sleep(30)"}'
# Expect: 400 {"detail":"forbidden function: pg_sleep"} — rejected pre-DB (post-critic C3 security)
# (statement_timeout is still active as a third-layer defense — see FR-012)

# Negative: DML disguised as CTE
curl -i -X POST http://192.168.1.11:8000/api/pg-viewer/sql \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"sql":"WITH t AS (DELETE FROM users RETURNING *) SELECT * FROM t"}'
# Expect: 400 {"detail":"forbidden keyword: DELETE"}

# Negative: timeout
curl -i -X POST http://192.168.1.11:8000/api/pg-viewer/sql \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"sql":"SELECT pg_sleep(30)"}'
# Expect: HTTP/1.1 408, audit row status='timeout'

# Verify audit captured the SQL editor attempts
curl -s 'http://192.168.1.11:8000/api/pg-viewer/audit?limit=20' \
  -H "authorization: Bearer $TOKEN" | jq '.entries[] | select(.query_type=="sql_editor") | {status, raw_sql, row_count}'
```

---

## 6. Attempting attacks (what vuln-verifier will do in T-041)

```bash
# Non-admin token → 403
curl -i -H "authorization: Bearer $USER_TOKEN" http://192.168.1.11:8000/api/pg-viewer/tables
# Expect: HTTP/1.1 403

# Unknown table → 404
curl -i -H "authorization: Bearer $TOKEN" http://192.168.1.11:8000/api/pg-viewer/tables/bogus_table/rows
# Expect: HTTP/1.1 404

# Bad operator → 400
curl -sG "http://192.168.1.11:8000/api/pg-viewer/tables/users/rows" \
  --data-urlencode 'filters=[{"column":"email","op":";DROP TABLE users--","value":"x"}]' \
  -H "authorization: Bearer $TOKEN"
# Expect: 400

# limit=100000 → clamped
curl -sG "http://192.168.1.11:8000/api/pg-viewer/tables/users/rows?limit=100000" \
  -H "authorization: Bearer $TOKEN" | jq '.limit'
# Expect: 1000

# Write attempt at DB level (use PGPASSWORD; script-friendly — post-critic L6)
PGPASSWORD="$PG_VIEWER_PASSWORD" docker exec aikm-postgres psql -h postgres -U aikm_viewer -d aikm -c   "INSERT INTO users VALUES ('x','x','x','x','x')"
# Expect: ERROR: permission denied for table users
# (Note: aikm_viewer has NO SELECT on users either — this also fails with 42501 for SELECT.)

# Direct SELECT on sensitive table (post-critic C3 security — should also fail)
PGPASSWORD="$PG_VIEWER_PASSWORD" docker exec aikm-postgres psql -h postgres -U aikm_viewer -d aikm -c "SELECT * FROM users LIMIT 1"
# Expect: ERROR: permission denied for table users

# Direct SELECT on the curated view — should succeed
PGPASSWORD="$PG_VIEWER_PASSWORD" docker exec aikm-postgres psql -h postgres -U aikm_viewer -d aikm -c "SELECT id, email FROM users_public LIMIT 1"
# Expect: one row
```

---

## 7. When you're done with your task

- Run `critic` on your diff before opening a PR.
- Include a line in your P7-COMPLETION of the form:
  `驗收：<the specific acceptance bullets you verified>`
- Do not merge to main until the full test matrix in T-041 is green.

---

## 8. Rollback (if something goes wrong in prod)

### Preferred: flip feature flag (no data loss)

```bash
ssh user@192.168.1.11
sed -i 's/^PG_VIEWER_ENABLED=.*/PG_VIEWER_ENABLED=false/' /etc/aikm/.env
sed -i 's/^NEXT_PUBLIC_PG_VIEWER_ENABLED=.*/NEXT_PUBLIC_PG_VIEWER_ENABLED=false/' /etc/aikm/.env
docker compose up -d backend frontend
# Endpoints 404; SSR shows "Feature temporarily disabled" banner.
```

### Nuclear (PERMANENT REMOVAL — LOSES AUDIT HISTORY FOREVER)

> WARNING: only for full feature removal. The audit history has forensic value; prefer the flag flip above.

A plain `DROP ROLE` will fail with `role cannot be dropped because some objects depend on it` because `aikm_audit_purger` owns the partitioned audit-log tree (R2 M1). The correct incident-safe idiom uses `REASSIGN OWNED` + `DROP OWNED` (R2 N1 resolution):

```bash
docker exec aikm-postgres psql -U postgres -d aikm -c "
  -- 1. Move any objects owned by the two pg-viewer roles back to postgres so we can drop
  REASSIGN OWNED BY aikm_viewer         TO postgres;
  REASSIGN OWNED BY aikm_audit_purger   TO postgres;
  DROP OWNED BY     aikm_viewer;
  DROP OWNED BY     aikm_audit_purger;
  -- 2. Drop feature-owned objects
  DROP TABLE IF EXISTS pg_viewer_audit_log           CASCADE;
  DROP TABLE IF EXISTS pg_viewer_audit_log_spillover CASCADE;
  DROP FUNCTION IF EXISTS ensure_next_audit_partition();
  DROP VIEW  IF EXISTS users_public;
  -- 3. Sweep any residual grants (belt-and-suspenders)
  REVOKE ALL ON ALL TABLES IN SCHEMA public FROM aikm_viewer;
  REVOKE ALL ON SCHEMA public FROM aikm_viewer;
  REVOKE ALL ON SCHEMA public FROM aikm_audit_purger;
  -- 4. Drop roles
  DROP ROLE IF EXISTS aikm_viewer;
  DROP ROLE IF EXISTS aikm_audit_purger;
"
```

Existing features are untouched — this feature is orthogonal.

---

## 9. Rotating `PG_VIEWER_PASSWORD` + `PG_AUDIT_PURGER_PASSWORD` (post-critic H3 ops + R2 M1)

Two roles; rotate on the same 90-day cadence (or immediately on suspected leak).

```bash
# ── aikm_viewer (backend connects with this) ──
NEW_PW_VIEWER=$(openssl rand -hex 32)
docker exec aikm-postgres psql -U postgres -d aikm -c \
  "ALTER ROLE aikm_viewer WITH PASSWORD '$NEW_PW_VIEWER'"
sed -i "s/^PG_VIEWER_PASSWORD=.*/PG_VIEWER_PASSWORD=$NEW_PW_VIEWER/" /etc/aikm/.env
docker compose up -d backend           # recycle backend pool

# ── aikm_audit_purger (weekly purge cron connects with this) ──
NEW_PW_PURGER=$(openssl rand -hex 32)
docker exec aikm-postgres psql -U postgres -d aikm -c \
  "ALTER ROLE aikm_audit_purger WITH PASSWORD '$NEW_PW_PURGER'"
sed -i "s/^PG_AUDIT_PURGER_PASSWORD=.*/PG_AUDIT_PURGER_PASSWORD=$NEW_PW_PURGER/" /etc/aikm/.env
# Purge cron is invoked fresh each run; no pool to recycle.

# ── Smoke tests ──
curl -s http://192.168.1.11:8000/api/pg-viewer/tables -H "authorization: Bearer $ADMIN_JWT" | jq '.tables | length'
# Dry-run purge (no-op — zero rows under default 180d retention on a young deploy)
docker exec aikm-postgres psql -U aikm_audit_purger -d aikm -c \
  "SELECT count(*) FROM pg_viewer_audit_log_spillover"
```

Rotate at least every 90 days, or immediately on any suspected leak.

---

## 10. Retention purge + partition healthcheck (post-critic H1 ops + R2 M1/N2)

Three crons on 192.168.1.11:

| Purpose | Schedule | Script | Identity |
|---|---|---|---|
| Weekly purge (DROP old partitions) | `0 3 * * 0` Sun 03:00 | `/usr/local/bin/pg_viewer_retention_purge.sh` | `aikm_audit_purger` (R2 M1) |
| Nightly partition healthcheck | `0 2 * * *` every 02:00 | `/usr/local/bin/pg_viewer_partition_ensure.sh` | `aikm` |
| Nightly spillover alert | bundled in healthcheck | (same file) | `aikm` |

### 10a. Weekly purge (retention) — **R2 M1 fix: runs as aikm_audit_purger, NOT aikm**

The parent table is partitioned and append-only at the aikm role level (REVOKE UPDATE/DELETE/TRUNCATE). Purging is now `DROP TABLE pg_viewer_audit_log_YYYY_MM` — a DDL that aikm cannot issue. The dedicated `aikm_audit_purger` role owns every partition and can drop them.

See `backend/scripts/pg_viewer_retention_purge.sh` for the full script (shipped T-043).
Key behaviour: computes `CUTOFF=$(date -d "-${RETENTION_DAYS} days" +%Y_%m)`, then
DROP TABLEs all `pg_viewer_audit_log_*` partitions lexicographically less than
`pg_viewer_audit_log_${CUTOFF}` using `pg_inherits`. Also purges `csp_violation_log`
rows older than 30 days (guarded: skips silently if migration 003 not yet applied).

Install via the deploy helper (idempotent):
```bash
# From the repo root on Mac Mini (deploys to 192.168.1.11):
bash backend/scripts/pg_viewer_cron_install.sh root@192.168.1.11
```

The cron file installed at `/etc/cron.d/pg-viewer-purge.cron`:
```
0 3 * * 0 root /usr/local/bin/pg_viewer_retention_purge.sh >> /var/log/pg-viewer-purge.log 2>&1
```

### 10b. Nightly partition healthcheck (R2 N2 — prevents "no partition for date" INSERT failure)

See `backend/scripts/pg_viewer_partition_ensure.sh` for the full script (shipped T-043).
Steps performed:
1. Calls `ensure_next_audit_partition()` — creates next month's partition if absent.
2. Verifies partition tree covers tomorrow + next month via `pg_inherits`; exits 2 and fires webhook on gap.
3. Alerts if `pg_viewer_audit_log_spillover` has rows from the last 24h; exits 3 and fires webhook.
Webhook (`ALERT_WEBHOOK_URL` from `/etc/aikm/.env`) is Discord-compatible JSON `{"content":"..."}`.
Degrades gracefully when `ALERT_WEBHOOK_URL` is unset — alert is logged to stderr only.

Install via the deploy helper (same command installs both crons):
```bash
bash backend/scripts/pg_viewer_cron_install.sh root@192.168.1.11
```

The cron file installed at `/etc/cron.d/pg-viewer-partition.cron`:
```
0 2 * * * root /usr/local/bin/pg_viewer_partition_ensure.sh >> /var/log/pg-viewer-partition.log 2>&1
```

### 10c. Manual partition creation template (emergency / pre-seed)

Each partition keeps the append-only property — note the per-partition REVOKE (R2 partition-level REVOKE). Run as the parent owner `aikm_audit_purger`:

```sql
-- Template: replace YYYY_MM + date boundaries for the target month
CREATE TABLE IF NOT EXISTS pg_viewer_audit_log_YYYY_MM
  PARTITION OF pg_viewer_audit_log FOR VALUES FROM ('YYYY-MM-01') TO ('YYYY-MM-01'::date + INTERVAL '1 month');
ALTER TABLE pg_viewer_audit_log_YYYY_MM OWNER TO aikm_audit_purger;
REVOKE UPDATE, DELETE, TRUNCATE ON pg_viewer_audit_log_YYYY_MM FROM aikm;
REVOKE SELECT ON pg_viewer_audit_log_YYYY_MM FROM aikm_viewer;
GRANT INSERT, SELECT ON pg_viewer_audit_log_YYYY_MM TO aikm;
```

### 10d. pg_partman alternative (if extension is available — R2 N2 preferred path)

If §2a step 3 detected `pg_partman`, the operator may opt in **after 002** runs:

```sql
CREATE EXTENSION IF NOT EXISTS pg_partman;
SELECT pg_partman.create_parent(
  p_parent_table := 'public.pg_viewer_audit_log',
  p_control      := 'created_at',
  p_type         := 'native',
  p_interval     := 'monthly',
  p_premake      := 4    -- keep 4 months pre-created ahead of NOW()
);
-- Replace nightly healthcheck with:
SELECT pg_partman.run_maintenance('public.pg_viewer_audit_log');
```

If this path is chosen, the fallback `ensure_next_audit_partition()` function is kept but unused; the weekly DROP cron in §10a still works (partitions are partitions regardless of who created them).

### 10e. Env-var handoff to ops (note from R2 N3)

The `.env.example` file shipped in the main `ai-km-platform` repo MUST list these new vars; operators merging 013 must append them to `/etc/aikm/.env` before applying 001:

```
# pg-viewer (013)
PG_VIEWER_ENABLED=true
PG_VIEWER_PASSWORD=<openssl rand -hex 32>
PG_VIEWER_DATABASE_URL=postgresql+asyncpg://aikm_viewer:${PG_VIEWER_PASSWORD}@postgres:5432/aikm
PG_VIEWER_ROW_LIMIT=1000
PG_VIEWER_STMT_TIMEOUT_MS=10000
PG_VIEWER_SQL_MAX_LEN=8000
PG_VIEWER_AUDIT_RETENTION_DAYS=180
PG_VIEWER_RATE_LIMIT_SQL=30
PG_VIEWER_RATE_LIMIT_ROWS=60
PG_AUDIT_PURGER_PASSWORD=<openssl rand -hex 32>
PG_AUDIT_PURGER_DATABASE_URL=postgresql://aikm_audit_purger:${PG_AUDIT_PURGER_PASSWORD}@postgres:5432/aikm
AIKM_VIEWER_DB_URL=${PG_VIEWER_DATABASE_URL}       # alias used by legacy helper code
# Frontend
NEXT_PUBLIC_PG_VIEWER_ENABLED=true
```

docker-compose.yml `backend.environment` block must forward each of these. If the 013 worktree's `.env.example` differs from the main repo's, the T-042 deploy PR must update the main repo's `.env.example` and docker-compose.yml before `docker compose up -d`.
