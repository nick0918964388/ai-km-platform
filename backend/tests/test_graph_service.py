"""Unit tests for GraphService — mock Neo4j driver。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from app.services.graph_service import (
    GraphService,
    GraphEntity,
    GraphPath,
    GraphUnavailableError,
    get_graph_service,
)


# ---------- helpers ----------

def _fake_node(element_id: str, labels: list[str], props: dict):
    n = MagicMock()
    n.element_id = element_id
    n.labels = labels
    n.__iter__ = lambda self: iter(props)
    n.keys.return_value = list(props.keys())
    n.items.return_value = list(props.items())
    # dict(node) 需要 mapping 協定；直接讓 MagicMock 支援 keys + __getitem__
    n.__getitem__ = lambda self, k: props[k]
    # hasattr(val, 'labels') 已 True
    return n


def _fake_rel(start_id: str, end_id: str, rel_type: str, props: dict):
    r = MagicMock()
    r.start_node = MagicMock(element_id=start_id)
    r.end_node = MagicMock(element_id=end_id)
    r.type = rel_type
    r.keys.return_value = list(props.keys())
    r.items.return_value = list(props.items())
    r.__getitem__ = lambda self, k: props[k]
    return r


def _make_driver_with_session(session_mock):
    """回傳一個 Driver mock，其 session() 進入 session_mock。"""
    driver = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=session_mock)
    ctx.__exit__ = MagicMock(return_value=False)
    driver.session.return_value = ctx
    driver.verify_connectivity.return_value = None
    return driver


@pytest.fixture
def svc():
    """每個測試獨立實例，避免 breaker 狀態污染。"""
    return GraphService(uri="bolt://fake:7687", user="u", password="p")


# ---------- 1. lazy connect ----------

def test_connect_lazy(svc):
    assert svc._driver is None
    with patch("app.services.graph_service.GraphDatabase.driver") as m:
        fake = MagicMock()
        fake.verify_connectivity.return_value = None
        m.return_value = fake

        svc.connect()
        assert svc._driver is fake
        m.assert_called_once()

        svc.connect()
        assert m.call_count == 1


def test_connect_failure_resets_driver(svc):
    from neo4j.exceptions import ServiceUnavailable
    with patch("app.services.graph_service.GraphDatabase.driver") as m:
        fake = MagicMock()
        fake.verify_connectivity.side_effect = ServiceUnavailable("nope")
        m.return_value = fake

        with pytest.raises(ServiceUnavailable):
            svc.connect()
        assert svc._driver is None


# ---------- 2. ping ----------

def test_ping_returns_true_on_success(svc):
    session = MagicMock()
    record = MagicMock()
    record.__getitem__ = lambda self, k: 1
    session.run.return_value.single.return_value = record

    with patch("app.services.graph_service.GraphDatabase.driver",
               return_value=_make_driver_with_session(session)):
        assert svc.ping() is True


def test_ping_returns_false_on_exception(svc):
    with patch("app.services.graph_service.GraphDatabase.driver") as m:
        m.side_effect = RuntimeError("boom")
        assert svc.ping() is False


# ---------- 3. neighbors cypher 驗證 ----------

def test_neighbors_builds_correct_cypher(svc):
    captured = {}
    session = MagicMock()

    def fake_run(cypher, **params):
        captured["cypher"] = cypher
        captured["params"] = params
        result = MagicMock()
        result.__iter__ = lambda self: iter([])
        return result

    session.run.side_effect = fake_run

    with patch("app.services.graph_service.GraphDatabase.driver",
               return_value=_make_driver_with_session(session)):
        svc.neighbors("WO123", "WorkOrder", "wonum", depth=2,
                      rel_types=["PERFORMED_ON", "CAUSED_BY"], limit=20)

    assert "MATCH (n:WorkOrder {wonum: $eid})" in captured["cypher"]
    assert "*1..2" in captured["cypher"]
    assert "PERFORMED_ON|CAUSED_BY" in captured["cypher"]
    assert captured["params"] == {"eid": "WO123", "limit": 20}


def test_neighbors_no_rel_filter(svc):
    captured = {}
    session = MagicMock()
    session.run.side_effect = lambda cypher, **params: (
        captured.update(cypher=cypher, params=params),
        iter([]),
    )[1]
    result_mock = MagicMock()
    result_mock.__iter__ = lambda self: iter([])
    session.run.return_value = result_mock

    def fake_run(cypher, **params):
        captured["cypher"] = cypher
        return result_mock

    session.run.side_effect = fake_run

    with patch("app.services.graph_service.GraphDatabase.driver",
               return_value=_make_driver_with_session(session)):
        svc.neighbors("A1", "Asset", "assetnum", depth=1)

    assert "[*1..1]" in captured["cypher"]


@pytest.mark.parametrize("depth,ok", [
    (1, True), (5, True), (0, False), (6, False), (-1, False),
])
def test_neighbors_depth_boundary(svc, depth, ok):
    if ok:
        session = MagicMock()
        session.run.return_value = MagicMock(__iter__=lambda self: iter([]))
        with patch("app.services.graph_service.GraphDatabase.driver",
                   return_value=_make_driver_with_session(session)):
            svc.neighbors("x", "L", "id", depth=depth)
    else:
        with pytest.raises(ValueError):
            svc.neighbors("x", "L", "id", depth=depth)


# ---------- 4. top_related ----------

def test_top_related_cypher(svc):
    captured = {}
    session = MagicMock()
    result_mock = MagicMock()
    result_mock.__iter__ = lambda self: iter([])

    def fake_run(cypher, **params):
        captured["cypher"] = cypher
        captured["params"] = params
        return result_mock

    session.run.side_effect = fake_run

    with patch("app.services.graph_service.GraphDatabase.driver",
               return_value=_make_driver_with_session(session)):
        svc.top_related("WO1", "WorkOrder", "wonum", "PERFORMED_ON", "Asset", limit=5)

    c = captured["cypher"]
    assert "(a:WorkOrder {wonum: $eid})-[:PERFORMED_ON]-(b:Asset)" in c
    assert "count(*) AS weight" in c
    assert "ORDER BY weight DESC" in c
    assert captured["params"] == {"eid": "WO1", "limit": 5}


# ---------- 5. shortest_path ----------

def test_shortest_path_returns_path(svc):
    n1 = _fake_node("n1", ["Asset"], {"assetnum": "A1"})
    n2 = _fake_node("n2", ["WorkOrder"], {"wonum": "W1"})
    rel = _fake_rel("n1", "n2", "PERFORMED_ON", {})

    path = MagicMock()
    path.nodes = [n1, n2]
    path.relationships = [rel]

    record = MagicMock()
    record.__getitem__ = lambda self, k: path

    session = MagicMock()
    session.run.return_value.single.return_value = record

    with patch("app.services.graph_service.GraphDatabase.driver",
               return_value=_make_driver_with_session(session)):
        result = svc.shortest_path("Asset", "assetnum", "A1",
                                   "WorkOrder", "wonum", "W1", max_depth=3)

    assert isinstance(result, GraphPath)
    assert result.length == 1
    assert len(result.nodes) == 2
    assert result.edges[0].rel_type == "PERFORMED_ON"


def test_shortest_path_returns_none_when_empty(svc):
    session = MagicMock()
    session.run.return_value.single.return_value = None

    with patch("app.services.graph_service.GraphDatabase.driver",
               return_value=_make_driver_with_session(session)):
        result = svc.shortest_path("A", "id", "1", "B", "id", "2")

    assert result is None


# ---------- 6. similar_cases ----------

def test_similar_cases_cypher(svc):
    captured = {}
    session = MagicMock()
    result_mock = MagicMock()
    result_mock.__iter__ = lambda self: iter([])

    def fake_run(cypher, **params):
        captured["cypher"] = cypher
        captured["params"] = params
        return result_mock

    session.run.side_effect = fake_run

    with patch("app.services.graph_service.GraphDatabase.driver",
               return_value=_make_driver_with_session(session)):
        svc.similar_cases("WO999", limit=5)

    c = captured["cypher"]
    assert ":PERFORMED_ON" in c
    assert ":CLASSIFIED_AS" in c
    assert "wo1 <> wo2" in c
    assert captured["params"] == {"wo": "WO999", "limit": 5}


# ---------- 7. recommended_sops ----------

def test_recommended_sops_cypher(svc):
    captured = {}
    session = MagicMock()
    result_mock = MagicMock()
    result_mock.__iter__ = lambda self: iter([])

    def fake_run(cypher, **params):
        captured["cypher"] = cypher
        captured["params"] = params
        return result_mock

    session.run.side_effect = fake_run

    with patch("app.services.graph_service.GraphDatabase.driver",
               return_value=_make_driver_with_session(session)):
        svc.recommended_sops("FC-001", limit=2)

    c = captured["cypher"]
    assert "FaultCode {code: $fc}" in c
    assert "TYPICALLY_REQUIRES" in c
    assert captured["params"] == {"fc": "FC-001", "limit": 2}


# ---------- 8. circuit breaker ----------

def test_circuit_breaker_opens_on_repeated_failure(svc):
    """連續失敗應使 breaker 切到 OPEN，之後呼叫直接短路不打 driver。"""
    call_count = {"n": 0}

    def boom(*args, **kwargs):
        call_count["n"] += 1
        raise RuntimeError("db down")

    session = MagicMock()
    session.run.side_effect = boom

    with patch("app.services.graph_service.GraphDatabase.driver",
               return_value=_make_driver_with_session(session)):
        # failure_threshold=5；連打 5 次應打開 breaker
        for _ in range(5):
            svc.neighbors("x", "L", "id", depth=1)

        assert svc._breaker.state.value == "open"
        calls_before = call_count["n"]

        # OPEN 狀態下再呼叫：應不打 driver，仍回 []（neighbors 會吞例外）
        result = svc.neighbors("x", "L", "id", depth=1)
        assert result == []
        assert call_count["n"] == calls_before  # 沒有再打 session.run


def test_circuit_breaker_records_success(svc):
    session = MagicMock()
    result_mock = MagicMock()
    result_mock.__iter__ = lambda self: iter([])
    session.run.return_value = result_mock

    with patch("app.services.graph_service.GraphDatabase.driver",
               return_value=_make_driver_with_session(session)):
        svc.neighbors("x", "L", "id", depth=1)

    assert svc._breaker._failure_count == 0
    assert svc._breaker.state.value == "closed"


# ---------- 9. parse nodes ----------

def test_run_and_parse_nodes_extracts_entity(svc):
    n = _fake_node("elem-1", ["Asset"], {"assetnum": "A1", "status": "ACTIVE"})
    record = MagicMock()
    record.values.return_value = [n]

    session = MagicMock()
    result = MagicMock()
    result.__iter__ = lambda self: iter([record])
    session.run.return_value = result

    with patch("app.services.graph_service.GraphDatabase.driver",
               return_value=_make_driver_with_session(session)):
        entities = svc._run_and_parse_nodes("RETURN n", {})

    assert len(entities) == 1
    assert entities[0].entity_id == "elem-1"
    assert entities[0].label == "Asset"


# ---------- 10. singleton ----------

def test_get_graph_service_singleton():
    import app.services.graph_service as mod
    mod._graph_service = None  # 重置
    s1 = get_graph_service()
    s2 = get_graph_service()
    assert s1 is s2


# ---------- 11. count helpers (W3-T3) ----------

def test_count_nodes_by_label_returns_dict(svc):
    session = MagicMock()
    rec1 = MagicMock()
    rec1.__getitem__ = lambda self, k: {"label": "WorkOrder", "c": 7995}[k]
    rec2 = MagicMock()
    rec2.__getitem__ = lambda self, k: {"label": "Asset", "c": 10662}[k]
    result_mock = MagicMock()
    result_mock.__iter__ = lambda self: iter([rec1, rec2])
    session.run.return_value = result_mock

    with patch("app.services.graph_service.GraphDatabase.driver",
               return_value=_make_driver_with_session(session)):
        counts = svc.count_nodes_by_label()

    assert counts == {"WorkOrder": 7995, "Asset": 10662}


def test_count_nodes_by_label_returns_empty_on_error(svc):
    with patch("app.services.graph_service.GraphDatabase.driver") as m:
        m.side_effect = RuntimeError("neo4j down")
        assert svc.count_nodes_by_label() == {}


def test_count_edges_by_type_returns_dict(svc):
    session = MagicMock()
    rec = MagicMock()
    rec.__getitem__ = lambda self, k: {"rt": "PERFORMED_ON", "c": 7995}[k]
    result_mock = MagicMock()
    result_mock.__iter__ = lambda self: iter([rec])
    session.run.return_value = result_mock

    with patch("app.services.graph_service.GraphDatabase.driver",
               return_value=_make_driver_with_session(session)):
        counts = svc.count_edges_by_type()

    assert counts == {"PERFORMED_ON": 7995}


def test_count_edges_by_type_returns_empty_on_error(svc):
    with patch("app.services.graph_service.GraphDatabase.driver") as m:
        m.side_effect = RuntimeError("neo4j down")
        assert svc.count_edges_by_type() == {}
