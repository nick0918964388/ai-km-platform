# Research: RAG 系統優化

**Feature**: 001-rag-optimization
**Date**: 2026-01-31

## 1. Reranker 整合研究

### Decision: 使用 Cohere Rerank API

**Rationale**:
- Cohere Rerank v3 針對多語言（含中文）有優秀表現
- API 介面簡潔，易於整合現有 RAG 流程
- 支援 batch reranking，可一次處理多個文件
- 提供 relevance score 可用於過濾低相關性結果

**Alternatives Considered**:

| 方案 | 優點 | 缺點 | 結論 |
|------|------|------|------|
| Cohere Rerank API | 高品質、中文支援佳、低延遲 | 需付費 API | ✅ 選用 |
| Cross-encoder (local) | 免費、可離線 | 延遲高、需 GPU、中文效果不穩定 | ❌ |
| BGE-reranker | 開源、中文專屬 | 需部署、記憶體需求高 | 備選 |
| ColBERT | 高效率 | 需額外索引、複雜度高 | ❌ |

**Implementation Notes**:
- 在 Hybrid Search 後呼叫 Cohere Rerank
- 設定 `top_n` 參數控制返回數量（建議 5-10）
- 實作 fallback：API 失敗時返回原始排序
- 快取 rerank 結果以降低 API 成本

---

## 2. 持久化向量資料庫研究

### Decision: Qdrant Persistent Mode (Docker)

**Rationale**:
- 現有系統已使用 Qdrant（in-memory），遷移成本低
- Docker 部署簡單，支援 volume 持久化
- 內建 snapshot 功能可用於備份/恢復
- 支援 collection 級別的備份

**Alternatives Considered**:

| 方案 | 優點 | 缺點 | 結論 |
|------|------|------|------|
| Qdrant Docker | 遷移簡單、snapshot 支援 | 需額外容器 | ✅ 選用 |
| Qdrant Cloud | 全託管、高可用 | 成本較高 | 備選（生產環境） |
| Milvus | 高效能、分散式 | 學習曲線、不同 API | ❌ |
| Pinecone | 全託管 | 閉源、成本高 | ❌ |

**Implementation Notes**:
- Docker Compose 設定 Qdrant 服務
- Volume 掛載 `/qdrant/storage` 持久化資料
- 使用 Qdrant REST API 進行 snapshot 管理
- 備份存放於 `./backups/qdrant/` 目錄

**Backup Strategy**:
```yaml
# 備份流程
1. 呼叫 POST /collections/{name}/snapshots 建立快照
2. 下載快照檔案至備份目錄
3. 記錄備份元資料（時間、大小、collection stats）

# 恢復流程
1. 上傳快照檔案至 Qdrant
2. 呼叫 PUT /collections/{name}/snapshots/recover
3. 驗證 collection 狀態
```

---

## 3. 常見問題快取研究

### Decision: Redis + 查詢雜湊快取

**Rationale**:
- Redis 是業界標準快取解決方案
- 支援 TTL 自動過期
- 支援 pub/sub 可用於快取失效通知
- Python `redis` 套件成熟穩定

**Alternatives Considered**:

| 方案 | 優點 | 缺點 | 結論 |
|------|------|------|------|
| Redis | 成熟、功能齊全、TTL 支援 | 需額外服務 | ✅ 選用 |
| In-memory dict | 簡單、無依賴 | 無 TTL、重啟遺失、無法分散 | ❌ |
| Memcached | 輕量 | 功能較少 | ❌ |
| File cache | 簡單 | 效能差 | ❌ |

**Cache Key Strategy**:
```python
# 查詢快取鍵格式
cache_key = f"query:{hash(normalized_query)}:top_k:{top_k}"

# 正規化步驟
1. 移除多餘空白
2. 轉小寫（英文）
3. 排序（如有多個關鍵字）
```

**Cache Invalidation Strategy**:
- TTL：預設 1 小時，可配置
- 主動清除：文件更新/刪除時清除相關快取
- 使用 Redis key pattern 刪除：`DEL query:*` 或 `SCAN` + `DEL`

**Implementation Notes**:
- 快取層級：
  1. 查詢 embedding（昂貴）
  2. 搜尋結果（含 rerank 後）
  3. Chat 回應（可選，需考慮上下文）
- 快取命中時直接返回，不呼叫 embedding/search

---

## 4. 前端上傳進度研究

### Decision: FastAPI WebSocket + React Hook

**Rationale**:
- FastAPI 原生支援 WebSocket
- 即時雙向通訊適合進度更新
- React 可透過 custom hook 管理 WebSocket 狀態

**Alternatives Considered**:

| 方案 | 優點 | 缺點 | 結論 |
|------|------|------|------|
| WebSocket | 即時、雙向 | 需維護連線 | ✅ 選用 |
| Server-Sent Events | 簡單、自動重連 | 單向 | 備選 |
| Polling | 簡單 | 延遲高、資源浪費 | ❌ |
| Long Polling | 較即時 | 複雜度高 | ❌ |

**Protocol Design**:
```typescript
// 訊息格式
interface ProgressMessage {
  task_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  step: 'parsing' | 'chunking' | 'embedding' | 'indexing';
  progress: number;  // 0-100
  message: string;
  error?: string;
}

// WebSocket 端點
ws://localhost:8000/api/ws/upload/{task_id}
```

**Implementation Notes**:
- 後端：`FastAPI.websocket` 裝飾器
- 前端：`useWebSocket` custom hook
- 進度計算：
  - parsing: 0-25%
  - chunking: 25-50%
  - embedding: 50-90%
  - indexing: 90-100%
- 任務狀態存於 Redis（TaskManager service）

---

## 5. 效能預估

| 操作 | 現況 | 優化後 |
|------|------|--------|
| 搜尋（首次） | ~1.5s | ~1.8s（含 rerank） |
| 搜尋（快取命中） | N/A | <100ms |
| 系統重啟後資料載入 | 需重新索引 | 自動恢復 |
| 文件處理進度 | 無回饋 | 即時更新（<2s 延遲） |

---

## 6. 依賴清單

### 新增 Python 套件
```
cohere>=5.0.0          # Rerank API
redis>=5.0.0           # 快取
aioredis>=2.0.0        # 非同步 Redis（可選）
```

### 新增 Docker 服務
```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - ./data/qdrant:/qdrant/storage

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - ./data/redis:/data
```

---

## 7. 風險與緩解

| 風險 | 影響 | 緩解措施 |
|------|------|----------|
| Cohere API 限流/故障 | 搜尋品質下降 | Fallback 至原排序 |
| Redis 故障 | 快取失效 | Fallback 至直接搜尋 |
| Qdrant 容器重啟 | 短暫無法搜尋 | Docker restart policy |
| WebSocket 斷線 | 進度更新中斷 | 前端自動重連 + 任務狀態查詢 |
