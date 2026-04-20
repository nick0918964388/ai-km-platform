"""
Integration tests for SearchWorkordersByVehicleTool (Tool 2) — requires live PostgreSQL.

Known real data (SSH verified 2026-04-20):
    35PPT1108 存在於 maximo_mxasset；PM/CM 工單表各有該車工單。

Skip trigger: set env var SKIP_INTEGRATION=1 OR if DATABASE_URL is unreachable.

DB connect: psycopg2，DATABASE_URL 去除 asyncpg 前綴。
Pool adapter: _SimplePoolAdapter 包住單一 psycopg2 connection。
"""
from __future__ import annotations

import os

import pytest

# ---------------------------------------------------------------------------
# Skip guard
# ---------------------------------------------------------------------------

_SKIP = os.getenv("SKIP_INTEGRATION", "").strip() not in ("", "0")
_SKIP_REASON = "SKIP_INTEGRATION is set" if _SKIP else ""

if not _SKIP:
    try:
        import psycopg2  # noqa: F401
    except ImportError:
        _SKIP = True
        _SKIP_REASON = "psycopg2 not installed"


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _raw_db_url() -> str:
    url = os.getenv(
        "DATABASE_URL",
        "postgresql://aikm:aikm@192.168.1.11:5432/aikm",
    )
    return (
        url.replace("postgresql+asyncpg://", "postgresql://")
           .replace("postgresql+psycopg2://", "postgresql://")
    )


class _SimplePoolAdapter:
    def __init__(self, conn):
        self._conn = conn

    def getconn(self):
        return self._conn

    def putconn(self, conn):
        pass


@pytest.fixture(scope="module")
def db_pool():
    if _SKIP:
        pytest.skip(_SKIP_REASON)

    import psycopg2

    try:
        conn = psycopg2.connect(_raw_db_url(), connect_timeout=5)
        conn.autocommit = True
    except Exception as exc:
        pytest.skip(f"Cannot connect to DB: {exc}")

    adapter = _SimplePoolAdapter(conn)
    yield adapter
    conn.close()


# ---------------------------------------------------------------------------
# Imports (after skip guard so test collection doesn't fail without psycopg2)
# ---------------------------------------------------------------------------

from app.services.maximo_tools.base import UserContext
from app.services.maximo_tools.tools.search_workorders_by_vehicle import (
    SearchWorkordersByVehicleTool,
)


def _ctx(section: str | None = None) -> UserContext:
    return UserContext(user_id="integration-test", role="admin", section=section)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_SKIP, reason=_SKIP_REASON)
class TestSearchWorkordersIntegration:

    @pytest.mark.asyncio
    async def test_real_db_returns_rows_with_chinese_keys(self, db_pool):
        """35PPT1108 查工單，驗證中文欄位存在。"""
        tool = SearchWorkordersByVehicleTool(db_pool=db_pool)
        result = await tool.execute(
            {"asset_num": "35PPT1108", "date_range": "all"},
            _ctx(),
        )

        assert result.success is True
        # 若該車無工單也 OK，只要 success + 欄位結構正確
        if result.row_count > 0:
            row = result.rows[0]
            expected_keys = {
                "工單號", "車號", "狀態", "工單類型",
                "工作類型", "描述", "通報日期", "實際開始", "實際完工",
            }
            assert expected_keys == set(row.keys()), (
                f"Missing/extra keys: expected={expected_keys}, got={set(row.keys())}"
            )

    @pytest.mark.asyncio
    async def test_real_db_wo_type_field_is_定檢_or_臨修(self, db_pool):
        """工單類型欄位值必須是 定檢 或 臨修。"""
        tool = SearchWorkordersByVehicleTool(db_pool=db_pool)
        result = await tool.execute(
            {"asset_num": "35PPT1108", "date_range": "all"},
            _ctx(),
        )

        assert result.success is True
        for row in result.rows:
            assert row["工單類型"] in ("定檢", "臨修"), (
                f"Unexpected wo_type: {row['工單類型']!r}"
            )

    @pytest.mark.asyncio
    async def test_real_db_wo_type_定檢_only_pm(self, db_pool):
        """wo_type=定檢 → 所有回傳工單類型必須是 定檢。"""
        tool = SearchWorkordersByVehicleTool(db_pool=db_pool)
        result = await tool.execute(
            {"asset_num": "35PPT1108", "wo_type": "定檢", "date_range": "all"},
            _ctx(),
        )

        assert result.success is True
        for row in result.rows:
            assert row["工單類型"] == "定檢"

    @pytest.mark.asyncio
    async def test_real_db_wo_type_臨修_only_cm(self, db_pool):
        """wo_type=臨修 → 所有回傳工單類型必須是 臨修。"""
        tool = SearchWorkordersByVehicleTool(db_pool=db_pool)
        result = await tool.execute(
            {"asset_num": "35PPT1108", "wo_type": "臨修", "date_range": "all"},
            _ctx(),
        )

        assert result.success is True
        for row in result.rows:
            assert row["工單類型"] == "臨修"

    @pytest.mark.asyncio
    async def test_real_db_not_found_asset(self, db_pool):
        """不存在車號 → rows=[], success=True。"""
        tool = SearchWorkordersByVehicleTool(db_pool=db_pool)
        result = await tool.execute(
            {"asset_num": "DEFINITELY_NOT_EXISTS_XYZ999"},
            _ctx(),
        )

        assert result.success is True
        assert result.rows == []
        assert result.row_count == 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_real_db_elapsed_ms_reasonable(self, db_pool):
        """查詢延遲應 < 10000ms。"""
        tool = SearchWorkordersByVehicleTool(db_pool=db_pool)
        result = await tool.execute(
            {"asset_num": "35PPT1108", "date_range": "all"},
            _ctx(),
        )

        assert result.elapsed_ms >= 0
        assert result.elapsed_ms < 10000, f"Query too slow: {result.elapsed_ms}ms"

    @pytest.mark.asyncio
    async def test_real_db_status_group_open_filter(self, db_pool):
        """status_group=open → 所有回傳工單的狀態必須在 open 集合內。"""
        from app.services.maximo_tools.tools.search_workorders_by_vehicle import _STATUS_OPEN

        tool = SearchWorkordersByVehicleTool(db_pool=db_pool)
        result = await tool.execute(
            {"asset_num": "35PPT1108", "status_group": "open", "date_range": "all"},
            _ctx(),
        )

        assert result.success is True
        for row in result.rows:
            assert row["狀態"] in _STATUS_OPEN, (
                f"Row with status={row['狀態']!r} should not be in open group"
            )
