"""
Maximo NL→SQL Service
Converts natural language to SQL targeting maximo_* tables.
Uses field metadata + few-shot examples from PostgreSQL for better accuracy.
Supports agentic self-verification loop (generate → validate → execute → verify).
"""

import os
import re
import json
import time
import hashlib
import logging
from typing import Optional, List, Dict, Any

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

log = logging.getLogger(__name__)

MAXIMO_SCHEMA = """
## Maximo 資料庫 Schema（PostgreSQL）

### maximo_assets（車輛主檔）
- assetnum VARCHAR(30) PK — 資產編號
- eq24 VARCHAR(30)        — 車號（如 EMU901-1）
- vehicle_type VARCHAR(20) — 車型（EMU900/EMU800/EMU3000/TEMU2000）
- vehicle_class VARCHAR(20) — 車種（EMU=電聯車, TEMU=傾斜式電聯車）
- vehicle_category VARCHAR(30) — 車輛類別代碼
- workshop VARCHAR(20)    — 維修機廠代碼
- section VARCHAR(20)     — 配屬段別代碼
- borrow_section VARCHAR(20) — 借用段別
- status VARCHAR(20)      — OPERATING/DECOMMISSIONED/INACTIVE
- status_desc VARCHAR(50) — 已啟用/停用/退役
- car_group VARCHAR(30)   — 所屬車組代碼
- position INTEGER        — 組內位置
- record_type VARCHAR(10) — 車輛/車組
- install_date TIMESTAMPTZ — 試運起始日期
- expected_life INTEGER   — 預期使用年限(年)
- manufacturer VARCHAR(30)

### maximo_pm_workorders（定期工單）
- wonum VARCHAR(30) PK
- description TEXT        — 工單說明（含車型+級別）
- status VARCHAR(30)      — 工單結案/工單初始/工單核准
- assetnum VARCHAR(30)    — 車組/車號（JOIN maximo_assets）
- work_type VARCHAR(10)   — 1A/2A/3A/4A（一級/二級/三級/四級定檢）
- owner_group VARCHAR(50) — 檢修單位
- maintenance_section VARCHAR(20) — 檢修段
- report_date TIMESTAMPTZ
- act_start TIMESTAMPTZ   — 實際開始日期
- act_finish TIMESTAMPTZ  — 完工日期
- last_act_finish TIMESTAMPTZ — 上次檢修日期
- car_in_result TEXT      — 進廠檢修結果
- car_out_result TEXT     — 出廠結果
- kilometers INTEGER

### maximo_cm_workorders（維修/臨修工單）
- wonum VARCHAR(30) PK
- description TEXT        — 故障說明
- long_description TEXT   — 故障詳細說明
- status VARCHAR(30)
- assetnum VARCHAR(30)    — 車號（JOIN maximo_assets）
- work_type VARCHAR(10)   — T1=一般臨修, TR=試車, CM=委外維修
- owner_group VARCHAR(50)
- maintenance_section VARCHAR(20)
- ticket_id VARCHAR(30)   — 關聯故障通報（JOIN maximo_fault_reports.ticketid）
- report_date TIMESTAMPTZ
- act_start TIMESTAMPTZ
- act_finish TIMESTAMPTZ
- target_start_date TIMESTAMPTZ — 預計進段日
- target_comp_date TIMESTAMPTZ  — 預計出段日
- failure_code VARCHAR(30)
- repair_proc TEXT        — 修復程序
- work_hours NUMERIC(8,2)

### maximo_fault_reports（故障通報）
- ticketid VARCHAR(30) PK
- im_num VARCHAR(30)      — 通報號
- description TEXT        — 故障概況
- fault_symptom TEXT      — 故障現象
- handling_desc TEXT      — 處理情形
- status VARCHAR(20)      — 立案/取消/結案
- status_desc VARCHAR(50)
- assetnum VARCHAR(30)    — 車號（JOIN maximo_assets）
- incident_class VARCHAR(50) — 事件分類（機務處）
- fault_location TEXT     — 故障位置
- tcms_code VARCHAR(30)   — TCMS故障碼
- grade VARCHAR(10)       — 故障等級
- urgency VARCHAR(20)     — 緊急程度
- restricted_status VARCHAR(20) — 列管狀態
- report_unit VARCHAR(50) — 通報單位
- occurrence_date TIMESTAMPTZ — 故障發生時間
- report_date TIMESTAMPTZ
- confirm_by VARCHAR(50)
- confirm_date TIMESTAMPTZ
- class_type VARCHAR(50)  — 進廠收容等
"""

# Static allowed tables (fallback when no extractor tables found)
STATIC_ALLOWED_TABLES = {
    "maximo_assets", "maximo_pm_workorders",
    "maximo_cm_workorders", "maximo_fault_reports",
}

FORBIDDEN_KEYWORDS = {
    "insert", "update", "delete", "drop", "truncate", "alter", "create",
    "grant", "revoke", "execute", "exec", "call", "shutdown", "copy",
    "pg_", "information_schema",
}


class MaximoNL2SQL:
    def __init__(self, db: AsyncSession):
        self.db = db
        provider = os.getenv("LLM_PROVIDER", "openai")
        if provider == "ollama":
            base_url = os.getenv("OLLAMA_CHAT_URL", "http://localhost:11434/v1")
            api_key = os.getenv("OLLAMA_CHAT_API_KEY", "ollama")
            self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            # Use light model for NL→SQL (faster, good enough for SQL generation)
            self.model = os.getenv("OLLAMA_LIGHT_MODEL",
                          os.getenv("OLLAMA_CHAT_MODEL", "gemma4:31b-cloud"))
        else:
            self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            self.model = os.getenv("OPENAI_MODEL", "gpt-4o")

        self._query_plan: Optional[Dict[str, Any]] = None

    # Column name → Chinese display label
    _COL_LABELS = {
        "wonum": "系統工單號", "wojp3": "工單號", "assetnum": "車號", "status": "狀態",
        "description": "說明", "worktype": "工作類型", "work_type": "工作類型",
        "reportdate": "通報日期", "report_date": "通報日期",
        "changedate": "變更日期", "act_start": "實際開始", "act_finish": "實際完工",
        "zz_actstart": "實際開始", "zz_actfinish": "實際完工",
        "owner_group": "負責單位", "ownergroup": "負責單位",
        "maintenance_section": "檢修段", "wol1": "檢修段",
        "eq24": "車號", "vehicle_type": "車型", "vehicle_class": "車種",
        "vehicle_category": "車輛類別", "workshop": "維修機廠",
        "section": "配屬段", "borrow_section": "借用段",
        "car_group": "車組", "position": "組內位置", "record_type": "記錄類型",
        "install_date": "試運日期", "expected_life": "預期年限",
        "manufacturer": "製造商", "failure_code": "故障碼",
        "ticketid": "通報號", "im_num": "通報號碼",
        "fault_symptom": "故障現象", "handling_desc": "處理情形",
        "incident_class": "事件分類", "fault_location": "故障位置",
        "tcms_code": "TCMS碼", "zz_tcms": "TCMS碼",
        "grade": "等級", "zz_im_grade": "故障等級",
        "urgency": "緊急程度", "zz_urgency": "緊急程度",
        "restricted_status": "列管狀態", "report_unit": "通報單位",
        "occurrence_date": "發生時間", "zz_entrydate": "發生日期",
        "confirm_by": "確認人", "confirm_date": "確認日期",
        "ticket_id": "關聯通報", "repair_proc": "修復程序",
        "work_hours": "工時", "target_start_date": "預計進段",
        "target_comp_date": "預計出段", "car_in_result": "進廠結果",
        "car_out_result": "出廠結果", "last_act_finish": "上次完工",
        "long_description": "詳細說明",
        "count": "筆數", "total": "合計", "total_reports": "通報總數",
        "order_count": "工單數", "cnt": "筆數",
        "zz_personbelong": "所屬單位", "zz_wol1": "檢修段",
        "zz_eq24": "車號", "statusdate": "狀態日期",
        "status_description": "狀態說明", "class": "分類",
        "class_description": "分類說明",
    }

    # Maximo objectname → our PostgreSQL table name
    _OBJ_TABLE = {
        "ASSET":     "maximo_mxasset",
        "WORKORDER": "maximo_mxwo",
        "SR":        "maximo_mxsr",
    }

    # Maximo attribute name → our PG column name (where they differ)
    _ATTR_COL = {
        "EQ24": "eq24", "EQ4": "vehicle_type", "EQ3": "vehicle_class",
        "EQ11": "vehicle_category", "EQ1": "workshop", "EQ2": "section",
        "EQ8": "borrow_section", "STATUS": "status", "ZZ_CARGROUP": "car_group",
        "ZZ_POSITION": "position", "EQ9": "record_type", "INSTALLDATE": "install_date",
        "EXPECTEDLIFE": "expected_life", "MANUFACTURER": "manufacturer",
        "WONUM": "wonum", "DESCRIPTION": "description", "ASSETNUM": "assetnum",
        "WORKTYPE": "work_type", "OWNERGROUP": "owner_group",
        "WOL1": "maintenance_section", "REPORTDATE": "report_date",
        "ACTSTART": "act_start", "ACTFINISH": "act_finish",
        "ZZ_ACTSTART": "act_start", "ZZ_ACTFINISH": "act_finish",
        "ZZ_LASTACTFINISH": "last_act_finish", "ZZ_CARIN": "car_in_result",
        "ZZ_CAROUT": "car_out_result", "TICKETID": "ticket_id",
        "ZZ_MAINSECTION": "maintenance_section",
        "ZZ_TARGSTARTDATE": "target_start_date", "ZZ_TARGCOMPDATE": "target_comp_date",
        "FAILURECODE": "failure_code", "ZZ_REPAIRPROC": "repair_proc",
        "WORK_HRS": "work_hours", "ZZ_IMNUM": "im_num",
        "ZZ_INCIDENT_NEW": "incident_class", "ZZ_IM_LOCATION": "fault_location",
        "ZZ_TCMS": "tcms_code", "ZZ_IM_GRADE": "grade", "ZZ_URGENCY": "urgency",
        "ZZ_RESTRICTED_STATUS": "restricted_status", "ZZ_PERSONBELONG": "report_unit",
        "ZZ_ENTRYDATE": "occurrence_date", "ZZ_CONFIRM_BY": "confirm_by",
        "ZZ_CONFIRM_DATE": "confirm_date", "CLASS": "class_type",
    }

    async def _build_schema_rag(self, question: str) -> tuple[str, set[str]]:
        """用 RAG 向量搜尋篩選相關表與欄位，減少 prompt 大小。
        回傳 (schema_text, allowed_tables)，失敗時回傳 ("", set())。
        """
        try:
            from app.services.maximo_schema_rag import MaximoSchemaRAG
            rag = MaximoSchemaRAG(self.db)
            schema_text, allowed_tables = await rag.build_schema(question)
            if schema_text:
                # Capture query plan from RAG
                self._query_plan = getattr(rag, '_query_plan', None)
                return schema_text, allowed_tables
        except Exception as e:
            log.warning("RAG schema 失敗: %s — 回退到完整 schema", e)
        return "", set()

    async def _build_schema_from_db(self) -> str:
        """從 maximo_zz_maxattribute 建立完整 schema（RAG fallback 用）。

        Returns empty string if table doesn't exist or is empty (falls back to MAXIMO_SCHEMA).
        """
        try:
            # Check if extractor attribute table exists and has rows
            cnt = await self.db.execute(text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name='maximo_zz_maxattribute'"
            ))
            if cnt.scalar() == 0:
                return ""
            cnt2 = await self.db.execute(text("SELECT COUNT(*) FROM maximo_zz_maxattribute"))
            if cnt2.scalar() == 0:
                return ""

            target_objs = list(self._OBJ_TABLE.keys())
            placeholders = ", ".join(f":o{i}" for i in range(len(target_objs)))
            params = {f"o{i}": v for i, v in enumerate(target_objs)}

            rows = await self.db.execute(text(
                f"SELECT objectname, attributename, title, domainid "
                f"FROM maximo_zz_maxattribute "
                f"WHERE objectname IN ({placeholders}) "
                f"AND persistent = 'True' "
                f"ORDER BY objectname, attributename"
            ), params)
            attrs = rows.fetchall()
            if not attrs:
                return ""

            # Load domain values via alndomain join
            # Chain: maxattribute.domainid → zz_domain.domainid → zz_domain.maxdomainid
            #        → alndomain._parent_key → alndomain.value / description
            domain_vals: dict[str, list[tuple[str, str]]] = {}
            try:
                drows = await self.db.execute(text(
                    """
                    SELECT d.domainid, a.value, a.description
                    FROM maximo_zz_domain d
                    JOIN maximo_zz_domain_alndomain a ON d.maxdomainid = a._parent_key
                    WHERE d.domainid IN (
                        SELECT DISTINCT domainid FROM maximo_zz_maxattribute
                        WHERE objectname IN ('ASSET','WORKORDER','SR')
                          AND domainid IS NOT NULL AND domainid != ''
                    )
                      AND a.value IS NOT NULL AND a.value != ''
                    ORDER BY d.domainid, a.value
                    """
                ))
                for dr in drows.fetchall():
                    domain_vals.setdefault(dr.domainid, []).append((dr.value, dr.description or ""))
            except Exception as de:
                log.warning("Domain value load failed: %s", de)

            from collections import defaultdict
            by_obj: dict[str, list] = defaultdict(list)
            for r in attrs:
                by_obj[r.objectname].append(r)

            lines = ["## Maximo 資料庫 Schema（從 maximo_zz_maxattribute 動態產生）"]
            for obj, tattrs in sorted(by_obj.items()):
                pg_table = self._OBJ_TABLE.get(obj, obj.lower())
                is_extractor = pg_table.startswith("maximo_mx")
                lines.append(f"\n### {pg_table}（Maximo {obj}）")
                for a in tattrs:
                    attr_upper = a.attributename.upper()
                    col_ref = a.attributename.lower() if is_extractor else self._ATTR_COL.get(attr_upper, a.attributename.lower())
                    label   = a.title or a.attributename
                    if a.domainid and a.domainid in domain_vals:
                        pairs = ", ".join(
                            f'"{v}"={desc}' if desc else f'"{v}"'
                            for v, desc in domain_vals[a.domainid][:20]
                        )
                        lines.append(f"- {col_ref} — {label}（值域：{pairs}）")
                    else:
                        lines.append(f"- {col_ref} — {label}")

            return "\n".join(lines)
        except Exception as e:
            log.warning("Dynamic schema build failed: %s — will use static schema", e)
            return ""

    async def _discover_tables(self) -> tuple[set, str]:
        """
        Discover available Maximo-related tables from PostgreSQL.
        Returns (allowed_table_names, schema_text).
        Includes both static maximo_* tables and extractor-created {tenant}_{obj} tables.
        """
        try:
            rows = await self.db.execute(text(
                """
                SELECT t.table_name,
                       array_agg(c.column_name ORDER BY c.ordinal_position) AS columns
                FROM information_schema.tables t
                JOIN information_schema.columns c
                  ON c.table_name = t.table_name AND c.table_schema = 'public'
                WHERE t.table_schema = 'public'
                  AND (
                    t.table_name LIKE 'maximo_%'
                    OR t.table_name ~ '^[a-z0-9_]+_mx[a-z]+'
                  )
                  AND t.table_name NOT LIKE '%_zz_max%'
                  AND t.table_name NOT LIKE '%_zz_domain%'
                  AND t.table_name NOT LIKE '%_attr_metadata'
                  AND t.table_name NOT LIKE '%_field_metadata'
                GROUP BY t.table_name
                ORDER BY t.table_name
                """
            ))
            results = rows.fetchall()
            if not results:
                return STATIC_ALLOWED_TABLES, MAXIMO_SCHEMA

            allowed = set()
            schema_lines = ["## 可用資料表（動態發現）"]
            for r in results:
                allowed.add(r.table_name)
                cols = ", ".join(r.columns[:30])  # cap at 30 cols for prompt size
                schema_lines.append(f"\n### {r.table_name}\n欄位：{cols}")

            return allowed, "\n".join(schema_lines)
        except Exception as e:
            log.warning("Table discovery failed: %s — using static schema", e)
            return STATIC_ALLOWED_TABLES, MAXIMO_SCHEMA

    async def _load_field_metadata(self) -> str:
        """Load value mappings + domain rules from maximo_field_metadata for prompt context.
        Also auto-discovers DISTINCT status values from actual data tables."""
        try:
            rows = await self.db.execute(text(
                "SELECT table_name, column_name, display_name, description, value_mapping "
                "FROM maximo_field_metadata"
            ))
            mapping_lines = ["## 欄位值域對應（重要：生成 SQL 時使用這些值）"]
            rule_lines = ["## 業務查詢規則（必須遵守）"]
            for r in rows.fetchall():
                if r.table_name == "_rules":
                    if r.description:
                        rule_lines.append(f"- {r.description}")
                else:
                    mapping = r.value_mapping if isinstance(r.value_mapping, dict) else {}
                    if mapping:
                        pairs = ", ".join(f'"{k}"={v}' for k, v in mapping.items())
                        mapping_lines.append(f"- {r.table_name}.{r.column_name}（{r.display_name}）：{pairs}")
                    elif r.description:
                        mapping_lines.append(f"- {r.table_name}.{r.column_name}（{r.display_name or r.column_name}）：{r.description}")

            # Auto-discover actual status values from data tables
            status_lines = ["## 資料庫中實際存在的狀態值（生成 SQL 時必須使用這些精確字串）"]
            status_queries = [
                ("maximo_mxwo",           "status", "工單狀態（extractor）"),
                ("maximo_mxsr",           "status", "故障通報狀態（extractor）"),
                ("maximo_mxasset",        "status", "車輛狀態（extractor）"),
                ("maximo_pm_workorders",  "status", "定期工單狀態"),
                ("maximo_cm_workorders",  "status", "維修工單狀態"),
                ("maximo_fault_reports",  "status", "故障通報狀態"),
                ("maximo_assets",         "status", "車輛狀態"),
            ]
            for tbl, col, label in status_queries:
                try:
                    res = await self.db.execute(text(
                        f"SELECT DISTINCT {col} FROM {tbl} WHERE {col} IS NOT NULL ORDER BY {col} LIMIT 20"
                    ))
                    vals = [str(r[0]) for r in res.fetchall() if r[0]]
                    if vals:
                        status_lines.append(f"- {tbl}.{col}（{label}）：{', '.join(repr(v) for v in vals)}")
                except Exception:
                    pass  # table may not exist yet

            return (
                "\n".join(rule_lines) + "\n\n" +
                "\n".join(status_lines) + "\n\n" +
                "\n".join(mapping_lines)
            )
        except Exception as e:
            log.warning("Failed to load field metadata: %s", e)
            return ""

    async def _load_examples(self) -> str:
        """Load verified NL→SQL examples as few-shot prompts."""
        try:
            rows = await self.db.execute(text(
                "SELECT question, sql_query FROM nl_sql_examples WHERE verified=true LIMIT 6"
            ))
            lines = ["## 範例問答（Few-shot）"]
            for r in rows.fetchall():
                lines.append(f"問：{r.question}")
                lines.append(f"SQL：{r.sql_query}")
                lines.append("")
            return "\n".join(lines)
        except Exception as e:
            log.warning("Failed to load examples: %s", e)
            return ""

    async def _get_preferred_columns(self, table_name: str) -> list[str]:
        """Get admin-configured preferred columns for a table."""
        try:
            result = await self.db.execute(text(
                "SELECT column_name FROM table_column_config WHERE table_name = :t ORDER BY display_order"
            ), {"t": table_name})
            cols = [r[0] for r in result.fetchall()]
            return cols if cols else []
        except Exception:
            return []

    async def generate_sql(self, question: str, feedback: str = None, history: list = None) -> Dict[str, Any]:
        """Generate SQL from natural language question."""
        # 優先嘗試 RAG schema（只傳相關表與欄位）
        rag_schema, rag_tables = await self._build_schema_rag(question)
        if rag_schema:
            schema_text = rag_schema
            allowed_tables = rag_tables
            log.info("使用 RAG schema（%d 表）", len(rag_tables))
        else:
            # Fallback: 完整 schema
            allowed_tables, schema_text = await self._discover_tables()
            dynamic_schema = await self._build_schema_from_db()
            if dynamic_schema:
                schema_text = dynamic_schema
            self._query_plan = {
                "selected_tables": sorted(allowed_tables),
                "selected_columns": {},
                "schema_source": "full_dump",
            }

        self._allowed_tables = allowed_tables  # store for validate_sql

        metadata = await self._load_field_metadata()
        examples = await self._load_examples()

        # Load preferred columns hint per table
        preferred_hints = []
        for tbl in sorted(allowed_tables):
            preferred_cols = await self._get_preferred_columns(tbl)
            if preferred_cols:
                preferred_hints.append(f"注意：{tbl} 的預設顯示欄位為：{', '.join(preferred_cols)}。請優先使用這些欄位。")
        preferred_section = "\n".join(preferred_hints)

        table_list = ", ".join(sorted(allowed_tables))
        system_prompt = f"""你是台鐵車輛維修資料庫的 SQL 專家。
將使用者的自然語言問題轉換為 PostgreSQL SELECT 語句。

{schema_text}

{metadata}

{examples}

{preferred_section}

規則：
1. 只產生 SELECT 查詢（不允許 INSERT/UPDATE/DELETE）
2. 只能查詢以下表：{table_list}
3. 多表查詢時必須使用正確的 JOIN
4. 預設 LIMIT 50，除非使用者指定
5. 日期欄位使用標準 SQL 日期比較

多輪對話規則：
- 如果對話歷史中有前一個查詢，請判斷當前問題是否為延續（follow-up）。
- 判斷方式：如果當前問題使用了「這些」「上面的」「那些」「列出」「詳細」等指代詞，或與前一次查詢主題相同（相同的表或實體），則為 follow-up，應延續前次的 WHERE 條件。
- 如果當前問題明確提到新的實體（如不同的車號、車型、時間範圍），則為新查詢，不應延續前次條件。
- follow-up 範例：前次查「EMU 有幾種車型」→ 接著問「列出這些車型」→ 應帶上 vehicle_class = 'EMU' 條件。
- 非 follow-up 範例：前次查「EMU900 狀態」→ 接著問「TEMU2000 的狀態」→ 這是新查詢。

只輸出 JSON，格式：
{{
  "sql": "SELECT ...",
  "explanation": "這個查詢的說明",
  "tables": ["用到的表名"]
}}

如果無法轉換：
{{
  "error": "原因",
  "sql": null
}}
"""
        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # Build user message with explicit context from previous queries
        user_msg = question
        if history:
            prev_parts = []
            for h in history[-3:]:
                q = h.get("question", "")
                sql = h.get("sql", "")
                if q and sql:
                    prev_parts.append(f"問題：{q}\nSQL：{sql}")
            if prev_parts:
                context_block = "\n---\n".join(prev_parts)
                user_msg = f"""以下是之前的對話查詢紀錄：
{context_block}

---
當前問題：{question}
（如果當前問題是延續前次查詢，請保留前次的 WHERE 條件；如果是新主題則忽略前次條件）"""

        messages.append({"role": "user", "content": user_msg})

        if feedback:
            messages.append({"role": "assistant", "content": "我上次產生的 SQL 有問題。"})
            messages.append({"role": "user", "content": f"上次的問題：{feedback}\n請重新產生正確的 SQL。"})

        try:
            t_llm = time.monotonic()
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0,
                timeout=60,
            )
            self._llm_ms = round((time.monotonic() - t_llm) * 1000, 1)
            content = resp.choices[0].message.content or ""
            # Extract JSON block if wrapped in markdown
            match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if match:
                content = match.group(1)
            else:
                # Try to find first { ... } block
                brace = content.find('{')
                if brace != -1:
                    content = content[brace:]
                    # find matching closing brace
                    depth, end = 0, -1
                    for i, c in enumerate(content):
                        if c == '{': depth += 1
                        elif c == '}':
                            depth -= 1
                            if depth == 0:
                                end = i + 1
                                break
                    if end != -1:
                        content = content[:end]
            result = json.loads(content)
            result["_model"] = self.model
            result["_llm_ms"] = getattr(self, "_llm_ms", None)
            return result
        except Exception as e:
            return {"error": str(e), "sql": None}

    def validate_sql(self, sql: str) -> Optional[str]:
        """Return error string if invalid, None if ok."""
        if not sql:
            return "SQL 為空"
        s = sql.lower()
        if not s.strip().startswith("select"):
            return "只允許 SELECT 查詢"
        for kw in FORBIDDEN_KEYWORDS:
            if re.search(rf'\b{kw}\b', s):
                return f"不允許的關鍵字：{kw}"
        if "--" in sql or "/*" in sql:
            return "不允許 SQL 注解"
        if ";" in sql.rstrip(";"):
            return "不允許多個語句"
        # Use dynamic allowed tables (set in generate_sql), fallback to static
        allowed = getattr(self, '_allowed_tables', STATIC_ALLOWED_TABLES)
        # Remove EXTRACT(...FROM...) and similar function usages before checking table names
        cleaned = re.sub(r'extract\s*\([^)]*\)', '', s, flags=re.IGNORECASE)
        cleaned = re.sub(r'::\w+', '', cleaned)  # remove PostgreSQL type casts like ::date
        tables = re.findall(r'\b(?:from|join)\s+(\w+)', cleaned)
        for t in tables:
            if t not in allowed and t not in {"lateral", "unnest", "generate_series"}:
                return f"不允許存取的表：{t}"
        return None

    async def execute_sql(self, sql: str, params: dict = None) -> Dict[str, Any]:
        """Execute SQL and return rows + columns."""
        t0 = time.monotonic()
        try:
            result = await self.db.execute(text(sql), params or {})
            cols = list(result.keys())
            rows = [dict(zip(cols, row)) for row in result.fetchall()]
            # Serialize non-JSON-serializable types
            for row in rows:
                for k, v in row.items():
                    if hasattr(v, 'isoformat'):
                        row[k] = v.isoformat()
                    elif v is None:
                        row[k] = None
            return {
                "columns": cols,
                "rows": rows,
                "row_count": len(rows),
                "execution_ms": round((time.monotonic() - t0) * 1000, 1),
            }
        except Exception as e:
            # Rollback failed transaction so next query can proceed
            try:
                await self.db.rollback()
            except Exception:
                pass
            return {"error": str(e), "rows": [], "columns": [], "row_count": 0}

    def _rule_validate(self, question: str, sql: str, result: Dict) -> list[str]:
        """Rule-based validation. Returns list of issues (empty = pass)."""
        issues = []
        q = question.lower()
        s = sql.lower()

        # Question asks for count but SQL doesn't use COUNT
        if any(kw in q for kw in ["幾筆", "幾台", "幾張", "多少", "數量", "統計"]):
            if "count" not in s and "count(*)" not in s:
                issues.append("問題要求統計數量，但 SQL 未使用 COUNT 函數")

        # 0 rows might indicate wrong table or condition
        if result.get("row_count", 0) == 0:
            issues.append("查詢結果為 0 筆，可能查錯表或 WHERE 條件有誤，請檢查狀態值是否正確")

        # Question mentions time but SQL has no date filter
        if any(kw in q for kw in ["最近", "今年", "上月", "去年", "本月", "上週"]):
            if not any(kw in s for kw in ["date", "time", "now()", "interval", "current_", "extract"]):
                issues.append("問題涉及時間範圍，但 SQL 未包含日期條件")

        # Question asks for ranking/top but no ORDER BY + LIMIT
        if any(kw in q for kw in ["最多", "最常", "排名", "前幾", "top"]):
            if "order by" not in s:
                issues.append("問題要求排名/排序，但 SQL 未使用 ORDER BY")

        return issues

    async def _llm_verify(self, question: str, sql: str, result: Dict) -> Dict:
        """LLM-based verification. Returns {passed, confidence, issues, feedback}."""
        row_count = result.get('row_count', 0)
        columns = result.get('columns', [])
        # Only send first row as sample (lighter prompt for speed)
        sample = result.get("rows", [])[:1]
        sample_str = json.dumps(sample, ensure_ascii=False, default=str)[:500] if sample else "無資料"

        verify_prompt = f"""/no_think
驗證 SQL 查詢是否正確回答問題。

問題：{question}
SQL：{sql}
結果：{row_count} 筆，欄位 {columns}
樣本：{sample_str}

檢查：1.正確的表？ 2.WHERE 條件正確？ 3.欄位涵蓋問題所需？

回覆 JSON：{{"passed": true/false, "confidence": 0-1, "issues": [], "feedback": ""}}"""

        try:
            t_verify = time.monotonic()
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": verify_prompt}],
                temperature=0,
                max_tokens=300,
            )
            self._verify_ms = round((time.monotonic() - t_verify) * 1000, 1)
            content = resp.choices[0].message.content or ""
            # Parse JSON (same extraction logic as generate_sql)
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                parsed.setdefault("passed", True)
                parsed.setdefault("confidence", 0.5)
                parsed.setdefault("issues", [])
                parsed.setdefault("feedback", "")
                return parsed
            return {"passed": True, "confidence": 0.5, "issues": ["無法解析驗證結果"], "feedback": ""}
        except Exception as e:
            log.warning("LLM 驗證失敗: %s", e)
            return {"passed": True, "confidence": 0.5, "issues": [], "feedback": ""}

    async def _load_user_permissions(self, user_context: dict) -> dict:
        """Load permission group settings for the current user."""
        if not user_context or user_context.get("role") == "admin":
            return {"allow_freeform": True, "allowed_tables": set(), "row_filters": {}, "max_results": 500}

        user_id = user_context.get("id", "guest")
        try:
            result = await self.db.execute(text("""
                SELECT pg.allowed_tables, pg.row_filters, pg.hidden_columns,
                       pg.allow_freeform, pg.max_results,
                       up.section, up.workshop
                FROM user_permissions up
                JOIN permission_groups pg ON pg.id = up.group_id
                WHERE up.user_id = :uid
                LIMIT 1
            """), {"uid": user_id})
            row = result.fetchone()
        except Exception as e:
            log.warning("載入使用者權限失敗: %s", e)
            row = None

        if not row:
            return {"allow_freeform": False, "allowed_tables": set(), "row_filters": {}, "max_results": 20, "section": "", "workshop": ""}

        return {
            "allow_freeform": row.allow_freeform,
            "allowed_tables": set(row.allowed_tables) if row.allowed_tables else set(),
            "row_filters": row.row_filters or {},
            "hidden_columns": row.hidden_columns or {},
            "max_results": row.max_results or 100,
            "section": row.section or "",
            "workshop": row.workshop or "",
        }

    def _inject_row_filters(self, sql: str, filters: dict, user_context: dict) -> tuple[str, dict]:
        """Inject row-level security WHERE clauses using parameterized approach.
        Returns (modified_sql, extra_params)."""
        section = (user_context or {}).get("section", "")
        workshop = (user_context or {}).get("workshop", "")

        if not section and not workshop:
            return sql, {}

        conditions = []
        params = {}
        for table, condition_template in filters.items():
            if table.lower() in sql.lower():
                if "{section}" in condition_template and section:
                    safe_cond = condition_template.replace("'{section}'", ":_perm_section")
                    params["_perm_section"] = section
                    conditions.append(safe_cond)
                if "{workshop}" in condition_template and workshop:
                    safe_cond = condition_template.replace("'{workshop}'", ":_perm_workshop")
                    params["_perm_workshop"] = workshop
                    conditions.append(safe_cond)
                break  # Only apply first matching filter

        if conditions and params:
            filter_clause = " AND ".join(conditions)
            sql = f"SELECT * FROM ({sql}) AS _filtered WHERE {filter_clause}"

        return sql, params

    async def _write_audit_log(self, user_context: dict, question: str, sql: str, result: dict):
        """Write query to audit log."""
        try:
            user_id = (user_context or {}).get("id", "guest")
            user_email = (user_context or {}).get("email", "")
            tables = re.findall(r'\b(?:from|join)\s+(\w+)', (sql or "").lower())
            request_id = result.get("request_id") or getattr(self, '_request_id', None)
            await self.db.execute(text("""
                INSERT INTO query_audit_log (user_id, user_email, question, sql_generated, tables_accessed, row_count, execution_ms, mode, request_id)
                VALUES (:uid, :email, :q, :sql, :tables, :rows, :exec_ms, :mode, :rid)
            """), {
                "uid": user_id, "email": user_email, "q": question,
                "sql": sql, "tables": list(set(tables)),
                "rows": result.get("row_count", 0),
                "exec_ms": result.get("execution_ms"),
                "mode": "nl2sql",
                "rid": request_id,
            })
            await self.db.commit()
        except Exception as e:
            log.warning("寫入稽核日誌失敗: %s", e)

    async def _get_column_labels(self, columns: list) -> Dict[str, str]:
        """Get Chinese labels for columns. Priority: custom_column_labels DB > static _COL_LABELS > maximo_zz_maxattribute."""
        labels = {}

        # 1) Load custom labels from DB first
        try:
            result = await self.db.execute(text("SELECT column_name, label FROM custom_column_labels"))
            custom = {r[0]: r[1] for r in result.fetchall()}
            for c in columns:
                col_lower = c.lower()
                if col_lower in custom:
                    labels[c] = custom[col_lower]
        except Exception:
            pass

        # 2) Static _COL_LABELS fallback
        missing = []
        for c in columns:
            if c in labels:
                continue
            static = self._COL_LABELS.get(c.lower())
            if static:
                labels[c] = static
            else:
                missing.append(c)

        if missing:
            try:
                placeholders = ", ".join(f":c{i}" for i in range(len(missing)))
                params = {f"c{i}": v.upper() for i, v in enumerate(missing)}
                rows = await self.db.execute(text(
                    f"SELECT attributename, title FROM maximo_zz_maxattribute "
                    f"WHERE UPPER(attributename) IN ({placeholders}) AND title IS NOT NULL "
                    f"LIMIT {len(missing)}"
                ), params)
                for r in rows.fetchall():
                    labels[r.attributename.lower()] = r.title
                    # Also map original case
                    for c in missing:
                        if c.lower() == r.attributename.lower():
                            labels[c] = r.title
            except Exception:
                pass

        # Fill any still-missing with original name
        for c in columns:
            if c not in labels:
                labels[c] = c
        return labels

    def _generate_summary(self, columns: list, data: list, row_count: int) -> Optional[str]:
        """Auto-generate summary stats for large result sets."""
        if row_count <= 10 or not data or not columns:
            return None

        parts = [f"共 {row_count} 筆結果"]

        for col in columns:
            values = [row.get(col) for row in data if row.get(col) is not None]
            if not values:
                continue

            # Count distinct
            unique = set(str(v) for v in values)
            if 2 <= len(unique) <= 20 and len(unique) < len(values) * 0.8:
                parts.append(f"{col} 共 {len(unique)} 種")

            # Numeric stats
            nums = [v for v in values if isinstance(v, (int, float))]
            if nums and len(nums) > 5:
                total = sum(nums)
                parts.append(f"{col} 合計 {total:,.0f}")

        return "｜".join(parts) if len(parts) > 1 else None

    def _suggest_chart(self, question: str, sql: str, result: Dict) -> Optional[Dict]:
        """Analyze SQL + result to suggest chart type. Returns None if table is best."""
        if not result.get("columns") or result.get("row_count", 0) == 0:
            return None

        cols = result["columns"]
        rows = result.get("rows", [])
        s = sql.lower()
        q = question.lower()

        # Detect aggregation queries
        has_count = "count(" in s or "count(*)" in s
        has_sum = "sum(" in s
        has_avg = "avg(" in s
        has_group_by = "group by" in s
        has_order_by = "order by" in s

        # Detect date columns
        date_cols = [c for c in cols if any(kw in c.lower() for kw in ["date", "time", "month", "year", "日期", "時間"])]

        # Detect numeric columns (check first row values)
        numeric_cols = []
        text_cols = []
        if rows:
            for c in cols:
                val = rows[0].get(c)
                if isinstance(val, (int, float)):
                    numeric_cols.append(c)
                elif val is not None:
                    text_cols.append(c)

        # Rule 1: GROUP BY + COUNT/SUM → Bar chart
        if has_group_by and (has_count or has_sum or has_avg):
            x_col = text_cols[0] if text_cols else cols[0]
            y_col = numeric_cols[0] if numeric_cols else cols[-1]

            # If only 2-5 categories → Pie chart might be better
            if result["row_count"] <= 5 and has_count:
                return {"type": "pie", "name_key": x_col, "value_key": y_col, "title": f"{x_col} 分布"}

            return {"type": "bar", "x_key": x_col, "y_key": y_col, "title": f"{x_col} 統計"}

        # Rule 2: Date column + numeric → Line chart
        if date_cols and numeric_cols and has_order_by:
            return {"type": "line", "x_key": date_cols[0], "y_key": numeric_cols[0], "title": f"{numeric_cols[0]} 趨勢"}

        # Rule 3: Date in question keywords → suggest line if date + count
        if any(kw in q for kw in ["趨勢", "變化", "走勢", "歷史"]) and date_cols:
            y = numeric_cols[0] if numeric_cols else "count"
            return {"type": "line", "x_key": date_cols[0], "y_key": y, "title": "趨勢圖"}

        # Default: no chart suggestion (use table)
        return None

    async def _suggest_alternatives(self, sql: str, question: str, table_name: str = None) -> list:
        """When query returns 0 results, analyze SQL and suggest alternatives."""
        suggestions = []
        s = sql.lower()

        # Extract main table name
        table_match = re.search(r'\bfrom\s+(\w+)', s)
        if not table_match:
            return suggestions
        table = table_match.group(1)

        # Extract WHERE conditions: col operator 'value'
        conditions = re.findall(r"(\w+)\s*(?:=|!=|<>|LIKE|like|ILIKE)\s*'([^']*)'", sql)

        # 1. For each string condition, check DISTINCT values
        for col, value in conditions:
            col_lower = col.lower()
            # Skip date-related columns for this check
            if any(d in col_lower for d in ['date', 'time', 'start', 'finish']):
                continue
            try:
                result = await self.db.execute(text(
                    f"SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL ORDER BY {col} LIMIT 15"
                ))
                actual_values = [str(r[0]) for r in result.fetchall() if r[0]]
                await self.db.rollback()  # reset any transaction state

                if actual_values and value not in actual_values:
                    # Value doesn't exist — show actual values
                    # Find closest matches
                    close_matches = [v for v in actual_values if value.lower() in v.lower() or v.lower() in value.lower()]

                    if close_matches:
                        for match in close_matches[:2]:
                            new_q = question.replace(value, match)
                            suggestions.append({
                                "label": f"改查 {col}='{match}'",
                                "query": new_q if new_q != question else f"{question}（{col}={match}）",
                            })
                    else:
                        # Show available values as options
                        vals_preview = "、".join(actual_values[:8])
                        suggestions.append({
                            "label": f"{col} 欄位現有值：{vals_preview}",
                            "query": question,  # same query, just informational
                            "type": "info",
                        })
                        # Offer top 2 actual values as clickable options
                        for av in actual_values[:2]:
                            suggestions.append({
                                "label": f"查 {col}='{av}' 的資料",
                                "query": question.replace(value, av) if value in question else f"{question}（改用 {col}={av}）",
                            })
            except Exception as e:
                log.debug("Alternative check failed for %s.%s: %s", table, col, e)
                try:
                    await self.db.rollback()
                except Exception:
                    pass

        # 2. For date conditions, check alternative date columns
        date_conditions = re.findall(r"(\w+)\s*(?:>=|<=|>|<)\s*'([\d-]+)'", sql)
        if date_conditions:
            used_date_col = date_conditions[0][0]
            try:
                # Find all timestamp columns in the table
                cols_result = await self.db.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = :tbl AND (data_type LIKE '%timestamp%' OR data_type LIKE '%date%')"
                ), {"tbl": table})
                date_cols = [r.column_name for r in cols_result.fetchall()]

                for dcol in date_cols:
                    if dcol.lower() == used_date_col.lower():
                        continue
                    try:
                        cnt_result = await self.db.execute(text(
                            f"SELECT COUNT(*) FROM {table} WHERE {dcol} IS NOT NULL"
                        ))
                        cnt = cnt_result.scalar() or 0
                        await self.db.rollback()
                        if cnt > 0:
                            suggestions.append({
                                "label": f"改用 {dcol} 欄位查詢（{cnt:,} 筆有資料）",
                                "query": question + f"（使用 {dcol} 欄位）",
                            })
                    except Exception:
                        try:
                            await self.db.rollback()
                        except Exception:
                            pass
            except Exception:
                pass

        # 3. Suggest removing filters
        if date_conditions or conditions:
            clean_question = question
            for kw in ["本月", "最近一週", "最近一個月", "今年", "上月", "去年"]:
                clean_question = clean_question.replace(kw, "")
            clean_question = clean_question.strip()
            if clean_question and clean_question != question:
                suggestions.append({
                    "label": "移除時間條件，查看所有資料",
                    "query": clean_question,
                })

        # 4. Suggest alternative tables
        alt_tables = {
            "maximo_pm_workorders": ("maximo_mxwo", "extractor 原始工單"),
            "maximo_cm_workorders": ("maximo_mxwo", "extractor 原始工單"),
            "maximo_assets": ("maximo_mxasset", "extractor 原始資產"),
            "maximo_fault_reports": ("maximo_mxsr", "extractor 原始故障通報"),
            "maximo_mxwo": ("maximo_pm_workorders", "ETL 定期工單"),
            "maximo_mxsr": ("maximo_fault_reports", "ETL 故障通報"),
        }
        if table in alt_tables:
            alt, desc = alt_tables[table]
            suggestions.append({
                "label": f"改查 {alt}（{desc}）",
                "query": question + f"（使用 {alt}）",
            })

        return suggestions[:5]  # Cap at 5 suggestions

    async def query(self, question: str, mode: str = "accurate", user_context: dict = None, conversation_history: list = None) -> Dict[str, Any]:
        """Full pipeline with optional verification loop.
        mode: 'fast' (no verification) or 'accurate' (with verification loop)
        """
        # Permission check
        perm = await self._load_user_permissions(user_context)
        if not perm.get("allow_freeform", True):
            return {"success": False, "error": "您的帳戶不允許自由查詢，請使用範例查詢",
                    "sql": None, "explanation": None, "data": [], "columns": [],
                    "row_count": 0, "model": self.model, "llm_ms": None, "verify_ms": None,
                    "iterations": 0, "confidence": 0.0, "verification_history": [],
                    "mode": mode, "cached": False, "query_plan": None}

        # Check Redis cache for SQL (only caches the generated SQL, not data)
        role = (user_context or {}).get("role", "guest")
        cache_key = f"nl2sql_sql:{role}:{hashlib.md5(question.encode()).hexdigest()}"
        redis_conn = None
        cached_sql = None
        try:
            import redis.asyncio as aioredis
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
            redis_conn = aioredis.from_url(redis_url)
            cached_raw = await redis_conn.get(cache_key)
            if cached_raw:
                cached_sql = json.loads(cached_raw)  # {"sql": "...", "explanation": "...", "model": "..."}
        except Exception:
            pass

        # If cached SQL exists, skip LLM generation and execute directly
        # (SQL was already validated when first cached, skip re-validation)
        if cached_sql and cached_sql.get("sql"):
            sql = cached_sql["sql"]
            result = await self.execute_sql(sql)
            if not result.get("error"):
                    final = {
                        "success": True,
                        "sql": sql,
                        "explanation": cached_sql.get("explanation"),
                        "data": result["rows"],
                        "columns": result["columns"],
                        "row_count": result["row_count"],
                        "execution_ms": result.get("execution_ms"),
                        "llm_ms": None,
                        "verify_ms": None,
                        "model": cached_sql.get("model"),
                        "iterations": 0,
                        "confidence": cached_sql.get("confidence"),
                        "verification_history": [],
                        "mode": mode,
                        "cached": True,
                        "query_plan": None,
                        "summary": self._generate_summary(result["columns"], result["rows"], result["row_count"]),
                        "suggestions": [],
                        "column_labels": await self._get_column_labels(result["columns"]),
                    }
                    if redis_conn:
                        try: await redis_conn.aclose()
                        except Exception: pass
                    return final

        max_iter = 3 if mode == "accurate" else 2  # fast mode: 1 generation + 1 auto-retry on error
        history: List[Dict[str, Any]] = []
        last_result: Optional[Dict[str, Any]] = None
        final_confidence = None

        for attempt in range(max_iter):
            feedback = history[-1].get("feedback") if history else None

            # 1. Generate SQL
            gen = await self.generate_sql(question, feedback=feedback, history=conversation_history)
            model_name = gen.get("_model", self.model)
            llm_ms = gen.get("_llm_ms")

            if gen.get("error") or not gen.get("sql"):
                history.append({
                    "attempt": attempt + 1,
                    "sql": None,
                    "error": gen.get("error", "無法產生 SQL"),
                    "feedback": gen.get("error", "無法產生 SQL"),
                })
                continue

            sql = gen["sql"]

            # 2. Validate SQL
            err = self.validate_sql(sql)
            if err:
                history.append({
                    "attempt": attempt + 1,
                    "sql": sql,
                    "error": f"SQL 驗證失敗：{err}",
                    "feedback": f"SQL 驗證失敗：{err}",
                })
                continue

            # 2b. Permission-based table access check
            if perm.get("allowed_tables"):
                tables_in_sql = re.findall(r'\b(?:from|join)\s+(\w+)', sql.lower())
                for t in tables_in_sql:
                    if t not in perm["allowed_tables"] and t not in {"lateral", "unnest"}:
                        history.append({
                            "attempt": attempt + 1,
                            "sql": sql,
                            "error": f"您沒有權限查詢 {t}",
                            "feedback": f"權限不足：無法查詢 {t}",
                        })
                        break
                else:
                    pass  # all tables allowed
                if history and history[-1].get("attempt") == attempt + 1 and "權限" in history[-1].get("error", ""):
                    continue

            # 2c. Inject row filters
            row_filter_params: dict = {}
            if perm.get("row_filters"):
                sql, row_filter_params = self._inject_row_filters(sql, perm["row_filters"], user_context)

            # 3. Execute SQL
            result = await self.execute_sql(sql, row_filter_params)
            if result.get("error"):
                history.append({
                    "attempt": attempt + 1,
                    "sql": sql,
                    "error": result["error"],
                    "feedback": f"SQL 執行錯誤：{result['error']}",
                })
                continue

            # 4. Rule-based validation
            rule_issues = self._rule_validate(question, sql, result)
            if rule_issues and attempt < max_iter - 1:
                feedback_text = "；".join(rule_issues)
                history.append({
                    "attempt": attempt + 1,
                    "sql": sql,
                    "row_count": result.get("row_count", 0),
                    "rule_issues": rule_issues,
                    "feedback": feedback_text,
                })
                continue

            # 5. LLM verification (only in accurate mode, skip on last attempt)
            verify_result = None
            if mode == "accurate" and attempt < max_iter - 1:
                verify_result = await self._llm_verify(question, sql, result)
                if not verify_result.get("passed", True) and verify_result.get("feedback"):
                    all_issues = rule_issues + verify_result.get("issues", [])
                    feedback_text = verify_result["feedback"]
                    if rule_issues:
                        feedback_text = "；".join(rule_issues) + "；" + feedback_text
                    history.append({
                        "attempt": attempt + 1,
                        "sql": sql,
                        "row_count": result.get("row_count", 0),
                        "rule_issues": rule_issues,
                        "llm_verify": verify_result,
                        "verify_ms": getattr(self, "_verify_ms", None),
                        "feedback": feedback_text,
                    })
                    continue

            # All passed — build final result
            if verify_result:
                final_confidence = verify_result.get("confidence", 0.8)
            elif rule_issues:
                final_confidence = 0.6
            else:
                final_confidence = 0.85 if mode == "fast" else 0.9

            history.append({
                "attempt": attempt + 1,
                "sql": sql,
                "row_count": result.get("row_count", 0),
                "rule_issues": rule_issues,
                "llm_verify": verify_result,
                "verify_ms": getattr(self, "_verify_ms", None),
                "passed": True,
            })

            # Chart suggestion (rule-based, no LLM) + column labels (parallel with verify if needed)
            chart_suggestion = self._suggest_chart(question, sql, result)
            column_labels = await self._get_column_labels(result["columns"])

            last_result = {
                "success": True,
                "sql": sql,
                "explanation": gen.get("explanation"),
                "data": result["rows"],
                "columns": result["columns"],
                "row_count": result["row_count"],
                "execution_ms": result.get("execution_ms"),
                "model": model_name,
                "llm_ms": llm_ms,
                "verify_ms": getattr(self, "_verify_ms", None),
                "iterations": len(history),
                "confidence": final_confidence,
                "verification_history": history,
                "mode": mode,
                "cached": False,
                "query_plan": self._query_plan,
                "chart_suggestion": chart_suggestion,
                "summary": self._generate_summary(result["columns"], result["rows"], result["row_count"]),
                "column_labels": column_labels,
            }
            break

        # If loop exhausted without success, return last error
        if last_result is None:
            last_error = history[-1] if history else {}
            last_result = {
                "success": False,
                "error": last_error.get("error", "所有重試均失敗"),
                "sql": last_error.get("sql"),
                "explanation": None,
                "data": [],
                "columns": [],
                "row_count": 0,
                "model": self.model,
                "llm_ms": None,
                "verify_ms": None,
                "iterations": len(history),
                "confidence": 0.0,
                "verification_history": history,
                "mode": mode,
                "cached": False,
                "query_plan": self._query_plan,
            }

        # Cache SQL permanently (no TTL) — only stores SQL + metadata, not data
        if last_result.get("success") and last_result.get("sql") and redis_conn:
            try:
                cache_data = {
                    "sql": last_result["sql"],
                    "explanation": last_result.get("explanation"),
                    "model": last_result.get("model"),
                    "confidence": last_result.get("confidence"),
                }
                await redis_conn.set(cache_key, json.dumps(cache_data, ensure_ascii=False))
            except Exception:
                pass

        if redis_conn:
            try:
                await redis_conn.aclose()
            except Exception:
                pass

        # If 0 results (or COUNT/SUM=0), generate alternative suggestions
        is_empty = last_result.get("row_count", 0) == 0
        # Also detect COUNT/SUM queries that return 1 row with value 0
        if not is_empty and last_result.get("row_count") == 1 and last_result.get("data"):
            row = last_result["data"][0] if last_result["data"] else {}
            vals = [v for v in row.values() if isinstance(v, (int, float))]
            if vals and all(v == 0 for v in vals) and "count" in last_result.get("sql", "").lower():
                is_empty = True

        if is_empty and last_result.get("sql"):
            try:
                alternatives = await self._suggest_alternatives(last_result["sql"], question)
                last_result["suggestions"] = alternatives
            except Exception as e:
                log.warning("Suggest alternatives failed: %s", e)
                last_result["suggestions"] = []
        else:
            last_result["suggestions"] = []

        # Enforce max_results
        max_results = perm.get("max_results", 500)
        if last_result.get("success") and last_result.get("data"):
            if len(last_result["data"]) > max_results:
                last_result["data"] = last_result["data"][:max_results]
                last_result["row_count"] = max_results

        # Write audit log
        if last_result.get("sql"):
            await self._write_audit_log(user_context, question, last_result.get("sql"), last_result)

        return last_result
