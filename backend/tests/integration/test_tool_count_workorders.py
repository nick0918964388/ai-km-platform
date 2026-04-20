"""
Integration tests for CountOpenWorkordersByCategoryTool (Tool 5) — requires live PostgreSQL.

Known real data (SSH verified 2026-04-20):
    maximo_mxasset: eq11 values = RSTL / RSTA / RSTF / RSTP (48% NULL)
    After filtering eq11 IS NOT NULL AND eq11 != '': exactly 3 categories
    (動力車 from RSTL, 客車 from RSTA, 貨車 merged from RSTF+RSTP)

Skip trigger: set env var SKIP_INTEGRATION=1 OR if DATABASE_URL is unreachable.
"""
from __future__ import annotations

import os

import pytest

_SKIP = os.getenv("SKIP_INTEGRATION", "").strip() not in ("", "0")
_SKIP_REASON = "SKIP_INTEGRATION is set" if _SKIP else ""

if not _SKIP:
    try:
        import psycopg2  # noqa: F401
    except ImportError:
        _SKIP = True
        _SKIP_REASON = "psycopg2 not installed"


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


from app.services.maximo_tools.base import UserContext
from app.services.maximo_tools.tools.count_open_workorders_by_category import (
    CountOpenWorkordersByCategoryTool,
)


def _ctx() -> UserContext:
    return UserContext(user_id="integration-test", role="admin")


@pytest.mark.skipif(_SKIP, reason=_SKIP_REASON)
class TestCountOpenWorkordersByCategoryIntegration:

    @pytest.mark.asyncio
    async def test_da_fen_lei_returns_exactly_three_categories(self, db_pool):
        """
        group_by=大分類 after filtering eq11 IS NOT NULL should yield
        exactly 3 rows: 動力車, 客車, 貨車 (RSTF+RSTP merged).
        """
        tool = CountOpenWorkordersByCategoryTool(db_pool=db_pool)
        result = await tool.execute({"group_by": "大分類"}, _ctx())

        assert result.success is True, f"Unexpected error: {result.error}"
        assert result.row_count == 3, (
            f"Expected 3 categories, got {result.row_count}: "
            f"{[r['分類'] for r in result.rows]}"
        )

        category_names = {r["分類"] for r in result.rows}
        assert category_names == {"動力車", "客車", "貨車"}

    @pytest.mark.asyncio
    async def test_da_fen_lei_percentage_sums_to_100(self, db_pool):
        """百分比加總 ≈ 100.00（允許 ±0.02 四捨五入誤差）。"""
        tool = CountOpenWorkordersByCategoryTool(db_pool=db_pool)
        result = await tool.execute({"group_by": "大分類"}, _ctx())

        assert result.success is True
        total_pct = sum(r["百分比"] for r in result.rows)
        assert abs(total_pct - 100.0) <= 0.02, f"Percentage sum = {total_pct}"

    @pytest.mark.asyncio
    async def test_freight_count_equals_rstf_plus_rstp(self, db_pool):
        """
        貨車的 count 應等於 RSTF + RSTP 的工單數合計（雙碼合併驗證）。
        """
        tool = CountOpenWorkordersByCategoryTool(db_pool=db_pool)
        result = await tool.execute({"group_by": "大分類"}, _ctx())

        assert result.success is True
        freight_rows = [r for r in result.rows if r["分類"] == "貨車"]
        if not freight_rows:
            pytest.skip("No 貨車 workorders in DB")

        freight_count = freight_rows[0]["工單數"]

        # Verify directly from DB: count workorders where asset eq11 IN ('RSTF','RSTP')
        _CLOSED = ("工單結案", "工單取消", "工單退回")
        closed_ph = ", ".join(["%s"] * len(_CLOSED))
        sql = f"""
            WITH wo AS (
                SELECT assetnum FROM maximo_pm_workorders
                WHERE status NOT IN ({closed_ph})
                UNION ALL
                SELECT assetnum FROM maximo_cm_workorders
                WHERE status NOT IN ({closed_ph})
            )
            SELECT COUNT(*) FROM wo
            JOIN maximo_mxasset a ON wo.assetnum = a.assetnum
            WHERE a.eq11 IN ('RSTF', 'RSTP')
        """
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(_CLOSED) + tuple(_CLOSED))
                raw_count = cur.fetchone()[0]
        finally:
            db_pool.putconn(conn)

        assert freight_count == int(raw_count), (
            f"Freight count mismatch: tool={freight_count}, direct={raw_count}"
        )

    @pytest.mark.asyncio
    async def test_da_fen_lei_rows_ordered_by_count_desc(self, db_pool):
        """結果應依工單數降冪排列。"""
        tool = CountOpenWorkordersByCategoryTool(db_pool=db_pool)
        result = await tool.execute({"group_by": "大分類"}, _ctx())

        assert result.success is True
        counts = [r["工單數"] for r in result.rows]
        assert counts == sorted(counts, reverse=True), f"Not sorted DESC: {counts}"

    @pytest.mark.asyncio
    async def test_da_fen_lei_output_keys_correct(self, db_pool):
        """每列必須有 分類/工單數/百分比 三個中文 key。"""
        tool = CountOpenWorkordersByCategoryTool(db_pool=db_pool)
        result = await tool.execute({"group_by": "大分類"}, _ctx())

        assert result.success is True
        for row in result.rows:
            assert "分類" in row
            assert "工單數" in row
            assert "百分比" in row

    @pytest.mark.asyncio
    async def test_da_fen_lei_chart_hint_is_pie(self, db_pool):
        tool = CountOpenWorkordersByCategoryTool(db_pool=db_pool)
        result = await tool.execute({"group_by": "大分類"}, _ctx())

        assert result.chart_hint is not None
        assert result.chart_hint["type"] == "pie"

    @pytest.mark.asyncio
    async def test_che_zhong_returns_rows_and_bar_hint(self, db_pool):
        """group_by=車種 應回傳至少 1 列且 chart_hint.type=bar。"""
        tool = CountOpenWorkordersByCategoryTool(db_pool=db_pool)
        result = await tool.execute({"group_by": "車種"}, _ctx())

        assert result.success is True
        assert result.chart_hint["type"] == "bar"
        # eq3 可能有多種車種，至少要有 1 列
        assert result.row_count >= 1

    @pytest.mark.asyncio
    async def test_elapsed_ms_reasonable(self, db_pool):
        tool = CountOpenWorkordersByCategoryTool(db_pool=db_pool)
        result = await tool.execute({"group_by": "大分類"}, _ctx())

        assert result.elapsed_ms >= 0
        assert result.elapsed_ms < 10000, f"Query too slow: {result.elapsed_ms}ms"
