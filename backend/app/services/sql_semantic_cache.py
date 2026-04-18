"""SQL 語意快取 (Phase 2 performance optimization).

用 Qdrant 儲存 (query_embedding, sql) 對，語意相似度 > 0.95 即命中複用 SQL。
與 Redis MD5 精確匹配互補，命中時省 LLM 3-4 秒。

風險控管：
- 錯誤命中：保守閾值 0.95；未來可配合使用者 feedback 做黑名單
- 儲存爆炸：payload 記錄 expires_at，lookup 時檢查 TTL（軟過期）
- embedding 版本：payload 多存 embedding_model + dim，版本不符當 miss
- 主流程保護：insert 失敗 swallow，不能 block 回應
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

log = logging.getLogger(__name__)

COLLECTION_NAME = "sql_semantic_cache"
SIMILARITY_THRESHOLD = 0.95   # 超過才算命中
DEFAULT_TTL = 86400 * 7       # 7 天（軟過期，lookup 時檢查）


@dataclass
class SQLCacheEntry:
    query: str
    sql: str
    similarity: float
    created_at: float
    explanation: Optional[str] = None
    model: Optional[str] = None
    confidence: Optional[float] = None


class SemanticSQLCache:
    """Qdrant-backed semantic cache for NL→SQL."""

    def __init__(
        self,
        qdrant: QdrantClient,
        embedder,
        embedding_model: str = "unknown",
        dimensions: Optional[int] = None,
        threshold: float = SIMILARITY_THRESHOLD,
        collection_name: str = COLLECTION_NAME,
    ):
        """
        embedder: 物件，需有 `.embed(text)` -> list[float]，或可呼叫。
        embedding_model: 記錄 embedding model 版本，便於未來換 model 時 invalidate。
        dimensions: 若 embedder 不知道維度可手動提供。
        """
        self.qdrant = qdrant
        self.embedder = embedder
        self.embedding_model = embedding_model
        self._dimensions = dimensions
        self.threshold = threshold
        self.collection_name = collection_name
        self._ensured = False

    def _embed(self, text: str) -> list[float]:
        # 支援 callable 或有 .embed 方法的 embedder
        if hasattr(self.embedder, "embed"):
            return self.embedder.embed(text)
        if callable(self.embedder):
            return self.embedder(text)
        raise TypeError("embedder must be callable or have .embed(text)")

    def _dim(self, sample_vec: Optional[list[float]] = None) -> int:
        if self._dimensions:
            return self._dimensions
        if sample_vec is not None:
            self._dimensions = len(sample_vec)
            return self._dimensions
        if hasattr(self.embedder, "dimensions"):
            return self.embedder.dimensions
        # 最後才真的 embed 一次 probe
        probe = self._embed("__probe__")
        self._dimensions = len(probe)
        return self._dimensions

    def _ensure(self, sample_vec: Optional[list[float]] = None) -> bool:
        """確保 collection 存在。回傳 False 若無法建立（Qdrant 不可用）。"""
        if self._ensured:
            return True
        try:
            existing = {c.name for c in self.qdrant.get_collections().collections}
            if self.collection_name not in existing:
                dim = self._dim(sample_vec)
                self.qdrant.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                )
                log.info(
                    "Created Qdrant collection %s (dim=%d) for SQL semantic cache",
                    self.collection_name, dim,
                )
            self._ensured = True
            return True
        except Exception as e:
            log.warning("Failed to ensure Qdrant collection %s: %s", self.collection_name, e)
            return False

    def lookup(self, query: str) -> Optional[SQLCacheEntry]:
        """查詢語意快取，命中回傳 entry，否則 None。任何錯誤 swallow 回傳 None。"""
        try:
            if not self._ensure():
                return None
            vec = self._embed(query)
            # Qdrant 1.10+ prefers query_points; fall back to search if unavailable
            if hasattr(self.qdrant, "query_points"):
                res = self.qdrant.query_points(
                    collection_name=self.collection_name,
                    query=vec,
                    limit=1,
                    with_payload=True,
                )
                points = res.points if hasattr(res, "points") else res
            else:
                points = self.qdrant.search(
                    collection_name=self.collection_name,
                    query_vector=vec,
                    limit=1,
                    with_payload=True,
                )
            if not points:
                return None
            top = points[0]
            if top.score < self.threshold:
                return None
            payload = top.payload or {}
            # embedding model 版本不符 → 當 miss
            if payload.get("embedding_model") and payload.get("embedding_model") != self.embedding_model:
                log.debug("Semantic cache miss: model mismatch (%s vs %s)",
                          payload.get("embedding_model"), self.embedding_model)
                return None
            # TTL 檢查
            expires_at = payload.get("expires_at", 0)
            if expires_at and expires_at < time.time():
                return None
            return SQLCacheEntry(
                query=payload.get("query", ""),
                sql=payload.get("sql", ""),
                similarity=float(top.score),
                created_at=float(payload.get("created_at", 0) or 0),
                explanation=payload.get("explanation"),
                model=payload.get("model"),
                confidence=payload.get("confidence"),
            )
        except Exception as e:
            log.warning("Semantic cache lookup failed: %s", e)
            return None

    def insert(
        self,
        query: str,
        sql: str,
        ttl: int = DEFAULT_TTL,
        explanation: Optional[str] = None,
        model: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> bool:
        """寫入快取。失敗 swallow（不能 block 主流程）。回傳是否成功。"""
        try:
            vec = self._embed(query)
            if not self._ensure(sample_vec=vec):
                return False
            now = time.time()
            self.qdrant.upsert(
                collection_name=self.collection_name,
                points=[PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vec,
                    payload={
                        "query": query,
                        "sql": sql,
                        "explanation": explanation,
                        "model": model,
                        "confidence": confidence,
                        "created_at": now,
                        "expires_at": now + ttl,
                        "embedding_model": self.embedding_model,
                    },
                )],
            )
            return True
        except Exception as e:
            log.warning("Semantic cache insert failed: %s", e)
            return False


# ── 全域單例（lazy）──────────────────────────────────────────────
_cache_instance: Optional[SemanticSQLCache] = None


def get_semantic_sql_cache() -> Optional[SemanticSQLCache]:
    """取得全域 semantic cache 實例。首次呼叫會 lazy 初始化。
    若 Qdrant 不可用，回傳 None（呼叫端要檢查）。
    """
    global _cache_instance
    if _cache_instance is not None:
        return _cache_instance

    try:
        from app.services.vector_store import get_client
        from app.services.embedding import (
            embed_text,
            get_text_embedding_dimension,
            get_embedding_info,
        )

        class _Embedder:
            def embed(self, text: str) -> list[float]:
                return embed_text(text)

        info = get_embedding_info()
        model_tag = f"{info.get('provider', 'unknown')}:{info.get('model', 'unknown')}"
        _cache_instance = SemanticSQLCache(
            qdrant=get_client(),
            embedder=_Embedder(),
            embedding_model=model_tag,
            dimensions=get_text_embedding_dimension(),
        )
        return _cache_instance
    except Exception as e:
        log.warning("Failed to initialize semantic SQL cache: %s", e)
        return None
