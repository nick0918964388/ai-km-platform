# Maximo NL→SQL 查詢技巧庫

新增查詢技巧後執行 `/maximo-learn` 自動匯入資料庫。

---

## 車組與子車廂關係

**問：** EMU901 車組由哪些車廂組成？

**SQL：**
```sql
SELECT assetnum, eq24, vehicle_type, position
FROM maximo_assets
WHERE parent_assetnum = 'EMU901'
ORDER BY position
```

**說明：** 子車廂的 `parent_assetnum` = 車組的 `assetnum`

---

## 查車組工單（不查子車廂）

**問：** 工單查詢要用車組 assetnum，不用子車廂

**SQL：**
```sql
SELECT w.wonum, a.eq24 AS 車組, a.vehicle_type AS 車型,
       w.work_type AS 級別, w.act_start, w.act_finish
FROM maximo_pm_workorders w
JOIN maximo_assets a ON w.assetnum = a.assetnum
WHERE a.record_type = '車組'
  AND w.status = '工單結案'
ORDER BY w.act_finish DESC
LIMIT 20
```

**說明：** 定期工單掛在車組上，所以 JOIN 時要確認 `record_type='車組'`

---

## 車組及其子車廂的故障通報

**問：** 查詢 EMU901 車組本身及其所有子車廂的故障通報

**SQL：**
```sql
SELECT f.ticketid, f.assetnum, f.description, f.occurrence_date, f.grade
FROM maximo_fault_reports f
WHERE f.assetnum = 'EMU901'
   OR f.assetnum IN (
       SELECT assetnum FROM maximo_assets WHERE parent_assetnum = 'EMU901'
   )
ORDER BY f.occurrence_date DESC
```

---

## 各車型車組數量

**問：** 各車型目前有幾組車組在營運？

**SQL：**
```sql
SELECT vehicle_type, COUNT(*) AS 車組數
FROM maximo_assets
WHERE record_type = '車組'
  AND status = 'OPERATING'
GROUP BY vehicle_type
ORDER BY 車組數 DESC
```

---

## 段別配屬查詢

**問：** 查詢某段別（如萬華段）目前配屬的車組清單

**SQL：**
```sql
SELECT assetnum, eq24, vehicle_type, section, status_desc
FROM maximo_assets
WHERE section LIKE '%WAY%'
  AND record_type = '車組'
  AND status = 'OPERATING'
ORDER BY vehicle_type, assetnum
```

**說明：** 萬華段代碼含 WAY，可依實際段別代碼調整

---

<!-- 新增技巧請複製以上格式，在此行之前加入 -->
