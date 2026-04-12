"""
Maximo Document Search Service
Finds SOP documents related to work orders, fault reports, or fault codes.
Combines structured lookup (fault_sop_mapping) + semantic search (RAG).
"""

import logging
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.services import rag as rag_service

log = logging.getLogger(__name__)


class MaximoDocSearch:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_related_docs(
        self,
        wo_number: str = None,
        fault_code: str = None,
        description: str = None,
        asset_num: str = None,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """Find SOP documents related to a work order, fault code, or description.

        Flow:
        1. If wo_number → lookup work order/fault report details from DB
        2. If fault_code → lookup fault_sop_mapping for explicit mappings
        3. Build search context from available info
        4. Semantic search against knowledge base (text_chunks in Qdrant)
        5. Merge structured + semantic results, deduplicate
        """
        context_parts = []
        structured_results = []

        # 1. Lookup work order or fault report details
        if wo_number:
            # Try work order first
            wo = await self.db.execute(text(
                "SELECT wonum, assetnum, status, worktype FROM maximo_mxwo WHERE wonum = :wo LIMIT 1"
            ), {"wo": wo_number})
            wo_row = wo.fetchone()
            if wo_row:
                context_parts.append(f"工單 {wo_row.wonum} 車號 {wo_row.assetnum} 類型 {wo_row.worktype}")
                asset_num = asset_num or wo_row.assetnum

            # Try fault report
            sr = await self.db.execute(text(
                "SELECT ticketid, description, assetnum, zz_tcms, zz_incident_new "
                "FROM maximo_mxsr WHERE ticketid = :id OR zz_imnum = :id LIMIT 1"
            ), {"id": wo_number})
            sr_row = sr.fetchone()
            if sr_row:
                if sr_row.description:
                    context_parts.append(sr_row.description)
                    description = description or sr_row.description
                if sr_row.zz_tcms:
                    fault_code = fault_code or sr_row.zz_tcms
                asset_num = asset_num or sr_row.assetnum

        # 2. Lookup explicit fault→SOP mappings
        if fault_code:
            mappings = await self.db.execute(text(
                "SELECT document_id, document_name, relevance_score, source "
                "FROM fault_sop_mapping WHERE fault_code = :code ORDER BY relevance_score DESC"
            ), {"code": fault_code})
            for m in mappings.fetchall():
                structured_results.append({
                    "document_id": m.document_id,
                    "document_name": m.document_name,
                    "score": m.relevance_score,
                    "source": "mapping",
                    "match_type": f"故障碼對應：{fault_code}",
                })
            context_parts.append(f"故障碼 {fault_code}")

        # 3. Build search query from context
        if description:
            context_parts.insert(0, description)
        if asset_num:
            context_parts.append(f"車號 {asset_num}")

        search_query = " ".join(context_parts) if context_parts else ""

        # 4. Semantic search against knowledge base (sync call)
        semantic_results = []
        if search_query:
            try:
                results = rag_service.search(
                    query=search_query,
                    top_k=top_k,
                    use_hybrid=True,
                    use_rerank=False,
                )
                for r in results:
                    semantic_results.append({
                        "document_id": r.document_id,
                        "document_name": r.document_name,
                        "score": round(r.score, 3),
                        "source": "semantic",
                        "match_type": "語意搜尋",
                        "content_preview": r.content[:200] if r.content else "",
                        "file_url": r.file_url,
                    })
            except Exception as e:
                log.warning("語意搜尋失敗: %s", e)

        # 5. Merge and deduplicate (structured results first, then semantic)
        seen_docs = set()
        merged = []
        for r in structured_results + semantic_results:
            doc_id = r.get("document_id", "")
            if doc_id and doc_id not in seen_docs:
                seen_docs.add(doc_id)
                merged.append(r)

        return {
            "query_context": search_query,
            "documents": merged[:top_k],
            "total_found": len(merged),
            "has_mapping": len(structured_results) > 0,
        }

    async def add_mapping(
        self,
        fault_code: str,
        document_id: str,
        document_name: str,
        fault_description: str = "",
        source: str = "manual",
    ) -> int:
        """Add a fault_code → document mapping."""
        result = await self.db.execute(text("""
            INSERT INTO fault_sop_mapping (fault_code, fault_description, document_id, document_name, source)
            VALUES (:code, :desc, :doc_id, :doc_name, :source)
            RETURNING id
        """), {
            "code": fault_code, "desc": fault_description,
            "doc_id": document_id, "doc_name": document_name,
            "source": source,
        })
        await self.db.commit()
        return result.scalar()
