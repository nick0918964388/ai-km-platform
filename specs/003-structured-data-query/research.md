# Research: 結構化資料查詢

**Feature**: 003-structured-data-query
**Date**: 2026-02-01

## 1. 自然語言轉 SQL (NL2SQL) 技術選型

### Decision: OpenAI Function Calling + Schema Prompt

### Rationale
- 現有系統已整合 OpenAI API，可直接複用
- Function Calling 可精確控制輸出格式
- 透過 Schema 描述引導 LLM 生成正確 SQL
- 支援中文自然語言輸入

### Alternatives Considered

| 方案 | 優點 | 缺點 | 結論 |
|------|------|------|------|
| OpenAI Function Calling | 易整合、高準確度、支援中文 | API 成本 | ✅ 採用 |
| LangChain SQL Agent | 生態系成熟 | 過度複雜、不需完整 agent | ❌ 過度設計 |
| Vanna.ai | 專門 NL2SQL 工具 | 需額外學習、依賴外部服務 | ❌ 增加依賴 |
| 本地 LLM (Ollama) | 無 API 成本 | 中文效果差、需 GPU 資源 | ❌ 效果不佳 |

### Implementation Notes
```python
# 使用 OpenAI Function Calling 產生 SQL
functions = [{
    "name": "execute_sql_query",
    "parameters": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "SQL query"},
            "tables": {"type": "array", "items": {"type": "string"}}
        }
    }
}]
```

---

## 2. 意圖識別 (Intent Classification) 策略

### Decision: LLM-based Classification with Few-shot Prompting

### Rationale
- 使用 LLM 進行意圖分類，準確度高
- Few-shot examples 可快速調整分類邏輯
- 支援混合型查詢識別
- 與現有 OpenAI 整合一致

### Intent Categories
1. **knowledge_query**: 知識庫查詢（維修手冊、技術文件）
2. **structured_query**: 結構化資料查詢（車輛、故障、檢修紀錄）
3. **hybrid_query**: 混合型查詢（需同時查詢兩者）
4. **clarification_needed**: 無法判斷，需請求澄清

### Prompt Template
```
你是一個意圖分類器。根據使用者的問題，判斷查詢類型：

範例：
- "煞車系統維修注意事項" → knowledge_query
- "EMU801 故障歷程" → structured_query
- "EMU801 為何經常出現轉向架故障" → hybrid_query
- "今天天氣如何" → clarification_needed

使用者問題：{query}
```

---

## 3. PostgreSQL 整合方案

### Decision: SQLAlchemy 2.0 + asyncpg

### Rationale
- SQLAlchemy 2.0 支援 async/await，與 FastAPI 配合良好
- asyncpg 是效能最佳的 PostgreSQL async driver
- ORM 模式便於維護，支援 migration
- 參數化查詢自動防止 SQL injection

### Configuration
```python
# 新增依賴
# requirements.txt
sqlalchemy[asyncio]>=2.0.0
asyncpg>=0.29.0
alembic>=1.13.0

# 連線設定
DATABASE_URL = "postgresql+asyncpg://user:pass@host:5432/aikm"
```

### Migration Strategy
- 使用 Alembic 管理資料庫 schema 變更
- 提供初始 seed data script 供開發測試

---

## 4. 資料卡片整合設計

### Decision: 對話訊息中嵌入結構化資料區塊

### Rationale
- 使用者體驗一致，無需切換介面
- 資料以卡片形式呈現，易於閱讀
- 可展開/收合查看詳細資料
- 支援從卡片直接匯出

### UI Pattern
```
+------------------------------------------+
| 🤖 AI Assistant                           |
|------------------------------------------|
| 以下是 EMU801 的故障歷程：                 |
|                                          |
| ┌────────────────────────────────────┐   |
| │ 📋 故障紀錄 (共 5 筆)                │   |
| ├────────────────────────────────────┤   |
| │ 2025-12-15 | 轉向架異音 | 已修復    │   |
| │ 2025-11-20 | 煞車壓力  | 已修復    │   |
| │ ... 查看更多                        │   |
| ├────────────────────────────────────┤   |
| │ [📥 匯出 CSV] [📊 開啟詳細面板]      │   |
| └────────────────────────────────────┘   |
+------------------------------------------+
```

---

## 5. 儀表板圖表庫選型

### Decision: Recharts (React 圖表庫)

### Rationale
- React 原生整合，與 Next.js 相容
- 聲明式 API，易於使用
- 支援響應式設計
- 輕量級，打包體積小

### Alternatives Considered

| 方案 | 優點 | 缺點 | 結論 |
|------|------|------|------|
| Recharts | React 原生、輕量 | 圖表類型較少 | ✅ 採用 |
| Chart.js | 功能豐富 | 非 React 原生 | ❌ 整合複雜 |
| D3.js | 最靈活 | 學習曲線陡峭 | ❌ 過度複雜 |
| Carbon Charts | 與 Carbon 一致 | 文檔較少 | 🔄 備選方案 |

### Charts Needed
- 折線圖：故障趨勢
- 長條圖：維修成本分布
- 圓餅圖：故障類型分布
- 數值卡片：關鍵指標

---

## 6. 匯出功能實作

### Decision: 後端生成 + 前端下載

### Rationale
- 後端處理大量資料較有效率
- 統一的資料格式控制
- 支援 CSV 與 Excel 格式
- 可加入權限控制

### Libraries
```python
# 後端
import csv
from openpyxl import Workbook  # 已在現有依賴中
```

### API Design
```
GET /api/structured/export?table=fault_records&format=csv&filters=...
Response: Content-Disposition: attachment; filename="fault_records.csv"
```

---

## 7. SQL 安全性最佳實踐

### Decision: 多層防護策略

### Security Measures

1. **參數化查詢**: 所有 SQL 使用 SQLAlchemy ORM 或參數化查詢
2. **白名單驗證**: NL2SQL 產生的 SQL 只允許 SELECT 語句
3. **表格限制**: 只允許查詢指定的 7 個資料表
4. **欄位過濾**: 排除敏感欄位（如內部備註）
5. **結果限制**: 預設 LIMIT 100，最大 1000

### Validation Pipeline
```python
def validate_generated_sql(sql: str) -> bool:
    # 1. 只允許 SELECT
    if not sql.strip().upper().startswith("SELECT"):
        return False
    # 2. 禁止危險關鍵字
    forbidden = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE"]
    if any(kw in sql.upper() for kw in forbidden):
        return False
    # 3. 只允許白名單表格
    allowed_tables = ["vehicles", "fault_records", ...]
    # ... 驗證邏輯
    return True
```

---

## 8. 效能優化策略

### Decision: 索引 + 查詢快取 + 分頁

### Optimizations

1. **資料庫索引**
   - 車輛編號 (vehicle_id)
   - 日期欄位 (created_at, fault_date, maintenance_date)
   - 常用篩選欄位 (fault_type, status)

2. **Redis 快取**
   - 快取常見查詢結果（TTL 5 分鐘）
   - 快取儀表板統計資料（TTL 15 分鐘）

3. **分頁策略**
   - 預設每頁 20 筆
   - 使用 cursor-based pagination 處理大量資料

### Target Metrics
- 單表查詢 < 200ms
- 複雜關聯查詢 < 500ms
- 儀表板載入 < 3s

---

## Summary of Decisions

| 項目 | 決策 | 主要理由 |
|------|------|----------|
| NL2SQL | OpenAI Function Calling | 易整合、高準確度 |
| 意圖識別 | LLM Few-shot | 準確度高、易調整 |
| PostgreSQL Driver | SQLAlchemy + asyncpg | async 支援、防 SQL injection |
| 資料呈現 | 對話嵌入卡片 | 使用者體驗一致 |
| 圖表庫 | Recharts | React 原生、輕量 |
| 匯出 | 後端生成 | 效率、權限控制 |
| 安全性 | 多層防護 | 防 SQL injection |
| 效能 | 索引 + 快取 + 分頁 | 符合效能目標 |
