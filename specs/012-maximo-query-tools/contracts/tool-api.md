# API Contracts: Maximo Query Tools

**Feature**: 012-maximo-query-tools
**Date**: 2026-04-20

## 修改既有 Endpoint

### `POST /api/maximo/nl2sql`

**行為變更**：進入時先跑 router，命中走 tool、未命中 fallback 現有 NL→SQL。Response schema backward-compatible + 新增欄位。

#### Request（不變）

```json
{
  "query": "A12345 最近一個月的故障通報",
  "conversation_id": "uuid-...",
  "mode": "accurate"
}
```

#### Response（新增 route_path 欄位）

```json
{
  "query_id": "uuid-...",
  "route_path": "tool",
  "tool_name": "search_faults_by_vehicle",
  "tool_input": {
    "asset_num": "A12345",
    "date_range": "last_30d"
  },
  "rows": [
    {
      "ticket_id": "SR00123",
      "描述": "...",
      "故障等級": "A",
      "通報日期": "2026-04-05T10:30:00+08:00"
    }
  ],
  "row_count": 3,
  "chart_hint": null,
  "elapsed_ms": 850,
  "debug": {
    "sql": "SELECT ...",
    "llm_stop_reason": "tool_use"
  }
}
```

**🔒 debug 欄位權限規則（強制）**：
- `debug` 欄位含 SQL、tool 內部 params、LLM 原始 stop_reason → 機敏資訊
- Backend 必須判斷 `user.role`：
  - `admin` / `analyst` → 回 `debug` 完整物件
  - 其他 role → 在 response 中 omit 整個 `debug` key（不回 empty object）
- 此規則與 2026-04-16 「機敏資訊隱藏」原則一致
- 實作位置：`backend/app/routers/maximo.py` 回應序列化時判斷

**欄位說明**:

| 欄位 | 型別 | 必填 | 說明 |
|-----|------|-----|------|
| `query_id` | UUID | ✅ | 唯一查詢 ID，串聯觀測 |
| `route_path` | `"tool" \| "fallback"` | ✅ | 本次走的路徑 |
| `tool_name` | string \| null | 條件 | `route_path="tool"` 時必填 |
| `tool_input` | object \| null | 條件 | LLM 抽出的參數 |
| `rows` | list[object] | ✅ | 已中文化的結果資料 |
| `row_count` | integer | ✅ | 結果筆數 |
| `chart_hint` | object \| null | 選填 | 統計類 tool 回傳的繪圖提示 |
| `elapsed_ms` | integer | ✅ | 總延遲 |
| `debug` | object | 條件 | admin 可見；含 sql / llm_stop_reason / fallback_reason |

#### Fallback Response 範例

```json
{
  "query_id": "uuid-...",
  "route_path": "fallback",
  "tool_name": null,
  "tool_input": null,
  "rows": [...],
  "row_count": 12,
  "elapsed_ms": 4500,
  "debug": {
    "sql": "SELECT ... (genSQL 產生)",
    "fallback_reason": "no_tool_selected",
    "llm_stop_reason": "end_turn"
  }
}
```

#### Error Response（統一為 200 + 固定 shape，保 backward compat）

**關鍵原則**：**不用 HTTP 4xx/5xx，改以 200 回固定 shape**。舊 client 取 `rows` 不會 crash；新 client 看 `debug.error` 做錯誤分流。

```json
{
  "query_id": "uuid-...",
  "route_path": "tool",
  "tool_name": "get_vehicle_info",
  "tool_input": { "asset_num": "A99999" },
  "rows": [],
  "row_count": 0,
  "chart_hint": null,
  "elapsed_ms": 120,
  "debug": {
    "error": {
      "code": "NOT_FOUND",
      "message": "找不到 asset_num=A99999 的車輛"
    },
    "user_facing_message": "查不到這個車號的資料"
  }
}
```

**僅在 HTTP 層真正錯誤（認證失敗、服務不可用）時才走 FastAPI 標準 HTTPException**（與既有 `backend/app/routers/maximo.py` 慣例一致）。

錯誤代碼列表（寫入 `debug.error.code`）：

| Code | 意義 | HTTP status |
|------|------|------------|
| `NOT_FOUND` | Tool 執行成功但無資料 | 200 |
| `TOOL_EXECUTION_ERROR` | Tool 執行錯誤（DB 錯、邏輯錯） | 200（保 backward compat） |
| `TOOL_INVOCATION_ERROR` | LLM 選對 tool 但 params 解不開 → 已 fallback | 200 |
| `LLM_CIRCUIT_OPEN` | Anthropic circuit breaker open → 已 fallback | 200 |
| `LLM_TIMEOUT` | LLM 呼叫超時 → 已 fallback | 200 |
| `PERMISSION_DENIED` | 使用者無權限存取 | 403（HTTPException） |
| `UNAUTHENTICATED` | Token 無效 | 401（HTTPException） |

---

## 新增 Admin Endpoints

### `GET /api/maximo/tools/analytics`

取得工具使用分析。**需 admin 權限**。

#### Request

```
GET /api/maximo/tools/analytics?days=30
```

#### Query Parameters

| 參數 | 型別 | 預設 | 說明 |
|-----|------|-----|------|
| `days` | integer | 30 | 分析期間（天） |

#### Response

```json
{
  "period_days": 30,
  "total_queries": 1234,
  "tool_hits": 456,
  "fallbacks": 778,
  "hit_rate_pct": 36.95,
  "tools": [
    {
      "tool_name": "get_vehicle_info",
      "total_calls": 150,
      "success_calls": 148,
      "failed_calls": 2,
      "avg_latency_ms": 620,
      "p50_latency_ms": 580,
      "p95_latency_ms": 1100,
      "avg_row_count": 1.0,
      "last_used_at": "2026-04-20T09:12:00+08:00"
    }
  ],
  "fallback_reasons": [
    { "fallback_reason": "no_tool_selected", "count": 720, "pct": 92.5 },
    { "fallback_reason": "tool_invocation_error", "count": 38, "pct": 4.9 },
    { "fallback_reason": "llm_timeout", "count": 20, "pct": 2.6 }
  ],
  "daily_hit_rate": [
    { "day": "2026-04-20", "tool_hits": 45, "fallbacks": 78, "hit_rate_pct": 36.59 }
  ]
}
```

---

### `GET /api/maximo/tools/calls`

分頁查詢 tool call log。**需 admin 權限**。

#### Request

```
GET /api/maximo/tools/calls?limit=50&offset=0&tool_name=get_vehicle_info&success=false
```

#### Query Parameters

| 參數 | 型別 | 說明 |
|-----|------|------|
| `limit` | integer | 每頁筆數（max 200） |
| `offset` | integer | 偏移 |
| `tool_name` | string? | 過濾特定工具 |
| `user_id` | string? | 過濾特定使用者（VARCHAR(36) UUID 格式） |
| `route_path` | `"tool" \| "fallback"`? | 過濾路徑 |
| `success` | boolean? | 過濾成功/失敗 |
| `from_date` | ISO date? | 起始時間 |
| `to_date` | ISO date? | 結束時間 |

#### Response

```json
{
  "total": 1234,
  "limit": 50,
  "offset": 0,
  "items": [
    {
      "id": 9876,
      "query_id": "uuid-...",
      "user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "tool_name": "search_faults_by_vehicle",
      "params": { "asset_num": "A12345", "date_range": "last_30d" },
      "route_path": "tool",
      "latency_ms": 850,
      "success": true,
      "row_count": 3,
      "fallback_reason": null,
      "error_message": null,
      "created_at": "2026-04-20T09:12:00+08:00"
    }
  ]
}
```

---

## 工具內部 Contracts（Python 層）

### `ToolDefinition`（Pydantic model）

```python
class ToolDefinition(BaseModel):
    name: str                           # "get_vehicle_info"
    description: str                    # 給 LLM 讀的工具說明
    input_schema: dict                  # JSON Schema for Anthropic tool_use
```

### `Tool` 抽象基類

```python
class Tool(ABC):
    definition: ToolDefinition

    @abstractmethod
    async def execute(
        self,
        params: dict,
        user_ctx: UserContext
    ) -> ToolResult: ...
```

### `UserContext`

```python
class UserContext(BaseModel):
    user_id: str                        # VARCHAR(36) — 對齊 users.id / query_audit_log.user_id
    role: Literal["admin", "maint_manager", "maint_tech", "analyst", "viewer"]
    section: str | None                 # 段管（對應 permission_groups.row_filters 的 {section}）
    workshop: str | None                # 機廠（maint_tech 使用）
    email: str | None
```

**依據**：
- `user_id` 型別對齊既有 `users.id VARCHAR(36)`（`backend/scripts/maximo_migrate_005_permissions.sql:18`）
- 5 個 role 對齊既有 seed（`maximo_migrate_005_permissions.sql:44-59`）
- 既有 row filter 使用 `{section}` / `{workshop}` 作 placeholder（`maximo_migrate_005_permissions.sql:49-53`），tool SQL 必須注入這些值

---

## 7 個 Tool 的 Input Schema

### 1. `get_vehicle_info`

```json
{
  "type": "object",
  "properties": {
    "asset_num": { "type": "string", "description": "車輛資產編號，如 A12345" }
  },
  "required": ["asset_num"]
}
```

### 2. `search_workorders_by_vehicle`

```json
{
  "type": "object",
  "properties": {
    "asset_num": { "type": "string", "description": "車號" },
    "status": {
      "type": "string",
      "enum": ["工單初始", "核簽中", "執行中未派工", "執行中已派工", "完工待回報", "檢修完成", "工單結案", "工單取消", "工單退回"],
      "description": "工單狀態（Maximo ETL 實際中文值；LLM 應將使用者口語映射到對應值）"
    },
    "status_group": {
      "type": "string",
      "enum": ["open", "closed", "cancelled"],
      "description": "狀態分組（使用者問「未結案/已完成/取消」走這個）：open=工單初始∪核簽中∪執行中未派工∪執行中已派工∪完工待回報∪檢修完成（6 種；註：ETL 尚未拉入「結案」狀態，故檢修完成/完工待回報皆視為 open）；closed=工單結案（唯一正式結案）；cancelled=工單取消∪工單退回"
    },
    "wo_type": {
      "type": "string",
      "enum": ["定檢", "臨修", "all"],
      "default": "all",
      "description": "工單類型：定檢=maximo_pm_workorders；臨修=maximo_cm_workorders；all=UNION 兩張表"
    },
    "date_range": {
      "type": "string",
      "enum": ["last_7d", "last_30d", "last_90d", "prev_week", "prev_month", "this_month", "all"],
      "default": "last_30d"
    }
  },
  "required": ["asset_num"]
}
```

**實際查詢表**：
- `maximo_pm_workorders`（ETL 定檢，34 萬筆，work_type=1A/2A/3A/4A）
- `maximo_cm_workorders`（ETL 臨修，6 千筆，work_type=T1/TR/CM）
- 預設 `wo_type="all"` 時 UNION ALL 兩張表並加虛擬欄位 `wo_type` 於 output
- Row filter: `maintenance_section = %s`（對齊 `UserContext.section`）
- 實際 status 值以 DB 內容為準（2026-04-20 SSH 實測得）

### 3. `search_faults_by_vehicle`

```json
{
  "type": "object",
  "properties": {
    "asset_num": { "type": "string", "description": "車號（對應 maximo_fault_reports.assetnum）" },
    "urgency": {
      "type": "string",
      "enum": ["A", "B", "C"],
      "description": "故障等級（對應 maximo_fault_reports.urgency；注意 DB 中約 224/395 筆 urgency 為空，空值不在過濾範圍）"
    },
    "status_group": {
      "type": "string",
      "enum": ["open", "closed", "cancelled"],
      "description": "故障狀態分組（對應 maximo_fault_reports 實測值）：open=立案∪接件中∪處理中；closed=結案∪可放車；cancelled=取消。註：raw maximo_mxsr 有「併單」狀態但 ETL fault_reports 不含，本期不支援。"
    },
    "date_range": {
      "type": "string",
      "enum": ["last_7d", "last_30d", "last_90d", "prev_week", "prev_month", "this_month", "all"],
      "default": "last_30d"
    }
  },
  "required": ["asset_num"]
}
```

**實際查詢表**：`maximo_fault_reports`（ETL 正規化表，395 筆）。Row filter: `report_unit = %s`。

### 4. ~~`search_faults_by_trip`~~（**Deferred to Phase 2**）

⚠️ **本期 defer** — 實測 `maximo_fault_reports` 與 `maximo_mxsr` **均無 `plusaflightnum` 欄位**（只有 `zz_plusaehmnumber` 是不同語意）。ETL 尚未拉入車次欄位，Phase 2 待 ETL 補完後實作。

Phase 2 預計實作時：
- 來源欄位：待確認（可能需要新增 ETL 同步邏輯）
- Input: `flight_num` string
- 行為：一個車次可能對應多台編組車，回傳 list 全列不去重

### 5. `count_open_workorders_by_category`

```json
{
  "type": "object",
  "properties": {
    "group_by": {
      "type": "string",
      "enum": ["大分類", "車種", "車型"],
      "default": "大分類"
    }
  }
}
```

**SQL 骨架**：
```sql
WITH wo AS (
    SELECT assetnum, status FROM maximo_pm_workorders
    WHERE status NOT IN ('工單結案', '工單取消', '工單退回')
      [AND maintenance_section = %s]   -- row filter (CTE 內側，減少掃描範圍)
    UNION ALL
    SELECT assetnum, status FROM maximo_cm_workorders
    WHERE status NOT IN ('工單結案', '工單取消', '工單退回')
      [AND maintenance_section = %s]
)
SELECT
    CASE WHEN a.eq11 IN ('RSTF','RSTP') THEN '貨車'
         ELSE <map_eq11_to_chinese>(a.eq11)   -- 由 mappers/vehicle_category.py 展開成 CASE WHEN
    END AS category,
    COUNT(*) AS count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS percentage
FROM wo
JOIN maximo_mxasset a ON wo.assetnum = a.assetnum
WHERE a.eq11 IS NOT NULL AND a.eq11 != ''   -- ⚠️ 排除 48% 空值
GROUP BY 1
ORDER BY count DESC;
```

**`<map_eq11_to_chinese>` 實作**：由 `backend/app/services/maximo_tools/mappers/vehicle_category.py` 提供，展開成 `CASE WHEN a.eq11 = 'RSTL' THEN '動力車' WHEN a.eq11 = 'RSTA' THEN '客車' ELSE a.eq11 END`（貨車邏輯上一層已處理）。

### 6. `list_open_workorders_in_category`

```json
{
  "type": "object",
  "properties": {
    "level": { "type": "string", "enum": ["大分類", "車種", "車型"] },
    "value": { "type": "string", "description": "中文值，如「客車」「EMU3000」" }
  },
  "required": ["level", "value"]
}
```

**SQL 骨架**（同上 UNION ALL + JOIN mxasset + eq11 NOT NULL filter，增加 level-based WHERE）

### 7. `get_recent_fault_distribution`

```json
{
  "type": "object",
  "properties": {
    "date_range": {
      "type": "string",
      "enum": ["last_7d", "last_30d", "last_90d", "prev_week", "prev_month", "this_month"],
      "default": "last_30d"
    },
    "group_by": {
      "type": "string",
      "enum": ["urgency", "section"],
      "default": "urgency",
      "description": "urgency = maximo_fault_reports.urgency (A/B/C，忽略 NULL)；section = 段管（取自 report_unit）"
    }
  }
}
```

**查詢表**：`maximo_fault_reports`（ETL，395 筆）。若 group_by=urgency 需過濾 `urgency IS NOT NULL AND urgency != ''`（實測 224/395 筆為空）。

---

## Backward Compatibility

**核心承諾**：舊 client 只看 `rows` / `row_count` / `elapsed_ms` 的情況下行為完全不變。

- 既有 `POST /api/maximo/nl2sql` client：
  - 不看 `route_path` / `tool_name` / `tool_input` / `chart_hint` / `debug` 的 client → 行為不變（仍拿到 `rows` 與 `row_count`）
  - 既有 admin UI 讀 `debug.sql` → tool path 會填解開 placeholder 後的 parameterized SQL，維持可讀
  - `conversation_id` / `mode` 等既有欄位行為不變

- **錯誤情境下的 backward compat**：
  - Tool 執行失敗或 fallback 失敗時 **不回 4xx/5xx**，改以 200 + `rows=[]` + `debug.error`
  - 舊 client 拿到空 rows 的行為 = 既有「查無資料」行為，不會 crash
  - 例外：401/403 仍走 FastAPI HTTPException（既有慣例）

- 既有 Dashboard API（`/api/dashboard/stats`）不受影響（獨立 endpoint）
