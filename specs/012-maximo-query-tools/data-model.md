# Phase 1: Data Model

**Feature**: 012-maximo-query-tools
**Date**: 2026-04-20

## 新增資料表

### `maximo_tool_calls`

記錄每次工具呼叫的觀測資料。

**事實校正**（2026-04-20 修）：
- 既有 `users.id` 是 `VARCHAR(36)`（`backend/scripts/maximo_migrate_005_permissions.sql:18`）
- 既有 `query_audit_log.user_id` 也是 `VARCHAR(36)`（`maximo_migrate_005_permissions.sql:28`）
- 既有 `query_audit_log` **沒有 `query_id` 欄位**（PK 是 `id SERIAL`）→ 本 table 自生 UUID 作 correlation id，與 `query_audit_log.id` 走 loose coupling（不宣稱 FK）

```sql
CREATE TABLE IF NOT EXISTS maximo_tool_calls (
    id SERIAL PRIMARY KEY,
    query_id UUID NOT NULL DEFAULT uuid_generate_v4(),  -- 本 feature 自生 UUID（既有 uuid-ossp extension，見 backend/scripts/init.sql:5）
    audit_log_id INTEGER,                              -- 對齊 query_audit_log.id（loose，無 FK）
    user_id VARCHAR(36),                               -- 對齊 users.id VARCHAR(36)，nullable（system user 呼叫）
    tool_name TEXT,                                    -- NULL when route_path='fallback'
    params JSONB NOT NULL DEFAULT '{}',                -- LLM 抽出的參數
    route_path TEXT NOT NULL
        CHECK (route_path IN ('tool', 'fallback', 'error')),
    latency_ms INTEGER NOT NULL,
    success BOOLEAN NOT NULL,
    row_count INTEGER,                                 -- NULL 表示失敗或未執行
    fallback_reason TEXT
        CHECK (fallback_reason IS NULL OR fallback_reason IN (
            'no_tool_selected',
            'tool_invocation_error',
            'llm_circuit_open',
            'llm_timeout',
            'tool_execution_error',
            'feature_flag_disabled'
        )),
    error_message TEXT,                                -- 敏感資訊須剝除
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tool_calls_tool_created
    ON maximo_tool_calls (tool_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tool_calls_user
    ON maximo_tool_calls (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tool_calls_created
    ON maximo_tool_calls (created_at DESC);           -- range scan 用（analytics view 必要）
CREATE INDEX IF NOT EXISTS idx_tool_calls_route
    ON maximo_tool_calls (route_path, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tool_calls_audit
    ON maximo_tool_calls (audit_log_id) WHERE audit_log_id IS NOT NULL;
```

**欄位說明**:

| 欄位 | 型別 | 說明 |
|-----|------|------|
| `id` | SERIAL | PK |
| `query_id` | UUID | 本 feature 自生；同一次 user query 的 router → tool execute → 回應共用一個 query_id |
| `audit_log_id` | INTEGER | Nullable；若該 query 有寫入 `query_audit_log`（fallback 路徑會寫），記下對應 `id` 以便 JOIN |
| `user_id` | VARCHAR(36) | 對齊既有 users/query_audit_log；nullable for system 呼叫（如 analytics 自 test） |
| `tool_name` | TEXT | 工具名稱；`route_path='fallback'` 時為 NULL |
| `params` | JSONB | LLM 抽出的參數，空物件代表 tool 無參數 |
| `route_path` | TEXT | `tool` / `fallback` / `error`（CHECK constraint 強制） |
| `latency_ms` | INTEGER | 從 router 開始到結果回傳的總延遲 |
| `success` | BOOLEAN | 是否正常回傳結果（不論 row_count） |
| `row_count` | INTEGER | NULL 表示失敗或未執行 |
| `fallback_reason` | TEXT | 6 個枚舉值（CHECK 強制），新增 `feature_flag_disabled` |
| `error_message` | TEXT | 失敗時的簡要錯誤訊息（**SQL / 使用者輸入原文禁入**） |
| `created_at` | TIMESTAMPTZ | 寫入時間 |

**State Transition**:
- 所有記錄都是 immutable（INSERT only），無 UPDATE / DELETE
- **保留策略**：90 天 + cleanup cron（見下方「Retention & Cleanup」）

---

## 新增視圖

### `maximo_tool_analytics`

Admin 分析用的聚合視圖。

**效能注意**：當 `maximo_tool_calls` > 1M 筆時 `percentile_cont` 會秒級慢查詢。本期先走一般 view（依 `idx_tool_calls_created` index 掃最近 30 天），若實測 analytics endpoint 慢 > 3s 則改 materialized view + 每小時 refresh（Phase 2 調整）。

```sql
CREATE OR REPLACE VIEW maximo_tool_analytics AS
SELECT
    tool_name,
    COUNT(*)                                              AS total_calls,
    COUNT(*) FILTER (WHERE success)                       AS success_calls,
    COUNT(*) FILTER (WHERE NOT success)                   AS failed_calls,
    ROUND(AVG(latency_ms)::numeric, 2)                    AS avg_latency_ms,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) AS p50_latency_ms,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms,
    ROUND(AVG(row_count)::numeric, 2)                     AS avg_row_count,
    MAX(created_at)                                       AS last_used_at
FROM maximo_tool_calls
WHERE route_path = 'tool'
  AND created_at > NOW() - INTERVAL '30 days'
GROUP BY tool_name
ORDER BY total_calls DESC;
```

### `maximo_route_hit_rate`

命中率趨勢視圖。

```sql
CREATE OR REPLACE VIEW maximo_route_hit_rate AS
SELECT
    DATE_TRUNC('day', created_at) AS day,
    COUNT(*) FILTER (WHERE route_path = 'tool')     AS tool_hits,
    COUNT(*) FILTER (WHERE route_path = 'fallback') AS fallbacks,
    COUNT(*)                                        AS total,
    ROUND(
        COUNT(*) FILTER (WHERE route_path = 'tool')::numeric * 100 / NULLIF(COUNT(*), 0),
        2
    ) AS hit_rate_pct
FROM maximo_tool_calls
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY DATE_TRUNC('day', created_at)
ORDER BY day DESC;
```

### `maximo_fallback_reasons`

Fallback 原因 Top 分析。

```sql
CREATE OR REPLACE VIEW maximo_fallback_reasons AS
SELECT
    fallback_reason,
    COUNT(*) AS count,
    ROUND(COUNT(*)::numeric * 100 / SUM(COUNT(*)) OVER (), 2) AS pct
FROM maximo_tool_calls
WHERE route_path = 'fallback'
  AND created_at > NOW() - INTERVAL '30 days'
GROUP BY fallback_reason
ORDER BY count DESC;
```

### `maximo_route_comparison`（新增）

同時比較 tool / fallback / error 三種路徑的效能，供 A/B 分析新架構 vs 舊 genSQL。

```sql
CREATE OR REPLACE VIEW maximo_route_comparison AS
SELECT
    route_path,
    COUNT(*)                                               AS total_calls,
    ROUND(AVG(latency_ms)::numeric, 2)                     AS avg_latency_ms,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms)  AS p50_latency_ms,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms,
    ROUND(100.0 * COUNT(*) FILTER (WHERE success) / NULLIF(COUNT(*),0), 2) AS success_pct
FROM maximo_tool_calls
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY route_path
ORDER BY total_calls DESC;
```

---

## Retention & Cleanup（新增）

### 保留策略
- 90 天內詳細資料保留於 `maximo_tool_calls`
- 超過 90 天的資料刪除（降低表大小以保 view 效能）
- 若後續需要歷史長期分析，考慮 dump 到 S3 parquet（Phase 2）

### Cleanup 實作
走應用程式 scheduler（既有 `apscheduler`-like 機制或 cron），**不用 pg_cron**（減少 DB extension 依賴）：

```python
# 每日凌晨 03:00 執行
async def cleanup_old_tool_calls():
    await db.execute("""
        DELETE FROM maximo_tool_calls
        WHERE created_at < NOW() - INTERVAL '90 days'
    """)
```

實作位置：整合既有 `backend/app/services/chat_job_runner.py` 的排程機制，或新建 `backend/app/services/maximo_tools/cleanup.py`。

### 爆表預估
- 假設流量：5k-50k calls/day
- 90 天：450k - 4.5M 筆
- 單筆 ~500 bytes（含 JSONB params）→ 225 MB - 2.25 GB
- **現階段可接受**，觸發 materialized view 改造條件：analytics endpoint P95 > 3s

---

## 讀取的既有資料表

### `maximo_mxasset`（車輛資產 — Maximo 原始鏡像）

**事實**（2026-04-20 SSH 實測）：eq-fields 只存在於這張原始鏡像表（`maximo_assets` 是另一張 ETL 產出，**缺 eq3/eq4/eq11**）。

關鍵欄位（本 feature 用到）：

| 欄位 | 型別 | 用途 |
|-----|------|------|
| `assetnum` | TEXT | 車號 |
| `eq11` | TEXT | 大分類代碼（RSTL=動力車 / RSTA=客車 / RSTF+RSTP=貨車）。**⚠️ 實測 48% 為空**（5159/10662） |
| `eq3` | TEXT | 車種代碼 |
| `eq4` | TEXT | 車型代碼 |
| `eq24` | TEXT | 車號替代欄位（用作車號顯示） |
| `description` | TEXT | 說明 |
| `status` | TEXT | **英文狀態**：`OPERATING`（2,982）/ `NOT READY`（801）/ `DECOMMISSIONED`（322）/ `INACTIVE`（18） |
| `assettype` | TEXT | 資產類型 |
| `siteid` | TEXT | 站點 |

**Tool 1 output 中文化**：asset.status 英文值由既有 `domain_mapper` 轉中文（OPERATING→「運轉中」/ NOT READY→「未就緒」/ DECOMMISSIONED→「除役」/ INACTIVE→「停用」）。

**eq11 空值處理**（FR-014c）：所有涉及 eq11 的 group by / filter 必須 `AND a.eq11 IS NOT NULL AND a.eq11 != ''`。

### `maximo_pm_workorders`（定檢工單 — ETL 正規化）

**選擇走 ETL 表**（2026-04-20 決議）：raw `maximo_mxwo` 欄位太少（只 14 個）、缺 row filter 欄位、缺「工單結案」狀態。ETL 表完整。

關鍵欄位：

| 欄位 | 型別 | 用途 |
|-----|------|------|
| `wonum` | VARCHAR(30) | 工單號 |
| `assetnum` | VARCHAR(30) | 關聯車號 |
| `status` | VARCHAR(30) | **中文狀態**（見下方實際值） |
| `work_type` | VARCHAR(10) | 1A/2A/3A/4A（定檢等級） |
| `maintenance_section` | VARCHAR(20) | **段管（row filter 用）** |
| `report_date` | TIMESTAMPTZ | 通報日期 |
| `act_start` | TIMESTAMPTZ | 實際開始 |
| `act_finish` | TIMESTAMPTZ | 實際完工 |
| `description` | TEXT | 說明 |

### `maximo_cm_workorders`（臨修工單 — ETL）

同上結構，`work_type` 值為 `T1`/`TR`/`CM`。筆數較少（6 千）但 schema 一致。

**status 實際中文值**（2026-04-20 SSH 實測，ORDER BY count DESC）：

PM 表（339,810 筆）：
- 工單初始（331,533）/ 工單結案（3,497）/ 執行中未派工（2,466）/ 核簽中（1,503）/ 執行中已派工（339）/ 完工待回報（314）/ 檢修完成（73）/ 工單取消（69）/ 工單退回（16）

CM 表（5,989 筆）：
- 工單初始（5,546）/ 執行中未派工（369）/ 工單取消（29）/ 執行中已派工（23）/ 工單結案（7）/ 完工待回報（5）/ 核簽中（5）/ 檢修完成（5）

**status_group 分組**（FR-014a）：
- `open` = `工單初始` ∪ `核簽中` ∪ `執行中未派工` ∪ `執行中已派工` ∪ `完工待回報` ∪ `檢修完成`
- `closed` = `工單結案`
- `cancelled` = `工單取消` ∪ `工單退回`

**Tool 查詢建議**：Tool 2/5/6 預設 UNION ALL 兩張 ETL 表，output 加虛擬欄位 `wo_type: "定檢"|"臨修"` 區分。

### `maximo_fault_reports`（故障通報 — ETL）

**選擇走 ETL 表**：Raw `maximo_mxsr` 中 `plusaflightnum` 不存在，且欄位命名混亂（多 zz_ 前綴）。ETL 表欄位清晰。

關鍵欄位：

| 欄位 | 型別 | 用途 |
|-----|------|------|
| `ticketid` | VARCHAR(30) | 通報號 |
| `assetnum` | VARCHAR(30) | 關聯車號 |
| `status` | VARCHAR(20) | **中文狀態** |
| `urgency` | VARCHAR(20) | **故障等級（A/B/C）**；實測 224/395 筆為空 |
| `grade` | VARCHAR(10) | ZZ_IM_GRADE: 等級（獨立欄位） |
| `tcms_code` | VARCHAR(30) | TCMS 故障碼 |
| `report_unit` | VARCHAR(50) | **通報單位（row filter 用，對應 zz_personbelong）** |
| `report_date` | TIMESTAMPTZ | 通報日期 |
| `description` | TEXT | 故障描述 |

**status 實際中文值**（2026-04-20 實測，395 筆）：
- 立案（360）/ 結案（14）/ 處理中（10）/ 取消（7）/ 接件中（2）/ 可放車（2）

**status_group 分組**（FR-014b）：
- `open` = `立案` ∪ `接件中` ∪ `處理中`
- `closed` = `結案` ∪ `可放車`
- `cancelled` = `取消`

**⚠️ 車次欄位 `plusaflightnum` 不存在於 fault_reports 或 mxsr** — Tool 4 defer 到 Phase 2。

---

## 核心物件（Python dataclass）

### `ToolCallRecord`

```python
class ToolCallRecord(BaseModel):
    model_config = ConfigDict(frozen=True)  # immutable

    query_id: UUID
    audit_log_id: int | None = None
    user_id: str | None = None              # VARCHAR(36)，nullable for system 呼叫
    tool_name: str | None                   # None if route_path='fallback'
    params: dict
    route_path: Literal["tool", "fallback", "error"]
    latency_ms: int
    success: bool
    row_count: int | None
    fallback_reason: Literal[
        "no_tool_selected",
        "tool_invocation_error",
        "llm_circuit_open",
        "llm_timeout",
        "tool_execution_error",
        "feature_flag_disabled",
    ] | None = None
    error_message: str | None = None
```

### `ToolResult`

每個 Tool.execute() 的統一回傳型別：

```python
class ToolResult(BaseModel):
    success: bool
    rows: list[dict]                           # 已中文化後的結果
    row_count: int
    chart_hint: dict | None                    # for 統計類 tool
    error: str | None
    elapsed_ms: int
```

### `RouterDecision`

Router 執行的結果物件：

```python
class RouterDecision(BaseModel):
    route_path: Literal["tool", "fallback"]
    tool_name: str | None
    tool_input: dict | None
    fallback_reason: str | None
    llm_stop_reason: str                       # Claude 的 stop_reason
    raw_response: dict                         # 供 debug 用
```

---

## 資料關聯圖

```text
query_audit_log (既有)
     │
     │ query_id (UUID)
     ▼
maximo_tool_calls (新增)
     │
     │ tool_name
     ▼
   ──────────
   │  工具邏輯讀取：
   │   - mxasset (read)
   │   - workorder (read)
   │   - sr (read)
   └──────────
```

---

## Migration Strategy

單一 migration 檔案：`backend/scripts/migration_012_tool_calls.sql`

內容：
1. `CREATE TABLE IF NOT EXISTS maximo_tool_calls` + **5 indexes**（tool_created / user / created / route / audit partial）
2. `CREATE OR REPLACE VIEW maximo_tool_analytics`
3. `CREATE OR REPLACE VIEW maximo_route_hit_rate`
4. `CREATE OR REPLACE VIEW maximo_fallback_reasons`
5. `CREATE OR REPLACE VIEW maximo_route_comparison`

**執行方式**：整合現有應用程式啟動時的自動 migration 機制（參考 2026-04-18 的 `fix_date_columns_migration` 流程）。

**Idempotency**：所有語句走 `IF NOT EXISTS` / `CREATE OR REPLACE`，重複執行安全。

**Rollback**：手動 DROP TABLE + DROP VIEW；不納入 migration 自動 rollback 機制（僅用於觀測，刪除資料不影響業務）。

---

## 權限 / RLS

- `maximo_tool_calls` 不暴露給一般使用者
- 只有 admin 角色可讀取（透過 `/api/maximo/tools/*` admin endpoint）
- 寫入由 backend 服務自動執行（system user），不受 row filter 限制
- 工具執行的 SQL 本身繼承既有 row filter（user_ctx 注入 WHERE clause）
