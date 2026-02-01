# Implementation Plan: RAG 系統優化

**Branch**: `001-rag-optimization` | **Date**: 2026-01-31 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-rag-optimization/spec.md`

## Summary

本次優化涵蓋四大功能：(1) Cohere Reranker 整合以提升專業術語搜尋準確度，(2) Qdrant 持久化模式確保資料重啟後保留，(3) Redis 快取熱門查詢加速回應，(4) WebSocket 即時推送文件處理進度。這些優化將顯著改善系統效能與使用者體驗。

## Technical Context

**Language/Version**: Python 3.10+ (Backend), TypeScript strict mode (Frontend)
**Primary Dependencies**: FastAPI, Qdrant, Redis, Cohere SDK, Next.js
**Storage**: Qdrant (persistent mode), Redis (cache)
**Testing**: pytest (backend), Jest (frontend)
**Target Platform**: Linux server (Docker), macOS (development)
**Project Type**: Web application (backend + frontend)
**Performance Goals**:
  - RAG 搜尋 < 2 秒 (p95)
  - 快取命中 < 100ms (p95)
  - WebSocket 更新間隔 < 2 秒
**Constraints**:
  - API 回應 < 200ms (p95)
  - Reranker fallback 必須無縫
**Scale/Scope**: 數千份文件、百位使用者

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|-----------|------|--------|
| I. 程式碼品質 | Python 3.10+, PEP 8, Type hints | ✅ Pass |
| II. 效能優先 | RAG < 2s, Vector < 500ms, API < 200ms | ✅ Pass (設計符合) |
| III. 可維護性 | 模組化設計, 服務層分離 | ✅ Pass |
| IV. 中文優先 | 繁體中文術語庫 | ✅ Pass (已有 terminology.py) |
| V. 安全性 | API 認證, 環境變數 | ✅ Pass |

## Project Structure

### Documentation (this feature)

```text
specs/001-rag-optimization/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── backup-api.yaml
│   ├── cache-api.yaml
│   └── websocket-api.yaml
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── main.py              # FastAPI 應用程式（新增 WebSocket 路由）
│   ├── config.py            # 設定（新增 Redis, Cohere 設定）
│   ├── models/
│   │   └── schemas.py       # 新增 BackupRecord, ProcessingTask schemas
│   ├── routers/
│   │   ├── kb.py            # 修改：新增備份/恢復端點
│   │   ├── chat.py          # 修改：整合快取
│   │   └── upload_ws.py     # 新增：WebSocket 上傳進度
│   └── services/
│       ├── vector_store.py  # 修改：persistent mode
│       ├── rag.py           # 修改：整合 reranker
│       ├── reranker.py      # 新增：Cohere Rerank 服務
│       ├── cache.py         # 新增：Redis 快取服務
│       └── task_manager.py  # 新增：處理任務管理
└── tests/
    ├── integration/
    │   ├── test_reranker.py
    │   ├── test_cache.py
    │   └── test_backup.py
    └── unit/
        ├── test_reranker_service.py
        └── test_cache_service.py

frontend/
└── src/
    ├── app/
    │   └── upload/
    │       └── page.tsx     # 新增：上傳進度頁面
    ├── components/
    │   └── UploadProgress.tsx  # 新增：進度元件
    └── hooks/
        └── useUploadProgress.ts  # 新增：WebSocket hook
```

**Structure Decision**: 使用現有 Web application 架構，新增服務模組於 `backend/app/services/`，前端新增 WebSocket 相關元件。

## Complexity Tracking

> 無 Constitution 違規，無需額外追蹤。
