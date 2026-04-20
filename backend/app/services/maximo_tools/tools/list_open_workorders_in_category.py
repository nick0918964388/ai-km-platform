"""Tool 6: list_open_workorders_in_category — 按階層查未結案工單明細"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.services.maximo_tools.base import (
    Tool,
    ToolDefinition,
    ToolResult,
    UserContext,
    validate_tool_schema,
)
from app.services.maximo_tools.mappers.vehicle_category import (
    CATEGORY_LEVEL_FIELD,
    to_codes,
)

logger = logging.getLogger(__name__)

# SSH 實測確認的結案/取消狀態（FR-014a）
_CLOSED_STATUSES = ("工單結案", "工單取消", "工單退回")

# 手動 flat schema — Literal 在 Pydantic v2 可能產生 anyOf，故手寫
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "level": {
            "type": "string",
            "enum": ["大分類", "車種", "車型"],
            "description": "車輛階層：大分類（動力車/客車/貨車）、車種（如 EMU/PPT）、車型（如 EMU800/35PPT1000）",
        },
        "value": {
            "type": "string",
            "description": "對應階層的中文值，如「客車」、「EMU」、「EMU800」",
        },
    },
    "required": ["level", "value"],
}

validate_tool_schema(_SCHEMA)  # 啟動時驗證，確保與 Anthropic tool_use 相容


class _Input(BaseModel):
    """Runtime 參數驗證。schema 與此分離（見 _SCHEMA）。"""

    level: Literal["大分類", "車種", "車型"]
    value: str = Field(..., min_length=1)


class ListOpenWorkordersInCategoryTool(Tool):
    definition = ToolDefinition(
        name="list_open_workorders_in_category",
        description=(
            "列出指定車輛階層下的未結案工單明細。"
            "level=大分類（動力車/客車/貨車，自動展開貨車雙碼）、車種、車型。value 為中文值。"
            "使用場景：『客車的未結案工單清單』、『EMU3000 車型工單』、『貨車工單』。"
        ),
        input_schema=_SCHEMA,
    )

    def __init__(self, db_pool=None):
        """
        Args:
            db_pool: psycopg2 pool with getconn()/putconn() interface。
                     允許 None；T014 API wiring 時透過 _db_pool 屬性注入。
        """
        self._db_pool = db_pool

    async def execute(self, params: dict, user_ctx: UserContext) -> ToolResult:
        start = time.monotonic()
        if self._db_pool is None:
            raise RuntimeError(
                "ListOpenWorkordersInCategoryTool._db_pool not injected. "
                "Call tool._db_pool = app.state.db_pool before execute."
            )

        try:
            validated = _Input.model_validate(params)
        except Exception as e:
            logger.warning("Invalid params for list_open_workorders_in_category: %s", e)
            return ToolResult(
                success=False,
                rows=[],
                row_count=0,
                error_code="TOOL_INVOCATION_ERROR",
                error="參數驗證失敗",
                elapsed_ms=int((time.monotonic() - start) * 1000),
            )

        try:
            rows = await asyncio.to_thread(
                self._query,
                validated.level,
                validated.value,
                user_ctx.section,
            )
        except Exception:
            logger.exception(
                "list_open_workorders_in_category query failed",
                extra={"level": validated.level, "value": validated.value, "user_id": user_ctx.user_id},
            )
            return ToolResult(
                success=False,
                rows=[],
                row_count=0,
                error_code="TOOL_EXECUTION_ERROR",
                error="工單明細查詢失敗",
                elapsed_ms=int((time.monotonic() - start) * 1000),
            )

        return ToolResult(
            success=True,
            rows=rows,
            row_count=len(rows),
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )

    def _query(self, level: str, value: str, section: str | None) -> list[dict[str, Any]]:
        """Sync SQL query on thread pool. Returns chinese-mapped rows."""
        field = CATEGORY_LEVEL_FIELD[level]  # eq11 / eq3 / eq4

        # 大分類走 to_codes() 支援貨車雙碼展開；其他層直接比對 value 字串
        if level == "大分類":
            codes = to_codes(value)
            if len(codes) == 1:
                field_filter = f"a.{field} = %s"
                field_args: list[Any] = [codes[0]]
            else:
                placeholders = ", ".join(["%s"] * len(codes))
                field_filter = f"a.{field} IN ({placeholders})"
                field_args = list(codes)
        else:
            field_filter = f"a.{field} = %s"
            field_args = [value]

        closed_placeholders = ", ".join(["%s"] * len(_CLOSED_STATUSES))
        section_clause = "AND maintenance_section = %s" if section else ""

        sql = f"""
            WITH wo AS (
                SELECT wonum, assetnum, status, '定檢' AS wo_type, work_type,
                       description, report_date, act_finish
                FROM maximo_pm_workorders
                WHERE status NOT IN ({closed_placeholders}) {section_clause}
                UNION ALL
                SELECT wonum, assetnum, status, '臨修' AS wo_type, work_type,
                       description, report_date, act_finish
                FROM maximo_cm_workorders
                WHERE status NOT IN ({closed_placeholders}) {section_clause}
            )
            SELECT wo.wonum, wo.assetnum, wo.status, wo.wo_type, wo.work_type,
                   wo.description, wo.report_date, wo.act_finish,
                   a.eq3, a.eq4, a.eq11
            FROM wo
            JOIN maximo_mxasset a ON wo.assetnum = a.assetnum
            WHERE {field_filter}
            ORDER BY wo.report_date DESC NULLS LAST
            LIMIT 200
        """

        # arg 順序：PM closed × N → PM section? → CM closed × N → CM section? → field filter
        args: list[Any] = list(_CLOSED_STATUSES)
        if section:
            args.append(section)
        args.extend(_CLOSED_STATUSES)
        if section:
            args.append(section)
        args.extend(field_args)

        conn = self._db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(args))
                col_names = [d[0] for d in cur.description]
                rows = [dict(zip(col_names, r)) for r in cur.fetchall()]
        finally:
            self._db_pool.putconn(conn)

        return [self._to_chinese(r) for r in rows]

    @staticmethod
    def _to_chinese(raw: dict) -> dict[str, Any]:
        """欄位名英文 → 中文，timestamp → ISO string。"""

        def _iso(val: Any) -> str | None:
            return val.isoformat() if val is not None else None

        return {
            "工單號":     raw.get("wonum"),
            "車號":       raw.get("assetnum"),
            "狀態":       raw.get("status"),
            "工單類型":    raw.get("wo_type"),
            "工作類型":    raw.get("work_type"),
            "車種":       raw.get("eq3"),
            "車型":       raw.get("eq4"),
            "大分類代碼":  raw.get("eq11"),
            "描述":       raw.get("description"),
            "通報日期":    _iso(raw.get("report_date")),
            "實際完工":    _iso(raw.get("act_finish")),
        }


# Registry auto-discovery：允許 db_pool=None；T014 API wiring 時注入：
#   registry.get("list_open_workorders_in_category")._db_pool = app.state.db_pool
REGISTER = ListOpenWorkordersInCategoryTool()
