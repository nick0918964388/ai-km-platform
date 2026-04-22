"""
Integration tests: orchestrator._run_sql_task uses tool router first.

Cases:
  1. Tool router returns route_path=tool → result has route_path=tool, tool_name set
  2. Tool router returns route_path=fallback → orchestrator unpacks nl2sql_result
  3. InFailedSQLTransactionError on first attempt → savepoint rollback → retry succeeds
  4. _adapt_tool_result_to_nl2sql_shape maps fields correctly
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.orchestrator import (
    SubTask,
    _adapt_tool_result_to_nl2sql_shape,
    _run_sql_task,
)
from app.services.maximo_tools.base import UserContext


# ---------------------------------------------------------------------------
# Unit: _adapt_tool_result_to_nl2sql_shape
# ---------------------------------------------------------------------------

def test_adapt_tool_result_maps_rows_to_data():
    router_result = {
        "query_id": "abc",
        "route_path": "tool",
        "tool_name": "get_vehicle_info",
        "tool_input": {"asset_num": "EMU852"},
        "rows": [{"車號": "EMU852", "狀態": "運轉中"}],
        "row_count": 1,
        "chart_hint": None,
        "elapsed_ms": 42,
        "debug": {},
    }
    result = _adapt_tool_result_to_nl2sql_shape(router_result)

    assert result["success"] is True
    assert result["data"] == [{"車號": "EMU852", "狀態": "運轉中"}]
    assert result["columns"] == ["車號", "狀態"]
    assert result["row_count"] == 1
    assert result["execution_ms"] == 42
    assert result["route_path"] == "tool"
    assert result["tool_name"] == "get_vehicle_info"
    assert "get_vehicle_info" in result["explanation"]
    assert result["sql"] is None


def test_adapt_tool_result_empty_rows():
    router_result = {
        "route_path": "tool",
        "tool_name": "search_faults_by_vehicle",
        "tool_input": {"vehicle_num": "EMU901"},
        "rows": [],
        "row_count": 0,
        "chart_hint": None,
        "elapsed_ms": 30,
    }
    result = _adapt_tool_result_to_nl2sql_shape(router_result)

    assert result["success"] is True
    assert result["data"] == []
    assert result["columns"] == []
    assert result["row_count"] == 0
    assert result["route_path"] == "tool"


# ---------------------------------------------------------------------------
# Integration: _run_sql_task routes through tool router
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_tool_router_hit():
    """Router returns route_path=tool with vehicle info rows."""
    router = AsyncMock()
    router.route = AsyncMock(return_value={
        "query_id": "qid-001",
        "route_path": "tool",
        "tool_name": "get_vehicle_info",
        "tool_input": {"asset_num": "EMU852"},
        "rows": [{"車號": "EMU852-1", "車型": "EMU800", "狀態": "運轉中"}],
        "row_count": 1,
        "chart_hint": None,
        "elapsed_ms": 55,
        "debug": {},
    })
    return router


@pytest.fixture
def mock_nl2sql_result():
    return {
        "success": True,
        "sql": "SELECT * FROM maximo_assets WHERE assetnum = 'EMU901'",
        "explanation": "查詢車輛資訊",
        "data": [{"assetnum": "EMU901", "status": "OPERATING"}],
        "columns": ["assetnum", "status"],
        "row_count": 1,
        "execution_ms": 20,
        "route_path": "nl2sql",
    }


@pytest.fixture
def mock_tool_router_fallback(mock_nl2sql_result):
    """Router returns route_path=fallback (no tool matched)."""
    router = AsyncMock()
    router.route = AsyncMock(return_value={
        "query_id": "qid-002",
        "route_path": "fallback",
        "tool_name": None,
        "tool_input": None,
        "rows": mock_nl2sql_result["data"],
        "row_count": 1,
        "chart_hint": None,
        "elapsed_ms": 200,
        "debug": {
            "sql": mock_nl2sql_result["sql"],
            "explanation": mock_nl2sql_result["explanation"],
            "nl2sql_result": mock_nl2sql_result,
        },
    })
    return router


@pytest.mark.asyncio
async def test_run_sql_task_hits_tool_router(mock_tool_router_hit):
    """When tool router returns route_path=tool, result has correct shape."""
    task = SubTask(id="sql_001", type="sql", sub_query="EMU852 車輛資訊", label="查詢車輛")

    # build_router is imported inside the function body, so patch it at the
    # router_factory module level where it is defined.
    with patch(
        "app.services.maximo_tools.router_factory.build_router",
        return_value=mock_tool_router_hit,
    ):
        worker_result = await _run_sql_task(task)

    assert worker_result["error"] is None
    assert worker_result["task_id"] == "sql_001"
    result = worker_result["result"]
    assert result["route_path"] == "tool"
    assert result["tool_name"] == "get_vehicle_info"
    assert result["data"] == [{"車號": "EMU852-1", "車型": "EMU800", "狀態": "運轉中"}]
    assert result["row_count"] == 1
    assert result["success"] is True


@pytest.mark.asyncio
async def test_run_sql_task_falls_back_to_nl2sql(mock_tool_router_fallback, mock_nl2sql_result):
    """When tool router returns route_path=fallback, nl2sql_result is used."""
    task = SubTask(id="sql_002", type="sql", sub_query="EMU901 的故障通報", label="查詢故障")

    with patch(
        "app.services.maximo_tools.router_factory.build_router",
        return_value=mock_tool_router_fallback,
    ):
        worker_result = await _run_sql_task(task)

    assert worker_result["error"] is None
    result = worker_result["result"]
    # nl2sql_result is unpacked from debug
    assert result["sql"] == mock_nl2sql_result["sql"]
    assert result["data"] == mock_nl2sql_result["data"]
    assert result["row_count"] == 1


# ---------------------------------------------------------------------------
# Unit: execute_sql savepoint prevents InFailedSQLTransactionError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_sql_savepoint_rollback_allows_retry():
    """
    Simulate: first execute raises ProgrammingError (bad SQL), savepoint rolls back.
    Second execute (on same session) must succeed without InFailedSQLTransactionError.
    """
    pytest.importorskip("sqlalchemy", reason="sqlalchemy not installed in this env")
    from sqlalchemy.exc import ProgrammingError
    from app.services.maximo_nl2sql import MaximoNL2SQL

    # Track savepoint calls
    sp_rollback_called = []

    class FakeSavepoint:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            if exc_type is not None:
                sp_rollback_called.append(True)
            return False  # re-raise

        async def rollback(self):
            sp_rollback_called.append(True)

    call_count = [0]

    mock_db = AsyncMock()
    mock_db.begin_nested = MagicMock(return_value=FakeSavepoint())

    async def fake_execute(stmt, params=None):
        call_count[0] += 1
        if call_count[0] == 1:
            raise ProgrammingError("column does not exist", None, None)
        # Second call succeeds
        result = MagicMock()
        result.keys.return_value = ["assetnum"]
        result.fetchall.return_value = [("EMU852",)]
        return result

    mock_db.execute = fake_execute

    service = MaximoNL2SQL.__new__(MaximoNL2SQL)
    service.db = mock_db

    # First call — should fail gracefully
    r1 = await service.execute_sql("SELECT bad_col FROM maximo_assets")
    assert "error" in r1
    assert r1["rows"] == []

    # Second call — should succeed (savepoint was rolled back, not outer tx)
    r2 = await service.execute_sql("SELECT assetnum FROM maximo_assets")
    assert r2.get("row_count") == 1
    assert r2["rows"] == [{"assetnum": "EMU852"}]
