"""
Integration tests for POST /api/maximo/nl2sql with MaximoQueryRouter wired in.

These tests use FastAPI TestClient with mocked Anthropic API and DB.
Set SKIP_INTEGRATION=1 to skip all tests in this file.

Cases:
  1. LLM returns tool_use (get_vehicle_info) → route_path=tool
  2. LLM returns end_turn (no tool) → route_path=fallback
  3. Feature flag MAXIMO_TOOL_ROUTER_ENABLED=false → pure legacy response
  4. Non-admin role → no debug key in response
"""
from __future__ import annotations

import os
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Skip guard
# ---------------------------------------------------------------------------
_SKIP = os.getenv("SKIP_INTEGRATION", "").strip() not in ("", "0")
_SKIP_REASON = "SKIP_INTEGRATION is set"

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_anthropic_tool_use_response():
    """Anthropic response that selects get_vehicle_info."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = "get_vehicle_info"
    block.input = {"asset_num": "A12345"}

    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [block]
    return response


@pytest.fixture
def mock_anthropic_end_turn_response():
    """Anthropic response with no tool selected."""
    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = []
    return response


@pytest.fixture
def mock_tool_result():
    from app.services.maximo_tools.base import ToolResult
    return ToolResult(
        success=True,
        rows=[{
            "車號": "A12345",
            "車種": "EMU",
            "車型": "EMU900",
            "大分類": "動力車",
            "大分類代碼": "RSTL",
            "狀態": "運轉中",
            "狀態代碼": "OPERATING",
            "資產類型": "VEHICLE",
            "站點": "TRATW",
        }],
        row_count=1,
        elapsed_ms=50,
    )


@pytest.fixture
def mock_nl2sql_result():
    return {
        "success": True,
        "sql": "SELECT * FROM maximo_assets WHERE assetnum = 'X'",
        "explanation": "查詢車輛",
        "data": [{"assetnum": "X", "status": "OPERATING"}],
        "columns": ["assetnum", "status"],
        "row_count": 1,
        "execution_ms": 500.0,
        "llm_ms": 300.0,
        "verify_ms": None,
        "model": "test-model",
        "error": None,
        "iterations": 1,
        "confidence": 0.95,
        "verification_history": [],
        "mode": "accurate",
        "cached": False,
        "query_plan": None,
        "chart_suggestion": None,
        "summary": None,
        "clarification": None,
        "suggestions": [],
        "column_labels": None,
    }


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def _make_app(auth_user: dict):
    """FastAPI app with dependency_overrides for auth and db."""
    from fastapi import FastAPI
    from app.routers.maximo import router as maximo_router
    from app.auth import require_auth
    from app.db.session import get_db

    app = FastAPI()
    app.include_router(maximo_router, prefix="/api")

    # Override auth dep
    async def override_auth():
        return auth_user

    # Override DB dep with a no-op async session mock
    async def override_db():
        yield MagicMock()

    app.dependency_overrides[require_auth] = override_auth
    app.dependency_overrides[get_db] = override_db
    return app


def _reset_singletons():
    import app.services.maximo_tools.router_factory as rf
    rf._initialized = False
    rf._registry = None
    rf._llm_caller = None
    rf._circuit_breaker = None
    rf._psycopg2_pool = None


def _admin_user():
    return {"id": "test-admin-001", "email": "admin@test.com", "role": "admin"}


def _viewer_user():
    return {"id": "test-viewer-001", "email": "viewer@test.com", "role": "viewer"}


# ---------------------------------------------------------------------------
# Case 1: LLM selects tool → route_path=tool
# ---------------------------------------------------------------------------

@pytest.mark.skipif(_SKIP, reason=_SKIP_REASON)
@pytest.mark.asyncio
async def test_route_path_tool_when_llm_selects_tool(
    mock_anthropic_tool_use_response,
    mock_tool_result,
):
    """When Anthropic responds tool_use for get_vehicle_info, route_path=tool."""
    from httpx import AsyncClient, ASGITransport

    _reset_singletons()

    app = _make_app(_admin_user())

    fake_llm_callable = AsyncMock(return_value=mock_anthropic_tool_use_response)

    def fake_ensure():
        import app.services.maximo_tools.router_factory as rf
        from app.services.maximo_tools.registry import ToolRegistry
        from app.services.circuit_breaker import get_breaker
        rf._psycopg2_pool = None
        rf._registry = ToolRegistry()
        rf._llm_caller = fake_llm_callable
        rf._circuit_breaker = get_breaker("anthropic")
        rf._initialized = True

    with (
        patch("app.services.maximo_tools.feature_flag.is_tool_router_enabled", return_value=True),
        patch("app.services.maximo_tools.router_factory._ensure_singletons", side_effect=fake_ensure),
        patch(
            "app.services.maximo_tools.tools.get_vehicle_info.GetVehicleInfoTool.execute",
            new=AsyncMock(return_value=mock_tool_result),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/maximo/nl2sql",
                json={"question": "查 A12345 的基本資料"},
            )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["route_path"] == "tool"
    assert body["tool_name"] == "get_vehicle_info"
    assert body["row_count"] == 1
    assert body["rows"][0]["車號"] == "A12345"
    # Admin sees debug
    assert "debug" in body
    # Backward compat fields
    assert "data" in body
    assert "success" in body


# ---------------------------------------------------------------------------
# Case 2: LLM end_turn → route_path=fallback
# ---------------------------------------------------------------------------

@pytest.mark.skipif(_SKIP, reason=_SKIP_REASON)
@pytest.mark.asyncio
async def test_route_path_fallback_when_no_tool_selected(
    mock_anthropic_end_turn_response,
    mock_nl2sql_result,
):
    """When LLM returns end_turn, router falls back to NL2SQL service."""
    from httpx import AsyncClient, ASGITransport

    _reset_singletons()

    app = _make_app(_admin_user())

    fake_llm_callable = AsyncMock(return_value=mock_anthropic_end_turn_response)

    def fake_ensure():
        import app.services.maximo_tools.router_factory as rf
        from app.services.maximo_tools.registry import ToolRegistry
        from app.services.circuit_breaker import get_breaker
        rf._psycopg2_pool = None
        rf._registry = ToolRegistry()
        rf._llm_caller = fake_llm_callable
        rf._circuit_breaker = get_breaker("anthropic")
        rf._initialized = True

    with (
        patch("app.services.maximo_tools.feature_flag.is_tool_router_enabled", return_value=True),
        patch("app.services.maximo_tools.router_factory._ensure_singletons", side_effect=fake_ensure),
        patch(
            "app.services.maximo_nl2sql.MaximoNL2SQL.query",
            new=AsyncMock(return_value=mock_nl2sql_result),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/maximo/nl2sql",
                json={"question": "some complex long tail query that no tool covers"},
            )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["route_path"] == "fallback"
    assert body["tool_name"] is None
    # Backward compat: old fields
    assert body["data"] == mock_nl2sql_result["data"]
    assert body["columns"] == mock_nl2sql_result["columns"]
    assert body["success"] is True
    assert body["sql"] == mock_nl2sql_result["sql"]


# ---------------------------------------------------------------------------
# Case 3: Feature flag disabled → pure legacy (no route_path)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(_SKIP, reason=_SKIP_REASON)
@pytest.mark.asyncio
async def test_feature_flag_disabled_uses_legacy_nl2sql(mock_nl2sql_result):
    """MAXIMO_TOOL_ROUTER_ENABLED=false → all queries use legacy NL2SQL."""
    from httpx import AsyncClient, ASGITransport

    app = _make_app(_viewer_user())

    with (
        patch("app.services.maximo_tools.feature_flag.is_tool_router_enabled", return_value=False),
        patch(
            "app.services.maximo_nl2sql.MaximoNL2SQL.query",
            new=AsyncMock(return_value=mock_nl2sql_result),
        ),
        patch("app.services.intent_router.detect_ambiguity", return_value=None),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/maximo/nl2sql",
                json={"question": "test query"},
            )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Legacy response: no route_path field
    assert "route_path" not in body
    assert body["success"] is True
    assert body["data"] == mock_nl2sql_result["data"]
    assert body["columns"] == mock_nl2sql_result["columns"]
    assert body["sql"] == mock_nl2sql_result["sql"]
    assert body["row_count"] == 1


# ---------------------------------------------------------------------------
# Case 4: Non-admin viewer role → no debug key
# ---------------------------------------------------------------------------

@pytest.mark.skipif(_SKIP, reason=_SKIP_REASON)
@pytest.mark.asyncio
async def test_non_admin_response_has_no_debug(
    mock_anthropic_end_turn_response,
    mock_nl2sql_result,
):
    """Non-admin/analyst roles should NOT receive debug key in response."""
    from httpx import AsyncClient, ASGITransport

    _reset_singletons()

    app = _make_app(_viewer_user())

    fake_llm_callable = AsyncMock(return_value=mock_anthropic_end_turn_response)

    def fake_ensure():
        import app.services.maximo_tools.router_factory as rf
        from app.services.maximo_tools.registry import ToolRegistry
        from app.services.circuit_breaker import get_breaker
        rf._psycopg2_pool = None
        rf._registry = ToolRegistry()
        rf._llm_caller = fake_llm_callable
        rf._circuit_breaker = get_breaker("anthropic")
        rf._initialized = True

    with (
        patch("app.services.maximo_tools.feature_flag.is_tool_router_enabled", return_value=True),
        patch("app.services.maximo_tools.router_factory._ensure_singletons", side_effect=fake_ensure),
        patch(
            "app.services.maximo_nl2sql.MaximoNL2SQL.query",
            new=AsyncMock(return_value=mock_nl2sql_result),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/maximo/nl2sql",
                json={"question": "查詢"},
            )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "debug" not in body, f"Viewer should not see debug, got keys: {list(body.keys())}"
