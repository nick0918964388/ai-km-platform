"""Qdrant collection management for skills_vectors.

Provides ensure_collection() (idempotent) and helpers to upsert/delete points.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.services.embedding import get_text_embedding_dimension

log = logging.getLogger(__name__)

SKILLS_COLLECTION = "skills_vectors"


def ensure_collection(qdrant: QdrantClient) -> None:
    """Create skills_vectors collection if it doesn't exist (idempotent)."""
    try:
        existing = {c.name for c in qdrant.get_collections().collections}
        if SKILLS_COLLECTION not in existing:
            dim = get_text_embedding_dimension()
            qdrant.create_collection(
                collection_name=SKILLS_COLLECTION,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            log.info("Created Qdrant collection '%s' (dim=%d)", SKILLS_COLLECTION, dim)
        else:
            log.debug("Qdrant collection '%s' already exists", SKILLS_COLLECTION)
    except Exception as exc:
        log.error("ensure_collection(%s) failed: %s", SKILLS_COLLECTION, exc)
        raise


def upsert_skill_point(
    qdrant: QdrantClient,
    skill_id: str,
    version: int,
    name: str,
    is_current: bool,
    vector: list[float],
    active: bool = False,
) -> None:
    """Upsert a single skill point.  Uses skill_id+version as deterministic UUID."""
    point_id = _point_id(skill_id, version)
    qdrant.upsert(
        collection_name=SKILLS_COLLECTION,
        points=[
            PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "skill_id": skill_id,
                    "version": version,
                    "name": name,
                    "is_current": is_current,
                    "active": active,
                },
            )
        ],
    )


def update_payload_is_current(
    qdrant: QdrantClient, skill_id: str, version: int, is_current: bool
) -> None:
    """Patch the is_current flag on an existing point (best-effort)."""
    try:
        point_id = _point_id(skill_id, version)
        qdrant.set_payload(
            collection_name=SKILLS_COLLECTION,
            payload={"is_current": is_current},
            points=[point_id],
        )
    except Exception as exc:
        log.warning(
            "update_payload_is_current(%s v%d) best-effort failed: %s",
            skill_id, version, exc,
        )


def update_payload_active(
    qdrant: QdrantClient, skill_id: str, version: int, active: bool
) -> None:
    """Patch the active flag on an existing point (best-effort)."""
    try:
        point_id = _point_id(skill_id, version)
        qdrant.set_payload(
            collection_name=SKILLS_COLLECTION,
            payload={"active": active},
            points=[point_id],
        )
    except Exception as exc:
        log.warning(
            "update_payload_active(%s v%d) best-effort failed: %s",
            skill_id, version, exc,
        )


def delete_skill_point(qdrant: QdrantClient, skill_id: str, version: int) -> None:
    """Delete a point (best-effort, used during hard delete if ever needed)."""
    try:
        qdrant.delete(
            collection_name=SKILLS_COLLECTION,
            points_selector=[_point_id(skill_id, version)],
        )
    except Exception as exc:
        log.warning("delete_skill_point(%s v%d) failed: %s", skill_id, version, exc)


def _point_id(skill_id: str, version: int) -> str:
    """Deterministic UUID from skill_id + version."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{skill_id}:{version}"))
