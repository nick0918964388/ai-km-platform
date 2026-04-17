-- Add tsvector column for full-text search on conversation messages
ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS content_tsv tsvector;

-- Populate existing rows
UPDATE conversation_messages SET content_tsv = to_tsvector('simple', content) WHERE content_tsv IS NULL;

-- Auto-update trigger
CREATE OR REPLACE FUNCTION conversation_messages_tsv_trigger() RETURNS trigger AS $$
BEGIN
  NEW.content_tsv := to_tsvector('simple', COALESCE(NEW.content, ''));
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_conv_msg_tsv ON conversation_messages;
CREATE TRIGGER trg_conv_msg_tsv BEFORE INSERT OR UPDATE OF content ON conversation_messages
FOR EACH ROW EXECUTE FUNCTION conversation_messages_tsv_trigger();

-- GIN index for fast FTS
CREATE INDEX IF NOT EXISTS idx_conv_messages_fts ON conversation_messages USING GIN(content_tsv)
