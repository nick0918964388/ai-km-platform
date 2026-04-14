# E2E Test Report — 2026-04-14

## Test Environment
- Frontend: http://192.168.1.11:3000
- Backend: http://192.168.1.11:8000
- LLM: gemma4:31b-cloud (ollama.webtw.xyz) + llama3.2:3b (intent)
- Tool: Playwright MCP

---

## Test 1: Job-based Chat Flow + SQL Query

### Steps
1. Navigate to http://192.168.1.11:3000/chat
2. Click "📊 EMU900 車輛狀態" quick button
3. Wait for clarification → click "直接搜尋，跳過釐清"
4. Wait for SQL result

### Expected
- Clarification options appear (全車隊資產總覽, 特定車號故障紀錄, 車輛維修成本排名)
- After skip → intent detection → SQL generation → result table with badges

### Result: ✅ PASS
- SQL result: OPERATING 26, NOT READY 26 (2筆, 95%)
- Step progress displayed dynamically

---

## Test 2: History Navigation + Result Persistence

### Steps
1. After Test 1, click "查詢紀錄" in sidebar
2. Find the "EMU900 車輛狀態" conversation at top
3. Click to navigate back to chat

### Expected
- Correct conversation loaded (not new chat)
- SQL result card displayed with table + badges

### Result: ✅ PASS
- Navigated to correct conversation via URL param
- SQL result card fully restored from localStorage

---

## Test 3: Job Recovery After Page Navigation

### Steps
1. Click "新對話"
2. Type "核簽中的工單有哪些？列出前10筆" and send
3. Wait 1 second (job just started), then navigate to Dashboard
4. Wait 15 seconds on Dashboard
5. Navigate to 查詢紀錄
6. Click the latest conversation to return to chat

### Expected
- Backend job continues processing while on Dashboard
- Returning to chat shows completed results
- SQL result card with 10 rows

### Result: ✅ PASS
- Job completed in background (Redis events stored)
- Recovery via SSE stream reconnect
- Full SQL result: 10 筆, 100%, table with 系統工單號/車號/工作類型/狀態

---

## Test 4: Dashboard Real Data

### Steps
1. Navigate to /admin/dashboard

### Expected
- Real data instead of mock (王小明)
- Stats from actual DB tables

### Result: ✅ PASS
- 歡迎回來，Admin (real user)
- 知識庫文件: 2, 今日查詢: 11, 車輛資產: 16165, 故障通報: 482

---

## Test 5: Audit Log Page

### Steps
1. Navigate to /admin/audit
2. Click a SQL row to expand details

### Expected
- Table with all queries (SQL + RAG)
- Expandable detail showing SQL, tables, mode, timing

### Result: ✅ PASS
- 84 total entries, pagination working
- SQL detail shows full query, tables, mode, cached status

---

## Known Issues
- Intent classifier (llama3.2:3b) often triggers clarification for clear queries
- gemma4:31b-cloud occasionally generates wrong column names
- <think> tags sometimes leak into older conversations (pre-fix)
