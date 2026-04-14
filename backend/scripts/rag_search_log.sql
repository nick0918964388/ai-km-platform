-- RAG Search Log: 記錄每次 RAG 搜尋的品質指標
CREATE TABLE IF NOT EXISTS rag_search_log (
    id SERIAL PRIMARY KEY,
    query TEXT NOT NULL,
    search_query TEXT,
    top_score FLOAT,
    avg_score FLOAT,
    source_count INT DEFAULT 0,
    rewrite_used BOOLEAN DEFAULT FALSE,
    rewrite_query TEXT,
    quality TEXT,  -- 'good', 'low', 'none'
    duration_ms INT,
    intent TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rag_search_log_created ON rag_search_log(created_at DESC);

-- RAG Feedback: 使用者對 RAG 回答的回饋
CREATE TABLE IF NOT EXISTS rag_feedback (
    id SERIAL PRIMARY KEY,
    message_id TEXT,
    query TEXT NOT NULL,
    rating TEXT NOT NULL,  -- 'up' or 'down'
    comment TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
