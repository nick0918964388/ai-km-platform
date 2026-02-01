"""
Database module for AI KM Platform.
Contains database engine, session management, and base model.
"""

from sqlalchemy.orm import declarative_base

# Create declarative base for all models
Base = declarative_base()

from .session import (
    engine,
    async_session_maker,
    get_db,
    init_db,
)

__all__ = [
    "Base",
    "engine",
    "async_session_maker",
    "get_db",
    "init_db",
]
