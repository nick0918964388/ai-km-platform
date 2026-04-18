"""Admin Knowledge Graph 監控 API (Phase 3 W3-T3)。

目前為骨架 + mock 回應；當 W1-T3（真 ETL）完成，Neo4j 有資料後
會自動切到 graph_service 的真實 count。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import require_admin
from app.services.graph_service import get_graph_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/kg", tags=["admin-kg"])


class SparseEntity(BaseModel):
    type: str
    code: Optional[str] = None
    id: Optional[str] = None
    edges: int


class KGStats(BaseModel):
    node_counts: dict[str, int]
    edge_counts: dict[str, int]
    clean_coverage: float
    sparse_entities: list[SparseEntity]
    last_etl_time: datetime | None
    last_etl_status: Literal["success", "failed", "running", "never"]
    source: Literal["real", "mock"]


class RebuildResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running"]
    message: str


class ETLLogResponse(BaseModel):
    lines: list[str]
    source: Literal["real", "mock"]


# ── Mock 資料（W1-T3 ETL 未完成時使用） ─────────────────────────────
_MOCK_NODE_COUNTS = {
    "WorkOrder": 7995,
    "Asset": 10662,
    "ClassStructure": 193,
    "ServiceRequest": 375,
    "SOP": 0,
    "Part": 0,
}
_MOCK_EDGE_COUNTS = {
    "PERFORMED_ON": 7995,
    "CLASSIFIED_AS": 10462,
    "REPORTED_ON": 375,
    "PARENT_OF": 192,
}
_MOCK_SPARSE_ENTITIES = [
    SparseEntity(type="FaultCode", code="FC-BRK-003", edges=1),
    SparseEntity(type="FaultCode", code="FC-ENG-021", edges=2),
    SparseEntity(type="SOP", id="SOP-BRK-001", edges=0),
]


@router.get("/stats", response_model=KGStats)
async def get_kg_stats(admin: dict = Depends(require_admin)) -> KGStats:
    """回傳知識圖譜統計；若 Neo4j 無資料則回 mock。"""
    graph = get_graph_service()
    real_node_counts: dict[str, int] = {}
    real_edge_counts: dict[str, int] = {}

    if graph.ping():
        try:
            real_node_counts = graph.count_nodes_by_label()
            real_edge_counts = graph.count_edges_by_type()
        except Exception as e:
            logger.warning("KG real stats query failed: %s", e)
            real_node_counts = {}
            real_edge_counts = {}

    has_real_data = bool(real_node_counts) and sum(real_node_counts.values()) > 0

    if has_real_data:
        return KGStats(
            node_counts=real_node_counts,
            edge_counts=real_edge_counts,
            clean_coverage=0.0,  # W1-T3 補真實覆蓋率計算
            sparse_entities=[],
            last_etl_time=None,
            last_etl_status="never",
            source="real",
        )

    # Mock 回應
    return KGStats(
        node_counts=_MOCK_NODE_COUNTS,
        edge_counts=_MOCK_EDGE_COUNTS,
        clean_coverage=0.741,
        sparse_entities=_MOCK_SPARSE_ENTITIES,
        last_etl_time=None,
        last_etl_status="never",
        source="mock",
    )


@router.post("/rebuild", response_model=RebuildResponse)
async def trigger_rebuild(
    full: bool = False,
    admin: dict = Depends(require_admin),
) -> RebuildResponse:
    """觸發 ETL rebuild；目前為 stub，W1-T3 完成後接真實 job。"""
    return RebuildResponse(
        job_id="mock-job-20260418-120000",
        status="queued",
        message=(
            "W1-T3 ETL 尚未實作，此為 stub 回應。"
            f"full={'true' if full else 'false'}"
        ),
    )


@router.get("/etl-log", response_model=ETLLogResponse)
async def get_etl_log(
    lines: int = 50,
    admin: dict = Depends(require_admin),
) -> ETLLogResponse:
    """回傳最近 N 行 ETL log；目前為 mock。"""
    lines = max(1, min(lines, 500))
    mock_lines = [
        "[mock] W1-T3 ETL 尚未實作",
        "[mock] 將顯示 scripts/build_graph_neo4j.py 的 log tail",
        "[mock] 包含進度條、錯誤計數、耗時",
    ]
    return ETLLogResponse(lines=mock_lines[:lines], source="mock")
