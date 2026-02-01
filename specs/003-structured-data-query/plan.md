# Implementation Plan: 結構化資料查詢

**Branch**: `003-structured-data-query` | **Date**: 2026-02-01 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-structured-data-query/spec.md`

## Summary

為 AIKM 車輛維修知識管理平台新增結構化資料查詢能力。透過 AI 意圖識別，自動判斷使用者查詢屬於知識庫或結構化資料，並將自然語言轉換為 SQL 查詢。新增 PostgreSQL 資料庫存儲車輛維修相關結構化資料（7 個資料表），並整合至現有對話介面。

## Technical Context

**Language/Version**: Python 3.10+ (Backend), TypeScript strict mode (Frontend)
**Primary Dependencies**:
- Backend: FastAPI, SQLAlchemy (新增), asyncpg (新增), OpenAI API
- Frontend: Next.js 16, React 19, IBM Carbon Design, Zustand
**Storage**: PostgreSQL (新增，結構化資料), Qdrant (現有，向量儲存)
**Testing**: pytest (Backend), Jest/Vitest (Frontend)
**Target Platform**: Linux server (Docker), Web browser
**Project Type**: Web application (frontend + backend)
**Performance Goals**:
- SQL 查詢回應 < 500ms (p95)
- 意圖識別 < 200ms
- 整體端到端回應 < 2 秒 (符合 Constitution)
**Constraints**:
- 繁體中文優先
- 與現有對話介面整合
- 權限控制整合
**Scale/Scope**:
- 7 個資料表
- 預估 10 萬筆以上歷史紀錄
- 支援 50+ 並發使用者

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. 程式碼品質 | ✅ PASS | Python 3.10+, TypeScript strict mode, 完整型別標註 |
| II. 效能優先 | ✅ PASS | RAG < 2s, SQL 查詢 < 500ms, API < 200ms |
| III. 可維護性 | ✅ PASS | 模組化設計，服務層分離，依賴注入 |
| IV. 中文優先 | ✅ PASS | 繁體中文介面，中文自然語言查詢支援 |
| V. 安全性 | ✅ PASS | SQL 參數化查詢防注入，權限控制，輸入驗證 |

## Project Structure

### Documentation (this feature)

```text
specs/003-structured-data-query/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── api.yaml         # OpenAPI specification
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── models/
│   │   ├── __init__.py
│   │   ├── structured/           # 新增：結構化資料模型
│   │   │   ├── __init__.py
│   │   │   ├── vehicle.py        # 車輛基本資料
│   │   │   ├── fault_record.py   # 故障歷程
│   │   │   ├── maintenance.py    # 檢修歷程
│   │   │   ├── usage.py          # 使用歷程
│   │   │   ├── parts.py          # 用料與庫存
│   │   │   └── cost.py           # 成本紀錄
│   │   └── existing...
│   ├── services/
│   │   ├── intent_classifier.py  # 新增：意圖識別服務
│   │   ├── nl2sql_service.py     # 新增：自然語言轉 SQL
│   │   ├── structured_query.py   # 新增：結構化查詢服務
│   │   └── existing...
│   ├── routers/
│   │   ├── structured.py         # 新增：結構化資料 API
│   │   ├── dashboard.py          # 新增：儀表板 API
│   │   └── existing...
│   └── db/                       # 新增：資料庫連線
│       ├── __init__.py
│       ├── session.py
│       └── migrations/
└── tests/
    ├── unit/
    │   ├── test_intent_classifier.py
    │   └── test_nl2sql.py
    └── integration/
        └── test_structured_api.py

frontend/
├── src/
│   ├── components/
│   │   ├── structured/           # 新增：結構化資料元件
│   │   │   ├── DataCard.tsx      # 資料卡片（嵌入對話）
│   │   │   ├── DataTable.tsx     # 資料表格
│   │   │   ├── FilterPanel.tsx   # 篩選面板
│   │   │   └── ExportButton.tsx  # 匯出按鈕
│   │   ├── dashboard/            # 新增：儀表板元件
│   │   │   ├── StatCard.tsx
│   │   │   ├── TrendChart.tsx
│   │   │   └── InventoryAlert.tsx
│   │   └── existing...
│   ├── app/
│   │   ├── dashboard/            # 新增：儀表板頁面
│   │   │   └── page.tsx
│   │   └── existing...
│   └── hooks/
│       ├── useStructuredQuery.ts # 新增：查詢 Hook
│       └── existing...
└── tests/
    └── components/
        └── structured/
```

**Structure Decision**: 採用現有的 Web application 結構（backend/ + frontend/），在各自目錄下新增結構化資料相關模組，保持與現有架構一致。

## Complexity Tracking

> **無違反項目，不需額外說明**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | - | - |
