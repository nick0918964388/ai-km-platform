# Phase 3：Knowledge Graph 實作計畫

> 版本：v1.0 · 建立日期：2026-04-18 · 狀態：計畫確認中
> 相關 memory：`~/.claude/projects/.../memory/project_knowledge_graph_plan.md`

## 0. 架構決策摘要

| 項目 | 決定 |
|------|------|
| 圖資料庫 | **Neo4j 5.20 Community**（APOC + GDS 插件） |
| 向量檢索 | **Qdrant 不動**（繼續處理文件 chunks） |
| Source of truth | **PostgreSQL**（Maximo 原始資料，Neo4j 為投影） |
| GraphRAG 框架 | **`neo4j-graphrag-python`**（官方 library，非重框架） |
| 整合點 | `services/rag.py`（合併 Qdrant + Neo4j → Hermes fenced context） |
| 同步策略 | Nightly full rebuild + 增量 CDC |
| LLM token 預算 | 單次 GraphRAG 擴充 ≤ 1500 tokens（沿用 Phase 2 tiktoken） |

---

## 1. Agent Team 分工協議

依 CLAUDE.md 規範，每項 Implementation Task 完成後觸發 Review + Test：

```
┌──────────────────────────────────────────────────────────┐
│  Implementation Agents（可平行）                           │
│   ├─ Backend Agent（Python / SQL / Cypher / Docker）      │
│   └─ Frontend Agent（Next.js / React / UI components）    │
│                      ↓                                    │
│  Review Agent（安全、正確性、架構、SQL/Cypher 注入）       │
│                      ↓（HIGH/CRITICAL 問題必修）           │
│  Test Agent                                               │
│   ├─ API curl 測試                                        │
│   └─ Playwright 視覺驗證（UI 改動必跑）                    │
│                      ↓                                    │
│  部署到 192.168.1.11（SSH + docker compose up --build）    │
└──────────────────────────────────────────────────────────┘
```

---

## 2. Week 0：資料準備（必做，不可省）

### W0-T1：Maximo 資料品質健檢報告
- **Agent**：Backend
- **工作內容**：
  - SSH 進 192.168.1.11 讀 `aikm-postgres`
  - 對 `trc_mxwo` / `trc_mxasset` / `trc_mxsr` / `maximo_zz_domain` / `maximo_zz_alndomain` 跑品質統計
  - 指標：orphan FaultCode 率、空值率、重複實體率、時間異常（未來日期、1900 年）、中文翻譯覆蓋率、parent-key 循環偵測
- **產出**：`docs/kg_data_quality_report.md`（含數據摘要 + 問題清單 + 建議處理）
- **Acceptance**：
  - 報告覆蓋 6 類指標，每類附 SQL 範例
  - 清楚標示「立即修復 / 可接受 / 需後續處理」三級
- **E2E**：N/A（純報表，無 UI）

### W0-T2：資料清理腳本
- **Agent**：Backend
- **工作內容**：`backend/scripts/clean_maximo_data.py`
  - Normalize FaultCode 格式（大小寫、空白、特殊字元）
  - Dedupe assets by serial + model
  - Fill 中文翻譯 via `domain_mapper`
  - 建 `kg_alias` 表處理已知同義詞
- **產出**：腳本 + dry-run 報告（改動前後 diff）
- **Acceptance**：
  - `--dry-run` 模式 100% 可重現
  - 所有改動寫進 `kg_clean_log` 表供稽核
  - 可 rollback（用 transaction + backup）
- **Review 重點**：SQL 注入防護、交易完整性
- **E2E**：API 層寫 pytest（不動 UI）

### W0-T3：基準資料集篩選
- **Agent**：Backend
- **工作內容**：
  - 定義 clean subset 條件：`WO.fault_code IS NOT NULL AND WO.asset_id IS NOT NULL AND LENGTH(WO.description) > 10`
  - 建 `kg_source_workorders` VIEW
  - 計算覆蓋率報告（clean vs dirty 比率）
- **產出**：VIEW + 覆蓋率報告
- **Acceptance**：clean subset 至少 3,000 筆工單（若不足，與使用者確認降低門檻）
- **E2E**：N/A

---

## 3. Week 1：Neo4j 基礎建設

### W1-T1：Neo4j Docker 服務上線
- **Agent**：Backend（infra）
- **工作內容**：
  - 更新 `docker-compose.yml` 加 `aikm-neo4j`
  - 設定 APOC + GDS 插件
  - 設 memory heap 2G、page cache 1G
  - 開 port 7474（browser）+ 7687（bolt）
  - `.env` 加 `NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD`
- **Acceptance**：
  - `docker compose up -d neo4j` 正常啟動
  - Browser `http://192.168.1.11:7474` 可登入
  - `CALL apoc.help("apoc")` 與 `CALL gds.list()` 都有回應
- **Review 重點**：密碼強度、port 暴露範圍、backup volume
- **E2E**：API health check `GET /health/circuits`（新增 Neo4j 斷路器）

### W1-T2：Graph Schema + Index + Constraint
- **Agent**：Backend
- **工作內容**：`backend/scripts/init_neo4j_schema.cypher`
  - 6 類節點：WorkOrder / FaultCode / Asset / SOP / Part / Technician
  - 8 類關係：PERFORMED_ON, CAUSED_BY, USED_PART, FOLLOWED_SOP, PERFORMED_BY, PARENT_OF (FaultCode), TYPICALLY_REQUIRES, LOCATED_AT
  - 每類節點主鍵 unique constraint
  - 常用查詢欄位建 index（WO.created_at、FaultCode.code 等）
- **Acceptance**：`SHOW CONSTRAINTS` 與 `SHOW INDEXES` 結果符合預期
- **E2E**：pytest 驗證 schema 建立成功

### W1-T3：Postgres → Neo4j ETL
- **Agent**：Backend
- **工作內容**：`backend/scripts/build_graph_neo4j.py`
  - 從 `kg_source_workorders` 讀 clean subset
  - 用 `apoc.periodic.iterate` 批次 MERGE（每批 1000 筆）
  - 加邊 decay 權重（`exp(-days_ago / 365)`）
  - 進度條 + 錯誤記錄到 `kg_etl_errors`
  - 支援 `--full-rebuild` 與 `--incremental` 兩模式
- **Acceptance**：
  - Full rebuild < 10 分鐘（10 萬筆邊）
  - 增量更新 < 1 分鐘（100 筆新工單）
  - 重跑結果一致（idempotent）
- **Review 重點**：MERGE 效能、記憶體使用、錯誤處理
- **E2E**：pytest + 資料量驗證查詢

### W1-T4：graph_service.py 基礎查詢封裝
- **Agent**：Backend
- **工作內容**：`backend/app/services/graph_service.py`
  - `neighbors(entity_id, depth, types)`
  - `top_related(entity_id, rel_type, limit=3)`
  - `shortest_path(src, dst, max_depth=5)`
  - `similar_cases(wo_id, limit=3)` — 核心業務查詢
  - `recommended_sops(fault_code_id)` — 核心業務查詢
  - 內建 Circuit Breaker（沿用 `circuit_breaker.py`）
- **Acceptance**：
  - 單元測試覆蓋 5 個核心方法
  - 每個方法平均回應時間 < 100ms（索引設對的前提下）
- **Review 重點**：Cypher 參數化、depth limit、read-only role

---

## 4. Week 2：GraphRAG 整合

### W2-T1：安裝與評估 `neo4j-graphrag-python`
- **Agent**：Backend
- **工作內容**：
  - `requirements.txt` 加 `neo4j-graphrag`
  - 實作 POC：`Text2CypherRetriever` + `VectorCypherRetriever` + `HybridRetriever`
  - 寫 benchmark：10 個典型問題，比對 retriever 品質
- **產出**：`docs/graphrag_poc_notes.md` + POC 測試腳本
- **Acceptance**：至少 2 個 retriever 達可用品質

### W2-T2：整合進 services/rag.py
- **Agent**：Backend
- **工作內容**：
  - 在現有 RAG pipeline 插入 entity linking 步驟
  - 做圖擴充：從 Qdrant chunk 識別實體 → Neo4j 擴展 → 合併到 Hermes fenced context
  - 遵守 tiktoken budget：圖擴充 context ≤ 1500 tokens
  - SSE 事件加 `graph_expansion` step（供 UI 顯示）
- **Acceptance**：
  - 既有 RAG 測試 100% 通過（不能破壞現有功能）
  - 新增 graph_expansion 單元測試
  - Token budget 違規時降級（純 RAG）
- **Review 重點**：context injection 安全、fallback 邏輯
- **E2E**：API curl 測試，比對 with/without graph 的回覆品質

### W2-T3：Cypher 安全稽核層
- **Agent**：Backend
- **工作內容**：`backend/app/services/cypher_validator.py`
  - 白名單：只允許 MATCH / RETURN / WHERE / WITH / ORDER BY / LIMIT
  - 禁止：CREATE / DELETE / DETACH / MERGE / SET / REMOVE / CALL（除了白名單 APOC）
  - 強制 LIMIT（預設 50）
  - 強制 max_depth（預設 5）
  - 所有查詢走 read-only user
- **Acceptance**：
  - 注入測試 20 個 payload 全部 block
  - 正常查詢 100% pass
- **Review 重點**：繞過測試（正則強度、關鍵字變形）

---

## 5. Week 3：UI + 驗證

### W3-T1：Chat 答案下方圖擴展面板
- **Agent**：Frontend
- **工作內容**：
  - 新 component `GraphExpansionPanel.tsx`
  - 三區：🔗 相關工單（top 3）/ 📋 建議 SOP（top 3）/ 🔧 常用零件（top 3）
  - 單跳預設顯示，「查看更多」逐層展開
  - Hover tooltip 顯示邊權重 + 信心 + 來源 WO IDs
  - 風格延續 Explore Mode 可收合卡片設計
- **Acceptance**：
  - RWD 在手機/平板/桌機都正常
  - 無資料時優雅隱藏（不顯空殼）
  - Loading state 用 Skeleton
- **E2E**：Playwright 測試「輸入故障描述 → 看到相關工單 → 點擊展開更多」

### W3-T2：可視化 — 圖路徑迷你視圖
- **Agent**：Frontend
- **工作內容**：
  - Message 中展開「可解釋性」區塊時，用 D3.js 或 react-flow 畫 3-5 節點的小圖
  - 節點可點擊 → popup 顯示實體詳情
  - 可選：嵌入 Neo4j Bloom iframe（admin only）
- **Acceptance**：
  - 單頁不超過 200KB 新增 JS
  - 繪製時間 < 200ms（5 節點）
- **E2E**：Playwright 截圖驗證

### W3-T3：Admin 圖品質監控頁
- **Agent**：Backend + Frontend
- **工作內容**：
  - 新 API `GET /api/admin/kg/stats` — 節點數、邊數、覆蓋率、稀疏 FaultCode 清單
  - 新 API `POST /api/admin/kg/rebuild` — 手動觸發 rebuild
  - Admin 頁新 tab「知識圖譜」顯示統計 + rebuild 按鈕 + ETL log tail
- **Acceptance**：只有 `admin` role 可存取
- **Review 重點**：權限、rebuild 防重入（lock）
- **E2E**：Playwright 權限測試（非 admin 看不到）

### W3-T4：A/B Eval 腳本 + 報告
- **Agent**：Backend
- **工作內容**：`backend/scripts/kg_ab_eval.py`
  - 抓 20 筆歷史工單的 description 當 query
  - 同時跑 Qdrant-only 與 Qdrant+Neo4j 兩種 pipeline
  - 用 LLM-as-judge 評分（相關性、完整性、可操作性）
  - 輸出 `docs/kg_ab_eval_report.md`
- **Acceptance**：至少 3/5 維度 Qdrant+Neo4j ≥ Qdrant-only

### W3-T5：部署 + 遷移 runbook
- **Agent**：Backend
- **工作內容**：
  - SSH 192.168.1.11，`docker compose up -d --build backend frontend neo4j`
  - 初始化 schema + 跑 ETL
  - Smoke test：chat 問「EMU900 煞車異響」看有無圖擴展回覆
  - 寫 `docs/phase3_deployment_runbook.md`（含 rollback 步驟）
- **Acceptance**：health check 全綠、E2E 31 tests 全過

---

## 6. Week 4（選配）：進階圖演算法

### W4-T1：PageRank 核心實體識別
- 識別「最中心的故障代碼」「最關鍵的 SOP」→ 輔助稀疏資料補全

### W4-T2：Leiden 社群偵測
- 找「常一起出現的故障/SOP/零件組合」→ 推薦 BOM

### W4-T3：路徑相似度推薦
- 對比新工單與歷史工單的處理路徑相似度

---

## 7. E2E 測試覆蓋總覽

沿用現有 Playwright 架構，新增測試集 `e2e/kg-regression.spec.ts`：

| 測試項 | 覆蓋 | 對應 W#-T# |
|--------|------|-----------|
| Neo4j health check | API | W1-T1 |
| Schema 建立 | API | W1-T2 |
| Chat 回覆含圖擴展區塊 | UI | W2-T2, W3-T1 |
| 點擊「查看更多」逐層展開 | UI | W3-T1 |
| 圖視覺化渲染 | UI | W3-T2 |
| Admin 圖統計頁權限 | UI | W3-T3 |
| Cypher 注入防護 | API | W2-T3 |
| Graph 斷路器 fallback | API | W2-T2 |

**目標**：Phase 3 完成後 E2E 從 31 tests → 40+ tests 全過。

---

## 8. Rollback 計畫

| 層級 | Rollback 動作 |
|------|--------------|
| Schema 錯誤 | `DROP CONSTRAINT` + `DROP INDEX`，重跑 init |
| ETL 資料錯誤 | Neo4j DB 整個 drop 重建（Postgres 是 source of truth） |
| 整合錯誤 | `rag.py` 加 feature flag `ENABLE_GRAPH_EXPANSION=false` 即時關閉 |
| 容器壞掉 | `docker compose down neo4j && docker compose up -d neo4j` |
| 整個 Phase 3 回滾 | Revert PR + 把 `aikm-neo4j` 從 docker-compose.yml 移除 |

---

## 9. 風險對策（摘要，細節見 memory）

- **R1 資料品質** → Week 0 先做健檢 + 清理 + 入圖閘門
- **R2 冷啟動** → MVP 只用 explicit 邊，Phase 3.2 再加 LLM retro-fill
- **R3 UX** → 單跳預設 + 逐層展開，Week 3 A/B test 兩種模式

---

## 10. 決策點

| 里程碑 | 需要使用者確認 |
|--------|---------------|
| W0-T1 報告完成 | 資料品質是否可進入 W1？（若 clean subset < 3000 筆需調整） |
| W1-T3 ETL 完成 | 實際邊數 vs 預估差異大 → 是否調整 Neo4j memory |
| W2-T1 POC 完成 | 選用哪個 retriever 作主 pipeline |
| W3-T4 A/B eval 結果 | KG 是否顯著優於 baseline → 決定是否正式發布 |
