"""
Unit tests for CountOpenWorkordersByCategoryTool (Tool 5).

策略：mock psycopg2 pool + cursor，不碰真實 DB。
SQL 驗證：擷取 cur.execute 的第一個引數字串做子字串斷言。
"""
from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from app.services.maximo_tools.base import ToolResult, UserContext
from app.services.maximo_tools.tools.count_open_workorders_by_category import (
    CountOpenWorkordersByCategoryTool,
    _CLOSED_STATUSES,
    _SCHEMA,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_user_ctx(**kwargs) -> UserContext:
    defaults = dict(user_id="u-test-001", role="admin")
    defaults.update(kwargs)
    return UserContext(**defaults)


def _make_pool(fetchall_return=None) -> MagicMock:
    """
    Build a mock psycopg2-style pool.

    fetchall_return: list of tuples, each tuple = (category, count, percentage).
    col_names for description: ["category", "count", "percentage"].
    """
    if fetchall_return is None:
        fetchall_return = []

    cursor = MagicMock()
    cursor.fetchall.return_value = fetchall_return
    cursor.description = [("category",), ("count",), ("percentage",)]
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.cursor.return_value = cursor

    pool = MagicMock()
    pool.getconn.return_value = conn
    return pool


def _get_executed_sql(pool: MagicMock) -> str:
    """Extract the SQL string passed to cursor.execute()."""
    conn = pool.getconn.return_value
    cursor = conn.cursor.return_value
    # cursor.execute is called once; get first positional arg
    return cursor.execute.call_args[0][0]


def _get_executed_args(pool: MagicMock) -> tuple:
    """Extract the args tuple passed to cursor.execute()."""
    conn = pool.getconn.return_value
    cursor = conn.cursor.return_value
    return cursor.execute.call_args[0][1]


# ---------------------------------------------------------------------------
# 1. ToolDefinition
# ---------------------------------------------------------------------------

class TestDefinition:
    def test_definition_name(self):
        assert CountOpenWorkordersByCategoryTool.definition.name == "count_open_workorders_by_category"

    def test_definition_has_description(self):
        assert len(CountOpenWorkordersByCategoryTool.definition.description) > 0

    def test_input_schema_valid(self):
        from app.services.maximo_tools.base import validate_tool_schema
        validate_tool_schema(_SCHEMA)

    def test_input_schema_has_group_by(self):
        assert "group_by" in _SCHEMA.get("properties", {})

    def test_input_schema_enum_values(self):
        enum_vals = _SCHEMA["properties"]["group_by"]["enum"]
        assert set(enum_vals) == {"大分類", "車種", "車型"}


# ---------------------------------------------------------------------------
# 2. SQL shape — 大分類
# ---------------------------------------------------------------------------

class TestSqlShapeDaFenLei:
    @pytest.mark.asyncio
    async def test_group_by_da_fen_lei_uses_case_when_rstf_rstp(self):
        pool = _make_pool()
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        await tool.execute({"group_by": "大分類"}, _make_user_ctx())

        sql = _get_executed_sql(pool)
        assert "RSTF" in sql
        assert "RSTP" in sql
        assert "貨車" in sql

    @pytest.mark.asyncio
    async def test_group_by_da_fen_lei_case_when_rstl_dynamic_che(self):
        pool = _make_pool()
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        await tool.execute({"group_by": "大分類"}, _make_user_ctx())

        sql = _get_executed_sql(pool)
        assert "RSTL" in sql
        assert "動力車" in sql
        assert "RSTA" in sql
        assert "客車" in sql

    @pytest.mark.asyncio
    async def test_group_by_da_fen_lei_eq11_not_null_filter(self):
        pool = _make_pool()
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        await tool.execute({"group_by": "大分類"}, _make_user_ctx())

        sql = _get_executed_sql(pool)
        assert "eq11 IS NOT NULL" in sql
        assert "eq11 != ''" in sql

    @pytest.mark.asyncio
    async def test_group_by_da_fen_lei_union_all_both_tables(self):
        pool = _make_pool()
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        await tool.execute({"group_by": "大分類"}, _make_user_ctx())

        sql = _get_executed_sql(pool)
        assert "maximo_pm_workorders" in sql
        assert "maximo_cm_workorders" in sql
        assert "UNION ALL" in sql

    @pytest.mark.asyncio
    async def test_group_by_da_fen_lei_closed_statuses_in_sql(self):
        pool = _make_pool()
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        await tool.execute({"group_by": "大分類"}, _make_user_ctx())

        sql = _get_executed_sql(pool)
        assert "NOT IN" in sql
        # 3 placeholders per table × 2 tables = 6 total
        assert sql.count("%s") >= 6

    @pytest.mark.asyncio
    async def test_group_by_da_fen_lei_percentage_over(self):
        pool = _make_pool()
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        await tool.execute({"group_by": "大分類"}, _make_user_ctx())

        sql = _get_executed_sql(pool)
        assert "OVER ()" in sql or "OVER()" in sql

    @pytest.mark.asyncio
    async def test_group_by_da_fen_lei_no_section_filter_when_none(self):
        pool = _make_pool()
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        await tool.execute({"group_by": "大分類"}, _make_user_ctx(section=None))

        sql = _get_executed_sql(pool)
        assert "maintenance_section" not in sql

    @pytest.mark.asyncio
    async def test_group_by_da_fen_lei_section_filter_in_both_cte_branches(self):
        pool = _make_pool()
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        await tool.execute({"group_by": "大分類"}, _make_user_ctx(section="台北機廠"))

        sql = _get_executed_sql(pool)
        # maintenance_section appears twice (once per UNION ALL branch)
        assert sql.count("maintenance_section") == 2


# ---------------------------------------------------------------------------
# 3. SQL shape — 車種
# ---------------------------------------------------------------------------

class TestSqlShapeCarType:
    @pytest.mark.asyncio
    async def test_group_by_che_zhong_uses_eq3(self):
        pool = _make_pool()
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        await tool.execute({"group_by": "車種"}, _make_user_ctx())

        sql = _get_executed_sql(pool)
        assert "a.eq3" in sql

    @pytest.mark.asyncio
    async def test_group_by_che_zhong_eq3_not_null_filter(self):
        pool = _make_pool()
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        await tool.execute({"group_by": "車種"}, _make_user_ctx())

        sql = _get_executed_sql(pool)
        assert "eq3 IS NOT NULL" in sql
        assert "eq3 != ''" in sql

    @pytest.mark.asyncio
    async def test_group_by_che_zhong_no_case_when_for_eq11(self):
        pool = _make_pool()
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        await tool.execute({"group_by": "車種"}, _make_user_ctx())

        sql = _get_executed_sql(pool)
        # RSTF/RSTP case logic should NOT appear for 車種
        assert "RSTF" not in sql
        assert "RSTP" not in sql


# ---------------------------------------------------------------------------
# 4. SQL shape — 車型
# ---------------------------------------------------------------------------

class TestSqlShapeCarModel:
    @pytest.mark.asyncio
    async def test_group_by_che_xing_uses_eq4(self):
        pool = _make_pool()
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        await tool.execute({"group_by": "車型"}, _make_user_ctx())

        sql = _get_executed_sql(pool)
        assert "a.eq4" in sql

    @pytest.mark.asyncio
    async def test_group_by_che_xing_eq4_not_null_filter(self):
        pool = _make_pool()
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        await tool.execute({"group_by": "車型"}, _make_user_ctx())

        sql = _get_executed_sql(pool)
        assert "eq4 IS NOT NULL" in sql
        assert "eq4 != ''" in sql


# ---------------------------------------------------------------------------
# 5. Args ordering with / without section
# ---------------------------------------------------------------------------

class TestArgsOrdering:
    @pytest.mark.asyncio
    async def test_no_section_args_are_closed_statuses_x2(self):
        pool = _make_pool()
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        await tool.execute({"group_by": "大分類"}, _make_user_ctx(section=None))

        args = _get_executed_args(pool)
        assert args == tuple(_CLOSED_STATUSES) + tuple(_CLOSED_STATUSES)

    @pytest.mark.asyncio
    async def test_with_section_args_include_section_twice(self):
        pool = _make_pool()
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        await tool.execute({"group_by": "大分類"}, _make_user_ctx(section="台北機廠"))

        args = _get_executed_args(pool)
        expected = (
            tuple(_CLOSED_STATUSES)
            + ("台北機廠",)
            + tuple(_CLOSED_STATUSES)
            + ("台北機廠",)
        )
        assert args == expected


# ---------------------------------------------------------------------------
# 6. chart_hint
# ---------------------------------------------------------------------------

class TestChartHint:
    @pytest.mark.asyncio
    async def test_da_fen_lei_chart_hint_is_pie(self):
        pool = _make_pool()
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        result = await tool.execute({"group_by": "大分類"}, _make_user_ctx())

        assert result.chart_hint is not None
        assert result.chart_hint["type"] == "pie"
        assert result.chart_hint["x_field"] == "category"
        assert result.chart_hint["y_field"] == "count"
        assert result.chart_hint["percentage_field"] == "percentage"

    @pytest.mark.asyncio
    async def test_che_zhong_chart_hint_is_bar(self):
        pool = _make_pool()
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        result = await tool.execute({"group_by": "車種"}, _make_user_ctx())

        assert result.chart_hint is not None
        assert result.chart_hint["type"] == "bar"

    @pytest.mark.asyncio
    async def test_che_xing_chart_hint_is_bar(self):
        pool = _make_pool()
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        result = await tool.execute({"group_by": "車型"}, _make_user_ctx())

        assert result.chart_hint is not None
        assert result.chart_hint["type"] == "bar"


# ---------------------------------------------------------------------------
# 7. Output row mapping
# ---------------------------------------------------------------------------

class TestOutputRowMapping:
    @pytest.mark.asyncio
    async def test_three_rows_maps_correctly(self):
        """Mock returns 3 rows: 動力車/客車/貨車 with percentages summing to 100."""
        fetchall = [
            ("動力車", 500, 50.00),
            ("客車",   300, 30.00),
            ("貨車",   200, 20.00),
        ]
        pool = _make_pool(fetchall_return=fetchall)
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        result = await tool.execute({"group_by": "大分類"}, _make_user_ctx())

        assert result.success is True
        assert result.row_count == 3
        assert len(result.rows) == 3

        assert result.rows[0] == {"分類": "動力車", "工單數": 500, "百分比": 50.00}
        assert result.rows[1] == {"分類": "客車",   "工單數": 300, "百分比": 30.00}
        assert result.rows[2] == {"分類": "貨車",   "工單數": 200, "百分比": 20.00}

    @pytest.mark.asyncio
    async def test_percentage_sum_equals_100(self):
        fetchall = [
            ("動力車", 500, 50.00),
            ("客車",   300, 30.00),
            ("貨車",   200, 20.00),
        ]
        pool = _make_pool(fetchall_return=fetchall)
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        result = await tool.execute({"group_by": "大分類"}, _make_user_ctx())

        total_pct = sum(r["百分比"] for r in result.rows)
        assert abs(total_pct - 100.0) < 0.02

    @pytest.mark.asyncio
    async def test_output_keys_are_chinese(self):
        fetchall = [("EMU", 100, 100.00)]
        pool = _make_pool(fetchall_return=fetchall)
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        result = await tool.execute({"group_by": "車種"}, _make_user_ctx())

        r = result.rows[0]
        assert "分類" in r
        assert "工單數" in r
        assert "百分比" in r
        # No raw column names exposed
        assert "category" not in r
        assert "count" not in r
        assert "percentage" not in r

    @pytest.mark.asyncio
    async def test_count_is_int_percentage_is_float(self):
        fetchall = [("動力車", 42, 100.00)]
        pool = _make_pool(fetchall_return=fetchall)
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        result = await tool.execute({"group_by": "大分類"}, _make_user_ctx())

        r = result.rows[0]
        assert isinstance(r["工單數"], int)
        assert isinstance(r["百分比"], float)

    @pytest.mark.asyncio
    async def test_empty_result_returns_success_with_zero_rows(self):
        pool = _make_pool(fetchall_return=[])
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        result = await tool.execute({"group_by": "大分類"}, _make_user_ctx())

        assert result.success is True
        assert result.rows == []
        assert result.row_count == 0


# ---------------------------------------------------------------------------
# 8. db_pool=None raises RuntimeError
# ---------------------------------------------------------------------------

class TestNoPool:
    @pytest.mark.asyncio
    async def test_no_pool_raises_runtime_error(self):
        tool = CountOpenWorkordersByCategoryTool()  # db_pool=None
        with pytest.raises(RuntimeError, match="db_pool not injected"):
            await tool.execute({"group_by": "大分類"}, _make_user_ctx())


# ---------------------------------------------------------------------------
# 9. Invalid params
# ---------------------------------------------------------------------------

class TestInvalidParams:
    @pytest.mark.asyncio
    async def test_invalid_group_by_value_returns_error(self):
        pool = _make_pool()
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        result = await tool.execute({"group_by": "不存在的維度"}, _make_user_ctx())

        assert result.success is False
        assert result.error_code == "TOOL_INVOCATION_ERROR"
        assert result.rows == []
        assert result.row_count == 0

    @pytest.mark.asyncio
    async def test_default_group_by_is_da_fen_lei(self):
        """group_by 省略時預設 大分類。"""
        pool = _make_pool()
        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        result = await tool.execute({}, _make_user_ctx())

        # default 大分類 → SQL should contain RSTF
        sql = _get_executed_sql(pool)
        assert "RSTF" in sql
        assert result.success is True


# ---------------------------------------------------------------------------
# 10. DB exception handling
# ---------------------------------------------------------------------------

class TestDbException:
    @pytest.mark.asyncio
    async def test_pool_getconn_raises_returns_execution_error(self):
        pool = MagicMock()
        pool.getconn.side_effect = Exception("Connection pool exhausted")

        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        result = await tool.execute({"group_by": "大分類"}, _make_user_ctx())

        assert result.success is False
        assert result.error_code == "TOOL_EXECUTION_ERROR"
        assert result.rows == []
        assert result.row_count == 0

    @pytest.mark.asyncio
    async def test_cursor_execute_raises_returns_execution_error(self):
        cursor = MagicMock()
        cursor.execute.side_effect = Exception("DB timeout")
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cursor

        pool = MagicMock()
        pool.getconn.return_value = conn

        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        result = await tool.execute({"group_by": "大分類"}, _make_user_ctx())

        assert result.success is False
        assert result.error_code == "TOOL_EXECUTION_ERROR"

    @pytest.mark.asyncio
    async def test_putconn_called_even_on_exception(self):
        """確認 finally 區塊有 putconn（防止 connection leak）。"""
        cursor = MagicMock()
        cursor.execute.side_effect = Exception("DB error")
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cursor

        pool = MagicMock()
        pool.getconn.return_value = conn

        tool = CountOpenWorkordersByCategoryTool(db_pool=pool)
        await tool.execute({"group_by": "大分類"}, _make_user_ctx())

        pool.putconn.assert_called_once_with(conn)


# ---------------------------------------------------------------------------
# 11. REGISTER module constant
# ---------------------------------------------------------------------------

class TestRegisterConstant:
    def test_register_is_tool_instance(self):
        from app.services.maximo_tools.tools.count_open_workorders_by_category import REGISTER
        from app.services.maximo_tools.base import Tool
        assert isinstance(REGISTER, Tool)

    def test_register_name(self):
        from app.services.maximo_tools.tools.count_open_workorders_by_category import REGISTER
        assert REGISTER.definition.name == "count_open_workorders_by_category"

    def test_register_db_pool_is_none(self):
        from app.services.maximo_tools.tools.count_open_workorders_by_category import REGISTER
        assert REGISTER._db_pool is None

    def test_register_db_pool_injectable(self):
        from app.services.maximo_tools.tools.count_open_workorders_by_category import REGISTER
        sentinel = object()
        old = REGISTER._db_pool
        try:
            REGISTER._db_pool = sentinel
            assert REGISTER._db_pool is sentinel
        finally:
            REGISTER._db_pool = old
