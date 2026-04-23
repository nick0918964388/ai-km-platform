"""Skill versioning: create new version, flip is_current, write changelog."""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.skills import repository as repo
from app.services.skills.qdrant_collection import (
    update_payload_active,
    update_payload_is_current,
    upsert_skill_point,
)

log = logging.getLogger(__name__)


async def bump_version(
    db: AsyncSession,
    qdrant,
    embedder,
    name: str,
    update_data: dict[str, Any],
    changed_by: Optional[str] = None,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    """Create a new version of an existing skill.

    Steps (atomic in DB):
    1. Find the current version of `name` (must exist).
    2. Set all existing is_current=True → False.
    3. Insert new version row with is_current=True.
    4. Write skill_changelog entry.
    5. commit()
    6. Best-effort: patch old Qdrant point + upsert new one.

    Returns the new skill row dict.
    """
    old = await repo.get_current_skill_by_name(db, name)
    if old is None:
        raise ValueError(f"Skill '{name}' not found")

    # Merge update_data onto old values (fallback to old if key absent)
    merged: dict[str, Any] = {
        "description": update_data.get("description", old["description"]),
        "triggers": update_data.get("triggers", old["triggers"]),
        "sql_template": update_data.get("sql_template", old["sql_template"]),
        "params_schema": update_data.get("params_schema", old["params_schema"]),
        "security": update_data.get("security", old["security"]),
        "stats": update_data.get("stats", old["stats"]),
        "active": update_data.get("active", old["active"]),
    }

    # Compute diff for changelog
    diff: dict[str, Any] = {
        k: {"old": old.get(k), "new": merged[k]}
        for k in merged
        if old.get(k) != merged[k]
    }

    # DB operations (within the same session, commit at end)
    await repo.deactivate_current_versions(db, name)
    new_row = await repo.create_new_version(db, name, merged)
    await repo.write_changelog(
        db,
        skill_id=UUID(new_row["id"]),
        version=new_row["version"],
        changed_by=changed_by,
        reason=reason,
        diff=diff,
    )
    await db.commit()

    # Best-effort Qdrant updates
    if qdrant is not None and embedder is not None:
        _qdrant_bump(qdrant, embedder, old, new_row)

    return new_row


def _qdrant_bump(qdrant, embedder, old: dict, new_row: dict) -> None:
    """Patch old point + upsert new point (best-effort, swallow errors)."""
    try:
        update_payload_is_current(qdrant, old["id"], old["version"], False)
    except Exception as exc:
        log.warning("_qdrant_bump: patch old point failed: %s", exc)

    try:
        # Embed the first trigger or the skill name as the canonical vector text
        triggers = new_row.get("triggers") or []
        embed_text = triggers[0] if triggers else new_row["name"]
        vector = embedder(embed_text)
        upsert_skill_point(
            qdrant,
            skill_id=new_row["id"],
            version=new_row["version"],
            name=new_row["name"],
            is_current=True,
            vector=vector,
            active=bool(new_row.get("active", False)),
        )
    except Exception as exc:
        log.warning("_qdrant_bump: upsert new point failed: %s", exc)
