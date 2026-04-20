# neo4j-graphrag-python POC 評估報告

- 日期：2026-04-18
- Ticket：Phase 3 · W2-T1
- 執行者：Backend Implementation Agent
- 腳本：`backend/scripts/neo4j/poc_graphrag.py`
- JSON 原始輸出：`backend/scripts/neo4j/poc_graphrag_result.json`

---

## 1. 套件安裝

| 項目 | 結果 |
|------|------|
| `neo4j-graphrag` 版本 | **1.14.1**（PASS） |
| 安裝指令 | `pip install 'neo4j-graphrag[openai,cohere,ollama]'` |
| 本地 venv | `backend/venv`（Python 3.14.3） |
| neo4j driver | 6.1.0（已安裝，本次 POC 沿用） |
| OpenAI extra | 安裝成功（供 `OpenAILLM` / `OpenAIEmbeddings`） |
| Cohere extra | 安裝成功（供 `CohereLLM` / 既有 rerank 服務共用） |
| Ollama extra | 安裝成功（本次 POC 實測用） |
| 匯入驗證 | `Text2CypherRetriever`, `VectorCypherRetriever`, `HybridRetriever`, `OllamaLLM`, `SentenceTransformerEmbeddings` 全部 import 成功 |

### 依賴衝突（已記錄，非阻斷）

- `neo4j-graphrag 1.14.1` 鎖 `openai<2.0.0`，會把目前 venv 的 `openai 2.16.0` 降級到 `1.109.1`
- 影響：`instructor 1.14.5` 要 `openai>=2.0.0` → pip 顯示 ResolutionImpossible 警告，但不 block 安裝
- 目前 codebase 沒直接用 `instructor`，POC 實測（`services/embedding.py` + `services/rag.py` 的 OpenAI 呼叫路徑）未壞掉
- Docker image 需要重建：目前 image 沒有 `neo4j-graphrag`，`docker compose up -d --build backend` 時會一併裝起來

### 結論

**GO on install**：本機 venv 實測可用；部署時需重建 backend image。

---

## 2. 環境 / 測試資料

| 項目 | 值 |
|------|----|
| Neo4j | `bolt://192.168.1.11:7687`（既有 aikm-neo4j） |
| Test Label 前綴 | `PocTest_*`（3 個 label × 10 節點 × 8 關係） |
| Seed 資料 | 5 WorkOrder + 3 Asset + 2 ClassStructure + 關係 `PERFORMED_ON / CLASSIFIED_AS / PARENT_OF` |
| Vector Index | `poc_wo_desc_vec`（cosine, dim=384） |
| Fulltext Index | `poc_wo_desc_fts`（on `description`） |
| Embedding | `sentence-transformers/all-MiniLM-L6-v2`（本地，避免外部 API） |
| LLM | OllamaLLM → `http://ollama.webtw.xyz:11434` / `gemma4:31b-cloud` |
| 清理驗證 | `MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'PocTest_') RETURN count(n) = 0` ✅ |

共 **3 retrievers × 3 questions = 9 cases，全部 PASS**。

---

## 3. Retriever 評估

### 3.1 Text2CypherRetriever

- **狀態**：works（3/3）
- **平均 latency**：3550 ms（高延遲，取決於 Ollama model）
- **案例**：

| # | 問題 | 結果 | Latency | 生成 Cypher 摘要 |
|---|------|------|---------|------------------|
| 1 | 找車號 POC_EMU01 的所有工單 | rows=3 | 1607 ms | `MATCH (w:PocTest_WorkOrder)-[:PocTest_PERFORMED_ON]->(a:PocTest_Asset {assetnum:'POC_EMU01'}) RETURN w` |
| 2 | EMU 車型相關的分類結構有哪些？ | rows=2 | 1227 ms | `MATCH (c:PocTest_ClassStructure) WHERE c.description CONTAINS 'EMU' RETURN c` |
| 3 | 顯示最近一週的工單狀態（reportdate >= '2026-04-11'） | rows=4 | 7818 ms | `MATCH (w:PocTest_WorkOrder) WHERE w.reportdate >= '2026-04-11' RETURN w.wonum, w.status, w.reportdate` |

- **優點**
  - 中文問題直接產出正確 Cypher，含關係遍歷、字串條件、日期比較
  - schema/examples 皆以參數注入，不需重訓；支援 few-shot 調校
  - 回傳可拿到生成的 cypher（`result.metadata`），方便 audit log / 稽核
- **缺點**
  - 單次呼叫 1.2–7.8 秒（受 Ollama 網路與 model 影響）；批量查詢成本高
  - 無內建 SQL/Cypher 注入防護，必須搭配 `cypher_validator.py`（已建）做白名單
  - 高度依賴 LLM 品質，冷僻關係或長 schema 易產錯誤 Cypher
- **適用場景**
  - 使用者自然語言查詢（Chat 整合、NL→Cypher 面板）
  - 結構化關係推論（找路徑、多跳查詢）

### 3.2 VectorCypherRetriever

- **狀態**：works（3/3）
- **平均 latency**：173 ms
- **案例**：

| # | 問題 | 結果 | Latency |
|---|------|------|---------|
| 1 | 找車號 POC_EMU01 的所有工單 | rows=5 | 311 ms |
| 2 | EMU 車型相關的分類結構有哪些？ | rows=5 | 125 ms |
| 3 | 顯示最近一週的工單狀態（reportdate >= '2026-04-11'） | rows=5 | 85 ms |

- **優點**
  - 延遲低（<200ms），無 LLM 呼叫成本
  - 透過自訂 `retrieval_query` 可在向量召回後再做 Cypher 擴充（例如帶出關聯 Asset、SOP）→ **這就是 GraphRAG 的 sweet spot**
  - 結果帶 `score`，可與 Qdrant 結果對齊排序
- **缺點**
  - 只靠 embedding 相似度，對精準條件（例如「工單編號 = X」）容易漏判
  - 所有可查屬性必須預先 embed，schema 改動時要重算
  - 必須預建 vector index（dim 需與 embedder 一致）
- **適用場景**
  - 故障描述語意模糊查詢（"煞車異常" → 找近似工單）
  - 向量 + 圖結構混合：召回後用 Cypher pull 關聯上下文，直接餵給 Hermes fenced context

### 3.3 HybridRetriever

- **狀態**：works（3/3）
- **平均 latency**：97 ms
- **案例**：

| # | 問題 | 結果 | Latency |
|---|------|------|---------|
| 1 | 找車號 POC_EMU01 的所有工單 | rows=5 | 234 ms |
| 2 | EMU 車型相關的分類結構有哪些？ | rows=5 | 27 ms |
| 3 | 顯示最近一週的工單狀態 | rows=5 | 30 ms |

- **優點**
  - 最低延遲（~30ms 熱查詢），Vector + Fulltext 融合
  - 對中文關鍵字（"EMU01"、"煞車"）回歸 fulltext；對語意（"電聯車故障"）回歸向量
  - API 最簡單，只要指定兩個 index name
- **缺點**
  - 不支援自訂 `retrieval_query`（相比 VectorCypherRetriever），拿不到結構化關聯
  - 中文分詞預設不理想（Neo4j fulltext 用 standard analyzer，繁中會被分成單字），**需要改用 `cjk` analyzer**（W2-T2 時處理）
  - 結果是扁平 node，不帶圖結構 context
- **適用場景**
  - 純文字搜尋（文件內全文 + 向量），不需要多跳關聯
  - 當作 Vector/Text2Cypher 的 baseline 對照

---

## 4. 整合建議

### 4.1 推薦架構：VectorCypherRetriever 為主力 + Text2CypherRetriever 為補強

```
使用者 Query
  ├─ intent_classifier ─┐
  │                     ├─ 結構化意圖（"EMU01 的 PM 工單"）→ Text2CypherRetriever
  │                     └─ 模糊語意意圖（"最近煞車相關故障"）→ VectorCypherRetriever
  │                                                           (retrieval_query 帶出 Asset/SOP)
  └─ 結果合併 → Hermes fenced context → LLM answer
```

理由：
- **VectorCypherRetriever** 是 GraphRAG 的核心價值點：向量召回 + 圖結構擴充，延遲低且不花 LLM token
- **Text2CypherRetriever** 處理明確的結構化查詢（關聯、路徑、聚合），但貴且慢，要守門
- **HybridRetriever** 當 fallback/baseline，除非我們之後真的要做「純文字站內搜尋」才獨立用

### 4.2 接進現有 `services/rag.py` 的落點

- 新增 `services/graph_rag.py`：封裝 driver + retriever factory
- `services/rag.py::retrieve()` 在 Qdrant 召回之後，依 intent 判斷是否額外呼叫 graph_rag，結果以 fenced block（`<graph_context>...</graph_context>`）注入 prompt
- Token budget 沿用 Phase 2 的 tiktoken（≤ 1500 tokens）
- Circuit breaker：graph_rag 套現有 `circuit_breaker.py` pattern（Neo4j / LLM 各一個）

### 4.3 需要預先建的 index（正式 schema）

在既有 `init_schema.cypher` 追加：

| Index | Target | 理由 |
|-------|--------|------|
| `wo_desc_vec` | `WorkOrder.desc_embedding` (cosine, dim 根據 embedder) | VectorCypherRetriever 主索引 |
| `sr_desc_vec` | `ServiceRequest.desc_embedding` | 故障描述召回 |
| `cs_desc_vec` | `ClassStructure.desc_embedding` | 分類語意查詢 |
| `wo_description_fts` | `WorkOrder.description` with **cjk analyzer** | 中文 fulltext 必要 |
| `sr_description_fts` | `ServiceRequest.description` with cjk | 同上 |

> **注意**：目前 `init_schema.cypher` 的 fulltext index 沒設 analyzer，預設 standard 對繁中不佳。W2-T2 整合時要補 `OPTIONS {indexConfig: {'fulltext.analyzer': 'cjk'}}`。

### 4.4 Embedding 選型

- POC 用 `all-MiniLM-L6-v2`（dim 384）僅為自帶避免外部 API
- 正式應改為 config 內的 `qwen3-embedding`（dim 4096）以與 Qdrant 共用向量空間
  - 但要確認 Neo4j vector index 支援 dim=4096（Neo4j 5.20 上限 4096，OK）
  - 或者用 `text-embedding-3-small` (1536) 降成本
- 建議：**與 Qdrant 同一 embedder**，避免雙索引雙成本

---

## 5. 風險 & 對應

| 風險 | 嚴重度 | 對應 |
|------|--------|------|
| LLM 呼叫成本（Text2Cypher 每次 ~1–8s） | 中 | intent gate + Redis cache（query→cypher 快取 24h） |
| Cypher 注入 | 高 | 強制經 `cypher_validator.py`（已建）白名單 + 參數化 |
| Neo4j-graphrag lock openai<2.0 | 低 | 目前 codebase 相容 openai 1.x，持續觀察 upstream；若 instructor 真的需要可 pin |
| Docker image 重建時間 | 低 | 加進 requirements.txt 後 `--build` 走標準流程 |
| 繁中 fulltext analyzer | 中 | 建 index 時指定 cjk analyzer；W2-T2 時一併處理 |
| Vector index dim 一致性 | 中 | 強制 embedding 模型與 Qdrant 一致，用 config 中央管理 |
| Embedding 漂移（schema 改動要 reindex） | 低 | 建 nightly job 針對新增/修改節點重算（sync 用 updated_at） |

---

## 6. GO / NO-GO

- [x] **GO** — 進入 W2-T2 整合
- [ ] NEEDS-FIX
- [ ] RECONSIDER

### 理由
1. 套件裝起來可用，三個 retriever 全綠（9/9 case pass）
2. VectorCypherRetriever + Text2CypherRetriever 的 latency / 正確性符合預期
3. 與現有架構（Hermes fenced context、circuit breaker、cypher_validator）對接點明確
4. 依賴衝突（openai 降版）可接受，無功能阻斷
5. 清理機制驗證通過（`remain=0`），不污染正式 schema

### 下一步（W2-T2 建議）
1. `services/graph_rag.py`：Retriever factory + driver lifecycle
2. 擴充 `init_schema.cypher`：加 vector index（WorkOrder/SR/ClassStructure）+ cjk fulltext
3. `rag.py` 整合點：intent → graph_rag → fenced context
4. Redis 快取 Text2Cypher 結果
5. 加 `/health/circuits` 的 Neo4j-graphrag 檢測
