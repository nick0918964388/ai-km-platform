"""Tool 5: count_open_workorders_by_category — 未結案工單按車輛階層統計"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Literal

from pydantic import BaseModel

from app.services.maximo_tools.base import (
    Tool,
    ToolDefinition,
    ToolResult,
    UserContext,
    validate_tool_schema,
)
from app.services.maximo_tools.mappers.vehicle_category import CATEGORY_LEVEL_FIELD

logger = logging.getLogger(__name__)

_CLOSED_STATUSES = ("工單結案", "工單取消", "工單退回")


class _Input(BaseModel):
    group_by: Literal["大分類", "車種", "車型"] = "大分類"


_SCHEMA = _Input.model_json_schema()
validate_tool_schema(_SCHEMA)


class CountOpenWorkordersByCategoryTool(Tool):
    definition = ToolDefinition(
        name="count_open_workorders_by_category",
        description=(
            "統計未結案工單按車輛階層（大分類/車種/車型）分組。"
            "自動合併貨車雙碼（RSTF+RSTP → 貨車）。自動排除無 eq11 分類的資產。"
            "回傳 count + percentage + chart_hint 供 Dashboard 圖表使用。"
            "使用場景：『各大分類未結案工單』、『按車種分組的故障工單數』。"
        ),
        input_schema=_SCHEMA,
    )

    def __init__(self, db_pool=None):
        self._db_pool = db_pool

    async def execute(self, params: dict, user_ctx: UserContext) -> ToolResult:
        start = time.monotonic()
        if self._db_pool is None:
            raise RuntimeError(
                "CountOpenWorkordersByCategoryTool._db_pool not injected. "
                "Call tool._db_pool = app.state.db_pool before execute."
            )

        try:
            validated = _Input.model_validate(params)
        except Exception as e:
            logger.warning("Invalid params for count_open_workorders_by_category: %s", e)
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
                self._query, validated.group_by, user_ctx.section
            )
        except Exception:
            logger.exception(
                "count_open_workorders_by_category failed",
                extra={"group_by": validated.group_by, "user_id": user_ctx.user_id},
            )
            return ToolResult(
                success=False,
                rows=[],
                row_count=0,
                error_code="TOOL_EXECUTION_ERROR",
                error="統計查詢失敗",
                elapsed_ms=int((time.monotonic() - start) * 1000),
            )

        chart_hint = {
            "type": "pie" if validated.group_by == "大分類" else "bar",
            "x_field": "category",
            "y_field": "count",
            "percentage_field": "percentage",
        }
        return ToolResult(
            success=True,
            rows=rows,
            row_count=len(rows),
            chart_hint=chart_hint,
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )

    def _query(self, group_by: str, section: str | None) -> list[dict[str, Any]]:
        field = CATEGORY_LEVEL_FIELD[group_by]  # eq11 / eq3 / eq4

        closed_placeholders = ", ".join(["%s"] * len(_CLOSED_STATUSES))

        section_filter_pm = "AND maintenance_section = %s" if section else ""
        section_filter_cm = "AND maintenance_section = %s" if section else ""

        if group_by == "大分類":
            category_expr = """
                CASE
                    WHEN a.eq11 IN ('RSTF', 'RSTP') THEN '貨車'
                    WHEN a.eq11 = 'RSTL' THEN '動力車'
                    WHEN a.eq11 = 'RSTA' THEN '客車'
                    ELSE a.eq11
                END
            """
            # 大分類 always filters on eq11
            null_filter = "a.eq11 IS NOT NULL AND a.eq11 != ''"
        else:
            category_expr = f"a.{field}"
            null_filter = f"a.{field} IS NOT NULL AND a.{field} != ''"

        sql = f"""
            WITH wo AS (
                SELECT assetnum, status FROM maximo_pm_workorders
                WHERE status NOT IN ({closed_placeholders}) {section_filter_pm}
                UNION ALL
                SELECT assetnum, status FROM maximo_cm_workorders
                WHERE status NOT IN ({closed_placeholders}) {section_filter_cm}
            )
            SELECT
                {category_expr} AS category,
                COUNT(*) AS count,
                ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS percentage
            FROM wo
            JOIN maximo_mxasset a ON wo.assetnum = a.assetnum
            WHERE {null_filter}
            GROUP BY 1
            ORDER BY count DESC
        """

        # Args order matches SQL placeholders:
        #   1. _CLOSED_STATUSES (for pm NOT IN)
        #   2. section (for pm, if set)
        #   3. _CLOSED_STATUSES (for cm NOT IN)
        #   4. section (for cm, if set)
        args: list[Any] = list(_CLOSED_STATUSES)
        if section:
            args.append(section)
        args.extend(_CLOSED_STATUSES)
        if section:
            args.append(section)

        conn = self._db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(args))
                col_names = [d[0] for d in cur.description]
                raw_rows = [dict(zip(col_names, r)) for r in cur.fetchall()]
        finally:
            self._db_pool.putconn(conn)

        return [
            {
                "分類": r["category"],
                "工單數": int(r["count"]),
                "百分比": float(r["percentage"]),
            }
            for r in raw_rows
        ]


# Registry auto-discovery: db_pool=None; T014 API wiring 時注入：
#   registry.get("count_open_workorders_by_category")._db_pool = app.state.db_pool
REGISTER = CountOpenWorkordersByCategoryTool()
