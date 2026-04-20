"""
Tool 2: search_workorders_by_vehicle — 依車號查工單（UNION PM+CM）

SSH 實測（2026-04-20）：
- maximo_pm_workorders 331K 筆，work_type: 1A/2A/3A/4A（定檢）
- maximo_cm_workorders   6K 筆，work_type: T1/TR/CM（臨修）
- status 為 9 種中文值（直接存中文，非英文 enum）
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

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

# SSH 實測的 9 種中文 status（FR-014a）
_STATUS_OPEN = ("工單初始", "核簽中", "執行中未派工", "執行中已派工", "完工待回報", "檢修完成")
_STATUS_CLOSED = ("工單結案",)
_STATUS_CANCELLED = ("工單取消", "工單退回")

# 手動建構 flat schema — pydantic Optional[Literal] 會產生 anyOf，被 validate_tool_schema 阻擋
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "asset_num": {
            "type": "string",
            "description": "車輛資產編號，如 A12345",
        },
        "status": {
            "type": "string",
            "enum": list(_STATUS_OPEN + _STATUS_CLOSED + _STATUS_CANCELLED),
            "description": "單一工單狀態過濾（與 status_group 擇一使用，同時設定以 status 優先）",
        },
        "status_group": {
            "type": "string",
            "enum": ["open", "closed", "cancelled"],
            "description": "open=執行中 6 種, closed=工單結案, cancelled=工單取消/工單退回",
        },
        "wo_type": {
            "type": "string",
            "enum": ["定檢", "臨修", "all"],
            "default": "all",
            "description": "工單類型：定檢(PM)/臨修(CM)/全部(all)",
        },
        "date_range": {
            "type": "string",
            "enum": ["last_7d", "last_30d", "last_90d", "prev_week", "prev_month", "this_month", "all"],
            "default": "last_30d",
            "description": "日期範圍 preset；若同時提供 from_date+to_date 則 preset 被覆蓋",
        },
        "from_date": {
            "type": "string",
            "description": "ISO 8601 起始日期，如 2026-01-01（與 to_date 配對使用）",
        },
        "to_date": {
            "type": "string",
            "description": "ISO 8601 結束日期，如 2026-03-31",
        },
    },
    "required": ["asset_num"],
}

validate_tool_schema(_SCHEMA)  # 啟動時驗證，確保與 Anthropic tool_use 相容


class _Input(BaseModel):
    """Runtime 參數驗證。schema 與此分離（見 _SCHEMA）。"""

    asset_num: str = Field(..., description="車輛資產編號")
    status: str | None = None
    status_group: str | None = None
    wo_type: str = "all"
    date_range: str = "last_30d"
    from_date: str | None = None
    to_date: str | None = None

    def model_post_init(self, __context: Any) -> None:
        _valid_statuses = set(_STATUS_OPEN + _STATUS_CLOSED + _STATUS_CANCELLED)
        if self.status is not None and self.status not in _valid_statuses:
            raise ValueError(f"Invalid status: {self.status!r}")
        if self.status_group is not None and self.status_group not in ("open", "closed", "cancelled"):
            raise ValueError(f"Invalid status_group: {self.status_group!r}")
        if self.wo_type not in ("定檢", "臨修", "all"):
            raise ValueError(f"Invalid wo_type: {self.wo_type!r}")
        if self.date_range not in ("last_7d", "last_30d", "last_90d", "prev_week", "prev_month", "this_month", "all"):
            raise ValueError(f"Invalid date_range: {self.date_range!r}")


class SearchWorkordersByVehicleTool(Tool):
    definition = ToolDefinition(
        name="search_workorders_by_vehicle",
        description=(
            "依車號查工單。合併 PM 定檢 + CM 臨修 ETL 表，回傳 list 含工單類型欄位。"
            "支援狀態過濾（單一中文值或 open/closed/cancelled 分組）、日期範圍、工單類型（定檢/臨修/all）。"
            "使用場景：『A12345 最近故障』、『查這台車的工單』、『上個月未結案工單』。"
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
                "SearchWorkordersByVehicleTool._db_pool not injected. "
                "Call tool._db_pool = app.state.db_pool before execute."
            )

        try:
            validated = _Input.model_validate(params)
        except Exception as e:
            logger.warning("Invalid params for search_workorders_by_vehicle: %s", e)
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
                "search_workorders_by_vehicle query failed",
                extra={"asset_num": validated.asset_num, "user_id": user_ctx.user_id},
            )
            return ToolResult(
                success=False,
                rows=[],
                row_count=0,
                error_code="TOOL_EXECUTION_ERROR",
                error="工單查詢失敗",
                elapsed_ms=int((time.monotonic() - start) * 1000),
            )

        return ToolResult(
            success=True,
            rows=rows,
            row_count=len(rows),
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )

    def _query(self, params: _Input, section: str | None) -> list[dict[str, Any]]:
        """Sync SQL query on thread pool. Returns chinese-mapped rows."""
        status_values = self._resolve_statuses(params)
        from_ts, to_ts = resolve_date_range(
            date_range=params.date_range,
            from_date=params.from_date,
            to_date=params.to_date,
        )

        subqueries: list[str] = []
        args: list[Any] = []

        def _add_subquery(table: str, wo_type_label: str) -> None:
            sub = (
                f"SELECT wonum, assetnum, status, '{wo_type_label}' AS wo_type,"  # noqa: S608
                " work_type, description, report_date, act_start, act_finish"
                f" FROM {table}"
                " WHERE assetnum = %s"
            )
            sub_args: list[Any] = [params.asset_num]

            if status_values is not None:
                placeholders = ", ".join(["%s"] * len(status_values))
                sub += f" AND status IN ({placeholders})"
                sub_args.extend(status_values)

            if from_ts and to_ts:
                sub += " AND report_date BETWEEN %s AND %s"
                sub_args.extend([from_ts, to_ts])

            if section:
                sub += " AND maintenance_section = %s"
                sub_args.append(section)

            subqueries.append(sub)
            args.extend(sub_args)

        if params.wo_type in ("定檢", "all"):
            _add_subquery("maximo_pm_workorders", "定檢")
        if params.wo_type in ("臨修", "all"):
            _add_subquery("maximo_cm_workorders", "臨修")

        sql = " UNION ALL ".join(subqueries) + " ORDER BY report_date DESC NULLS LAST LIMIT 200"

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
    def _resolve_statuses(p: _Input) -> tuple[str, ...] | None:
        """status 優先；status_group 次之；都無則不加 filter（return None）。"""
        if p.status is not None:
            return (p.status,)
        if p.status_group == "open":
            return _STATUS_OPEN
        if p.status_group == "closed":
            return _STATUS_CLOSED
        if p.status_group == "cancelled":
            return _STATUS_CANCELLED
        return None

    @staticmethod
    def _to_chinese(raw: dict) -> dict[str, Any]:
        """欄位名英文 → 中文，timestamp → ISO string。"""

        def _iso(val: Any) -> str | None:
            return val.isoformat() if val is not None else None

        return {
            "工單號":   raw.get("wonum"),
            "車號":     raw.get("assetnum"),
            "狀態":     raw.get("status"),
            "工單類型":  raw.get("wo_type"),
            "工作類型":  raw.get("work_type"),
            "描述":     raw.get("description"),
            "通報日期":  _iso(raw.get("report_date")),
            "實際開始":  _iso(raw.get("act_start")),
            "實際完工":  _iso(raw.get("act_finish")),
        }


# Registry auto-discovery：允許 db_pool=None；T014 API wiring 時注入：
#   registry.get("search_workorders_by_vehicle")._db_pool = app.state.db_pool
REGISTER = SearchWorkordersByVehicleTool()
