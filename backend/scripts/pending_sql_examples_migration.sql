CREATE TABLE IF NOT EXISTS pending_sql_examples (
    id SERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    sql_query TEXT NOT NULL,
    submitted_by VARCHAR(100) NOT NULL,
    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'pending',  -- pending/approved/rejected
    reviewed_by VARCHAR(100),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_pending_sql_status ON pending_sql_examples(status);
