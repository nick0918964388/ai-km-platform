# Research: 文件預覽功能 (Document Preview)

**Date**: 2026-02-01
**Feature Branch**: `002-document-preview`

## Research Topics

### 1. FastAPI 檔案下載最佳實踐

**Decision**: 使用 `FileResponse` 搭配適當的 `Content-Disposition` 標頭

**Rationale**:
- FastAPI 內建 `FileResponse` 支援高效的檔案串流傳輸
- 對於 PDF 使用 `Content-Disposition: inline` 實現瀏覽器內嵌預覽
- 對於 Word/圖片使用 `Content-Disposition: attachment` 觸發下載
- 支援正確的 `Content-Type` 設定 (MIME type)

**Alternatives Considered**:
- `StreamingResponse`: 適合大檔案但增加程式碼複雜度，50MB 以內使用 FileResponse 足夠
- Base64 編碼回傳: 增加 33% 資料量，不適合大檔案

### 2. 檔案儲存目錄結構

**Decision**: `./storage/documents/{document_id}/{original_filename}`

**Rationale**:
- 使用 document_id 作為目錄名稱，確保唯一性
- 保留原始檔名方便使用者識別
- 與現有 `./uploads/` 目錄分離，明確區分暫存與持久儲存
- 結構簡單，易於備份與遷移

**Alternatives Considered**:
- Flat structure `./storage/{document_id}-{filename}`: 檔名衝突風險
- Hash-based naming: 失去原始檔名資訊

### 3. MIME Type 對應

**Decision**: 使用 Python `mimetypes` 模組搭配預設對應表

**Rationale**:
- 標準函式庫，無需額外依賴
- 涵蓋常見檔案格式
- 可自定義擴充

**MIME Type 對應表**:

| 副檔名 | MIME Type | Content-Disposition |
|--------|-----------|---------------------|
| .pdf | application/pdf | inline |
| .docx | application/vnd.openxmlformats-officedocument.wordprocessingml.document | attachment |
| .png | image/png | attachment |
| .jpg/.jpeg | image/jpeg | attachment |

### 4. 前端預覽實作方式

**Decision**: 使用 `window.open()` 在新分頁開啟檔案 URL

**Rationale**:
- PDF 可直接在瀏覽器內嵌顯示（現代瀏覽器原生支援）
- 其他格式由瀏覽器處理下載行為
- 實作簡單，無需額外函式庫

**Alternatives Considered**:
- PDF.js 嵌入式預覽: 增加 bundle 大小，現階段不需要
- iframe 嵌入: CORS 限制可能造成問題

### 5. 錯誤處理策略

**Decision**: 前端優雅降級，後端明確錯誤碼

**Rationale**:
- 原始檔案遺失時回傳 404 錯誤
- 前端收到錯誤時顯示中文提示訊息
- 不影響查詢結果的正常顯示

**錯誤情境處理**:

| 情境 | HTTP Status | 前端處理 |
|------|-------------|----------|
| 檔案不存在 | 404 | 顯示「原始檔案不可用」 |
| 檔案讀取失敗 | 500 | 顯示「載入失敗，請稍後再試」 |
| document_id 無效 | 404 | 隱藏預覽按鈕 |

## Technical Decisions Summary

1. **檔案傳輸**: FastAPI FileResponse + Content-Disposition
2. **儲存結構**: `./storage/documents/{document_id}/{filename}`
3. **MIME 處理**: Python mimetypes 模組
4. **前端開啟**: window.open() 新分頁
5. **錯誤處理**: HTTP 404/500 + 中文訊息
