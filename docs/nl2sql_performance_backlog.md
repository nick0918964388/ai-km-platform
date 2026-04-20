# NL→SQL 效能優化 Backlog

> 建立日期：2026-04-19 · 基準報告：`docs/nl2sql_latency_report_2026-04-18.md`

## 已完成（2026-04-18 Quick Wins，commit 773a222 / e147951 / 9b5e389）

- ✅ **A** Intent few-shot 10→4（system prompt -74%，省 0.5-1s/call）
- ✅ **B** Schema embedding 2→1 次（省 0.3-0.5s/call）
- ✅ **C** SQL 語意快取（Qdrant 0.95 threshold，命中省 4s）
- ✅ **D** Embedding 硬編碼修正（改走 config，實際走 Ollama 本地）

**成效**：首次查詢 6-7s → 冷啟動 3-4s / 重複查詢 2-3s。

---

## 下一批（本 session 已授權）

### 🔥 Batch 2-A：Hybrid decompose 平行化
- **現況**：hybrid 查詢 90+秒（BGE reranker 17.5s + 2 sub SQL 各 20s 序列 + self-reflection 重試）
- **修法**：
  - Sub SQL 平行跑（`asyncio.gather`）
  - Hybrid 路徑 disable self-reflection 重試（cap retries = 0）
  - ✅ **BGE reranker：改 Ollama GPU（已完成 2026-04-19）**
- **預估**：90s → 15-20s（-80%）

#### Reranker 升級：BGE CPU → Ollama GPU（✅ 2026-04-19）
- **實作**：`backend/app/services/reranker_ollama.py` — 透過 Ollama `/api/embed`
  批次取 query+docs embedding，cosine similarity 當 score，單次 HTTP call。
- **模型**：`linux6200/bge-reranker-v2-m3:latest`（keep_alive=-1 熱載入 GPU）
- **實測（20 docs top_n=5）**：BGE CPU 17500ms → Ollama GPU **1603ms（~10.9x 加速）**
- **Factory 策略**：`RERANKER_PROVIDER=ollama`；auto 模式順序改 Cohere → Ollama → BGE
- **fallback chain**：主 provider 失敗 → 依序嘗試其他可用 provider
- **測試**：14 unit tests + 1 integration test（真實 Ollama endpoint，< 3s 通過）

### 🔥 Batch 2-B：Self-Reflection 閾值調優
- **現況**：品質低才 retry 但閾值偏低常觸發，每次 +2-3s
- **修法**：
  - 提高 confidence 閾值
  - SQL validator 通過 → skip reflection
  - 僅明顯錯誤（SQL syntax error / schema mismatch）才 retry
- **預估**：平均每次省 1-2s

### 🔥 Batch 2-C：SQL Generation 改 NVIDIA minimax
- **現況**：Sonnet 4.6 + 龐大 schema prompt，3.5-4.5s/call（cache miss）
- **修法**：改用 NVIDIA `minimaxai/minimax-m2.7`（記憶體顯示 ~0.5s/call）
- **風險**：SQL 品質可能下降，需用 20 題 benchmark 驗證 
- **預估**：省 3s/call，但若品質掉要 rollback

---

## 未來 Backlog（本 session 未做，之後可做）

### 🟡 中影響

#### Backlog #1：Speculative Execution 真平行化
- **問題**：Pattern 1 設計是 intent + schema 平行，但 intent 2s 永遠比 schema 慢，實際平行度幾乎 0
- **方案**：
  - Intent + Schema + 第一版 SQL 三層真平行（SQL 用 speculative pre-generate）
  - SQL speculative 若判斷失誤要捨棄重生（白做工風險）
- **複雜度**：中高（要設計 speculative fallback logic）
- **預估**：省 1-2s

#### Backlog #2：Redis + Qdrant Cache 優化
- **問題**：目前 Redis MD5 優先，miss 才查 Qdrant；Redis 已命中是否仍要驗證 schema 沒飄？
- **方案**：
  - Redis hit 直接返回不再驗證（現在可能已是如此）
  - Qdrant semantic hit 先跑 schema diff 確認 columns 相容才回
  - 雙層 TTL（Redis 短、Qdrant 長）
- **預估**：邊際效益小，但預防語意 cache 誤命中

#### Backlog #3：Intent 改 Local Small Model
- **問題**：Haiku LLM call 本身 1.8-2.4s（網路+推理）
- **方案**：改用 local Ollama small model（gemma-2b 或 phi-3-mini），預期 < 0.5s
- **風險**：意圖分類品質可能下降，需評估
- **預估**：省 1.3-2s

### 🟢 小影響 / 體驗改善

#### Backlog #4：SQL 流式輸出（perceived speed）
- **問題**：SQL gen 3-4s 使用者乾等
- **方案**：SQL 逐字 token stream 顯示在 debug/UI
- **效益**：不減總時間，但感覺快 + 提前 debug

#### Backlog #5：Frontend SSE 渲染優化
- **問題**：Chat 訊息累積多時 render 可能卡
- **方案**：React.memo / virtual scroll（react-window）
- **預估**：視訊息量

#### Backlog #6：Conversation 載入優化
- **問題**：開 chat 頁載入歷史對話可能慢（視資料量）
- **方案**：分頁載入 + skeleton loading
- **預估**：視訊息量

#### Backlog #7：Circuit Breaker 預熱
- **問題**：啟動後第一次呼叫各 service 可能多一點延遲
- **方案**：啟動時 ping 一輪
- **預估**：僅首次影響，整體小

#### Backlog #8：Schema 查詢結果快取
- **問題**：同 query 可能重複觸發 schema 檢索
- **方案**：短期 LRU cache（key = embedding vector hash）
- **預估**：5-10% 命中率，小幅省時

---

## 決策點

- 若 Batch 2 結束後延遲仍 > 3s，考慮 Backlog #1（Speculative 真平行）
- 若 intent 仍是瓶頸，考慮 Backlog #3（local small model）
- Frontend backlog 視使用者反映延後處理

---

## 🛡️ 安全性 Backlog（非效能，但需排程）

### Security #1：輸入層 Guardrail（Topic Classifier + Jailbreak Detector）
- **問題**：使用者可問「天氣」「股價」等 off-topic 問題浪費 LLM 成本；也可能嘗試 prompt injection（「忽略之前指令…」）
- **方案**：
  - Topic Classifier 判斷是否屬於 work_order/fault/asset/sop/maintenance 領域，否則婉拒
  - Jailbreak 偵測器（regex + 小模型）擋經典 injection patterns
- **預估**：半天 ~ 1 天

### Security #2：System Prompt 強化
- 每個 LLM call 的 system prompt 開頭加領域限制 + refusal template
- **預估**：半天

### Security #3：Output Scanner
- LLM 結果掃 regex：密碼 / token / 信用卡號 / 內部 IP
- **預估**：半天

### Security #4：SQL Row-level Policy 強化
- Validator 目前擋 DDL/DML 沒問題，但跨 tenant 越權查詢（SELECT * FROM users）需補 row-level policy
- **預估**：1 天

### Security #5：Rate Limiting + 告警
- 同使用者 5 分鐘 3 次被拒絕 → notify admin
- 每使用者 RPS 上限
- **預估**：1 天

**決策**：使用者選 (C) — Batch 2 驗證完再規劃安全性工作。
