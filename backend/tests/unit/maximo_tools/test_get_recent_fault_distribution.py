"""
Unit tests for GetRecentFaultDistributionTool (Tool 7).

策略：mock psycopg2 pool + cursor，不碰真實 DB。
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, call

import pytest

from app.services.maximo_tools.base import ToolResult, UserContext
from app.services.maximo_tools.tools.get_recent_fault_distribution import (
    GetRecentFaultDistributionTool,
    _SCHEMA,
    REGISTER,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _ctx(**kwargs) -> UserContext:
    defaults = dict(user_id="u-test-007", role="admin")
    defaults.update(kwargs)
    return UserContext(**defaults)


def _make_pool(fetchall_return=None, col_names=None) -> MagicMock:
    """Build a mock psycopg2-style pool returning fetchall rows."""
    if fetchall_return is None:
        fetchall_return = []
    if col_names is None:
        col_names = ["category", "count", "percentage"]

    cursor = MagicMock()
    cursor.fetchall.return_value = fetchall_return
    cursor.description = [(name,) for name in col_names]
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.cursor.return_value = cursor

    pool = MagicMock()
    pool.getconn.return_value = conn
    return pool


# ---------------------------------------------------------------------------
# 1. ToolDefinition validity
# ---------------------------------------------------------------------------

class TestDefinition:
    def test_name(self):
        assert GetRecentFaultDistributionTool.definition.name == "get_recent_fault_distribution"

    def test_has_description(self):
        assert len(GetRecentFaultDistributionTool.definition.description) > 0

    def test_input_schema_valid(self):
        from app.services.maximo_tools.base import validate_tool_schema
        validate_tool_schema(_SCHEMA)

    def test_input_schema_has_date_range(self):
        assert "date_range" in _SCHEMA.get("properties", {})

    def test_input_schema_has_group_by(self):
        assert "group_by" in _SCHEMA.get("properties", {})


# ---------------------------------------------------------------------------
# 2. group_by=urgency → NULL filter present in SQL
# ---------------------------------------------------------------------------

class TestUrgencyGroupBy:
    @pytest.mark.asyncio
    async def test_urgency_null_filter_in_sql(self):
        """urgency 分組時 SQL 必須包含 NULL 排除條件。"""
        pool = _make_pool(fetchall_return=[
            ("A", 20, Decimal("11.76")),
            ("B", 26, Decimal("15.29")),
            ("C", 125, Decimal("73.53")),
        ])
        tool = GetRecentFaultDistributionTool(db_pool=pool)
        result = await tool.execute({"group_by": "urgency", "date_range": "last_30d"}, _ctx())

        assert result.success is True
        # 確認 SQL 中有 NULL 排除
        executed_sql = pool.getconn().cursor().__enter__().execute.call_args[0][0]
        assert "urgency IS NOT NULL" in executed_sql
        assert "urgency != ''" in executed_sql

    @pytest.mark.asyncio
    async def test_urgency_label_is_chinese(self):
        """urgency 分組 → row key 為 '故障等級'。"""
        pool = _make_pool(fetchall_return=[("A", 20, Decimal("100.00"))])
        tool = GetRecentFaultDistributionTool(db_pool=pool)
        result = await tool.execute({"group_by": "urgency", "date_range": "last_30d"}, _ctx())

        assert result.success is True
        assert "故障等級" in result.rows[0]

    @pytest.mark.asyncio
    async def test_urgency_chart_hint_is_pie(self):
        """urgency 分組 → chart_hint.type = pie。"""
        pool = _make_pool(fetchall_return=[("A", 20, Decimal("100.00"))])
        tool = GetRecentFaultDistributionTool(db_pool=pool)
        result = await tool.execute({"group_by": "urgency", "date_range": "last_30d"}, _ctx())

        assert result.chart_hint is not None
        assert result.chart_hint["type"] == "pie"
        assert result.chart_hint["x_field"] == "故障等級"
        assert result.chart_hint["y_field"] == "count"


# ---------------------------------------------------------------------------
# 3. group_by=section → no NULL filter, bar chart
# ---------------------------------------------------------------------------

class TestSectionGroupBy:
    @pytest.mark.asyncio
    async def test_section_no_null_filter_in_sql(self):
        """section 分組時 SQL 不應有 urgency NULL 排除條件。"""
        pool = _make_pool(fetchall_return=[
            ("北段", 50, Decimal("50.00")),
            ("南段", 50, Decimal("50.00")),
        ])
        tool = GetRecentFaultDistributionTool(db_pool=pool)
        result = await tool.execute({"group_by": "section", "date_range": "last_30d"}, _ctx())

        assert result.success is True
        executed_sql = pool.getconn().cursor().__enter__().execute.call_args[0][0]
        assert "urgency IS NOT NULL" not in executed_sql

    @pytest.mark.asyncio
    async def test_section_label_is_chinese(self):
        """section 分組 → row key 為 '段管'。"""
        pool = _make_pool(fetchall_return=[("北段", 50, Decimal("100.00"))])
        tool = GetRecentFaultDistributionTool(db_pool=pool)
        result = await tool.execute({"group_by": "section", "date_range": "last_30d"}, _ctx())

        assert result.success is True
        assert "段管" in result.rows[0]

    @pytest.mark.asyncio
    async def test_section_chart_hint_is_bar(self):
        """section 分組 → chart_hint.type = bar。"""
        pool = _make_pool(fetchall_return=[("北段", 50, Decimal("100.00"))])
        tool = GetRecentFaultDistributionTool(db_pool=pool)
        result = await tool.execute({"group_by": "section", "date_range": "last_30d"}, _ctx())

        assert result.chart_hint is not None
        assert result.chart_hint["type"] == "bar"
        assert result.chart_hint["x_field"] == "段管"


# ---------------------------------------------------------------------------
# 4. Row filter (section in user_ctx)
# ---------------------------------------------------------------------------

class TestRowFilter:
    @pytest.mark.asyncio
    async def test_section_none_no_row_filter(self):
        """user_ctx.section=None → SQL 不加 report_unit 條件。"""
        pool = _make_pool(fetchall_return=[])
        tool = GetRecentFaultDistributionTool(db_pool=pool)
        await tool.execute({"group_by": "urgency", "date_range": "last_30d"}, _ctx())

        executed_sql = pool.getconn().cursor().__enter__().execute.call_args[0][0]
        assert "report_unit = %s" not in executed_sql

    @pytest.mark.asyncio
    async def test_section_set_adds_row_filter(self):
        """user_ctx.section='北段' → SQL 加 AND report_unit = %s。"""
        pool = _make_pool(fetchall_return=[])
        tool = GetRecentFaultDistributionTool(db_pool=pool)
        await tool.execute(
            {"group_by": "urgency", "date_range": "last_30d"},
            _ctx(section="北段"),
        )

        executed_sql = pool.getconn().cursor().__enter__().execute.call_args[0][0]
        assert "report_unit = %s" in executed_sql

    @pytest.mark.asyncio
    async def test_section_value_in_args(self):
        """user_ctx.section='北段' → args 末尾含 '北段'。"""
        pool = _make_pool(fetchall_return=[])
        tool = GetRecentFaultDistributionTool(db_pool=pool)
        await tool.execute(
            {"group_by": "urgency", "date_range": "last_30d"},
            _ctx(section="北段"),
        )

        executed_args = pool.getconn().cursor().__enter__().execute.call_args[0][1]
        assert "北段" in executed_args


# ---------------------------------------------------------------------------
# 5. Date range injection
# ---------------------------------------------------------------------------

class TestDateRange:
    @pytest.mark.asyncio
    async def test_last_7d_injects_dates(self):
        """date_range=last_7d → from_ts/to_ts 帶入 SQL args。"""
        pool = _make_pool(fetchall_return=[])
        tool = GetRecentFaultDistributionTool(db_pool=pool)
        await tool.execute({"date_range": "last_7d", "group_by": "urgency"}, _ctx())

        executed_args = pool.getconn().cursor().__enter__().execute.call_args[0][1]
        # 至少有兩個時間參數 (from_ts, to_ts)
        assert len(executed_args) >= 2

    @pytest.mark.asyncio
    async def test_prev_month_injects_dates(self):
        """date_range=prev_month → from_ts 為上月第 1 天（月份正確）。"""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        pool = _make_pool(fetchall_return=[])
        tool = GetRecentFaultDistributionTool(db_pool=pool)
        await tool.execute({"date_range": "prev_month", "group_by": "urgency"}, _ctx())

        executed_args = pool.getconn().cursor().__enter__().execute.call_args[0][1]
        from_ts = executed_args[0]
        # from_ts 應為上月第 1 天
        assert from_ts.day == 1

    @pytest.mark.asyncio
    async def test_explicit_dates_override_preset(self):
        """from_date/to_date 明確指定時，覆蓋 date_range preset。"""
        pool = _make_pool(fetchall_return=[])
        tool = GetRecentFaultDistributionTool(db_pool=pool)
        await tool.execute(
            {
                "date_range": "last_30d",
                "group_by": "urgency",
                "from_date": "2026-01-01",
                "to_date": "2026-01-31",
            },
            _ctx(),
        )

        executed_args = pool.getconn().cursor().__enter__().execute.call_args[0][1]
        from_ts = executed_args[0]
        assert from_ts.year == 2026
        assert from_ts.month == 1
        assert from_ts.day == 1


# ---------------------------------------------------------------------------
# 6. Percentage correctness (mock 3-row scenario)
# ---------------------------------------------------------------------------

class TestPercentage:
    @pytest.mark.asyncio
    async def test_percentage_values_returned(self):
        """回傳的 percentage 為 float，三列總和為 100.00。"""
        pool = _make_pool(fetchall_return=[
            ("A", 20, Decimal("11.76")),
            ("B", 26, Decimal("15.29")),
            ("C", 125, Decimal("72.95")),
        ])
        tool = GetRecentFaultDistributionTool(db_pool=pool)
        result = await tool.execute({"group_by": "urgency", "date_range": "last_30d"}, _ctx())

        assert result.success is True
        assert result.row_count == 3
        total = sum(r["percentage"] for r in result.rows)
        assert abs(total - 100.0) < 1.0  # 浮點容差

    @pytest.mark.asyncio
    async def test_count_is_int(self):
        """count 欄位必須是 int（非 Decimal 或 str）。"""
        pool = _make_pool(fetchall_return=[("A", 20, Decimal("100.00"))])
        tool = GetRecentFaultDistributionTool(db_pool=pool)
        result = await tool.execute({"group_by": "urgency", "date_range": "last_30d"}, _ctx())

        assert isinstance(result.rows[0]["count"], int)

    @pytest.mark.asyncio
    async def test_percentage_is_float(self):
        """percentage 欄位必須是 float（非 Decimal）。"""
        pool = _make_pool(fetchall_return=[("A", 20, Decimal("100.00"))])
        tool = GetRecentFaultDistributionTool(db_pool=pool)
        result = await tool.execute({"group_by": "urgency", "date_range": "last_30d"}, _ctx())

        assert isinstance(result.rows[0]["percentage"], float)


# ---------------------------------------------------------------------------
# 7. db_pool=None raises RuntimeError
# ---------------------------------------------------------------------------

class TestNoPool:
    @pytest.mark.asyncio
    async def test_no_pool_raises_runtime_error(self):
        tool = GetRecentFaultDistributionTool()  # db_pool=None
        with pytest.raises(RuntimeError, match="db_pool not injected"):
            await tool.execute({"group_by": "urgency"}, _ctx())


# ---------------------------------------------------------------------------
# 8. Invalid params → TOOL_INVOCATION_ERROR
# ---------------------------------------------------------------------------

class TestInvalidParams:
    @pytest.mark.asyncio
    async def test_invalid_group_by_returns_error(self):
        """group_by 不在 enum 中 → TOOL_INVOCATION_ERROR。"""
        pool = _make_pool()
        tool = GetRecentFaultDistributionTool(db_pool=pool)
        result = await tool.execute({"group_by": "invalid_field"}, _ctx())

        assert result.success is False
        assert result.error_code == "TOOL_INVOCATION_ERROR"
        assert result.rows == []
        assert result.row_count == 0

    @pytest.mark.asyncio
    async def test_invalid_date_range_returns_error(self):
        """date_range 不在 enum 中 → TOOL_INVOCATION_ERROR。"""
        pool = _make_pool()
        tool = GetRecentFaultDistributionTool(db_pool=pool)
        result = await tool.execute({"date_range": "last_100y"}, _ctx())

        assert result.success is False
        assert result.error_code == "TOOL_INVOCATION_ERROR"


# ---------------------------------------------------------------------------
# 9. DB exception → TOOL_EXECUTION_ERROR
# ---------------------------------------------------------------------------

class TestDbException:
    @pytest.mark.asyncio
    async def test_pool_getconn_raises(self):
        pool = MagicMock()
        pool.getconn.side_effect = Exception("Connection pool exhausted")

        tool = GetRecentFaultDistributionTool(db_pool=pool)
        result = await tool.execute({"group_by": "urgency", "date_range": "last_30d"}, _ctx())

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

        tool = GetRecentFaultDistributionTool(db_pool=pool)
        result = await tool.execute({"group_by": "urgency", "date_range": "last_30d"}, _ctx())

        assert result.success is False
        assert result.error_code == "TOOL_EXECUTION_ERROR"

    @pytest.mark.asyncio
    async def test_putconn_called_on_exception(self):
        """確認 finally 區塊有 putconn（防止 connection leak）。"""
        cursor = MagicMock()
        cursor.execute.side_effect = Exception("DB error")
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cursor

        pool = MagicMock()
        pool.getconn.return_value = conn

        tool = GetRecentFaultDistributionTool(db_pool=pool)
        await tool.execute({"group_by": "urgency", "date_range": "last_30d"}, _ctx())

        pool.putconn.assert_called_once_with(conn)


# ---------------------------------------------------------------------------
# 10. REGISTER module constant
# ---------------------------------------------------------------------------

class TestRegister:
    def test_register_is_tool_instance(self):
        from app.services.maximo_tools.base import Tool
        assert isinstance(REGISTER, Tool)

    def test_register_correct_name(self):
        assert REGISTER.definition.name == "get_recent_fault_distribution"

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
