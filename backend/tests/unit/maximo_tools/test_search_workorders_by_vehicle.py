"""
Unit tests for SearchWorkordersByVehicleTool (Tool 2).

策略：mock psycopg2 pool + cursor，不碰真實 DB。
"""
from __future__ import annotations

from datetime import datetime, date
from unittest.mock import MagicMock, call, patch

import pytest

from app.services.maximo_tools.base import ToolResult, UserContext
from app.services.maximo_tools.tools.search_workorders_by_vehicle import (
    SearchWorkordersByVehicleTool,
    _SCHEMA,
    _STATUS_OPEN,
    _STATUS_CLOSED,
    _STATUS_CANCELLED,
    REGISTER,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user_ctx(**kwargs) -> UserContext:
    defaults = dict(user_id="u-test-002", role="admin")
    defaults.update(kwargs)
    return UserContext(**defaults)


_WO_COLS = ["wonum", "assetnum", "status", "wo_type", "work_type", "description",
            "report_date", "act_start", "act_finish"]


def _make_pool(fetchall_return: list | None = None) -> MagicMock:
    """
    Build a mock psycopg2-style pool.
    fetchall_return: list of tuples matching _WO_COLS column order.
    """
    rows = fetchall_return or []
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    cursor.description = [(col,) for col in _WO_COLS]
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.cursor.return_value = cursor

    pool = MagicMock()
    pool.getconn.return_value = conn
    return pool


def _sample_wo_tuple(
    wonum="WO001", assetnum="35PPT1108", status="執行中已派工",
    wo_type="定檢", work_type="1A", description="月檢",
    report_date=None, act_start=None, act_finish=None,
) -> tuple:
    return (wonum, assetnum, status, wo_type, work_type, description,
            report_date, act_start, act_finish)


# ---------------------------------------------------------------------------
# 1. ToolDefinition
# ---------------------------------------------------------------------------

class TestDefinition:
    def test_definition_name(self):
        assert SearchWorkordersByVehicleTool.definition.name == "search_workorders_by_vehicle"

    def test_definition_has_description(self):
        assert len(SearchWorkordersByVehicleTool.definition.description) > 0

    def test_input_schema_valid(self):
        from app.services.maximo_tools.base import validate_tool_schema
        validate_tool_schema(_SCHEMA)

    def test_input_schema_has_asset_num_and_vehicle_type(self):
        """asset_num and vehicle_type are both optional in schema (XOR enforced at runtime)."""
        assert "asset_num" in _SCHEMA.get("properties", {})
        assert "vehicle_type" in _SCHEMA.get("properties", {})
        # Neither is required[] — XOR constraint enforced by _Input model_validator
        assert "asset_num" not in _SCHEMA.get("required", [])
        assert "vehicle_type" not in _SCHEMA.get("required", [])

    def test_schema_has_no_forbidden_keys(self):
        """Flat schema — no $defs / $ref / anyOf / oneOf / allOf."""
        import json
        schema_str = json.dumps(_SCHEMA)
        for forbidden in ("$defs", "$ref", "anyOf", "oneOf", "allOf"):
            assert f'"{forbidden}"' not in schema_str, f"Forbidden key found: {forbidden}"


# ---------------------------------------------------------------------------
# 2. Happy path — default params (wo_type=all, date_range=last_30d)
# ---------------------------------------------------------------------------

class TestExecuteHappyPath:
    @pytest.mark.asyncio
    async def test_returns_chinese_keys(self):
        row = _sample_wo_tuple()
        tool = SearchWorkordersByVehicleTool(db_pool=_make_pool([row]))
        result = await tool.execute({"asset_num": "35PPT1108"}, _make_user_ctx())

        assert result.success is True
        assert result.row_count == 1
        r = result.rows[0]
        expected_keys = {"工單號", "車號", "狀態", "工單類型", "工作類型", "描述", "通報日期", "實際開始", "實際完工"}
        assert expected_keys == set(r.keys())

    @pytest.mark.asyncio
    async def test_wo_type_field_present(self):
        row = _sample_wo_tuple(wo_type="定檢")
        tool = SearchWorkordersByVehicleTool(db_pool=_make_pool([row]))
        result = await tool.execute({"asset_num": "35PPT1108"}, _make_user_ctx())

        assert result.rows[0]["工單類型"] == "定檢"

    @pytest.mark.asyncio
    async def test_empty_result_is_success(self):
        tool = SearchWorkordersByVehicleTool(db_pool=_make_pool([]))
        result = await tool.execute({"asset_num": "NO_WO_ASSET"}, _make_user_ctx())

        assert result.success is True
        assert result.rows == []
        assert result.row_count == 0
        assert result.error is None


# ---------------------------------------------------------------------------
# 3. status_group filter
# ---------------------------------------------------------------------------

class TestStatusGroupFilter:
    @pytest.mark.asyncio
    async def test_status_group_open_expands_to_6_values(self):
        pool = _make_pool([])
        tool = SearchWorkordersByVehicleTool(db_pool=pool)
        await tool.execute({"asset_num": "X", "status_group": "open"}, _make_user_ctx())

        # Capture the SQL args passed to cursor.execute
        conn = pool.getconn()
        cursor = conn.cursor().__enter__()
        call_args = cursor.execute.call_args
        sql, args = call_args[0]
        # Both PM and CM subqueries → 6 statuses each = 12 total status args
        # (plus 2 asset_num args + date args from last_30d × 2 subqueries)
        open_statuses = list(_STATUS_OPEN)
        for s in open_statuses:
            assert s in args, f"Expected status '{s}' in SQL args"

    @pytest.mark.asyncio
    async def test_status_group_closed_only_has_one_status(self):
        pool = _make_pool([])
        tool = SearchWorkordersByVehicleTool(db_pool=pool)
        await tool.execute({"asset_num": "X", "status_group": "closed"}, _make_user_ctx())

        conn = pool.getconn()
        cursor = conn.cursor().__enter__()
        _, args = cursor.execute.call_args[0]
        # 工單結案 should appear (once per subquery, 2 subqueries default = 2 times)
        assert "工單結案" in args
        # No open statuses
        for s in _STATUS_OPEN:
            assert s not in args, f"Unexpected open status '{s}' in closed filter"

    @pytest.mark.asyncio
    async def test_status_group_cancelled_has_two_statuses(self):
        pool = _make_pool([])
        tool = SearchWorkordersByVehicleTool(db_pool=pool)
        await tool.execute({"asset_num": "X", "status_group": "cancelled"}, _make_user_ctx())

        conn = pool.getconn()
        cursor = conn.cursor().__enter__()
        _, args = cursor.execute.call_args[0]
        assert "工單取消" in args
        assert "工單退回" in args


# ---------------------------------------------------------------------------
# 4. wo_type filter
# ---------------------------------------------------------------------------

class TestWoTypeFilter:
    @pytest.mark.asyncio
    async def test_wo_type_pm_only_queries_pm_table(self):
        pool = _make_pool([])
        tool = SearchWorkordersByVehicleTool(db_pool=pool)
        await tool.execute({"asset_num": "X", "wo_type": "定檢"}, _make_user_ctx())

        conn = pool.getconn()
        cursor = conn.cursor().__enter__()
        sql, _ = cursor.execute.call_args[0]
        assert "maximo_pm_workorders" in sql
        assert "maximo_cm_workorders" not in sql

    @pytest.mark.asyncio
    async def test_wo_type_cm_only_queries_cm_table(self):
        pool = _make_pool([])
        tool = SearchWorkordersByVehicleTool(db_pool=pool)
        await tool.execute({"asset_num": "X", "wo_type": "臨修"}, _make_user_ctx())

        conn = pool.getconn()
        cursor = conn.cursor().__enter__()
        sql, _ = cursor.execute.call_args[0]
        assert "maximo_cm_workorders" in sql
        assert "maximo_pm_workorders" not in sql

    @pytest.mark.asyncio
    async def test_wo_type_all_unions_both_tables(self):
        pool = _make_pool([])
        tool = SearchWorkordersByVehicleTool(db_pool=pool)
        await tool.execute({"asset_num": "X", "wo_type": "all"}, _make_user_ctx())

        conn = pool.getconn()
        cursor = conn.cursor().__enter__()
        sql, _ = cursor.execute.call_args[0]
        assert "maximo_pm_workorders" in sql
        assert "maximo_cm_workorders" in sql
        assert "UNION ALL" in sql

    @pytest.mark.asyncio
    async def test_wo_type_default_is_all(self):
        pool = _make_pool([])
        tool = SearchWorkordersByVehicleTool(db_pool=pool)
        await tool.execute({"asset_num": "X"}, _make_user_ctx())

        conn = pool.getconn()
        cursor = conn.cursor().__enter__()
        sql, _ = cursor.execute.call_args[0]
        assert "maximo_pm_workorders" in sql
        assert "maximo_cm_workorders" in sql


# ---------------------------------------------------------------------------
# 5. date_range filter
# ---------------------------------------------------------------------------

class TestDateRangeFilter:
    @pytest.mark.asyncio
    async def test_prev_month_injects_date_range(self):
        """prev_month → from_ts/to_ts injected in SQL args."""
        pool = _make_pool([])
        tool = SearchWorkordersByVehicleTool(db_pool=pool)
        await tool.execute({"asset_num": "X", "date_range": "prev_month"}, _make_user_ctx())

        conn = pool.getconn()
        cursor = conn.cursor().__enter__()
        _, args = cursor.execute.call_args[0]
        # args should contain datetime objects (from_ts, to_ts) × 2 subqueries
        datetime_args = [a for a in args if isinstance(a, datetime)]
        assert len(datetime_args) >= 2

    @pytest.mark.asyncio
    async def test_prev_month_timestamps_are_correct_month(self):
        """prev_month 的 from_ts 應在上月 1 日。"""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        pool = _make_pool([])
        tool = SearchWorkordersByVehicleTool(db_pool=pool)
        # Patch resolve to capture output
        with patch(
            "app.services.maximo_tools.tools.search_workorders_by_vehicle.resolve_date_range",
            wraps=lambda **kw: __import__(
                "app.services.maximo_tools.mappers.date_range", fromlist=["resolve"]
            ).resolve(**kw),
        ) as mock_resolve:
            await tool.execute(
                {"asset_num": "X", "date_range": "prev_month"},
                _make_user_ctx(),
            )
            mock_resolve.assert_called_once()
            kw = mock_resolve.call_args.kwargs
            assert kw["date_range"] == "prev_month"


# ---------------------------------------------------------------------------
# 6. Single status filter
# ---------------------------------------------------------------------------

class TestSingleStatusFilter:
    @pytest.mark.asyncio
    async def test_single_status_工單初始(self):
        pool = _make_pool([])
        tool = SearchWorkordersByVehicleTool(db_pool=pool)
        await tool.execute({"asset_num": "X", "status": "工單初始"}, _make_user_ctx())

        conn = pool.getconn()
        cursor = conn.cursor().__enter__()
        _, args = cursor.execute.call_args[0]
        assert "工單初始" in args
        # Should NOT contain other statuses
        for s in _STATUS_OPEN[1:]:  # 核簽中 etc.
            assert s not in args


# ---------------------------------------------------------------------------
# 7. Row filter (maintenance_section)
# ---------------------------------------------------------------------------

class TestRowFilter:
    @pytest.mark.asyncio
    async def test_section_injected_when_set(self):
        pool = _make_pool([])
        tool = SearchWorkordersByVehicleTool(db_pool=pool)
        ctx = _make_user_ctx(section="北部維修段")
        await tool.execute({"asset_num": "X"}, ctx)

        conn = pool.getconn()
        cursor = conn.cursor().__enter__()
        sql, args = cursor.execute.call_args[0]
        assert "maintenance_section" in sql
        assert "北部維修段" in args

    @pytest.mark.asyncio
    async def test_section_none_no_filter(self):
        pool = _make_pool([])
        tool = SearchWorkordersByVehicleTool(db_pool=pool)
        ctx = _make_user_ctx(section=None)
        await tool.execute({"asset_num": "X"}, ctx)

        conn = pool.getconn()
        cursor = conn.cursor().__enter__()
        sql, args = cursor.execute.call_args[0]
        assert "maintenance_section" not in sql


# ---------------------------------------------------------------------------
# 8. No pool — RuntimeError
# ---------------------------------------------------------------------------

class TestNoPool:
    @pytest.mark.asyncio
    async def test_no_pool_raises_runtime_error(self):
        tool = SearchWorkordersByVehicleTool()  # db_pool=None by default
        with pytest.raises(RuntimeError, match="db_pool not injected"):
            await tool.execute({"asset_num": "X"}, _make_user_ctx())


# ---------------------------------------------------------------------------
# 9. Invalid params — TOOL_INVOCATION_ERROR
# ---------------------------------------------------------------------------

class TestInvalidParams:
    @pytest.mark.asyncio
    async def test_missing_asset_num(self):
        tool = SearchWorkordersByVehicleTool(db_pool=_make_pool())
        result = await tool.execute({}, _make_user_ctx())

        assert result.success is False
        assert result.error_code == "TOOL_INVOCATION_ERROR"
        assert result.rows == []
        assert result.row_count == 0

    @pytest.mark.asyncio
    async def test_invalid_status_value(self):
        tool = SearchWorkordersByVehicleTool(db_pool=_make_pool())
        result = await tool.execute(
            {"asset_num": "X", "status": "不存在的狀態"},
            _make_user_ctx(),
        )
        assert result.success is False
        assert result.error_code == "TOOL_INVOCATION_ERROR"

    @pytest.mark.asyncio
    async def test_invalid_status_group_value(self):
        tool = SearchWorkordersByVehicleTool(db_pool=_make_pool())
        result = await tool.execute(
            {"asset_num": "X", "status_group": "invalid_group"},
            _make_user_ctx(),
        )
        assert result.success is False
        assert result.error_code == "TOOL_INVOCATION_ERROR"

    @pytest.mark.asyncio
    async def test_invalid_wo_type(self):
        tool = SearchWorkordersByVehicleTool(db_pool=_make_pool())
        result = await tool.execute(
            {"asset_num": "X", "wo_type": "不存在"},
            _make_user_ctx(),
        )
        assert result.success is False
        assert result.error_code == "TOOL_INVOCATION_ERROR"


# ---------------------------------------------------------------------------
# 10. DB exception — TOOL_EXECUTION_ERROR
# ---------------------------------------------------------------------------

class TestDbException:
    @pytest.mark.asyncio
    async def test_pool_getconn_raises(self):
        pool = MagicMock()
        pool.getconn.side_effect = Exception("Connection pool exhausted")

        tool = SearchWorkordersByVehicleTool(db_pool=pool)
        result = await tool.execute({"asset_num": "X"}, _make_user_ctx())

        assert result.success is False
        assert result.error_code == "TOOL_EXECUTION_ERROR"
        assert result.rows == []

    @pytest.mark.asyncio
    async def test_cursor_execute_raises(self):
        cursor = MagicMock()
        cursor.execute.side_effect = Exception("DB timeout")
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cursor

        pool = MagicMock()
        pool.getconn.return_value = conn

        tool = SearchWorkordersByVehicleTool(db_pool=pool)
        result = await tool.execute({"asset_num": "X"}, _make_user_ctx())

        assert result.success is False
        assert result.error_code == "TOOL_EXECUTION_ERROR"

    @pytest.mark.asyncio
    async def test_putconn_called_on_exception(self):
        """finally 區塊確保 connection 不 leak。"""
        cursor = MagicMock()
        cursor.execute.side_effect = Exception("DB error")
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cursor

        pool = MagicMock()
        pool.getconn.return_value = conn

        tool = SearchWorkordersByVehicleTool(db_pool=pool)
        await tool.execute({"asset_num": "X"}, _make_user_ctx())

        pool.putconn.assert_called_once_with(conn)


# ---------------------------------------------------------------------------
# 11. _to_chinese field mapping
# ---------------------------------------------------------------------------

class TestToChineseMapping:
    def test_all_fields_mapped(self):
        raw = {
            "wonum": "WO123",
            "assetnum": "35PPT1108",
            "status": "執行中已派工",
            "wo_type": "定檢",
            "work_type": "1A",
            "description": "月定檢作業",
            "report_date": datetime(2026, 3, 1, 8, 0, 0),
            "act_start": datetime(2026, 3, 2, 9, 0, 0),
            "act_finish": datetime(2026, 3, 2, 17, 0, 0),
        }
        result = SearchWorkordersByVehicleTool._to_chinese(raw)

        assert result["工單號"] == "WO123"
        assert result["車號"] == "35PPT1108"
        assert result["狀態"] == "執行中已派工"
        assert result["工單類型"] == "定檢"
        assert result["工作類型"] == "1A"
        assert result["描述"] == "月定檢作業"
        assert result["通報日期"] == "2026-03-01T08:00:00"
        assert result["實際開始"] == "2026-03-02T09:00:00"
        assert result["實際完工"] == "2026-03-02T17:00:00"

    def test_none_timestamps_map_to_none(self):
        raw = {
            "wonum": "WO456",
            "assetnum": "X",
            "status": "工單初始",
            "wo_type": "臨修",
            "work_type": "CM",
            "description": None,
            "report_date": None,
            "act_start": None,
            "act_finish": None,
        }
        result = SearchWorkordersByVehicleTool._to_chinese(raw)

        assert result["通報日期"] is None
        assert result["實際開始"] is None
        assert result["實際完工"] is None
        assert result["描述"] is None


# ---------------------------------------------------------------------------
# 12. REGISTER module constant
# ---------------------------------------------------------------------------

class TestRegisterConstant:
    def test_register_is_tool_instance(self):
        from app.services.maximo_tools.base import Tool
        assert isinstance(REGISTER, Tool)

    def test_register_has_correct_name(self):
        assert REGISTER.definition.name == "search_workorders_by_vehicle"

    def test_register_db_pool_is_none(self):
        assert REGISTER._db_pool is None

    def test_register_db_pool_injectable(self):
        sentinel = object()
        old = REGISTER._db_pool
        try:
            REGISTER._db_pool = sentinel
            assert REGISTER._db_pool is sentinel
        finally:
            REGISTER._db_pool = old
