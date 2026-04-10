"""
Maximo NL→SQL Service
Converts natural language to SQL targeting maximo_* tables.
Uses field metadata + few-shot examples from PostgreSQL for better accuracy.
"""

import os
import re
import json
import time
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
            self.client = AsyncOpenAI(api_key="ollama", base_url=base_url)
            # Use light model for NL→SQL (faster, good enough for SQL generation)
            self.model = os.getenv("OLLAMA_LIGHT_MODEL",
                          os.getenv("OLLAMA_CHAT_MODEL", "gemma4:31b-cloud"))
        else:
            self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            self.model = os.getenv("OPENAI_MODEL", "gpt-4o")

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
        """Load value mappings + domain rules from maximo_field_metadata for prompt context."""
        try:
            rows = await self.db.execute(text(
                "SELECT table_name, column_name, display_name, description, value_mapping "
                "FROM maximo_field_metadata"
            ))
            mapping_lines = ["## 欄位值域對應（重要：生成 SQL 時使用這些值）"]
            rule_lines = ["## 業務查詢規則（必須遵守）"]
            for r in rows.fetchall():
                if r.table_name == "_rules":
                    # Domain knowledge rules
                    if r.description:
                        rule_lines.append(f"- {r.description}")
                else:
                    mapping = r.value_mapping if isinstance(r.value_mapping, dict) else {}
                    if mapping:
                        pairs = ", ".join(f'"{k}"={v}' for k, v in mapping.items())
                        mapping_lines.append(f"- {r.table_name}.{r.column_name}（{r.display_name}）：{pairs}")
                    elif r.description:
                        mapping_lines.append(f"- {r.table_name}.{r.column_name}（{r.display_name or r.column_name}）：{r.description}")
            return "\n".join(rule_lines) + "\n\n" + "\n".join(mapping_lines)
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

    async def generate_sql(self, question: str) -> Dict[str, Any]:
        """Generate SQL from natural language question."""
        allowed_tables, schema_text = await self._discover_tables()
        self._allowed_tables = allowed_tables  # store for validate_sql

        metadata = await self._load_field_metadata()
        examples = await self._load_examples()

        table_list = ", ".join(sorted(allowed_tables))
        system_prompt = f"""你是台鐵車輛維修資料庫的 SQL 專家。
將使用者的自然語言問題轉換為 PostgreSQL SELECT 語句。

{schema_text}

{metadata}

{examples}

規則：
1. 只產生 SELECT 查詢（不允許 INSERT/UPDATE/DELETE）
2. 只能查詢以下表：{table_list}
3. 多表查詢時必須使用正確的 JOIN
4. 預設 LIMIT 50，除非使用者指定
5. 日期欄位使用標準 SQL 日期比較

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
        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ],
                temperature=0,
                timeout=60,
            )
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
            return json.loads(content)
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
        tables = re.findall(r'\b(?:from|join)\s+(\w+)', s)
        for t in tables:
            if t not in allowed and t not in {"lateral", "unnest"}:
                return f"不允許存取的表：{t}"
        return None

    async def execute_sql(self, sql: str) -> Dict[str, Any]:
        """Execute SQL and return rows + columns."""
        t0 = time.monotonic()
        try:
            result = await self.db.execute(text(sql))
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
            return {"error": str(e), "rows": [], "columns": [], "row_count": 0}

    async def query(self, question: str) -> Dict[str, Any]:
        """Full pipeline: NL → SQL → execute → return."""
        gen = await self.generate_sql(question)

        if gen.get("error") or not gen.get("sql"):
            return {
                "success": False,
                "error": gen.get("error", "無法產生 SQL"),
                "sql": None,
                "explanation": None,
                "data": [],
                "columns": [],
                "row_count": 0,
            }

        sql = gen["sql"]
        err = self.validate_sql(sql)
        if err:
            return {
                "success": False,
                "error": f"SQL 驗證失敗：{err}",
                "sql": sql,
                "explanation": gen.get("explanation"),
                "data": [],
                "columns": [],
                "row_count": 0,
            }

        result = await self.execute_sql(sql)
        if result.get("error"):
            return {
                "success": False,
                "error": result["error"],
                "sql": sql,
                "explanation": gen.get("explanation"),
                "data": [],
                "columns": [],
                "row_count": 0,
            }

        return {
            "success": True,
            "sql": sql,
            "explanation": gen.get("explanation"),
            "data": result["rows"],
            "columns": result["columns"],
            "row_count": result["row_count"],
            "execution_ms": result.get("execution_ms"),
        }
