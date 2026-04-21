-- Transform raw mxasset + mxsr into 012-derived assets + fault_reports tables.
-- Idempotent: TRUNCATE + INSERT (rebuild from scratch).
-- Run: docker exec -i aikm-postgres psql -U aikm -d aikm < maximo_transform_raw_to_derived.sql
--
-- Sources:
--   maximo_mxasset (all text)  -> maximo_assets
--   maximo_mxsr    (all text)  -> maximo_fault_reports
-- Fields missing in raw are NULL (documented inline).
-- Date columns are ISO8601 text -> timestamptz via NULLIF(empty) -> cast.

BEGIN;

-- ============================================================================
-- maximo_mxasset -> maximo_assets
-- ============================================================================
TRUNCATE maximo_assets RESTART IDENTITY;

INSERT INTO maximo_assets (
    assetnum, eq24, vehicle_type, vehicle_class, vehicle_category,
    workshop, section, borrow_section, status, status_desc,
    car_group, position, record_type, install_date, expected_life,
    manufacturer, failure_code, parent_assetnum, synced_at
)
SELECT
    assetnum,
    NULLIF(eq24, ''),
    NULLIF(eq4, ''),                     -- vehicle_type  EMU800 / EMU900 / ...
    NULLIF(eq3, ''),                     -- vehicle_class EMU / TEMU
    NULLIF(eq11, ''),                    -- vehicle_category RSTL / ...
    NULLIF(eq1, ''),                     -- workshop WAY00 / ...
    NULLIF(eq2, ''),                     -- section MMY20 / ...
    NULLIF(eq8, ''),                     -- borrow_section (often empty)
    NULLIF(status, ''),
    CASE NULLIF(status, '')
        WHEN 'OPERATING'      THEN '已啟用'
        WHEN 'DECOMMISSIONED' THEN '退役'
        WHEN 'INACTIVE'       THEN '停用'
        ELSE NULL
    END,
    NULL,                                -- car_group (not in raw; post-ETL-only)
    NULL,                                -- position  (not in raw)
    NULLIF(eq9, ''),                     -- record_type 車輛/車組/TOOL
    NULLIF(eq10, '')::timestamptz,       -- install_date
    NULL, NULL, NULL, NULL,              -- expected_life/manufacturer/failure_code/parent_assetnum
    now()
FROM maximo_mxasset
WHERE assetnum IS NOT NULL AND assetnum <> ''
ON CONFLICT (assetnum) DO NOTHING;

-- ============================================================================
-- maximo_mxsr -> maximo_fault_reports
-- ============================================================================
TRUNCATE maximo_fault_reports RESTART IDENTITY;

INSERT INTO maximo_fault_reports (
    ticketid, im_num, description, fault_symptom, handling_desc,
    status, status_desc, assetnum, incident_class, fault_location,
    tcms_code, grade, urgency, restricted_status, report_unit,
    occurrence_date, report_date, confirm_by, confirm_date,
    class_type, synced_at
)
SELECT
    ticketid,
    NULLIF(zz_imnum, ''),
    NULLIF(description, ''),
    NULL,                                -- fault_symptom (no longdesc in raw)
    NULL,                                -- handling_desc (no longdesc in raw)
    NULLIF(status, ''),
    NULLIF(status_description, ''),
    COALESCE(NULLIF(assetnum, ''), NULLIF(zz_eq24, '')),
    NULLIF(zz_incident_new_description, ''),
    NULLIF(zz_im_location, ''),
    NULLIF(zz_tcms, ''),
    NULLIF(zz_im_grade, ''),
    NULLIF(zz_urgency, ''),
    NULLIF(zz_restricted_status, ''),
    NULLIF(zz_personbelong, ''),
    NULLIF(zz_entrydate, '')::timestamptz,
    NULLIF(reportdate, '')::timestamptz,
    NULLIF(zz_confirm_by, ''),
    NULLIF(zz_confirm_date, '')::timestamptz,
    NULLIF(class, ''),
    now()
FROM maximo_mxsr
WHERE ticketid IS NOT NULL AND ticketid <> ''
ON CONFLICT (ticketid) DO NOTHING;

-- Refresh planner stats after bulk rebuild so Tool 1/3/7 pick good plans.
ANALYZE maximo_assets;
ANALYZE maximo_fault_reports;

COMMIT;

-- Verification
SELECT 'assets' AS t, count(*) FROM maximo_assets
UNION ALL
SELECT 'fault_reports', count(*) FROM maximo_fault_reports;
