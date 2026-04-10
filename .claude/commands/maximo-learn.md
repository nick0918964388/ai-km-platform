# /maximo-learn — 匯入 Maximo 查詢技巧

從指定的 Markdown 檔案中解析查詢問答對，批次匯入 `nl_sql_examples` 資料表。

## 使用方式

```
/maximo-learn [檔案路徑]
```

若未指定路徑，預設讀取 `docs/maximo-query-patterns.md`。

## Markdown 格式規範

檔案中每個查詢技巧用以下格式撰寫：

```markdown
## 問題描述

**問：** 自然語言問題

**SQL：**
```sql
SELECT ...
```

**說明：** （選填）解釋這個查詢的重點或注意事項
```

## 執行流程

1. 讀取指定的 md 檔案
2. 解析所有「問：」+ 「SQL：」配對
3. 顯示解析到的問答數量，列出清單讓使用者確認
4. 使用 SSH 連到 192.168.1.11，執行以下 SQL 批次插入：
   ```sql
   INSERT INTO nl_sql_examples (question, sql_query, verified)
   VALUES (...)
   ON CONFLICT DO NOTHING;
   ```
5. 回報成功匯入幾條、略過幾條（已存在）

## 注意事項

- SQL 必須是 SELECT 語句，非 SELECT 的跳過並警告
- 重複問題（ON CONFLICT DO NOTHING）自動略過
- 匯入後建議執行一條測試 NL→SQL 驗證效果

## ARGUMENTS: 檔案路徑
