"""
SQL Error-Aware Repair Loop using Anthropic tool_use.

Provides:
  - SQL_REPAIR_TOOLS: three Anthropic tool schemas
  - exec_inspect_schema / exec_sample_rows / exec_execute_sql: tool executors
  - repair_with_tools: multi-turn tool_use loop that repairs failed SQL
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# A1. Tool schemas (Anthropic tool_use format)
# ---------------------------------------------------------------------------

SQL_REPAIR_TOOLS = [
    {
        "name": "inspect_schema",
        "description": (
            "檢視資料表 schema：欄位名、型別、範例值。"
            "當 SQL 失敗是因為欄位不存在或型別不符時呼叫。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "要檢視的資料表名稱",
                }
            },
            "required": ["table_name"],
        },
    },
    {
        "name": "sample_rows",
        "description": (
            "查看資料表前 N 筆實際資料（最多 5 筆）。"
            "當不確定資料實際長什麼樣子時呼叫。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
                "n": {"type": "integer", "default": 3, "maximum": 5},
            },
            "required": ["table_name"],
        },
    },
    {
        "name": "execute_sql",
        "description": (
            "執行修正後的 SQL 驗證。執行成功回傳前 3 筆資料與欄位；"
            "失敗回傳錯誤訊息。只有 SELECT 可以執行。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "修正後的 SELECT SQL",
                }
            },
            "required": ["sql"],
        },
    },
]

# ---------------------------------------------------------------------------
# C2: Safe-SELECT validator — blocks non-SELECT, writable CTEs, comments,
#     multi-statements, and FORBIDDEN_KEYWORDS before executing user SQL.
# ---------------------------------------------------------------------------

# Must stay in sync with maximo_nl2sql.FORBIDDEN_KEYWORDS
# Keywords matched with \b word-boundary (all-alpha identifiers)
_FORBIDDEN_KEYWORDS_WORD = frozenset({
    "insert", "update", "delete", "drop", "truncate", "alter", "create",
    "grant", "revoke", "execute", "exec", "call", "shutdown", "copy",
})
# Keywords that contain underscores — use plain substring match instead of \b
_FORBIDDEN_KEYWORDS_SUBSTR = frozenset({
    "pg_", "information_schema",
})

# Detects writable CTEs: WITH ... (DELETE|UPDATE|INSERT|TRUNCATE ... )
_WRITABLE_CTE_RE = re.compile(
    r"with\b.+?\bas\s*\(\s*(delete|update|insert|truncate)\b",
    re.IGNORECASE | re.DOTALL,
)


def _is_safe_select(sql: str) -> tuple[bool, str]:
    """Return (True, "") if sql is a safe read-only SELECT/WITH-SELECT.

    Rejects:
    - non-SELECT/WITH openers
    - -- or /* SQL comments
    - ; multi-statement (allows trailing ; after strip)
    - FORBIDDEN_KEYWORDS (case-insensitive word-boundary match)
    - writable CTEs: WITH ... AS (DELETE|UPDATE|INSERT|TRUNCATE ...)
    """
    stripped = sql.strip()
    if not stripped:
        return False, "SQL 為空"

    # 1. Comment check (before anything else to prevent evasion)
    if "--" in stripped or "/*" in stripped:
        return False, "FORBIDDEN: SQL 注解不允許"

    # 2. Multi-statement check (semicolon anywhere except optional trailing)
    if ";" in stripped.rstrip(";"):
        return False, "FORBIDDEN: 不允許多個語句（;）"

    lower = stripped.lower()

    # 3. Must start with SELECT or WITH
    if not re.match(r"^\s*(with|select)\b", lower):
        return False, "FORBIDDEN: 只允許 SELECT 查詢"

    # 4. Writable CTE check (before keyword scan — catches WITH...DELETE pattern)
    if _WRITABLE_CTE_RE.search(lower):
        return False, "FORBIDDEN: 不允許可寫入的 CTE（writable CTE）"

    # 5. Forbidden keyword scan (word-boundary for all-alpha, substring for underscore-containing)
    for kw in _FORBIDDEN_KEYWORDS_WORD:
        if re.search(rf"\b{re.escape(kw)}\b", lower):
            return False, f"FORBIDDEN: 不允許的關鍵字：{kw}"
    for kw in _FORBIDDEN_KEYWORDS_SUBSTR:
        if kw in lower:
            return False, f"FORBIDDEN: 不允許的關鍵字：{kw}"

    return True, ""


# ---------------------------------------------------------------------------
# Identifier whitelist — only [a-zA-Z0-9_] is allowed in table names
# ---------------------------------------------------------------------------

_TABLE_NAME_RE = re.compile(r"^[a-zA-Z0-9_]+$")


def _validate_table_name(table_name: str) -> str:
    """Raise ValueError if table_name contains injection-risky characters."""
    if not _TABLE_NAME_RE.match(table_name):
        raise ValueError(
            f"Invalid table_name '{table_name}': only [a-zA-Z0-9_] allowed"
        )
    return table_name


# ---------------------------------------------------------------------------
# A2. Executor functions
# ---------------------------------------------------------------------------


async def exec_inspect_schema(db: AsyncSession, table_name: str) -> dict:
    """Return {columns: [{name, type, sample_values}], row_count}.

    Uses information_schema for column metadata, then fetches 2 random sample
    values per column via a savepoint-isolated query.
    """
    try:
        _validate_table_name(table_name)
    except ValueError as exc:
        return {"columns": [], "row_count": 0, "error": str(exc)}

    columns_info: list[dict] = []
    row_count = 0

    try:
        # H1: Let exception propagate out of begin_nested for automatic rollback.
        async with db.begin_nested():
            # Column metadata
            col_result = await db.execute(
                text(
                    """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = :tname
                    ORDER BY ordinal_position
                    """
                ),
                {"tname": table_name},
            )
            col_rows = col_result.fetchall()

            # Row count
            cnt_result = await db.execute(
                text(f"SELECT COUNT(*) FROM {table_name}")  # noqa: S608 – whitelist-validated
            )
            row_count = cnt_result.scalar() or 0

            # Sample values: fetch 2 rows for each column
            sample_data: dict[str, list] = {}
            if col_rows:
                sample_result = await db.execute(
                    text(f"SELECT * FROM {table_name} LIMIT 2")  # noqa: S608
                )
                sample_keys = list(sample_result.keys())
                sample_rows_raw = sample_result.fetchall()
                for r in sample_rows_raw:
                    for k, v in zip(sample_keys, r):
                        sample_data.setdefault(k, [])
                        sample_data[k].append(
                            v.isoformat() if hasattr(v, "isoformat") else v
                        )

            for col_name, data_type in col_rows:
                columns_info.append(
                    {
                        "name": col_name,
                        "type": data_type,
                        "sample_values": sample_data.get(col_name, []),
                    }
                )

    except Exception as exc:
        return {"columns": [], "row_count": 0, "error": str(exc)}

    return {"columns": columns_info, "row_count": row_count}


async def exec_sample_rows(db: AsyncSession, table_name: str, n: int = 3) -> dict:
    """Return {rows: [{col: val, ...}], columns: [...]}.

    n is capped at 5 to avoid overloading context window.
    Executes inside a savepoint to prevent polluting outer transaction.
    """
    try:
        _validate_table_name(table_name)
    except ValueError as exc:
        return {"rows": [], "columns": [], "error": str(exc)}
    n = min(max(1, n), 5)

    try:
        # H1: Let exception propagate out of begin_nested for automatic rollback.
        async with db.begin_nested():
            result = await db.execute(
                text(f"SELECT * FROM {table_name} LIMIT :n"),  # noqa: S608
                {"n": n},
            )
            cols = list(result.keys())
            rows = []
            for row in result.fetchall():
                row_dict = {}
                for k, v in zip(cols, row):
                    row_dict[k] = v.isoformat() if hasattr(v, "isoformat") else v
                rows.append(row_dict)
            return {"rows": rows, "columns": cols}
    except Exception as exc:
        return {"rows": [], "columns": [], "error": str(exc)}


async def exec_execute_sql(db: AsyncSession, sql: str) -> dict:
    """Execute a SELECT SQL and return {success, data?, columns?, row_count?, error?}.

    Only SELECT statements (optionally prefixed by WITH) are accepted.
    Returns at most 3 rows to keep context window usage low.
    Executes inside a savepoint; a failure does NOT affect the outer transaction.
    """
    # C2: Full safe-SELECT validation (blocks non-SELECT, writable CTEs,
    # comments, multi-statements, forbidden keywords)
    ok, err_msg = _is_safe_select(sql)
    if not ok:
        return {"success": False, "error": err_msg}

    sql_stripped = sql.strip()
    try:
        # H1: Let exception propagate out of begin_nested; SQLAlchemy rolls
        # back the savepoint automatically on __aexit__ with an exception.
        async with db.begin_nested():
            result = await db.execute(text(sql_stripped))
            cols = list(result.keys())
            rows_raw = result.fetchall()
            rows = []
            for row in rows_raw[:3]:
                row_dict = {}
                for k, v in zip(cols, row):
                    row_dict[k] = v.isoformat() if hasattr(v, "isoformat") else v
                rows.append(row_dict)
            return {
                "success": True,
                "data": rows,
                "columns": cols,
                "row_count": len(rows_raw),
            }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# A3. Main repair function
# ---------------------------------------------------------------------------

_REPAIR_SYSTEM_PROMPT = """\
你是 SQL 修復專家。使用者的 SQL 執行失敗，你的任務是用工具診斷問題並產出正確的 SQL。

流程：
1. 先呼叫 inspect_schema 確認欄位名稱與型別是否正確。
2. 若需要了解實際資料，呼叫 sample_rows。
3. 修正 SQL 後，呼叫 execute_sql 驗證是否成功。
4. 確認成功後，在最終回應中輸出修正後的 SQL，格式：

FIXED_SQL:
<corrected SELECT statement>

如果無法修復，請回覆 CANNOT_FIX: <原因>。
"""

_SQL_EXTRACT_RE = re.compile(
    r"FIXED_SQL:\s*\n(.*?)(?:\n\n|$)", re.DOTALL | re.IGNORECASE
)


def _extract_fixed_sql(text_content: str) -> str | None:
    """Parse 'FIXED_SQL:\\n...' from LLM final turn."""
    m = _SQL_EXTRACT_RE.search(text_content)
    if m:
        return m.group(1).strip()
    # Fallback: look for bare SELECT block
    lines = text_content.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^\s*(WITH|SELECT)\b", line, re.IGNORECASE):
            # Collect until blank line or end
            block = []
            for l in lines[i:]:
                if not l.strip():
                    break
                block.append(l)
            if block:
                return "\n".join(block).strip()
    return None


async def repair_with_tools(
    db: AsyncSession,
    question: str,
    last_sql: str,
    last_error: str,
    schema_ctx: str,
    anthropic_client: Any,
    model: str,
    max_tool_calls: int = 3,
) -> dict:
    """Run Anthropic tool_use loop to repair failed SQL.

    Returns:
        {
            "success": bool,
            "sql": str | None,          # repaired SQL on success
            "tool_calls": list[dict],   # log of every tool call made
            "error": str | None,        # reason on failure
        }
    """
    if anthropic_client is None:
        return {"success": False, "sql": None, "tool_calls": [], "error": "no anthropic client"}

    user_content = (
        f"使用者問題：{question}\n\n"
        f"失敗的 SQL：\n{last_sql}\n\n"
        f"DB 錯誤訊息：{last_error}\n\n"
        f"資料庫 Schema 摘要：\n{schema_ctx[:3000]}"
    )

    messages: list[dict] = [{"role": "user", "content": user_content}]
    tool_calls_log: list[dict] = []
    tool_call_count = 0

    try:
        while tool_call_count <= max_tool_calls:
            t0 = time.monotonic()
            # M1: 30-second timeout on each Anthropic call
            response = await asyncio.wait_for(
                anthropic_client.messages.create(
                    model=model,
                    max_tokens=2048,
                    system=_REPAIR_SYSTEM_PROMPT,
                    messages=messages,
                    tools=SQL_REPAIR_TOOLS,
                ),
                timeout=30.0,
            )
            elapsed_ms = round((time.monotonic() - t0) * 1000, 1)

            # Append assistant turn to messages
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                # Extract fixed SQL from text blocks
                # Use type == "text" (not hasattr) so MagicMock tool_use blocks are excluded
                full_text = " ".join(
                    b.text for b in response.content if getattr(b, "type", None) == "text"
                )
                fixed_sql = _extract_fixed_sql(full_text)
                if fixed_sql:
                    return {
                        "success": True,
                        "sql": fixed_sql,
                        "tool_calls": tool_calls_log,
                        "error": None,
                    }
                # LLM said CANNOT_FIX or gave no SQL
                return {
                    "success": False,
                    "sql": None,
                    "tool_calls": tool_calls_log,
                    "error": f"LLM did not produce fixed SQL: {full_text[:200]}",
                }

            if response.stop_reason == "tool_use":
                # H2: Check for mixed text+tool_use response — LLM may embed
                # FIXED_SQL in a text block alongside tool_use blocks.
                text_blocks_text = " ".join(
                    b.text for b in response.content if getattr(b, "type", None) == "text"
                )
                if text_blocks_text:
                    fallback_sql = _extract_fixed_sql(text_blocks_text)
                    if fallback_sql:
                        log.debug(
                            "repair_with_tools: found FIXED_SQL in mixed tool_use+text turn"
                        )
                        return {
                            "success": True,
                            "sql": fallback_sql,
                            "tool_calls": tool_calls_log,
                            "error": None,
                        }

                # Collect all tool_use blocks in this turn
                tool_use_blocks = [
                    b for b in response.content if b.type == "tool_use"
                ]
                if not tool_use_blocks:
                    return {
                        "success": False,
                        "sql": None,
                        "tool_calls": tool_calls_log,
                        "error": "stop_reason=tool_use but no tool_use blocks found",
                    }

                if tool_call_count >= max_tool_calls:
                    return {
                        "success": False,
                        "sql": None,
                        "tool_calls": tool_calls_log,
                        "error": f"max_tool_calls ({max_tool_calls}) reached",
                    }

                # Execute each tool and build tool_result content list
                tool_result_content: list[dict] = []
                for block in tool_use_blocks:
                    tool_call_count += 1
                    tool_name = block.name
                    tool_input = block.input or {}
                    tool_id = block.id

                    tool_result = await _dispatch_tool(db, tool_name, tool_input)

                    tool_calls_log.append(
                        {
                            "tool": tool_name,
                            "input": tool_input,
                            "result": tool_result,
                            "ms": elapsed_ms,
                        }
                    )

                    import json as _json
                    tool_result_content.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": _json.dumps(tool_result, ensure_ascii=False, default=str),
                        }
                    )

                messages.append({"role": "user", "content": tool_result_content})
                continue  # next LLM turn

            # Unexpected stop_reason
            return {
                "success": False,
                "sql": None,
                "tool_calls": tool_calls_log,
                "error": f"Unexpected stop_reason: {response.stop_reason}",
            }

    except Exception as exc:
        log.warning("repair_with_tools exception: %s", exc)
        return {
            "success": False,
            "sql": None,
            "tool_calls": tool_calls_log,
            "error": str(exc),
        }

    # Loop exhausted (max_tool_calls guard via while condition)
    return {
        "success": False,
        "sql": None,
        "tool_calls": tool_calls_log,
        "error": f"max_tool_calls ({max_tool_calls}) reached",
    }


async def _dispatch_tool(
    db: AsyncSession, tool_name: str, tool_input: dict
) -> dict:
    """Route tool_name to executor; return result dict."""
    if tool_name == "inspect_schema":
        table_name = tool_input.get("table_name", "")
        try:
            return await exec_inspect_schema(db, table_name)
        except ValueError as exc:
            return {"error": str(exc)}

    if tool_name == "sample_rows":
        table_name = tool_input.get("table_name", "")
        n = int(tool_input.get("n", 3))
        try:
            return await exec_sample_rows(db, table_name, n)
        except ValueError as exc:
            return {"error": str(exc)}

    if tool_name == "execute_sql":
        sql = tool_input.get("sql", "")
        return await exec_execute_sql(db, sql)

    return {"error": f"Unknown tool: {tool_name}"}
