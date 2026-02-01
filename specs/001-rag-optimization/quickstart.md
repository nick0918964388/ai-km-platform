# Quickstart: RAG 系統優化

本指南說明如何設定與驗證 RAG 系統優化功能。

## 前置需求

- Docker & Docker Compose
- Python 3.10+
- Node.js 18+
- Cohere API Key
- Redis
- Qdrant

## 1. 環境設定

### 1.1 啟動 Docker 服務

```bash
# 在專案根目錄建立 docker-compose.yml（如尚未存在）
cat >> docker-compose.yml << 'EOF'
version: '3.8'

services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - ./data/qdrant:/qdrant/storage
    environment:
      - QDRANT__SERVICE__GRPC_PORT=6334

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - ./data/redis:/data
    command: redis-server --appendonly yes
EOF

# 啟動服務
docker-compose up -d
```

### 1.2 設定環境變數

```bash
# 複製範例檔案
cp backend/.env.example backend/.env

# 編輯 .env 檔案，新增以下設定
cat >> backend/.env << 'EOF'

# Cohere Reranker
COHERE_API_KEY=your-cohere-api-key
COHERE_MODEL=rerank-v3.5
RERANK_TOP_N=10

# Redis
REDIS_URL=redis://localhost:6379
CACHE_TTL=3600

# Qdrant (persistent)
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

# Backup
BACKUP_DIR=./backups
EOF
```

### 1.3 安裝依賴

```bash
# Backend
cd backend
pip install cohere redis aioredis

# Frontend (如需 WebSocket hook)
cd ../
npm install
```

## 2. 驗證功能

### 2.1 驗證 Reranker 整合

```bash
# 啟動後端服務
cd backend
uvicorn app.main:app --reload --port 8000

# 測試搜尋 API（另開終端機）
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "轉向架軸箱潤滑", "top_k": 5}'

# 預期結果：返回經過 rerank 的相關結果
```

### 2.2 驗證持久化

```bash
# 1. 上傳測試文件
curl -X POST http://localhost:8000/api/kb/upload \
  -F "file=@test-document.pdf"

# 2. 驗證資料存在
curl http://localhost:8000/api/kb/stats

# 3. 重啟服務
docker-compose restart qdrant

# 4. 再次驗證資料（應仍然存在）
curl http://localhost:8000/api/kb/stats
```

### 2.3 驗證備份/恢復

```bash
# 建立備份
curl -X POST http://localhost:8000/api/kb/backups \
  -H "Content-Type: application/json" \
  -d '{"collection_name": "text_chunks"}'

# 列出備份
curl http://localhost:8000/api/kb/backups

# 恢復備份（使用返回的 backup_id）
curl -X POST http://localhost:8000/api/kb/backups/{backup_id}/restore
```

### 2.4 驗證快取

```bash
# 第一次查詢（快取未命中）
time curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "EMU800 保養週期", "top_k": 5}'

# 第二次查詢（快取命中，應明顯較快）
time curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "EMU800 保養週期", "top_k": 5}'

# 查看快取統計
curl http://localhost:8000/api/cache/stats
```

### 2.5 驗證 WebSocket 進度

```python
# test_websocket.py
import asyncio
import websockets
import json

async def test_upload_progress():
    task_id = "test-task-123"  # 替換為實際任務 ID
    uri = f"ws://localhost:8000/api/ws/upload/{task_id}"

    async with websockets.connect(uri) as ws:
        print(f"Connected to {uri}")
        while True:
            message = await ws.recv()
            data = json.loads(message)
            print(f"Progress: {data['progress']}% - {data['message']}")

            if data['status'] in ['completed', 'failed']:
                break

asyncio.run(test_upload_progress())
```

## 3. 前端整合

### 3.1 使用 WebSocket Hook

已實作的 Hook 位於 `frontend/src/hooks/useUploadProgress.ts`：

```typescript
import { useUploadProgress, getStepLabel } from '@/hooks/useUploadProgress';

function MyComponent() {
  const {
    connect,
    disconnect,
    cancel,
    progress,
    isConnected,
    isComplete,
    error,
  } = useUploadProgress({
    onComplete: (msg) => console.log('Upload complete!', msg),
    onError: (err) => console.error('Upload error:', err),
  });

  // Connect when you have a task ID
  useEffect(() => {
    if (taskId) connect(taskId);
    return () => disconnect();
  }, [taskId]);

  return (
    <div>
      {progress && (
        <>
          <p>{getStepLabel(progress.step)}: {progress.progress}%</p>
          <p>{progress.message}</p>
        </>
      )}
    </div>
  );
}
```

### 3.2 進度元件

已實作的元件位於 `frontend/src/components/upload/UploadProgress.tsx`：

```tsx
import { UploadProgress } from '@/components/upload/UploadProgress';

function UploadPage() {
  const [taskId, setTaskId] = useState<string | null>(null);

  return (
    <UploadProgress
      taskId={taskId}
      onComplete={(msg) => {
        console.log('Complete:', msg.chunk_count, 'chunks');
        setTaskId(null);
      }}
      onError={(err) => console.error(err)}
    />
  );
}
```

完整整合範例請參考 `frontend/src/app/(main)/admin/knowledge-base/page.tsx`。

## 4. 效能驗證

| 測試項目 | 目標 | 驗證方法 |
|----------|------|----------|
| 搜尋回應（首次） | < 2s | `time curl` 測試 |
| 搜尋回應（快取） | < 100ms | `time curl` 測試 |
| 資料持久化 | 100% | 重啟後驗證 |
| 進度更新 | < 2s 延遲 | WebSocket 監控 |

## 5. 疑難排解

### Qdrant 無法連線

```bash
# 檢查容器狀態
docker-compose ps

# 檢查日誌
docker-compose logs qdrant
```

### Redis 連線失敗

```bash
# 測試 Redis 連線
redis-cli ping
# 預期回應: PONG
```

### Cohere API 錯誤

```bash
# 驗證 API Key
curl https://api.cohere.ai/v1/check-api-key \
  -H "Authorization: Bearer $COHERE_API_KEY"
```

### WebSocket 連線失敗

1. 確認後端已啟用 WebSocket 路由
2. 檢查 CORS 設定是否允許 WebSocket
3. 確認任務 ID 有效
