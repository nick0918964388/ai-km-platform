# E2E Browser Validation

用瀏覽器對前端進行合理性驗證測試。

## 步驟

1. **確認服務狀態**：檢查 backend (port 8000) 和 frontend (port 3000) 是否正在運行
   - 如果沒有運行，先啟動：
     - Backend: `cd backend && ./venv/bin/uvicorn app.main:app --reload &`
     - Frontend: `cd frontend && npm run dev &`
   - 等待服務啟動完成

2. **首頁驗證**：
   - 開啟 http://localhost:3000
   - 確認頁面正確載入（無白屏、無 JS 錯誤）
   - 截圖記錄

3. **對話功能驗證**：
   - 確認聊天界面正確顯示
   - 嘗試發送一則測試訊息
   - 確認回應正常（SSE streaming）

4. **個人資料頁面驗證**：
   - 導航至 /profile
   - 確認 ProfileForm 正確載入
   - 確認顯示名稱欄位可編輯
   - 確認帳號等級欄位顯示
   - 截圖記錄

5. **儀表板驗證**：
   - 導航至 /dashboard
   - 確認 MetricsCard 元件正確顯示
   - 確認 ActivityTimeline 元件存在
   - 確認 TopTopics 元件存在
   - 確認無 loading 卡住的狀態
   - 截圖記錄

6. **響應式設計驗證**：
   - 調整視窗大小至手機尺寸 (375px)
   - 確認 layout 正確響應
   - 截圖記錄

7. **側邊欄導航驗證**：
   - 確認側邊欄有 Profile 和 Dashboard 連結
   - 點擊導航連結確認正確跳轉

8. **總結報告**：
   - 列出所有通過/失敗的測試項目
   - 附上截圖
   - 提出發現的問題和建議修復方案

## 注意事項
- 使用 Playwright MCP 或瀏覽器工具進行測試
- 每個步驟都要截圖作為證據
- 如果遇到錯誤，記錄完整的錯誤訊息
- 測試完成後整理成結構化報告
