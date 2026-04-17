-- Migration 004: Add domain_group column to maximo_table_catalog
-- Groups tables by business domain for better organization and filtering

ALTER TABLE maximo_table_catalog ADD COLUMN IF NOT EXISTS domain_group VARCHAR(30) DEFAULT 'general';

UPDATE maximo_table_catalog SET domain_group = 'workorder' WHERE object_name = 'WORKORDER' OR table_name LIKE '%wo%' OR table_name LIKE '%workorder%';
UPDATE maximo_table_catalog SET domain_group = 'asset' WHERE object_name = 'ASSET' OR table_name LIKE '%asset%';
UPDATE maximo_table_catalog SET domain_group = 'fault' WHERE object_name = 'SR' OR table_name LIKE '%fault%' OR table_name LIKE '%sr%';

COMMENT ON COLUMN maximo_table_catalog.domain_group IS '領域分組：asset/workorder/fault/inventory/procurement/operation/general';
