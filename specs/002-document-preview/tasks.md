# Tasks: 文件預覽功能 (Document Preview)

**Input**: Design documents from `/specs/002-document-preview/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/openapi.yaml

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Backend**: `backend/app/`
- **Frontend**: `frontend/src/`
- **Storage**: `backend/storage/documents/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 建立儲存目錄與基礎設定

- [x] T001 建立儲存目錄 `backend/storage/documents/`
- [x] T002 [P] 在 `backend/app/config.py` 新增 `storage_dir` 設定項

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 核心服務模組，所有 User Story 都依賴此階段

**⚠️ CRITICAL**: 此階段完成前，無法開始任何 User Story

- [x] T003 建立檔案儲存服務 `backend/app/services/file_storage.py`
  - 實作 `save_file(document_id: str, filename: str, content: bytes) -> str`
  - 實作 `get_file_path(document_id: str) -> Optional[Path]`
  - 實作 `get_file_info(document_id: str) -> Optional[dict]` (filename, content_type)
  - 實作 `file_exists(document_id: str) -> bool`
- [x] T004 在 `backend/app/models/schemas.py` 的 SearchResult 新增 `file_url: Optional[str]` 欄位
- [x] T005 [P] 在 `frontend/src/types/index.ts` 新增 SearchResult 的 `file_url` 欄位

**Checkpoint**: 基礎設施就緒 - 可開始 User Story 實作 ✅

---

## Phase 3: User Story 2 - 上傳時保存原始檔案 (Priority: P1) 🎯 MVP

**Goal**: 上傳文件時，除了向量化處理外，同時保存原始檔案到 storage 目錄

**Independent Test**: 上傳一份 PDF，檢查 `storage/documents/{document_id}/` 目錄下有原始檔案

> 注意：雖然 spec 中 US2 排在 US1 後面，但邏輯上需先實作「保存原檔」才能「預覽原檔」

### Implementation for User Story 2

- [x] T006 [US2] 修改 `backend/app/services/document_processor.py` 的處理函數
  - 在 `process_pdf()` 中呼叫 `file_storage.save_file()` 保存原檔
  - 在 `process_word()` 中呼叫 `file_storage.save_file()` 保存原檔
  - 在 `process_image()` 中呼叫 `file_storage.save_file()` 保存原檔
- [x] T007 [US2] 修改 `backend/app/routers/kb.py` 的 `upload_document()` 端點
  - 確保 document_id 在儲存原檔前已生成
  - 傳遞 content bytes 給 document_processor

**Checkpoint**: 上傳文件後，原始檔案會保存到 storage 目錄 ✅

---

## Phase 4: User Story 3 - 直接存取原始文件 API (Priority: P2)

**Goal**: 提供 API 端點讓前端或外部系統能取得原始檔案

**Independent Test**: 呼叫 `GET /api/documents/{document_id}/file` 並驗證回傳正確的檔案內容和 MIME type

### Implementation for User Story 3

- [x] T008 [US3] 在 `backend/app/routers/kb.py` 新增 `GET /api/kb/documents/{document_id}/file` 端點
  - 使用 `file_storage.get_file_path()` 取得檔案路徑
  - 使用 `file_storage.get_file_info()` 取得 filename 和 content_type
  - PDF 格式：回傳 `FileResponse` 搭配 `Content-Disposition: inline`
  - Word/圖片格式：回傳 `FileResponse` 搭配 `Content-Disposition: attachment`
  - 檔案不存在：回傳 404 錯誤（中文訊息）

**Checkpoint**: 可透過 API 直接下載或預覽原始文件 ✅

---

## Phase 5: User Story 1 - 查詢結果預覽原始文件 (Priority: P1)

**Goal**: 使用者在查詢結果中可點擊「預覽原檔」按鈕，開啟或下載原始文件

**Independent Test**: 執行查詢，點擊結果中的「預覽原檔」按鈕，PDF 在新分頁開啟，Word/圖片觸發下載

### Implementation for User Story 1 - Backend

- [x] T009 [US1] 修改 `backend/app/services/rag.py` 的搜尋結果處理
  - 在建構 SearchResult 時，加入 `file_url` 欄位
  - 格式：`/api/kb/documents/{document_id}/file`
  - 使用 `file_storage.file_exists()` 檢查原檔是否存在
  - 若原檔不存在，`file_url` 設為 `None`

### Implementation for User Story 1 - Frontend

- [x] T010 [P] [US1] 建立預覽按鈕元件 `frontend/src/components/chat/SourcePreview.tsx`
  - Props: `fileUrl: string | null`, `documentName: string`
  - 若 `fileUrl` 為 null，不顯示按鈕
  - 按鈕文字：「預覽原檔」
  - 點擊行為：`window.open(fileUrl, '_blank')`
  - 使用 IBM Carbon Button 元件
- [x] T011 [US1] 修改 `frontend/src/components/chat/ChatWindow.tsx`
  - 在來源引用區域整合 SourcePreview 元件
  - 傳遞 `source.file_url` 和 `source.document_name`

**Checkpoint**: 完整的端對端文件預覽功能可運作 ✅

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 優化與邊界情況處理

- [x] T012 [P] 處理邊界情況：原始檔案遺失時的錯誤處理
  - 後端：404 回應包含中文訊息「找不到原始檔案」
  - 前端：SourcePreview 元件處理按鈕點擊後的錯誤情況（透過 file_url 為 null 時隱藏按鈕）
- [x] T013 [P] 確認 CORS 設定允許 FileResponse 的跨域存取（已在 main.py 設定 allow_origins=["*"]）
- [x] T014 驗證 quickstart.md 中的測試流程（手動驗證）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 無依賴 - 可立即開始 ✅
- **Foundational (Phase 2)**: 依賴 Setup 完成 - 阻擋所有 User Stories ✅
- **User Story 2 (Phase 3)**: 依賴 Foundational 完成 - 實作「保存原檔」 ✅
- **User Story 3 (Phase 4)**: 依賴 US2 完成 - 實作「下載 API」 ✅
- **User Story 1 (Phase 5)**: 依賴 US3 完成 - 實作「前端預覽按鈕」 ✅
- **Polish (Phase 6)**: 依賴所有 User Stories 完成 ✅

### User Story Dependencies

```
Foundational ✅
     │
     ▼
User Story 2 (保存原檔) ✅
     │
     ▼
User Story 3 (下載 API) ✅
     │
     ▼
User Story 1 (前端預覽) ✅
     │
     ▼
   Polish ✅
```

> 注意：此功能的 User Stories 有嚴格的順序依賴關係，無法平行開發

---

## Implementation Summary

**所有任務已完成！** ✅

| Phase | Tasks | Status |
|-------|-------|--------|
| Phase 1: Setup | T001, T002 | ✅ Complete |
| Phase 2: Foundational | T003, T004, T005 | ✅ Complete |
| Phase 3: US2 (保存原檔) | T006, T007 | ✅ Complete |
| Phase 4: US3 (下載 API) | T008 | ✅ Complete |
| Phase 5: US1 (前端預覽) | T009, T010, T011 | ✅ Complete |
| Phase 6: Polish | T012, T013, T014 | ✅ Complete |

**Total**: 14/14 tasks completed
