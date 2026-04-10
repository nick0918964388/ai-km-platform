# Maximo 查詢知識庫

更新此檔案後執行 `/maximo-learn` 自動匯入。

---

## 領域規則
> 這裡寫業務知識筆記，每條一行，自動注入 NL→SQL 的 system prompt

- EQ9（record_type）可以區分車組、車輛、工具等車輛類型
- 電聯車查詢通常只需要車組（record_type='車組'），不需要子車廂
- 透過 parent_assetnum 可以找到電聯車跟子車廂的關聯：子車廂的 parent_assetnum = 車組的 assetnum
- 工單（pm_workorders/cm_workorders）是掛在車組的 assetnum 上，不是子車廂
- 故障通報（fault_reports）可能掛在車組或子車廂，查完整資料要用 assetnum=車組 OR parent_assetnum=車組 兩個條件
- EMU900 車組每組由 10 輛子車廂組成（ED/EM/EP 三種類型）
- 車型（vehicle_type）是電聯車型號如 EMU900/EMU800/EMU3000，車種（vehicle_class）是更上層的 EM/EP/ED 等車廂分類
- 段別代碼如 WAY=萬華段，需要用 LIKE '%WAY%' 查詢

---

## 查詢範例
> 問 + SQL 配對，作為 few-shot 範例

**問：** EMU900 目前有幾組車組？
```sql
SELECT COUNT(*) FROM maximo_assets
WHERE vehicle_type = 'EMU900' AND record_type = '車組' AND status = 'OPERATING'
```

---

**問：** EMU901 車組由哪些車廂組成？
```sql
SELECT assetnum, eq24, vehicle_type, position
FROM maximo_assets
WHERE parent_assetnum = 'EMU901'
ORDER BY position
```

---

**問：** 查詢 EMU901 車組本身及其所有子車廂的故障通報
```sql
SELECT f.ticketid, f.assetnum, f.description, f.occurrence_date, f.grade
FROM maximo_fault_reports f
WHERE f.assetnum = 'EMU901'
   OR f.assetnum IN (SELECT assetnum FROM maximo_assets WHERE parent_assetnum = 'EMU901')
ORDER BY f.occurrence_date DESC
```

---

**問：** EMU900 完成的二級定檢工單有幾張？
```sql
SELECT COUNT(*) FROM maximo_pm_workorders pw
JOIN maximo_assets a ON pw.assetnum = a.assetnum
WHERE a.vehicle_type = 'EMU900' AND a.record_type = '車組'
  AND pw.work_type = '2A' AND pw.status = '工單結案'
```

---

<!-- 新增規則請在「領域規則」區塊加一行 -->
<!-- 新增範例請複製「問 + SQL」格式貼在此行之前 -->
