---
description: "Task list for Maximo Query Tools (012-maximo-query-tools)"
---

# Tasks: Maximo 查詢工具化（Tool-based Hot Path）

**Input**: Design documents from `/specs/012-maximo-query-tools/`
**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/tool-api.md, quickstart.md
**Tests**: 包含 unit + integration + E2E（spec FR-001..023 明確要求）

**Organization**: 按 user story 分組以支援 P9 平行派遣。

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: 可並行執行（不同檔案、無未完成的依賴）
- **[Story]**: US1 / US2 / US3 / US4（對應 spec.md 四個 user story）
- 檔案路徑一律為絕對路徑（相對 repo root）

## Path Conventions

- **Backend**: `backend/app/services/maximo_tools/`, `backend/app/routers/`, `backend/scripts/`, `backend/tests/`
- **Frontend**: `frontend/src/components/chat/`, `frontend/src/lib/`, `frontend/tests/e2e/`
- **Specs**: `specs/012-maximo-query-tools/`

---

## Phase 1: Setup（共享基礎設施）

**Purpose**: branch / 目錄結構 / 基礎檔案骨架

- [x] T001 Create feature branch `012-maximo-query-tools`（已完成，by `/speckit.specify`）
- [ ] T002 Create directory structure `backend/app/services/maximo_tools/{mappers,tools}/` with `__init__.py`
- [ ] T003 [P] Create migration file placeholder `backend/scripts/migration_012_tool_calls.sql`（空檔，由 T004 填寫）

---

## Phase 2: Foundational（阻塞所有 User Stories 的前置）

**Purpose**: 共用元件 + router 骨架 + pipeline validator（Tool 1）

**⚠️ CRITICAL**: 任何 User Story 實作都必須等這個 phase 全部 done。

### 資料層

- [ ] T004 Write migration SQL in `backend/scripts/migration_012_tool_calls.sql`（create `maximo_tool_calls` table + **4 views** + **5 indexes**；使用既有 `uuid-ossp` extension 的 `uuid_generate_v4()`，**禁用** `gen_random_uuid()` 避免需要 `pgcrypto`）
- [ ] T005 Apply migration on dev DB at 192.168.1.11 (aikm-postgres) 並驗證 `\dt maximo_tool_calls` + `\dv maximo_tool_*`

### 共用元件（可並行）

- [ ] T006 [P] Implement `backend/app/services/maximo_tools/mappers/vehicle_category.py`（中文↔eq11 雙向，含 RSTF/RSTP 雙碼 IN 語意）
- [ ] T007 [P] Implement `backend/app/services/maximo_tools/mappers/date_range.py`（enum → `(from_ts, to_ts)` tuple）
- [ ] T008 [P] Implement `backend/app/services/maximo_tools/base.py`（`Tool` ABC + `ToolDefinition` + `ToolResult` + `UserContext` Pydantic models）
- [ ] T009 [P] Implement `backend/app/services/maximo_tools/telemetry.py`（DAO: `record_tool_call` / `record_fallback` 同步 INSERT，錯誤 swallow）

### Registry / Router 骨架

- [ ] T010 Implement `backend/app/services/maximo_tools/registry.py` 為 **auto-discovery registry**（scan `tools/` 目錄自動 import 並註冊每個繼承 `Tool` base class 的實例）— **解決 registry.py merge conflict 問題**：每個 tool 檔案自帶 `REGISTER = MyTool()`，registry.py 只做掃描，6 個 engineer 各自新增 tool 檔不再搶改 registry.py
- [ ] T011 Implement `backend/app/services/maximo_tools/router.py`（MaximoQueryRouter：Anthropic tool_use 呼叫 + single-turn 判定 + single tool_use block assertion + circuit breaker 整合 + **feature flag `MAXIMO_TOOL_ROUTER_ENABLED` 檢查**）
- [ ] T011a Implement feature flag helper in `backend/app/services/maximo_tools/feature_flag.py`（讀 env var `MAXIMO_TOOL_ROUTER_ENABLED`，預設 `true`，false 時 router 直接回 fallback）

### Pipeline Validator

- [ ] T012 [P] Implement Tool 1 `backend/app/services/maximo_tools/tools/get_vehicle_info.py`（ToolDefinition + execute + 中文化 output via `domain_mapper` + 檔尾 `REGISTER = GetVehicleInfoTool()` 供 auto-discovery 掃描）
- [ ] T013 ~~Register Tool 1 in registry~~ → **已由 T010 auto-discovery 自動處理**，不需手動註冊（保留編號避免後續 ID 錯位）

### API Wiring

- [ ] T014 Modify `backend/app/routers/maximo.py`：`POST /api/maximo/nl2sql` 入口先走 `MaximoQueryRouter`，未命中 fallback 到現有 `maximo_nl2sql` service；response 新增 `route_path` / `tool_name` / `tool_input` 欄位
- [ ] T015 Add Pydantic schemas `backend/app/models/maximo_tool_schemas.py`（`MaximoQueryRequest`, `MaximoQueryResponse` 新版）

### Foundational 測試

- [ ] T016 [P] Unit test `backend/tests/unit/maximo_tools/test_vehicle_category.py`（含 RSTF+RSTP 雙碼 IN 語意 + 反向翻譯）
- [ ] T017 [P] Unit test `backend/tests/unit/maximo_tools/test_date_range.py`（4 preset + explicit from/to）
- [ ] T018 [P] Unit test `backend/tests/unit/maximo_tools/test_telemetry.py`（mock DB + 錯誤 swallow）
- [ ] T019 [P] Unit test `backend/tests/unit/maximo_tools/test_get_vehicle_info.py`（happy / not-found / 中文化 output）
- [ ] T020 Integration test `backend/tests/integration/test_maximo_tool_router.py::test_foundational_pipeline`（Tool 1 端到端：curl → router → tool → DB → 中文化 result）

**Checkpoint**：Phase 2 完成後，整條 pipeline 可用單一 tool 驗證成功。任何 US 實作可開始。

---

## Phase 3: User Story 1 - 維修技師快速查詢工單 / 故障通報（Priority: P1）🎯 MVP

**Goal**: 維修技師在 Chat 輸入「A12345 最近一個月故障」→ 1 秒內看到結果 + UI 標記「⚡ 快速查詢」。

**Independent Test**: Chat 送 `"查 A12345 工單"` → 驗 `route_path="tool"`、`tool_name="search_workorders_by_vehicle"`、`elapsed_ms < 1000`、`rows` 與直接 SQL 查詢一致。

### Tool 2 + Tool 3（可並行派 2 個 fullstack-engineer）

- [ ] T021 [P] [US1] Implement Tool 2 `backend/app/services/maximo_tools/tools/search_workorders_by_vehicle.py`（查 `maximo_pm_workorders` UNION ALL `maximo_cm_workorders`，output 加 `wo_type:"定檢"/"臨修"`；支援 status enum **中文值** + `status_group` + date_range；row filter `maintenance_section = %s`）
- [ ] T022 [P] [US1] Implement Tool 3 `backend/app/services/maximo_tools/tools/search_faults_by_vehicle.py`（查 `maximo_fault_reports`；urgency A/B/C 過濾 + status_group + date_range；row filter `report_unit = %s`；注意 urgency 224/395 筆為空）

### 測試

- [ ] T023 [P] [US1] Unit test `backend/tests/unit/maximo_tools/test_search_workorders_by_vehicle.py`（happy / 空結果 / 各狀態過濾 / 各日期範圍 / 中文化）
- [ ] T024 [P] [US1] Unit test `backend/tests/unit/maximo_tools/test_search_faults_by_vehicle.py`（happy / 空結果 / urgency A/B/C 過濾 / 日期範圍 / 中文化）
- [ ] T025 [US1] Integration test `backend/tests/integration/test_tool_search_workorders.py`（真實 DB：A12345 驗證）
- [ ] T026 [US1] Integration test `backend/tests/integration/test_tool_search_faults.py`（真實 DB：A12345 + urgency 過濾）

### Router E2E（auto-discovery 不需手動 register）

- [ ] T027 ~~Register Tool 2 + Tool 3 in registry~~ → **auto-discovery 處理**（保留編號）
- [ ] T028 [US1] Router E2E test `backend/tests/integration/test_maximo_tool_router.py::test_us1_queries`（5 個 US1 代表 query：查工單 / 查故障 / 按日期 / 按狀態 / urgency 過濾；命中率 5/5）

**Checkpoint**：US1 可獨立展示 — 任意車號的工單/故障查詢，延遲 <1s。

---

## Phase 4: User Story 2 - 管理者車輛分類統計（Priority: P1）

**Goal**: 管理者問「各大分類未結案工單」→ 秒回帶 chart_hint 的統計資料；可直接丟給 Dashboard Recharts。

**Independent Test**: curl `POST /api/maximo/nl2sql` with `"各大分類未結案工單"` → 驗 `route_path="tool"`、`tool_name="count_open_workorders_by_category"`、`rows` 含三類（動力車/客車/貨車），貨車數量為 RSTF+RSTP 合計。

### Tool 5 + Tool 6（可並行派 2 個 fullstack-engineer）

- [ ] T029 [P] [US2] Implement Tool 5 `backend/app/services/maximo_tools/tools/count_open_workorders_by_category.py`（UNION ALL `maximo_pm_workorders` + `maximo_cm_workorders` → filter `status NOT IN ('工單結案','工單取消','工單退回')` → JOIN `maximo_mxasset` → **`WHERE a.eq11 IS NOT NULL AND a.eq11 != ''`** → group_by 大分類/車種/車型 → count + percentage + chart_hint）
- [ ] T030 [P] [US2] Implement Tool 6 `backend/app/services/maximo_tools/tools/list_open_workorders_in_category.py`（level + value → 中文→eq 代碼轉換 → 貨車雙碼 `eq11 = ANY(ARRAY['RSTF','RSTP'])` → UNION ALL 兩張工單表 + eq11 NOT NULL filter → 查工單明細）

### 測試

- [ ] T031 [P] [US2] Unit test `backend/tests/unit/maximo_tools/test_count_open_workorders_by_category.py`（三種 group_by + chart_hint 格式）
- [ ] T032 [P] [US2] Unit test `backend/tests/unit/maximo_tools/test_list_open_workorders_in_category.py`（三層 level + 貨車雙碼 IN 驗證）
- [ ] T033 [US2] Integration test `backend/tests/integration/test_tool_count_workorders.py`（真實 DB：三種 group_by 的 percentage 總和 = 100）
- [ ] T034 [US2] Integration test `backend/tests/integration/test_tool_list_category.py`（真實 DB：輸入「貨車」→ SQL 必含 `eq11 IN ('RSTF','RSTP')`）

### Router E2E

- [ ] T035 ~~Register Tool 5 + 6 in registry~~ → **auto-discovery 處理**
- [ ] T036 [US2] Router E2E test `backend/tests/integration/test_maximo_tool_router.py::test_us2_queries`（4 個 US2 代表 query：「各大分類」/ 「客車清單」/「貨車清單」/「EMU3000 清單」；命中率 4/4；貨車 IN ('RSTF','RSTP') 驗證）

**Checkpoint**：US2 可展示 — 各車輛階層的未結案統計與明細。

---

## Phase 5: User Story 3 - 車輛基本資料 + 按車次查故障（Priority: P2）

**Goal**: 使用者問「A00567 車型」或「近 30 天故障分布」→ 對應 Tool 1 / Tool 7，回傳中文化結果。車次查詢 (Tool 4) 已 defer 到 Phase 2。

**Independent Test**:
1. `"A00567 基本資料"` → `tool_name="get_vehicle_info"`（Tool 1 已在 Foundational 完成）+ status 英文→中文翻譯
2. `"近 30 天故障等級分布"` → `tool_name="get_recent_fault_distribution"`、A/B/C 分布 + chart_hint + urgency NULL 排除

### Tool 7（Tool 4 deferred to Phase 2）

- [ ] ~~T037 [P] [US3] Implement Tool 4 search_faults_by_trip~~ **→ Deferred to Phase 2**（2026-04-20 實測 `plusaflightnum` 不存在於 ETL 表 + mxsr；ETL 補完後再做）
- [ ] T038 [P] [US3] Implement Tool 7 `backend/app/services/maximo_tools/tools/get_recent_fault_distribution.py`（date_range + group_by: urgency/section；查 `maximo_fault_reports`；urgency 需 filter `IS NOT NULL AND != ''`）

### 測試

- [ ] ~~T039~~ （Tool 4 deferred）
- [ ] T040 [P] [US3] Unit test `backend/tests/unit/maximo_tools/test_get_recent_fault_distribution.py`（urgency A/B/C 分布 + section 分組 + percentage 驗證 + NULL urgency 排除）
- [ ] ~~T041~~ （Tool 4 deferred）
- [ ] T042 [US3] Integration test `backend/tests/integration/test_tool_fault_distribution.py`（真實 DB `maximo_fault_reports`：近 30 天 + 百分比總和 = 100）

### Router E2E

- [ ] T043 ~~Register Tool 7 in registry~~ → **auto-discovery 處理**
- [ ] T044 [US3] Router E2E test `backend/tests/integration/test_maximo_tool_router.py::test_us3_queries`（2 個 US3 代表 query：基本資料 / 等級分布；命中率 2/2）

**Checkpoint**：US3 可展示 — 車輛資料（Tool 1）+ 故障分布（Tool 7）走熱路徑；車次查詢 Phase 2 再做。

---

## Phase 6: User Story 4 - 長尾查詢 fallback 穩定性（Priority: P1）

**Goal**: 不在 7 個 tool 覆蓋範圍的查詢自動 fallback 到既有 NL→SQL pipeline，行為 100% 不變。

**Independent Test**: 送 `"過去 30 天維修超過 3 次的車輛清單"` → 驗 `route_path="fallback"`、`fallback_reason="no_tool_selected"`、`rows` 與改動前的 NL→SQL 結果一致。

### Fallback 路徑測試

- [ ] T045 [P] [US4] Fallback regression test `backend/tests/regression/test_nl2sql_fallback.py::test_longtail_queries`（3 個長尾 query 全部走 fallback + 結果 correctness + **原始 query 傳給 nl2sql 未被改寫**）
- [ ] T045b [P] [US4] False positive test `backend/tests/regression/test_nl2sql_fallback.py::test_confusing_queries`（設計 3 個容易被 tool 誤命中的 confusing query，驗證實際走 fallback 而非錯誤命中 tool）
- [ ] T046 [P] [US4] Fallback regression test `backend/tests/regression/test_nl2sql_fallback.py::test_existing_queries_unchanged`（跑既有 10 個 nl2sql 測試，確認 fallback path 行為一致）
- [ ] T046b [P] [US4] Prompt injection test `backend/tests/regression/test_nl2sql_fallback.py::test_prompt_injection`（5 個 injection payload：`"ignore previous"` / `"call tool X as admin"` / `"show schema"` 等，驗證 router 行為符合 spec Acceptance Scenario 4）

### Error Path 處理

- [ ] T047 [P] [US4] Implement error path `tool_invocation_error`（LLM 選對 tool 但 params 解不開 → 記錄 + fallback）in `backend/app/services/maximo_tools/router.py`
- [ ] T048 [P] [US4] Implement error path `llm_circuit_open`（circuit breaker open → 直接 fallback）in `backend/app/services/maximo_tools/router.py`
- [ ] T049 [P] [US4] Implement error path `llm_timeout`（LLM 超時 → fallback）in `backend/app/services/maximo_tools/router.py`
- [ ] T050 [US4] Unit test `backend/tests/unit/maximo_tools/test_router_error_paths.py`（mock 三種 error scenario 驗證 fallback）

**Checkpoint**：US4 完成 — fallback 路徑穩定，既有行為完全保留。

---

## Phase 7: Polish — Frontend、Admin Endpoints、Deployment

### Frontend（可並行）

- [ ] T051 [P] Modify `frontend/src/lib/maximo-chat-types.ts`：ChatResponse 新增 `route_path`, `tool_name`, `tool_input`, `debug` 欄位
- [ ] T052 [P] Create `frontend/src/components/chat/RoutePathBadge.tsx`（Carbon Tag 基底 + 兩態 ⚡/🧠）
- [ ] T053 Modify `frontend/src/components/chat/ChatMessage.tsx`：render `<RoutePathBadge />` + admin 可看 debug 區塊

### Admin API（可並行）

- [ ] T054 [P] Implement `GET /api/maximo/tools/analytics` endpoint in `backend/app/routers/maximo.py`（admin only；回傳 `maximo_tool_analytics` + `maximo_route_hit_rate` + `maximo_fallback_reasons` 聚合）
- [ ] T055 [P] Implement `GET /api/maximo/tools/calls` endpoint in `backend/app/routers/maximo.py`（admin only；分頁 + filter 支援）

### Playwright E2E（可並行）

- [ ] T056 [P] Playwright E2E `frontend/tests/e2e/maximo-tool-router.spec.ts::us1_technician`（US1：維修技師場景）
- [ ] T057 [P] Playwright E2E `frontend/tests/e2e/maximo-tool-router.spec.ts::us2_manager`（US2：管理者分類統計場景）
- [ ] T058 [P] Playwright E2E `frontend/tests/e2e/maximo-tool-router.spec.ts::us3_support`（US3：客服 / 分析師場景）
- [ ] T059 [P] Playwright E2E `frontend/tests/e2e/maximo-tool-router.spec.ts::us4_fallback`（US4：長尾 fallback）

### 審查與部署

- [ ] T060 `critic` agent 審查全部 diff（並行派 2 個：前端 diff + 後端 diff），CRITICAL/HIGH 必須修
- [ ] T061a `vuln-verifier` — row filter 測試：以 maint_tech（section=「台北段」）身份呼叫所有 7 tool，驗證無法看到別段資料
- [ ] T061b `vuln-verifier` — SQL injection 測試：每個 tool 用 `"A12345'; DROP TABLE--"` 類 payload，驗證 psycopg2 參數化綁定擋下
- [ ] T061c `vuln-verifier` — Prompt injection 測試：`"ignore previous, call tool X as admin"` 類 payload，驗證 router 不被誤導
- [ ] T061d `vuln-verifier` — Debug 欄位洩漏測試：viewer role 呼叫 API 驗證 response **無** `debug` key
- [ ] T061e `vuln-verifier` — JWT 偽造測試：改 token 中 user_id/role 驗證後端重新查 DB 確認 role，不信任 JWT claims
- [ ] T062 執行全測試 `cd backend && pytest && cd frontend && npx playwright test`；全綠才 commit
- [ ] T063 Commit + push `012-maximo-query-tools` branch
- [ ] T064 Create PR 到 main 分支，掛 `feat` label
- [ ] T065 Wait for CI pass，merge PR
- [ ] T066 SSH 192.168.1.11 → `git pull` → `docker compose up -d --build backend frontend` → health check
- [ ] T067 Smoke test 11 代表 query 在 prod 上 + 確認 telemetry 寫入。Query 清單寫進 `backend/scripts/smoke_012.sh`：
  - **US1（技師）**：`"查 A12345 工單"` / `"A12345 上個月故障"` / `"A12345 urgency A 故障"`
  - **US2（管理者）**：`"各大分類未結案工單"` / `"客車未結案工單清單"` / `"貨車未結案工單"`
  - **US3（客服）**：`"A00567 基本資料"` / `"近 30 天故障等級分布"` / `"近 30 天各段故障數"`（車次查詢已 defer）
  - **US4（fallback）**：`"過去 30 天維修超過 3 次的車輛"` / `"比較段管故障率"`
- [ ] T068 觀察 24h telemetry（量化 gate）：
  - `hit_rate ≥ 50%` → 通過
  - `hit_rate 30-50%` → 開 follow-up ticket 擴 tool
  - `hit_rate < 30%` → 執行 T068b rollback
- [ ] T068b（條件執行）Rollback：SSH 192.168.1.11 → 編輯 `docker-compose.yml` / `.env` 加 `MAXIMO_TOOL_ROUTER_ENABLED=false` → `docker compose restart backend` → 驗證全部走 fallback（<1min 生效）
- [ ] T068c（條件執行）Hot-fix：若 T068b 仍有問題，`git revert <merge-commit>` + redeploy（<10min）
- [ ] T069 Update `memory/MEMORY.md` + `memory/daily/2026-04-20.md`（由 `/update-memory` 產出）
- [ ] T069b Update `docs/maximo_tool_router.md`：列 7 tool 定義 + analytics endpoint 範例 + admin 操作指南 + rollback SOP

---

## Dependencies & Execution Order

### Phase 依賴圖

```text
Phase 1 Setup (T001-T003)
    ↓
Phase 2 Foundational (T004-T020)  ← 阻塞所有 User Story
    ↓
    ├─→ Phase 3 US1 (T021-T028)  ← MVP
    ├─→ Phase 4 US2 (T029-T036)  ← 可並行 US1
    ├─→ Phase 5 US3 (T037-T044)  ← 可並行 US1/US2
    └─→ Phase 6 US4 (T045-T050)  ← 可並行其他 US
         ↓
Phase 7 Polish (T051-T069)
```

### 任務內依賴

**Foundational 內部依賴鏈**：
- T004 → T005（migration 先寫才能 apply）
- T006/T007/T008/T009 可並行（不同檔案）
- T008 → T010（registry 依賴 base class）
- T008 → T011（router 依賴 base class）
- T010 → T011（router 依賴 registry）
- T011 → T012（tool 1 依賴 router 已 skeleton）
- T012 → T013（先實作才能註冊）
- T013 → T014（registry + tool 1 → 改 API 入口）
- T014 → T015（schema 定義要對齊 API）
- T020 需等 T012+T013+T014 完成

**每個 US 內部依賴**：
- Tool 實作（`.py`） → Unit test → Integration test → Register → Router E2E

### 可並行的任務

**Day 1 Foundational 平行窗口**：
- T006 + T007 + T008 + T009（4 個 fullstack-engineer 並行）
- T016 + T017 + T018 + T019（測試 4 個並行）

**Day 3-4 US1+US2+US3 平行窗口**（Phase 2 完成後）：
- T021 + T022（US1 Tool 2+3 並行）
- T029 + T030（US2 Tool 5+6 並行）
- T038（US3 Tool 7 單線，因 Tool 4 defer）
- 共 **5 個 tool 檔案可同時派 5 個 fullstack-engineer**

**Phase 7 Polish 並行窗口**：
- T051+T052+T054+T055+T056-T059（前端 + admin API + E2E 可同時進行）

---

## Parallel Execution Examples

### Day 1 Foundational 並行派遣

```bash
# 同一則訊息派 4 個 fullstack-engineer（並行）
Task T006: "Implement backend/app/services/maximo_tools/mappers/vehicle_category.py..."
Task T007: "Implement backend/app/services/maximo_tools/mappers/date_range.py..."
Task T008: "Implement backend/app/services/maximo_tools/base.py..."
Task T009: "Implement backend/app/services/maximo_tools/telemetry.py..."
```

### Day 3 Tool 並行派遣（Foundational 完成後）

```bash
# 同一則訊息派 5 個 fullstack-engineer（並行實作 5 個 tool；Tool 4 已 defer 到 Phase 2）
Task T021 [US1]: "Implement Tool 2 search_workorders_by_vehicle..."
Task T022 [US1]: "Implement Tool 3 search_faults_by_vehicle..."
Task T029 [US2]: "Implement Tool 5 count_open_workorders_by_category..."
Task T030 [US2]: "Implement Tool 6 list_open_workorders_in_category..."
Task T038 [US3]: "Implement Tool 7 get_recent_fault_distribution..."
```

---

## Implementation Strategy

### MVP First（US1 + US2 + US4 — 全部 P1 story，與排程一致）

**修訂**（2026-04-20 複審後對齊）：spec 明標 US1/US2/US4 為 P1；Day 3 排程本來就包含 US2 的 Tool 5/6；MVP 定義應與實際排程一致，**不做「文件遊戲」**。US3（P2）才是真正可 delay 的部分。

1. Complete Phase 1 Setup
2. Complete Phase 2 Foundational（**關鍵阻塞**）
3. Complete Phase 3 US1 + Phase 4 US2 + Phase 6 US4（Day 3 並行）
4. Complete Phase 7 前端 badge + vuln-verifier
5. **STOP & VALIDATE**：US1 技師查詢 <1s + US2 管理者分類統計 <1s + US4 fallback regression 全過
6. Deploy MVP to 192.168.1.11（先 canary，FEATURE_FLAG 預設 true）
7. US3（車次查詢 + 等級分布）可在 MVP 上線後隔天追加

**MVP 展示價值**：
- 維修技師查工單/故障 4-5s → <1s
- 管理者 Dashboard 分類統計即時出圖
- 長尾查詢行為 100% 不變

### Incremental Delivery

1. Setup + Foundational → 整條 pipeline 可跑（Tool 1 驗證）
2. + US1 → 維修技師場景（MVP）
3. + US2 → 管理者 Dashboard 統計
4. + US3 → 車次查詢 + 故障分布
5. + US4 → 長尾 fallback 穩定性
6. + Phase 7 → 前端 badge + admin analytics + 部署

每個增量都可獨立部署、不破壞前一版行為。

### Parallel Team Strategy（**6 天完成，含 1 天 buffer**）

**修訂**：原 5 天太緊沒 buffer；實務上 tool 實作 + critic 返修會吃掉半天。

```
Day 1 上午:  [Foundational A]  4 engineers 並行 T006/T007/T008/T009
Day 1 下午:  [Foundational B]  1 engineer T010→T011 串行（registry 要先於 router）
Day 2:       [Tool 1 + Wiring] 1 engineer T012→T014→T015→T016-T020 testing
Day 3:       [Tool 爆發]        **5 engineers** 並行 T021/T022/T029/T030/T038
             （Tool 4 已 defer；auto-discovery registry 已解決 merge conflict）
Day 4:       [US4 + Error Path] 3 engineers 並行 T045/T045b/T046/T046b/T047-T050
Day 5:       [Frontend + E2E]   2 engineers T051-T059 並行
Day 6:       [Critic + Deploy]  T060-T069b（critic 返修、部署、觀察）
Day 6 晚段:  [Buffer]            預留給 CRITICAL/HIGH 返修
```

**關鍵依賴修正**：
- T011 router 依賴 T008 base + T010 registry → **不能 Day 1 上午與 T008 並行**，必須排 Day 1 下午或 Day 2 早段
- T014 API wiring 依賴 T011 router + T015 schema → 排 Day 2
- T016-T020 測試依賴前述 → 排 Day 2 下午

---

## P9 Task Prompt Templates（供 fullstack-engineer 直接領取）

以下為關鍵任務的 Task Prompt，每份含 P9 六要素（目標 / 範圍 / 輸入 / 輸出 / 驗收標準 / 邊界）。Claude 派遣時用這些作為 prompt 主體。

### Template: T006 vehicle_category mapper

```
[P7 Task]
目標：實作中文↔eq11 代碼雙向對照，特別處理「貨車」對應雙碼（RSTF + RSTP）。

範圍：
- 新建檔案 backend/app/services/maximo_tools/mappers/vehicle_category.py

輸入（依賴）：
- spec.md FR-013/FR-014
- data-model.md 中 mxasset.eq11 欄位說明

輸出：
- `VEHICLE_CATEGORY_CODES: dict[str, list[str]]`：{"動力車":["RSTL"], "客車":["RSTA"], "貨車":["RSTF","RSTP"]}
- `to_codes(chinese: str) -> list[str]`：中文→代碼列表（unknown 回 [chinese] 原值）
- `from_code(code: str) -> str`：代碼→中文（unknown 回 code 原值）
- `CATEGORY_LEVEL_FIELD: dict[str, str]`：{"大分類":"eq11","車種":"eq3","車型":"eq4"}

驗收標準：
- `to_codes("貨車")` 回 `["RSTF","RSTP"]`
- `from_code("RSTA")` 回 `"客車"`
- `from_code("RSTF")` 和 `from_code("RSTP")` 都回 `"貨車"`
- T016 unit test 全過

邊界：
- 不使用任何 DB / LLM call（純 in-memory dict）
- 不處理車種 / 車型的代碼對照（那些由既有 domain_mapper 處理）
- 不 import Pydantic（純 Python dict + function）
```

### Template: T011 router skeleton

```
[P7 Task]
目標：實作 MaximoQueryRouter — 以 Claude tool_use 決定路由，命中走 tool / 未命中走 fallback。

範圍：
- 新建檔案 backend/app/services/maximo_tools/router.py

輸入（依賴）：
- T008 base.py（Tool ABC + UserContext）
- T010 registry.py（ToolRegistry 介面）
- T009 telemetry.py（record_tool_call / record_fallback）
- research.md R1/R7/R8（LLM provider / fallback 判定 / system prompt）
- contracts/tool-api.md（response schema）
- 既有 backend/app/services/circuit_breaker.py（整合 LLM 斷路器）

輸出：
- class `MaximoQueryRouter`：
  - `__init__(registry, anthropic_client, circuit_breaker, fallback_fn: Callable)`
  - `async route(query: str, user_ctx: UserContext, query_id: UUID) -> dict`
    - 1. 呼叫 Claude Sonnet 4.6 with tools
    - 2. 判 `stop_reason`：`tool_use` → dispatch Tool.execute；`end_turn` → fallback
    - 3. 整合 circuit breaker：open 時直接 fallback
    - 4. 每條路徑都寫 telemetry
  - 回傳 `{route_path, tool_name, tool_input, rows, row_count, chart_hint, elapsed_ms, debug}`
- fallback_fn 介面：`async fallback_fn(query: str, user_ctx: UserContext) -> dict`

驗收標準：
- `test_foundational_pipeline`（T020）通過
- 5 個 error scenario 都有明確 fallback_reason：
  `no_tool_selected` / `tool_invocation_error` / `llm_circuit_open` / `llm_timeout` / `tool_execution_error`
- 每個 route_path 都寫一筆 maximo_tool_calls 記錄

邊界：
- 不實作任何 tool（那是 Tool class 的事）
- 不改 existing maximo_nl2sql.py（只透過 fallback_fn 呼叫它）
- 不改 frontend（只吐新版 response）
- 不做 confidence threshold（信任 Claude stop_reason）
```

### Template: T021 Tool 2 search_workorders_by_vehicle

```
[P7 Task]
目標：實作 Tool 2「依車號查工單」，UNION ALL PM+CM 兩張 ETL 表。

範圍：
- 新建檔案 backend/app/services/maximo_tools/tools/search_workorders_by_vehicle.py

輸入（依賴）：
- T008 base.py（Tool ABC）
- T007 date_range.py（enum → timestamp）
- 既有 domain_mapper.py（status 不需再翻，DB 已中文）
- contracts/tool-api.md Tool 2 schema
- data-model.md maximo_pm_workorders + maximo_cm_workorders 欄位

輸出：
- class `SearchWorkordersByVehicleTool(Tool)`：
  - `definition = ToolDefinition(name="search_workorders_by_vehicle", description="...", input_schema={...})`
  - input schema 包含：asset_num, status (9 種中文 enum), status_group (open/closed/cancelled), wo_type (定檢/臨修/all), date_range
  - `async execute(params: dict, user_ctx: UserContext) -> ToolResult`
    - parameterized SQL: 
      ```sql
      SELECT wonum, assetnum, status, '定檢' AS wo_type, work_type, description, report_date, act_finish
      FROM maximo_pm_workorders
      WHERE assetnum = %s [AND status = %s | status IN (%s...)]
        [AND report_date BETWEEN %s AND %s]
        [AND maintenance_section = %s]
      UNION ALL
      SELECT wonum, assetnum, status, '臨修' AS wo_type, work_type, description, report_date, act_finish
      FROM maximo_cm_workorders
      WHERE assetnum = %s [...]
      ORDER BY report_date DESC
      LIMIT %s
      ```
    - status 已中文不需再翻
    - rows 回傳含 `工單號 / 車號 / 狀態 / 工單類型 / 工作類型 / 描述 / 通報日期 / 實際完工`

驗收標準：
- T023 unit test 全過
- T025 integration test（真實 DB）：A12345 回傳正確工單 + 狀態已中文化
- SQL 走 **psycopg2** 參數化綁定 `cursor.execute(sql, (params,))`（grep 檢查無 f-string/.format）
- 整合 `user_ctx.section` 做 row filter（SQL 含 `maintenance_section = %s`，對應 PM/CM ETL 表）
- **檔尾必須有 `REGISTER = SearchWorkordersByVehicleTool()` 供 auto-discovery 掃描**

邊界：
- 不動既有 maximo_nl2sql.py
- 不做多 asset 批次查詢（單車號 only）
- 不做 pagination（結果 >500 筆未來再加）
- 不 cache（維持即時性）
```

### Template: T022 Tool 3 search_faults_by_vehicle

```
[P7 Task]
目標：實作 Tool 3「依車號查故障通報」，查 maximo_fault_reports ETL 表。

範圍：
- 新建檔案 backend/app/services/maximo_tools/tools/search_faults_by_vehicle.py

輸入（依賴）：
- T008 base.py + T007 date_range.py + 既有 domain_mapper.py
- contracts/tool-api.md Tool 3 schema
- data-model.md maximo_fault_reports 欄位（ETL，非 mxsr）

輸出：
- class `SearchFaultsByVehicleTool(Tool)`:
  - ToolDefinition with input_schema = `{asset_num, urgency?:A|B|C, status_group?, date_range?, from_date?, to_date?}`
  - execute() → SQL: 
    ```sql
    SELECT ticketid, assetnum, description, status, urgency, grade, tcms_code, report_date
    FROM maximo_fault_reports
    WHERE assetnum = %s
      [AND urgency = %s]
      [AND status IN ('立案','接件中','處理中')]   -- status_group=open
      [AND report_date BETWEEN %s AND %s]
      [AND report_unit = %s]                        -- row filter
    ORDER BY report_date DESC
    LIMIT %s
    ```
  - status 已中文不需再翻；urgency A/B/C 原樣
  - rows 回傳含 `通報號 / 車號 / 描述 / 狀態 / 故障等級 / TCMS碼 / 通報日期`
- 檔尾 `REGISTER = SearchFaultsByVehicleTool()` 給 auto-discovery

驗收標準：
- T024 unit test 全過（含 urgency NULL 排除）
- T026 integration test（真實 DB：某 asset + urgency=A）
- Row filter 注入 `report_unit = %s`
- grep 驗證無 f-string SQL

邊界：
- 不做 SR→WO join（Phase 2）
- urgency NULL 的通報不會被 urgency filter 命中（符合現實：沒填等級就不按等級查）
```

### Template: T029 Tool 5 count_open_workorders_by_category

```
[P7 Task]
目標：實作 Tool 5「未結案工單按車輛階層統計」，for dashboard 圖表。

範圍：
- 新建檔案 backend/app/services/maximo_tools/tools/count_open_workorders_by_category.py

輸入（依賴）：
- T006 vehicle_category.py（中文↔eq11 雙向 + 貨車雙碼 IN 處理）
- 既有 domain_mapper.py
- contracts/tool-api.md Tool 5 schema

輸出：
- class `CountOpenWorkordersByCategoryTool(Tool)`:
  - input_schema = `{group_by: 大分類|車種|車型}`
  - execute() → SQL:
    ```sql
    WITH wo AS (
        SELECT assetnum, status, maintenance_section FROM maximo_pm_workorders
        WHERE status NOT IN ('工單結案','工單取消','工單退回')
        UNION ALL
        SELECT assetnum, status, maintenance_section FROM maximo_cm_workorders
        WHERE status NOT IN ('工單結案','工單取消','工單退回')
    )
    SELECT
      CASE WHEN a.eq11 IN ('RSTF','RSTP') THEN '貨車'
           ELSE <map_eq11_to_chinese>(a.eq11)
      END AS category,
      COUNT(*) AS count,
      ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS percentage
    FROM wo
    JOIN maximo_mxasset a ON wo.assetnum = a.assetnum
    WHERE a.eq11 IS NOT NULL AND a.eq11 != ''  -- ⚠️ 排除 48% 空值
      [AND wo.maintenance_section = %s]         -- row filter
    GROUP BY 1
    ORDER BY count DESC
    ```
  - 輸出含 `chart_hint: {type: "pie", x_field: "category", y_field: "count"}`

驗收標準：
- T031 unit test 三種 group_by 都過
- T033 integration test：percentage 總和 = 100
- 貨車雙碼合併後**恰好 3 列**（大分類 group_by）
- 不改既有 dashboard API
- **檔尾必須有 `REGISTER = CountOpenWorkordersByCategoryTool()` 供 auto-discovery 掃描**

邊界：
- 只查 OPEN 狀態分組的工單（不含 COMP/CLOSE/CAN）
- 不做 depot-level 過濾（非本 tool 責任）
```

### Template: T030 Tool 6 list_open_workorders_in_category

```
[P7 Task]
目標：實作 Tool 6「列出指定車輛階層下的未結案工單明細」，支援中文輸入自動轉代碼。

範圍：
- 新建檔案 backend/app/services/maximo_tools/tools/list_open_workorders_in_category.py

輸入（依賴）：
- T006 vehicle_category.py
- 既有 domain_mapper.py
- contracts/tool-api.md Tool 6 schema

輸出：
- class `ListOpenWorkordersInCategoryTool(Tool)`:
  - input_schema = `{level: 大分類|車種|車型, value: str}`（value 中文，如「客車」「EMU3000」）
  - execute() 邏輯：
    1. `CATEGORY_LEVEL_FIELD[level]` 取得欄位（eq11/eq3/eq4）
    2. 若 level=大分類：呼叫 `vehicle_category.to_codes(value)` → list；SQL 用 `{field} = ANY(%s)` 綁定
    3. 若 level=車種/車型：SQL 用 `{field} = %s`（單值）
    4. `WITH wo AS (SELECT ... FROM maximo_pm_workorders UNION ALL SELECT ... FROM maximo_cm_workorders) SELECT wonum, assetnum, a.eq3, a.eq4, a.eq11, wo.status, wo.description, wo.report_date FROM wo JOIN maximo_mxasset a ON ... WHERE {level_filter} AND wo.status NOT IN ('工單結案','工單取消','工單退回') AND a.eq11 IS NOT NULL [AND wo.maintenance_section = %s]`
    5. status 已中文；eq11 代碼→中文由 vehicle_category_mapper 處理

驗收標準：
- T032 unit test：三層 level + 貨車輸入 → SQL 含 `eq11 = ANY(ARRAY['RSTF','RSTP'])`
- T034 integration test：輸入「貨車」→ SQL 實際執行且 WHERE 語意正確
- Row filter 注入 `wo.maintenance_section = %s`（ETL 表欄位）
- **檔尾必須有 `REGISTER = ListOpenWorkordersInCategoryTool()` 供 auto-discovery 掃描**

邊界：
- 若輸入的 value 沒對應代碼（如「飛機」），回空結果 + fallback_reason="unknown_category_value"
- Pagination 支援 page_size 預設 50，max 200（FR-024）
```

### ~~Template: T037 Tool 4 search_faults_by_trip~~

**Deferred to Phase 2** — 2026-04-20 實測 `maximo_fault_reports` 與 `maximo_mxsr` 均無 `plusaflightnum` 欄位。ETL 補完車次欄位後再實作。

### Template: T038 Tool 7 get_recent_fault_distribution

```
[P7 Task]
目標：實作 Tool 7「近期故障通報等級分布」，查 maximo_fault_reports ETL 表，for dashboard 分布圖。

範圍：
- 新建檔案 backend/app/services/maximo_tools/tools/get_recent_fault_distribution.py

輸入（依賴）：
- T007 date_range.py + 既有 domain_mapper.py
- contracts/tool-api.md Tool 7 schema

輸出：
- class `GetRecentFaultDistributionTool(Tool)`:
  - input_schema = `{date_range?, group_by: urgency|section}`
  - execute() → SQL:
    - group_by=urgency:
      ```sql
      SELECT urgency, COUNT(*) AS count,
             ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS percentage
      FROM maximo_fault_reports
      WHERE report_date BETWEEN %s AND %s
        AND urgency IS NOT NULL AND urgency != ''   -- ⚠️ 排除 224/395 空值
      GROUP BY urgency
      ORDER BY urgency
      ```
    - group_by=section:
      ```sql
      SELECT report_unit AS section, COUNT(*) AS count, ...
      FROM maximo_fault_reports
      WHERE report_date BETWEEN %s AND %s
      GROUP BY report_unit
      ORDER BY count DESC
      ```
  - chart_hint: `{type: "bar", x_field: "urgency"|"section", y_field: "count"}`

驗收標準：
- T040 unit test：A/B/C 三級 + percentage 總和 = 100% + NULL urgency 排除
- T042 integration test：近 30 天真實資料分布正確
- Row filter 若 role 是 maint_tech：限縮在 user.section
- **檔尾必須有 `REGISTER = GetRecentFaultDistributionTool()` 供 auto-discovery 掃描**

邊界：
- 時間維度固定用 report_date（非 confirm_date）
- urgency NULL 的通報不計入 urgency group_by 分子分母
```

> 以上 4 份 Task Prompt（T022/T029/T030/T038；T037 Tool 4 已 defer）加上先前 T006/T011/T021 共 **7 份**，完整覆蓋所有本期高風險實作任務。fullstack-engineer 可直接領取。

---

## 任務總計（2026-04-20 二次修訂：Tool 7→6 個，車次查詢 defer）

| Phase | 任務數 | 並行 slots | 預計天數 |
|-------|-------|-----------|---------|
| 1 Setup | 3 | 1 | 0.2 |
| 2 Foundational | 18 | 4 | 1.5 |
| 3 US1 | 8 | 3 | 0.8 |
| 4 US2 | 8 | 3 | 0.8 |
| 5 US3 | 5（Tool 4 deferred） | 2 | 0.4 |
| 6 US4 | 8 | 3 | 0.6 |
| 7 Polish | 25 | 6 | 2.0 |
| **總計** | **75** | — | **6.3** |

**Tool 清單（本期 6 個；編號保留對齊原 spec 避免 cross-ref 錯位）**：
1. get_vehicle_info
2. search_workorders_by_vehicle（PM + CM UNION）
3. search_faults_by_vehicle（fault_reports ETL）
4. ~~search_faults_by_trip~~ → **Phase 2**
5. count_open_workorders_by_category
6. list_open_workorders_in_category
7. get_recent_fault_distribution

本期生效：1, 2, 3, 5, 6, 7（共 6 個）

**時程**：規劃 **6 天 + 1 天 buffer = 7 天**（比先前 5 天更現實）

**關鍵新增**：
- T011a feature_flag.py（rollback 機制）
- T045b/T046b false positive + prompt injection 測試
- T061a-e vuln-verifier 拆成 5 個專項（row filter / SQL injection / prompt injection / debug leak / JWT 偽造）
- T068b/c 條件 rollback 任務（hit_rate <30% 時觸發）
- T069b docs 更新

---

## Notes

- `[P]` 任務可在同一天派遣給不同 engineer（不同檔案，無依賴）
- `[Story]` label 用於追溯（每個 US 獨立可交付）
- 每個 tool 的 Task Prompt 六要素已內嵌，`fullstack-engineer` 可直接領取
- 每個 Phase 末尾 checkpoint 強制派 `critic` 審查再進下一階段（不用手工記憶）
- 測試 failure 先用 `debugger` agent 排查，不自行猜測原因
