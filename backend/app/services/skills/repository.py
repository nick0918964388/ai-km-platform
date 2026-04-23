"""DB CRUD for Skills."""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


async def create_skill(db: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    """Insert a new skill (version=1, is_current=True). Returns the created row."""
    result = await db.execute(
        text("""
            INSERT INTO skills (name, description, triggers, sql_template,
                                params_schema, security, stats, active)
            VALUES (:name, :description, :triggers, :sql_template,
                    :params_schema::jsonb, :security::jsonb, :stats::jsonb, :active)
            RETURNING id, name, version, is_current, description, triggers,
                      sql_template, params_schema, security, stats, active
        """),
        {
            "name": data["name"],
            "description": data.get("description"),
            "triggers": data.get("triggers", []),
            "sql_template": data.get("sql_template"),
            "params_schema": _jsonb(data.get("params_schema", {})),
            "security": _jsonb(data.get("security", {})),
            "stats": _jsonb(data.get("stats", {})),
            "active": data.get("active", False),
        },
    )
    await db.commit()
    row = result.fetchone()
    return _row_to_dict(row)


async def get_skill_by_id(db: AsyncSession, skill_id: UUID) -> Optional[dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT id, name, version, is_current, description, triggers,
                   sql_template, params_schema, security, stats, active
            FROM skills WHERE id = :id
        """),
        {"id": str(skill_id)},
    )
    row = result.fetchone()
    return _row_to_dict(row) if row else None


async def get_current_skill_by_name(db: AsyncSession, name: str) -> Optional[dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT id, name, version, is_current, description, triggers,
                   sql_template, params_schema, security, stats, active
            FROM skills
            WHERE name = :name AND is_current = TRUE
            LIMIT 1
        """),
        {"name": name},
    )
    row = result.fetchone()
    return _row_to_dict(row) if row else None


async def list_skills(
    db: AsyncSession,
    only_current: bool = True,
    only_active: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    filters = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if only_current:
        filters.append("is_current = TRUE")
    if only_active:
        filters.append("active = TRUE")
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    result = await db.execute(
        text(f"""
            SELECT id, name, version, is_current, description, triggers,
                   sql_template, params_schema, security, stats, active
            FROM skills
            {where}
            ORDER BY name, version DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    return [_row_to_dict(r) for r in result.fetchall()]


async def deactivate_current_versions(db: AsyncSession, name: str) -> None:
    """Set is_current=False for all existing versions of a skill name."""
    await db.execute(
        text("UPDATE skills SET is_current = FALSE WHERE name = :name AND is_current = TRUE"),
        {"name": name},
    )


async def create_new_version(db: AsyncSession, name: str, data: dict[str, Any]) -> dict[str, Any]:
    """Determine next version number, insert, return new row. Caller must commit."""
    ver_result = await db.execute(
        text("SELECT COALESCE(MAX(version), 0) + 1 AS next_ver FROM skills WHERE name = :name"),
        {"name": name},
    )
    next_ver = ver_result.scalar()

    result = await db.execute(
        text("""
            INSERT INTO skills (name, version, is_current, description, triggers,
                                sql_template, params_schema, security, stats, active)
            VALUES (:name, :version, TRUE, :description, :triggers, :sql_template,
                    :params_schema::jsonb, :security::jsonb, :stats::jsonb, :active)
            RETURNING id, name, version, is_current, description, triggers,
                      sql_template, params_schema, security, stats, active
        """),
        {
            "name": name,
            "version": next_ver,
            "description": data.get("description"),
            "triggers": data.get("triggers", []),
            "sql_template": data.get("sql_template"),
            "params_schema": _jsonb(data.get("params_schema", {})),
            "security": _jsonb(data.get("security", {})),
            "stats": _jsonb(data.get("stats", {})),
            "active": data.get("active", False),
        },
    )
    row = result.fetchone()
    return _row_to_dict(row)


async def soft_delete_skill(db: AsyncSession, skill_id: UUID) -> bool:
    """Set active=False (soft delete). Returns True if row found."""
    result = await db.execute(
        text("UPDATE skills SET active = FALSE WHERE id = :id"),
        {"id": str(skill_id)},
    )
    await db.commit()
    return result.rowcount > 0


async def write_changelog(
    db: AsyncSession,
    skill_id: UUID,
    version: int,
    changed_by: Optional[str],
    reason: Optional[str],
    diff: dict[str, Any],
) -> None:
    await db.execute(
        text("""
            INSERT INTO skill_changelog (skill_id, version, changed_by, reason, diff)
            VALUES (:skill_id, :version, :changed_by, :reason, :diff::jsonb)
        """),
        {
            "skill_id": str(skill_id),
            "version": version,
            "changed_by": changed_by,
            "reason": reason,
            "diff": _jsonb(diff),
        },
    )


async def get_all_current_active_skills(db: AsyncSession) -> list[dict[str, Any]]:
    """Return all is_current=True, active=True skills (for matcher seed)."""
    return await list_skills(db, only_current=True, only_active=True, limit=10000)


# ─── helpers ─────────────────────────────────────────────────────────────────

import json as _json


def _jsonb(v: Any) -> str:
    return _json.dumps(v, ensure_ascii=False)


def _row_to_dict(row) -> dict[str, Any]:
    d = dict(row._mapping)
    # UUID → str for JSON serialisation
    if "id" in d and d["id"] is not None:
        d["id"] = str(d["id"])
    # triggers comes back as list from asyncpg; JSONB fields come as dict/str
    for jsonb_col in ("params_schema", "security", "stats"):
        if jsonb_col in d and isinstance(d[jsonb_col], str):
            d[jsonb_col] = _json.loads(d[jsonb_col])
    return d
