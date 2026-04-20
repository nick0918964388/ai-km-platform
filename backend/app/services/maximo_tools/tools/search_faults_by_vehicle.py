"""Tool 3: search_faults_by_vehicle — 依車號查故障通報 (maximo_fault_reports ETL)

SSH 實測資料（2026-04-20）：
- 表：maximo_fault_reports（395 筆）
- status 中文 6 種：立案(360) / 結案(14) / 處理中(10) / 取消(7) / 接件中(2) / 可放車(2)
- urgency A(20) / B(26) / C(125) / NULL(224) — 224/395 筆為空
- row filter 欄位：report_unit（段/所）
"""
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
from app.services.maximo_tools.mappers.date_range import resolve as resolve_date_range

logger = logging.getLogger(__name__)

# status_group 展開（FR-014b）
_STATUS_OPEN = ("立案", "接件中", "處理中")
_STATUS_CLOSED = ("結案", "可放車")
_STATUS_CANCELLED = ("取消",)

# 手工 flat schema — 避免 Pydantic v2 為 Optional[Literal] 產生 anyOf
# validate_tool_schema 會拒絕 anyOf / $ref / $defs / oneOf / allOf
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "asset_num": {
            "type": "string",
            "description": "車輛資產編號",
        },
        "urgency": {
            "type": "string",
            "enum": ["A", "B", "C"],
            "description": "故障等級篩選（A/B/C）；不填則不過濾",
        },
        "status_group": {
            "type": "string",
            "enum": ["open", "closed", "cancelled"],
            "description": "狀態分組：open=立案/接件中/處理中；closed=結案/可放車；cancelled=取消",
        },
        "date_range": {
            "type": "string",
            "enum": [
                "last_7d", "last_30d", "last_90d",
                "prev_week", "prev_month", "this_month", "all",
            ],
            "default": "last_30d",
            "description": "日期範圍預設（以 report_date 過濾）",
        },
        "from_date": {
            "type": "string",
            "description": "自訂起始日期 ISO 8601（YYYY-MM-DD）；與 to_date 同時提供時優先於 date_range",
        },
        "to_date": {
            "type": "string",
            "description": "自訂結束日期 ISO 8601（YYYY-MM-DD）",
        },
    },
    "required": ["asset_num"],
}

validate_tool_schema(_SCHEMA)  # 啟動時驗證，確保 flat schema 相容


class _Input(BaseModel):
    """內部驗證用，不用於 schema 產生。"""
    asset_num: str = Field(..., description="車輛資產編號")
    urgency: Literal["A", "B", "C"] | None = None
    status_group: Literal["open", "closed", "cancelled"] | None = None
    date_range: Literal[
        "last_7d", "last_30d", "last_90d",
        "prev_week", "prev_month", "this_month", "all",
    ] = "last_30d"
    from_date: str | None = None
    to_date: str | None = None


class SearchFaultsByVehicleTool(Tool):
    definition = ToolDefinition(
        name="search_faults_by_vehicle",
        description=(
            "依車號查故障通報。支援故障等級（A/B/C）、狀態分組（open/closed/cancelled）、日期範圍過濾。"
            "回傳欄位：通報號 / 車號 / 狀態 / 故障等級 / 描述 / TCMS碼 / 通報日期。"
            "使用場景：『A12345 故障』、『urgency A 故障』、『上個月 A 車故障』。"
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
                "SearchFaultsByVehicleTool._db_pool not injected. "
                "Call tool._db_pool = app.state.db_pool before execute."
            )

        try:
            validated = _Input.model_validate(params)
        except Exception as exc:
            logger.warning("Invalid params for search_faults_by_vehicle: %s", exc)
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
                "search_faults_by_vehicle query failed",
                extra={"asset_num": validated.asset_num, "user_id": user_ctx.user_id},
            )
            return ToolResult(
                success=False,
                rows=[],
                row_count=0,
                error_code="TOOL_EXECUTION_ERROR",
                error="故障通報查詢失敗",
                elapsed_ms=int((time.monotonic() - start) * 1000),
            )

        return ToolResult(
            success=True,
            rows=rows,
            row_count=len(rows),
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )

    def _query(self, p: _Input, section: str | None) -> list[dict[str, Any]]:
        sql = """
            SELECT ticketid, assetnum, status, urgency, grade, tcms_code,
                   description, fault_symptom, handling_desc,
                   report_date, occurrence_date
            FROM maximo_fault_reports
            WHERE assetnum = %s
        """
        args: list[Any] = [p.asset_num]

        # urgency filter（NULL 值不會被 '= A' 命中，行為正確）
        if p.urgency is not None:
            sql += " AND urgency = %s"
            args.append(p.urgency)

        # status_group 展開
        status_values = self._resolve_statuses(p.status_group)
        if status_values is not None:
            placeholders = ", ".join(["%s"] * len(status_values))
            sql += f" AND status IN ({placeholders})"
            args.extend(status_values)

        # 日期範圍（date_range=all 時不加 WHERE 條件，避免無謂 BETWEEN 1970 AND now）
        if p.date_range != "all" or (p.from_date and p.to_date):
            from_ts, to_ts = resolve_date_range(
                date_range=p.date_range,
                from_date=p.from_date,
                to_date=p.to_date,
            )
            sql += " AND report_date BETWEEN %s AND %s"
            args.extend([from_ts, to_ts])

        # row filter（依段/所過濾，section=None 時不限制）
        if section:
            sql += " AND report_unit = %s"
            args.append(section)

        sql += " ORDER BY report_date DESC NULLS LAST LIMIT 200"

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
    def _resolve_statuses(group: str | None) -> tuple[str, ...] | None:
        if group == "open":
            return _STATUS_OPEN
        if group == "closed":
            return _STATUS_CLOSED
        if group == "cancelled":
            return _STATUS_CANCELLED
        return None

    @staticmethod
    def _to_chinese(raw: dict) -> dict[str, Any]:
        report_date = raw.get("report_date")
        occurrence_date = raw.get("occurrence_date")
        return {
            "通報號":  raw.get("ticketid"),
            "車號":   raw.get("assetnum"),
            "狀態":   raw.get("status"),
            "故障等級": raw.get("urgency"),
            "事件等級": raw.get("grade"),
            "TCMS碼": raw.get("tcms_code"),
            "故障描述": raw.get("description"),
            "故障現象": raw.get("fault_symptom"),
            "處理情形": raw.get("handling_desc"),
            "通報日期": report_date.isoformat() if report_date is not None else None,
            "發生時間": occurrence_date.isoformat() if occurrence_date is not None else None,
        }


# Registry auto-discovery：允許 db_pool=None；T014 API wiring 時注入：
#   registry.get("search_faults_by_vehicle")._db_pool = app.state.db_pool
REGISTER = SearchFaultsByVehicleTool()
