"""System settings service — read/write from DB, cache in memory."""
import logging
from typing import Optional
from sqlalchemy import text
from app.db.session import get_db_context

log = logging.getLogger(__name__)

_cache: dict[str, str] = {}
_loaded = False


async def load_settings():
    """Load all settings from DB into memory cache."""
    global _cache, _loaded
    try:
        async with get_db_context() as session:
            result = await session.execute(text("SELECT key, value FROM system_settings"))
            _cache = {r[0]: r[1] for r in result.fetchall()}
            _loaded = True
    except Exception as e:
        log.warning("Failed to load settings from DB: %s", e)


async def get_setting(key: str, default: str = "") -> str:
    if not _loaded:
        await load_settings()
    return _cache.get(key, default)


async def set_setting(key: str, value: str):
    global _cache
    try:
        async with get_db_context() as session:
            await session.execute(
                text(
                    "INSERT INTO system_settings (key, value, updated_at) "
                    "VALUES (:k, :v, NOW()) "
                    "ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = NOW()"
                ),
                {"k": key, "v": value},
            )
        _cache[key] = value
    except Exception as e:
        log.error("Failed to save setting %s: %s", key, e)


async def get_all_settings() -> dict[str, str]:
    if not _loaded:
        await load_settings()
    return dict(_cache)
