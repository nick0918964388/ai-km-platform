#!/usr/bin/env bash
# pg_viewer_cron_install.sh
# Deploys retention purge + partition healthcheck crons to the target host.
# Usage: ./backend/scripts/pg_viewer_cron_install.sh [deploy_host]
# Default host: root@192.168.1.11
set -euo pipefail

HOST="${1:-root@192.168.1.11}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[cron-install] deploying to ${HOST}"

# Ensure /etc/aikm/.env exists with required vars; create skeleton if absent.
ssh "${HOST}" 'bash -s' <<'REMOTECHECK'
if [ ! -f /etc/aikm/.env ]; then
  mkdir -p /etc/aikm
  cat > /etc/aikm/.env <<'ENVEOF'
# pg-viewer (013) — fill in real values before running migrations
PG_VIEWER_ENABLED=true
PG_VIEWER_PASSWORD=CHANGE_ME
PG_VIEWER_DATABASE_URL=postgresql+asyncpg://aikm_viewer:${PG_VIEWER_PASSWORD}@postgres:5432/aikm
PG_VIEWER_ROW_LIMIT=1000
PG_VIEWER_STMT_TIMEOUT_MS=10000
PG_VIEWER_SQL_MAX_LEN=8000
PG_VIEWER_AUDIT_RETENTION_DAYS=180
PG_VIEWER_RATE_LIMIT_SQL=30
PG_VIEWER_RATE_LIMIT_ROWS=60
PG_AUDIT_PURGER_PASSWORD=CHANGE_ME
PG_AUDIT_PURGER_DATABASE_URL=postgresql://aikm_audit_purger:${PG_AUDIT_PURGER_PASSWORD}@postgres:5432/aikm
ALERT_WEBHOOK_URL=
ENVEOF
  chmod 600 /etc/aikm/.env
  echo "[cron-install] created /etc/aikm/.env skeleton — fill in passwords before use"
else
  echo "[cron-install] /etc/aikm/.env already exists"
fi
REMOTECHECK

# Copy shell scripts to /usr/local/bin/
scp "${SCRIPT_DIR}/pg_viewer_retention_purge.sh" \
    "${SCRIPT_DIR}/pg_viewer_partition_ensure.sh" \
    "${HOST}:/usr/local/bin/"

ssh "${HOST}" 'chmod +x /usr/local/bin/pg_viewer_retention_purge.sh /usr/local/bin/pg_viewer_partition_ensure.sh'
echo "[cron-install] shell scripts installed and made executable"

# Copy cron files to /etc/cron.d/
scp "${SCRIPT_DIR}/cron/pg-viewer-purge.cron" \
    "${SCRIPT_DIR}/cron/pg-viewer-partition.cron" \
    "${HOST}:/etc/cron.d/"

ssh "${HOST}" 'chown root:root /etc/cron.d/pg-viewer-purge.cron /etc/cron.d/pg-viewer-partition.cron && chmod 644 /etc/cron.d/pg-viewer-purge.cron /etc/cron.d/pg-viewer-partition.cron'
echo "[cron-install] cron files installed"

echo "[cron-install] verifying..."
ssh "${HOST}" 'ls -la /usr/local/bin/pg_viewer_*.sh && ls -la /etc/cron.d/pg-viewer-*.cron'

echo "[cron-install] done. Verify cron daemon: ssh ${HOST} systemctl status cron"
