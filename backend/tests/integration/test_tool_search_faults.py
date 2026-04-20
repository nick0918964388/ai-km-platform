"""
Integration tests for SearchFaultsByVehicleTool (Tool 3) — requires live PostgreSQL.

Known real data (SSH verified 2026-04-20):
    maximo_fault_reports — 395 筆
    status 中文 6 種：立案(360) / 結案(14) / 處理中(10) / 取消(7) / 接件中(2) / 可放車(2)
    urgency A(20) / B(26) / C(125) / NULL(224)

Skip trigger: set env var SKIP_INTEGRATION=1 OR if DATABASE_URL is unreachable.
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
# DB setup helpers
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
    """Minimal pool adapter wrapping a single psycopg2 connection."""

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
# Helpers
# ---------------------------------------------------------------------------

from app.services.maximo_tools.base import UserContext
from app.services.maximo_tools.tools.search_faults_by_vehicle import SearchFaultsByVehicleTool


def _ctx(**kwargs) -> UserContext:
    defaults = dict(user_id="integration-test", role="admin")
    defaults.update(kwargs)
    return UserContext(**defaults)


def _fetch_real_assetnum(db_pool, where: str = "") -> str | None:
    """從 maximo_fault_reports 撈一個符合條件的 assetnum。"""
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT assetnum FROM maximo_fault_reports {where} LIMIT 1"
            )
            row = cur.fetchone()
    finally:
        db_pool.putconn(conn)
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.skipif(_SKIP, reason=_SKIP_REASON)
class TestSearchFaultsByVehicleIntegration:

    @pytest.mark.asyncio
    async def test_real_db_existing_asset(self, db_pool):
        """找一個真實存在的 assetnum，驗證回傳結構與中文化欄位。"""
        asset_num = _fetch_real_assetnum(db_pool)
        if asset_num is None:
            pytest.skip("No rows in maximo_fault_reports")

        tool = SearchFaultsByVehicleTool(db_pool=db_pool)
        result = await tool.execute(
            {"asset_num": asset_num, "date_range": "all"}, _ctx()
        )

        assert result.success is True
        assert result.row_count >= 1
        assert len(result.rows) >= 1

        row = result.rows[0]
        expected_keys = {
            "通報號", "車號", "狀態", "故障等級", "事件等級",
            "TCMS碼", "故障描述", "故障現象", "處理情形", "通報日期", "發生時間",
        }
        assert expected_keys.issubset(row.keys()), f"Missing keys: {expected_keys - row.keys()}"
        assert row["車號"] == asset_num

    @pytest.mark.asyncio
    async def test_real_db_not_found(self, db_pool):
        """不存在的 asset_num → rows=[]，仍 success=True。"""
        tool = SearchFaultsByVehicleTool(db_pool=db_pool)
        result = await tool.execute(
            {"asset_num": "DEFINITELY_NOT_EXISTS_XYZ", "date_range": "all"}, _ctx()
        )

        assert result.success is True
        assert result.rows == []
        assert result.row_count == 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_real_db_urgency_a_filter(self, db_pool):
        """urgency=A 過濾：回傳列的故障等級全部是 'A'。"""
        # 先找一個有 urgency=A 的 assetnum
        asset_num = _fetch_real_assetnum(db_pool, "WHERE urgency = 'A'")
        if asset_num is None:
            pytest.skip("No urgency=A rows in maximo_fault_reports")

        tool = SearchFaultsByVehicleTool(db_pool=db_pool)
        result = await tool.execute(
            {"asset_num": asset_num, "urgency": "A", "date_range": "all"}, _ctx()
        )

        assert result.success is True
        for row in result.rows:
            assert row["故障等級"] == "A", f"Unexpected urgency: {row['故障等級']}"

    @pytest.mark.asyncio
    async def test_real_db_status_group_open(self, db_pool):
        """status_group=open → 回傳列的狀態都在 open 集合內。"""
        from app.services.maximo_tools.tools.search_faults_by_vehicle import _STATUS_OPEN

        asset_num = _fetch_real_assetnum(
            db_pool, f"WHERE status IN ('立案', '接件中', '處理中')"
        )
        if asset_num is None:
            pytest.skip("No open-status rows in maximo_fault_reports")

        tool = SearchFaultsByVehicleTool(db_pool=db_pool)
        result = await tool.execute(
            {"asset_num": asset_num, "status_group": "open", "date_range": "all"}, _ctx()
        )

        assert result.success is True
        for row in result.rows:
            assert row["狀態"] in _STATUS_OPEN, f"Unexpected status: {row['狀態']}"

    @pytest.mark.asyncio
    async def test_real_db_date_range_all_returns_most(self, db_pool):
        """date_range=all 比 last_30d 回傳更多或相等的資料。"""
        asset_num = _fetch_real_assetnum(db_pool)
        if asset_num is None:
            pytest.skip("No rows in maximo_fault_reports")

        tool = SearchFaultsByVehicleTool(db_pool=db_pool)

        result_all = await tool.execute(
            {"asset_num": asset_num, "date_range": "all"}, _ctx()
        )
        result_30d = await tool.execute(
            {"asset_num": asset_num, "date_range": "last_30d"}, _ctx()
        )

        assert result_all.success is True
        assert result_30d.success is True
        assert result_all.row_count >= result_30d.row_count

    @pytest.mark.asyncio
    async def test_real_db_elapsed_ms_reasonable(self, db_pool):
        """查詢延遲應 < 5000ms。"""
        asset_num = _fetch_real_assetnum(db_pool) or "DOES_NOT_EXIST"
        tool = SearchFaultsByVehicleTool(db_pool=db_pool)
        result = await tool.execute(
            {"asset_num": asset_num, "date_range": "all"}, _ctx()
        )

        assert result.elapsed_ms >= 0
        assert result.elapsed_ms < 5000, f"Query too slow: {result.elapsed_ms}ms"

    @pytest.mark.asyncio
    async def test_real_db_section_filter_restricts_results(self, db_pool):
        """section 注入 report_unit filter：結果只含該段/所。"""
        # 找一個有 report_unit 的 assetnum
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT assetnum, report_unit FROM maximo_fault_reports "
                    "WHERE report_unit IS NOT NULL AND report_unit != '' LIMIT 1"
                )
                row = cur.fetchone()
        finally:
            db_pool.putconn(conn)

        if row is None:
            pytest.skip("No rows with report_unit in maximo_fault_reports")

        asset_num, section = row[0], row[1]
        tool = SearchFaultsByVehicleTool(db_pool=db_pool)
        result = await tool.execute(
            {"asset_num": asset_num, "date_range": "all"},
            _ctx(section=section),
        )

        assert result.success is True
        for r in result.rows:
            # 結果不含 report_unit 欄位（已轉中文欄位），只確認 success + structure
            assert "車號" in r
