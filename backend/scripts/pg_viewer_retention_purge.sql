-- =============================================================================
-- Feature       : 013-postgres-viewer
-- Script        : pg_viewer_retention_purge.sql
-- Purpose       : Manual / idempotent purge of old audit-log partitions
--                 + csp_violation_log rows older than 30 days.
-- Runs as       : aikm_audit_purger (owns partitions; required for DROP TABLE)
--                 EXCEPT the csp block which runs as aikm.
-- Usage         : docker exec -i -e PGPASSWORD="$PG_AUDIT_PURGER_PASSWORD" \
--                   aikm-postgres psql -U aikm_audit_purger -d aikm \
--                   -v retention_days=180 \
--                   < backend/scripts/pg_viewer_retention_purge.sql
-- Idempotency   : DROP TABLE IF EXISTS — safe to re-run.
-- =============================================================================

\set ON_ERROR_STOP on

-- Compute cutoff: partitions whose relname < pg_viewer_audit_log_CUTOFF are dropped.
-- The :retention_days variable defaults to 180 if not supplied via -v.
\if :{?retention_days}
\else
  \set retention_days 180
\endif

DO $purge$
DECLARE
  part           RECORD;
  cutoff_date    DATE   := CURRENT_DATE - (:retention_days || ' days')::INTERVAL;
  cutoff_suffix  TEXT   := to_char(cutoff_date, 'YYYY_MM');
  cutoff_name    TEXT   := 'pg_viewer_audit_log_' || cutoff_suffix;
  dropped_count  INT    := 0;
BEGIN
  RAISE NOTICE 'Purge start: retention_days=%, cutoff_name=%', :retention_days, cutoff_name;

  FOR part IN
    SELECT c.relname AS name
      FROM pg_inherits  i
      JOIN pg_class     c ON c.oid = i.inhrelid
      JOIN pg_class     p ON p.oid = i.inhparent
     WHERE p.relname = 'pg_viewer_audit_log'
       AND c.relname < cutoff_name
     ORDER BY c.relname
  LOOP
    RAISE NOTICE 'Dropping partition: %', part.name;
    EXECUTE format('DROP TABLE IF EXISTS public.%I', part.name);
    dropped_count := dropped_count + 1;
  END LOOP;

  RAISE NOTICE 'Purge complete: % partition(s) dropped', dropped_count;
END $purge$;
