-- Transform raw mxwo into 012-derived PM and CM workorder tables.
-- Idempotent: TRUNCATE + INSERT (rebuild from scratch).
-- Run: docker exec -i aikm-postgres psql -U aikm -d aikm < maximo_transform_mxwo_to_workorders.sql
--
-- Source: maximo_mxwo (raw ETL, 13 columns, all text).
-- Worktype split: PM = 1A/2A/3A/4A (per spec 012); everything else = CM.
-- Fields not present in raw mxwo set to NULL (description, owner_group,
--   maintenance_section, ticket_id, failure_code, kilometers, work_hours,
--   long_description, target_start_date, target_comp_date, repair_proc,
--   car_in_result, car_out_result).
-- Date columns are ISO8601 text -> timestamptz via NULLIF-empty-to-NULL.

BEGIN;

TRUNCATE maximo_pm_workorders RESTART IDENTITY;

INSERT INTO maximo_pm_workorders (
    wonum, description, status, assetnum, work_type, owner_group,
    maintenance_section, report_date, act_start, act_finish,
    last_act_finish, car_in_result, car_out_result, kilometers,
    failure_code, synced_at
)
SELECT
    wonum,
    NULL,                                               -- description: not in raw
    status,
    assetnum,
    worktype,
    NULL,                                               -- owner_group
    NULL,                                               -- maintenance_section
    NULLIF(reportdate, '')::timestamptz,
    COALESCE(NULLIF(actstart, ''), NULLIF(zz_actstart, ''))::timestamptz,
    COALESCE(NULLIF(actfinish, ''), NULLIF(zz_actfinish, ''))::timestamptz,
    NULLIF(zz_actfinish, '')::timestamptz,              -- last_act_finish ~= zz_actfinish
    NULL, NULL,                                         -- car_in/out_result
    NULL,                                               -- kilometers
    NULL,                                               -- failure_code
    now()
FROM maximo_mxwo
WHERE worktype IN ('1A','2A','3A','4A')
ON CONFLICT (wonum) DO NOTHING;

TRUNCATE maximo_cm_workorders RESTART IDENTITY;

INSERT INTO maximo_cm_workorders (
    wonum, description, long_description, status, assetnum, work_type,
    owner_group, maintenance_section, ticket_id, report_date, act_start,
    act_finish, target_start_date, target_comp_date, failure_code,
    repair_proc, kilometers, work_hours, synced_at
)
SELECT
    wonum,
    NULL, NULL,                                         -- description, long_description
    status,
    assetnum,
    worktype,
    NULL, NULL, NULL,                                   -- owner_group, maintenance_section, ticket_id
    NULLIF(reportdate, '')::timestamptz,
    COALESCE(NULLIF(actstart, ''), NULLIF(zz_actstart, ''))::timestamptz,
    COALESCE(NULLIF(actfinish, ''), NULLIF(zz_actfinish, ''))::timestamptz,
    NULL, NULL,                                         -- target_start_date, target_comp_date
    NULL, NULL,                                         -- failure_code, repair_proc
    NULL, NULL,                                         -- kilometers, work_hours
    now()
FROM maximo_mxwo
WHERE worktype NOT IN ('1A','2A','3A','4A') OR worktype IS NULL
ON CONFLICT (wonum) DO NOTHING;

COMMIT;

-- Verification
SELECT 'pm' AS t, count(*) FROM maximo_pm_workorders
UNION ALL
SELECT 'cm', count(*) FROM maximo_cm_workorders;
