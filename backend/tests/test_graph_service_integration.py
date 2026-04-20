"""Integration tests against a real Neo4j instance.

預設 skip；設 NEO4J_INTEGRATION=1 並提供 NEO4J_URI/USER/PASSWORD 才會跑。

Usage:
    NEO4J_URI=bolt://192.168.1.11:7687 \\
    NEO4J_USER=neo4j \\
    NEO4J_PASSWORD='<pwd>' \\
    NEO4J_INTEGRATION=1 \\
    pytest tests/test_graph_service_integration.py -v
"""
import os
import pytest

from app.services.graph_service import GraphService

pytestmark = pytest.mark.skipif(
    os.getenv("NEO4J_INTEGRATION") != "1",
    reason="set NEO4J_INTEGRATION=1 to enable",
)


@pytest.fixture
def real_svc():
    svc = GraphService()
    yield svc
    svc.close()


def test_ping(real_svc):
    """確認能連上部署機上的 aikm-neo4j。"""
    assert real_svc.ping() is True


def test_ping_after_reconnect(real_svc):
    assert real_svc.ping() is True
    real_svc.close()
    assert real_svc.ping() is True
