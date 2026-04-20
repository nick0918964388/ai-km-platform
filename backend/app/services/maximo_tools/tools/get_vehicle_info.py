"""
Tool 1: get_vehicle_info — 查詢單一車輛基本資料。

SSH 實測資料（2026-04-20）：
- maximo_mxasset 無 description 欄位（已移除）
- status 為英文 enum：OPERATING / NOT READY / DECOMMISSIONED / INACTIVE
- eq3/eq4/eq11 可能為空（eq11 實測 48% 為空）
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
from app.services.maximo_tools.mappers.vehicle_category import from_code

logger = logging.getLogger(__name__)

# Asset status 英文 → 中文（SSH 實測 2026-04-20）
_ASSET_STATUS_CHINESE: dict[str, str] = {
    "OPERATING":      "運轉中",
    "NOT READY":      "未就緒",
    "DECOMMISSIONED": "除役",
    "INACTIVE":       "停用",
}


class _Input(BaseModel):
    asset_num: str = Field(..., description="車輛資產編號，如 A12345")


_SCHEMA = _Input.model_json_schema()
validate_tool_schema(_SCHEMA)  # 啟動時驗證，確保與 Anthropic tool_use 相容


class GetVehicleInfoTool(Tool):
    definition = ToolDefinition(
        name="get_vehicle_info",
        description=(
            "查詢單一車輛的基本資料（車型、車種、大分類、狀態、站點等）。"
            "適用情境：使用者問『A12345 基本資料』、『這台車是什麼車型』。"
            "限制：一次查一台車，不支援批次。"
        ),
        input_schema=_SCHEMA,
    )

    def __init__(self, db_pool=None):
        """
        Args:
            db_pool: psycopg2 pool with getconn()/putconn() interface。
                     允許 None，T014 API wiring 時透過 _db_pool 屬性注入。
        """
        self._db_pool = db_pool

    async def execute(self, params: dict, user_ctx: UserContext) -> ToolResult:
        if self._db_pool is None:
            raise RuntimeError(
                "GetVehicleInfoTool._db_pool not injected. "
                "Call tool._db_pool = app.state.db_pool before execute."
            )

        start = time.monotonic()
        try:
            validated = _Input.model_validate(params)
        except Exception as e:
            logger.warning("Invalid params for get_vehicle_info: %s", e)
            return ToolResult(
                success=False,
                rows=[],
                row_count=0,
                error_code="TOOL_INVOCATION_ERROR",
                error="參數驗證失敗",
                elapsed_ms=int((time.monotonic() - start) * 1000),
            )

        try:
            rows = await asyncio.to_thread(self._query, validated.asset_num)
        except Exception:
            logger.exception(
                "get_vehicle_info query failed",
                extra={"asset_num": validated.asset_num, "user_id": user_ctx.user_id},
            )
            return ToolResult(
                success=False,
                rows=[],
                row_count=0,
                error_code="TOOL_EXECUTION_ERROR",
                error="車輛資料查詢失敗",
                elapsed_ms=int((time.monotonic() - start) * 1000),
            )

        elapsed = int((time.monotonic() - start) * 1000)
        return ToolResult(
            success=True,
            rows=rows,
            row_count=len(rows),
            elapsed_ms=elapsed,
        )

    def _query(self, asset_num: str) -> list[dict[str, Any]]:
        """Sync SQL query on thread pool. Returns chinese-mapped rows.

        Note: maximo_mxasset 無 description 欄位（SSH 實測確認）。
        """
        sql = """
            SELECT
                assetnum,
                eq3,
                eq4,
                eq11,
                status,
                assettype,
                siteid
            FROM maximo_mxasset
            WHERE assetnum = %s
            LIMIT 1
        """
        conn = self._db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (asset_num,))
                row = cur.fetchone()
                if row is None:
                    return []
                col_names = [d[0] for d in cur.description]
                raw = dict(zip(col_names, row))
        finally:
            self._db_pool.putconn(conn)

        return [self._to_chinese(raw)]

    @staticmethod
    def _to_chinese(raw: dict) -> dict[str, Any]:
        """英文代碼 → 中文顯示欄位。空字串統一轉 None 讓前端好處理。"""
        eq11 = raw.get("eq11") or ""
        status_raw = raw.get("status") or ""
        return {
            "車號":     raw.get("assetnum"),
            "車種":     raw.get("eq3") or None,
            "車型":     raw.get("eq4") or None,
            "大分類":   from_code(eq11) if eq11 else None,
            "大分類代碼": eq11 or None,
            "狀態":     _ASSET_STATUS_CHINESE.get(status_raw) or status_raw or None,
            "狀態代碼":  status_raw or None,
            "資產類型":  raw.get("assettype") or None,
            "站點":     raw.get("siteid") or None,
        }


# Registry auto-discovery：允許 db_pool=None；T014 API wiring 時注入：
#   registry.get("get_vehicle_info")._db_pool = app.state.db_pool
REGISTER = GetVehicleInfoTool()
