-- Document version tracking
CREATE TABLE IF NOT EXISTS document_versions (
    id SERIAL PRIMARY KEY,
    document_id TEXT NOT NULL,
    version INT NOT NULL DEFAULT 1,
    filename TEXT NOT NULL,
    file_size BIGINT DEFAULT 0,
    chunk_count INT DEFAULT 0,
    file_hash TEXT,
    change_note TEXT,
    uploaded_by TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_doc_versions_doc_id ON document_versions(document_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_doc_versions_unique ON document_versions(document_id, version);

-- Add version column to existing documents table if not exists
DO $$ BEGIN
    ALTER TABLE documents ADD COLUMN IF NOT EXISTS current_version INT DEFAULT 1;
EXCEPTION WHEN undefined_table THEN NULL; END $$;
