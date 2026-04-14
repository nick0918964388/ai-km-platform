CREATE TABLE IF NOT EXISTS chat_jobs (
    id VARCHAR(36) PRIMARY KEY,
    query TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    result JSONB,
    error TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    duration_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_chat_jobs_status ON chat_jobs(status);
CREATE INDEX IF NOT EXISTS idx_chat_jobs_created ON chat_jobs(created_at DESC);
