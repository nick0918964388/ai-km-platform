"""
Unit tests for backend/app/services/maximo_tools/router.py

All 12 acceptance criteria covered.
No real LLM / DB calls — all injected dependencies are mocked.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.services.maximo_tools.base import (
    RouterDecision,
    ToolDefinition,
    ToolResult,
    UserContext,
)
from app.services.maximo_tools.router import MaximoQueryRouter, _safe_error_message


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

def _make_user_ctx(**overrides) -> UserContext:
    defaults = dict(user_id="u-001", role="admin")
    defaults.update(overrides)
    return UserContext(**defaults)


def _make_registry(tool_name: str = "get_vehicle_info", tool: object | None = None):
    """Return a mock ToolRegistry with one registered tool."""
    mock_tool = tool or _make_mock_tool(tool_name)
    registry = MagicMock()
    registry.get.side_effect = lambda name: mock_tool if name == tool_name else None
    registry.list_definitions.return_value = [
        ToolDefinition(
            name=tool_name,
            description="查詢車輛資訊",
            input_schema={"type": "object", "properties": {"asset_num": {"type": "string"}}},
        )
    ]
    return registry


def _make_mock_tool(name: str = "get_vehicle_info") -> MagicMock:
    """Return a mock Tool whose execute() returns a simple ToolResult."""
    tool = MagicMock()
    tool.definition = ToolDefinition(
        name=name,
        description="查詢車輛資訊",
        input_schema={"type": "object", "properties": {"asset_num": {"type": "string"}}},
    )
    tool.execute = AsyncMock(return_value=ToolResult(
        success=True,
        rows=[{"asset_num": "A12345", "status": "運行中"}],
        row_count=1,
    ))
    return tool


def _make_llm_response(
    stop_reason: str = "tool_use",
    tool_name: str = "get_vehicle_info",
    tool_input: dict | None = None,
    num_tool_use_blocks: int = 1,
) -> MagicMock:
    """Assemble a mock AnthropicResponse object."""
    response = MagicMock()
    response.stop_reason = stop_reason

    blocks = []
    for _ in range(num_tool_use_blocks):
        block = MagicMock()
        block.type = "tool_use"
        block.name = tool_name
        block.input = tool_input if tool_input is not None else {"asset_num": "A12345"}
        blocks.append(block)

    if stop_reason != "tool_use":
        # For end_turn etc., add a text block only (no tool_use blocks)
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "NO_TOOL"
        response.content = [text_block]
    else:
        response.content = blocks

    return response


def _make_fallback_result(rows=None, row_count=None) -> dict:
    rows = rows or [{"sql_result": "some data"}]
    return {
        "rows": rows,
        "row_count": row_count if row_count is not None else len(rows),
        "chart_hint": None,
        "debug": {"sql": "SELECT ...", "fallback_reason": "no_tool_selected"},
    }


def _make_router(
    *,
    tool_name: str = "get_vehicle_info",
    tool: object | None = None,
    llm_response: MagicMock | None = None,
    fallback_result: dict | None = None,
    circuit_breaker=None,
    db_pool=None,
    llm_call: object | None = None,
) -> tuple[MaximoQueryRouter, AsyncMock, AsyncMock]:
    """
    Build a MaximoQueryRouter with fully mocked dependencies.
    Returns (router, mock_llm_call, mock_fallback_fn).
    """
    registry = _make_registry(tool_name=tool_name, tool=tool)

    if llm_call is None:
        mock_llm = AsyncMock(return_value=llm_response or _make_llm_response())
    else:
        mock_llm = llm_call

    fb_result = fallback_result or _make_fallback_result()
    mock_fallback = AsyncMock(return_value=fb_result)

    router = MaximoQueryRouter(
        registry=registry,
        llm_call=mock_llm,
        fallback_fn=mock_fallback,
        circuit_breaker=circuit_breaker,
        db_pool=db_pool,
    )
    return router, mock_llm, mock_fallback


# ---------------------------------------------------------------------------
# Test 1 — Happy path tool_use
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_happy_path_tool_use():
    """LLM 回 tool_use + 1 block → tool.execute 被呼叫 → route_path=tool + rows."""
    llm_resp = _make_llm_response(stop_reason="tool_use", tool_name="get_vehicle_info",
                                   tool_input={"asset_num": "A12345"})
    router, mock_llm, mock_fallback = _make_router(llm_response=llm_resp)
    ctx = _make_user_ctx()

    with patch.dict("os.environ", {"MAXIMO_TOOL_ROUTER_ENABLED": "true"}):
        result = await router.route("查詢 A12345 的車輛資料", ctx)

    assert result["route_path"] == "tool"
    assert result["tool_name"] == "get_vehicle_info"
    assert result["tool_input"] == {"asset_num": "A12345"}
    assert result["rows"] == [{"asset_num": "A12345", "status": "運行中"}]
    assert result["row_count"] == 1
    assert UUID(result["query_id"])  # valid UUID
    assert result["elapsed_ms"] >= 0
    mock_llm.assert_awaited_once()
    mock_fallback.assert_not_awaited()

    # tool.execute must have been called with the extracted params
    # Use the registry mock directly (avoid accessing private _registry attribute)
    mock_tool = router._registry.get("get_vehicle_info")
    mock_tool.execute.assert_awaited_once_with({"asset_num": "A12345"}, ctx)


# ---------------------------------------------------------------------------
# Test 2 — Happy path fallback (end_turn)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_happy_path_fallback_end_turn():
    """LLM stop_reason=end_turn → fallback_fn 被呼叫 with 原始 query → route_path=fallback."""
    original_query = "最近一季的故障分布"
    llm_resp = _make_llm_response(stop_reason="end_turn")
    router, mock_llm, mock_fallback = _make_router(llm_response=llm_resp)
    ctx = _make_user_ctx()

    with patch.dict("os.environ", {"MAXIMO_TOOL_ROUTER_ENABLED": "true"}):
        result = await router.route(original_query, ctx)

    assert result["route_path"] == "fallback"
    assert result["debug"].get("fallback_reason") == "no_tool_selected"
    mock_llm.assert_awaited_once()

    # Verify fallback_fn received the ORIGINAL query
    mock_fallback.assert_awaited_once()
    call_args = mock_fallback.call_args
    assert call_args[0][0] == original_query  # positional arg 0 = query


# ---------------------------------------------------------------------------
# Test 3 — Feature flag off
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_feature_flag_disabled():
    """MAXIMO_TOOL_ROUTER_ENABLED=false → LLM 不被呼叫 → fallback + reason=feature_flag_disabled."""
    router, mock_llm, mock_fallback = _make_router()
    ctx = _make_user_ctx()

    with patch.dict("os.environ", {"MAXIMO_TOOL_ROUTER_ENABLED": "false"}):
        result = await router.route("查詢 A12345", ctx)

    assert result["route_path"] == "fallback"
    assert result["debug"]["fallback_reason"] == "feature_flag_disabled"
    mock_llm.assert_not_awaited()
    mock_fallback.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 4 — Circuit breaker open
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_circuit_breaker_open():
    """circuit_breaker.is_available=False → LLM 不被呼叫 → fallback + reason=llm_circuit_open."""
    cb = MagicMock()
    cb.is_available = False  # property = False means circuit is OPEN

    router, mock_llm, mock_fallback = _make_router(circuit_breaker=cb)
    ctx = _make_user_ctx()

    with patch.dict("os.environ", {"MAXIMO_TOOL_ROUTER_ENABLED": "true"}):
        result = await router.route("查詢 A12345", ctx)

    assert result["route_path"] == "fallback"
    assert result["debug"]["fallback_reason"] == "llm_circuit_open"
    mock_llm.assert_not_awaited()
    mock_fallback.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 5 — LLM timeout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_timeout():
    """llm_call sleeps > _LLM_TIMEOUT_SECONDS → fallback + reason=llm_timeout."""
    async def slow_llm(*args, **kwargs):
        await asyncio.sleep(20)  # far exceeds 10s timeout

    mock_llm = AsyncMock(side_effect=slow_llm)
    mock_fallback = AsyncMock(return_value=_make_fallback_result())
    registry = _make_registry()
    router = MaximoQueryRouter(
        registry=registry,
        llm_call=mock_llm,
        fallback_fn=mock_fallback,
        circuit_breaker=None,
        db_pool=None,
    )
    ctx = _make_user_ctx()

    with patch.dict("os.environ", {"MAXIMO_TOOL_ROUTER_ENABLED": "true"}):
        # Patch timeout to 0.05s to avoid waiting 10 real seconds in tests
        with patch("app.services.maximo_tools.router._LLM_TIMEOUT_SECONDS", 0.05):
            result = await router.route("查詢 A12345", ctx)

    assert result["route_path"] == "fallback"
    assert result["debug"]["fallback_reason"] == "llm_timeout"
    mock_fallback.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 6 — LLM raises exception
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_raises_exception():
    """llm_call raise → fallback + reason=tool_invocation_error."""
    mock_llm = AsyncMock(side_effect=RuntimeError("Anthropic API error"))
    mock_fallback = AsyncMock(return_value=_make_fallback_result())
    registry = _make_registry()
    router = MaximoQueryRouter(
        registry=registry,
        llm_call=mock_llm,
        fallback_fn=mock_fallback,
        circuit_breaker=None,
        db_pool=None,
    )
    ctx = _make_user_ctx()

    with patch.dict("os.environ", {"MAXIMO_TOOL_ROUTER_ENABLED": "true"}):
        result = await router.route("查詢 A12345", ctx)

    assert result["route_path"] == "fallback"
    assert result["debug"]["fallback_reason"] == "tool_invocation_error"
    mock_fallback.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 7 — Multiple tool_use blocks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multiple_tool_use_blocks():
    """LLM 回 2 個 tool_use blocks → fallback + reason=tool_invocation_error."""
    llm_resp = _make_llm_response(stop_reason="tool_use", num_tool_use_blocks=2)
    router, mock_llm, mock_fallback = _make_router(llm_response=llm_resp)
    ctx = _make_user_ctx()

    with patch.dict("os.environ", {"MAXIMO_TOOL_ROUTER_ENABLED": "true"}):
        result = await router.route("查詢 A12345 的工單與故障", ctx)

    assert result["route_path"] == "fallback"
    assert result["debug"]["fallback_reason"] == "tool_invocation_error"
    mock_fallback.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 8 — Tool name not in registry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_name_not_in_registry():
    """LLM 回 tool_use name='nonexistent' → registry.get returns None → fallback + reason=tool_invocation_error."""
    llm_resp = _make_llm_response(stop_reason="tool_use", tool_name="nonexistent_tool")
    router, mock_llm, mock_fallback = _make_router(llm_response=llm_resp)
    ctx = _make_user_ctx()

    with patch.dict("os.environ", {"MAXIMO_TOOL_ROUTER_ENABLED": "true"}):
        result = await router.route("查詢 A12345", ctx)

    assert result["route_path"] == "fallback"
    assert result["debug"]["fallback_reason"] == "tool_invocation_error"
    mock_fallback.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 9 — Tool execute raises exception
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_execute_raises_exception():
    """tool.execute raise → route_path=error + reason=tool_execution_error + rows=[]."""
    failing_tool = _make_mock_tool("get_vehicle_info")
    failing_tool.execute = AsyncMock(side_effect=Exception("DB connection failed"))

    llm_resp = _make_llm_response(stop_reason="tool_use", tool_name="get_vehicle_info")
    router, mock_llm, mock_fallback = _make_router(
        tool=failing_tool, llm_response=llm_resp
    )
    ctx = _make_user_ctx()

    with patch.dict("os.environ", {"MAXIMO_TOOL_ROUTER_ENABLED": "true"}):
        result = await router.route("查詢 A12345", ctx)

    assert result["route_path"] == "error"
    assert result["rows"] == []
    assert result["row_count"] == 0
    # code = exception class name (sanitized — no raw exception text)
    assert result["debug"]["error"]["code"] == "Exception"
    # message is the safe generalized string, not the raw exception message
    assert "DB connection failed" not in result["debug"]["error"]["message"]
    assert result["debug"]["error"]["message"] == "系統執行錯誤"
    # fallback_fn must NOT be called in this error path
    mock_fallback.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test 10 — stop_reason=max_tokens
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stop_reason_max_tokens():
    """stop_reason=max_tokens → fallback + reason=tool_invocation_error."""
    llm_resp = _make_llm_response(stop_reason="max_tokens")
    router, mock_llm, mock_fallback = _make_router(llm_response=llm_resp)
    ctx = _make_user_ctx()

    with patch.dict("os.environ", {"MAXIMO_TOOL_ROUTER_ENABLED": "true"}):
        result = await router.route("查詢 A12345", ctx)

    assert result["route_path"] == "fallback"
    assert result["debug"]["fallback_reason"] == "tool_invocation_error"
    mock_fallback.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 11 — Telemetry written for each route_path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_telemetry_tool_path():
    """route_path=tool → record_tool_call called with correct params."""
    llm_resp = _make_llm_response(stop_reason="tool_use", tool_name="get_vehicle_info",
                                   tool_input={"asset_num": "A12345"})
    router, _, _ = _make_router(llm_response=llm_resp, db_pool=MagicMock())
    ctx = _make_user_ctx()

    with (
        patch.dict("os.environ", {"MAXIMO_TOOL_ROUTER_ENABLED": "true"}),
        patch("app.services.maximo_tools.router.record_tool_call", new_callable=AsyncMock) as mock_record,
    ):
        result = await router.route("查詢 A12345", ctx)

    assert result["route_path"] == "tool"
    mock_record.assert_awaited_once()
    record_arg = mock_record.call_args[0][0]
    assert record_arg.route_path == "tool"
    assert record_arg.tool_name == "get_vehicle_info"
    assert record_arg.params == {"asset_num": "A12345"}
    assert record_arg.success is True
    assert record_arg.user_id == "u-001"
    assert record_arg.fallback_reason is None


@pytest.mark.asyncio
async def test_telemetry_fallback_path():
    """route_path=fallback → record_tool_call called with correct fallback params."""
    llm_resp = _make_llm_response(stop_reason="end_turn")
    router, _, _ = _make_router(llm_response=llm_resp, db_pool=MagicMock())
    ctx = _make_user_ctx()

    with (
        patch.dict("os.environ", {"MAXIMO_TOOL_ROUTER_ENABLED": "true"}),
        patch("app.services.maximo_tools.router.record_tool_call", new_callable=AsyncMock) as mock_record,
    ):
        result = await router.route("複雜的跨工具查詢", ctx)

    assert result["route_path"] == "fallback"
    mock_record.assert_awaited_once()
    record_arg = mock_record.call_args[0][0]
    assert record_arg.route_path == "fallback"
    assert record_arg.tool_name is None
    assert record_arg.fallback_reason == "no_tool_selected"
    assert record_arg.success is True


@pytest.mark.asyncio
async def test_telemetry_error_path():
    """route_path=error (tool raises) → record_tool_call called with error params."""
    failing_tool = _make_mock_tool("get_vehicle_info")
    failing_tool.execute = AsyncMock(side_effect=Exception("oops"))

    llm_resp = _make_llm_response(stop_reason="tool_use", tool_name="get_vehicle_info")
    router, _, _ = _make_router(tool=failing_tool, llm_response=llm_resp, db_pool=MagicMock())
    ctx = _make_user_ctx()

    with (
        patch.dict("os.environ", {"MAXIMO_TOOL_ROUTER_ENABLED": "true"}),
        patch("app.services.maximo_tools.router.record_tool_call", new_callable=AsyncMock) as mock_record,
    ):
        result = await router.route("查詢 A12345", ctx)

    assert result["route_path"] == "error"
    mock_record.assert_awaited_once()
    record_arg = mock_record.call_args[0][0]
    assert record_arg.route_path == "error"
    assert record_arg.success is False
    assert record_arg.fallback_reason == "tool_execution_error"
    # error_message is sanitized — raw exception text must not be present
    assert "oops" not in (record_arg.error_message or "")
    assert record_arg.error_message == "系統執行錯誤"


@pytest.mark.asyncio
async def test_telemetry_skipped_when_no_pool():
    """db_pool=None → record_tool_call never called (no TypeError raised)."""
    llm_resp = _make_llm_response(stop_reason="tool_use", tool_name="get_vehicle_info")
    router, _, _ = _make_router(llm_response=llm_resp, db_pool=None)
    ctx = _make_user_ctx()

    with (
        patch.dict("os.environ", {"MAXIMO_TOOL_ROUTER_ENABLED": "true"}),
        patch("app.services.maximo_tools.router.record_tool_call", new_callable=AsyncMock) as mock_record,
    ):
        result = await router.route("查詢 A12345", ctx)

    assert result["route_path"] == "tool"
    mock_record.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test 12 — Fallback receives original query (not rewritten)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fallback_receives_original_query():
    """Verify fallback_fn always receives the exact original user query string."""
    original_query = "A12345 過去一個月的工單狀況？（含未結案和已完成）"
    llm_resp = _make_llm_response(stop_reason="end_turn")

    captured_queries: list[str] = []

    async def capturing_fallback(query: str, user_ctx: UserContext, query_id: UUID) -> dict:
        captured_queries.append(query)
        return _make_fallback_result()

    registry = _make_registry()
    mock_llm = AsyncMock(return_value=llm_resp)
    router = MaximoQueryRouter(
        registry=registry,
        llm_call=mock_llm,
        fallback_fn=capturing_fallback,
        circuit_breaker=None,
        db_pool=None,
    )
    ctx = _make_user_ctx()

    with patch.dict("os.environ", {"MAXIMO_TOOL_ROUTER_ENABLED": "true"}):
        await router.route(original_query, ctx)

    assert len(captured_queries) == 1
    assert captured_queries[0] == original_query


@pytest.mark.asyncio
async def test_fallback_receives_original_query_on_feature_flag_off():
    """Even when feature flag is off, fallback receives original query."""
    original_query = "系統停機時的查詢"

    captured_queries: list[str] = []

    async def capturing_fallback(query: str, user_ctx: UserContext, query_id: UUID) -> dict:
        captured_queries.append(query)
        return _make_fallback_result()

    registry = _make_registry()
    mock_llm = AsyncMock()
    router = MaximoQueryRouter(
        registry=registry,
        llm_call=mock_llm,
        fallback_fn=capturing_fallback,
        circuit_breaker=None,
        db_pool=None,
    )
    ctx = _make_user_ctx()

    with patch.dict("os.environ", {"MAXIMO_TOOL_ROUTER_ENABLED": "false"}):
        await router.route(original_query, ctx)

    assert captured_queries == [original_query]
    mock_llm.assert_not_awaited()


# ---------------------------------------------------------------------------
# Additional: circuit_breaker is_available callable (HALF_OPEN scenario)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_circuit_breaker_available_allows_llm_call():
    """circuit_breaker.is_available=True → circuit is not open → LLM is called."""
    cb = MagicMock()
    cb.is_available = True  # property = True means circuit is CLOSED/usable

    llm_resp = _make_llm_response(stop_reason="tool_use", tool_name="get_vehicle_info")
    router, mock_llm, mock_fallback = _make_router(
        circuit_breaker=cb, llm_response=llm_resp
    )
    ctx = _make_user_ctx()

    with patch.dict("os.environ", {"MAXIMO_TOOL_ROUTER_ENABLED": "true"}):
        result = await router.route("查詢 A12345", ctx)

    assert result["route_path"] == "tool"
    mock_llm.assert_awaited_once()


@pytest.mark.asyncio
async def test_circuit_breaker_none_allows_llm_call():
    """circuit_breaker=None → _is_circuit_open returns False → LLM is called."""
    llm_resp = _make_llm_response(stop_reason="tool_use", tool_name="get_vehicle_info")
    router, mock_llm, _ = _make_router(circuit_breaker=None, llm_response=llm_resp)
    ctx = _make_user_ctx()

    with patch.dict("os.environ", {"MAXIMO_TOOL_ROUTER_ENABLED": "true"}):
        result = await router.route("查詢 A12345", ctx)

    assert result["route_path"] == "tool"
    mock_llm.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test: error message sanitization (HIGH-2)
# ---------------------------------------------------------------------------

def test_safe_error_message_known_types():
    """_safe_error_message returns (class_name, safe_message) for known exception types."""

    class OperationalError(Exception):
        pass

    exc = OperationalError("host=10.0.0.1 user=aikm password=secret")
    code, msg = _safe_error_message(exc)
    assert code == "OperationalError"
    assert "host" not in msg
    assert "password" not in msg
    assert "secret" not in msg
    assert msg == "資料庫連線或操作失敗"


def test_safe_error_message_unknown_type():
    """Unknown exception type returns generic safe message."""
    exc = Exception("something internal")
    code, msg = _safe_error_message(exc)
    assert code == "Exception"
    assert "internal" not in msg
    assert msg == "系統執行錯誤"


@pytest.mark.asyncio
async def test_error_message_sanitization_operational_error():
    """
    Tool raises OperationalError with DB credentials in message.
    Response debug.error.message must NOT contain host/password/user details.
    """

    class OperationalError(Exception):
        pass

    failing_tool = _make_mock_tool("get_vehicle_info")
    failing_tool.execute = AsyncMock(
        side_effect=OperationalError("host=10.0.0.1 user=aikm password=secret port=5432")
    )

    llm_resp = _make_llm_response(stop_reason="tool_use", tool_name="get_vehicle_info")
    router, _, mock_fallback = _make_router(tool=failing_tool, llm_response=llm_resp)
    ctx = _make_user_ctx()

    with patch.dict("os.environ", {"MAXIMO_TOOL_ROUTER_ENABLED": "true"}):
        result = await router.route("查詢 A12345", ctx)

    assert result["route_path"] == "error"
    error_message = result["debug"]["error"]["message"]
    assert "host" not in error_message
    assert "password" not in error_message
    assert "secret" not in error_message
    assert "10.0.0.1" not in error_message
    assert "aikm" not in error_message
    assert error_message == "資料庫連線或操作失敗"
    mock_fallback.assert_not_awaited()
