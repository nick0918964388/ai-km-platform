CREATE TABLE IF NOT EXISTS call_traces (
    id SERIAL PRIMARY KEY,
    request_id TEXT NOT NULL,
    step TEXT NOT NULL,
    url TEXT,
    model TEXT,
    request_body TEXT,
    response_body TEXT,
    duration_ms INT,
    status TEXT DEFAULT 'ok',
    error TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_call_traces_request ON call_traces(request_id);
CREATE INDEX IF NOT EXISTS idx_call_traces_created ON call_traces(created_at DESC);
