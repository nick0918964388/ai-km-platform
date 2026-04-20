#!/usr/bin/env bash
# /usr/local/bin/pg_viewer_partition_ensure.sh
# Nightly partition healthcheck + spillover alert.
# Schedule: 0 2 * * *  (daily 02:00)
# Identity: aikm (application superuser in this env)
#
# 1. Calls ensure_next_audit_partition() — creates next month's partition if absent.
# 2. Verifies partition tree covers tomorrow + next month.
# 3. Alerts if spillover table received rows in the past 24h.
# Webhook (Discord) fires on any anomaly; degrades gracefully if ALERT_WEBHOOK_URL unset.
set -euo pipefail

source /etc/aikm/.env

PSQL="docker exec -i aikm-postgres psql -U aikm -d aikm"

echo "[pg-viewer-partition] $(date -u +%Y-%m-%dT%H:%M:%SZ) starting healthcheck"

# 1. Ensure next month's partition exists (idempotent).
RESULT=$(${PSQL} -v ON_ERROR_STOP=1 -tAc \
  "SELECT partition_name || '|created=' || created FROM ensure_next_audit_partition()")
echo "[pg-viewer-partition] ensure_next_audit_partition => ${RESULT}"

# 2. Verify partition tree covers tomorrow + next month.
COVERED=$(${PSQL} -v ON_ERROR_STOP=1 -tAc "
  SELECT bool_and(EXISTS (
    SELECT 1 FROM pg_inherits i
    JOIN pg_class c ON c.oid = i.inhrelid
    JOIN pg_class p ON p.oid = i.inhparent
    WHERE p.relname = 'pg_viewer_audit_log'
      AND c.relname = 'pg_viewer_audit_log_' || to_char(d, 'YYYY_MM')))
  FROM (VALUES (CURRENT_DATE + INTERVAL '1 day'),
               (CURRENT_DATE + INTERVAL '1 month')) AS t(d);
")

if [ "${COVERED}" != "t" ]; then
  echo "[pg-viewer-partition] ALERT: partition coverage gap detected" >&2
  if [ -n "${ALERT_WEBHOOK_URL:-}" ]; then
    curl -sS -X POST "${ALERT_WEBHOOK_URL}" \
      -H "Content-Type: application/json" \
      -d '{"content":"[pg-viewer] ALERT: audit_log partition coverage gap — next-month partition may be missing. Check ensure_next_audit_partition()."}' || true
  fi
  exit 2
fi

echo "[pg-viewer-partition] partition coverage: OK"

# 3. Alert if spillover has rows from the last 24h.
SPILL=$(${PSQL} -v ON_ERROR_STOP=1 -tAc \
  "SELECT count(*) FROM pg_viewer_audit_log_spillover WHERE spilled_at > NOW() - INTERVAL '1 day'")
SPILL="${SPILL// /}"

if [ "${SPILL}" -gt 0 ]; then
  echo "[pg-viewer-partition] ALERT: ${SPILL} spillover row(s) in last 24h" >&2
  if [ -n "${ALERT_WEBHOOK_URL:-}" ]; then
    curl -sS -X POST "${ALERT_WEBHOOK_URL}" \
      -H "Content-Type: application/json" \
      -d "{\"content\":\"[pg-viewer] ALERT: pg_viewer_audit_log_spillover has ${SPILL} row(s) in the last 24h — partition cron may have failed\"}" || true
  fi
  exit 3
fi

echo "[pg-viewer-partition] spillover check: 0 rows — OK"
echo "[pg-viewer-partition] healthcheck complete"
