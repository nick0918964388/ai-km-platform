# Quickstart: 結構化資料查詢

**Feature**: 003-structured-data-query
**Date**: 2026-02-01

## 環境需求

- Python 3.10+
- Node.js 18+
- PostgreSQL 15+
- Redis 7+ (現有)
- Docker & Docker Compose (可選)

## 快速開始

### 1. 安裝後端依賴

```bash
cd backend

# 建立虛擬環境 (如尚未建立)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# .\venv\Scripts\activate  # Windows

# 安裝新依賴
pip install sqlalchemy[asyncio]>=2.0.0 asyncpg>=0.29.0 alembic>=1.13.0
pip install -r requirements.txt
```

### 2. 設定 PostgreSQL

```bash
# 使用 Docker 啟動 PostgreSQL
docker run -d \
  --name aikm-postgres \
  -e POSTGRES_USER=aikm \
  -e POSTGRES_PASSWORD=aikm_secret \
  -e POSTGRES_DB=aikm_db \
  -p 5432:5432 \
  postgres:15

# 或加入 docker-compose.yml
```

### 3. 設定環境變數

編輯 `backend/.env`:

```env
# 新增 PostgreSQL 設定
DATABASE_URL=postgresql+asyncpg://aikm:aikm_secret@localhost:5432/aikm_db

# 現有設定保持不變
OPENAI_API_KEY=sk-...
QDRANT_URL=http://localhost:6333
REDIS_URL=redis://localhost:6379
```

### 4. 初始化資料庫

```bash
cd backend

# 初始化 Alembic
alembic init alembic

# 執行資料庫遷移
alembic upgrade head

# 載入測試資料 (開發用)
python scripts/seed_data.py
```

### 5. 啟動後端服務

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### 6. 安裝前端依賴

```bash
cd frontend

# 安裝圖表庫
npm install recharts

# 安裝其他依賴
npm install
```

### 7. 啟動前端開發伺服器

```bash
cd frontend
npm run dev
```

---

## 驗證安裝

### 測試後端 API

```bash
# 測試查詢 API
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "查詢 EMU801 故障歷程"}'

# 預期回應
{
  "intent": "structured_query",
  "answer": "以下是 EMU801 的故障歷程：",
  "data": {
    "type": "table",
    "title": "故障紀錄",
    "rows": [...]
  }
}
```

### 測試前端頁面

開啟瀏覽器訪問：
- 對話介面: http://localhost:3000
- 儀表板: http://localhost:3000/dashboard

---

## 開發指引

### 新增資料表欄位

1. 修改 `backend/app/models/structured/*.py`
2. 建立遷移腳本:
   ```bash
   alembic revision --autogenerate -m "add column description"
   ```
3. 執行遷移:
   ```bash
   alembic upgrade head
   ```

### 測試 NL2SQL

```python
from app.services.nl2sql_service import NL2SQLService

service = NL2SQLService()
result = await service.translate("EMU801 最近三個月的故障紀錄")
print(result.sql)
# SELECT * FROM fault_records
# WHERE vehicle_code = 'EMU801'
# AND fault_date >= NOW() - INTERVAL '3 months'
```

### 新增意圖類型

編輯 `backend/app/services/intent_classifier.py`:

```python
INTENT_EXAMPLES = {
    "knowledge_query": [
        "煞車系統維修注意事項",
        "如何更換空調濾網",
    ],
    "structured_query": [
        "EMU801 故障歷程",
        "查詢零件庫存",
    ],
    # 新增意圖...
}
```

---

## 常見問題

### Q: PostgreSQL 連線失敗

```
Error: connection refused
```

**解決**: 確認 PostgreSQL 容器正在運行：
```bash
docker ps | grep aikm-postgres
```

### Q: 資料庫遷移失敗

```
Error: Can't locate revision
```

**解決**: 重置遷移狀態：
```bash
alembic downgrade base
alembic upgrade head
```

### Q: NL2SQL 產生錯誤 SQL

**解決**: 檢查 schema prompt 是否包含最新的表格結構：
```python
# 確認 app/services/nl2sql_service.py 中的 SCHEMA_PROMPT 是最新的
```

---

## 下一步

1. 閱讀 [data-model.md](./data-model.md) 了解資料模型
2. 閱讀 [contracts/api.yaml](./contracts/api.yaml) 了解 API 規格
3. 閱讀 [research.md](./research.md) 了解技術決策
4. 執行 `/speckit.tasks` 取得任務清單
