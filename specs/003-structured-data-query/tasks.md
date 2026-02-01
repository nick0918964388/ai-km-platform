# Tasks: 結構化資料查詢

**Input**: Design documents from `/specs/003-structured-data-query/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.yaml

**Tests**: 未明確要求測試，本任務清單不包含測試任務。

**Organization**: 任務依 User Story 組織，支援獨立實作與測試。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行執行（不同檔案、無依賴）
- **[Story]**: 所屬 User Story（US1、US2、US3、US4）
- 所有路徑皆為絕對路徑

---

## Phase 1: Setup (共用基礎設施)

**Purpose**: 專案初始化與基礎結構

- [ ] T001 新增 PostgreSQL 依賴至 backend/requirements.txt (sqlalchemy[asyncio], asyncpg, alembic)
- [ ] T002 [P] 更新 docker-compose.yml 加入 PostgreSQL 服務
- [ ] T003 [P] 新增前端圖表庫依賴至 frontend/package.json (recharts)
- [ ] T004 建立資料庫連線模組 backend/app/db/__init__.py
- [ ] T005 建立資料庫 session 管理 backend/app/db/session.py
- [ ] T006 初始化 Alembic 遷移框架於 backend/alembic/

---

## Phase 2: Foundational (基礎模型 - 阻塞性前置任務)

**Purpose**: 所有 User Story 共用的核心基礎設施

**⚠️ CRITICAL**: 此階段完成前，任何 User Story 皆無法開始

- [ ] T007 [P] 建立 Vehicle 模型 backend/app/models/structured/vehicle.py
- [ ] T008 [P] 建立 FaultRecord 模型 backend/app/models/structured/fault_record.py
- [ ] T009 [P] 建立 MaintenanceRecord 模型 backend/app/models/structured/maintenance.py
- [ ] T010 [P] 建立 UsageRecord 模型 backend/app/models/structured/usage.py
- [ ] T011 [P] 建立 PartsUsed 模型 backend/app/models/structured/parts.py
- [ ] T012 [P] 建立 CostRecord 模型 backend/app/models/structured/cost.py
- [ ] T013 [P] 建立 PartsInventory 模型 backend/app/models/structured/parts.py (與 PartsUsed 同檔)
- [ ] T014 建立結構化模型 __init__.py 匯出 backend/app/models/structured/__init__.py
- [ ] T015 建立 Alembic 初始遷移腳本 backend/alembic/versions/001_initial_structured_tables.py
- [ ] T016 建立測試資料 seed script backend/scripts/seed_data.py
- [ ] T017 更新環境變數範例 backend/.env.example (加入 DATABASE_URL)

**Checkpoint**: 基礎架構就緒 - User Story 實作可開始

---

## Phase 3: User Story 1 - 自然語言查詢車輛故障歷程 (Priority: P1) 🎯 MVP

**Goal**: 維修技師可透過自然語言查詢車輛故障歷程，系統自動轉換為 SQL 並返回資料卡片

**Independent Test**: 輸入「查詢 EMU801 故障歷程」→ 返回正確的故障紀錄清單

### Implementation for User Story 1

- [ ] T018 [US1] 建立 NL2SQL 服務 backend/app/services/nl2sql_service.py
- [ ] T019 [US1] 建立 SQL 驗證器（白名單、安全檢查）於 nl2sql_service.py
- [ ] T020 [US1] 建立結構化查詢服務 backend/app/services/structured_query.py
- [ ] T021 [US1] 建立故障歷程查詢 API backend/app/routers/structured.py (GET /structured/vehicles/{code}/faults)
- [ ] T022 [US1] 建立統一查詢 API backend/app/routers/query.py (POST /query)
- [ ] T023 [P] [US1] 建立前端 DataCard 元件 frontend/src/components/structured/DataCard.tsx
- [ ] T024 [P] [US1] 建立前端 DataTable 元件 frontend/src/components/structured/DataTable.tsx
- [ ] T025 [US1] 建立 useStructuredQuery Hook frontend/src/hooks/useStructuredQuery.ts
- [ ] T026 [US1] 整合 DataCard 至現有對話介面 frontend/src/components/chat/MessageList.tsx
- [ ] T027 [US1] 新增結構化查詢結果類型定義 frontend/src/types/structured.ts
- [ ] T028 [US1] 處理查無資料與錯誤狀態顯示

**Checkpoint**: User Story 1 應可獨立運作與測試

---

## Phase 4: User Story 2 - AI 意圖識別與路由 (Priority: P1)

**Goal**: 系統自動判斷使用者查詢屬於知識庫查詢、結構化資料查詢或混合型查詢

**Independent Test**: 輸入不同類型問句，驗證正確路由至對應處理引擎

### Implementation for User Story 2

- [ ] T029 [US2] 建立意圖識別服務 backend/app/services/intent_classifier.py
- [ ] T030 [US2] 實作 Few-shot Prompt 模板於 intent_classifier.py
- [ ] T031 [US2] 建立混合查詢處理邏輯（同時查詢知識庫與結構化資料）
- [ ] T032 [US2] 更新 /query API 整合意圖識別 backend/app/routers/query.py
- [ ] T033 [US2] 建立澄清請求回應機制（無法判斷意圖時）
- [ ] T034 [US2] 前端顯示混合查詢結果（知識 + 資料卡片）frontend/src/components/chat/MessageList.tsx

**Checkpoint**: User Story 1 與 2 應皆可獨立運作

---

## Phase 5: User Story 3 - 資料瀏覽與篩選 (Priority: P2)

**Goal**: 使用者可透過側邊面板瀏覽結構化資料、套用篩選條件、匯出報表

**Independent Test**: 開啟側邊面板、套用篩選、驗證結果、匯出 CSV

### Implementation for User Story 3

- [ ] T035 [P] [US3] 建立車輛清單 API backend/app/routers/structured.py (GET /structured/vehicles)
- [ ] T036 [P] [US3] 建立庫存查詢 API backend/app/routers/structured.py (GET /structured/inventory)
- [ ] T037 [P] [US3] 建立檢修歷程 API backend/app/routers/structured.py (GET /structured/vehicles/{code}/maintenance)
- [ ] T038 [P] [US3] 建立成本查詢 API backend/app/routers/structured.py (GET /structured/vehicles/{code}/costs)
- [ ] T039 [US3] 建立資料匯出服務 backend/app/services/export_service.py
- [ ] T040 [US3] 建立匯出 API backend/app/routers/export.py (POST /export)
- [ ] T041 [P] [US3] 建立前端 FilterPanel 元件 frontend/src/components/structured/FilterPanel.tsx
- [ ] T042 [P] [US3] 建立前端 ExportButton 元件 frontend/src/components/structured/ExportButton.tsx
- [ ] T043 [US3] 建立側邊資料面板 frontend/src/components/structured/DataBrowserPanel.tsx
- [ ] T044 [US3] 整合側邊面板至主畫面佈局 frontend/src/app/layout.tsx
- [ ] T045 [US3] 實作分頁載入（超過 100 筆時）

**Checkpoint**: User Story 1、2、3 應皆可獨立運作

---

## Phase 6: User Story 4 - 關鍵指標儀表板 (Priority: P3)

**Goal**: 管理者可查看故障趨勢、維修成本分布、庫存警示等統計圖表

**Independent Test**: 載入儀表板頁面，驗證圖表正確顯示

### Implementation for User Story 4

- [ ] T046 [P] [US4] 建立儀表板摘要 API backend/app/routers/dashboard.py (GET /dashboard/summary)
- [ ] T047 [P] [US4] 建立故障趨勢 API backend/app/routers/dashboard.py (GET /dashboard/fault-trends)
- [ ] T048 [P] [US4] 建立成本分布 API backend/app/routers/dashboard.py (GET /dashboard/cost-distribution)
- [ ] T049 [US4] 建立儀表板統計服務 backend/app/services/dashboard_service.py
- [ ] T050 [P] [US4] 建立前端 StatCard 元件 frontend/src/components/dashboard/StatCard.tsx
- [ ] T051 [P] [US4] 建立前端 TrendChart 元件 frontend/src/components/dashboard/TrendChart.tsx
- [ ] T052 [P] [US4] 建立前端 InventoryAlert 元件 frontend/src/components/dashboard/InventoryAlert.tsx
- [ ] T053 [P] [US4] 建立前端 CostDistributionChart 元件 frontend/src/components/dashboard/CostDistributionChart.tsx
- [ ] T054 [US4] 建立儀表板頁面 frontend/src/app/dashboard/page.tsx
- [ ] T055 [US4] 建立 useDashboard Hook frontend/src/hooks/useDashboard.ts
- [ ] T056 [US4] 實作圖表鑽取功能（點擊數據點顯示詳情）
- [ ] T057 [US4] 加入儀表板快取（Redis TTL 15 分鐘）backend/app/services/dashboard_service.py

**Checkpoint**: 所有 User Story 應皆可獨立運作

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: 跨功能改善與優化

- [ ] T058 [P] 新增資料庫索引優化 backend/alembic/versions/002_add_indexes.py
- [ ] T059 [P] 加入 Redis 查詢快取（TTL 5 分鐘）backend/app/services/structured_query.py
- [ ] T060 更新主應用程式載入新路由 backend/app/main.py
- [ ] T061 權限控制整合（根據使用者角色限制資料存取）
- [ ] T062 效能日誌記錄（符合 Constitution II）
- [ ] T063 驗證 quickstart.md 流程可正確執行

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 無依賴 - 可立即開始
- **Foundational (Phase 2)**: 依賴 Phase 1 完成 - 阻塞所有 User Story
- **User Stories (Phase 3-6)**: 皆依賴 Phase 2 完成
  - US1 與 US2 可平行進行（但 US2 部分功能依賴 US1）
  - US3 可獨立進行
  - US4 可獨立進行
- **Polish (Phase 7)**: 依賴所有目標 User Story 完成

### User Story Dependencies

```
Phase 1 (Setup)
    ↓
Phase 2 (Foundational) ─── BLOCKS ALL ───
    ↓                                    ↓
Phase 3 (US1) ←──────────────────→ Phase 4 (US2)
    ↓                                    ↓
    └──────────→ Phase 5 (US3) ←─────────┘
                      ↓
                Phase 6 (US4)
                      ↓
                Phase 7 (Polish)
```

### Within Each User Story

1. 後端模型/服務 → 後端 API
2. 前端元件 → 前端整合
3. 核心功能 → 錯誤處理

### Parallel Opportunities

**Phase 2 (Foundational)**: T007-T013 可全部平行（7 個模型檔案）

**Phase 3 (US1)**: T023-T024 可平行（不同前端元件）

**Phase 5 (US3)**: T035-T038 可平行（不同 API 端點）；T041-T042 可平行（不同前端元件）

**Phase 6 (US4)**: T046-T048 可平行（不同 API）；T050-T053 可平行（不同圖表元件）

---

## Parallel Example: Phase 2 (Foundational)

```bash
# 同時建立所有資料模型（7 個平行任務）：
Task: "建立 Vehicle 模型 backend/app/models/structured/vehicle.py"
Task: "建立 FaultRecord 模型 backend/app/models/structured/fault_record.py"
Task: "建立 MaintenanceRecord 模型 backend/app/models/structured/maintenance.py"
Task: "建立 UsageRecord 模型 backend/app/models/structured/usage.py"
Task: "建立 PartsUsed 模型 backend/app/models/structured/parts.py"
Task: "建立 CostRecord 模型 backend/app/models/structured/cost.py"
Task: "建立 PartsInventory 模型 backend/app/models/structured/parts.py"
```

## Parallel Example: User Story 4 (US4)

```bash
# 同時建立所有儀表板圖表元件（4 個平行任務）：
Task: "建立前端 StatCard 元件 frontend/src/components/dashboard/StatCard.tsx"
Task: "建立前端 TrendChart 元件 frontend/src/components/dashboard/TrendChart.tsx"
Task: "建立前端 InventoryAlert 元件 frontend/src/components/dashboard/InventoryAlert.tsx"
Task: "建立前端 CostDistributionChart 元件 frontend/src/components/dashboard/CostDistributionChart.tsx"
```

---

## Implementation Strategy

### MVP First (僅 User Story 1)

1. 完成 Phase 1: Setup
2. 完成 Phase 2: Foundational（**關鍵 - 阻塞所有後續工作**）
3. 完成 Phase 3: User Story 1
4. **STOP and VALIDATE**: 獨立測試 User Story 1
5. 可部署/展示 MVP

### Incremental Delivery

1. Setup + Foundational → 基礎架構就緒
2. 加入 User Story 1 → 獨立測試 → 部署（MVP!）
3. 加入 User Story 2 → 獨立測試 → 部署
4. 加入 User Story 3 → 獨立測試 → 部署
5. 加入 User Story 4 → 獨立測試 → 部署
6. 每個 Story 獨立增加價值，不破壞前面功能

### Parallel Team Strategy

多人協作時：
1. 團隊共同完成 Setup + Foundational
2. Foundational 完成後：
   - 開發者 A: User Story 1 + 2
   - 開發者 B: User Story 3
   - 開發者 C: User Story 4
3. 各 Story 獨立完成後整合

---

## Summary

| 階段 | 任務數 | 可平行任務 |
|------|--------|-----------|
| Phase 1: Setup | 6 | 2 |
| Phase 2: Foundational | 11 | 7 |
| Phase 3: US1 (P1 MVP) | 11 | 2 |
| Phase 4: US2 (P1) | 6 | 0 |
| Phase 5: US3 (P2) | 11 | 6 |
| Phase 6: US4 (P3) | 12 | 7 |
| Phase 7: Polish | 6 | 2 |
| **Total** | **63** | **26** |

**MVP 建議**: Phase 1-3（共 28 個任務）可作為最小可行產品
**完整功能**: 全部 63 個任務

---

## Notes

- [P] 任務 = 不同檔案、無依賴，可平行執行
- [Story] 標籤 = 對應 spec.md 中的 User Story，便於追蹤
- 每個 User Story 應可獨立完成與測試
- 每個任務或邏輯群組完成後 commit
- 任何 checkpoint 皆可暫停驗證
- 避免：模糊任務、同檔衝突、跨 Story 依賴破壞獨立性
