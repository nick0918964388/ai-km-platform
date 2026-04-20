"""
Unit tests for GetVehicleInfoTool (Tool 1).

策略：mock psycopg2 pool + cursor，不碰真實 DB。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.maximo_tools.base import ToolResult, UserContext
from app.services.maximo_tools.tools.get_vehicle_info import (
    GetVehicleInfoTool,
    _ASSET_STATUS_CHINESE,
    _SCHEMA,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_user_ctx(**kwargs) -> UserContext:
    defaults = dict(user_id="u-test-001", role="admin")
    defaults.update(kwargs)
    return UserContext(**defaults)


def _make_pool(fetchone_return=None) -> MagicMock:
    """
    Build a mock psycopg2-style pool that returns one row on fetchone().
    fetchone_return should be a tuple matching the SELECT column order:
        (assetnum, eq3, eq4, eq11, status, assettype, siteid)
    """
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_return
    # Simulate cursor.description for col_names extraction
    if fetchone_return is not None:
        col_names = ["assetnum", "eq3", "eq4", "eq11", "status", "assettype", "siteid"]
        cursor.description = [(name,) for name in col_names]
    else:
        cursor.description = [
            ("assetnum",), ("eq3",), ("eq4",), ("eq11",), ("status",), ("assettype",), ("siteid",)
        ]

    # cursor as context manager
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
    def test_definition_name(self):
        assert GetVehicleInfoTool.definition.name == "get_vehicle_info"

    def test_definition_has_description(self):
        assert len(GetVehicleInfoTool.definition.description) > 0

    def test_input_schema_valid(self):
        from app.services.maximo_tools.base import validate_tool_schema
        # Should not raise — validate_tool_schema is also called at module import
        validate_tool_schema(_SCHEMA)

    def test_input_schema_requires_asset_num(self):
        assert "asset_num" in _SCHEMA.get("properties", {})
        assert "asset_num" in _SCHEMA.get("required", [])


# ---------------------------------------------------------------------------
# 2. Happy path
# ---------------------------------------------------------------------------

class TestExecuteHappyPath:
    @pytest.mark.asyncio
    async def test_returns_chinese_keys(self):
        row = ("EMU852", "EMU", "EMU800", "RSTL", "OPERATING", None, "TRATW")
        tool = GetVehicleInfoTool(db_pool=_make_pool(fetchone_return=row))
        result = await tool.execute({"asset_num": "EMU852"}, _make_user_ctx())

        assert result.success is True
        assert result.row_count == 1
        assert len(result.rows) == 1
        r = result.rows[0]
        assert "車號" in r
        assert "車種" in r
        assert "車型" in r
        assert "大分類" in r
        assert "大分類代碼" in r
        assert "狀態" in r
        assert "狀態代碼" in r
        assert "資產類型" in r
        assert "站點" in r

    @pytest.mark.asyncio
    async def test_values_correct(self):
        row = ("EMU852", "EMU", "EMU800", "RSTL", "OPERATING", None, "TRATW")
        tool = GetVehicleInfoTool(db_pool=_make_pool(fetchone_return=row))
        result = await tool.execute({"asset_num": "EMU852"}, _make_user_ctx())

        r = result.rows[0]
        assert r["車號"] == "EMU852"
        assert r["車種"] == "EMU"
        assert r["車型"] == "EMU800"
        assert r["大分類代碼"] == "RSTL"
        assert r["站點"] == "TRATW"
        assert result.error is None
        assert result.error_code is None


# ---------------------------------------------------------------------------
# 3. Not found
# ---------------------------------------------------------------------------

class TestExecuteNotFound:
    @pytest.mark.asyncio
    async def test_empty_rows_on_not_found(self):
        tool = GetVehicleInfoTool(db_pool=_make_pool(fetchone_return=None))
        result = await tool.execute({"asset_num": "DOES_NOT_EXIST"}, _make_user_ctx())

        assert result.success is True
        assert result.rows == []
        assert result.row_count == 0
        assert result.error is None


# ---------------------------------------------------------------------------
# 4. Status translation
# ---------------------------------------------------------------------------

class TestStatusTranslation:
    @pytest.mark.asyncio
    async def test_operating_maps_to_chinese(self):
        row = ("A001", None, None, None, "OPERATING", None, None)
        tool = GetVehicleInfoTool(db_pool=_make_pool(fetchone_return=row))
        result = await tool.execute({"asset_num": "A001"}, _make_user_ctx())
        assert result.rows[0]["狀態"] == "運轉中"

    @pytest.mark.asyncio
    async def test_not_ready_maps_to_chinese(self):
        row = ("A002", None, None, None, "NOT READY", None, None)
        tool = GetVehicleInfoTool(db_pool=_make_pool(fetchone_return=row))
        result = await tool.execute({"asset_num": "A002"}, _make_user_ctx())
        assert result.rows[0]["狀態"] == "未就緒"

    @pytest.mark.asyncio
    async def test_decommissioned_maps_to_chinese(self):
        row = ("A003", None, None, None, "DECOMMISSIONED", None, None)
        tool = GetVehicleInfoTool(db_pool=_make_pool(fetchone_return=row))
        result = await tool.execute({"asset_num": "A003"}, _make_user_ctx())
        assert result.rows[0]["狀態"] == "除役"

    @pytest.mark.asyncio
    async def test_inactive_maps_to_chinese(self):
        row = ("A004", None, None, None, "INACTIVE", None, None)
        tool = GetVehicleInfoTool(db_pool=_make_pool(fetchone_return=row))
        result = await tool.execute({"asset_num": "A004"}, _make_user_ctx())
        assert result.rows[0]["狀態"] == "停用"

    @pytest.mark.asyncio
    async def test_unknown_status_returned_as_is(self):
        row = ("A005", None, None, None, "FUTURE_STATUS", None, None)
        tool = GetVehicleInfoTool(db_pool=_make_pool(fetchone_return=row))
        result = await tool.execute({"asset_num": "A005"}, _make_user_ctx())
        # Unknown status passes through unchanged (not in dict)
        assert result.rows[0]["狀態"] == "FUTURE_STATUS"
        assert result.rows[0]["狀態代碼"] == "FUTURE_STATUS"

    @pytest.mark.asyncio
    async def test_null_status_returns_none(self):
        row = ("A006", None, None, None, None, None, None)
        tool = GetVehicleInfoTool(db_pool=_make_pool(fetchone_return=row))
        result = await tool.execute({"asset_num": "A006"}, _make_user_ctx())
        assert result.rows[0]["狀態"] is None
        assert result.rows[0]["狀態代碼"] is None

    @pytest.mark.asyncio
    async def test_empty_string_status_returns_none(self):
        row = ("A007", None, None, "", "", None, None)
        tool = GetVehicleInfoTool(db_pool=_make_pool(fetchone_return=row))
        result = await tool.execute({"asset_num": "A007"}, _make_user_ctx())
        assert result.rows[0]["狀態"] is None
        assert result.rows[0]["狀態代碼"] is None


# ---------------------------------------------------------------------------
# 5. eq11 translation
# ---------------------------------------------------------------------------

class TestEq11Translation:
    @pytest.mark.asyncio
    async def test_rstf_maps_to_freight(self):
        row = ("A010", None, None, "RSTF", "OPERATING", None, None)
        tool = GetVehicleInfoTool(db_pool=_make_pool(fetchone_return=row))
        result = await tool.execute({"asset_num": "A010"}, _make_user_ctx())
        assert result.rows[0]["大分類"] == "貨車"
        assert result.rows[0]["大分類代碼"] == "RSTF"

    @pytest.mark.asyncio
    async def test_rstp_maps_to_freight(self):
        row = ("A011", None, None, "RSTP", "OPERATING", None, None)
        tool = GetVehicleInfoTool(db_pool=_make_pool(fetchone_return=row))
        result = await tool.execute({"asset_num": "A011"}, _make_user_ctx())
        assert result.rows[0]["大分類"] == "貨車"

    @pytest.mark.asyncio
    async def test_rsta_maps_to_passenger(self):
        row = ("A012", None, None, "RSTA", "OPERATING", None, None)
        tool = GetVehicleInfoTool(db_pool=_make_pool(fetchone_return=row))
        result = await tool.execute({"asset_num": "A012"}, _make_user_ctx())
        assert result.rows[0]["大分類"] == "客車"

    @pytest.mark.asyncio
    async def test_rstl_maps_to_locomotive(self):
        row = ("A013", None, None, "RSTL", "OPERATING", None, None)
        tool = GetVehicleInfoTool(db_pool=_make_pool(fetchone_return=row))
        result = await tool.execute({"asset_num": "A013"}, _make_user_ctx())
        assert result.rows[0]["大分類"] == "動力車"

    @pytest.mark.asyncio
    async def test_eq11_empty_string_returns_none(self):
        row = ("A014", None, None, "", "OPERATING", None, None)
        tool = GetVehicleInfoTool(db_pool=_make_pool(fetchone_return=row))
        result = await tool.execute({"asset_num": "A014"}, _make_user_ctx())
        assert result.rows[0]["大分類"] is None
        assert result.rows[0]["大分類代碼"] is None

    @pytest.mark.asyncio
    async def test_eq11_none_returns_none(self):
        row = ("A015", None, None, None, "OPERATING", None, None)
        tool = GetVehicleInfoTool(db_pool=_make_pool(fetchone_return=row))
        result = await tool.execute({"asset_num": "A015"}, _make_user_ctx())
        assert result.rows[0]["大分類"] is None
        assert result.rows[0]["大分類代碼"] is None

    @pytest.mark.asyncio
    async def test_unknown_eq11_passes_through(self):
        row = ("A016", None, None, "UNKNOWN_CODE", "OPERATING", None, None)
        tool = GetVehicleInfoTool(db_pool=_make_pool(fetchone_return=row))
        result = await tool.execute({"asset_num": "A016"}, _make_user_ctx())
        # from_code returns original value for unknown codes
        assert result.rows[0]["大分類"] == "UNKNOWN_CODE"
        assert result.rows[0]["大分類代碼"] == "UNKNOWN_CODE"


# ---------------------------------------------------------------------------
# 6. eq3/eq4 empty / null handling
# ---------------------------------------------------------------------------

class TestEq3Eq4Handling:
    @pytest.mark.asyncio
    async def test_eq3_empty_string_returns_none(self):
        row = ("A020", "", "EMU800", "RSTL", "OPERATING", None, None)
        tool = GetVehicleInfoTool(db_pool=_make_pool(fetchone_return=row))
        result = await tool.execute({"asset_num": "A020"}, _make_user_ctx())
        assert result.rows[0]["車種"] is None

    @pytest.mark.asyncio
    async def test_eq4_empty_string_returns_none(self):
        row = ("A021", "EMU", "", "RSTL", "OPERATING", None, None)
        tool = GetVehicleInfoTool(db_pool=_make_pool(fetchone_return=row))
        result = await tool.execute({"asset_num": "A021"}, _make_user_ctx())
        assert result.rows[0]["車型"] is None

    @pytest.mark.asyncio
    async def test_eq3_none_returns_none(self):
        row = ("A022", None, None, "RSTL", "OPERATING", None, None)
        tool = GetVehicleInfoTool(db_pool=_make_pool(fetchone_return=row))
        result = await tool.execute({"asset_num": "A022"}, _make_user_ctx())
        assert result.rows[0]["車種"] is None


# ---------------------------------------------------------------------------
# 7. Invalid params
# ---------------------------------------------------------------------------

class TestInvalidParams:
    @pytest.mark.asyncio
    async def test_missing_asset_num_returns_error(self):
        tool = GetVehicleInfoTool(db_pool=_make_pool())
        result = await tool.execute({}, _make_user_ctx())

        assert result.success is False
        assert result.error_code == "TOOL_INVOCATION_ERROR"
        assert result.rows == []
        assert result.row_count == 0

    @pytest.mark.asyncio
    async def test_wrong_type_asset_num_coerces_or_fails(self):
        # Pydantic v2 coerces int to str, but we guard overall via model_validate
        # Either succeeds (coerced) or returns TOOL_INVOCATION_ERROR
        tool = GetVehicleInfoTool(db_pool=_make_pool(fetchone_return=None))
        result = await tool.execute({"asset_num": 12345}, _make_user_ctx())
        # Pydantic coerces int → str, so this may succeed with not-found
        assert isinstance(result, ToolResult)


# ---------------------------------------------------------------------------
# 8. DB exception
# ---------------------------------------------------------------------------

class TestDbException:
    @pytest.mark.asyncio
    async def test_pool_getconn_raises(self):
        pool = MagicMock()
        pool.getconn.side_effect = Exception("Connection pool exhausted")

        tool = GetVehicleInfoTool(db_pool=pool)
        result = await tool.execute({"asset_num": "EMU852"}, _make_user_ctx())

        assert result.success is False
        assert result.error_code == "TOOL_EXECUTION_ERROR"
        assert result.rows == []
        assert result.row_count == 0

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

        tool = GetVehicleInfoTool(db_pool=pool)
        result = await tool.execute({"asset_num": "EMU852"}, _make_user_ctx())

        assert result.success is False
        assert result.error_code == "TOOL_EXECUTION_ERROR"

    @pytest.mark.asyncio
    async def test_pool_putconn_called_even_on_exception(self):
        """確認 finally 區塊有 putconn（防止 connection leak）。"""
        cursor = MagicMock()
        cursor.execute.side_effect = Exception("DB error")
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cursor

        pool = MagicMock()
        pool.getconn.return_value = conn

        tool = GetVehicleInfoTool(db_pool=pool)
        await tool.execute({"asset_num": "EMU852"}, _make_user_ctx())

        pool.putconn.assert_called_once_with(conn)


# ---------------------------------------------------------------------------
# 9. No pool raises RuntimeError
# ---------------------------------------------------------------------------

class TestNoPool:
    @pytest.mark.asyncio
    async def test_no_pool_raises_runtime_error(self):
        tool = GetVehicleInfoTool()  # db_pool=None by default
        with pytest.raises(RuntimeError, match="db_pool not injected"):
            await tool.execute({"asset_num": "EMU852"}, _make_user_ctx())


# ---------------------------------------------------------------------------
# 10. REGISTER module constant
# ---------------------------------------------------------------------------

class TestRegisterConstant:
    def test_register_is_tool_instance(self):
        from app.services.maximo_tools.tools.get_vehicle_info import REGISTER
        from app.services.maximo_tools.base import Tool
        assert isinstance(REGISTER, Tool)

    def test_register_has_correct_name(self):
        from app.services.maximo_tools.tools.get_vehicle_info import REGISTER
        assert REGISTER.definition.name == "get_vehicle_info"

    def test_register_db_pool_is_none(self):
        """REGISTER 啟動時 db_pool=None，等 T014 API wiring 注入。"""
        from app.services.maximo_tools.tools.get_vehicle_info import REGISTER
        assert REGISTER._db_pool is None

    def test_register_db_pool_injectable(self):
        """驗證 _db_pool 屬性可寫（T014 monkey-patch approach）。"""
        from app.services.maximo_tools.tools.get_vehicle_info import REGISTER
        sentinel = object()
        old = REGISTER._db_pool
        try:
            REGISTER._db_pool = sentinel
            assert REGISTER._db_pool is sentinel
        finally:
            REGISTER._db_pool = old  # restore
