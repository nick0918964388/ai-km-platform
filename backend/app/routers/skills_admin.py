"""Skills Admin API.

Endpoints:
  GET    /api/admin/skills           — list skills
  POST   /api/admin/skills           — create skill (version=1)
  PUT    /api/admin/skills/{id}      — update (bumps to new version)
  DELETE /api/admin/skills/{id}      — soft delete (active=False)
  GET    /api/admin/skills/{id}      — get single skill
  POST   /api/admin/skills/seed      — seed from nl_sql_examples
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from app.auth import require_admin, get_current_user
from app.db.session import get_db, get_db_context
from app.services.maximo_nl2sql_tools import _is_safe_select
from app.services.skills import repository as repo
from app.services.skills.schema import SkillCreate, SkillUpdate
from app.services.skills.versioning import bump_version
from app.services.skills.seed import seed_from_nl_sql_examples
from app.services.skills.qdrant_collection import (
    ensure_collection,
    upsert_skill_point,
    update_payload_active,
    SKILLS_COLLECTION,
)
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/skills", tags=["skills-admin"])


def _get_qdrant_and_embedder():
    """Return (qdrant_client, embedder_callable) or (None, None) on failure."""
    try:
        from app.services.vector_store import get_client
        from app.services.embedding import embed_text
        return get_client(), embed_text
    except Exception as exc:
        log.warning("skills_admin: could not load qdrant/embedder: %s", exc)
        return None, None


# ─── LIST ────────────────────────────────────────────────────────────────────

@router.get("")
async def list_skills(
    only_current: bool = Query(True),
    only_active: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_admin),
):
    skills = await repo.list_skills(
        db,
        only_current=only_current,
        only_active=only_active,
        limit=limit,
        offset=offset,
    )
    return {"skills": skills, "count": len(skills)}


# ─── GET ONE ─────────────────────────────────────────────────────────────────

@router.get("/{skill_id}")
async def get_skill(
    skill_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_admin),
):
    skill = await repo.get_skill_by_id(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


# ─── CREATE ──────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_skill(
    payload: SkillCreate,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_admin),
):
    # Validate sql_template if provided
    if payload.sql_template:
        ok, err = _is_safe_select(payload.sql_template)
        if not ok:
            raise HTTPException(status_code=400, detail=f"unsafe_sql: {err}")

    # Check duplicate name (current version already exists)
    existing = await repo.get_current_skill_by_name(db, payload.name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Skill '{payload.name}' already exists (version {existing['version']}). Use PUT to update.",
        )

    skill = await repo.create_skill(db, payload.model_dump())

    # Best-effort Qdrant
    qdrant, embedder = _get_qdrant_and_embedder()
    if qdrant and embedder:
        try:
            ensure_collection(qdrant)
            triggers = skill.get("triggers") or []
            embed_text_val = triggers[0] if triggers else skill["name"]
            vector = embedder(embed_text_val)
            upsert_skill_point(
                qdrant,
                skill_id=skill["id"],
                version=skill["version"],
                name=skill["name"],
                is_current=True,
                vector=vector,
                active=bool(skill.get("active", False)),
            )
        except Exception as exc:
            log.warning("create_skill: qdrant upsert failed: %s", exc)

    return JSONResponse(status_code=201, content=skill)


# ─── UPDATE (new version) ────────────────────────────────────────────────────

@router.put("/{skill_id}")
async def update_skill(
    skill_id: UUID,
    payload: SkillUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_admin),
):
    # Validate sql_template if provided
    if payload.sql_template is not None:
        ok, err = _is_safe_select(payload.sql_template)
        if not ok:
            raise HTTPException(status_code=400, detail=f"unsafe_sql: {err}")

    existing = await repo.get_skill_by_id(db, skill_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Skill not found")

    qdrant, embedder = _get_qdrant_and_embedder()

    new_skill = await bump_version(
        db=db,
        qdrant=qdrant,
        embedder=embedder,
        name=existing["name"],
        update_data=payload.model_dump(exclude_none=True, exclude={"reason", "changed_by"}),
        changed_by=user.get("email"),
        reason=payload.reason,
    )
    return new_skill


# ─── DELETE (soft) ───────────────────────────────────────────────────────────

@router.delete("/{skill_id}", status_code=204)
async def delete_skill(
    skill_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_admin),
):
    existing = await repo.get_skill_by_id(db, skill_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Skill not found")
    await repo.soft_delete_skill(db, skill_id)
    # Write changelog for soft delete
    try:
        await repo.write_changelog(
            db,
            skill_id=skill_id,
            version=existing["version"],
            changed_by=user.get("email"),
            reason=f"soft delete by {user.get('email')}",
            diff={"active": {"old": existing.get("active"), "new": False}},
        )
        await db.commit()
    except Exception as exc:
        log.warning("delete_skill: changelog write failed: %s", exc)
    # Best-effort Qdrant active=False sync
    qdrant, _ = _get_qdrant_and_embedder()
    if qdrant:
        try:
            update_payload_active(qdrant, str(skill_id), existing["version"], False)
        except Exception as exc:
            log.warning("delete_skill: qdrant active sync failed: %s", exc)


# ─── SEED ────────────────────────────────────────────────────────────────────

@router.post("/seed", status_code=200)
async def seed_skills(
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_admin),
):
    """Seed skills from nl_sql_examples.verified=TRUE (conservative: active=False)."""
    qdrant, embedder = _get_qdrant_and_embedder()
    inserted = await seed_from_nl_sql_examples(db, qdrant=qdrant, embedder=embedder)
    return {"seeded": inserted}
