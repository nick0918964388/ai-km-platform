"""Tool 7: get_recent_fault_distribution — 近期故障按 urgency/section 分布"""
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
from app.services.maximo_tools.mappers.date_range import resolve as resolve_date_range

logger = logging.getLogger(__name__)


# 手動 flat schema — pydantic Optional 會產生 anyOf，被 validate_tool_schema 阻擋
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "date_range": {
            "type": "string",
            "enum": ["last_7d", "last_30d", "last_90d", "prev_week", "prev_month", "this_month"],
            "default": "last_30d",
            "description": "日期範圍 preset；若同時提供 from_date+to_date 則 preset 被覆蓋",
        },
        "group_by": {
            "type": "string",
            "enum": ["urgency", "section"],
            "default": "urgency",
            "description": "urgency=故障等級 A/B/C（排除 NULL）；section=段管（report_unit）",
        },
        "from_date": {
            "type": "string",
            "description": "ISO 8601 起始日期，如 2026-01-01",
        },
        "to_date": {
            "type": "string",
            "description": "ISO 8601 結束日期，如 2026-03-31",
        },
    },
    "required": [],
}

validate_tool_schema(_SCHEMA)


class _Input(BaseModel):
    """Runtime 參數驗證；schema 與此分離（見 _SCHEMA）。"""
    date_range: str = "last_30d"
    group_by: str = "urgency"
    from_date: str | None = None
    to_date: str | None = None

    def model_post_init(self, __context: Any) -> None:
        _valid_ranges = {"last_7d", "last_30d", "last_90d", "prev_week", "prev_month", "this_month"}
        if self.date_range not in _valid_ranges:
            raise ValueError(f"Invalid date_range: {self.date_range!r}")
        if self.group_by not in ("urgency", "section"):
            raise ValueError(f"Invalid group_by: {self.group_by!r}")


class GetRecentFaultDistributionTool(Tool):
    definition = ToolDefinition(
        name="get_recent_fault_distribution",
        description=(
            "統計近期故障通報按故障等級 (A/B/C) 或段管分布。回傳 count + percentage + chart_hint 給 Dashboard。"
            "urgency 分組時自動排除 NULL 等級（實測 224/395 筆為空）。"
            "使用場景：『近 30 天故障等級分布』、『上個月各段故障數』、『本月故障分布圖表』。"
        ),
        input_schema=_SCHEMA,
    )

    def __init__(self, db_pool=None):
        self._db_pool = db_pool

    async def execute(self, params: dict, user_ctx: UserContext) -> ToolResult:
        start = time.monotonic()
        if self._db_pool is None:
            raise RuntimeError(
                "GetRecentFaultDistributionTool._db_pool not injected. "
                "Call tool._db_pool = app.state.db_pool before execute."
            )

        try:
            validated = _Input.model_validate(params)
        except Exception as e:
            logger.warning("Invalid params for get_recent_fault_distribution: %s", e)
            return ToolResult(
                success=False,
                rows=[],
                row_count=0,
                error_code="TOOL_INVOCATION_ERROR",
                error="參數驗證失敗",
                elapsed_ms=int((time.monotonic() - start) * 1000),
            )

        try:
            rows = await asyncio.to_thread(self._query, validated, user_ctx.section)
        except Exception:
            logger.exception(
                "get_recent_fault_distribution failed",
                extra={"group_by": validated.group_by, "user_id": user_ctx.user_id},
            )
            return ToolResult(
                success=False,
                rows=[],
                row_count=0,
                error_code="TOOL_EXECUTION_ERROR",
                error="故障分布查詢失敗",
                elapsed_ms=int((time.monotonic() - start) * 1000),
            )

        label = "故障等級" if validated.group_by == "urgency" else "段管"
        chart_hint = {
            "type": "bar" if validated.group_by == "section" else "pie",
            "x_field": label,
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

    def _query(self, p: _Input, section: str | None) -> list[dict[str, Any]]:
        from_ts, to_ts = resolve_date_range(
            date_range=p.date_range,
            from_date=p.from_date,
            to_date=p.to_date,
        )

        if p.group_by == "urgency":
            group_field = "urgency"
            null_filter = "AND urgency IS NOT NULL AND urgency != ''"
            order_by = "urgency"
            label = "故障等級"
        else:
            group_field = "report_unit"
            null_filter = ""
            order_by = "count DESC"
            label = "段管"

        sql = f"""
            SELECT
                {group_field} AS category,
                COUNT(*) AS count,
                ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS percentage
            FROM maximo_fault_reports
            WHERE report_date BETWEEN %s AND %s
            {null_filter}
        """
        args: list[Any] = [from_ts, to_ts]

        if section:
            sql += " AND report_unit = %s"
            args.append(section)

        sql += f" GROUP BY {group_field} ORDER BY {order_by}"

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
                label: r["category"],
                "count": int(r["count"]),
                "percentage": float(r["percentage"]),
            }
            for r in raw_rows
        ]


# Registry auto-discovery: db_pool=None; T014 API wiring 時注入：
#   registry.get("get_recent_fault_distribution")._db_pool = app.state.db_pool
REGISTER = GetRecentFaultDistributionTool()
