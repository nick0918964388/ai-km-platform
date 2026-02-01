# Implementation Plan: 文件預覽功能 (Document Preview)

**Branch**: `002-document-preview` | **Date**: 2026-02-01 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-document-preview/spec.md`

## Summary

實作文件預覽功能，讓使用者在 RAG 查詢結果中能直接預覽或下載原始文件。主要變更包括：

1. **後端**：上傳時保存原檔到 `./storage/documents/{document_id}/`，新增文件下載 API 端點
2. **資料模型**：SearchResult 加入 `file_url` 欄位
3. **前端**：查詢結果顯示「預覽原檔」按鈕，PDF 瀏覽器內預覽、其他格式觸發下載

## Technical Context

**Language/Version**: Python 3.10+ (Backend), TypeScript strict mode (Frontend)
**Primary Dependencies**: FastAPI, Qdrant, Redis, Cohere SDK (Backend) / Next.js 14, React 18, IBM Carbon (Frontend)
**Storage**: 本地檔案系統 `./storage/documents/`，Qdrant 向量資料庫
**Testing**: pytest (Backend), Jest (Frontend)
**Target Platform**: Web application (Linux/macOS server + modern browsers)
**Project Type**: Web application (frontend + backend)
**Performance Goals**: 文件預覽 API < 5 秒 (50MB 以下)，端到端點擊到預覽 < 3 秒
**Constraints**: 沿用現有 50MB 上傳限制，PDF 使用 inline 模式、其他格式使用 attachment 模式
**Scale/Scope**: 支援 PDF、Word (.docx)、PNG、JPG、JPEG 格式

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. 程式碼品質 | ✅ PASS | Python 3.10+ with type hints, TypeScript strict mode |
| II. 效能優先 | ✅ PASS | 文件預覽 API < 5s 符合 API 回應 < 200ms (小檔案)，大檔案使用 streaming |
| III. 可維護性 | ✅ PASS | 新增獨立 file_storage 服務模組，與現有模組分離 |
| IV. 中文優先 | ✅ PASS | 按鈕文字「預覽原檔」、錯誤訊息使用繁體中文 |
| V. 安全性 | ✅ PASS | 透過 document_id 驗證存取，沿用現有認證機制 |

## Project Structure

### Documentation (this feature)

```text
specs/002-document-preview/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── openapi.yaml     # API contract
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── config.py                    # 新增 storage_dir 設定
│   ├── models/
│   │   └── schemas.py               # SearchResult 新增 file_url
│   ├── routers/
│   │   └── kb.py                    # 新增 GET /api/documents/{id}/file
│   └── services/
│       ├── document_processor.py    # 修改：上傳時保存原檔
│       ├── file_storage.py          # 新增：檔案儲存服務
│       └── rag.py                   # 修改：回傳 file_url
└── storage/
    └── documents/                   # 原檔儲存目錄
        └── {document_id}/
            └── {original_filename}

frontend/
└── src/
    ├── components/
    │   └── chat/
    │       ├── ChatWindow.tsx       # 修改：顯示預覽按鈕
    │       └── SourcePreview.tsx    # 新增：預覽按鈕元件
    └── types/
        └── index.ts                 # SearchResult 新增 file_url
```

**Structure Decision**: 沿用現有 Web application 架構 (backend/ + frontend/)，新增 `file_storage` 服務模組處理檔案儲存邏輯。

## Complexity Tracking

> **No violations - table intentionally empty**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | N/A | N/A |
