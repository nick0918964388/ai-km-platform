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

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("DB_ECHO", "false").lower() == "true",
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

# Create async session maker
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI to get database session.
    Usage: db: AsyncSession = Depends(get_db)
    """
    async with async_session_maker() as session:
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
    async with async_session_maker() as session:
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
    
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """
    Close database connections.
    Should be called on application shutdown.
    """
    await engine.dispose()
