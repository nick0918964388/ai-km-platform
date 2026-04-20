# Review Report: W2-T3 Cypher Validator

日期: 2026-04-18 · Reviewer: Review Agent

審查目標：
- `/backend/app/services/cypher_validator.py`
- `/backend/tests/test_cypher_validator.py`

POC 測試：
- `/backend/tests/test_cypher_validator_review.py`（新增，未修改既有測試）

---

## 摘要

- **CRITICAL 問題**：2 個（必修才能交付）
- **HIGH 問題**：2 個
- **NICE-TO-HAVE**：3 個

POC 跑了 11 條攻擊/邊界測試：**8 passed / 3 failed**。
3 個 FAILED 代表：2 個真實繞過 + 1 個誤殺合法查詢。

---

## CRITICAL

### [C1] Unicode 零寬字元繞過黑名單（真實繞過）

- **問題描述**
  `_FORBIDDEN_RE` 使用 `\bDELETE\b` 等 word-boundary regex，但 `_strip_strings_and_comments` 不會正規化 unicode。攻擊者（或 LLM 幻覺/prompt injection）在關鍵字中間插入零寬字元就能完全繞過：
  - U+200B (zero-width space) — `DE\u200bLETE`
  - U+00AD (soft hyphen) — `DE\u00adLETE`
  - U+200C / U+200D / U+FEFF 同理

- **重現方式（POC）**
  ```python
  q = "MATCH (n) DE\u200bLETE n"
  ok, reasons, _ = validate_cypher(q)
  # 實際：ok=True, reasons=[]   ← 竟然通過！
  ```
  測試：`test_zero_width_inside_keyword_blocked` — FAILED
  測試：`test_soft_hyphen_inside_keyword_blocked` — FAILED

- **影響**
  Neo4j Cypher parser 在某些版本會容許 identifier 中的 zero-width 字元，或把 `DE\u200bLETE` 當成未知標識符拒絕；無論哪種，validator 讓這類異常輸入通過就是 fail-open，違反「safe-by-default」原則。若 Neo4j 任一版本接受，直接變成 RCE-等級寫入漏洞。

- **建議修法**
  在 `_strip_strings_and_comments` 開頭先做 unicode 正規化並刪除零寬字元：
  ```python
  import unicodedata
  _ZERO_WIDTH = dict.fromkeys(
      [0x200B, 0x200C, 0x200D, 0xFEFF, 0x00AD, 0x2060], None
  )
  def _strip_strings_and_comments(cypher: str) -> str:
      cypher = unicodedata.normalize("NFKC", cypher).translate(_ZERO_WIDTH)
      ...
  ```
  或更激進：直接 reject 含任何非 ASCII 控制字元的查詢（chat-to-cypher 的輸出本就該是純 ASCII）。

---

### [C2] 子查詢深度誤判 property map → 誤殺合法查詢（正確性）

- **問題描述**
  `max_depth_seen` 計算用裸 `{` `}` 字元配對。但 Cypher 中 `{` 同時是：
  1. `CALL { ... }` 子查詢
  2. property map：`{id: 1, name: 'x'}`
  3. 巢狀 map / JSON-like return
  四者語意完全不同，validator 全部當成子查詢計算深度。

- **重現方式（POC）**
  ```python
  q = "MATCH (n) RETURN {a: {b: {c: {d: {e: 1}}}}} AS x LIMIT 5"
  # 實際：ok=False, reasons=['subquery depth 5 exceeds max 3']
  ```
  測試：`test_property_maps_inflate_subquery_depth` — FAILED

- **影響**
  1. 合法查詢被誤殺（false positive，影響 Text2Cypher 召回率）
  2. 反向攻擊：攻擊者可把真實 `CALL { DELETE ... }` 藏在一堆 property-map 噪音中，但 subquery counter 不會誤判「寫入」—— 這是單純誤殺，非安全洞。

- **建議修法**
  真正要偵測 subquery 深度，應 match `\bCALL\s*\{` 的開頭配對：
  ```python
  # 用 tokenizer 或至少 regex 找 CALL { 開頭，再往後平衡配對
  call_block_re = re.compile(r"\bCALL\s*\{", re.IGNORECASE)
  ```
  把「CALL subquery 開頭」計數，忽略一般 `{` property map。
  或乾脆放寬 `max_subquery_depth` 到 10（Neo4j 實務極少 > 3）。

---

## HIGH

### [H1] UNION 自動 LIMIT 只作用於最後一段

- **問題描述**
  `_ensure_limit` 粗暴地在查詢尾端 append ` LIMIT 50`。但 Cypher UNION 語意下：
  ```cypher
  MATCH (n:A) RETURN n UNION MATCH (m:B) RETURN m LIMIT 50
  ```
  LIMIT 僅作用於 **最後一個 RETURN 子句**，第一段 `MATCH (n:A) RETURN n` 仍可回傳無上限行數。
  （Neo4j 5.x 對 UNION + 結尾 LIMIT 的語意是 parse 為最後 sub-query 的 LIMIT；整體結果仍可能超過預期。）

- **重現方式**
  ```python
  q = "MATCH (n:A) RETURN n UNION MATCH (m:B) RETURN m"
  # rewritten = "... UNION MATCH (m:B) RETURN m LIMIT 50"
  # 只限制 B, A 可能回傳 100,000 行
  ```
  測試：`test_union_without_any_limit_gets_rewritten` — PASSED（僅驗證有 append），但實質上 LIMIT 失效。

- **建議修法**
  檢測是否含 `\bUNION\b`，若有則改用外層包裝：
  ```python
  if re.search(r"\bUNION\b", sanitized, re.IGNORECASE):
      rewritten = f"CALL {{ {original_no_semicolon} }} WITH * LIMIT {self.max_limit}"
  ```
  或直接拒絕缺少 LIMIT 的 UNION 查詢（更保守）。

---

### [H2] 尾端行註解可能吞掉補注的 LIMIT

- **問題描述**
  若查詢尾端是行註解 `//`，`_ensure_limit` 直接 append 會變成 `... // LIMIT 50` — LIMIT 整段被視為註解內容，Neo4j 執行時沒有 LIMIT。

- **重現方式**
  ```python
  q = "MATCH (n) RETURN n //"
  # rewritten = "MATCH (n) RETURN n // LIMIT 50"
  # Neo4j 執行：無 LIMIT
  ```
  POC test `test_trailing_line_comment_does_not_hide_limit` 目前 PASS（驗證較寬鬆），但手動檢視 `rewritten` 確實有隱患。

- **建議修法**
  `_ensure_limit` 前先在 sanitized 上確認尾端沒有 `//` 未閉合的狀態；或改成在 append 前加換行：
  ```python
  return f"{trimmed}\nLIMIT {self.max_limit}"
  ```

---

## NICE-TO-HAVE

### [N1] 效能確認 OK
POC 未量測（既有 `test_performance_under_10ms` 已涵蓋）。單次 validate ~0.1ms 級，無 ReDoS 風險（所有 regex 都是 linear）。

### [N2] FOREACH / MERGE / 寫入類 procedure 已擋好
`apoc.cypher.runFirstColumn` 與 `apoc.cypher.parallel` 的 POC 都被 `apoc.cypher.run` 前綴正確攔截。FOREACH 被 `\bFOREACH\b` 擋。MERGE 已在黑名單。**這些都 OK。**

### [N3] 介面設計：建議回傳 dataclass
目前 `tuple[bool, list[str], str]` 難以擴充。改 `ValidationResult` dataclass 會更好維護（未來加 `severity`、`suggested_fix` 欄位不用改呼叫點）。

---

## POC 測試結果

```
tests/test_cypher_validator_review.py ... 11 collected
  ✓ test_apoc_cypher_runfirstcolumn_blocked
  ✓ test_apoc_cypher_parallel_blocked
  ✓ test_unterminated_string_does_not_crash
  ✓ test_string_then_real_delete_still_caught
  ✓ test_union_without_any_limit_gets_rewritten
  ✓ test_trailing_line_comment_does_not_hide_limit
  ✓ test_fullwidth_delete_is_harmless
  ✓ test_oversized_query_logs_truncated
  ✗ test_zero_width_inside_keyword_blocked       ← C1 真實繞過
  ✗ test_soft_hyphen_inside_keyword_blocked      ← C1 真實繞過
  ✗ test_property_maps_inflate_subquery_depth    ← C2 誤殺

8 passed, 3 failed in 0.03s
```

---

## 建議的修正優先序

1. **[C1] Unicode 零寬字元繞過** — 必修（2-3 行程式碼：NFKC + translate）
2. **[C2] Property map 誤判 subquery depth** — 必修（改 CALL `{` 專門計數）
3. **[H1] UNION + auto-LIMIT 語意錯誤** — 強烈建議（資料洩漏風險）
4. **[H2] 行註解吞 LIMIT** — 強烈建議（換行符 1 行即可修）
5. **[N3] 回傳型別改 dataclass** — 下個 sprint 再做

## GO / NO-GO 判定

**NO-GO** —— 有 1 個真實可利用的繞過（C1）+ 1 個會破壞 Text2Cypher 召回率的誤殺（C2）。
建議 Backend Agent 修掉 C1 + C2 後重跑 `tests/test_cypher_validator.py`（49 tests）+ `tests/test_cypher_validator_review.py`（11 tests），全綠再交付。

H1/H2 可排在同一輪修掉，成本很低（各 1-3 行）。
