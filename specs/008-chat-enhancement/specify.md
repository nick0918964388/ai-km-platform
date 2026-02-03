# Specification - Chat Enhancement

## Feature 1: Source Document Preview (Modal)

### Requirements
- 點擊「預覽原檔」按鈕時，開啟 Modal 彈窗（非下載/新分頁）
- 根據檔案類型選擇預覽方式：
  - **PDF**: `<iframe>` 嵌入顯示
  - **Word/Excel**: Google Docs Viewer (`https://docs.google.com/viewer?url=`)
  - **Image**: `<img>` 直接顯示
- Modal 需有關閉按鈕、點擊背景關閉
- 需顯示文件名稱作為 Modal 標題

### File Changes
- `frontend/src/components/chat/SourcePreview.tsx` - 完整重寫

---

## Feature 2: Similarity Score Visualization

### Requirements
- 後端已回傳 `score` 欄位（0-1 浮點數）
- 前端來源文件區塊顯示：
  - 相似度百分比文字（如 "85%"）
  - 視覺化進度條
  - 顏色編碼：
    - >0.8: 綠色 (#24a148)
    - 0.5-0.8: 黃色 (#f1c21b)
    - <0.5: 紅色 (#da1e28)

### File Changes
- `frontend/src/components/chat/ChatWindow.tsx` - 來源文件區塊新增分數顯示

---

## Feature 3: Follow-up Questions

### Requirements

#### Backend
- 在 streaming 回應完成後，額外呼叫 LLM 生成 2-3 個引導問題
- 透過新的 SSE event type `follow_up` 傳送
- Prompt: 基於使用者問題和回答內容，生成相關的後續問題

#### Frontend
- 在回答末尾顯示引導問題按鈕
- 點擊後自動填入輸入框並送出
- 視覺風格：類似首頁建議問題的 pill button

### File Changes
- `backend/app/routers/chat.py` - 新增 follow-up generation
- `backend/app/services/rag.py` - 新增 generate_follow_up_questions()
- `frontend/src/components/chat/ChatWindow.tsx` - 新增 follow-up UI
