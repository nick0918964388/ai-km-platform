"""Build MaximoQueryRouter with app-level singletons injected."""
from __future__ import annotations

import logging
import os
from typing import Callable, Awaitable, Any

logger = logging.getLogger(__name__)

# Module-level singletons (one per worker process)
_registry = None
_llm_caller = None
_circuit_breaker = None
_psycopg2_pool = None
_initialized = False


def _build_psycopg2_pool():
    """
    Create a psycopg2 ThreadedConnectionPool for sync tool queries.

    Uses DATABASE_URL env var, stripping the asyncpg driver prefix so
    psycopg2 can parse it.
    """
    try:
        import psycopg2.pool as pg2pool

        raw_url = os.getenv(
            "DATABASE_URL",
            "postgresql://aikm:aikm@localhost:5432/aikm",
        )
        dsn = (
            raw_url
            .replace("postgresql+asyncpg://", "postgresql://")
            .replace("postgresql+psycopg2://", "postgresql://")
        )

        pool = pg2pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=5,
            dsn=dsn,
            connect_timeout=5,
        )
        logger.info("psycopg2 ThreadedConnectionPool created (minconn=1, maxconn=5)")
        return pool
    except Exception:
        logger.exception(
            "Failed to create psycopg2 pool; tool db_pool will be None "
            "(GetVehicleInfoTool will raise RuntimeError on execute)"
        )
        return None


def _ensure_singletons() -> None:
    """
    Lazy-init module-level singletons on first call.
    Idempotent — safe to call multiple times (CPython GIL protects assignment).
    """
    global _registry, _llm_caller, _circuit_breaker, _psycopg2_pool, _initialized

    if _initialized:
        return

    from app.services.maximo_tools.anthropic_llm import AnthropicToolUseCaller
    from app.services.maximo_tools.registry import ToolRegistry
    from app.services.circuit_breaker import get_breaker
    from app.config import get_settings

    # psycopg2 pool (used by tools for sync SQL + by telemetry)
    _psycopg2_pool = _build_psycopg2_pool()

    # Tool registry with auto-discovery
    _registry = ToolRegistry()

    # Inject psycopg2 pool into tools that declare _db_pool = None
    if _psycopg2_pool is not None:
        for tool in _registry.list_tools():
            if hasattr(tool, "_db_pool") and getattr(tool, "_db_pool", None) is None:
                tool._db_pool = _psycopg2_pool
                logger.info("Injected db_pool into tool: %s", tool.definition.name)

    # Anthropic LLM caller
    settings = get_settings()
    api_key = getattr(settings, "anthropic_api_key", None) or None
    _llm_caller = AnthropicToolUseCaller(api_key=api_key)

    # Circuit breaker for Anthropic (auto-created if not present)
    _circuit_breaker = get_breaker("anthropic", failure_threshold=3, recovery_timeout=60.0)

    _initialized = True
    logger.info("MaximoQueryRouter singletons initialized")


def build_router(fallback_fn: Callable[..., Awaitable[Any]]):
    """
    Build a MaximoQueryRouter for a single request.

    Singletons (registry, llm_caller, circuit_breaker, db_pool) are shared
    across requests. Only the fallback_fn is request-scoped (it captures
    the per-request AsyncSession).

    Args:
        fallback_fn: async callable with signature
            (query: str, user_ctx: UserContext, query_id: UUID) -> dict

    Returns:
        MaximoQueryRouter ready for use within this request.
    """
    _ensure_singletons()

    from app.services.maximo_tools.router import MaximoQueryRouter

    return MaximoQueryRouter(
        registry=_registry,
        llm_call=_llm_caller,
        fallback_fn=fallback_fn,
        circuit_breaker=_circuit_breaker,
        db_pool=_psycopg2_pool,
    )


def get_psycopg2_pool():
    """Expose the psycopg2 pool for tests / health checks."""
    _ensure_singletons()
    return _psycopg2_pool
