"""
Database session management with async support.
Uses asyncpg for PostgreSQL connections.
"""

import os
from typing import AsyncGenerator
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)

# Get database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://aikm:aikm@localhost:5432/aikm"
)

# Lazy engine — created on first access so the event loop is always the
# FastAPI worker loop, not the import-time loop.  This fixes
# "RuntimeError: Task got Future attached to a different loop" that caused
# every audit write to fail silently.
_engine = None


def get_engine():
    """Return the singleton AsyncEngine, creating it on first call.

    Lazy creation ensures the engine is bound to the running event loop
    (FastAPI worker) rather than the import-time loop.
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            DATABASE_URL,
            echo=os.getenv("DB_ECHO", "false").lower() == "true",
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
    return _engine


def __getattr__(name: str):
    """Module-level __getattr__ — makes `from app.db.session import engine`
    and `from app.db.session import async_session_maker` return lazy
    singletons without requiring callers to change their import statements.
    """
    if name == "engine":
        return get_engine()
    if name == "async_session_maker":
        return _get_session_maker()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_session_maker = None


def _get_session_maker():
    global _session_maker
    if _session_maker is None:
        _session_maker = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_maker


# Backward-compat name — callers that do
# `from app.db.session import async_session_maker` get a lazy proxy
# by virtue of module __getattr__ below.
# Direct usage (async_session_maker()) inside this module is via
# _get_session_maker() to avoid circular issues.


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI to get database session.
    Usage: db: AsyncSession = Depends(get_db)
    """
    async with _get_session_maker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for getting database session outside of FastAPI.
    Usage: async with get_db_context() as db: ...
    """
    async with _get_session_maker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """
    Initialize database tables.
    Should be called on application startup.
    """
    from . import Base

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """
    Close database connections.
    Should be called on application shutdown.
    """
    await get_engine().dispose()
