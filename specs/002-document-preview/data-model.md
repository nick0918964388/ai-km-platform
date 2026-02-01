# Data Model: 文件預覽功能 (Document Preview)

**Date**: 2026-02-01
**Feature Branch**: `002-document-preview`

## Entity Changes

### SearchResult (Modified)

現有欄位保持不變，新增 `file_url` 欄位。

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | string | Yes | Chunk ID |
| content | string | Yes | Chunk 內容 |
| doc_type | ChunkType | Yes | text / image |
| document_id | string | Yes | 文件 ID |
| document_name | string | Yes | 原始檔名 |
| score | float | Yes | 相似度分數 |
| image_base64 | string | No | 圖片 Base64 編碼 |
| **file_url** | **string** | **No** | **原始文件下載 URL** |

**file_url 格式**: `/api/documents/{document_id}/file`

### StoredFile (New - Filesystem Entity)

不存入資料庫，以檔案系統結構表示。

```text
storage/documents/{document_id}/{original_filename}
```

| Attribute | Description |
|-----------|-------------|
| document_id | 文件唯一識別碼 (UUID) |
| original_filename | 原始上傳檔名（含副檔名）|
| file_path | 完整檔案路徑 |
| content_type | MIME type |

## Configuration Changes

### Settings (Modified)

新增 `storage_dir` 設定項。

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| storage_dir | string | "./storage/documents" | 原始文件儲存目錄 |

## Relationships

```
Document (Qdrant)
    │
    ├── 1:N ──→ TextChunk (Qdrant - text_chunks collection)
    │              └── SearchResult.document_id
    │
    ├── 1:N ──→ ImageChunk (Qdrant - image_chunks collection)
    │              └── SearchResult.document_id
    │
    └── 1:1 ──→ StoredFile (Filesystem)
                   └── storage/documents/{document_id}/
```

## Validation Rules

1. **file_url**:
   - 格式必須為 `/api/documents/{document_id}/file`
   - 僅當原始檔案存在時才填入
   - 若原始檔案不存在，設為 `null`

2. **StoredFile**:
   - document_id 必須為有效 UUID
   - original_filename 不得包含路徑分隔符
   - 檔案大小不超過 50MB

## State Transitions

### Document Lifecycle

```
Upload Request
    │
    ▼
┌─────────────────┐
│ 驗證檔案格式/大小  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 生成 document_id │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐ ┌───────────┐
│保存原檔│ │處理向量化  │
└───┬───┘ └─────┬─────┘
    │           │
    ▼           ▼
 StoredFile   Chunks
    │           │
    └─────┬─────┘
          │
          ▼
    Upload Complete
```

### File Access Flow

```
GET /api/documents/{id}/file
    │
    ▼
┌─────────────────┐
│ 查詢 document 記錄 │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
 存在       不存在
    │         │
    ▼         ▼
┌───────┐   404
│讀取檔案│
└───┬───┘
    │
┌───┴───┐
│       │
成功    失敗
│       │
▼       ▼
FileResponse  500
```
