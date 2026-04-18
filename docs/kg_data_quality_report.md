# Maximo 資料品質健檢報告 — Phase 3 Week 0 準備

> 日期：2026-04-18（**v3 重跑 10:39 AM**） · 資料來源：aikm-postgres @ 192.168.1.11 · 全程 SELECT only

---

## v3 重跑摘要（2026-04-18 10:39 AM 三次掃描）

**本次重跑背景**：使用者再次修正 aikm-postgres 後（相較 v2 早上 7:43 AM 版）要求重跑，比對是否有進一步變化。

### TL;DR — v3 vs v2

| 類別 | v2 (7:43 AM) | v3 (10:39 AM) | 變化 |
|------|--------------|---------------|------|
| 三表列數（mxwo/mxasset/mxsr） | 8,068 / 10,662 / 517 | **8,068 / 10,662 / 517** | **完全一致** |
| Clean subset（工單 / 故障通報） | 7,995 / 375 | **7,995 / 375** | **完全一致** |
| mxwo.reportdate 跨度 | 11 天 | **11 天（2026-04-05~16）** | 未改善 |
| mxsr → mxwo 連結率 | 3/513 (0.6%) | **3/513 (0.6%)** | 未改善 |
| mxwo 欄位數 | 14 | **14** | 未改善（仍無 description / failurecode） |
| mxasset 欄位數 | 27 | **27** | 持平 |
| mxsr 欄位數 | 97 | **97** | 持平 |
| mxasset.classstructure 欄位空 | 100% | **100%** | 未改善 |
| mxsr 故障要因 4 欄空 | 99.42% | **99.42%（514/517）** | 未改善 |
| **新表 `maximo_mxasset_classstructure`** | — | **新增 11,006 列 / 193 distinct** | 🟡 **新資產層抓取** |
| public schema 表數 | 18 | **19** | +1（新增 classstructure） |

### v3 關鍵新發現：新增 `maximo_mxasset_classstructure` 表

這是 v2 之後新出現的表：

| 指標 | 值 |
|------|----|
| 總列數 | 11,006 |
| distinct `classstructureid` | **193** |
| 重複率 | **94.7%**（和 v2 mxwo/mxasset 同樣的 ETL 重複 bug） |
| `description` 欄位填值率 | 100%（英文為主，如 `EMU800`） |
| 中文 description | **0 筆（0%）** |
| `zz_carkind` / `zz_dept` / `zz_carclass` 填值率 | 100% |

**意涵**：
- 資產分類 taxonomy 終於有來源表了，但 **`maximo_mxasset.classstructure` 欄位仍 100% 空**，**完全無法 join** — 資產分類鏈依舊斷裂
- 新表本身 94.7% 重複（ETL dedup bug 未套用到此表），Week 1 前須去重
- description 皆英文代碼，無中文 — Phase 3.2 需人工補翻譯
- 欄位 `zz_carkind`、`zz_dept`、`zz_carclass`、`zz_mainsection`、`sortorder` 可當 KG 資產層分類 fallback

### 結論：GO / No-Go v3 更新建議

**維持「有條件 GO」**。相較 v2，條件**新增 1 項、其他不變**：

1. ~~ETL 去重（mxwo/mxasset/mxsr）~~ ✅ v2 已解決
2. **ETL 去重需補到 `maximo_mxasset_classstructure`**（🔴 新，193 distinct / 11,006 列，重複率 94.7%）
3. **mxwo 抓取窗擴大** — 🔴 仍未動（11 天未變）
4. **`mxasset.classstructure` 欄位仍 100% 空** — 新 classstructure 表出現但無法 join 回 asset。若要啟用資產分類層，**需在 ETL 同時補 `mxasset.classstructure` 外鍵**
5. `classstructure / 故障要因` 其他空值問題：方案依 v1/v2 不變

**新增 Action Item（Week 1 前）**：
- 修復 `maximo_mxasset_classstructure` 的 ETL dedup（同 v2 修 mxwo/mxasset 的模式）
- ETL 補抽 `mxasset.classstructure` 欄位（或以 `assetnum` prefix 推導）

---

## v2 重跑摘要（2026-04-18 二次掃描）

**本次重跑背景**：使用者修正 aikm-postgres（ETL 去重 + schema 擴充）後重新健檢。

### TL;DR — 一眼看完

| 類別 | 狀態 | 說明 |
|------|------|------|
| ETL 重複率 (🔴→🟢) | **全部修復** | mxwo / mxasset / mxsr 重複率皆歸零（原 45% / 68% / 45%） |
| mxasset / mxsr schema | **大幅擴充** | mxasset 15→27 欄、mxsr 32→97 欄，新欄位涵蓋故障處理鏈、廠商送修、鎖定、區域等 |
| mxwo 日期跨度 | **未改善** | 仍只有 11 天（2026-04-05~16），抓取窗未擴大 |
| mxsr→mxwo 連結率 | **未改善** | 仍僅 0.6% 能 join（3/513），與 v1 的 4/672 同樣斷裂 |
| mxwo schema | **未改善** | 仍 14 欄，無 description / failurecode |
| classstructure 空值 | **未改善** | 仍 100% 空 |
| 故障要因 4 欄空值 | **未改善** | 仍 99.42% 空（v1: 99.56%） |
| Clean subset | 持平 | 工單 7,995、故障通報 375（未變） |

### 版本對比

| 指標 | v1 | v2 | Δ | 狀態 |
|------|----|----|---|------|
| mxwo 原始列數 | 10,742 | **8,068** | -2,674 (-24.9%) | 🟢 去重生效 |
| mxwo distinct wonum | 8,068 | 8,068 | 0 | = |
| mxasset 原始列數 | 16,165 | **10,662** | -5,503 (-34.0%) | 🟢 去重生效 |
| mxasset distinct assetnum | 10,662 | 10,662 | 0 | = |
| mxsr 原始列數 | 676 | **517** | -159 | 🟢 去重 + 新增 5 筆 |
| mxsr distinct ticketid | 512 | **517** | +5 | 🟢 略增 |
| mxwo reportdate 跨度 | 11 天 | **11 天** | 0 | 🔴 未改善 |
| mxsr → mxwo linked wonum | 4/672 (0.6%) | **3/513 (0.6%)** | 同比率 | 🔴 未改善 |
| mxwo orphan asset | 89 (0.83%) | 73 (0.90%) | 幾乎同比率 | 🟢 可接受 |
| mxwo worktype 找不到 domain | 1,095 (10.19%) | 892 (11.05%) | 比率略升 | 🟡 持平 |
| mxasset classstructure 空 | 100% | **100%** | 0 | 🔴 未改善 |
| mxasset assettype 空 | 68.46% | **52.19%** | -16.3pp | 🟡 改善 |
| mxsr 故障要因 4 欄空 | 99.56% | **99.42%** | -0.14pp | 🔴 未改善 |
| mxwo schema 欄位數 | 14 | **14** | 0 | 🔴 未改善 |
| mxasset schema 欄位數 | 15 | **27** | +12 | 🟢 擴充 |
| mxsr schema 欄位數 | 32 | **97** | +65 | 🟢 大幅擴充 |
| ALN orphan | 1,658 (11.04%) | 1,658 (11.04%) | 0 | = |
| Clean subset 工單 | 7,995 | **7,995** | 0 | = |
| Clean subset 故障通報 | 375 | **375** | 0 | = |
| 關鍵問題數（🔴） | 4 | **3** | -1 | 🟢 減少 |

### 新增 schema 欄位對 KG 的影響

- **mxasset 新增**：`eq1–eq12`、`eq23–eq24`、`status_description`、`assettype_description`、`eq9_description`、`zz_status`、`zz_faseq`、`zz_repeq2`、`zz_toolorequip`。→ KG 資產節點屬性豐富，`assettype_description` 可當中文標籤用。
- **mxsr 新增 65 欄**：涵蓋「故障處理鏈」完整欄位群 — `zz_fnm_handler/measure/memo/point/behavior`（處理者/措施/備註/點位/行為）、`zz_repair_class/dept/frequency/reason`（維修類別/部門/頻率/原因）、`zz_from_vendor_date/to_vendor_date`（廠商送修時間）、`zz_incident/confirm_by/confirm_date`、`zz_area/area_description`、`zz_urgency`（緊急度）等。→ 即使 fnm_factor/event/element/measure 仍空，**新欄位 `zz_repair_reason_description`、`zz_repair_class_description`、`zz_fnm_factor_description` 可能填補故障分類語意**，Week 1 值得先抽樣驗證是否有值。
- **Action Item**：下一步 DQ 補查這些新欄位的填值率，若 `zz_repair_reason_description` 有覆蓋率 > 50%，可考慮改用此路線取代 fnm_factor。

### 結論：GO / No-Go 更新建議

**維持「有條件 GO」**，但條件從 4 項縮成 **2 項**：
1. ~~ETL 去重~~ ✅ **已解決**
2. ~~重複資料會讓 KG 節點重複~~ ✅ **已解決**
3. **mxwo 抓取窗擴大** — 🔴 仍未動，`zz_currwonum` 斷鍵率 99.4% 依舊。進入 Week 1 前**必須**處理，否則故障→工單語意鏈仍斷掉。
4. **classstructure / 故障要因仍空** — 方案依 v1（`assettype` + prefix 分類、先建骨架邊）不變。

**新利多**：mxsr 新增 65 欄，故障 KG 建模可從原「只能看 description」升級為「結構化欄位 + 自由文字雙軌」，建議 Week 1 Day 1 先對新欄位做填值率抽樣。

---

## 執行摘要（v3 最新數字）

| 項目 | 數值 |
|------|------|
| 工單總筆數（`maximo_mxwo`） | **8,068** 列（已去重）/ 8,068 distinct `wonum` |
| 資產總筆數（`maximo_mxasset`） | **10,662** 列（已去重）/ 10,662 distinct `assetnum` |
| 故障通報總筆數（`maximo_mxsr`） | **517** 列（已去重）/ 517 distinct `ticketid` |
| 資產分類結構（`maximo_mxasset_classstructure`） | **11,006** 列 / **193** distinct classstructureid（🔴 ETL 重複，未去重） |
| Domain 主表（`maximo_zz_domain`） | 1,069 筆（ALN 358、SYNONYM 431、TABLE 227） |
| Domain ALN 展開（`maximo_zz_domain_alndomain`） | 15,019 筆 |
| Clean subset（工單：有 assetnum + reportdate + 對應 asset 存在） | **7,995** distinct wonum |
| Clean subset（故障通報：有 assetnum + description>10字 + reportdate + 對應 asset） | **375** distinct ticketid |
| 關鍵問題數（🔴 立即修復） | **4**（v2: 3；新增 classstructure 表 ETL 重複） |
| 可接受問題數（🟡 需標註） | **5** |
| 後續處理（🟢 Phase 3.2） | **3** |

## 重要背景

1. **任務描述與實際 schema 不一致**：任務指名 `trc_mxwo / trc_mxasset / trc_mxsr` — 此三表在 `aikm` DB 並不存在。實際 Maximo raw 表為 `maximo_mxwo / maximo_mxasset / maximo_mxsr`。本報告以實際表為準。
2. **`maximo_mxwo` 只有 14 欄**，確實沒有 `description` 或 `failurecode` 欄位。工單文字敘述不存在，只能用 `worktype` + `wonum`（工單編號）+ `assetnum`（資產編號）作為連結鍵。
3. **日期範圍極窄**：`mxwo.reportdate` 範圍是 `2026-04-05` ~ `2026-04-16`，只有 **11 天**資料。這是 ETL 增量抓取的結果，不是歷史資料。影響後續建 KG 的樣本多樣性評估。
4. **舊表仍存在**：`maximo_assets` (4,123)、`maximo_cm_workorders` (5,989)、`maximo_pm_workorders` (339,810)、`maximo_fault_reports` (395) — 這些是 Phase 1 時期表，與 raw `maximo_mx*` 並存。**不建議混用**，本 Phase 3 應只使用 raw `mx*` 表。
5. **`maximo_domains` 表 0 筆** — 應廢棄。

---

## 1. Orphan Rate（孤兒實體）

### 1.1 工單 `assetnum` → 資產表

```sql
SELECT COUNT(*) AS mxwo_total,
       COUNT(*) FILTER (WHERE assetnum IS NULL OR assetnum='') AS null_asset,
       COUNT(*) FILTER (
         WHERE assetnum IS NOT NULL AND assetnum != ''
           AND NOT EXISTS (SELECT 1 FROM maximo_mxasset a WHERE a.assetnum = maximo_mxwo.assetnum)
       ) AS orphan_asset
FROM maximo_mxwo;
```

| 指標 | 值 |
|------|----|
| 工單總數 | 10,742 |
| assetnum 空值 | 0 |
| **orphan**（找不到對應 asset） | **89**（0.83%） |

**分級**：🟢 **可接受**
**建議**：0.83% 偏低，KG 建構時直接捨棄這 89 筆即可。樣本：`EMU613`、`R154` 等工程用代碼各有 4 筆，可能是新上線資產尚未寫入 mxasset，或是測試工單。

**v2 對比**：

| 指標 | v1 | v2 | Δ |
|------|----|----|---|
| 工單總數 | 10,742 | **8,068** | -24.9%（去重） |
| orphan 筆數 | 89 | **73** | -16 |
| orphan 比率 | 0.83% | **0.90%** | +0.07pp |

orphan 絕對數減少（去重後），比率微升但仍在 🟢 可接受範圍。

**v3 對比**：工單總數 8,068、orphan 73（0.90%）— 與 v2 **完全一致，無變化**。

### 1.2 工單 `worktype` → `alndomain` 值

```sql
SELECT w.worktype, COUNT(*) FROM maximo_mxwo w
 WHERE NOT EXISTS (SELECT 1 FROM maximo_zz_domain_alndomain a WHERE a.value = w.worktype)
 GROUP BY 1 ORDER BY 2 DESC;
```

| worktype | 筆數 |
|----------|------|
| T1 | 739 |
| T4 | 278 |
| C5 | 34 |
| C9 | 29 |
| T3 | 7 |
| 其他 | 8 |
| **合計** | **1,095（10.19%）** |

**分級**：🟡 **可接受但需標註**
**建議**：`worktype` 在資料字典裡不存在對應的中文翻譯（如 T1/T4 在 ZZ_WORKTYPE domain 缺項）。KG schema 裡應保留 raw `worktype`，不強制 join domain；Phase 3.2 再由業務確認這些代碼的語意。

**v2 對比**：

| worktype | v1 | v2 |
|----------|----|----|
| T1 | 739 | **595** |
| T4 | 278 | **230** |
| C5 | 34 | **30** |
| C9 | 29 | **24** |
| 2C | — | **6** (新出現) |
| T3 | 7 | **5** |
| JB | — | **2** (新出現) |
| **合計** | 1,095 (10.19%) | **892 (11.05%)** |

絕對筆數下降（去重），比率略升。問題性質不變，仍建議 🟡 保留原值。

**v3 對比**：T1=595、T4=230、C5=30、C9=24、2C=6、T3=5、JB=2，合計 892（11.05%）— 與 v2 **完全一致，無變化**。

### 1.3 故障通報 `assetnum` → 資產表

```sql
SELECT COUNT(*) FILTER (
  WHERE assetnum != '' AND NOT EXISTS (SELECT 1 FROM maximo_mxasset a WHERE a.assetnum = maximo_mxsr.assetnum)
) AS orphan FROM maximo_mxsr;
```

| 指標 | 值 |
|------|----|
| 總數 | 676 |
| assetnum 空值 | 0 |
| orphan | **0（0%）** |

**分級**：🟢 **完美**

**v3 對比**：總數 517、orphan 0、null 0 — 與 v2 一致，🟢 維持完美。

### 1.4 故障通報 `zz_currwonum` → 工單表

```sql
SELECT COUNT(*) FROM maximo_mxsr s
 WHERE s.zz_currwonum IS NOT NULL AND s.zz_currwonum!=''
   AND EXISTS (SELECT 1 FROM maximo_mxwo w WHERE w.wonum = s.zz_currwonum);
```

| 指標 | 值 |
|------|----|
| 有連結 wonum 的 mxsr | 672 / 676（99.4%） |
| wonum 能在 mxwo 找到 | **4 / 672（0.6%）** |

**分級**：🔴 **立即修復** — KG blocker
**建議**：這是**最關鍵問題**。故障通報宣稱關聯到工單，但實際 99.4% 的 `zz_currwonum` 在 `maximo_mxwo` 裡找不到。原因很可能是 mxwo 只抓了近 11 天，而 mxsr 含跨度較長（最早到 2025-07）的通報。**必須補拉歷史工單資料**，否則 KG 的「故障 → 工單 → 處置」語意鏈斷掉。

**v3 對比**：mxsr 有 `zz_currwonum` = 513、能對上 mxwo = **3**（0.58%） — 與 v2 的 3/513 完全一致。**mxwo 抓取窗仍是 11 天，無任何改善**，🔴 此問題仍為 KG blocker。

### 1.5 ALN Domain `_parent_key` → Domain 主表

```sql
SELECT COUNT(*) FROM maximo_zz_domain_alndomain a
 WHERE NOT EXISTS (SELECT 1 FROM maximo_zz_domain d
                    WHERE d.maxdomainid = a._parent_key OR d.domainid = a._parent_key);
```

| 指標 | 值 |
|------|----|
| ALN 總筆數 | 15,019 |
| orphan（兩種 key 都找不到父） | **1,658（11.04%）** |

樣本：`_parent_key='704'` 有 339 筆、`'543'` 有 239 筆，這些 maxdomainid 在 `maximo_zz_domain` 已被刪除但子節點仍在。

**分級**：🟡 **可接受但需標註**
**建議**：KG 建構時以 `_parent_key` 實際存在的 domain 為主，孤兒列可視為 legacy 標籤保留。

**v3 對比**：ALN 總 15,019、orphan 1,658（11.04%）— 與 v2 完全一致。

---

## 2. 空值率

### 2.1 `maximo_mxwo`（工單）

| 欄位 | 空值筆數 | 比例 |
|------|---------|------|
| `status` | 0 | 0% |
| `worktype` | 0 | 0% |
| `reportdate` | 0 | 0% |
| `assetnum` | 0 | 0% |
| `actstart` | 7,023 | 65.38% |
| `actfinish` | 7,072 | 65.83% |

**分級**：🟡 `actstart`/`actfinish` 空值率高屬正常（尚未結案工單沒有實際起迄時間）。

**v3 對比**：在去重後的 8,068 列上 `actstart` 空 5,015（**62.16%**）、`actfinish` 空 5,054（**62.64%**），status/worktype/reportdate/assetnum 仍 0% 空。比率略降（去重把多餘列拿掉後分母比較乾淨），性質不變。

### 2.2 `maximo_mxasset`（資產）

| 欄位 | 空值筆數 | 比例 |
|------|---------|------|
| `status` | 0 | 0% |
| `siteid` | 0 | 0%（全為 TRATW） |
| `assettype` | 11,067 | 68.46% |
| `classstructure` | 16,165 | **100%** |

**分級**：🔴 `classstructure` 100% 空值 — Phase 3 KG 原本規劃用 classstructure 做資產分類層，此路不通。
**建議**：改用 `assettype_description`（「設備」/「工具」/「車輛」/「拖車」等）做初階分類，並從 `assetnum` prefix 衍生細分類（EM/EMU/R/T…）。

**v3 對比**：
| 欄位 | v2 | v3 | 變化 |
|------|----|----|------|
| status | 0 | 0 | = |
| siteid | 0 | 0 | = |
| assettype | 52.19% | **52.19%**（5,564/10,662） | 未變 |
| assettype_description | — | **52.19%**（5,564/10,662） | 同 assettype |
| classstructure 欄位 | 100% | **100%**（10,662/10,662） | 🔴 仍全空 |

⚠️ v3 新發現：雖然出現了獨立表 `maximo_mxasset_classstructure`（193 distinct），但 `maximo_mxasset.classstructure` 欄位仍 100% 空，**兩表無法 join**。資產分類鏈依然斷裂。

### 2.3 `maximo_mxsr`（故障通報）

| 欄位 | 空值筆數 | 比例 |
|------|---------|------|
| `description` | 0 | 0% |
| `status` | 0 | 0% |
| `reportdate` | 0 | 0% |
| `assetnum` | 0 | 0% |
| `zz_fnm_factor`（故障要因） | 673 | **99.56%** |
| `zz_fnm_event` | 673 | 99.56% |
| `zz_fnm_element` | 673 | 99.56% |
| `zz_fnm_measure` | 673 | 99.56% |

**分級**：🔴 **立即修復** — KG blocker
**建議**：故障要因/事件/元件/處置 這四個欄位幾乎全空（676 筆裡僅 3 筆有填），代表**故障分類 taxonomy 沒有在來源系統被實際使用**。這擋住 Phase 3 KG 的「故障節點 ↔ 要因/部件節點」關係建模。**方案 A**：改從 `description` 自由文字用 LLM 抽取故障要因（成本較高）。**方案 B**：縮減 KG 範圍，故障實體只保留「ticket → asset」邊，不細分要因。建議採 B + Phase 3.2 再補 A。

**v3 對比**（基於去重後 517 列）：

| 欄位 | 空值筆數 | 比例 | 備註 |
|------|---------|------|------|
| `zz_fnm_factor` | 514 | **99.42%** | 同 v2 |
| `zz_fnm_event` | 514 | 99.42% | 同 v2 |
| `zz_fnm_element` | 514 | 99.42% | 同 v2 |
| `zz_fnm_measure` | 514 | 99.42% | 同 v2 |
| `zz_fnm_factor_description` | 517 | **100%** | v3 新查：description 對應欄位**完全為空** |
| `zz_repair_class_description` | 517 | **100%** | v3 新查：同上 |
| `zz_repair_reason_description` | 517 | **100%** | v3 新查：同上 |
| `zz_area` | 517 | **100%** | v3 新查：區域欄位全空 |
| `zz_urgency` | 0 | 0% | ✅ 有填值（可用於急迫度分類） |

⚠️ **v3 打臉 v2 的樂觀預期**：v2 推測「`zz_repair_reason_description` 可能填補故障分類語意」，但 v3 實測**三個新 description 欄位全部 100% 空**。唯一有值的是 `zz_urgency`（緊急度），可作 KG 屬性但無法取代故障分類。**方案 B（先不拆要因）依然是正確決定**。

---

## 3. 重複實體

### 3.1 工單 `wonum` 重複

```sql
SELECT dup_count, COUNT(*) AS pattern
  FROM (SELECT wonum, COUNT(*) AS dup_count FROM maximo_mxwo GROUP BY wonum) t
 GROUP BY dup_count ORDER BY 1;
```

| 重複次數 | wonum 數 |
|---------|---------|
| 1（唯一） | 5,888 |
| 2（2 倍） | 1,933 |
| 4（4 倍） | 247 |

總 wonum distinct = 8,068；**4,854 筆（45.19%）是重複列**。抽樣驗證：`wonum='16413681'` 的 4 行所有欄位完全相同。

**分級**：🔴 **立即修復** — ETL 缺 dedup
**建議**：ETL 缺去重機制，把同一筆抓 N 次就插 N 行。馬上補 `INSERT ... ON CONFLICT (wonum) DO UPDATE` 或先建 UNIQUE index。**KG 建構前必須去重**，否則每個工單節點會在 graph 裡出現 2-4 次。

**v3 對比**：重複次數皆為 1（8,068 wonum × 1 列）— 🟢 **已完全去重，維持 v2 狀態**。

### 3.2 資產 `assetnum` 重複

| 重複次數 | assetnum 數 |
|---------|------------|
| 1 | 5,159 |
| 2 | 5,503 |

distinct = 10,662；**11,006 筆（68.1%）是重複列**，樣本內容完全相同。

**分級**：🔴 **立即修復** — 同上 ETL 問題

**v3 對比**：重複次數皆為 1（10,662 assetnum × 1 列）— 🟢 **已完全去重，維持 v2 狀態**。

### 3.3 故障通報 `ticketid` 重複

| 重複次數 | ticketid 數 |
|---------|------------|
| 1 | 369 |
| 2 | 143 |
| 3 | 2 |
| 4 | 2 |
| 7 | 1 |

distinct = 512；**307 筆（45.4%）是重複列**。

**分級**：🔴 同上。

**v3 對比**：重複次數皆為 1（517 ticketid × 1 列）— 🟢 **已完全去重，維持 v2 狀態**。

### 3.3b 資產分類結構 `maximo_mxasset_classstructure` 重複（v3 新增）

此表在 v2 時不存在，為 v3 新抓取：

| 重複次數 | pattern 數 |
|---------|-----------|
| 2 | 34 |
| 4 | 11 |
| 8 | 10 |
| 10 | 6 |
| 20 | 7 |
| 40 | 7 |
| 100 | 15 |
| 400 | 2 |
| ... 多種不規則倍數 ... | |

distinct classstructureid = 193；總列數 11,006；**重複率 98.2%**。

**分級**：🔴 **立即修復** — 新表 ETL 未套用 dedup
**建議**：將 v2 修好的 `ON CONFLICT (classstructureid) DO UPDATE` 同樣套用到此表。此表是資產分類 taxonomy 的來源，Week 1 必須先去重，否則接 KG 時分類節點會大量重複。

### 3.4 Domain value 中文翻譯衝突

```sql
SELECT _parent_key, value, COUNT(DISTINCT description)
  FROM maximo_zz_domain_alndomain
 GROUP BY 1,2 HAVING COUNT(DISTINCT description)>1;
```

結果：**0 筆**。

**分級**：🟢 相同 `(_parent_key, value)` 沒有不同 description，中文翻譯無衝突。

**v3 對比**：衝突 0 筆，維持 🟢 狀態。

---

## 4. 時間異常

### 4.1 未來日期 / 早於 2000 年

| 檢查 | 筆數 |
|------|------|
| `mxwo.reportdate` > NOW() | 0 |
| `mxwo.reportdate` < '2000-01-01' | 0 |
| `mxwo.actstart` > NOW() | 0 |
| `mxwo.actstart` < '2000-01-01' | 0 |
| `mxsr.reportdate` > NOW() | 0 |
| `mxsr.reportdate` < '2000-01-01' | 0 |
| `mxasset.statusdate` > NOW() | 0 |
| `mxasset.statusdate` < '2000-01-01' | 0 |

**分級**：🟢 **完美**

**v3 對比**：所有未來日期 / <2000 年檢查均為 0，維持 🟢 完美。

### 4.2 `actstart` > `actfinish`

```sql
SELECT COUNT(*) FROM maximo_mxwo
 WHERE actstart IS NOT NULL AND actfinish!=''
   AND actstart::timestamptz > actfinish::timestamptz;
```

| 指標 | 值 |
|------|----|
| 兩欄都有值 | 3,577 |
| actstart > actfinish | **0** |

**分級**：🟢 **完美**

**v3 對比**：兩欄都有值 2,925（去重後）、逆序 0 筆，維持 🟢 完美。

### 4.3 資料涵蓋期間偏窄

| 表 | 最早 | 最晚 | 跨度 |
|----|------|------|------|
| `mxwo.reportdate` | 2026-04-05 | 2026-04-16 | 11 天 |
| `mxwo.actstart` | 2025-05-05 | 2026-04-16 | ~11 個月 |
| `mxsr.reportdate` | 2025-07 | 2026-04 | ~9 個月 |

**分級**：🟡 非 data quality 問題，但會限制 KG 時序分析能力。
**建議**：Week 1 開始前先讓 ETL 補拉 `mxwo` 近 12 個月資料（這也是解決 1.4 的最終辦法）。

**v3 對比**：

| 表 | 最早 | 最晚 | 跨度 |
|----|------|------|------|
| `mxwo.reportdate` | **2026-04-05** | **2026-04-16** | **11 天（未改善）** |
| `mxwo.actstart` | 2025-05-05 | 2026-04-16 | 346 天 |
| `mxsr.reportdate` | 2025-07-09 | 2026-04-16 | 281 天 |
| `mxasset.statusdate` | 2021-06-29 | 2026-04-09 | 1,745 天 |

🔴 **`mxwo.reportdate` 仍卡在 11 天**，這是 1.4 連結斷裂的根因，v3 仍未處理。

---

## 5. 中文翻譯覆蓋率

### 5.1 `maximo_zz_domain` 主表

```sql
SELECT COUNT(*), COUNT(*) FILTER (WHERE description ~ '[一-龥]') AS chinese
  FROM maximo_zz_domain;
```

| 指標 | 值 | 比例 |
|------|----|------|
| 總 domain | 1,069 | 100% |
| 有 description | 1,029 | 96.3% |
| description 含中文 | 945 | **88.4%** |

**分級**：🟢 覆蓋率高。

**v3 對比**：1,069 / 1,029 / 945（含中文 88.4%）— 與 v2 完全一致。

### 5.2 `maximo_zz_domain_alndomain` ALN 項目

| 指標 | 值 | 比例 |
|------|----|------|
| 總項目 | 15,019 | 100% |
| 有 description | 13,147 | 87.5% |
| description 含中文 | 5,674 | **37.78%** |

**分級**：🟡 ALN 項目層 37.78% 偏低。
**建議**：KG 翻譯層應從 `domain.description`（父層 88.4%）優先取，次之才查 alndomain。

**v3 對比**：15,019 / 13,147 / 5,674（含中文 37.78%）— 與 v2 完全一致。

### 5.3 `maximo_zz_dept` 部門

| 指標 | 值 |
|------|----|
| 總數 | 40 |
| description 含中文 | **40（100%）** |

**分級**：🟢

**v3 對比**：40 / 40 中文，維持 🟢。

### 5.4 故障分類 FaultCode 中文覆蓋

`ZZ_FNM_FACTOR`（故障要因）有 6 個 value，value 自身就是中文（「設備故障」、「人為因素」…），description 為空。視為**已有中文意義**。

**分級**：🟢

---

## 6. Parent-key 循環偵測

### 6.1 `maximo_zz_dept` 遞迴

```sql
WITH RECURSIVE chain AS (
  SELECT parent, ma_deptid AS child, 1 AS depth FROM maximo_zz_dept WHERE parent!=''
  UNION ALL
  SELECT c.parent, d.ma_deptid, c.depth+1
    FROM chain c JOIN maximo_zz_dept d ON d.parent = c.child
   WHERE c.depth < 10
)
SELECT MAX(depth), COUNT(*) FROM chain;
```

| 指標 | 值 |
|------|----|
| 最大深度 | **1** |
| 循環偵測 | **0 筆** |
| distinct parent 值 | 1（只有 `MAY00`） |
| 指向不存在 parent | **34 筆**（parent=MAY00，而 MAY00 本身無 ma_deptid 記錄） |

**分級**：🟡 **可接受**
**建議**：組織結構其實是 2 層（機務處/處 → 機廠/機務段），但 `MAY00`（機務處）沒有自己的 `ma_deptid` 記錄。KG 建構時要嘛人工補一筆 MAY00 根節點，要嘛 parent 視為 NULL。

**v3 對比**：max_depth=1、chain_rows=34，維持 v2 狀態。

### 6.2 `maximo_zz_domain` 的 parent 結構

該表無明確 parent_id 欄位，`domaintype` 是分類而非父子關係；`maxdomainid` 為 PK 的數字版本。**無循環可查**。

**分級**：🟢 N/A

### 6.3 `maximo_zz_domain_alndomain` 的 `_parent_key`

```sql
SELECT COUNT(DISTINCT _parent_key) AS parents FROM maximo_zz_domain_alndomain;
```

| 指標 | 值 |
|------|----|
| distinct parents | 712 |
| orphan parents（第 1.5 節已算） | 1,658 列（11.04%） |
| 循環偵測 | **N/A**（alndomain 是 value 層級，不是層級結構） |

**分級**：🟢 結構上不會循環。

---

## 進入 Week 1 的建議

### v3 最終 GO / No-Go 決策：**有條件 GO**（條件從 v2 的 2 項調整為 3 項）

Week 1 啟動前必須完成：
1. ✅ mxwo/mxasset/mxsr ETL 去重（v2 已完成）
2. 🔴 **`maximo_mxasset_classstructure` ETL 去重**（新表 98.2% 重複）
3. 🔴 **mxwo 抓取窗擴大至 2025-07 以後**（修復 mxsr→mxwo 連結斷裂）
4. 🔴 **補抽 `maximo_mxasset.classstructure` 欄位**（否則新 classstructure 表無法 join）
5. 🟡 故障要因 4 欄 + 3 個新 description 欄位仍全空 — 走方案 B（Week 1 先不拆故障 taxonomy）

新 Action Item（相較 v2 新增）：
- 對 `maximo_mxasset_classstructure` 套用 dedup + 補 mxasset.classstructure 外鍵
- 抽樣驗證結果表示 **v2 期待的 `zz_repair_reason_description` 路線已證實不可行**（100% 空），不再保留該計畫。

---

### GO / No-Go 決策（v1 原版）：**有條件 GO**

**Clean subset 實際筆數**：
- 工單（去重後）：**7,995** distinct wonum ✅ 遠超 3,000 門檻
- 故障通報（去重、description>10字、assetnum 存在）：**375** distinct ticketid ❌ 不足
- 資產：**10,662** distinct assetnum ✅

### Week 1 前必須修的 4 個關鍵問題（🔴）

1. **ETL 去重**：mxwo 重複率 45%、mxasset 68%、mxsr 45%。在 Week 0 結束前補上 `ON CONFLICT DO UPDATE` 或至少建立 `SELECT DISTINCT` 的去重 view。這是所有下游 KG 工作的前提。
2. **故障通報 → 工單 連結斷裂**（zz_currwonum 只有 0.6% 能 join）：ETL 擴大 mxwo 抓取窗到 2025-07 至今，至少跟齊 mxsr 的時間範圍。
3. **`classstructure` 100% 空值**：Phase 3 KG 的資產分類層改用 `assettype` + `assetnum` prefix，Week 1 的 schema 設計要同步調整。
4. **故障要因 4 欄 99.5% 空值**：KG 的故障節點先只建「ticket → asset」骨架，不拆要因/事件/部件；Phase 3.2 再用 LLM 從 description 抽取。

### 可接受但需在 KG 中標註的（🟡）

1. 工單 `worktype` 10.19% 找不到 domain 翻譯（T1/T4 等）— 保留原值即可
2. `alndomain._parent_key` 11.04% 孤兒 — 資料足夠多不影響 KG
3. mxwo 資料僅 11 天（待 ETL 擴大抓取後解決）
4. zz_dept 的 parent=MAY00 無記錄 — 人工補 1 筆根節點
5. `mxsr` 故障詳情欄位空值 — 改用 description 文字

### 後續處理（🟢 Phase 3.2）

1. ALN domain 項目中文覆蓋 37.78% — Phase 3.2 人工補翻譯
2. 資產 `assettype` 68% 空值（大多是「無類型」本身就是語意）— Phase 3.2 用 assetnum prefix 分類
3. `maximo_assets` / `maximo_cm_workorders` / `maximo_pm_workorders` / `maximo_fault_reports` 舊表 — Phase 3.2 評估廢棄

### 建議的 Week 1 切入點

- **Day 1-2**：部署去重（修 🔴 #1），ETL 擴窗（修 🔴 #2）
- **Day 3**：以去重後 clean subset 7,995 工單 + 所有 10,662 資產 + 512 故障通報建 KG 骨架（Asset、WorkOrder、Ticket 三實體 + HAS_WO / REPORTED_ON 兩邊）
- **Day 4-5**：Domain 翻譯層注入（`maximo_zz_domain` 主表 945 筆中文）

---

> 本報告全程 SELECT only，無任何 DDL / DML 寫入。SQL 皆可重現於 `docker exec -i aikm-postgres psql -U aikm -d aikm -c "..."`。
