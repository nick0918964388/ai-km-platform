-- Permission groups
CREATE TABLE IF NOT EXISTS permission_groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT,
    allowed_tables TEXT[] DEFAULT '{}',
    denied_tables TEXT[] DEFAULT '{}',
    row_filters JSONB DEFAULT '{}',
    hidden_columns JSONB DEFAULT '{}',
    allow_freeform BOOLEAN DEFAULT true,
    max_results INTEGER DEFAULT 100,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- User to permission group mapping
CREATE TABLE IF NOT EXISTS user_permissions (
    user_id VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE,
    group_id INTEGER REFERENCES permission_groups(id) ON DELETE CASCADE,
    section VARCHAR(50),
    workshop VARCHAR(50),
    PRIMARY KEY (user_id, group_id)
);

-- Query audit log
CREATE TABLE IF NOT EXISTS query_audit_log (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(36),
    user_email VARCHAR(255),
    question TEXT NOT NULL,
    sql_generated TEXT,
    tables_accessed TEXT[],
    row_count INTEGER DEFAULT 0,
    execution_ms FLOAT,
    mode VARCHAR(20),
    cached BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_user ON query_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON query_audit_log(created_at DESC);

-- Seed default permission groups
INSERT INTO permission_groups (name, display_name, description, allowed_tables, row_filters, allow_freeform, max_results)
VALUES
    ('admin', '系統管理員', '完整存取所有資料表與功能', '{}', '{}', true, 500),
    ('maint_manager', '維修主管', '可查詢工單、故障通報、資產，依段別過濾',
     ARRAY['maximo_mxwo','maximo_mxsr','maximo_mxasset','maximo_pm_workorders','maximo_cm_workorders','maximo_assets','maximo_fault_reports'],
     '{"maximo_mxwo": "wol1 = ''{section}''", "maximo_mxsr": "zz_personbelong = ''{section}''"}',
     true, 200),
    ('maint_tech', '維修技師', '可查詢工單、故障通報、資產，依機廠+段別過濾',
     ARRAY['maximo_mxwo','maximo_mxsr','maximo_mxasset','maximo_pm_workorders','maximo_cm_workorders','maximo_assets','maximo_fault_reports'],
     '{"maximo_mxwo": "wol1 = ''{section}''", "maximo_mxsr": "zz_personbelong = ''{section}''"}',
     true, 100),
    ('analyst', '分析師', '可查詢所有資料表，無資料範圍限制', '{}', '{}', true, 500),
    ('viewer', '一般使用者', '只能使用範例查詢，依段別過濾',
     ARRAY['maximo_mxwo','maximo_mxsr','maximo_mxasset'],
     '{}',
     false, 50)
ON CONFLICT (name) DO NOTHING;
