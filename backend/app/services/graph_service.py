"""Neo4j Graph Service — KG 查詢封裝（Phase 3）"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, TypeVar
from contextlib import contextmanager
import os
import logging

from neo4j import GraphDatabase, Driver
from neo4j.exceptions import ServiceUnavailable, AuthError

from .circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

T = TypeVar("T")


class GraphUnavailableError(RuntimeError):
    """Circuit breaker 開啟時拋出。"""


@dataclass
class GraphEntity:
    entity_id: str
    label: str
    properties: dict[str, Any]


@dataclass
class GraphEdge:
    src: str
    dst: str
    rel_type: str
    properties: dict[str, Any]


@dataclass
class GraphPath:
    nodes: list[GraphEntity]
    edges: list[GraphEdge]
    length: int


class GraphService:
    """Neo4j 查詢服務；封裝 driver、connection pool、circuit breaker。"""

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        max_connection_lifetime: int = 3600,
        max_connection_pool_size: int = 50,
    ):
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://neo4j:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "")

        self._driver: Driver | None = None
        self._max_lifetime = max_connection_lifetime
        self._max_pool = max_connection_pool_size
        self._breaker = CircuitBreaker(
            name="neo4j",
            failure_threshold=5,
            recovery_timeout=30.0,
        )

    def connect(self) -> None:
        """Lazy 建立 driver；失敗會讓 _driver 維持 None 並 raise。"""
        if self._driver is not None:
            return
        driver = GraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password),
            max_connection_lifetime=self._max_lifetime,
            max_connection_pool_size=self._max_pool,
        )
        try:
            driver.verify_connectivity()
        except (ServiceUnavailable, AuthError) as e:
            logger.error("Neo4j connect failed: %s", e)
            driver.close()
            raise
        self._driver = driver

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    @contextmanager
    def _session(self):
        self.connect()
        assert self._driver is not None
        with self._driver.session() as session:
            yield session

    def _guarded(self, fn: Callable[[], T]) -> T:
        """以 circuit breaker 包裹呼叫；OPEN 時直接 raise。"""
        if not self._breaker.is_available:
            raise GraphUnavailableError(f"neo4j breaker is {self._breaker.state.value}")
        try:
            result = fn()
            self._breaker.record_success()
            return result
        except Exception:
            self._breaker.record_failure()
            raise

    # ----- 公開 API -----

    def ping(self) -> bool:
        """健康檢查；失敗時回 False（不 raise）。"""
        try:
            def _run():
                with self._session() as s:
                    rec = s.run("RETURN 1 AS n").single()
                    return rec is not None and rec["n"] == 1
            return self._guarded(_run)
        except Exception:
            return False

    def neighbors(
        self,
        entity_id: str,
        label: str,
        id_field: str,
        depth: int = 1,
        rel_types: list[str] | None = None,
        limit: int = 50,
    ) -> list[GraphEntity]:
        """取得起點實體 N 跳內的鄰居節點。"""
        if depth < 1 or depth > 5:
            raise ValueError("depth must be 1..5")

        rel_filter = f":{'|'.join(rel_types)}" if rel_types else ""
        cypher = (
            f"MATCH (n:{label} {{{id_field}: $eid}})-[{rel_filter}*1..{depth}]-(m) "
            f"RETURN DISTINCT m LIMIT $limit"
        )
        try:
            return self._guarded(
                lambda: self._run_and_parse_nodes(cypher, {"eid": entity_id, "limit": limit})
            )
        except Exception as e:
            logger.warning("neighbors query failed: %s", e)
            return []

    def top_related(
        self,
        entity_id: str,
        src_label: str,
        src_id_field: str,
        rel_type: str,
        target_label: str,
        limit: int = 3,
    ) -> list[GraphEntity]:
        """目標類型中與起點最相關的 top-N（by edge count）。"""
        cypher = (
            f"MATCH (a:{src_label} {{{src_id_field}: $eid}})-[:{rel_type}]-(b:{target_label}) "
            f"WITH b, count(*) AS weight "
            f"ORDER BY weight DESC "
            f"LIMIT $limit "
            f"RETURN b"
        )
        try:
            return self._guarded(
                lambda: self._run_and_parse_nodes(cypher, {"eid": entity_id, "limit": limit})
            )
        except Exception as e:
            logger.warning("top_related failed: %s", e)
            return []

    def shortest_path(
        self,
        src_label: str,
        src_id_field: str,
        src_id: str,
        dst_label: str,
        dst_id_field: str,
        dst_id: str,
        max_depth: int = 5,
    ) -> GraphPath | None:
        """兩節點最短路徑。"""
        cypher = (
            f"MATCH p = shortestPath("
            f"(a:{src_label} {{{src_id_field}: $src}})-[*..{max_depth}]-"
            f"(b:{dst_label} {{{dst_id_field}: $dst}})"
            f") RETURN p LIMIT 1"
        )
        try:
            return self._guarded(
                lambda: self._run_and_parse_path(cypher, {"src": src_id, "dst": dst_id})
            )
        except Exception as e:
            logger.warning("shortest_path failed: %s", e)
            return None

    def similar_cases(self, wo_id: str, limit: int = 3) -> list[GraphEntity]:
        """相似工單（相同 ClassStructure 的 Asset 之 WorkOrder）。"""
        cypher = """
        MATCH (wo1:WorkOrder {wonum: $wo})-[:PERFORMED_ON]->(a1:Asset)-[:CLASSIFIED_AS]->(cs:ClassStructure)
        MATCH (cs)<-[:CLASSIFIED_AS]-(a2:Asset)<-[:PERFORMED_ON]-(wo2:WorkOrder)
        WHERE wo1 <> wo2
        WITH wo2, count(*) AS score
        ORDER BY score DESC, wo2.reportdate DESC
        LIMIT $limit
        RETURN wo2
        """
        try:
            return self._guarded(
                lambda: self._run_and_parse_nodes(cypher, {"wo": wo_id, "limit": limit})
            )
        except Exception as e:
            logger.warning("similar_cases failed: %s", e)
            return []

    def recommended_sops(self, fault_code: str, limit: int = 3) -> list[GraphEntity]:
        """給定故障代碼推薦 SOP（Phase 3.1 待資料）。"""
        cypher = """
        MATCH (fc:FaultCode {code: $fc})-[r:TYPICALLY_REQUIRES]->(sop:SOP)
        RETURN sop ORDER BY r.success_rate DESC LIMIT $limit
        """
        try:
            return self._guarded(
                lambda: self._run_and_parse_nodes(cypher, {"fc": fault_code, "limit": limit})
            )
        except Exception as e:
            logger.warning("recommended_sops failed: %s", e)
            return []

    def community_of(self, entity_id: str, label: str, id_field: str) -> int | None:
        """實體的社群 ID；需 GDS 預計算，Phase 3.1 補。"""
        return None

    def count_nodes_by_label(self) -> dict[str, int]:
        """統計各 label 的節點數。Neo4j 空或錯誤時回空 dict。"""
        cypher = (
            "CALL db.labels() YIELD label "
            "CALL { WITH label MATCH (n) WHERE label IN labels(n) RETURN count(n) AS c } "
            "RETURN label, c"
        )
        try:
            def _run():
                with self._session() as s:
                    result = s.run(cypher)
                    return {r["label"]: r["c"] for r in result}
            return self._guarded(_run)
        except Exception as e:
            logger.warning("count_nodes_by_label failed: %s", e)
            return {}

    def count_edges_by_type(self) -> dict[str, int]:
        """統計各 relationship type 的邊數。Neo4j 空或錯誤時回空 dict。"""
        cypher = (
            "CALL db.relationshipTypes() YIELD relationshipType AS rt "
            "CALL { WITH rt MATCH ()-[r]->() WHERE type(r) = rt RETURN count(r) AS c } "
            "RETURN rt, c"
        )
        try:
            def _run():
                with self._session() as s:
                    result = s.run(cypher)
                    return {r["rt"]: r["c"] for r in result}
            return self._guarded(_run)
        except Exception as e:
            logger.warning("count_edges_by_type failed: %s", e)
            return {}

    # ----- 內部工具 -----

    def _run_and_parse_nodes(self, cypher: str, params: dict) -> list[GraphEntity]:
        with self._session() as s:
            result = s.run(cypher, **params)
            entities: list[GraphEntity] = []
            for record in result:
                for val in record.values():
                    if hasattr(val, "labels"):
                        labels = list(val.labels)
                        entities.append(GraphEntity(
                            entity_id=val.element_id,
                            label=labels[0] if labels else "Unknown",
                            properties=dict(val),
                        ))
            return entities

    def _run_and_parse_path(self, cypher: str, params: dict) -> GraphPath | None:
        with self._session() as s:
            result = s.run(cypher, **params).single()
            if not result:
                return None
            p = result["p"]
            nodes = [GraphEntity(
                entity_id=n.element_id,
                label=list(n.labels)[0] if n.labels else "Unknown",
                properties=dict(n),
            ) for n in p.nodes]
            edges = [GraphEdge(
                src=r.start_node.element_id,
                dst=r.end_node.element_id,
                rel_type=r.type,
                properties=dict(r),
            ) for r in p.relationships]
            return GraphPath(nodes=nodes, edges=edges, length=len(edges))


_graph_service: GraphService | None = None


def get_graph_service() -> GraphService:
    global _graph_service
    if _graph_service is None:
        _graph_service = GraphService()
    return _graph_service
