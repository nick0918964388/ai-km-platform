"""Lazy singleton AsyncEngine for the pg_viewer read-only connection pool.

Security layers for statement_timeout (three-layer defence-in-depth):
  Layer 1 — Role-level: `ALTER ROLE aikm_viewer SET statement_timeout = '10s'`
             Applied by migration 001. Not this module's responsibility.
  Layer 2 — asyncpg command_timeout=10 (connect_args).  Applied here in
             pool config — kills the TCP socket after 10 s at the driver level.
  Layer 3 — Per-transaction: `SET LOCAL statement_timeout = '10s'` executed
             inside every engine.begin() block (get_viewer_db dep). Applied here.

Pool is intentionally separate from the main app engine (db/session.py) so the
viewer's 10-connection cap does not affect application workloads.

SQLAlchemy + asyncpg imports are deferred to function bodies so the module is
importable in environments where those packages are not installed (e.g. running
unit tests on the dev machine without a full Docker environment).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator

from fastapi import HTTPException

if TYPE_CHECKING:
    # Only for type checkers — not executed at runtime.
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

# Module-level singleton — None until first call to _get_engine().
_engine: "AsyncEngine | None" = None


def _get_engine() -> "AsyncEngine":
    """Return the singleton AsyncEngine, creating it on first call.

    Raises:
        HTTPException(503): if PG_VIEWER_DATABASE_URL is empty/unset.
    """
    global _engine
    if _engine is not None:
        return _engine

    # Deferred imports — avoids import errors when sqlalchemy is not installed
    # (unit-test environments on dev machines without full deps).
    from sqlalchemy.ext.asyncio import create_async_engine  # noqa: PLC0415

    # Deferred import — avoids circular deps and keeps module importable before
    # the settings cache is warmed.
    from app.config import get_settings  # noqa: PLC0415

    settings = get_settings()
    url: str = settings.pg_viewer_database_url

    if not url:
        raise HTTPException(
            status_code=503,
            detail="pg_viewer not configured",
        )

    # Ensure the URL uses the asyncpg driver dialect.
    # Operators may set PG_VIEWER_DATABASE_URL as a plain postgresql:// URL.
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)

    _engine = create_async_engine(
        url,
        # --- Pool config (critic C3 + H2 ops) ---
        pool_size=3,
        max_overflow=7,
        pool_pre_ping=True,
        pool_recycle=1800,
        # Layer 2 timeout: asyncpg cancels any statement after 10 s at the
        # network/protocol level, independently of Postgres server config.
        connect_args={"command_timeout": 10},
        echo=False,
    )
    return _engine


async def get_viewer_db() -> AsyncGenerator["AsyncConnection", None]:
    """FastAPI dependency — yields one AsyncConnection per request.

    The connection is always inside an explicit transaction (engine.begin()).
    AUTOCOMMIT is never set.  Layer 3 statement_timeout is applied at the start
    of every transaction so it cannot be bypassed by role-level GUC resets.

    Usage::

        @router.get("/example")
        async def example(conn: AsyncConnection = Depends(get_viewer_db)):
            result = await conn.execute(text("SELECT 1"))
            return result.scalar()
    """
    from sqlalchemy import text  # noqa: PLC0415 — deferred for unit-test compat

    engine = _get_engine()
    async with engine.begin() as conn:
        # Layer 3: per-transaction timeout.  SET LOCAL is transaction-scoped and
        # survives even if the caller's role does not have statement_timeout set.
        await conn.execute(text("SET LOCAL statement_timeout = '10s'"))
        yield conn
