"""Tests for SemanticSQLCache — Qdrant-backed NL→SQL semantic cache.

Uses in-memory Qdrant (QdrantClient(":memory:")) + deterministic fake embedder
to avoid external dependencies.
"""
from __future__ import annotations

import time
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from qdrant_client import QdrantClient

from app.services.sql_semantic_cache import (
    SIMILARITY_THRESHOLD,
    SemanticSQLCache,
)


# ── Fake deterministic embedder ─────────────────────────────────────────
class FakeEmbedder:
    """Keyword-based deterministic embedder in 8 dims.

    Lets us construct pairs of queries with predictable cosine similarity:
    - identical query → sim = 1.0
    - share most keywords → sim > 0.95
    - different keywords → sim < 0.90
    """
    dimensions = 8
    # 8 slots: [emu, fault, count, list, repair, latest, asset, inventory]
    _KEYWORDS = [
        ("emu", ["EMU", "emu"]),
        ("fault", ["故障", "fault"]),
        ("count", ["幾次", "幾個", "count", "count()"]),
        ("list", ["列出", "list", "show"]),
        ("repair", ["維修", "repair"]),
        ("latest", ["最新", "最近", "latest"]),
        ("asset", ["車輛", "assets", "asset"]),
        ("inventory", ["庫存", "inventory"]),
    ]

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * len(self._KEYWORDS)
        for i, (_, kws) in enumerate(self._KEYWORDS):
            for kw in kws:
                if kw in text:
                    vec[i] = 1.0
                    break
        # normalize to unit length for cosine
        norm = sum(v * v for v in vec) ** 0.5
        if norm == 0:
            vec[0] = 1.0  # avoid zero vector
            return vec
        return [v / norm for v in vec]


# ── Fixtures ─────────────────────────────────────────────────────────────
@pytest.fixture
def qdrant() -> QdrantClient:
    return QdrantClient(":memory:")


@pytest.fixture
def cache(qdrant: QdrantClient) -> SemanticSQLCache:
    return SemanticSQLCache(
        qdrant=qdrant,
        embedder=FakeEmbedder(),
        embedding_model="fake:v1",
        dimensions=FakeEmbedder.dimensions,
        collection_name="test_sql_semantic_cache",
    )


# ── Tests ────────────────────────────────────────────────────────────────
def test_insert_then_lookup_exact(cache: SemanticSQLCache):
    """完全相同的 query → similarity ~= 1.0，應命中。"""
    q = "EMU900 去年故障幾次"
    sql = "SELECT count(*) FROM maximo_fault_reports WHERE assetnum='EMU900'"
    assert cache.insert(q, sql) is True

    hit = cache.lookup(q)
    assert hit is not None, "identical query should hit"
    assert hit.sql == sql
    assert hit.similarity > 0.99  # 近乎 1.0
    assert hit.query == q


def test_lookup_similar_query_above_threshold(cache: SemanticSQLCache):
    """語意相似（共用 keyword）且相似度 > 0.95 → 命中。

    FakeEmbedder: "EMU故障幾次" 與 "EMU 故障幾次" 共用所有 3 slot → cos=1.0
    """
    cache.insert("EMU900 故障幾次", "SELECT count(*) FROM ...")
    # 同樣 3 個 keyword hit (EMU/故障/幾次) → 相同向量 → cos=1.0
    hit = cache.lookup("EMU900 故障 幾次?")
    assert hit is not None
    assert hit.similarity >= SIMILARITY_THRESHOLD


def test_lookup_dissimilar_below_threshold(cache: SemanticSQLCache):
    """語意明顯不同（完全無共用 keyword）→ similarity 低 → 不命中。"""
    cache.insert("EMU900 故障幾次", "SELECT count(*) FROM faults")
    # 完全沒有共同 keyword（inventory/庫存 vs emu/故障/幾次） → cos=0
    hit = cache.lookup("庫存 inventory 列出")
    assert hit is None, f"dissimilar query should miss, got {hit}"


def test_ttl_expiry(qdrant: QdrantClient):
    """expires_at 過期 → 即使 similarity 夠高也不命中。"""
    cache = SemanticSQLCache(
        qdrant=qdrant,
        embedder=FakeEmbedder(),
        embedding_model="fake:v1",
        dimensions=FakeEmbedder.dimensions,
        collection_name="test_ttl_expiry",
    )
    # TTL = -1 秒 → 立刻過期
    cache.insert("EMU故障", "SELECT 1", ttl=-1)
    hit = cache.lookup("EMU故障")
    assert hit is None, "expired entry should not be returned"


def test_no_collection_auto_create(qdrant: QdrantClient):
    """初始時 collection 不存在，insert/lookup 會自動建立。"""
    col_name = "test_auto_create_collection"
    # 確認初始沒有 collection
    existing = {c.name for c in qdrant.get_collections().collections}
    assert col_name not in existing

    cache = SemanticSQLCache(
        qdrant=qdrant,
        embedder=FakeEmbedder(),
        embedding_model="fake:v1",
        dimensions=FakeEmbedder.dimensions,
        collection_name=col_name,
    )

    # 第一次 insert 應自動建立
    assert cache.insert("test query", "SELECT 1") is True

    after = {c.name for c in qdrant.get_collections().collections}
    assert col_name in after, "collection should be auto-created on first insert"


def test_embedding_model_mismatch_invalidates(qdrant: QdrantClient):
    """換 embedding model 後，舊 cache 應 miss（避免 vector space 不一致）。"""
    col = "test_model_mismatch"
    c1 = SemanticSQLCache(
        qdrant=qdrant, embedder=FakeEmbedder(), embedding_model="model-A",
        dimensions=FakeEmbedder.dimensions, collection_name=col,
    )
    c1.insert("EMU故障", "SELECT 1 FROM a")

    # 同一 collection，但 embedding_model 不同
    c2 = SemanticSQLCache(
        qdrant=qdrant, embedder=FakeEmbedder(), embedding_model="model-B",
        dimensions=FakeEmbedder.dimensions, collection_name=col,
    )
    hit = c2.lookup("EMU故障")
    assert hit is None, "different embedding_model should invalidate cached entry"


def test_insert_failure_does_not_raise(qdrant: QdrantClient):
    """Qdrant 故障時 insert 應 swallow 失敗，不拋例外（不能 block 主流程）。"""
    broken_qdrant = MagicMock()
    broken_qdrant.get_collections.side_effect = RuntimeError("qdrant down")
    broken_qdrant.upsert.side_effect = RuntimeError("qdrant down")

    cache = SemanticSQLCache(
        qdrant=broken_qdrant,
        embedder=FakeEmbedder(),
        embedding_model="fake:v1",
        dimensions=FakeEmbedder.dimensions,
        collection_name="broken",
    )
    # 不應拋例外
    assert cache.insert("q", "SELECT 1") is False
    assert cache.lookup("q") is None


# ── B 任務對應測試：schema embedding 去重 ─────────────────────────
def test_schema_build_calls_embed_once():
    """build_schema 應只呼叫 embed_text 一次（B: schema embedding 去重）。

    原本 find_relevant_tables + find_relevant_columns 各自呼叫一次 = 2 次；
    修正後只在 build_schema 頂層呼叫一次，兩個 search 共用 embedding。
    """
    import asyncio
    from app.services import maximo_schema_rag

    # Mock embed_text 計次
    call_count = {"n": 0}

    def mock_embed(text: str) -> list[float]:
        call_count["n"] += 1
        return [0.1] * 8

    # Mock Qdrant client
    fake_qdrant = MagicMock()

    # _collection_ready() → True
    fake_collection = MagicMock()
    fake_collection.name = maximo_schema_rag.MaximoSchemaRAG.TABLES_COLLECTION
    fake_collection2 = MagicMock()
    fake_collection2.name = maximo_schema_rag.MaximoSchemaRAG.ATTRS_COLLECTION
    fake_qdrant.get_collections.return_value.collections = [fake_collection, fake_collection2]
    info = MagicMock()
    info.points_count = 10
    fake_qdrant.get_collection.return_value = info

    # query_points 依 collection_name 回傳不同 payload
    def fake_query_points(*args, **kwargs):
        col = kwargs.get("collection_name", "")
        res = MagicMock()
        if col == maximo_schema_rag.MaximoSchemaRAG.TABLES_COLLECTION:
            hit = MagicMock()
            hit.payload = {
                "table_name": "maximo_assets",
                "object_name": "ASSET",
                "description": "車輛主檔",
                "key_columns": ["assetnum"],
                "fk_relations": {},
            }
            hit.score = 0.9
            res.points = [hit]
        elif col == maximo_schema_rag.MaximoSchemaRAG.ATTRS_COLLECTION:
            hit = MagicMock()
            hit.payload = {
                "attribute_name": "assetnum",
                "title": "資產編號",
                "domain_id": "",
                "object_name": "ASSET",
            }
            hit.score = 0.8
            res.points = [hit]
        else:
            res.points = []
        return res

    fake_qdrant.query_points.side_effect = fake_query_points

    # Mock db
    fake_db = MagicMock()

    async def run():
        # Patch embed_text and get_client
        with patch.object(maximo_schema_rag, "embed_text", side_effect=mock_embed), \
             patch.object(maximo_schema_rag, "get_client", return_value=fake_qdrant):
            rag = maximo_schema_rag.MaximoSchemaRAG(db=fake_db)
            # stub DB-dependent helpers
            async def _all_tables():
                return []
            async def _domain_vals(ids):
                return {}
            rag._get_all_tables_cached = _all_tables
            rag._get_domain_vals_cached = _domain_vals

            # 修正前：會呼叫 embed_text 2 次
            # 修正後：只呼叫 1 次（build_schema 頂層計算後共用）
            await rag.build_schema("EMU900 故障幾次")

    asyncio.run(run())

    assert call_count["n"] == 1, (
        f"build_schema should call embed_text exactly once "
        f"(schema embedding dedup), got {call_count['n']}"
    )
