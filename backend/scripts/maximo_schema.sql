-- Maximo data tables for AI KM Platform
-- Run after init.sql

-- ─── 車輛主檔 ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS maximo_assets (
    id               SERIAL PRIMARY KEY,
    assetnum         VARCHAR(30) UNIQUE NOT NULL,
    eq24             VARCHAR(30),          -- 車號
    vehicle_type     VARCHAR(20),          -- EQ4: EMU900/EMU800/EMU3000...
    vehicle_class    VARCHAR(20),          -- EQ3: EMU/TEMU
    vehicle_category VARCHAR(30),          -- EQ11: 車輛類別代碼
    workshop         VARCHAR(20),          -- EQ1: 維修機廠
    section          VARCHAR(20),          -- EQ2: 配屬段別
    borrow_section   VARCHAR(20),          -- EQ8: 借用段別
    status           VARCHAR(20),          -- OPERATING/DECOMMISSIONED/...
    status_desc      VARCHAR(50),          -- 已啟用/停用/...
    car_group        VARCHAR(30),          -- zz_cargroup
    position         INTEGER,              -- zz_position (組內位置)
    record_type      VARCHAR(10),          -- 車輛/車組
    install_date     TIMESTAMPTZ,          -- 試運起始日期
    expected_life    INTEGER,              -- 預期使用年限(年)
    manufacturer     VARCHAR(30),
    failure_code     VARCHAR(30),
    parent_assetnum  VARCHAR(30),          -- 所屬車組
    synced_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_assets_vehicle_type ON maximo_assets(vehicle_type);
CREATE INDEX IF NOT EXISTS idx_assets_section      ON maximo_assets(section);
CREATE INDEX IF NOT EXISTS idx_assets_status       ON maximo_assets(status);
CREATE INDEX IF NOT EXISTS idx_assets_record_type  ON maximo_assets(record_type);

-- ─── 定期工單 (PMWO) ─────────────────────────────────────────────────────────
-- worktype IN ('1A','2A','3A','4A') from mxwo
CREATE TABLE IF NOT EXISTS maximo_pm_workorders (
    id                SERIAL PRIMARY KEY,
    wonum             VARCHAR(30) UNIQUE NOT NULL,
    description       TEXT,                -- 工單說明（含車型+級別）
    status            VARCHAR(30),         -- 工單結案/工單初始/...
    assetnum          VARCHAR(30),         -- 車組/車號
    work_type         VARCHAR(10),         -- 1A/2A/3A/4A
    owner_group       VARCHAR(50),         -- ownergroup: 檢修單位
    maintenance_section VARCHAR(20),       -- WOL1: 檢修段
    report_date       TIMESTAMPTZ,         -- reportdate
    act_start         TIMESTAMPTZ,         -- 實際開始日期 (ZZ_ACTSTART)
    act_finish        TIMESTAMPTZ,         -- 完工/試車日期 (ZZ_ACTFINISH)
    last_act_finish   TIMESTAMPTZ,         -- 上次檢修日期 (ZZ_LASTACTFINISH)
    car_in_result     TEXT,                -- ZZ_CARIN: 進廠檢修結果
    car_out_result    TEXT,                -- ZZ_CAROUT: 出廠結果
    kilometers        INTEGER,             -- 里程數
    failure_code      VARCHAR(30),
    synced_at         TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pmwo_assetnum   ON maximo_pm_workorders(assetnum);
CREATE INDEX IF NOT EXISTS idx_pmwo_work_type  ON maximo_pm_workorders(work_type);
CREATE INDEX IF NOT EXISTS idx_pmwo_status     ON maximo_pm_workorders(status);
CREATE INDEX IF NOT EXISTS idx_pmwo_act_finish ON maximo_pm_workorders(act_finish);

-- ─── 維修工單 / 臨修工單 (CMWO) ──────────────────────────────────────────────
-- worktype IN ('T1','TR','CM',...) from mxwo
CREATE TABLE IF NOT EXISTS maximo_cm_workorders (
    id                SERIAL PRIMARY KEY,
    wonum             VARCHAR(30) UNIQUE NOT NULL,
    description       TEXT,                -- 故障說明
    long_description  TEXT,                -- 故障詳細說明 (DESCRIPTION_LONGDESCRIPTION)
    status            VARCHAR(30),
    assetnum          VARCHAR(30),
    work_type         VARCHAR(10),         -- T1/TR/CM/...
    owner_group       VARCHAR(50),         -- 負責單位
    maintenance_section VARCHAR(20),       -- ZZ_MAINSECTION
    ticket_id         VARCHAR(30),         -- TICKETID: 關聯故障通報
    report_date       TIMESTAMPTZ,
    act_start         TIMESTAMPTZ,
    act_finish        TIMESTAMPTZ,
    target_start_date TIMESTAMPTZ,         -- ZZ_TARGSTARTDATE: 預計進段日
    target_comp_date  TIMESTAMPTZ,         -- ZZ_TARGcompDATE: 預計出段日
    failure_code      VARCHAR(30),
    repair_proc       TEXT,                -- ZZ_REPAIRPROC: 修復程序
    kilometers        INTEGER,
    work_hours        NUMERIC(8,2),        -- WORK_HRS
    synced_at         TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cmwo_assetnum  ON maximo_cm_workorders(assetnum);
CREATE INDEX IF NOT EXISTS idx_cmwo_ticket_id ON maximo_cm_workorders(ticket_id);
CREATE INDEX IF NOT EXISTS idx_cmwo_status    ON maximo_cm_workorders(status);

-- ─── 故障通報 (FNM / mxsr) ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS maximo_fault_reports (
    id                SERIAL PRIMARY KEY,
    ticketid          VARCHAR(30) UNIQUE NOT NULL,
    im_num            VARCHAR(30),          -- ZZ_IMNUM: 通報號
    description       TEXT,                 -- 故障概況與處理情形
    fault_symptom     TEXT,                 -- DESCRIPTION_LONGDESCRIPTION: 故障現象
    handling_desc     TEXT,                 -- FR2CODE_LONGDESCRIPTION: 處理情形
    status            VARCHAR(20),
    status_desc       VARCHAR(50),
    assetnum          VARCHAR(30),          -- 車號 (ZZ_EQ24 → assetnum)
    incident_class    VARCHAR(50),          -- ZZ_INCIDENT_NEW: 事件分類(機務處)
    fault_location    TEXT,                 -- ZZ_IM_LOCATION: 故障位置
    tcms_code         VARCHAR(30),          -- ZZ_TCMS: TCMS故障碼
    grade             VARCHAR(10),          -- ZZ_IM_GRADE: 等級
    urgency           VARCHAR(20),          -- ZZ_URGENCY: 緊急程度
    restricted_status VARCHAR(20),          -- ZZ_RESTRICTED_STATUS: 列管狀態
    report_unit       VARCHAR(50),          -- ZZ_PERSONBELONG: 通報單位
    occurrence_date   TIMESTAMPTZ,          -- ZZ_ENTRYDATE + ZZ_IM_TIME
    report_date       TIMESTAMPTZ,
    confirm_by        VARCHAR(50),          -- ZZ_CONFIRM_BY
    confirm_date      TIMESTAMPTZ,          -- ZZ_CONFIRM_DATE
    class_type        VARCHAR(50),          -- class: 進廠收容 etc.
    synced_at         TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_fnm_assetnum  ON maximo_fault_reports(assetnum);
CREATE INDEX IF NOT EXISTS idx_fnm_status    ON maximo_fault_reports(status);
CREATE INDEX IF NOT EXISTS idx_fnm_tcms_code ON maximo_fault_reports(tcms_code);
CREATE INDEX IF NOT EXISTS idx_fnm_occ_date  ON maximo_fault_reports(occurrence_date);

-- ─── 欄位說明對照表（NL→SQL 用） ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS maximo_field_metadata (
    id            SERIAL PRIMARY KEY,
    table_name    VARCHAR(60) NOT NULL,
    column_name   VARCHAR(60) NOT NULL,
    display_name  VARCHAR(100),
    description   TEXT,
    value_mapping JSONB,
    tag           VARCHAR(30) DEFAULT 'general',
    UNIQUE(table_name, column_name)
);

INSERT INTO maximo_field_metadata (table_name, column_name, display_name, description, value_mapping)
VALUES
-- assets
('maximo_assets','vehicle_type','車型','車輛型號',NULL),
('maximo_assets','vehicle_class','車種','電聯車種類',
 '{"EMU":"電聯車","TEMU":"傾斜式電聯車"}'),
('maximo_assets','workshop','維修機廠','負責保養機廠代碼',NULL),
('maximo_assets','section','配屬段別','車輛配屬段別代碼',NULL),
('maximo_assets','status','車輛狀態','車輛目前狀態',
 '{"OPERATING":"已啟用","DECOMMISSIONED":"退役","INACTIVE":"停用"}'),
('maximo_assets','record_type','記錄類型','車輛=單輛, 車組=整組',
 '{"車輛":"單輛車","車組":"整組電聯車"}'),
-- pm workorders
('maximo_pm_workorders','work_type','檢修級別','定期檢修級別',
 '{"1A":"一級檢修","2A":"二級檢修","3A":"三級檢修","4A":"四級檢修"}'),
('maximo_pm_workorders','status','工單狀態','定期工單狀態',
 '{"WAPPR":"核簽中（待主管核准）","APPR":"已核准","WMATL":"待料","WSCH":"待排程","INPRG":"作業中","COMP":"完成","CLOSE":"結案","CAN":"取消"}'),
-- cm workorders
('maximo_cm_workorders','work_type','維修類型','維修/臨修類型',
 '{"T1":"一般臨修","TR":"試車作業","CM":"委外維修"}'),
('maximo_cm_workorders','status','工單狀態','維修工單狀態',
 '{"WAPPR":"核簽中（待主管核准）","APPR":"已核准","WMATL":"待料","WSCH":"待排程","INPRG":"作業中","COMP":"完成","CLOSE":"結案","CAN":"取消"}'),
-- fault reports
('maximo_fault_reports','status','通報狀態','故障通報狀態',
 '{"立案":"立案中","取消":"已取消","結案":"已結案"}'),
('maximo_fault_reports','grade','等級','故障等級(ZZ_IM_GRADE)',NULL),
('maximo_fault_reports','urgency','緊急程度','ZZ_URGENCY',NULL),
('maximo_fault_reports','restricted_status','列管狀態','ZZ_RESTRICTED_STATUS',NULL)
ON CONFLICT (table_name, column_name) DO NOTHING;

-- ─── NL→SQL 範例庫 ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS nl_sql_examples (
    id         SERIAL PRIMARY KEY,
    question   TEXT NOT NULL,
    sql_query  TEXT NOT NULL,
    verified   BOOLEAN DEFAULT FALSE,
    tag        VARCHAR(30) DEFAULT 'general',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO nl_sql_examples (question, sql_query, verified) VALUES
('EMU900 目前有幾組車組？',
 'SELECT COUNT(*) FROM maximo_assets WHERE vehicle_type=''EMU900'' AND record_type=''車組'' AND status=''OPERATING''',
 true),
('配屬在萬華段的車輛有哪些車型？',
 'SELECT vehicle_type, COUNT(*) FROM maximo_assets WHERE section LIKE ''%WAY%'' AND status=''OPERATING'' GROUP BY vehicle_type ORDER BY vehicle_type',
 true),
('EMU800 今年完成的二級定檢有幾張？',
 'SELECT COUNT(*) FROM maximo_pm_workorders pw JOIN maximo_assets a ON pw.assetnum=a.assetnum WHERE a.vehicle_type=''EMU800'' AND pw.work_type=''2A'' AND pw.status=''工單結案'' AND EXTRACT(YEAR FROM pw.act_finish)=EXTRACT(YEAR FROM NOW())',
 true),
('最近一個月故障通報最多的車型？',
 'SELECT a.vehicle_type, COUNT(*) cnt FROM maximo_fault_reports f JOIN maximo_assets a ON f.assetnum=a.assetnum WHERE f.report_date >= NOW()-INTERVAL ''1 month'' GROUP BY a.vehicle_type ORDER BY cnt DESC',
 true),
('EMU900 有哪些未結案的維修工單？',
 'SELECT wonum, assetnum, description, status, report_date FROM maximo_cm_workorders wo JOIN maximo_assets a ON wo.assetnum=a.assetnum WHERE a.vehicle_type=''EMU900'' AND wo.status!=''工單結案'' ORDER BY report_date DESC',
 true),
('TCMS代碼 BXXXXX 出現在哪些車上？',
 'SELECT assetnum, im_num, description, occurrence_date FROM maximo_fault_reports WHERE tcms_code LIKE ''B%'' ORDER BY occurrence_date DESC',
 true)
ON CONFLICT DO NOTHING;
