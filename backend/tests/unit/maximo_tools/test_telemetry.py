"""
Unit tests for backend/app/services/maximo_tools/telemetry.py

All DB interactions are mocked — no real connection required.
"""

import asyncio
from unittest.mock import MagicMock, patch, call
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.services.maximo_tools.telemetry import (
    ToolCallRecord,
    get_counters,
    record_tool_call,
    reset_counters,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(**overrides) -> ToolCallRecord:
    defaults = dict(
        tool_name="get_vehicle_info",
        params={"asset_num": "A12345"},
        route_path="tool",
        latency_ms=42,
        success=True,
        row_count=1,
    )
    defaults.update(overrides)
    return ToolCallRecord(**defaults)


def _make_pool_mock():
    """Return a mock that looks like a psycopg2 ThreadedConnectionPool."""
    conn = MagicMock()
    pool = MagicMock()
    pool.getconn.return_value = conn
    return pool, conn


# ---------------------------------------------------------------------------
# Test 1 — Happy path: cursor.execute called once with correct params
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_tool_call_happy_path():
    reset_counters()
    record = _make_record()
    pool, conn = _make_pool_mock()

    await record_tool_call(record, db_pool=pool)

    # Pool used correctly
    pool.getconn.assert_called_once()
    pool.putconn.assert_called_once_with(conn)
    conn.commit.assert_called_once()

    # cursor.execute called exactly once
    cursor = conn.cursor.return_value.__enter__.return_value
    assert cursor.execute.call_count == 1

    # First positional arg is the SQL string, second is the params dict
    _, kwargs = cursor.execute.call_args
    execute_args = cursor.execute.call_args[0]
    sql_arg, params_arg = execute_args[0], execute_args[1]

    assert "INSERT INTO maximo_tool_calls" in sql_arg
    assert params_arg["query_id"] == str(record.query_id)
    assert params_arg["tool_name"] == "get_vehicle_info"
    assert params_arg["route_path"] == "tool"
    assert params_arg["latency_ms"] == 42
    assert params_arg["success"] is True
    assert params_arg["row_count"] == 1
    # params field must be JSON-serialised
    import json
    assert json.loads(params_arg["params"]) == {"asset_num": "A12345"}

    # Counters unchanged
    c = get_counters()
    assert c["timeout"] == 0
    assert c["failed"] == 0


# ---------------------------------------------------------------------------
# Test 2 — DB exception: function must not raise; logger.exception called;
#           failed counter increments
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_tool_call_db_exception():
    reset_counters()
    record = _make_record()
    pool, conn = _make_pool_mock()

    # Simulate DB error on getconn
    pool.getconn.side_effect = RuntimeError("connection refused")

    with patch("app.services.maximo_tools.telemetry.logger") as mock_logger:
        # Must NOT raise
        await record_tool_call(record, db_pool=pool)

        mock_logger.exception.assert_called_once()
        call_kwargs = mock_logger.exception.call_args
        assert "telemetry write failed" in call_kwargs[0][0]
        # PII extra fields must be passed to logger so structured logs carry context
        assert call_kwargs.kwargs["extra"]["query_id"] == str(record.query_id)
        assert call_kwargs.kwargs["extra"]["tool_name"] == record.tool_name

    c = get_counters()
    assert c["failed"] == 1
    assert c["timeout"] == 0


# ---------------------------------------------------------------------------
# Test 3 — Timeout: slow _sync_insert triggers asyncio.TimeoutError;
#           function must not raise; timeout counter increments
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_tool_call_timeout():
    reset_counters()
    record = _make_record()
    pool, _ = _make_pool_mock()

    # asyncio.to_thread(fn, *args) — side_effect receives (fn, rec, pool)
    async def slow_to_thread(*args, **kwargs):
        await asyncio.sleep(0.5)  # longer than 200ms timeout

    with (
        patch(
            "app.services.maximo_tools.telemetry.asyncio.to_thread",
            side_effect=slow_to_thread,
        ),
        patch("app.services.maximo_tools.telemetry.logger") as mock_logger,
    ):
        # Must NOT raise
        await record_tool_call(record, db_pool=pool)

        mock_logger.warning.assert_called_once()
        assert "telemetry write timeout" in mock_logger.warning.call_args[0][0]

    c = get_counters()
    assert c["timeout"] == 1
    assert c["failed"] == 0


# ---------------------------------------------------------------------------
# Test 4a — ToolCallRecord schema validation: invalid route_path
# ---------------------------------------------------------------------------

def test_tool_call_record_invalid_route_path():
    with pytest.raises(ValidationError) as exc_info:
        ToolCallRecord(
            route_path="invalid_path",  # not in Literal["tool","fallback","error"]
            latency_ms=10,
            success=True,
        )
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("route_path",) for e in errors)


# ---------------------------------------------------------------------------
# Test 4b — ToolCallRecord schema validation: invalid fallback_reason
# ---------------------------------------------------------------------------

def test_tool_call_record_invalid_fallback_reason():
    with pytest.raises(ValidationError) as exc_info:
        ToolCallRecord(
            route_path="fallback",
            latency_ms=10,
            success=False,
            fallback_reason="made_up_reason",  # not in the Literal union
        )
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("fallback_reason",) for e in errors)


# ---------------------------------------------------------------------------
# Test 5 — ToolCallRecord is frozen (immutable)
# ---------------------------------------------------------------------------

def test_tool_call_record_frozen():
    record = _make_record()
    with pytest.raises(Exception):  # pydantic raises ValidationError or TypeError
        record.tool_name = "mutated"


# ---------------------------------------------------------------------------
# Additional: fallback route_path, None db_pool path (psycopg2 direct connect)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_tool_call_raises_type_error_when_no_pool():
    """record_tool_call must raise TypeError immediately when db_pool is None."""
    reset_counters()
    record = _make_record(
        route_path="fallback",
        tool_name=None,
        success=False,
        row_count=None,
        fallback_reason="no_tool_selected",
    )

    with pytest.raises(TypeError, match="db_pool"):
        await record_tool_call(record, db_pool=None)

    # Counters must be untouched — TypeError is not a telemetry failure
    c = get_counters()
    assert c["timeout"] == 0
    assert c["failed"] == 0


def test_sync_insert_no_pool_raises_attribute_error():
    """_sync_insert with None pool raises AttributeError — no-pool fallback is removed."""
    from app.services.maximo_tools.telemetry import _sync_insert

    record = _make_record()
    with pytest.raises(AttributeError):
        _sync_insert(record, None)
