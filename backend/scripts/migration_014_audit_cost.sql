-- Migration 014: Add LLM cost tracking columns to query_audit_log
-- Idempotent (IF NOT EXISTS)

ALTER TABLE query_audit_log
    ADD COLUMN IF NOT EXISTS total_llm_ms INTEGER;

ALTER TABLE query_audit_log
    ADD COLUMN IF NOT EXISTS estimated_tokens INTEGER;
