"""
Skill Agent Tools — S3

4 tool definitions + executor functions.
Security: run_sql must pass _is_safe_select + _run_security_gates before execution.
SQL failures return error blocks (not raised) to allow LLM self-correction.
"""
from __future__ import annotations

import logging
from typing import Any

from app.services.maximo_nl2sql_tools import _is_safe_select  # noqa: F401

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool JSON Schema definitions (Anthropic tool_use format)
# ---------------------------------------------------------------------------

AGENT_TOOLS: list[dict] = [
    {
        "name": "run_sql",
        "description": (
            "對 Maximo PostgreSQL 資料庫執行 SELECT 查詢，回傳 rows。"
            "只允許 SELECT 語句，禁止 INSERT/UPDATE/DELETE/DROP 等 DML/DDL。"
            "失敗時回傳 error block，請修正 SQL 後重試。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "要執行的 SELECT SQL 語句",
                }
            },
            "required": ["sql"],
        },
    },
    {
        "name": "search_docs",
        "description": (
            "在知識庫中全文搜尋相關文件。適合查 SOP、維修手冊、技術說明。"
            "回傳最多 top_k 筆，每筆含 title / snippet / score。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜尋關鍵字或問題",
                },
                "top_k": {
                    "type": "integer",
                    "description": "回傳筆數，預設 3，最大 10",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "inspect_schema",
        "description": (
            "取得指定 Maximo 資料表的欄位清單與型別，協助撰寫正確的 SQL。"
            "表名範圍：maximo_assets / maximo_pm_workorders / maximo_cm_workorders / maximo_fault_reports"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "description": "資料表名稱",
                }
            },
            "required": ["table"],
        },
    },
    {
        "name": "run_skill",
        "description": (
            "呼叫已建立的 Skill（SQL template）查詢，比自行撰寫 SQL 更安全可靠。"
            "name 是 skill 名稱（snake_case），params 是 SQL template 的參數。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Skill 名稱，例如 count_emu_trains",
                },
                "params": {
                    "type": "object",
                    "description": "Skill SQL template 的參數 dict",
                },
            },
            "required": ["name"],
        },
    },
]

# ---------------------------------------------------------------------------
# Static schema summaries (used by inspect_schema without DB round-trip)
# ---------------------------------------------------------------------------
_TABLE_SCHEMAS: dict[str, str] = {
    "maximo_assets": (
        "assetnum VARCHAR PK, eq24 VARCHAR(車號), vehicle_type VARCHAR, "
        "vehicle_class VARCHAR, vehicle_category VARCHAR, workshop VARCHAR, "
        "section VARCHAR, status VARCHAR(OPERATING/DECOMMISSIONED/INACTIVE), "
        "status_desc VARCHAR, car_group VARCHAR, position INT, record_type VARCHAR, "
        "install_date TIMESTAMPTZ, expected_life INT, manufacturer VARCHAR"
    ),
    "maximo_pm_workorders": (
        "wonum VARCHAR PK, description TEXT, status VARCHAR, assetnum VARCHAR, "
        "work_type VARCHAR(1A/2A/3A/4A), owner_group VARCHAR, maintenance_section VARCHAR, "
        "report_date TIMESTAMPTZ, act_start TIMESTAMPTZ, act_finish TIMESTAMPTZ, "
        "last_act_finish TIMESTAMPTZ, car_in_result TEXT, car_out_result TEXT, kilometers INT"
    ),
    "maximo_cm_workorders": (
        "wonum VARCHAR PK, description TEXT, long_description TEXT, status VARCHAR, "
        "assetnum VARCHAR, work_type VARCHAR(T1/TR/CM), owner_group VARCHAR, "
        "maintenance_section VARCHAR, ticket_id VARCHAR, report_date TIMESTAMPTZ, "
        "act_start TIMESTAMPTZ, act_finish TIMESTAMPTZ, target_start_date TIMESTAMPTZ, "
        "target_comp_date TIMESTAMPTZ, failure_code VARCHAR, repair_proc TEXT, work_hours NUMERIC"
    ),
    "maximo_fault_reports": (
        "ticketid VARCHAR PK, im_num VARCHAR, description TEXT, fault_symptom TEXT, "
        "handling_desc TEXT, status VARCHAR(立案/取消/結案), status_desc VARCHAR, "
        "assetnum VARCHAR, incident_class VARCHAR, fault_location TEXT, tcms_code VARCHAR, "
        "grade VARCHAR, urgency VARCHAR, restricted_status VARCHAR, report_unit VARCHAR, "
        "occurrence_date TIMESTAMPTZ, report_date TIMESTAMPTZ, confirm_by VARCHAR, confirm_date TIMESTAMPTZ"
    ),
}


# ---------------------------------------------------------------------------
# Tool executors
# ---------------------------------------------------------------------------

async def execute_run_sql(
    params: dict,
    user_ctx,
    db_pool=None,
) -> dict:
    """
    Execute a SELECT SQL against the DB pool.
    Security:
      1. _is_safe_select() — keyword + table allowlist
      2. _run_security_gates() imported from maximo_nl2sql (permission/row-filter)
    SQL failure returns error dict (never raises) to allow LLM self-correction.
    """
    sql: str = params.get("sql", "").strip()

    # Gate 1: static guard
    safe, reason = _is_safe_select(sql)
    if not safe:
        return {"error": reason, "rows": [], "row_count": 0, "columns": []}

    # Gate 2: maximo_nl2sql security gates (permission + row-filter)
    # We import lazily to avoid circular deps at module load time.
    try:
        from app.services.maximo_nl2sql import MaximoNL2SQL  # noqa: PLC0415
        perm = _build_perm(user_ctx)
        user_context_dict = _build_user_context(user_ctx)
        svc_stub = _make_nl2sql_stub()
        allowed, err_msg, final_sql, row_filter_params = svc_stub._run_security_gates(
            sql, perm, user_context_dict
        )
        if not allowed:
            return {"error": err_msg, "rows": [], "row_count": 0, "columns": []}
        sql = final_sql
    except ImportError:
        # maximo_nl2sql not available (test context) — fall through with basic guard only
        row_filter_params = {}

    if db_pool is None:
        return {"error": "db_pool 未注入", "rows": [], "row_count": 0, "columns": []}

    try:
        async with db_pool.acquire() as conn:
            rows_raw = await conn.fetch(sql)
            if not rows_raw:
                return {"rows": [], "row_count": 0, "columns": []}
            columns = list(rows_raw[0].keys())
            rows = [dict(r) for r in rows_raw]
            # Serialize non-JSON-serializable types
            for row in rows:
                for k, v in row.items():
                    if hasattr(v, "isoformat"):
                        row[k] = v.isoformat()
            return {"rows": rows, "row_count": len(rows), "columns": columns}
    except Exception as e:
        log.warning("run_sql execution error: %s", e)
        return {"error": f"SQL 執行失敗：{type(e).__name__}", "rows": [], "row_count": 0, "columns": []}


async def execute_search_docs(params: dict, rag_search_fn=None) -> dict:
    """
    Search the knowledge base.
    rag_search_fn is injected (default: rag.search). Allows mocking in tests.
    """
    query: str = params.get("query", "").strip()
    top_k: int = min(int(params.get("top_k", 3)), 10)

    if not query:
        return {"results": [], "count": 0}

    if rag_search_fn is None:
        try:
            from app.services import rag  # noqa: PLC0415
            rag_search_fn = rag.search
        except ImportError:
            return {"results": [], "count": 0, "error": "rag module not available"}

    try:
        results = rag_search_fn(query=query, top_k=top_k, use_cache=True)
        docs = []
        for r in results:
            docs.append({
                "title": getattr(r, "title", None) or getattr(r, "source", "unknown"),
                "snippet": (getattr(r, "content", "") or "")[:300],
                "score": round(float(getattr(r, "score", 0.0)), 4),
            })
        return {"results": docs, "count": len(docs)}
    except Exception as e:
        log.warning("search_docs error: %s", e)
        return {"results": [], "count": 0, "error": f"搜尋失敗：{type(e).__name__}"}


async def execute_inspect_schema(params: dict) -> dict:
    """Return static schema summary for a Maximo table. No DB round-trip needed."""
    table: str = params.get("table", "").strip().lower()
    schema = _TABLE_SCHEMAS.get(table)
    if schema is None:
        return {
            "error": f"未知資料表：{table}",
            "available_tables": sorted(_TABLE_SCHEMAS.keys()),
        }
    return {"table": table, "columns": schema}


async def execute_run_skill(
    params: dict,
    user_ctx,
    skill_runner=None,
) -> dict:
    """
    Execute a named Skill via injected skill_runner.
    skill_runner signature: async (name: str, params: dict, user_ctx) -> dict
    Returns rows or error dict.
    """
    name: str = params.get("name", "").strip()
    skill_params: dict = params.get("params") or {}

    if not name:
        return {"error": "name 必填", "rows": [], "row_count": 0}

    if skill_runner is None:
        return {"error": "skill_runner 未注入", "rows": [], "row_count": 0}

    try:
        result = await skill_runner(name, skill_params, user_ctx)
        return result
    except Exception as e:
        log.warning("run_skill error skill=%s: %s", name, e)
        return {"error": f"Skill 執行失敗：{type(e).__name__}", "rows": [], "row_count": 0}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_perm(user_ctx) -> dict:
    """Build permission dict from UserContext for security gates."""
    from app.services.maximo_nl2sql import STATIC_ALLOWED_TABLES
    role = getattr(user_ctx, "role", "viewer")
    if role == "admin":
        return {"allowed_tables": None, "row_filters": {}}
    return {
        "allowed_tables": list(STATIC_ALLOWED_TABLES),
        "row_filters": {},
    }


def _build_user_context(user_ctx) -> dict:
    return {
        "user_id": getattr(user_ctx, "user_id", ""),
        "role": getattr(user_ctx, "role", "viewer"),
        "section": getattr(user_ctx, "section", None),
        "workshop": getattr(user_ctx, "workshop", None),
    }


_nl2sql_security_stub = None


def _make_nl2sql_stub():
    """
    Return a cached MaximoNL2SQL(db=None) used solely for _run_security_gates.
    Lazy-init on first call; reused thereafter to avoid per-call construction overhead.
    _run_security_gates only performs regex + policy checks and never executes DB calls,
    so sharing one stateless stub across requests is safe.
    """
    global _nl2sql_security_stub
    if _nl2sql_security_stub is None:
        from app.services.maximo_nl2sql import MaximoNL2SQL  # noqa: PLC0415
        _nl2sql_security_stub = MaximoNL2SQL(db=None)
    return _nl2sql_security_stub
