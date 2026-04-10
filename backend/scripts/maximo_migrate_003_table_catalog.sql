-- maximo_migrate_003_table_catalog.sql
-- 建立 table catalog，供 RAG schema selector 使用

CREATE TABLE IF NOT EXISTS maximo_table_catalog (
    table_name   VARCHAR(100) PRIMARY KEY,
    object_name  VARCHAR(50),
    description  TEXT NOT NULL,
    key_columns  TEXT[] DEFAULT '{}',
    fk_relations JSONB DEFAULT '{}',
    row_count    INTEGER DEFAULT 0,
    indexed_at   TIMESTAMPTZ
);

-- 初始資料：Maximo extractor 原始表
INSERT INTO maximo_table_catalog (table_name, object_name, description, key_columns, fk_relations)
VALUES
    ('maximo_mxwo', 'WORKORDER',
     '工單資料表，包含維修工單、定期檢修工單。主要欄位：工單號(wonum)、車號(assetnum)、狀態(status)、工作類型(worktype)、說明(description)、實際開始/完工日期',
     ARRAY['wonum', 'assetnum', 'status', 'worktype'],
     '{"assetnum": "maximo_mxasset.assetnum"}'::jsonb),

    ('maximo_mxasset', 'ASSET',
     '車輛資產主檔，包含所有列車車輛與車組。主要欄位：資產編號(assetnum)、車號(eq24)、車型(vehicle_type)、狀態(status)、配屬段別、車組資訊',
     ARRAY['assetnum', 'status', 'eq24'],
     '{}'::jsonb),

    ('maximo_mxsr', 'SR',
     '故障通報/服務請求，記錄列車故障事件。主要欄位：通報號(ticketid)、車號(assetnum)、故障描述(description)、狀態(status)、故障等級、TCMS故障碼',
     ARRAY['ticketid', 'assetnum', 'status'],
     '{"assetnum": "maximo_mxasset.assetnum"}'::jsonb),

    ('maximo_pm_workorders', NULL,
     '定期檢修工單（ETL 產出），包含一級至四級定檢。主要欄位：wonum、assetnum、work_type(1A/2A/3A/4A)、status、act_start、act_finish',
     ARRAY['wonum', 'assetnum', 'status', 'work_type'],
     '{"assetnum": "maximo_assets.assetnum"}'::jsonb),

    ('maximo_cm_workorders', NULL,
     '維修/臨修工單（ETL 產出），包含一般臨修與委外維修。主要欄位：wonum、assetnum、work_type(T1/TR/CM)、ticket_id、failure_code、repair_proc',
     ARRAY['wonum', 'assetnum', 'status', 'work_type', 'ticket_id'],
     '{"assetnum": "maximo_assets.assetnum", "ticket_id": "maximo_fault_reports.ticketid"}'::jsonb),

    ('maximo_assets', NULL,
     '車輛資產主檔（ETL 產出），包含車號、車型、車種、配屬段別。主要欄位：assetnum、eq24、vehicle_type、status、section',
     ARRAY['assetnum', 'status', 'eq24', 'vehicle_type'],
     '{}'::jsonb),

    ('maximo_fault_reports', NULL,
     '故障通報（ETL 產出），記錄列車故障事件與處理情形。主要欄位：ticketid、assetnum、description、fault_symptom、tcms_code、grade',
     ARRAY['ticketid', 'assetnum', 'status'],
     '{"assetnum": "maximo_assets.assetnum"}'::jsonb)

ON CONFLICT (table_name) DO UPDATE SET
    object_name  = EXCLUDED.object_name,
    description  = EXCLUDED.description,
    key_columns  = EXCLUDED.key_columns,
    fk_relations = EXCLUDED.fk_relations;
