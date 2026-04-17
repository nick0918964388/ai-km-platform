ALTER TABLE rag_search_log ADD COLUMN IF NOT EXISTS conversation_id VARCHAR(64);
ALTER TABLE query_audit_log ADD COLUMN IF NOT EXISTS conversation_id VARCHAR(64);
CREATE INDEX IF NOT EXISTS idx_rag_search_conversation ON rag_search_log(conversation_id);
CREATE INDEX IF NOT EXISTS idx_query_audit_conversation ON query_audit_log(conversation_id);
