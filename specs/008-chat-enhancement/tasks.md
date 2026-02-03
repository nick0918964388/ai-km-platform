# Tasks - Chat Enhancement

## Task List

- [x] T1: Rewrite `SourcePreview.tsx` with Modal preview
- [x] T2: Add similarity score visualization to `ChatWindow.tsx` source section
- [x] T3: Add `generate_follow_up_questions()` to `rag.py` (already existed)
- [x] T4: Add `follow_up` SSE event to `chat.py` streaming endpoint (already existed)
- [x] T5: Add follow-up questions UI to `ChatWindow.tsx`
- [x] T6: Integration test - backend API verified working

## Completion Notes

### Feature 1: Source Preview Modal
- PDF: iframe 直接嵌入
- Word/Excel: Google Docs Viewer
- Image: img 直接顯示
- 支援 ESC 關閉、點擊背景關閉

### Feature 2: Similarity Score
- 顯示百分比 + 進度條
- 顏色編碼：綠(>80%)、黃(50-80%)、紅(<50%)

### Feature 3: Follow-up Questions
- Backend: gpt-4o-mini 生成 2-3 個引導問題
- Frontend: pill button 樣式，點擊後自動送出
- SSE event: `{"type": "follow_up", "data": ["q1", "q2", "q3"]}`
