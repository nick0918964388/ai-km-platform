-- Fix date columns stored as TEXT → convert to TIMESTAMPTZ
-- All values are ISO 8601 format (e.g., '2026-04-06T00:00:00+08:00')

-- maximo_mxsr (故障通報) — 12 date columns
ALTER TABLE maximo_mxsr
  ALTER COLUMN zz_entrydate TYPE TIMESTAMPTZ USING NULLIF(zz_entrydate, '')::TIMESTAMPTZ,
  ALTER COLUMN reportdate TYPE TIMESTAMPTZ USING NULLIF(reportdate, '')::TIMESTAMPTZ,
  ALTER COLUMN statusdate TYPE TIMESTAMPTZ USING NULLIF(statusdate, '')::TIMESTAMPTZ,
  ALTER COLUMN zz_startdate TYPE TIMESTAMPTZ USING NULLIF(zz_startdate, '')::TIMESTAMPTZ,
  ALTER COLUMN zz_issuedate TYPE TIMESTAMPTZ USING NULLIF(zz_issuedate, '')::TIMESTAMPTZ,
  ALTER COLUMN zz_confirm_date TYPE TIMESTAMPTZ USING NULLIF(zz_confirm_date, '')::TIMESTAMPTZ,
  ALTER COLUMN zz_modify_date TYPE TIMESTAMPTZ USING NULLIF(zz_modify_date, '')::TIMESTAMPTZ,
  ALTER COLUMN zz_received_date TYPE TIMESTAMPTZ USING NULLIF(zz_received_date, '')::TIMESTAMPTZ,
  ALTER COLUMN zz_require_date TYPE TIMESTAMPTZ USING NULLIF(zz_require_date, '')::TIMESTAMPTZ,
  ALTER COLUMN zz_from_vendor_date TYPE TIMESTAMPTZ USING NULLIF(zz_from_vendor_date, '')::TIMESTAMPTZ,
  ALTER COLUMN zz_to_vendor_date TYPE TIMESTAMPTZ USING NULLIF(zz_to_vendor_date, '')::TIMESTAMPTZ,
  ALTER COLUMN zz_im_time TYPE TIMESTAMPTZ USING NULLIF(zz_im_time, '')::TIMESTAMPTZ;

-- maximo_mxwo (工單) — 4 date columns
ALTER TABLE maximo_mxwo
  ALTER COLUMN reportdate TYPE TIMESTAMPTZ USING NULLIF(reportdate, '')::TIMESTAMPTZ,
  ALTER COLUMN actstart TYPE TIMESTAMPTZ USING NULLIF(actstart, '')::TIMESTAMPTZ,
  ALTER COLUMN changedate TYPE TIMESTAMPTZ USING NULLIF(changedate, '')::TIMESTAMPTZ,
  ALTER COLUMN zz_actstart TYPE TIMESTAMPTZ USING NULLIF(zz_actstart, '')::TIMESTAMPTZ;

-- maximo_mxasset (資產) — 1 date column
ALTER TABLE maximo_mxasset
  ALTER COLUMN statusdate TYPE TIMESTAMPTZ USING NULLIF(statusdate, '')::TIMESTAMPTZ;

-- maximo_mxasset_classstructure — 1 date column
ALTER TABLE maximo_mxasset_classstructure
  ALTER COLUMN zz_changedate TYPE TIMESTAMPTZ USING NULLIF(zz_changedate, '')::TIMESTAMPTZ;

-- Create indexes on frequently queried date columns
CREATE INDEX IF NOT EXISTS idx_mxsr_entrydate ON maximo_mxsr(zz_entrydate);
CREATE INDEX IF NOT EXISTS idx_mxsr_reportdate ON maximo_mxsr(reportdate);
CREATE INDEX IF NOT EXISTS idx_mxwo_reportdate ON maximo_mxwo(reportdate);
CREATE INDEX IF NOT EXISTS idx_mxwo_actstart ON maximo_mxwo(actstart);
