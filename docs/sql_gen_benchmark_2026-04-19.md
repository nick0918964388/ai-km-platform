# SQL Generation Provider Benchmark — Anthropic Sonnet vs NVIDIA minimax

日期：2026-04-19
腳本：`backend/scripts/sql_gen_benchmark.py`
目的：驗證 Batch 2-C 能否把 SQL Generation 從 Anthropic `claude-sonnet-4-6`（3.5–4.5s/call）換成 NVIDIA `minimaxai/minimax-m2.7`（~0.5s/call），省 ~3s/call。

---

## 1. 執行方式（需在部署機 192.168.1.11 上跑）

腳本依賴：
- Live Postgres（aikm-postgres，20+ maximo_* 表）
- `ANTHROPIC_API_KEY` 可用
- `NVIDIA_API_KEY` 可用（`.env` 已設定）
- 已透過 DB settings 或 env 設好 `sql_generation_provider` 切換

```bash
# SSH 進部署機
ssh root@192.168.1.11
cd ~/ai-km-platform

# 進 backend container 跑 benchmark（確保 backend image 已含最新 code）
docker exec -it aikm-backend python /app/scripts/sql_gen_benchmark.py \
    --out /tmp/sql_gen_benchmark_result.json

# 拷貝結果
docker cp aikm-backend:/tmp/sql_gen_benchmark_result.json ./docs/
```

---

## 2. 測試題目（20 題 core20 set）

涵蓋：純 count、asset filter、時間範圍、排名、JOIN cm+fault、follow-up、domain lookup。

| # | 題目 | 類型 |
|---|------|------|
| 1 | 全部車輛數量 | count |
| 2 | EMU900 去年故障了幾次 | filter+count |
| 3 | 哪台車最常故障前5名 | ranking |
| 4 | 列出最近一週臨修工單 | time+list |
| 5 | 列出最新 10 個工單 | list |
| 6 | TEMU2000 的狀態 | filter |
| 7 | 去年每月的故障通報數量 | group by month |
| 8 | 列出所有 EMU800 車輛 | filter |
| 9 | EMU901-1 的所有故障紀錄 | filter+join |
| 10 | 定檢工單中 3A 的數量 | filter+count |
| 11 | 借用段在南港的車輛 | filter (domain) |
| 12 | 最近一個月的臨修工單數量 | time+count |
| 13 | 故障等級為高的通報數量 | filter+count |
| 14 | 2025 年的定檢工單 | time+list |
| 15 | T1 工單中最近 10 筆 | filter+list |
| 16 | 列出故障說明包含煞車的工單 | like filter |
| 17 | 每個機廠的車輛數量 | group by |
| 18 | EMU3000 車型的車輛有幾台 | filter+count |
| 19 | 本月已結案的故障通報 | time+status filter |
| 20 | 狀態為 OPERATING 的 EMU 車輛 | filter |

---

## 3. 評估準則

對每題分別用 Anthropic Sonnet 與 NVIDIA minimax 產 SQL，執行後比對：

1. **Syntax OK**：SQL 通過 `validate_sql()`（規則檢查 + 允許的表 + 禁用關鍵字）
2. **Exec OK**：PostgreSQL 成功回傳（無 SQL error）
3. **等價**（其中之一）：
   - 聚合查詢（row_count ≤ 5）：row 內容完全一致
   - 大結果集：row_count 差異在 ±10% 內（允許不同 ORDER BY）

**切換門檻**：等價率 ≥ 85%（17/20）→ 建議切換 NVIDIA 作預設。

---

## 4. 結果（待填）

> 腳本已就緒、feature flag 已加、單元測試 passing。
> 部署機執行後請將 `/tmp/sql_gen_benchmark_result.json` 回傳並更新本表。

### 4.1 Summary（範本）

| 指標 | Anthropic Sonnet | NVIDIA minimax |
|------|------------------|----------------|
| Syntax OK | ?/20 | ?/20 |
| Exec OK | ?/20 | ?/20 |
| 等價率 | — | ?/20 |
| 平均 LLM 延遲 | ~4000ms | ~500ms（預期） |

### 4.2 逐題對照（範本）

| # | 題目 | Anthropic ms | NVIDIA ms | 等價 | 備註 |
|---|------|-------------:|----------:|:----:|------|
| 1 | ... | | | | |
| 2 | ... | | | | |
| ... | ... | | | | |

### 4.3 建議

- **若等價率 ≥ 17/20（85%）**：建議設 `sql_generation_provider=nvidia` 作預設（經 system_settings 表或 env），可省 ~3s/call。保留 feature flag 以便 rollback。
- **若等價率 < 85%**：保留 `anthropic` 預設；NVIDIA 作為選項，待 prompt 調校後再測。
- **若 NVIDIA syntax_ok < 15/20**：代表 prompt 不適合 minimax 模型，需改寫 system prompt（減少 domain_lookup JOIN 複雜度或調整 instruction 格式）再重測。

---

## 5. 回滾

若上線後發現品質回退，立即在 system_settings 表執行：

```sql
UPDATE system_settings SET value='anthropic' WHERE key='sql_generation_provider';
```

container 重啟或下次 `get_settings.cache_clear()` 後即生效。
