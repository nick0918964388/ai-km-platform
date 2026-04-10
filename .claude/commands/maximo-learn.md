# /maximo-learn — 匯入 Maximo 查詢知識

讀取 `docs/maximo-query-patterns.md`，解析兩種內容並分別匯入 DB：

1. **領域規則** → 存入 `maximo_field_metadata`（table=_rules, column=rule_N），注入 NL→SQL 的 system prompt
2. **查詢範例** → 存入 `nl_sql_examples`（few-shot 範例）

## 執行流程

### Step 1 — 讀取檔案
讀取 `docs/maximo-query-patterns.md`

### Step 2 — 解析領域規則
從 `## 領域規則` 區塊解析每一條 `- ` 開頭的筆記，存入：
```sql
INSERT INTO maximo_field_metadata (table_name, column_name, display_name, description)
VALUES ('_rules', 'rule_<序號>', '查詢規則', '<規則內容>')
ON CONFLICT (table_name, column_name) DO UPDATE SET description = EXCLUDED.description;
```

### Step 3 — 解析查詢範例
從 `## 查詢範例` 區塊解析每個 `**問：**` + SQL code block 配對，存入：
```sql
INSERT INTO nl_sql_examples (question, sql_query, verified)
VALUES ('<問題>', '<SQL>', true)
ON CONFLICT DO NOTHING;
```

### Step 4 — 執行
透過 SSH 連到 192.168.1.11，在 aikm-postgres container 執行以上 SQL

### Step 5 — 回報
- ✅ 匯入 N 條規則
- ✅ 匯入 N 條範例（略過 N 條已存在）

## ARGUMENTS: （無，固定讀 docs/maximo-query-patterns.md）
