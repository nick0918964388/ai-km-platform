# Plan - Chat Enhancement

## Implementation Plan

### Feature 1: Source Preview Modal

**SourcePreview.tsx** - 完整重寫：
1. 新增 `isOpen` state 控制 Modal
2. 根據 `documentName` 副檔名判斷類型（.pdf / .docx / .xlsx / .jpg/.png 等）
3. Modal 使用 `position: fixed` overlay + Portal
4. PDF → `<iframe src={fileUrl}>`
5. Word/Excel → `<iframe src="https://docs.google.com/viewer?url={encodeURIComponent(absoluteUrl)}&embedded=true">`
6. Image → `<img src={fileUrl}>`
7. ESC 鍵關閉、點背景關閉

### Feature 2: Similarity Score

**ChatWindow.tsx** - 來源區塊修改：
1. 在每個 source item 中新增 score 顯示
2. 新增 `getScoreColor()` helper function
3. 進度條使用 `div` + `width: ${score*100}%` + 背景色

### Feature 3: Follow-up Questions

**Backend (rag.py)**:
1. 新增 `generate_follow_up_questions(query, answer, sources)` function
2. 使用 gpt-4o 生成 2-3 個引導問題
3. 返回 list[str]

**Backend (chat.py)**:
1. 在 streaming 的 `done` event 之前，呼叫 follow-up generation
2. 新增 SSE event type: `{"type": "follow_up", "data": ["q1", "q2", "q3"]}`

**Frontend (ChatWindow.tsx)**:
1. 新增 `messageFollowUps` state: `{[messageId]: string[]}`
2. 解析 `follow_up` SSE event
3. 在 message 底部（metadata 之後）渲染 follow-up 按鈕
4. 點擊 → `setInput(question)` → `handleSend()`
