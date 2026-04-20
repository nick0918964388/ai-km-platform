# Quickstart: Maximo Query Tools

**Feature**: 012-maximo-query-tools
**Audience**: 工程師 / Reviewer / QA

---

## 本地開發環境

本 feature 的開發在 **Mac Mini 本機寫 code**，但所有服務（backend / frontend / PostgreSQL）跑在 **192.168.1.11 Ubuntu 部署機**上（依循 CLAUDE.md 強制規則）。

### 先決條件

1. SSH 到 192.168.1.11 的 key 已設置（`~/.ssh/id_ed25519`）
2. 本機有 docker / docker compose（用來跑整合測試）
3. Python 3.10+ / Node 20+ 安裝（本地跑 unit test）
4. `ANTHROPIC_API_KEY` 已寫入 `.env`（Claude Sonnet 4.6 tool_use 用）

### 拉分支

```bash
git fetch origin
git checkout 012-maximo-query-tools
```

---

## 先跑一次 Migration

```bash
# 在 192.168.1.11 上執行
ssh user@192.168.1.11
cd /path/to/ai-km-platform
docker exec -i aikm-postgres psql -U aikm -d aikm < backend/scripts/migration_012_tool_calls.sql
```

**驗證**：
```sql
-- 應該看到 4 個物件
\dt maximo_tool_calls
\dv maximo_tool_analytics
\dv maximo_route_hit_rate
\dv maximo_fallback_reasons
```

---

## 驗 Tool 1（get_vehicle_info）獨立測試

Tool 1 是最窄、最穩的 tool，用它驗整條 pipeline。

### Unit Test

```bash
cd backend
pytest tests/unit/maximo_tools/test_get_vehicle_info.py -v
```

預期：
- `test_execute_happy_path` ✅
- `test_execute_not_found` ✅（回傳空 list）
- `test_execute_chinese_output` ✅（eq11/eq3/eq4 已轉中文）
- `test_input_schema_valid_json_schema` ✅

### Integration Test（真實 DB）

```bash
cd backend
pytest tests/integration/test_maximo_tool_router.py::test_get_vehicle_info_e2e -v
```

### curl 端到端

```bash
curl -X POST http://192.168.1.11:8000/api/maximo/nl2sql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "查 A12345 基本資料"}'
```

預期回傳：
```json
{
  "route_path": "tool",
  "tool_name": "get_vehicle_info",
  "tool_input": {"asset_num": "A12345"},
  "rows": [{ "assetnum": "A12345", "大分類": "客車", ... }],
  "elapsed_ms": 800
}
```

---

## 驗 Router 命中率

跑 10 個代表 query，統計命中率：

```bash
cd backend
pytest tests/integration/test_maximo_tool_router.py::test_router_hit_rate -v -s
```

預期：命中率 ≥ 70%（10 題至少命中 7 題）

**10 個代表 query 清單**：

| # | Query | 預期工具 |
|---|-------|---------|
| 1 | "查 A12345 基本資料" | get_vehicle_info |
| 2 | "A00567 的車型是什麼" | get_vehicle_info |
| 3 | "A12345 最近一個月工單" | search_workorders_by_vehicle |
| 4 | "A12345 上週的故障" | search_faults_by_vehicle |
| 5 | "A12345 urgency A 故障" | search_faults_by_vehicle |
| 6 | "車次 F123 的故障通報" | search_faults_by_trip |
| 7 | "各大分類未結案工單數量" | count_open_workorders_by_category |
| 8 | "客車的未結案工單" | list_open_workorders_in_category |
| 9 | "貨車未結案清單" | list_open_workorders_in_category（含 RSTF+RSTP） |
| 10 | "近 30 天故障等級分布" | get_recent_fault_distribution |

**長尾 fallback 測試**（3 題）：

| # | Query | 預期行為 |
|---|-------|---------|
| 11 | "過去 30 天維修超過 3 次的車輛清單" | fallback to nl2sql |
| 12 | "A 和 B 段管故障率比較" | fallback to nl2sql |
| 13 | "故障率最高的車型是什麼" | fallback to nl2sql |

---

## 驗 Fallback 品質

確保既有 NL→SQL 的 regression：

```bash
cd backend
pytest tests/regression/test_nl2sql_fallback.py -v
```

預期：所有既有 test case 通過（對 fallback 路徑不得有破壞）

---

## E2E（Playwright）

4 個 user story 場景驗證：

```bash
cd frontend
npx playwright test maximo-tool-router.spec.ts --headed
```

覆蓋：
- US1: 維修技師查工單/故障（Chat 輸入）
- US2: 管理者看分類統計（Chat 輸入）
- US3: 車號基本資料查詢 / 車次查故障
- US4: 長尾 query 走 fallback

---

## 觀測 / 觀察 Telemetry

### Admin dashboard URL

```
https://aikm.example/admin/maximo/tool-analytics
```

### 直接查 DB

```sql
-- 熱門工具 Top 10
SELECT * FROM maximo_tool_analytics LIMIT 10;

-- 當日命中率
SELECT * FROM maximo_route_hit_rate LIMIT 7;

-- Fallback 原因 TOP
SELECT * FROM maximo_fallback_reasons;

-- 失敗案例
SELECT * FROM maximo_tool_calls
WHERE success = false
  AND created_at > NOW() - INTERVAL '1 day'
ORDER BY created_at DESC
LIMIT 50;
```

---

## 部署流程

### 部署到 192.168.1.11

```bash
# 1. 本機 commit + push
git add -A
git commit -m "feat(maximo): tool-based hot path for query routing"
git push origin 012-maximo-query-tools

# 2. SSH 部署機
ssh user@192.168.1.11
cd /path/to/ai-km-platform
git fetch origin
git checkout 012-maximo-query-tools
git pull

# 3. 重建服務
docker compose up -d --build backend frontend

# 4. 跑 migration（若應用程式未自動跑）
docker exec -i aikm-postgres psql -U aikm -d aikm < backend/scripts/migration_012_tool_calls.sql

# 5. 健康檢查
curl http://192.168.1.11:8000/health
curl http://192.168.1.11:8000/api/maximo/nl2sql -X POST ... # 測試 tool path
```

### Rollback

```bash
# SSH 部署機
ssh user@192.168.1.11
cd /path/to/ai-km-platform
git checkout main    # 或前一個 tag
docker compose up -d --build backend frontend
# maximo_tool_calls table 留著（觀測資料，不影響業務）
```

---

## 常見問題 / Troubleshooting

### Q1: 為什麼我的 query 都走 fallback，命中率很低？

檢查：
1. `SELECT fallback_reason, COUNT(*) FROM maximo_tool_calls WHERE route_path='fallback' GROUP BY 1;`
2. 若 `llm_circuit_open` 多 → Anthropic API 有問題，檢查 API key / 額度
3. 若 `no_tool_selected` 多 → 使用者 query 真的是長尾；考慮擴 tool 或加 suggested queries
4. 若 `tool_invocation_error` 多 → LLM 抽參數不穩，檢查 input_schema description 是否夠清楚

### Q2: 工具 SQL 寫錯怎麼辦？

1. 看 `SELECT * FROM maximo_tool_calls WHERE tool_name = 'X' AND success = false LIMIT 10;`
2. 在本機用 `pytest tests/unit/maximo_tools/test_X.py` 寫 repro case
3. 修 tool 邏輯 → 重跑測試 → commit → 部署

### Q3: 前端 badge 沒顯示？

1. F12 看 `/api/maximo/nl2sql` response 是否有 `route_path` 欄位
2. 檢查 `ChatMessage.tsx` 是否正確 destructure
3. 看 `RoutePathBadge.tsx` 是否 render 條件判斷錯

---

## Definition of Done（Phase 5 完工條件）

- [ ] 7 個 tool 全部有 unit test（≥ 80% coverage）
- [ ] 7 個 tool 有 integration E2E（真實 DB）
- [ ] Router E2E：10 個代表 query 命中率 ≥ 70%
- [ ] Fallback regression：3 個長尾 query 正確走 nl2sql
- [ ] Migration 在部署機成功執行
- [ ] Playwright E2E 4 個 user story 通過
- [ ] 前端 RoutePathBadge 顯示正確
- [ ] Admin analytics 頁面可讀 telemetry
- [ ] health check 通過
- [ ] Critic 審查 PR、無 CRITICAL/HIGH 問題
