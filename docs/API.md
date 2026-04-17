# API 文檔

AIKM Platform REST API 完整說明

## 基礎資訊

| 項目 | 說明 |
|------|------|
| Base URL | `http://localhost:8000` (開發) / `https://aikmbackend.nickai.cc` (生產) |
| 認證方式 | `X-API-Key` Header |
| 內容類型 | `application/json` |
| API 文檔 | `/docs` (Swagger UI) / `/redoc` (ReDoc) |

## 認證

除了公開端點外，所有 API 請求都需要在 Header 中包含 API Key：

```http
X-API-Key: your-api-key-here
```

### 公開端點（不需認證）
- `GET /` - 根端點
- `GET /health` - 健康檢查
- `GET /docs` - API 文檔
- `GET /openapi.json` - OpenAPI Schema
- `GET /redoc` - ReDoc 文檔

---

## 聊天與搜尋 API

### POST /api/chat

與知識庫進行 RAG 問答。

**Request Body:**
```json
{
  "query": "轉向架維修標準流程是什麼？",
  "image_base64": null,
  "top_k": 10
}
```

| 參數 | 類型 | 必要 | 說明 |
|------|------|------|------|
| query | string | ✅ | 查詢問題 |
| image_base64 | string | ❌ | Base64 編碼的圖片 (多模態查詢) |
| top_k | integer | ❌ | 檢索文件數量 (預設: 10) |

**Response:**
```json
{
  "answer": "轉向架維修標準流程包含以下步驟...",
  "sources": [
    {
      "id": "chunk_123",
      "document_id": "doc_456",
      "filename": "maintenance_manual.pdf",
      "page": 15,
      "text": "轉向架維修步驟：1. 拆卸...",
      "score": 0.85
    }
  ]
}
```

---

### POST /api/chat/stream

串流式 RAG 問答，使用 Server-Sent Events (SSE)。

**Request Body:** 同 `/api/chat`

**Response:** SSE 串流

```
data: {"type": "sources", "data": [...]}

data: {"type": "content", "data": "轉向架"}

data: {"type": "content", "data": "維修標準"}

data: {"type": "metadata", "data": {"model": "gpt-4o", "duration_ms": 1234, "tokens": 500}}

data: {"type": "done"}

data: {"type": "follow_up", "data": ["如何檢查轉向架磨損？", "維修週期是多久？"]}
```

**事件類型:**
| 類型 | 說明 |
|------|------|
| `sources` | 檢索到的來源文件 (首先發送) |
| `content` | 串流回應內容片段 |
| `metadata` | 模型資訊、耗時、Token 使用量 |
| `done` | 串流完成信號 |
| `follow_up` | 建議的後續問題 |
| `error` | 錯誤訊息 |

---

### POST /api/search

搜尋知識庫，不生成回答。

**Request Body:**
```json
{
  "query": "煞車系統",
  "top_k": 10
}
```

**Response:**
```json
{
  "results": [...],
  "total": 10
}
```

---

## 知識庫管理 API

### POST /api/kb/upload

上傳文件到知識庫。

**Request:** `multipart/form-data`

| 參數 | 類型 | 說明 |
|------|------|------|
| file | File | 文件 (PDF/Word/Excel/圖片) |

**支援格式:**
- PDF (`.pdf`)
- Word (`.docx`)
- Excel (`.xlsx`, `.xls`)
- 圖片 (`.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`)

**Response:**
```json
{
  "success": true,
  "document_id": "doc_abc123",
  "filename": "manual.pdf",
  "doc_type": "pdf",
  "chunk_count": 45,
  "message": "成功上傳並處理 manual.pdf，產生 45 個向量區塊。"
}
```

---

### GET /api/kb/documents

列出所有已上傳的文件。

**Response:**
```json
{
  "documents": [
    {
      "id": "doc_abc123",
      "filename": "manual.pdf",
      "doc_type": "pdf",
      "chunk_count": 45,
      "uploaded_at": "2024-02-01T10:30:00",
      "file_size": 2048576
    }
  ],
  "total": 1
}
```

---

### DELETE /api/kb/documents/{document_id}

刪除指定文件及其所有區塊。

**Response:**
```json
{
  "success": true,
  "message": "成功刪除文件 doc_abc123"
}
```

---

### GET /api/kb/documents/{document_id}/file

取得原始文件供預覽或下載。

**Response:** 
- PDF 文件：直接在瀏覽器中顯示 (`Content-Disposition: inline`)
- 其他格式：觸發下載 (`Content-Disposition: attachment`)

---

### GET /api/kb/stats

取得知識庫統計資訊。

**Response:**
```json
{
  "total_documents": 15,
  "total_chunks": 523,
  "storage_size_mb": 156.7,
  "last_updated": "2024-02-01T15:00:00"
}
```

---

## 統一查詢 API

### POST /api/query

智慧路由查詢，自動識別意圖並路由至適當的後端。

**Request Body:**
```json
{
  "query": "查詢 EMU801 故障歷程",
  "context": null,
  "include_sources": true
}
```

**Response:**
```json
{
  "success": true,
  "query": "查詢 EMU801 故障歷程",
  "query_type": "structured",
  "intent_info": {
    "intent": "structured",
    "confidence": 0.95,
    "entities": {"vehicle_code": "EMU801"},
    "reasoning": "查詢特定車輛的故障記錄，屬於結構化資料查詢"
  },
  "structured_result": {
    "type": "structured",
    "sql": "SELECT * FROM fault_records WHERE vehicle_id = ...",
    "data": [...],
    "row_count": 10,
    "columns": ["fault_code", "fault_date", ...],
    "execution_time_ms": 15.3
  },
  "timestamp": "2024-02-01T10:30:00"
}
```

**查詢類型 (query_type):**
| 類型 | 說明 |
|------|------|
| `structured` | 結構化資料查詢 (SQL) |
| `knowledge` | 知識庫查詢 (RAG) |
| `hybrid` | 混合查詢 |
| `clarification` | 需要更多資訊 |

---

### POST /api/query/classify

僅進行意圖分類，不執行查詢。

**Request Body:** 同 `/api/query`

**Response:**
```json
{
  "intent": "structured",
  "confidence": 0.95,
  "entities": {"vehicle_code": "EMU801"},
  "reasoning": "..."
}
```

---

### POST /api/query/sql

直接執行自然語言轉 SQL 查詢（跳過意圖分類）。

---

## 結構化資料 API

### GET /api/structured/vehicles

查詢車輛清單。

**Query Parameters:**
| 參數 | 說明 |
|------|------|
| depot | 車站篩選 |
| vehicle_type | 車型篩選 |
| status | 狀態篩選 (active/maintenance/retired) |
| limit | 回傳數量上限 (預設: 100) |

---

### GET /api/structured/vehicles/{vehicle_code}

查詢特定車輛資訊。

---

### GET /api/structured/vehicles/{vehicle_code}/faults

查詢車輛故障記錄。

**Query Parameters:**
| 參數 | 說明 |
|------|------|
| status | 狀態篩選 (open/in_progress/resolved) |
| fault_type | 故障類型篩選 |
| limit | 回傳數量上限 |

---

### GET /api/structured/vehicles/{vehicle_code}/maintenance

查詢車輛維修記錄。

---

### GET /api/structured/vehicles/{vehicle_code}/costs

查詢車輛成本記錄。

---

### GET /api/structured/inventory

查詢零件庫存。

**Query Parameters:**
| 參數 | 說明 |
|------|------|
| category | 分類篩選 |
| low_stock_only | 僅顯示低庫存項目 |

---

## 儀表板 API

### GET /api/dashboard/stats

取得儀表板統計資料。

### GET /api/dashboard/trends

取得趨勢資料。

### GET /api/dashboard/alerts

取得系統警報。

---

## 匯出 API

### POST /api/export/documents

匯出文件清單為 CSV/Excel。

### POST /api/export/chat-history

匯出聊天記錄。

---

## 備份與快取 API

### POST /api/kb/backups

建立向量資料庫備份。

### GET /api/kb/backups

列出所有備份。

### POST /api/kb/backups/{backup_id}/restore

還原備份。

### GET /api/kb/cache/stats

取得快取統計。

### POST /api/kb/cache/clear

清除快取。

---

## 評測 API

### GET /api/kb/evaluate/metrics

取得可用的評測指標說明。

### POST /api/kb/evaluate

執行 RAGAS 評測。

**Request Body:**
```json
{
  "test_data": [
    {
      "user_input": "轉向架維修週期是多久？",
      "reference": "轉向架每 5 年進行一次大修"
    }
  ],
  "top_k": 10,
  "metrics": ["context_recall", "faithfulness", "factual_correctness"]
}
```

---

## 錯誤處理

所有 API 錯誤回應格式：

```json
{
  "detail": "錯誤訊息說明"
}
```

**HTTP 狀態碼:**
| 狀態碼 | 說明 |
|--------|------|
| 200 | 成功 |
| 400 | 請求格式錯誤 |
| 401 | 未授權 (API Key 無效) |
| 404 | 資源不存在 |
| 500 | 伺服器內部錯誤 |
