# Quickstart: 文件預覽功能 (Document Preview)

**Date**: 2026-02-01
**Feature Branch**: `002-document-preview`

## Prerequisites

- Python 3.10+
- Node.js 18+
- Docker (for Qdrant & Redis)
- 現有 AIKM 平台環境已設定完成

## Setup

### 1. 建立儲存目錄

```bash
mkdir -p storage/documents
```

### 2. 更新環境變數（可選）

如需自訂儲存路徑，在 `.env` 中設定：

```env
STORAGE_DIR=./storage/documents
```

### 3. 啟動服務

```bash
# 啟動 Docker 服務
docker-compose up -d

# 啟動後端
cd backend
uvicorn app.main:app --reload --port 8000

# 啟動前端（另一終端）
cd frontend
npm run dev
```

## Testing the Feature

### 1. 上傳測試文件

```bash
# 上傳 PDF
curl -X POST "http://localhost:8000/api/kb/upload" \
  -F "file=@test.pdf"

# 回應範例：
# {
#   "success": true,
#   "document_id": "550e8400-e29b-41d4-a716-446655440000",
#   "filename": "test.pdf",
#   "doc_type": "pdf",
#   "chunk_count": 15,
#   "message": "成功上傳並處理..."
# }
```

### 2. 驗證檔案已儲存

```bash
ls -la storage/documents/550e8400-e29b-41d4-a716-446655440000/
# 應顯示 test.pdf
```

### 3. 測試預覽 API

```bash
# PDF 預覽（瀏覽器會內嵌顯示）
curl -I "http://localhost:8000/api/documents/550e8400-e29b-41d4-a716-446655440000/file"

# 應回傳：
# Content-Type: application/pdf
# Content-Disposition: inline; filename="test.pdf"
```

### 4. 測試查詢結果

```bash
curl -X POST "http://localhost:8000/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"query": "測試查詢"}'

# 回應的 sources 應包含 file_url：
# {
#   "answer": "...",
#   "sources": [
#     {
#       "id": "...",
#       "document_id": "550e8400...",
#       "document_name": "test.pdf",
#       "file_url": "/api/documents/550e8400.../file",
#       ...
#     }
#   ]
# }
```

### 5. 前端測試

1. 開啟 http://localhost:3001
2. 進入聊天頁面
3. 輸入查詢問題
4. 確認結果來源旁顯示「預覽原檔」按鈕
5. 點擊按鈕，PDF 應在新分頁開啟

## File Structure After Setup

```
ai-km-platform/
├── backend/
│   └── storage/
│       └── documents/
│           └── {document_id}/
│               └── {filename}
└── frontend/
    └── ...
```

## Troubleshooting

### 問題：預覽按鈕未顯示

**原因**: file_url 為 null（原始檔案不存在）

**解決**: 確認 `storage/documents/` 目錄下有對應的原始檔案

### 問題：PDF 無法內嵌顯示

**原因**: 瀏覽器設定或 CORS 問題

**解決**:
1. 確認使用現代瀏覽器（Chrome/Firefox/Safari/Edge）
2. 確認後端 CORS 設定正確

### 問題：404 錯誤

**原因**: document_id 無效或檔案已刪除

**解決**: 使用 `GET /api/kb/documents` 確認文件存在
