# Feature Specification: 文件預覽功能 (Document Preview)

**Feature Branch**: `002-document-preview`
**Created**: 2026-02-01
**Status**: Draft
**Input**: 文件預覽功能：1) 上傳文件時保存原檔案到 ./storage/documents/{document_id}/ 目錄 2) SearchResult 加入 file_url 欄位 3) 新增 GET /api/documents/{document_id}/file 端點返回原檔案 4) 支援 PDF 在瀏覽器直接預覽、Word/圖片下載 5) 前端查詢結果顯示「預覽原檔」按鈕

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 查詢結果預覽原始文件 (Priority: P1)

當使用者透過 RAG 系統查詢知識庫，並從查詢結果中找到相關資訊時，使用者希望能直接查看該資訊的原始文件來源，以便驗證資訊的正確性或獲取更完整的上下文。

**Why this priority**: 這是文件預覽功能的核心價值 - 讓使用者能從查詢結果直接連結到原始文件，確保資訊可追溯性和可信度。

**Independent Test**: 可透過執行一次查詢，點擊結果中的「預覽原檔」按鈕，驗證能正確開啟或下載對應的原始文件。

**Acceptance Scenarios**:

1. **Given** 使用者在聊天介面輸入查詢問題，**When** 系統返回帶有來源引用的答案，**Then** 每個來源旁邊顯示「預覽原檔」按鈕
2. **Given** 來源文件為 PDF 格式，**When** 使用者點擊「預覽原檔」按鈕，**Then** PDF 在瀏覽器新分頁中直接開啟預覽
3. **Given** 來源文件為 Word 格式（.docx），**When** 使用者點擊「預覽原檔」按鈕，**Then** 瀏覽器觸發檔案下載
4. **Given** 來源文件為圖片格式（PNG/JPG），**When** 使用者點擊「預覽原檔」按鈕，**Then** 瀏覽器觸發圖片下載

---

### User Story 2 - 上傳時保存原始檔案 (Priority: P1)

當管理員上傳文件到知識庫時，系統除了處理文件內容進行向量化外，還需保存原始檔案副本，以便日後提供預覽功能。

**Why this priority**: 這是實現文件預覽的基礎必要條件 - 沒有原始檔案儲存，就無法提供預覽功能。

**Independent Test**: 可透過上傳一份文件，然後檢查儲存目錄確認原始檔案已正確保存。

**Acceptance Scenarios**:

1. **Given** 管理員選擇 PDF/Word/圖片檔案準備上傳，**When** 上傳處理完成，**Then** 原始檔案保存在 `./storage/documents/{document_id}/` 目錄下
2. **Given** 同一份文件重複上傳（相同檔名），**When** 上傳處理完成，**Then** 系統應建立新的 document_id 並分別儲存

---

### User Story 3 - 直接存取原始文件 (Priority: P2)

系統提供 API 端點讓前端或外部系統能夠直接存取特定文件的原始檔案。

**Why this priority**: 這是實現前端預覽功能的必要 API 介面。

**Independent Test**: 可透過直接呼叫 API 端點並驗證回傳正確的檔案內容和 MIME type。

**Acceptance Scenarios**:

1. **Given** 存在已上傳的文件 document_id，**When** 呼叫 GET /api/documents/{document_id}/file，**Then** 回傳該文件的原始檔案內容
2. **Given** 文件為 PDF 格式，**When** 呼叫 API 取得檔案，**Then** 回應 Content-Type 為 `application/pdf`，並設定 `Content-Disposition: inline` 以便瀏覽器內嵌顯示
3. **Given** 文件為 Word 格式，**When** 呼叫 API 取得檔案，**Then** 回應設定 `Content-Disposition: attachment` 以觸發下載
4. **Given** 不存在的 document_id，**When** 呼叫 API，**Then** 回傳 404 錯誤

---

### Edge Cases

- 如果原始檔案在儲存後被意外刪除，系統如何處理？（顯示「原始檔案不可用」訊息）
- 如果檔案大小超過限制（如 100MB），預覽行為為何？（改為下載而非在線預覽）
- 如果查詢結果來自圖片內容（CLIP 向量），是否顯示預覽按鈕？（是，提供圖片下載）
- 如果同一 chunk 來自多頁 PDF，預覽是否跳轉到特定頁面？（僅開啟 PDF 首頁，不跳轉特定頁）

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系統必須在文件上傳成功後，將原始檔案保存到 `./storage/documents/{document_id}/` 目錄
- **FR-002**: 系統必須保持原始檔案的檔名不變（含副檔名）
- **FR-003**: 系統必須在 SearchResult 回應中加入 `file_url` 欄位，指向原始文件 API 端點
- **FR-004**: 系統必須提供 GET /api/documents/{document_id}/file 端點以取得原始檔案
- **FR-005**: 系統必須根據檔案類型設定正確的 Content-Type 回應標頭
- **FR-006**: 系統必須對 PDF 檔案設定 inline 顯示模式（瀏覽器內預覽）
- **FR-007**: 系統必須對 Word 和圖片檔案設定 attachment 下載模式
- **FR-008**: 前端必須在查詢結果的來源引用旁顯示「預覽原檔」按鈕
- **FR-009**: 系統必須在原始檔案不存在時回傳 404 錯誤
- **FR-010**: 系統必須支援 PDF、Word (.docx)、PNG、JPG、JPEG 格式的檔案預覽/下載

### Key Entities

- **Document**: 知識庫文件，包含 document_id、filename、file_path（原始檔案路徑）、file_size、doc_type、uploaded_at
- **SearchResult**: 搜尋結果，新增 file_url 欄位指向文件下載端點
- **StoredFile**: 儲存的原始檔案，位於 storage/documents/{document_id}/ 目錄下

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% 的新上傳文件在處理完成後，原始檔案可在儲存目錄中找到
- **SC-002**: 使用者可在 3 秒內從查詢結果點擊預覽按鈕並看到檔案內容或開始下載
- **SC-003**: PDF 檔案在主流瀏覽器（Chrome、Firefox、Safari、Edge）中可直接內嵌預覽
- **SC-004**: 文件預覽 API 對於 50MB 以下檔案的回應時間不超過 5 秒
- **SC-005**: 100% 的查詢結果來源（有對應原始檔案者）都顯示「預覽原檔」按鈕

## Assumptions

- 假設使用者已通過驗證，無需額外的文件存取權限控制（沿用現有系統驗證機制）
- 假設儲存空間足夠，不需實作檔案大小配額管理
- 假設現有的 50MB 上傳限制繼續適用於此功能
- 假設不需要支援文件版本控制（同一 document_id 對應唯一一份原始檔案）
