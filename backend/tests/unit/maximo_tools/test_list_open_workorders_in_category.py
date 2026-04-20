"""
Unit tests for ListOpenWorkordersInCategoryTool (Tool 6).

策略：mock psycopg2 pool + cursor，不碰真實 DB。
驗證重點：SQL fragment 正確性（field_filter、IN 展開、section 注入、UNION ALL）、
         arg 順序、edge cases（db_pool=None、參數驗證失敗、DB 異常）。
"""
from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from app.services.maximo_tools.base import ToolResult, UserContext
from app.services.maximo_tools.tools.list_open_workorders_in_category import (
    ListOpenWorkordersInCategoryTool,
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


def _make_pool(rows: list[tuple] | None = None) -> MagicMock:
    """
    Build a mock psycopg2-style pool.
    rows: list of tuples matching SELECT column order:
        (wonum, assetnum, status, wo_type, work_type,
         description, report_date, act_finish, eq3, eq4, eq11)
    """
    col_names = [
        "wonum", "assetnum", "status", "wo_type", "work_type",
        "description", "report_date", "act_finish", "eq3", "eq4", "eq11",
    ]
    cursor = MagicMock()
    cursor.description = [(name,) for name in col_names]
    cursor.fetchall.return_value = rows if rows is not None else []
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.cursor.return_value = cursor

    pool = MagicMock()
    pool.getconn.return_value = conn
    return pool


def _extract_sql_and_args(pool: MagicMock) -> tuple[str, tuple]:
    """從 mock pool 中取出 cur.execute 的呼叫參數。"""
    conn = pool.getconn.return_value
    cursor = conn.cursor.return_value
    # execute 被 context manager __enter__ 回傳的 cursor 呼叫
    args = cursor.execute.call_args
    assert args is not None, "cursor.execute was never called"
    sql: str = args[0][0]
    params: tuple = args[0][1]
    return sql, params


# ---------------------------------------------------------------------------
# 1. ToolDefinition validity
# ---------------------------------------------------------------------------

class TestDefinition:
    def test_definition_name(self):
        assert ListOpenWorkordersInCategoryTool.definition.name == "list_open_workorders_in_category"

    def test_definition_has_description(self):
        assert len(ListOpenWorkordersInCategoryTool.definition.description) > 0

    def test_input_schema_valid(self):
        from app.services.maximo_tools.base import validate_tool_schema
        validate_tool_schema(_SCHEMA)

    def test_input_schema_required_fields(self):
        assert "level" in _SCHEMA.get("required", [])
        assert "value" in _SCHEMA.get("required", [])

    def test_input_schema_no_forbidden_keys(self):
        """確認無 $defs/$ref/anyOf 等 forbidden key（flat schema 要求）。"""
        import json
        schema_str = json.dumps(_SCHEMA)
        for forbidden in ("$defs", "$ref", "anyOf", "oneOf", "allOf"):
            assert f'"{forbidden}"' not in schema_str


# ---------------------------------------------------------------------------
# 2. level=大分類 + 單碼（客車）
# ---------------------------------------------------------------------------

class TestLevelDaFenLeiSingleCode:
    @pytest.mark.asyncio
    async def test_ke_che_uses_eq_single(self):
        """客車 → to_codes() = ['RSTA'] → `a.eq11 = %s` 而非 IN"""
        pool = _make_pool()
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        result = await tool.execute({"level": "大分類", "value": "客車"}, _make_user_ctx())

        sql, params = _extract_sql_and_args(pool)
        assert "a.eq11 = %s" in sql
        # eq11 應該用單值比對（= %s），不應出現 `a.eq11 IN`
        # （SQL 有 `status NOT IN` 供 closed filter 使用，那是 OK 的）
        assert "a.eq11 IN (" not in sql
        # field arg 是最後一個：closed×3 + closed×3 + 'RSTA'
        assert params[-1] == "RSTA"
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dong_li_che_uses_eq_single(self):
        """動力車 → to_codes() = ['RSTL'] → `a.eq11 = %s`"""
        pool = _make_pool()
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        await tool.execute({"level": "大分類", "value": "動力車"}, _make_user_ctx())

        sql, params = _extract_sql_and_args(pool)
        assert "a.eq11 = %s" in sql
        assert params[-1] == "RSTL"

    @pytest.mark.asyncio
    async def test_unknown_category_falls_back_to_value(self):
        """未知分類 → to_codes() = ['未知'] → field_arg = '未知'（fallback）"""
        pool = _make_pool()
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        await tool.execute({"level": "大分類", "value": "未知"}, _make_user_ctx())

        sql, params = _extract_sql_and_args(pool)
        assert "a.eq11 = %s" in sql
        assert params[-1] == "未知"


# ---------------------------------------------------------------------------
# 3. level=大分類 + 雙碼（貨車）
# ---------------------------------------------------------------------------

class TestLevelDaFenLeiDoubleCode:
    @pytest.mark.asyncio
    async def test_huo_che_uses_in_clause(self):
        """貨車 → to_codes() = ['RSTF', 'RSTP'] → `a.eq11 IN (%s, %s)`"""
        pool = _make_pool()
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        result = await tool.execute({"level": "大分類", "value": "貨車"}, _make_user_ctx())

        sql, params = _extract_sql_and_args(pool)
        assert "a.eq11 IN (%s, %s)" in sql
        assert "a.eq11 = %s" not in sql.replace("IN (%s, %s)", "")  # no single-eq for eq11
        # last two args are the field_args
        assert params[-2] == "RSTF"
        assert params[-1] == "RSTP"
        assert result.success is True

    @pytest.mark.asyncio
    async def test_huo_che_arg_count(self):
        """無 section 時 args = closed×3 + closed×3 + field×2 = 8 個"""
        pool = _make_pool()
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        await tool.execute({"level": "大分類", "value": "貨車"}, _make_user_ctx())

        _, params = _extract_sql_and_args(pool)
        expected_len = len(_CLOSED_STATUSES) * 2 + 2  # 3+3+2 = 8
        assert len(params) == expected_len


# ---------------------------------------------------------------------------
# 4. level=車種
# ---------------------------------------------------------------------------

class TestLevelCheZhong:
    @pytest.mark.asyncio
    async def test_ppt_uses_eq3(self):
        """level=車種 + value=PPT → `a.eq3 = %s` + arg 'PPT'"""
        pool = _make_pool()
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        await tool.execute({"level": "車種", "value": "PPT"}, _make_user_ctx())

        sql, params = _extract_sql_and_args(pool)
        assert "a.eq3 = %s" in sql
        assert params[-1] == "PPT"

    @pytest.mark.asyncio
    async def test_emu_uses_eq3(self):
        """level=車種 + value=EMU → `a.eq3 = %s`"""
        pool = _make_pool()
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        await tool.execute({"level": "車種", "value": "EMU"}, _make_user_ctx())

        sql, params = _extract_sql_and_args(pool)
        assert "a.eq3 = %s" in sql
        assert params[-1] == "EMU"


# ---------------------------------------------------------------------------
# 5. level=車型
# ---------------------------------------------------------------------------

class TestLevelCheXing:
    @pytest.mark.asyncio
    async def test_35ppt1000_uses_eq4(self):
        """level=車型 + value=35PPT1000 → `a.eq4 = %s`"""
        pool = _make_pool()
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        await tool.execute({"level": "車型", "value": "35PPT1000"}, _make_user_ctx())

        sql, params = _extract_sql_and_args(pool)
        assert "a.eq4 = %s" in sql
        assert params[-1] == "35PPT1000"

    @pytest.mark.asyncio
    async def test_emu800_uses_eq4(self):
        pool = _make_pool()
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        await tool.execute({"level": "車型", "value": "EMU800"}, _make_user_ctx())

        sql, params = _extract_sql_and_args(pool)
        assert "a.eq4 = %s" in sql
        assert params[-1] == "EMU800"


# ---------------------------------------------------------------------------
# 6. SQL 結構驗證（UNION ALL + JOIN + ORDER）
# ---------------------------------------------------------------------------

class TestSqlStructure:
    @pytest.mark.asyncio
    async def test_contains_union_all(self):
        """SQL 必須含 UNION ALL 合併 PM + CM"""
        pool = _make_pool()
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        await tool.execute({"level": "車種", "value": "EMU"}, _make_user_ctx())

        sql, _ = _extract_sql_and_args(pool)
        assert "UNION ALL" in sql

    @pytest.mark.asyncio
    async def test_queries_both_pm_and_cm_tables(self):
        pool = _make_pool()
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        await tool.execute({"level": "車種", "value": "EMU"}, _make_user_ctx())

        sql, _ = _extract_sql_and_args(pool)
        assert "maximo_pm_workorders" in sql
        assert "maximo_cm_workorders" in sql

    @pytest.mark.asyncio
    async def test_joins_mxasset(self):
        pool = _make_pool()
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        await tool.execute({"level": "車種", "value": "EMU"}, _make_user_ctx())

        sql, _ = _extract_sql_and_args(pool)
        assert "maximo_mxasset" in sql
        assert "JOIN" in sql.upper()

    @pytest.mark.asyncio
    async def test_has_limit_200(self):
        pool = _make_pool()
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        await tool.execute({"level": "車種", "value": "EMU"}, _make_user_ctx())

        sql, _ = _extract_sql_and_args(pool)
        assert "LIMIT 200" in sql

    @pytest.mark.asyncio
    async def test_has_order_by_report_date(self):
        pool = _make_pool()
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        await tool.execute({"level": "車種", "value": "EMU"}, _make_user_ctx())

        sql, _ = _extract_sql_and_args(pool)
        assert "report_date" in sql
        assert "ORDER BY" in sql.upper()


# ---------------------------------------------------------------------------
# 7. section（maintenance_section）注入
# ---------------------------------------------------------------------------

class TestSectionFilter:
    @pytest.mark.asyncio
    async def test_section_injected_twice_in_union(self):
        """section 非 None → SQL 含 2 處 maintenance_section（PM + CM 各一）"""
        pool = _make_pool()
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        ctx = _make_user_ctx(section="北段")
        await tool.execute({"level": "車種", "value": "EMU"}, ctx)

        sql, params = _extract_sql_and_args(pool)
        assert sql.count("maintenance_section = %s") == 2
        # params = closed×3 + '北段' + closed×3 + '北段' + field_arg
        section_positions = [i for i, p in enumerate(params) if p == "北段"]
        assert len(section_positions) == 2

    @pytest.mark.asyncio
    async def test_no_section_no_maintenance_clause(self):
        """section=None → SQL 不含 maintenance_section"""
        pool = _make_pool()
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        ctx = _make_user_ctx()  # section=None
        await tool.execute({"level": "車種", "value": "EMU"}, ctx)

        sql, params = _extract_sql_and_args(pool)
        assert "maintenance_section" not in sql
        # params = closed×3 + closed×3 + field_arg = 7 個
        assert len(params) == len(_CLOSED_STATUSES) * 2 + 1

    @pytest.mark.asyncio
    async def test_section_arg_count_with_single_field(self):
        """section + 單碼 → args = closed×3 + section + closed×3 + section + field×1 = 9 個"""
        pool = _make_pool()
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        ctx = _make_user_ctx(section="南段")
        await tool.execute({"level": "大分類", "value": "客車"}, ctx)

        _, params = _extract_sql_and_args(pool)
        expected = len(_CLOSED_STATUSES) * 2 + 2 + 1  # 3+3+2+1 = 9
        assert len(params) == expected


# ---------------------------------------------------------------------------
# 8. 回傳資料中文欄位映射
# ---------------------------------------------------------------------------

class TestChineseMapping:
    @pytest.mark.asyncio
    async def test_chinese_keys_present(self):
        import datetime
        rows = [
            ("WO001", "EMU852", "執行中已派工", "定檢", "1A",
             "定期檢查", datetime.date(2026, 4, 1), None, "EMU", "EMU800", "RSTL"),
        ]
        pool = _make_pool(rows=rows)
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        result = await tool.execute({"level": "車種", "value": "EMU"}, _make_user_ctx())

        assert result.success is True
        assert result.row_count == 1
        r = result.rows[0]
        expected_keys = {"工單號", "車號", "狀態", "工單類型", "工作類型", "車種", "車型",
                         "大分類代碼", "描述", "通報日期", "實際完工"}
        assert expected_keys == set(r.keys())

    @pytest.mark.asyncio
    async def test_date_serialized_to_iso(self):
        import datetime
        rows = [
            ("WO002", "PPT001", "執行中已派工", "臨修", "CM",
             None, datetime.date(2026, 3, 15), datetime.date(2026, 3, 20),
             "PPT", "35PPT1000", "RSTA"),
        ]
        pool = _make_pool(rows=rows)
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        result = await tool.execute({"level": "車種", "value": "PPT"}, _make_user_ctx())

        r = result.rows[0]
        assert r["通報日期"] == "2026-03-15"
        assert r["實際完工"] == "2026-03-20"

    @pytest.mark.asyncio
    async def test_null_dates_become_none(self):
        rows = [
            ("WO003", "A001", "執行中已派工", "定檢", "2A",
             None, None, None, None, None, "RSTF"),
        ]
        pool = _make_pool(rows=rows)
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        result = await tool.execute({"level": "大分類", "value": "貨車"}, _make_user_ctx())

        r = result.rows[0]
        assert r["通報日期"] is None
        assert r["實際完工"] is None

    @pytest.mark.asyncio
    async def test_empty_result_success(self):
        pool = _make_pool(rows=[])
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        result = await tool.execute({"level": "車型", "value": "NONEXISTENT"}, _make_user_ctx())

        assert result.success is True
        assert result.rows == []
        assert result.row_count == 0


# ---------------------------------------------------------------------------
# 9. db_pool=None → RuntimeError
# ---------------------------------------------------------------------------

class TestNoPool:
    @pytest.mark.asyncio
    async def test_no_pool_raises_runtime_error(self):
        tool = ListOpenWorkordersInCategoryTool()  # db_pool=None
        with pytest.raises(RuntimeError, match="db_pool not injected"):
            await tool.execute({"level": "車種", "value": "EMU"}, _make_user_ctx())


# ---------------------------------------------------------------------------
# 10. 參數驗證失敗 → TOOL_INVOCATION_ERROR
# ---------------------------------------------------------------------------

class TestInvalidParams:
    @pytest.mark.asyncio
    async def test_missing_level_returns_invocation_error(self):
        pool = _make_pool()
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        result = await tool.execute({"value": "客車"}, _make_user_ctx())

        assert result.success is False
        assert result.error_code == "TOOL_INVOCATION_ERROR"
        assert result.rows == []
        assert result.row_count == 0

    @pytest.mark.asyncio
    async def test_missing_value_returns_invocation_error(self):
        pool = _make_pool()
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        result = await tool.execute({"level": "大分類"}, _make_user_ctx())

        assert result.success is False
        assert result.error_code == "TOOL_INVOCATION_ERROR"

    @pytest.mark.asyncio
    async def test_invalid_level_value_returns_invocation_error(self):
        pool = _make_pool()
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        result = await tool.execute({"level": "無效層", "value": "客車"}, _make_user_ctx())

        assert result.success is False
        assert result.error_code == "TOOL_INVOCATION_ERROR"

    @pytest.mark.asyncio
    async def test_empty_params_returns_invocation_error(self):
        pool = _make_pool()
        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        result = await tool.execute({}, _make_user_ctx())

        assert result.success is False
        assert result.error_code == "TOOL_INVOCATION_ERROR"


# ---------------------------------------------------------------------------
# 11. DB 異常 → TOOL_EXECUTION_ERROR
# ---------------------------------------------------------------------------

class TestDbException:
    @pytest.mark.asyncio
    async def test_pool_getconn_raises(self):
        pool = MagicMock()
        pool.getconn.side_effect = Exception("Connection pool exhausted")

        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        result = await tool.execute({"level": "車種", "value": "EMU"}, _make_user_ctx())

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

        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        result = await tool.execute({"level": "大分類", "value": "客車"}, _make_user_ctx())

        assert result.success is False
        assert result.error_code == "TOOL_EXECUTION_ERROR"

    @pytest.mark.asyncio
    async def test_putconn_called_even_on_db_exception(self):
        """確認 finally 區塊有 putconn（防止 connection leak）。"""
        cursor = MagicMock()
        cursor.execute.side_effect = Exception("DB error")
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cursor

        pool = MagicMock()
        pool.getconn.return_value = conn

        tool = ListOpenWorkordersInCategoryTool(db_pool=pool)
        await tool.execute({"level": "大分類", "value": "貨車"}, _make_user_ctx())

        pool.putconn.assert_called_once_with(conn)


# ---------------------------------------------------------------------------
# 12. REGISTER module constant
# ---------------------------------------------------------------------------

class TestRegisterConstant:
    def test_register_is_tool_instance(self):
        from app.services.maximo_tools.tools.list_open_workorders_in_category import REGISTER
        from app.services.maximo_tools.base import Tool
        assert isinstance(REGISTER, Tool)

    def test_register_has_correct_name(self):
        from app.services.maximo_tools.tools.list_open_workorders_in_category import REGISTER
        assert REGISTER.definition.name == "list_open_workorders_in_category"

    def test_register_db_pool_is_none(self):
        from app.services.maximo_tools.tools.list_open_workorders_in_category import REGISTER
        assert REGISTER._db_pool is None

    def test_register_db_pool_injectable(self):
        from app.services.maximo_tools.tools.list_open_workorders_in_category import REGISTER
        sentinel = object()
        old = REGISTER._db_pool
        try:
            REGISTER._db_pool = sentinel
            assert REGISTER._db_pool is sentinel
        finally:
            REGISTER._db_pool = old  # restore
