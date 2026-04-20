"""
Unit tests for SearchFaultsByVehicleTool (Tool 3).

策略：mock psycopg2 pool + cursor，不碰真實 DB。
"""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, call

import pytest

from app.services.maximo_tools.base import ToolResult, UserContext
from app.services.maximo_tools.tools.search_faults_by_vehicle import (
    SearchFaultsByVehicleTool,
    _SCHEMA,
    _STATUS_CANCELLED,
    _STATUS_CLOSED,
    _STATUS_OPEN,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_COL_NAMES = [
    "ticketid", "assetnum", "status", "urgency", "grade", "tcms_code",
    "description", "fault_symptom", "handling_desc", "report_date", "occurrence_date",
]


def _make_user_ctx(**kwargs) -> UserContext:
    defaults = dict(user_id="u-test-001", role="admin")
    defaults.update(kwargs)
    return UserContext(**defaults)


def _make_pool(fetchall_return: list | None = None) -> MagicMock:
    """
    Build a mock psycopg2-style pool returning given rows on fetchall().
    Each item in fetchall_return must be a tuple matching _COL_NAMES order.
    """
    if fetchall_return is None:
        fetchall_return = []

    cursor = MagicMock()
    cursor.fetchall.return_value = fetchall_return
    cursor.description = [(name,) for name in _COL_NAMES]
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.cursor.return_value = cursor

    pool = MagicMock()
    pool.getconn.return_value = conn
    return pool


def _make_row(**overrides) -> tuple:
    """Return a row tuple with sensible defaults, allow field overrides by name."""
    defaults = dict(
        ticketid="FR-001",
        assetnum="EMU852",
        status="立案",
        urgency="A",
        grade="1",
        tcms_code="T001",
        description="故障描述",
        fault_symptom="現象",
        handling_desc="處理",
        report_date=date(2026, 4, 1),
        occurrence_date=date(2026, 3, 31),
    )
    defaults.update(overrides)
    return tuple(defaults[k] for k in _COL_NAMES)


# ---------------------------------------------------------------------------
# 1. ToolDefinition validity
# ---------------------------------------------------------------------------

class TestDefinition:
    def test_name(self):
        assert SearchFaultsByVehicleTool.definition.name == "search_faults_by_vehicle"

    def test_description_nonempty(self):
        assert len(SearchFaultsByVehicleTool.definition.description) > 0

    def test_schema_flat_no_any_of(self):
        """_SCHEMA 必須通過 validate_tool_schema（無 anyOf / $ref 等）。"""
        from app.services.maximo_tools.base import validate_tool_schema
        validate_tool_schema(_SCHEMA)  # must not raise

    def test_schema_requires_asset_num(self):
        assert "asset_num" in _SCHEMA["properties"]
        assert "asset_num" in _SCHEMA["required"]

    def test_schema_optional_urgency_present(self):
        assert "urgency" in _SCHEMA["properties"]
        assert "urgency" not in _SCHEMA.get("required", [])

    def test_schema_optional_status_group_present(self):
        assert "status_group" in _SCHEMA["properties"]

    def test_schema_date_range_has_default(self):
        assert _SCHEMA["properties"]["date_range"]["default"] == "last_30d"


# ---------------------------------------------------------------------------
# 2. Happy path — no filters
# ---------------------------------------------------------------------------

class TestHappyPathNoFilter:
    @pytest.mark.asyncio
    async def test_returns_chinese_keys(self):
        pool = _make_pool([_make_row()])
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        result = await tool.execute({"asset_num": "EMU852"}, _make_user_ctx())

        assert result.success is True
        assert result.row_count == 1
        r = result.rows[0]
        expected = {"通報號", "車號", "狀態", "故障等級", "事件等級", "TCMS碼",
                    "故障描述", "故障現象", "處理情形", "通報日期", "發生時間"}
        assert expected.issubset(r.keys())

    @pytest.mark.asyncio
    async def test_sql_only_where_assetnum(self):
        """無 filter 時 SQL 只含 WHERE assetnum = %s，不含 urgency / status / date。"""
        pool = _make_pool()
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        await tool.execute({"asset_num": "EMU852"}, _make_user_ctx())

        conn = pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        executed_sql, executed_args = cur.execute.call_args[0]

        assert "assetnum = %s" in executed_sql
        assert "urgency = %s" not in executed_sql
        assert "status IN" not in executed_sql
        # date_range 預設 last_30d → 應含 BETWEEN
        assert "BETWEEN" in executed_sql
        assert executed_args[0] == "EMU852"

    @pytest.mark.asyncio
    async def test_empty_result_is_success(self):
        pool = _make_pool([])
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        result = await tool.execute({"asset_num": "NOT_EXIST"}, _make_user_ctx())

        assert result.success is True
        assert result.rows == []
        assert result.row_count == 0
        assert result.error is None


# ---------------------------------------------------------------------------
# 3. urgency filter
# ---------------------------------------------------------------------------

class TestUrgencyFilter:
    @pytest.mark.asyncio
    async def test_urgency_a_adds_sql_filter(self):
        pool = _make_pool()
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        await tool.execute({"asset_num": "EMU852", "urgency": "A"}, _make_user_ctx())

        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        sql, args = cur.execute.call_args[0]
        assert "urgency = %s" in sql
        assert "A" in args

    @pytest.mark.asyncio
    async def test_urgency_b(self):
        pool = _make_pool()
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        await tool.execute({"asset_num": "EMU852", "urgency": "B"}, _make_user_ctx())

        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        _, args = cur.execute.call_args[0]
        assert "B" in args

    @pytest.mark.asyncio
    async def test_urgency_c(self):
        pool = _make_pool()
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        await tool.execute({"asset_num": "EMU852", "urgency": "C"}, _make_user_ctx())

        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        _, args = cur.execute.call_args[0]
        assert "C" in args

    @pytest.mark.asyncio
    async def test_urgency_none_no_filter(self):
        """urgency=None → SQL WHERE clause 不含 urgency = %s。"""
        pool = _make_pool()
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        await tool.execute({"asset_num": "EMU852"}, _make_user_ctx())

        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        sql, _ = cur.execute.call_args[0]
        assert "urgency = %s" not in sql

    @pytest.mark.asyncio
    async def test_urgency_null_rows_not_matched_by_a_filter(self):
        """urgency=A filter 不會讓 urgency=NULL 的行通過（SQL 正確，DB 端保證）。
        此 test 驗證 SQL args 中 urgency='A' 確實被注入（不是 wildcard）。"""
        pool = _make_pool()
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        await tool.execute({"asset_num": "EMU852", "urgency": "A"}, _make_user_ctx())

        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        sql, args = cur.execute.call_args[0]
        # args 只有 'A'，沒有 NULL / None 混入
        assert "A" in args
        assert None not in args or args.index(None) > args.index("A")  # A 在前，無 wildcard


# ---------------------------------------------------------------------------
# 4. status_group filter
# ---------------------------------------------------------------------------

class TestStatusGroupFilter:
    @pytest.mark.asyncio
    async def test_open_adds_3_statuses(self):
        pool = _make_pool()
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        await tool.execute(
            {"asset_num": "EMU852", "status_group": "open", "date_range": "all"},
            _make_user_ctx(),
        )

        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        sql, args = cur.execute.call_args[0]
        assert "status IN" in sql
        for s in _STATUS_OPEN:
            assert s in args

    @pytest.mark.asyncio
    async def test_closed_adds_2_statuses(self):
        pool = _make_pool()
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        await tool.execute(
            {"asset_num": "EMU852", "status_group": "closed", "date_range": "all"},
            _make_user_ctx(),
        )

        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        sql, args = cur.execute.call_args[0]
        assert "status IN" in sql
        for s in _STATUS_CLOSED:
            assert s in args
        # only 2 status values
        status_in_args = [a for a in args if a in _STATUS_CLOSED]
        assert len(status_in_args) == 2

    @pytest.mark.asyncio
    async def test_cancelled_adds_1_status(self):
        pool = _make_pool()
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        await tool.execute(
            {"asset_num": "EMU852", "status_group": "cancelled", "date_range": "all"},
            _make_user_ctx(),
        )

        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        sql, args = cur.execute.call_args[0]
        assert "status IN" in sql
        assert _STATUS_CANCELLED[0] in args

    @pytest.mark.asyncio
    async def test_no_status_group_no_status_filter(self):
        pool = _make_pool()
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        await tool.execute({"asset_num": "EMU852"}, _make_user_ctx())

        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        sql, _ = cur.execute.call_args[0]
        assert "status IN" not in sql


# ---------------------------------------------------------------------------
# 5. date_range filter
# ---------------------------------------------------------------------------

class TestDateRangeFilter:
    @pytest.mark.asyncio
    async def test_last_7d_adds_between(self):
        pool = _make_pool()
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        await tool.execute(
            {"asset_num": "EMU852", "date_range": "last_7d"}, _make_user_ctx()
        )

        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        sql, args = cur.execute.call_args[0]
        assert "BETWEEN" in sql
        # args contains two datetime objects after asset_num
        datetime_args = [a for a in args if isinstance(a, datetime)]
        assert len(datetime_args) == 2

    @pytest.mark.asyncio
    async def test_last_30d_default_adds_between(self):
        """date_range 預設 last_30d → BETWEEN 存在。"""
        pool = _make_pool()
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        await tool.execute({"asset_num": "EMU852"}, _make_user_ctx())

        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        sql, _ = cur.execute.call_args[0]
        assert "BETWEEN" in sql

    @pytest.mark.asyncio
    async def test_date_range_all_no_between(self):
        """date_range=all → SQL 不含 BETWEEN（效能優化，不篩日期）。"""
        pool = _make_pool()
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        await tool.execute(
            {"asset_num": "EMU852", "date_range": "all"}, _make_user_ctx()
        )

        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        sql, _ = cur.execute.call_args[0]
        assert "BETWEEN" not in sql

    @pytest.mark.asyncio
    async def test_explicit_from_to_overrides_preset(self):
        """from_date + to_date 同時提供 → 走 explicit，忽略 date_range preset。"""
        pool = _make_pool()
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        await tool.execute(
            {
                "asset_num": "EMU852",
                "date_range": "last_7d",
                "from_date": "2026-01-01",
                "to_date": "2026-01-31",
            },
            _make_user_ctx(),
        )

        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        sql, args = cur.execute.call_args[0]
        assert "BETWEEN" in sql
        # from_date 應對應 2026-01-01 00:00
        datetime_args = [a for a in args if isinstance(a, datetime)]
        assert datetime_args[0].month == 1
        assert datetime_args[0].day == 1


# ---------------------------------------------------------------------------
# 6. section (row filter)
# ---------------------------------------------------------------------------

class TestSectionRowFilter:
    @pytest.mark.asyncio
    async def test_section_adds_report_unit_filter(self):
        pool = _make_pool()
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        ctx = _make_user_ctx(section="台北段")
        await tool.execute({"asset_num": "EMU852", "date_range": "all"}, ctx)

        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        sql, args = cur.execute.call_args[0]
        assert "report_unit = %s" in sql
        assert "台北段" in args

    @pytest.mark.asyncio
    async def test_section_none_no_report_unit_filter(self):
        """section=None（一般 admin）→ 不加 report_unit filter。"""
        pool = _make_pool()
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        ctx = _make_user_ctx()  # section=None by default
        await tool.execute({"asset_num": "EMU852", "date_range": "all"}, ctx)

        cur = pool.getconn.return_value.cursor.return_value.__enter__.return_value
        sql, _ = cur.execute.call_args[0]
        assert "report_unit" not in sql


# ---------------------------------------------------------------------------
# 7. db_pool=None raises RuntimeError
# ---------------------------------------------------------------------------

class TestNoPool:
    @pytest.mark.asyncio
    async def test_no_pool_raises_runtime_error(self):
        tool = SearchFaultsByVehicleTool()  # db_pool=None
        with pytest.raises(RuntimeError, match="db_pool not injected"):
            await tool.execute({"asset_num": "EMU852"}, _make_user_ctx())


# ---------------------------------------------------------------------------
# 8. Invalid params → TOOL_INVOCATION_ERROR
# ---------------------------------------------------------------------------

class TestInvalidParams:
    @pytest.mark.asyncio
    async def test_missing_asset_num_returns_error(self):
        pool = _make_pool()
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        result = await tool.execute({}, _make_user_ctx())

        assert result.success is False
        assert result.error_code == "TOOL_INVOCATION_ERROR"
        assert result.rows == []
        assert result.row_count == 0

    @pytest.mark.asyncio
    async def test_invalid_urgency_returns_error(self):
        """urgency='Z' 不在 Literal 範圍 → TOOL_INVOCATION_ERROR。"""
        pool = _make_pool()
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        result = await tool.execute(
            {"asset_num": "EMU852", "urgency": "Z"}, _make_user_ctx()
        )

        assert result.success is False
        assert result.error_code == "TOOL_INVOCATION_ERROR"

    @pytest.mark.asyncio
    async def test_invalid_status_group_returns_error(self):
        """status_group='merged' 不在 Literal 範圍 → TOOL_INVOCATION_ERROR。"""
        pool = _make_pool()
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        result = await tool.execute(
            {"asset_num": "EMU852", "status_group": "merged"}, _make_user_ctx()
        )

        assert result.success is False
        assert result.error_code == "TOOL_INVOCATION_ERROR"


# ---------------------------------------------------------------------------
# 9. DB exception → TOOL_EXECUTION_ERROR
# ---------------------------------------------------------------------------

class TestDbException:
    @pytest.mark.asyncio
    async def test_getconn_raises(self):
        pool = MagicMock()
        pool.getconn.side_effect = Exception("Connection pool exhausted")
        tool = SearchFaultsByVehicleTool(db_pool=pool)
        result = await tool.execute(
            {"asset_num": "EMU852", "date_range": "all"}, _make_user_ctx()
        )

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

        tool = SearchFaultsByVehicleTool(db_pool=pool)
        result = await tool.execute(
            {"asset_num": "EMU852", "date_range": "all"}, _make_user_ctx()
        )

        assert result.success is False
        assert result.error_code == "TOOL_EXECUTION_ERROR"

    @pytest.mark.asyncio
    async def test_putconn_called_even_on_exception(self):
        """finally 區塊確保 putconn 被呼叫，防止 connection leak。"""
        cursor = MagicMock()
        cursor.execute.side_effect = Exception("DB error")
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cursor

        pool = MagicMock()
        pool.getconn.return_value = conn

        tool = SearchFaultsByVehicleTool(db_pool=pool)
        await tool.execute({"asset_num": "EMU852", "date_range": "all"}, _make_user_ctx())

        pool.putconn.assert_called_once_with(conn)


# ---------------------------------------------------------------------------
# 10. _to_chinese mapping
# ---------------------------------------------------------------------------

class TestToChineseMapping:
    def test_date_isoformat(self):
        raw = {
            "ticketid": "FR-100",
            "assetnum": "EMU852",
            "status": "立案",
            "urgency": "A",
            "grade": "1",
            "tcms_code": "T001",
            "description": "desc",
            "fault_symptom": "symptom",
            "handling_desc": "handling",
            "report_date": date(2026, 4, 1),
            "occurrence_date": date(2026, 3, 31),
        }
        result = SearchFaultsByVehicleTool._to_chinese(raw)
        assert result["通報日期"] == "2026-04-01"
        assert result["發生時間"] == "2026-03-31"

    def test_none_dates_return_none(self):
        raw = {k: None for k in _COL_NAMES}
        result = SearchFaultsByVehicleTool._to_chinese(raw)
        assert result["通報日期"] is None
        assert result["發生時間"] is None

    def test_all_chinese_keys_present(self):
        raw = {k: None for k in _COL_NAMES}
        result = SearchFaultsByVehicleTool._to_chinese(raw)
        expected = {"通報號", "車號", "狀態", "故障等級", "事件等級", "TCMS碼",
                    "故障描述", "故障現象", "處理情形", "通報日期", "發生時間"}
        assert expected == set(result.keys())


# ---------------------------------------------------------------------------
# 11. _resolve_statuses
# ---------------------------------------------------------------------------

class TestResolveStatuses:
    def test_open(self):
        assert SearchFaultsByVehicleTool._resolve_statuses("open") == _STATUS_OPEN

    def test_closed(self):
        assert SearchFaultsByVehicleTool._resolve_statuses("closed") == _STATUS_CLOSED

    def test_cancelled(self):
        assert SearchFaultsByVehicleTool._resolve_statuses("cancelled") == _STATUS_CANCELLED

    def test_none_returns_none(self):
        assert SearchFaultsByVehicleTool._resolve_statuses(None) is None


# ---------------------------------------------------------------------------
# 12. REGISTER module constant
# ---------------------------------------------------------------------------

class TestRegisterConstant:
    def test_register_is_tool_instance(self):
        from app.services.maximo_tools.tools.search_faults_by_vehicle import REGISTER
        from app.services.maximo_tools.base import Tool
        assert isinstance(REGISTER, Tool)

    def test_register_has_correct_name(self):
        from app.services.maximo_tools.tools.search_faults_by_vehicle import REGISTER
        assert REGISTER.definition.name == "search_faults_by_vehicle"

    def test_register_db_pool_is_none(self):
        from app.services.maximo_tools.tools.search_faults_by_vehicle import REGISTER
        assert REGISTER._db_pool is None

    def test_register_db_pool_injectable(self):
        from app.services.maximo_tools.tools.search_faults_by_vehicle import REGISTER
        sentinel = object()
        old = REGISTER._db_pool
        try:
            REGISTER._db_pool = sentinel
            assert REGISTER._db_pool is sentinel
        finally:
            REGISTER._db_pool = old
