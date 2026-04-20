-- Migration 012: maximo_tool_calls
-- Feature: 012-maximo-query-tools
-- Date: 2026-04-20
-- Note: uuid-ossp extension already enabled in init.sql (uuid_generate_v4())

-- ============================================================
-- TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS maximo_tool_calls (
    id              SERIAL PRIMARY KEY,
    query_id        UUID NOT NULL DEFAULT uuid_generate_v4(),
    audit_log_id    INTEGER,                          -- loose coupling; 對應 query_audit_log.id，無 FK
    user_id         VARCHAR(36),                      -- 對應 users.id VARCHAR(36)，nullable for system calls
    tool_name       TEXT,                             -- NULL when route_path = 'fallback'
    params          JSONB NOT NULL DEFAULT '{}',
    route_path      TEXT NOT NULL
                        CHECK (route_path IN ('tool', 'fallback', 'error')),
    latency_ms      INTEGER NOT NULL,
    success         BOOLEAN NOT NULL,
    row_count       INTEGER,                          -- NULL 表示失敗或未執行
    fallback_reason TEXT
                        CHECK (fallback_reason IS NULL OR fallback_reason IN (
                            'no_tool_selected',
                            'tool_invocation_error',
                            'llm_circuit_open',
                            'llm_timeout',
                            'tool_execution_error',
                            'feature_flag_disabled'
                        )),
    error_message   TEXT,                             -- 敏感資訊須剝除，禁入 SQL / 使用者原文
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- INDEXES (5)
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_tool_calls_tool_created
    ON maximo_tool_calls (tool_name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_tool_calls_user
    ON maximo_tool_calls (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_tool_calls_created
    ON maximo_tool_calls (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_tool_calls_route
    ON maximo_tool_calls (route_path, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_tool_calls_audit
    ON maximo_tool_calls (audit_log_id) WHERE audit_log_id IS NOT NULL;

-- ============================================================
-- VIEWS (4)
-- ============================================================

-- 熱門工具聚合 + percentile 延遲（最近 30 天，tool 路徑）
CREATE OR REPLACE VIEW maximo_tool_analytics AS
SELECT
    tool_name,
    COUNT(*)                                                        AS total_calls,
    COUNT(*) FILTER (WHERE success)                                  AS success_calls,
    COUNT(*) FILTER (WHERE NOT success)                              AS failed_calls,
    ROUND(AVG(latency_ms)::numeric, 2)                               AS avg_latency_ms,
    percentile_cont(0.5)  WITHIN GROUP (ORDER BY latency_ms)         AS p50_latency_ms,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)         AS p95_latency_ms,
    ROUND(AVG(row_count)::numeric, 2)                                AS avg_row_count,
    MAX(created_at)                                                  AS last_used_at
FROM maximo_tool_calls
WHERE route_path = 'tool'
  AND created_at > NOW() - INTERVAL '30 days'
GROUP BY tool_name
ORDER BY total_calls DESC;

-- 命中率趨勢（每日，最近 30 天）
CREATE OR REPLACE VIEW maximo_route_hit_rate AS
SELECT
    DATE_TRUNC('day', created_at)                                    AS day,
    COUNT(*) FILTER (WHERE route_path = 'tool')                      AS tool_hits,
    COUNT(*) FILTER (WHERE route_path = 'fallback')                  AS fallbacks,
    COUNT(*)                                                         AS total,
    ROUND(
        COUNT(*) FILTER (WHERE route_path = 'tool')::numeric * 100
        / NULLIF(COUNT(*), 0),
        2
    )                                                                AS hit_rate_pct
FROM maximo_tool_calls
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY DATE_TRUNC('day', created_at)
ORDER BY day DESC;

-- Fallback 原因 Top 分析（最近 30 天，fallback 路徑）
CREATE OR REPLACE VIEW maximo_fallback_reasons AS
SELECT
    fallback_reason,
    COUNT(*)                                                         AS count,
    ROUND(COUNT(*)::numeric * 100 / SUM(COUNT(*)) OVER (), 2)        AS pct
FROM maximo_tool_calls
WHERE route_path = 'fallback'
  AND created_at > NOW() - INTERVAL '30 days'
GROUP BY fallback_reason
ORDER BY count DESC;

-- 三路徑 A/B 比較（tool / fallback / error，最近 30 天）
CREATE OR REPLACE VIEW maximo_route_comparison AS
SELECT
    route_path,
    COUNT(*)                                                         AS total_calls,
    ROUND(AVG(latency_ms)::numeric, 2)                               AS avg_latency_ms,
    percentile_cont(0.5)  WITHIN GROUP (ORDER BY latency_ms)         AS p50_latency_ms,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)         AS p95_latency_ms,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE success) / NULLIF(COUNT(*), 0),
        2
    )                                                                AS success_pct
FROM maximo_tool_calls
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY route_path
ORDER BY total_calls DESC;
