# Phase 0: Research & Technical Decisions

**Feature**: 012-maximo-query-tools
**Date**: 2026-04-20

## R1. LLM Provider for Tool-use Routing

**Decision**: Claude Sonnet 4.6（`claude-sonnet-4-6`）經由現有 Anthropic SDK

**Rationale**:
- 既有專案已整合 Anthropic client（multi-provider fallback chain）
- Claude 的 tool_use（Function Calling）為 native 設計，模型級別支援，非事後包裝
- 7 個 tool 的 input_schema 用 JSON Schema 直接傳，無額外轉換層
- 既有 `circuit_breaker.py`（Pattern 5）已覆蓋 Anthropic provider，LLM 斷線時可自動 fallback

**Alternatives considered**:
| Provider | 結果 | 否決原因 |
|---------|------|---------|
| OpenAI GPT-4o function calling | 未選 | 公司既定主 provider 是 Anthropic；切 provider 要動 multi-provider router，超出本 feature 範圍 |
| Ollama (本地 GPU) + MiniMax / DeepSeek | 未選 | 本地模型 tool_use 可靠度差（JSON Schema 遵守度 <80%），對命中率有風險。保留作為未來「成本優化」選項 |
| 純規則式 router（keyword matching） | 未選 | 命中率預估 <20%，且無法正確 extract 參數（車號 / 日期 / 等級）。已記錄於 plan.md Complexity Tracking |

---

## R2. Tool Definition Schema

**Decision**: Pydantic v2 + `model_json_schema()`，但 **強制 flat schema**（primitive + Literal enum only，禁用 nested BaseModel 和 union 型別）

**修訂理由**（2026-04-20，依 critic 建議）：
- Pydantic `model_json_schema()` 預設會產 `$defs` + `$ref`，Anthropic tool_use input_schema 僅支援 JSON Schema draft-2020-12 **子集**，複雜 nested 會被拒
- 原 data-model.md 設計的 `DateRange = Literal[...] | DateRangeExplicit` union 型別會產 `anyOf` + `$ref`，實測容易踩雷
- 對策：所有 tool input 只用 primitive（str/int/bool）+ `Literal["a","b","c"]` enum；日期範圍用 enum + 必要時加 `from_date: str | None` / `to_date: str | None` 兩個獨立欄位（不用 union）

**Rationale**:
- Pydantic v2 是既有 codebase 標準
- Flat schema 還能加速 LLM 參數抽取（nested 的決策成本高）
- Tool 內部再把 flat input 組成嚴格結構（`DateRangeExplicit` 這類 model 作為內部表示，不 export 給 LLM）

**Alternatives considered**:
- 手寫 JSON Schema dict → 否決（DRY 破壞）
- 用 Pydantic 但保留 nested / union → 否決（Anthropic 相容性風險）
- 寫 post-processor resolve `$ref` → 否決（額外 200+ 行程式碼維護成本不划算）

**Implementation sketch**:
```python
class GetVehicleInfoInput(BaseModel):
    asset_num: str = Field(..., description="車輛資產編號，如 A12345")

schema = GetVehicleInfoInput.model_json_schema()
# 驗證 schema 無 $defs / $ref（unit test）
assert "$defs" not in schema
assert "$ref" not in str(schema)

ToolDefinition(
    name="get_vehicle_info",
    description="查詢單一車輛的基本資料...",
    input_schema=schema,
)
```

`base.py` 應加 `validate_tool_schema(schema)` helper 強制檢查 flat 特性。

---

## R3. Telemetry 寫入時機

**Decision**: **FastAPI `BackgroundTasks` 非同步寫**（fire-and-forget），失敗 `logger.exception` + counter 不靜默，**200ms timeout** 超時放棄

**修訂理由**（2026-04-20，依 critic 建議）：
- 先前方案「同步寫 + try/except swallow」會掩蓋 DB 掛、磁碟滿、schema 漂移等系統性問題
- 改用 `BackgroundTasks`：HTTP response 已送出後才寫，不阻塞 critical path
- 失敗時 `logger.exception(...)` + Prometheus `telemetry_write_failed_total` 計數器遞增（可告警）
- 200ms timeout 保護：即便 background 寫也可能在 DB 卡住時累積，加 timeout 放棄

**實作範例**:
```python
async def record_tool_call_bg(record: ToolCallRecord):
    try:
        async with asyncio.timeout(0.2):
            await db.execute(INSERT_SQL, record.model_dump())
    except asyncio.TimeoutError:
        logger.warning("telemetry write timeout", extra={"query_id": record.query_id})
        TELEMETRY_TIMEOUT_COUNTER.inc()
    except Exception as e:
        logger.exception("telemetry write failed", extra={"query_id": record.query_id})
        TELEMETRY_FAILED_COUNTER.inc()
```

**Alternatives considered**:
- 同步寫 + swallow → **否決**（掩蓋系統性問題）
- 異步 task queue（Celery/Redis）→ 否決（ROI 不夠）
- 批次 buffer → 否決（失敗時資料遺失）

---

## R4. 參數化查詢執行層

**Decision**: **psycopg2（`psycopg2-binary`）** 原生 `cursor.execute(sql, params)`，不走 ORM，與既有 codebase 對齊

**事實校正**（2026-04-20）：先前誤寫 psycopg3。查 `backend/requirements.txt:48` 實際為 `psycopg2-binary>=2.9.0`；既有 `backend/app/etl/maximo_etl.py` 與 `backend/app/services/rag.py` 全用 psycopg2。本 feature 禁止引入 psycopg3（會加依賴、改連線池、改 async 行為，超出本期範圍）。

**Rationale**:
- 既有 codebase 100% 走 psycopg2，保持一致
- 每個 tool 的 SQL 是寫死的 template，不需要 ORM 動態組合
- psycopg2 的 `cursor.execute(sql, (params,))` 本身就安全（型別綁定，不做字串拼接）
- 容易 inspect 實際執行的 SQL（for telemetry / debug）

**async 策略**：psycopg2 非 async，但可用 `asyncio.to_thread` 包裝避免 block event loop，這與既有 maximo_nl2sql 模式一致。

**Alternatives considered**:
- SQLAlchemy Core → 否決（對 fixed SQL template 是過度抽象）
- SQLAlchemy ORM → 否決（既有 Maximo 相關 model 未 mapping，成本太高）
- Raw string formatting → **嚴禁**（SQL injection）

**Safety enforcement**:
- 每個 tool 的 SQL template 用 `%s` placeholder
- 參數透過 tuple 傳入
- critic 審 diff 時強制 grep 確認無 f-string / `.format()` 的 SQL

---

## R5. 前端 Route-path Badge 元件

**Decision**: 自訂 `RoutePathBadge.tsx`，使用 Carbon `Tag` 作基底

**Rationale**:
- Carbon Tag 原生支援 type / size / label，符合憲法 V「Component Library Consistency」
- 封裝成專用 component 便於未來擴展（hover tooltip、admin debug 面板整合）
- 兩種狀態：`tool` → 綠色 Tag「⚡ 快速查詢」；`nl2sql` → 藍色 Tag「🧠 NL→SQL」

**Alternatives considered**:
- 直接用 Carbon Tag inline → 否決（重複樣式，後續要加 hover info 需全改）
- 自製純 Tailwind badge → 否決（違反憲法 V）
- 圖示 only（無文字） → 否決（可讀性差，新使用者不懂）

---

## R6. 日期範圍 Enum 設計

**Decision**: **7 個 preset enum**（flat schema，避免 nested model）+ 獨立 `from_date` / `to_date` 欄位作 escape hatch

**修訂**（2026-04-20）：原方案 `Literal | BaseModel union` 會產 `anyOf + $ref`，不符 Anthropic input_schema 要求（見 R2）。改成 flat schema。

### Preset 清單
```python
DateRangePreset = Literal[
    "last_7d",       # 過去 7 天（滾動）
    "last_30d",      # 過去 30 天（滾動）
    "last_90d",      # 過去 90 天（滾動）
    "prev_week",     # 上週一到上週日（固定區間）
    "prev_month",    # 上個完整月份（4/20 當下 = 3/1–3/31）
    "this_month",    # 本月 1 號到今天
    "all",           # 不過濾日期
]
```

### 語意修正（依 critic 建議）
原 spec 把「上個月」映射到 `last_30d` 是錯的：4/20 的「上個月」應該是 3/1–3/31，而非 3/21–4/20。現在 enum 含：
- `prev_month`（上個完整月）
- `prev_week`（上個完整週）
- `last_30d`（過去 30 天滾動）
三者有明確語意差異，LLM 根據 user query 自主選擇。

### Tool input schema 整合
```python
class SearchWorkordersInput(BaseModel):
    asset_num: str
    status: Literal["工單初始","核簽中","執行中未派工","執行中已派工","完工待回報","檢修完成","工單結案","工單取消","工單退回"] | None = None
    status_group: Literal["open","closed"] | None = None
    date_range: DateRangePreset = "last_30d"
    from_date: str | None = None   # ISO 8601 date; 僅當使用者指定明確區間
    to_date: str | None = None     # ISO 8601 date
```

`date_range_parser.py` 邏輯：若 `from_date` / `to_date` 同時提供 → 走 explicit；否則解析 preset 成 `(from_ts, to_ts)` tuple。

**Alternatives considered**:
- 自由字串 → 否決（LLM 產 `"上個月"` 或 `"2026-03"` 不一致）
- Union 型別（原方案）→ 否決（Anthropic schema 相容性，見 R2）
- 加更多 preset（`last_1d`, `last_year`） → Phase 2 根據 telemetry 再決定

---

## R7. Fallback 觸發判定（Single-Turn Only）

**Decision**: **Single-turn** 判定：只看 Claude 第一次 response。`stop_reason='tool_use'` 且恰好 1 個 tool_use block → 執行；否則一律 fallback。

**修訂**（2026-04-20，依 critic 建議）：

### 本期明確限制：Single-turn only
- 本 feature **不處理** Claude multi-turn tool chain（先 tool_use → 回 result → 再 end_turn）
- Router.py 要 `assert len(tool_use_blocks) == 1`；若 >1 → fallback（`tool_invocation_error`）
- Phase 2 再擴充到 multi-turn（含 tool result 回丟 + 繼續對話）

### 涵蓋 stop_reason 列表
| stop_reason | 處理 |
|------------|------|
| `tool_use` + 1 block | 正常執行 tool |
| `tool_use` + >1 blocks | 不支援 → fallback (`tool_invocation_error`) |
| `end_turn` | 沒選 tool → fallback (`no_tool_selected`) |
| `max_tokens` | LLM 被截斷 → fallback (`tool_invocation_error`) |
| `stop_sequence` | 非預期 → fallback (`tool_invocation_error`) |
| `refusal`（Sonnet 4.5+） | LLM 拒絕 → fallback (`tool_invocation_error`) |

### Input schema 解碼失敗
- Claude 選了 tool 但 `tool_input` 解不開 Pydantic → `tool_invocation_error`，fallback

### Circuit breaker / timeout
- Circuit breaker open → 直接 fallback (`llm_circuit_open`)，不發 LLM 請求
- LLM 呼叫超時（10s）→ fallback (`llm_timeout`)

**Alternatives considered**:
- 手工 confidence threshold → 否決（Claude 沒有這個 output）
- Multi-sample 投票 → 否決（成本 × 3，效益低）
- 本期就做 multi-turn chain → 否決（超出範圍，先 MVP 驗單輪效果）

---

## R8. Router 系統 Prompt 設計

**Decision**: 極簡 system prompt + 7 個 tool definitions，不做 few-shot

```
你是 AI-KM Platform 的 Maximo 查詢助理。你可以使用下列工具回答車輛、工單、故障通報相關查詢。
規則：
1. 只在使用者問的問題明確對應到某個工具時才呼叫。
2. 如果問題涉及跨工具組合、複雜條件、或工具清單未涵蓋的情境，不要呼叫任何工具，直接回覆 "NO_TOOL"。
3. 參數要從使用者問題中抽取，不要自行推測不存在的資訊。
```

**Rationale**:
- Claude tool_use 天生會判斷「沒合適工具時不呼叫」，system prompt 只需強化這個行為
- 不做 few-shot：會吃大量 prompt cache 空間，而且 tool description 寫清楚後 LLM 判得很好
- "NO_TOOL" 明確信號讓 router 能分辨「LLM 主動放棄」vs 「LLM 選錯但參數壞」

**Alternatives considered**:
- 放 20 個 few-shot examples → 否決（prompt 爆炸，推理變慢）
- 動態從 telemetry 撈 top 10 example → 否決（Phase 2 再評估，本期不做）

---

## R9. 測試資料來源

**Decision**: 使用現有 dev/staging Postgres（192.168.1.11 上的 aikm-postgres）作 integration test；unit test 用 mock

**Rationale**:
- 192.168.1.11 上有真實 Maximo ETL 後的資料（10,742 工單、676 故障、16,165 資產）
- Integration test 需要真實 domain 值分布（eq11 實際有 RSTA/RSTL/RSTF/RSTP 的真實比例）
- Unit test 只測邏輯（mapper、parser），mock DB connection 即可，跑得快

**Alternatives considered**:
- testcontainers（每次測試起新 Postgres）→ 否決（對現有 CI 是過度改造）
- 純 mock → 否決（mapper / SQL 正確性需要真實 schema 驗證）
- Docker compose test profile → Phase 2 考慮（目前先用 staging DB）

---

## 決策總覽（2026-04-20 二次修訂版，含 SSH 實測校正）

| # | 決策項 | 選擇 |
|---|-------|------|
| R1 | LLM provider | Claude Sonnet 4.6（強制使用 Anthropic，不走 Ollama/NVIDIA；tool_use 要求最可靠） |
| R2 | Tool schema 產生 | Pydantic v2 + **flat schema**（禁 nested + union，避免 $ref 相容性問題） |
| R3 | Telemetry 寫入 | **BackgroundTasks 非同步**（200ms timeout + exception log + counter） |
| R4 | SQL 執行 | **psycopg2**（既有 codebase 一致）+ `asyncio.to_thread` 包裝 |
| R5 | Badge 元件 | 自訂 RoutePathBadge（基底 Carbon Tag） |
| R6 | 日期 enum | **7 preset**（last_7d/30d/90d + prev_week/prev_month/this_month + all）+ 獨立 from_date/to_date |
| R7 | Fallback 判定 | **Single-turn only**：tool_use + 1 block → 執行；其餘一律 fallback |
| R8 | Router prompt | 極簡 + 不做 few-shot |
| R9 | 測試資料 | Unit mock + Integration 走 staging Postgres |
| **R10** | **目標表選擇** | **走 ETL 表**（pm/cm/fault_reports），不走 raw（mxwo/mxsr）— raw 欄位不全且缺 row filter 欄位 |
| **R11** | **Status enum 語言** | **全用中文**（DB 實際存的值）— 2026-04-20 SSH 實測得知，禁用英文 WAPPR/APPR 代碼（那些只在 migration 註解出現，實際 DB 無此值）|
| **R12** | **Tool 4 範圍** | **Defer 到 Phase 2** — `plusaflightnum` 欄位在 ETL 與 raw 表都不存在（實測 information_schema 確認）|
| **R13** | **eq11 空值** | 所有 eq11 查詢 filter `IS NOT NULL AND != ''`（實測 48% 為空） |

**主要修訂點**（vs 初版）：
- R2 Pydantic schema 強制 flat（禁 nested/union）
- R3 Telemetry 從「同步 swallow」改「BackgroundTasks + timeout + 告警」
- R4 從 psycopg3 回退到 psycopg2（既有依賴）
- R6 從 3 preset 擴到 7 preset + 修正「上個月」語意錯誤
- R7 明確 single-turn、列舉所有 stop_reason 處理路徑

所有決策已記錄，無遺留 NEEDS CLARIFICATION。
