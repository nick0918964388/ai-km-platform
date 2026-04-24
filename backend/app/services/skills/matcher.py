"""SkillMatcher — vector-based skill matching via skills_vectors Qdrant collection.

Only returns skills where is_current=True AND active=True.
Threshold: 0.85 cosine similarity.
"""
from __future__ import annotations

import logging
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.services.skills.qdrant_collection import SKILLS_COLLECTION, ensure_collection

log = logging.getLogger(__name__)

MATCH_THRESHOLD = 0.85


class SkillMatcher:
    def __init__(self, qdrant: QdrantClient, embedder):
        """
        embedder: callable (text: str) -> list[float]
        """
        self._qdrant = qdrant
        self._embedder = embedder
        ensure_collection(qdrant)

    def match(self, query: str, top_k: int = 5) -> list[dict]:
        """Return up to top_k skills with score >= MATCH_THRESHOLD.

        Only considers points where payload.is_current == true.
        Returns list of dicts: {skill_id, version, name, score, ...}.
        """
        try:
            vector = self._embedder(query)
        except Exception as exc:
            log.warning("SkillMatcher: embed failed — %s", exc)
            return []

        try:
            response = self._qdrant.query_points(
                collection_name=SKILLS_COLLECTION,
                query=vector,
                limit=top_k,
                query_filter=Filter(
                    must=[
                        FieldCondition(
                            key="is_current",
                            match=MatchValue(value=True),
                        ),
                        FieldCondition(
                            key="active",
                            match=MatchValue(value=True),
                        ),
                    ]
                ),
            )
        except Exception as exc:
            log.warning("SkillMatcher: Qdrant search failed — %s", exc)
            return []

        hits = []
        for r in response.points:
            if r.score < MATCH_THRESHOLD:
                continue
            payload = r.payload or {}
            hits.append(
                {
                    "skill_id": payload.get("skill_id", str(r.id)),
                    "name": payload.get("name", ""),
                    "version": payload.get("version", 1),
                    "score": r.score,
                    "is_current": payload.get("is_current", True),
                }
            )
        return hits
