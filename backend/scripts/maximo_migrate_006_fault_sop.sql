CREATE TABLE IF NOT EXISTS fault_sop_mapping (
    id SERIAL PRIMARY KEY,
    fault_code VARCHAR(50),
    fault_description TEXT,
    document_id VARCHAR(100),
    document_name TEXT,
    relevance_score FLOAT DEFAULT 1.0,
    source VARCHAR(20) DEFAULT 'manual',  -- 'manual', 'auto', 'user_feedback'
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fsm_fault ON fault_sop_mapping(fault_code);
CREATE INDEX IF NOT EXISTS idx_fsm_doc ON fault_sop_mapping(document_id);
