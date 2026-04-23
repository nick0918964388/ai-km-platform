"""skill_feedback writer.

Writes feedback to the skill_feedback table and bumps stats snapshot in skills.
Does NOT touch rag_feedback.
"""
from __future__ import annotations

import json
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


async def record(
    db: AsyncSession,
    skill_id: UUID,
    skill_version: int,
    rating: str,
    message_id: Optional[str] = None,
    comment: Optional[str] = None,
    user_id: Optional[str] = None,
) -> int:
    """Write one feedback row and return its id."""
    if rating not in ("up", "down"):
        raise ValueError(f"Invalid rating: {rating!r}")

    result = await db.execute(
        text("""
            INSERT INTO skill_feedback
                (skill_id, skill_version, message_id, rating, comment, user_id)
            VALUES
                (:skill_id, :skill_version, :message_id, :rating, :comment, :user_id)
            RETURNING id
        """),
        {
            "skill_id": str(skill_id),
            "skill_version": skill_version,
            "message_id": message_id,
            "rating": rating,
            "comment": comment,
            "user_id": user_id,
        },
    )
    feedback_id = result.scalar()
    await db.commit()
    log.info(
        "skill_feedback: skill_id=%s version=%d rating=%s id=%d",
        skill_id, skill_version, rating, feedback_id,
    )
    return feedback_id


async def get_feedback_stats(
    db: AsyncSession, skill_id: UUID, skill_version: int
) -> dict:
    """Aggregate up/down counts for a specific skill version."""
    result = await db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE rating = 'up')   AS up_count,
                COUNT(*) FILTER (WHERE rating = 'down') AS down_count
            FROM skill_feedback
            WHERE skill_id = :skill_id AND skill_version = :skill_version
        """),
        {"skill_id": str(skill_id), "skill_version": skill_version},
    )
    row = result.fetchone()
    return {"up": row.up_count or 0, "down": row.down_count or 0}
