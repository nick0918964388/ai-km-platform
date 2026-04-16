-- Source Feedback: 使用者對 RAG 來源文件 chunk 的回饋（👍/👎）
-- 用於在搜尋 re-ranking 時給予被標記「有幫助」的 chunk 加分

CREATE TABLE IF NOT EXISTS source_feedback (
    id SERIAL PRIMARY KEY,
    chunk_id VARCHAR(100) NOT NULL,
    document_id VARCHAR(100),
    question TEXT,
    rating VARCHAR(10) NOT NULL CHECK (rating IN ('up', 'down')),
    user_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_source_feedback_chunk ON source_feedback(chunk_id);
CREATE INDEX IF NOT EXISTS idx_source_feedback_created ON source_feedback(created_at DESC);

-- View: 每個 chunk 的淨分數（up 數 - down 數），供 RAG 搜尋快速查找
-- 注意：PostgreSQL 不支援 CREATE VIEW IF NOT EXISTS，改用 CREATE OR REPLACE VIEW
CREATE OR REPLACE VIEW source_boost_scores AS
SELECT
    chunk_id,
    COUNT(*) FILTER (WHERE rating = 'up') - COUNT(*) FILTER (WHERE rating = 'down') AS net_score
FROM source_feedback
GROUP BY chunk_id;
