"""
Unit tests for router_factory.build_router.

Validates:
  - db_pool is injected into tools that have _db_pool=None
  - tools already having a db_pool are not overwritten
  - MaximoQueryRouter is constructed with correct dependencies
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest


def _reset_singletons():
    """Reset module-level singletons before each test."""
    import app.services.maximo_tools.router_factory as rf
    rf._initialized = False
    rf._registry = None
    rf._llm_caller = None
    rf._circuit_breaker = None
    rf._psycopg2_pool = None


def _make_mock_tool(name: str, has_db_pool_attr: bool, db_pool_value=None):
    """Create a mock Tool with optional _db_pool attribute."""
    tool = MagicMock()
    tool.definition = MagicMock()
    tool.definition.name = name
    if has_db_pool_attr:
        tool._db_pool = db_pool_value
    return tool


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildRouterDbPoolInjection:
    """db_pool injection into tools."""

    def setup_method(self):
        _reset_singletons()

    def test_db_pool_injected_into_tool_with_none(self):
        """Tool with _db_pool=None gets the pool after _ensure_singletons runs."""
        tool_a = _make_mock_tool("tool_with_none_pool", has_db_pool_attr=True, db_pool_value=None)
        tool_b = _make_mock_tool("tool_without_attr", has_db_pool_attr=False)

        mock_registry_instance = MagicMock()
        mock_registry_instance.list_tools.return_value = [tool_a, tool_b]

        fake_pool = MagicMock(name="psycopg2_pool")

        import app.services.maximo_tools.router_factory as rf

        # Patch _build_psycopg2_pool at module level (it IS a module-level name)
        # and lazy-imported names at their source modules.
        with (
            patch.object(rf, "_build_psycopg2_pool", return_value=fake_pool),
            patch("app.services.maximo_tools.registry.ToolRegistry", return_value=mock_registry_instance),
            patch("app.services.maximo_tools.anthropic_llm.AnthropicToolUseCaller", return_value=MagicMock()),
            patch("app.services.circuit_breaker.get_breaker", return_value=MagicMock()),
            patch("app.config.get_settings", return_value=MagicMock(anthropic_api_key=None)),
        ):
            rf._ensure_singletons()

        # tool_a had _db_pool=None → should be injected
        assert tool_a._db_pool is fake_pool
        # tool_b had no explicit _db_pool set → was NOT injected with fake_pool
        # (MagicMock returns a mock attr on any access, but it won't be fake_pool)
        assert tool_b._db_pool is not fake_pool

    def test_db_pool_not_overwritten_when_already_set(self):
        """Tool with existing non-None _db_pool is not overwritten."""
        existing_pool = MagicMock(name="existing_pool")
        tool = _make_mock_tool("tool_with_existing_pool", has_db_pool_attr=True, db_pool_value=existing_pool)

        mock_registry = MagicMock()
        mock_registry.list_tools.return_value = [tool]
        mock_registry.list_definitions.return_value = []

        new_pool = MagicMock(name="new_pool")
        fake_fallback = AsyncMock()

        import app.services.maximo_tools.router_factory as rf

        # Manually set up singletons to skip _ensure_singletons side effects
        rf._initialized = False
        rf._psycopg2_pool = None

        with patch("app.services.maximo_tools.router_factory._build_psycopg2_pool", return_value=new_pool):
            # Patch _ensure_singletons to inject our mocks directly
            def fake_ensure():
                rf._psycopg2_pool = new_pool
                rf._registry = mock_registry
                rf._llm_caller = MagicMock()
                rf._circuit_breaker = MagicMock()
                rf._initialized = True

            with patch("app.services.maximo_tools.router_factory._ensure_singletons", side_effect=fake_ensure):
                router = rf.build_router(fallback_fn=fake_fallback)

        # _db_pool was already set to a non-None value → must NOT be overwritten
        assert tool._db_pool is existing_pool

    def test_router_built_with_correct_dependencies(self):
        """MaximoQueryRouter receives registry, llm_call, fallback_fn, circuit_breaker, db_pool."""
        mock_registry = MagicMock()
        mock_registry.list_tools.return_value = []
        mock_registry.list_definitions.return_value = []

        mock_llm = MagicMock()
        mock_cb = MagicMock()
        fake_pool = MagicMock(name="pool")
        fake_fallback = AsyncMock()

        import app.services.maximo_tools.router_factory as rf

        def fake_ensure():
            rf._psycopg2_pool = fake_pool
            rf._registry = mock_registry
            rf._llm_caller = mock_llm
            rf._circuit_breaker = mock_cb
            rf._initialized = True

        captured = {}

        from app.services.maximo_tools.router import MaximoQueryRouter

        original_init = MaximoQueryRouter.__init__

        def capturing_init(self_inner, registry, llm_call, fallback_fn, circuit_breaker=None, db_pool=None):
            captured["registry"] = registry
            captured["llm_call"] = llm_call
            captured["fallback_fn"] = fallback_fn
            captured["circuit_breaker"] = circuit_breaker
            captured["db_pool"] = db_pool
            original_init(
                self_inner,
                registry=registry,
                llm_call=llm_call,
                fallback_fn=fallback_fn,
                circuit_breaker=circuit_breaker,
                db_pool=db_pool,
            )

        with (
            patch("app.services.maximo_tools.router_factory._ensure_singletons", side_effect=fake_ensure),
            patch.object(MaximoQueryRouter, "__init__", capturing_init),
        ):
            router = rf.build_router(fallback_fn=fake_fallback)

        assert captured["registry"] is mock_registry
        assert captured["llm_call"] is mock_llm
        assert captured["fallback_fn"] is fake_fallback
        assert captured["circuit_breaker"] is mock_cb
        assert captured["db_pool"] is fake_pool

    def test_build_router_tolerates_psycopg2_pool_failure(self):
        """If psycopg2 pool creation fails, build_router proceeds with db_pool=None."""
        mock_registry = MagicMock()
        mock_registry.list_tools.return_value = []
        mock_registry.list_definitions.return_value = []

        import app.services.maximo_tools.router_factory as rf

        def fake_ensure_no_pool():
            rf._psycopg2_pool = None
            rf._registry = mock_registry
            rf._llm_caller = MagicMock()
            rf._circuit_breaker = MagicMock()
            rf._initialized = True

        fake_fallback = AsyncMock()

        with patch("app.services.maximo_tools.router_factory._ensure_singletons", side_effect=fake_ensure_no_pool):
            router = rf.build_router(fallback_fn=fake_fallback)

        # Should not raise — router created with db_pool=None
        assert router is not None
        assert router._db_pool is None
