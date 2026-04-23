"""Seed skills from nl_sql_examples WHERE verified=TRUE.

Conservative mode:
- active=False (won't be matched until admin reviews)
- triggers = [question]
- stats.seed_origin = 'nl_sql_examples'
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.skills import repository as repo
from app.services.skills.qdrant_collection import ensure_collection, upsert_skill_point

log = logging.getLogger(__name__)


async def seed_from_nl_sql_examples(
    db: AsyncSession,
    qdrant=None,
    embedder=None,
) -> int:
    """Seed skills v1 from nl_sql_examples.verified=TRUE.

    Skips rows where a skill with the same name already exists.
    Returns count of inserted skills.
    """
    if qdrant is not None:
        ensure_collection(qdrant)

    result = await db.execute(
        text("""
            SELECT id, question, sql_query
            FROM nl_sql_examples
            WHERE verified = TRUE
            ORDER BY id
        """)
    )
    rows = result.fetchall()
    inserted = 0

    for row in rows:
        name = _make_name(row.question)
        existing = await repo.get_current_skill_by_name(db, name)
        if existing:
            log.debug("seed: skip '%s' — already exists", name)
            continue

        skill = await repo.create_skill(
            db,
            {
                "name": name,
                "description": row.question,
                "triggers": [row.question],
                "sql_template": row.sql_query,
                "params_schema": {},
                "security": {},
                "stats": {"seed_origin": "nl_sql_examples", "source_id": row.id},
                "active": False,
            },
        )
        inserted += 1

        # Best-effort Qdrant insert
        if qdrant is not None and embedder is not None:
            try:
                vector = embedder(row.question)
                upsert_skill_point(
                    qdrant,
                    skill_id=skill["id"],
                    version=skill["version"],
                    name=skill["name"],
                    is_current=True,
                    vector=vector,
                )
            except Exception as exc:
                log.warning("seed: qdrant upsert failed for '%s': %s", name, exc)

    log.info("seed_from_nl_sql_examples: inserted %d skills", inserted)
    return inserted


def _make_name(question: str) -> str:
    """Derive a stable skill name from the example question (max 120 chars)."""
    return question.strip()[:120]
