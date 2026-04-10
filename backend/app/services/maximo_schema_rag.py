"""
Maximo Schema RAG Service
用向量搜尋篩選相關表與欄位，減少 NL→SQL prompt 的 schema 大小。
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from qdrant_client.models import (
    VectorParams, Distance, PointStruct,
    Filter, FieldCondition, MatchValue,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.services.embedding import embed_text, embed_texts, get_text_embedding_dimension
from app.services.vector_store import get_client

log = logging.getLogger(__name__)


class MaximoSchemaRAG:
    TABLES_COLLECTION = "maximo_table_catalog"
    ATTRS_COLLECTION = "maximo_attributes"

    def __init__(self, db: AsyncSession):
        self.db = db
        self.qdrant = get_client()

    # ── Index ────────────────────────────────────────────────────────────────

    async def index_all(self) -> dict:
        """索引 table catalog + attributes 到 Qdrant。"""
        dim = get_text_embedding_dimension()

        # 重建 collections
        self.qdrant.recreate_collection(
            collection_name=self.TABLES_COLLECTION,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        self.qdrant.recreate_collection(
            collection_name=self.ATTRS_COLLECTION,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )

        # 1) 索引 table catalog
        rows = await self.db.execute(text(
            "SELECT table_name, object_name, description, key_columns, fk_relations "
            "FROM maximo_table_catalog"
        ))
        tables = rows.fetchall()
        if not tables:
            return {"tables_indexed": 0, "attributes_indexed": 0}

        table_texts = [t.description for t in tables]
        table_embeddings = embed_texts(table_texts)

        table_points = []
        for i, (t, emb) in enumerate(zip(tables, table_embeddings)):
            table_points.append(PointStruct(
                id=i,
                vector=emb,
                payload={
                    "table_name": t.table_name,
                    "object_name": t.object_name or "",
                    "description": t.description,
                    "key_columns": list(t.key_columns) if t.key_columns else [],
                    "fk_relations": dict(t.fk_relations) if t.fk_relations else {},
                },
            ))
        self.qdrant.upsert(collection_name=self.TABLES_COLLECTION, points=table_points)

        # 2) 索引 attributes（只取 persistent + 已知 object）
        known_objects = [t.object_name for t in tables if t.object_name]
        if not known_objects:
            await self._update_indexed_at()
            return {"tables_indexed": len(tables), "attributes_indexed": 0}

        placeholders = ", ".join(f":o{i}" for i in range(len(known_objects)))
        params = {f"o{i}": v for i, v in enumerate(known_objects)}
        attr_rows = await self.db.execute(text(
            f"SELECT objectname, attributename, title, domainid "
            f"FROM maximo_zz_maxattribute "
            f"WHERE persistent = 'True' AND objectname IN ({placeholders}) "
            f"ORDER BY objectname, attributename"
        ), params)
        attrs = attr_rows.fetchall()

        if not attrs:
            await self._update_indexed_at()
            return {"tables_indexed": len(tables), "attributes_indexed": 0}

        # 建立 object→table 對應
        obj_to_table = {t.object_name: t.table_name for t in tables if t.object_name}

        # 批次 embed
        attr_texts = [f"{a.title or a.attributename}（{a.attributename}）" for a in attrs]
        # 分批處理避免一次送太多
        BATCH = 200
        attr_embeddings = []
        for start in range(0, len(attr_texts), BATCH):
            batch = attr_texts[start:start + BATCH]
            attr_embeddings.extend(embed_texts(batch))

        attr_points = []
        for i, (a, emb) in enumerate(zip(attrs, attr_embeddings)):
            attr_points.append(PointStruct(
                id=i,
                vector=emb,
                payload={
                    "object_name": a.objectname,
                    "attribute_name": a.attributename,
                    "title": a.title or a.attributename,
                    "domain_id": a.domainid or "",
                    "table_name": obj_to_table.get(a.objectname, ""),
                },
            ))

        # 分批 upsert
        for start in range(0, len(attr_points), BATCH):
            self.qdrant.upsert(
                collection_name=self.ATTRS_COLLECTION,
                points=attr_points[start:start + BATCH],
            )

        await self._update_indexed_at()
        return {"tables_indexed": len(tables), "attributes_indexed": len(attrs)}

    async def _update_indexed_at(self):
        """更新 maximo_table_catalog.indexed_at"""
        try:
            await self.db.execute(text(
                "UPDATE maximo_table_catalog SET indexed_at = :ts"
            ), {"ts": datetime.now(timezone.utc)})
            await self.db.commit()
        except Exception as e:
            log.warning("更新 indexed_at 失敗: %s", e)

    # ── Search ───────────────────────────────────────────────────────────────

    async def find_relevant_tables(self, question: str, top_k: int = 3) -> list[dict]:
        """向量搜尋 table catalog，回傳最相關的表。"""
        query_emb = embed_text(question)
        results = self.qdrant.query_points(
            collection_name=self.TABLES_COLLECTION,
            query=query_emb,
            limit=top_k,
        )
        return [
            {**r.payload, "score": r.score}
            for r in results.points
        ]

    async def find_relevant_columns(
        self, question: str, object_names: list[str], top_k_per_table: int = 20
    ) -> dict[str, list[dict]]:
        """向量搜尋各 object 的相關欄位。"""
        if not object_names:
            return {}

        query_emb = embed_text(question)
        result_map: dict[str, list[dict]] = {}

        for obj in object_names:
            results = self.qdrant.query_points(
                collection_name=self.ATTRS_COLLECTION,
                query=query_emb,
                query_filter=Filter(
                    must=[FieldCondition(key="object_name", match=MatchValue(value=obj))]
                ),
                limit=top_k_per_table,
            )
            result_map[obj] = [
                {
                    "attribute_name": r.payload["attribute_name"],
                    "title": r.payload["title"],
                    "domain_id": r.payload.get("domain_id", ""),
                    "score": r.score,
                }
                for r in results.points
            ]

        return result_map

    # ── Build Schema ─────────────────────────────────────────────────────────

    async def build_schema(self, question: str) -> tuple[str, set[str]]:
        """完整 RAG pipeline：找表 → 找欄位 → 組裝 schema text。
        回傳 (schema_text, allowed_table_names)。
        """
        # 先確認 collection 存在且有資料
        if not self._collection_ready():
            return "", set()

        # 1) 找相關表
        tables = await self.find_relevant_tables(question, top_k=3)
        if not tables:
            return "", set()

        # 載入全部 table catalog 作為摘要
        all_tables_rows = await self.db.execute(text(
            "SELECT table_name, description FROM maximo_table_catalog ORDER BY table_name"
        ))
        all_tables = all_tables_rows.fetchall()

        # 2) 找相關欄位（只查有 object_name 的表）
        obj_names = [t["object_name"] for t in tables if t.get("object_name")]
        columns_by_obj = await self.find_relevant_columns(question, obj_names, top_k_per_table=20)

        # 確保 key_columns 也包含在內
        key_col_set: dict[str, set[str]] = {}
        for t in tables:
            obj = t.get("object_name", "")
            if obj and t.get("key_columns"):
                key_col_set[obj] = set(c.upper() for c in t["key_columns"])

        for obj, cols in columns_by_obj.items():
            existing = {c["attribute_name"].upper() for c in cols}
            missing_keys = key_col_set.get(obj, set()) - existing
            if missing_keys:
                # 從 DB 補齊 key columns 的 metadata
                placeholders = ", ".join(f":k{i}" for i in range(len(missing_keys)))
                params = {f"k{i}": v for i, v in enumerate(missing_keys)}
                params["obj"] = obj
                key_rows = await self.db.execute(text(
                    f"SELECT attributename, title FROM maximo_zz_maxattribute "
                    f"WHERE objectname = :obj AND UPPER(attributename) IN ({placeholders})"
                ), params)
                for kr in key_rows.fetchall():
                    cols.append({
                        "attribute_name": kr.attributename,
                        "title": kr.title or kr.attributename,
                        "domain_id": "",
                        "score": 1.0,  # key columns 優先
                    })

        # 3) 載入 domain values
        all_domain_ids = set()
        for cols in columns_by_obj.values():
            for c in cols:
                if c.get("domain_id"):
                    all_domain_ids.add(c["domain_id"])

        domain_vals: dict[str, list[tuple[str, str]]] = {}
        if all_domain_ids:
            try:
                placeholders = ", ".join(f":d{i}" for i in range(len(all_domain_ids)))
                params = {f"d{i}": v for i, v in enumerate(all_domain_ids)}
                drows = await self.db.execute(text(
                    f"SELECT d.domainid, a.value, a.description "
                    f"FROM maximo_zz_domain d "
                    f"JOIN maximo_zz_domain_alndomain a ON d.maxdomainid = a._parent_key "
                    f"WHERE d.domainid IN ({placeholders}) "
                    f"  AND a.value IS NOT NULL AND a.value != '' "
                    f"ORDER BY d.domainid, a.value"
                ), params)
                for dr in drows.fetchall():
                    domain_vals.setdefault(dr.domainid, []).append(
                        (dr.value, dr.description or "")
                    )
            except Exception as e:
                log.warning("載入 domain values 失敗: %s", e)

        # 4) 組裝 schema text
        # 引入欄位名對應
        from app.services.maximo_nl2sql import MaximoNL2SQL
        attr_col_map = MaximoNL2SQL._ATTR_COL
        obj_table_map = MaximoNL2SQL._OBJ_TABLE

        lines = ["## Maximo 資料庫 Schema（RAG 篩選，僅顯示相關表與欄位）"]

        # 全表摘要
        lines.append("\n### 全部可用資料表")
        for t in all_tables:
            lines.append(f"- {t.table_name}：{t.description[:60]}...")

        # 各表詳細欄位
        allowed_tables: set[str] = set()
        for t in tables:
            obj = t.get("object_name", "")
            table_name = t.get("table_name", "")
            allowed_tables.add(table_name)

            lines.append(f"\n### {table_name}（Maximo {obj}）")
            if t.get("fk_relations"):
                fk_str = ", ".join(f"{k}→{v}" for k, v in t["fk_relations"].items())
                lines.append(f"FK：{fk_str}")

            cols = columns_by_obj.get(obj, [])
            for c in cols:
                attr_upper = c["attribute_name"].upper()
                col_ref = attr_col_map.get(attr_upper, c["attribute_name"].lower())
                label = c["title"]
                did = c.get("domain_id", "")
                if did and did in domain_vals:
                    pairs = ", ".join(
                        f'"{v}"={desc}' if desc else f'"{v}"'
                        for v, desc in domain_vals[did][:15]
                    )
                    lines.append(f"- {col_ref} — {label}（值域：{pairs}）")
                else:
                    lines.append(f"- {col_ref} — {label}")

        # 也加入沒有 object_name 但被選中的 ETL 表
        for t in tables:
            if not t.get("object_name") and t.get("table_name"):
                allowed_tables.add(t["table_name"])
                lines.append(f"\n### {t['table_name']}")
                lines.append(f"說明：{t['description']}")
                if t.get("key_columns"):
                    lines.append(f"主要欄位：{', '.join(t['key_columns'])}")
                if t.get("fk_relations"):
                    fk_str = ", ".join(f"{k}→{v}" for k, v in t["fk_relations"].items())
                    lines.append(f"FK：{fk_str}")

        # 也把全部 ETL 表加入 allowed（讓 LLM 可以 JOIN）
        for t in all_tables:
            allowed_tables.add(t.table_name)

        schema_text = "\n".join(lines)
        return schema_text, allowed_tables

    def _collection_ready(self) -> bool:
        """檢查 Qdrant collections 是否存在且有資料。"""
        try:
            collections = self.qdrant.get_collections().collections
            names = {c.name for c in collections}
            if self.TABLES_COLLECTION not in names or self.ATTRS_COLLECTION not in names:
                return False
            info = self.qdrant.get_collection(self.TABLES_COLLECTION)
            return info.points_count > 0
        except Exception:
            return False
