# Phase 3 批次部署 + Playwright 驗證報告
日期: 2026-04-18

## 部署摘要
- 部署 commit: `9a19ee6` (HEAD of feat/dashboard-domain-e2e)
- 部署範圍: 4 commits
  - `ed75c68` — W2-T3 Cypher validator 修復
  - `11305a6` — W1-T4 graph_service.py 骨架 + neo4j driver
  - `47f6998` — W3-T1 Chat UI 圖擴展面板
  - `9a19ee6` — W2-T1 neo4j-graphrag lib POC
- Rollback 基準 commit: `229947b`（本次未觸發 rollback）
- Backend rebuild: OK（157.5s pip install，全部依賴成功安裝，openai 降版至 1.109.1 如預期）
- Frontend rebuild: OK（cached layers 加速，無 build error）
- Rollback 是否觸發: 否

### Build 中的關鍵觀察
- `openai-1.109.1`（符合預期降版）
- `neo4j-6.1.0`, `neo4j-graphrag-1.14.1`（新依賴）
- 既有 qdrant client 1.17.1 vs server 1.12.5 版本不匹配警告（既有問題，非本次部署造成）
- Frontend build 通過，未出現阻塞性 TypeScript error

## Health Check
- `/health`: `{"status":"healthy"}` ✅
- `/health/circuits`: llm/qdrant/redis 全部 `state: closed` ✅
- Frontend `/`: HTTP 200 ✅
- Container 狀態:
  - `aikm-backend`: Up (healthy)
  - `aikm-frontend`: Up (health: starting → running)
  - `aikm-neo4j`: Up 4 hours (healthy) — 未動
  - `aikm-postgres`: Up 8 days (healthy) — 未動
  - `aikm-redis`: Up 9 days (healthy) — 未動
  - `aikm-qdrant`: Up 3 days (unhealthy) — 既有狀態，非本次造成

## Playwright 視覺驗證
- 三個區塊顯示正確: OK
  - 🔗 相關工單 (3)
  - 📋 建議 SOP (3)
  - 🔧 常用零件 (3)
- 「🕸️ 知識圖譜擴展」標題存在且顯示
- 收合/展開動作: OK
  - 預設 collapsed 狀態 (▶ icon)
  - 點擊後展開顯示工單列表（W0123456 EMU01 煞車異響，相似 92%）
- RWD 三斷點:
  - 375px (mobile): OK — 垂直堆疊排列
  - 768px (tablet): OK — 垂直堆疊排列（chat 寬度有限）
  - 1440px (desktop): OK — 三區塊並排 grid layout
- Feature flag OFF 時隱藏: OK
  - 無 `?enableGraph=1` 時，「知識圖譜擴展」「相關工單」「建議 SOP」「常用零件」四關鍵字在 DOM 中均不存在

## 截圖
Playwright 輸出於 Mac Mini 本機：
- `phase3-graph-expansion-collapsed.png` — 桌機收合狀態全頁
- `phase3-graph-expansion-wo-expanded.png` — 展開「相關工單」
- `phase3-graph-expansion-mobile.png` — 手機 375px 全頁
- `phase3-graph-expansion-mobile-panel.png` — 手機面板特寫
- `phase3-graph-expansion-tablet.png` — 平板 768px
- `phase3-graph-expansion-desktop.png` — 桌機 1440px（panel 聚焦）
- `phase3-graph-expansion-flag-off.png` — flag OFF 畫面

## Regression 抽查
- Chat 主路徑: OK — 既有對話歷史正常載入與顯示
- 歷史 assistant 回應的 Markdown 渲染（heading、list、表格）: OK
- Feedback 按鈕（👍👎 及「這個回答是否有幫助？」）: OK，仍存在於每則回應下方
- 輸入框、模型選擇器（claude-sonnet-4-6）、語音輸入、附件按鈕: OK
- 側邊欄導航（AI 問答 / 查詢紀錄 / 管理員 / 系統設定 / 個人資料）: OK

## 發現的問題（非本次造成，記錄待處理）
1. Conversations FTS migration 在 startup 出現 `syntax error at or near "RETURN"` — asyncpg driver 無法執行 PL/pgSQL 函數 body。非本次 commits 造成（既有），但應修正。
2. `aikm-qdrant` 容器 health: unhealthy（Up 3 days）— 既有問題。qdrant client 1.17.1 與 server 1.12.5 版本不匹配警告。

## GO / NO-GO
**GO** — 本次 Phase 3 部署全部驗證通過：
- Backend + Frontend rebuild + up 成功
- 所有 circuit breakers closed
- Feature flag 行為正確（ON 顯示、OFF 完全隱藏）
- 三個區塊 UI 呈現 + 展開動作 + RWD 三斷點全綠
- 主路徑無 regression
