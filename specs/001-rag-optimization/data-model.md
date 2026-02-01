# Data Model: RAG 系統優化

**Feature**: 001-rag-optimization
**Date**: 2026-01-31

## 1. 新增實體

### 1.1 CachedQuery（快取查詢）

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| cache_key | str | 快取鍵（查詢雜湊） | Required, unique |
| query | str | 原始查詢文字 | Required |
| query_normalized | str | 正規化後查詢 | Required |
| top_k | int | 返回數量 | 1-20 |
| results | list[SearchResult] | 搜尋結果（JSON 序列化） | Required |
| created_at | datetime | 建立時間 | Auto |
| expires_at | datetime | 過期時間 | Auto (created_at + TTL) |
| hit_count | int | 命中次數 | Default: 0 |

**Storage**: Redis Hash
```
Key: query:{cache_key}
Fields: query, results, created_at, hit_count
TTL: 3600 seconds (configurable)
```

---

### 1.2 BackupRecord（備份記錄）

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| id | str (UUID) | 備份唯一識別碼 | Auto-generated |
| collection_name | str | 被備份的 collection | Required |
| snapshot_name | str | Qdrant snapshot 名稱 | Required |
| file_path | str | 備份檔案路徑 | Required |
| file_size | int | 檔案大小（bytes） | Required |
| vector_count | int | 向量數量 | Required |
| status | BackupStatus | 狀態 | Required |
| created_at | datetime | 建立時間 | Auto |
| completed_at | datetime | 完成時間 | Nullable |
| error_message | str | 錯誤訊息 | Nullable |

**BackupStatus Enum**:
- `pending`: 排隊中
- `in_progress`: 執行中
- `completed`: 完成
- `failed`: 失敗

**Storage**: JSON file (`./backups/manifest.json`)

---

### 1.3 ProcessingTask（處理任務）

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| id | str (UUID) | 任務唯一識別碼 | Auto-generated |
| document_id | str | 文件識別碼 | Required |
| filename | str | 檔案名稱 | Required |
| file_size | int | 檔案大小 | Required |
| status | TaskStatus | 任務狀態 | Required |
| step | ProcessingStep | 目前步驟 | Required |
| progress | int | 完成百分比 (0-100) | Required |
| chunk_count | int | 處理的區塊數 | Default: 0 |
| message | str | 狀態訊息 | Nullable |
| error | str | 錯誤訊息 | Nullable |
| created_at | datetime | 建立時間 | Auto |
| updated_at | datetime | 更新時間 | Auto |
| completed_at | datetime | 完成時間 | Nullable |

**TaskStatus Enum**:
- `pending`: 等待處理
- `processing`: 處理中
- `completed`: 完成
- `failed`: 失敗
- `cancelled`: 已取消

**ProcessingStep Enum**:
- `uploading`: 上傳中
- `parsing`: 解析中
- `chunking`: 分塊中
- `embedding`: 向量化中
- `indexing`: 索引中
- `done`: 完成

**Storage**: Redis Hash with TTL
```
Key: task:{task_id}
Fields: All task fields (JSON serialized)
TTL: 86400 seconds (24 hours after completion)
```

---

## 2. 修改現有實體

### 2.1 Settings（config.py 新增欄位）

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| cohere_api_key | str | None | Cohere API 金鑰 |
| cohere_model | str | "rerank-v3.5" | Rerank 模型 |
| rerank_top_n | int | 10 | Rerank 返回數量 |
| redis_url | str | "redis://localhost:6379" | Redis 連線 URL |
| cache_ttl | int | 3600 | 快取 TTL（秒） |
| qdrant_url | str | "http://localhost:6333" | Qdrant 服務 URL |
| qdrant_api_key | str | None | Qdrant API 金鑰（可選） |
| backup_dir | str | "./backups" | 備份目錄 |

---

## 3. 資料關係

```
┌─────────────────┐
│   Document      │
│   (existing)    │
└────────┬────────┘
         │ 1:1
         ▼
┌─────────────────┐     ┌─────────────────┐
│ ProcessingTask  │     │   BackupRecord  │
│   (new)         │     │     (new)       │
└────────┬────────┘     └────────┬────────┘
         │                       │
         │                       │ references
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│  Vector Chunks  │ ◄── │ Qdrant Snapshot │
│   (Qdrant)      │     │                 │
└─────────────────┘     └─────────────────┘
         ▲
         │ cached results
         │
┌─────────────────┐
│  CachedQuery    │
│    (Redis)      │
└─────────────────┘
```

---

## 4. 狀態轉換圖

### 4.1 ProcessingTask 狀態機

```
        ┌──────────┐
        │  START   │
        └────┬─────┘
             │ create
             ▼
        ┌──────────┐
        │ pending  │
        └────┬─────┘
             │ start processing
             ▼
        ┌──────────┐    cancel
        │processing├──────────┐
        └────┬─────┘          │
             │                ▼
        ┌────┴────┐     ┌──────────┐
        │         │     │cancelled │
     success    fail    └──────────┘
        │         │
        ▼         ▼
   ┌──────────┐ ┌──────────┐
   │completed │ │  failed  │
   └──────────┘ └──────────┘
```

### 4.2 BackupRecord 狀態機

```
        ┌──────────┐
        │  START   │
        └────┬─────┘
             │ create
             ▼
        ┌──────────┐
        │ pending  │
        └────┬─────┘
             │ start backup
             ▼
        ┌───────────┐
        │in_progress│
        └────┬──────┘
             │
        ┌────┴────┐
        │         │
     success    fail
        │         │
        ▼         ▼
   ┌──────────┐ ┌──────────┐
   │completed │ │  failed  │
   └──────────┘ └──────────┘
```

---

## 5. Redis Key 設計

| Pattern | Purpose | TTL |
|---------|---------|-----|
| `query:{hash}` | 查詢結果快取 | 3600s (配置) |
| `task:{task_id}` | 處理任務狀態 | 86400s |
| `tasks:active` | 活躍任務 ID 列表 (Set) | No TTL |
| `embedding:{text_hash}` | Embedding 快取（可選） | 604800s (7 days) |

---

## 6. Pydantic Schema 定義

```python
from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ProcessingStep(str, Enum):
    UPLOADING = "uploading"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    DONE = "done"

class BackupStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class ProcessingTask(BaseModel):
    id: str
    document_id: str
    filename: str
    file_size: int
    status: TaskStatus = TaskStatus.PENDING
    step: ProcessingStep = ProcessingStep.UPLOADING
    progress: int = Field(ge=0, le=100, default=0)
    chunk_count: int = 0
    message: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

class BackupRecord(BaseModel):
    id: str
    collection_name: str
    snapshot_name: str
    file_path: str
    file_size: int
    vector_count: int
    status: BackupStatus = BackupStatus.PENDING
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

class ProgressMessage(BaseModel):
    """WebSocket 進度訊息"""
    task_id: str
    status: TaskStatus
    step: ProcessingStep
    progress: int
    message: str
    error: Optional[str] = None
```
