-- Full-text search on conversation_messages.content
-- Uses GENERATED column (PostgreSQL 12+) to avoid PL/pgSQL trigger,
-- because asyncpg cannot execute PL/pgSQL function bodies split naively by ";".
--
-- This file only contains simple, single-statement SQL separated by semicolons.
-- The legacy trigger/function and legacy plain tsvector column (if any) are
-- dropped by the python migration runner in app/main.py BEFORE this script runs.

-- Add the generated tsvector column (idempotent)
ALTER TABLE conversation_messages
  ADD COLUMN IF NOT EXISTS content_tsv tsvector
  GENERATED ALWAYS AS (to_tsvector('simple', COALESCE(content, ''))) STORED;

-- GIN index for fast FTS
CREATE INDEX IF NOT EXISTS idx_conv_messages_fts
  ON conversation_messages USING GIN(content_tsv);
