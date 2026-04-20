"""
Integration tests for GetVehicleInfoTool (Tool 1) — requires live PostgreSQL.

Known real data (SSH verified 2026-04-20):
    EMU852 | eq3=EMU | eq4=EMU800 | eq11=RSTL | status=OPERATING | siteid=TRATW

Skip trigger: set env var SKIP_INTEGRATION=1 OR if DATABASE_URL is unreachable.

DB connect URL: 使用 psycopg2，DATABASE_URL 中去除 asyncpg 前綴。
Pool adapter: 用 _SimplePoolAdapter 包住單一 psycopg2 connection，
              實作 getconn()/putconn() 介面，讓 GetVehicleInfoTool._query 可用。
"""
from __future__ import annotations

import os

import pytest

# ---------------------------------------------------------------------------
# Skip guard: SKIP_INTEGRATION env var OR psycopg2 not installed
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
# DB setup helpers
# ---------------------------------------------------------------------------

def _raw_db_url() -> str:
    """Strip async driver prefix so psycopg2 can connect."""
    url = os.getenv(
        "DATABASE_URL",
        "postgresql://aikm:aikm@192.168.1.11:5432/aikm",
    )
    return (
        url.replace("postgresql+asyncpg://", "postgresql://")
           .replace("postgresql+psycopg2://", "postgresql://")
    )


class _SimplePoolAdapter:
    """
    Minimal pool adapter wrapping a single psycopg2 connection.
    Implements getconn()/putconn() so GetVehicleInfoTool._query works unchanged.
    Not thread-safe; only for single-threaded integration tests.
    """

    def __init__(self, conn):
        self._conn = conn

    def getconn(self):
        return self._conn

    def putconn(self, conn):
        pass  # single-connection adapter — don't close here


@pytest.fixture(scope="module")
def db_pool():
    """
    Module-scoped fixture: create one psycopg2 connection for all tests.
    Skip if SKIP_INTEGRATION is set or connection fails.
    """
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
# Helpers
# ---------------------------------------------------------------------------

from app.services.maximo_tools.base import UserContext
from app.services.maximo_tools.tools.get_vehicle_info import GetVehicleInfoTool


def _ctx() -> UserContext:
    return UserContext(user_id="integration-test", role="admin")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_SKIP, reason=_SKIP_REASON)
class TestGetVehicleInfoIntegration:

    @pytest.mark.asyncio
    async def test_real_db_existing_asset(self, db_pool):
        """EMU852 は SSH 実測で確認済みの存在資產。"""
        tool = GetVehicleInfoTool(db_pool=db_pool)
        result = await tool.execute({"asset_num": "EMU852"}, _ctx())

        assert result.success is True
        assert result.row_count == 1
        assert len(result.rows) == 1

        row = result.rows[0]

        # 確認中文欄位 key 全部存在
        expected_keys = {"車號", "車種", "車型", "大分類", "大分類代碼", "狀態", "狀態代碼", "資產類型", "站點"}
        assert expected_keys.issubset(row.keys()), f"Missing keys: {expected_keys - row.keys()}"

        # 確認已知值正確
        assert row["車號"] == "EMU852"
        assert row["車種"] == "EMU"
        assert row["車型"] == "EMU800"
        assert row["大分類代碼"] == "RSTL"
        assert row["大分類"] == "動力車"       # from_code("RSTL") → 動力車
        assert row["狀態代碼"] == "OPERATING"
        assert row["狀態"] == "運轉中"
        assert row["站點"] == "TRATW"

    @pytest.mark.asyncio
    async def test_real_db_not_found(self, db_pool):
        """不存在的 asset_num → rows=[]，仍 success=True。"""
        tool = GetVehicleInfoTool(db_pool=db_pool)
        result = await tool.execute({"asset_num": "DEFINITELY_NOT_EXISTS_XYZ"}, _ctx())

        assert result.success is True
        assert result.rows == []
        assert result.row_count == 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_real_db_elapsed_ms_reasonable(self, db_pool):
        """DB 查詢延遲應 < 5000ms（合理範圍）。"""
        tool = GetVehicleInfoTool(db_pool=db_pool)
        result = await tool.execute({"asset_num": "EMU852"}, _ctx())

        assert result.elapsed_ms >= 0
        assert result.elapsed_ms < 5000, f"Query too slow: {result.elapsed_ms}ms"

    @pytest.mark.asyncio
    async def test_real_db_null_eq11_asset(self, db_pool):
        """eq11 為空的資產（實測 48% 為空）→ 大分類=None，不 crash。"""
        # 查一個 eq11 為空的車（用 siteid 已知，eq11=NULL 的）
        tool = GetVehicleInfoTool(db_pool=db_pool)

        # 先用 psycopg2 找一個 eq11 為 NULL 或空的 asset_num
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT assetnum FROM maximo_mxasset "
                    "WHERE (eq11 IS NULL OR eq11 = '') LIMIT 1"
                )
                row = cur.fetchone()
        finally:
            db_pool.putconn(conn)

        if row is None:
            pytest.skip("No asset with empty eq11 found in DB")

        asset_num = row[0]
        result = await tool.execute({"asset_num": asset_num}, _ctx())

        assert result.success is True
        assert result.row_count == 1
        assert result.rows[0]["大分類"] is None
        assert result.rows[0]["大分類代碼"] is None
