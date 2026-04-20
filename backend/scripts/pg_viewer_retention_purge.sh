#!/usr/bin/env bash
# /usr/local/bin/pg_viewer_retention_purge.sh
# Weekly retention purge for pg_viewer_audit_log partitions + csp_violation_log rows.
# Schedule: 0 3 * * 0  (Sunday 03:00)
# Identity: aikm_audit_purger (owns partitions; can DROP TABLE)
#
# DROPs all monthly audit-log partitions whose name is lexicographically
# less than pg_viewer_audit_log_CUTOFF_YYYY_MM (i.e. older than retention window).
# Purges csp_violation_log rows older than 30 days using the aikm role.
set -euo pipefail

source /etc/aikm/.env

RETENTION_DAYS="${PG_VIEWER_AUDIT_RETENTION_DAYS:-180}"
# Compute CUTOFF as YYYY_MM of the month that is RETENTION_DAYS ago.
# Partitions strictly older than this month are eligible to drop.
CUTOFF=$(date -d "-${RETENTION_DAYS} days" +%Y_%m)

echo "[pg-viewer-purge] $(date -u +%Y-%m-%dT%H:%M:%SZ) retention_days=${RETENTION_DAYS} cutoff=${CUTOFF}"

docker exec -i \
  -e PGPASSWORD="${PG_AUDIT_PURGER_PASSWORD}" \
  aikm-postgres \
  psql -U aikm_audit_purger -d aikm -v ON_ERROR_STOP=1 <<SQL
DO \$purge\$
DECLARE
  part RECORD;
  cutoff_partition TEXT := 'pg_viewer_audit_log_${CUTOFF}';
BEGIN
  FOR part IN
    SELECT c.relname AS name
      FROM pg_inherits  i
      JOIN pg_class     c ON c.oid = i.inhrelid
      JOIN pg_class     p ON p.oid = i.inhparent
     WHERE p.relname = 'pg_viewer_audit_log'
       AND c.relname < cutoff_partition
  LOOP
    RAISE NOTICE 'dropping partition %', part.name;
    EXECUTE format('DROP TABLE IF EXISTS public.%I', part.name);
  END LOOP;
END \$purge\$;
SQL

echo "[pg-viewer-purge] audit partition purge complete"

# Purge csp_violation_log rows older than 30 days.
# csp_violation_log is owned by aikm — no purger perms required there.
# Guard: skip silently if table does not exist yet (migration 003 not yet applied).
docker exec -i \
  aikm-postgres \
  psql -U aikm -d aikm -v ON_ERROR_STOP=1 <<'CSPSQL'
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_class WHERE relname = 'csp_violation_log' AND relkind = 'r') THEN
    DELETE FROM csp_violation_log WHERE created_at < NOW() - INTERVAL '30 days';
    RAISE NOTICE 'csp_violation_log purge complete';
  ELSE
    RAISE NOTICE 'csp_violation_log does not exist yet — skipping';
  END IF;
END $$;
CSPSQL

echo "[pg-viewer-purge] csp_violation_log purge complete"
