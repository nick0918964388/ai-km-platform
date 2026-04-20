# Phase 3 W3-T2 / W3-T3 Playwright 驗證報告

日期: 2026-04-19
驗證人員: Test Agent (Playwright MCP)
環境: 192.168.1.11:3000 (frontend) / 192.168.1.11:8000 (backend)
Admin 帳號: admin@example.com / admin
前置動作: 因 frontend container 早於 W3-T2/T3 commit 啟動，已先在 192.168.1.11 執行 `docker compose up -d --build frontend` 重建。

---

## W3-T2 迷你圖（GraphExpansionPanel 圖路徑 + MiniGraphView）

- [OK] 「🕸️ 圖路徑」區塊可見（顯示 count=5）
- [OK] 展開後 react-flow canvas 渲染（`.react-flow.light` 存在）
- [OK] 5 節點、4 連線（精確匹配規格）
- [OK] 節點 labels 正確：
  - `Query / 煞車異響查詢`
  - `FaultCode / 煞車異響 (F001)`
  - `SOP / BR-001 煞車診斷流程`
  - `WorkOrder / WO123456 (EMU01)`
  - `WorkOrder / WO123457 (EMU02)`
- [OK] 節點點擊 callback 成功觸發
  - Console log: `mini-graph node clicked: {id: wo1, type: WorkOrder, label: WO123456\n(EMU01)}`
- [OK] Zoom/Pan 控制按鈕 (+/−/fit) 顯示於左下角
- [OK] Edge 標籤正確顯示（MATCHES / REQUIRES / OCCURS_IN / IS_RELATED）
- 截圖：
  - `phase3-w3t2-minigraph-collapsed.png`
  - `phase3-w3t2-minigraph-expanded.png`

---

## W3-T3 Admin KG 監控頁（/admin/knowledge-graph）

- [OK] Admin 登入成功（自動帶入 session）
- [OK] Sidebar 有「知識圖譜」項目（`/admin/knowledge-graph`）
- [OK] 頁面六區塊齊全
  - 頁面標題「知識圖譜監控」+ `MOCK 資料` 黃色 badge
  - 區塊 1 總覽：4 卡（總節點數 19,225 / 總關係數 19,024 / Clean 覆蓋率 74.1% / 最近 ETL never）
  - 區塊 2 節點分佈：6 列（WorkOrder 7995 / Asset 10662 / ClassStructure 193 / ServiceRequest 375 / SOP 0 / Part 0）
  - 區塊 3 關係分佈：4 列（PERFORMED_ON / CLASSIFIED_AS / REPORTED_ON / PARENT_OF）
  - 區塊 4 稀疏實體：FaultCode FC-BRK-003 · 1 邊
  - 區塊 5 操作：「觸發 ETL Rebuild」按鈕可點
  - 區塊 6 ETL Log：pre tag 含 mock 紀錄
- [OK] MOCK 資料 badge 顯示
- [OK] Rebuild 按鈕 stub 回應
  - 訊息：`queued: W1-T3 ETL 尚未實作，此為 stub 回應。full=false (job=mock-job-20260418-120000)`
- [OK] RWD 通過
  - 375×812 手機：sidebar 收合、4 卡垂直堆疊、可讀
  - 1440×900 桌機：sidebar + 主區塊左右配置正常
- [OK] 非 admin 存取被擋
  - 清除 cookie 後 navigate `/admin/knowledge-graph` → 自動 redirect 到 `/login`
  - API 直打 `/api/admin/kg/stats`（無 Authorization header）→ HTTP 403
- 截圖：
  - `phase3-w3t3-admin-overview.png`
  - `phase3-w3t3-rebuild-clicked.png`
  - `phase3-w3t3-mobile.png`
  - `phase3-w3t3-desktop.png`
  - `phase3-w3t3-redirect-to-login.png`

---

## 發現的 issue

1. (INFO / 非阻塞) 部署機 frontend container 此次驗證前未包含 d576beb (W3-T2) 與 52332fd (W3-T3) 程式碼，需要重建。建議將 frontend build 納入 CI/CD 流程，或在 merge 後自動觸發 `docker compose up -d --build frontend`，避免 reviewer 驗證時看到舊版。
2. (MINOR) 節點分佈裡 SOP / Part 為 0，符合目前 mock 規格，但 W3-T2 的圖展示中有 SOP 節點，前後稍有語義落差；W1-T3 真 ETL 上線後會一併解決，此處只做備註。
3. (MINOR) admin 頁在 sidebar 上的高亮項目名稱「知識圖譜」與頁面標題「知識圖譜監控」略有不同，不影響功能。

---

## GO / NO-GO

**GO** — W3-T2 迷你圖與 W3-T3 Admin KG 監控頁兩個功能皆達交付標準：

- 迷你圖視覺化正確、互動 callback 正常、mock 資料結構 5 節點 4 連線符合規格
- Admin 監控頁六區塊齊全、MOCK badge 清楚標示、Rebuild stub 回應正常、RWD 通過、權限保護有效（頁面 redirect 到 login、API 回 403）
