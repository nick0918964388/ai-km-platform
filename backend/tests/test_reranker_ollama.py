"""Unit tests for OllamaReranker.

All tests except the `integration` suite mock out `urllib.request.urlopen`,
so they run without any network dependency.
"""
from __future__ import annotations

import io
import json
import math
import os
from typing import Optional
from unittest.mock import patch, MagicMock

import pytest

from app.services.reranker_ollama import OllamaReranker, _MAX_DOC_CHARS
from app.models.reranker import RerankerError


def _make_urlopen_mock(response_payload: dict, *, captured_request: Optional[dict] = None):
    """Return a context-manager-compatible mock mimicking urllib.request.urlopen."""

    def _urlopen(req, timeout=None):
        if captured_request is not None:
            captured_request["url"] = req.full_url
            captured_request["body"] = json.loads(req.data.decode("utf-8"))
            captured_request["timeout"] = timeout

        cm = MagicMock()
        cm.__enter__.return_value.read.return_value = json.dumps(response_payload).encode()
        cm.__exit__.return_value = False
        return cm

    return _urlopen


def _embedding(n_dim: int, seed: float) -> list[float]:
    """Make a deterministic fake embedding vector."""
    return [math.sin(seed + i) for i in range(n_dim)]


# --- Tests ----------------------------------------------------------------


def test_cosine_similarity_correctness():
    # Identical vectors → cosine 1.0
    v = [1.0, 2.0, 3.0]
    assert OllamaReranker._cosine(v, v) == pytest.approx(1.0, abs=1e-9)

    # Orthogonal vectors → cosine 0.0
    assert OllamaReranker._cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    # Anti-parallel → cosine -1.0
    assert OllamaReranker._cosine([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    # Zero vector → 0.0 (no division by zero)
    assert OllamaReranker._cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_normalize_maps_to_unit_interval():
    assert OllamaReranker._normalize(1.0) == pytest.approx(1.0)
    assert OllamaReranker._normalize(-1.0) == pytest.approx(0.0)
    assert OllamaReranker._normalize(0.0) == pytest.approx(0.5)
    # Clamping
    assert OllamaReranker._normalize(2.0) == 1.0
    assert OllamaReranker._normalize(-2.0) == 0.0


def test_empty_documents_returns_empty():
    r = OllamaReranker(base_url="http://fake", model="m", timeout=1.0)
    result = r.rerank("anything", [])
    assert result.documents == []
    assert result.provider == "ollama"


def test_empty_query_returns_original_order():
    r = OllamaReranker(base_url="http://fake", model="m", timeout=1.0)
    docs = [{"content": "a"}, {"content": "b"}]
    result = r.rerank("   ", docs)
    assert [d["content"] for d in result.documents] == ["a", "b"]
    assert result.provider == "ollama"
    # original_ranks should be 1-indexed preserving order
    assert result.original_ranks == [1, 2]


def test_single_document_short_circuit():
    r = OllamaReranker(base_url="http://fake", model="m", timeout=1.0)
    result = r.rerank("q", [{"content": "only"}])
    assert len(result.documents) == 1
    assert result.documents[0]["relevance_score"] == 1.0


def test_rerank_orders_by_cosine_score():
    """Highest cosine → first."""
    dim = 8
    # Query embedding identical to doc #1; doc #0 orthogonal-ish
    q_emb = [1.0] + [0.0] * (dim - 1)
    doc0_emb = [0.0, 1.0] + [0.0] * (dim - 2)  # orthogonal
    doc1_emb = [1.0] + [0.0] * (dim - 1)       # identical
    doc2_emb = [0.5] + [0.5] * (dim - 1)       # partial

    payload = {"embeddings": [q_emb, doc0_emb, doc1_emb, doc2_emb]}
    captured = {}

    r = OllamaReranker(base_url="http://fake", model="bge", timeout=1.0)
    docs = [
        {"content": "doc zero"},
        {"content": "doc one"},
        {"content": "doc two"},
    ]

    with patch("urllib.request.urlopen", side_effect=_make_urlopen_mock(payload, captured_request=captured)):
        result = r.rerank("query", docs, top_n=3)

    # Doc 1 (identical) must be first
    assert result.documents[0]["content"] == "doc one"
    # Score should be ~1 after normalization
    assert result.documents[0]["relevance_score"] == pytest.approx(1.0, abs=1e-6)
    assert result.provider == "ollama"
    assert not result.fallback_used
    # Verify we sent a single batched call
    assert captured["url"].endswith("/api/embed")
    assert captured["body"]["model"] == "bge"
    assert captured["body"]["input"] == ["query", "doc zero", "doc one", "doc two"]
    assert captured["body"]["keep_alive"] == -1


def test_top_n_respected():
    dim = 4
    # Three docs, top_n=2 → only 2 returned
    q = [1.0, 0.0, 0.0, 0.0]
    embs = [q, [0.9, 0.1, 0, 0], [0.2, 0.8, 0, 0], [0.99, 0, 0, 0]]
    payload = {"embeddings": embs}

    r = OllamaReranker(base_url="http://fake", model="m", timeout=1.0)
    docs = [{"content": f"d{i}"} for i in range(3)]

    with patch("urllib.request.urlopen", side_effect=_make_urlopen_mock(payload)):
        result = r.rerank("q", docs, top_n=2)

    assert len(result.documents) == 2
    # Top-ranked should be d2 (0.99) then d0 (0.9)
    assert result.documents[0]["content"] == "d2"
    assert result.documents[1]["content"] == "d0"


def test_long_document_truncated_before_embed():
    """Docs longer than _MAX_DOC_CHARS must be cut before sending."""
    long_text = "x" * (_MAX_DOC_CHARS + 500)
    payload = {"embeddings": [[1.0], [1.0]]}
    captured = {}

    r = OllamaReranker(base_url="http://fake", model="m", timeout=1.0)
    docs = [{"content": long_text}, {"content": "short"}]

    with patch("urllib.request.urlopen", side_effect=_make_urlopen_mock(payload, captured_request=captured)):
        r.rerank("q", docs, top_n=2)

    # Captured body[0] is query, body[1] is truncated doc
    sent_inputs = captured["body"]["input"]
    assert len(sent_inputs[1]) == _MAX_DOC_CHARS
    assert sent_inputs[2] == "short"


def test_fallback_content_keys():
    """Falls back to 'description' or 'text' when content_key missing."""
    payload = {"embeddings": [[1.0], [1.0], [1.0]]}
    captured = {}

    r = OllamaReranker(base_url="http://fake", model="m", timeout=1.0)
    docs = [
        {"description": "desc-only"},
        {"text": "text-only"},
    ]

    with patch("urllib.request.urlopen", side_effect=_make_urlopen_mock(payload, captured_request=captured)):
        r.rerank("q", docs, top_n=2)

    inputs = captured["body"]["input"]
    assert inputs[1] == "desc-only"
    assert inputs[2] == "text-only"


def test_missing_embeddings_raises_reranker_error():
    r = OllamaReranker(base_url="http://fake", model="m", timeout=1.0)
    bad_payload = {"error": "model not found"}

    with patch("urllib.request.urlopen", side_effect=_make_urlopen_mock(bad_payload)):
        with pytest.raises(RerankerError):
            r.rerank("q", [{"content": "a"}, {"content": "b"}])


def test_mismatched_embedding_count_raises():
    r = OllamaReranker(base_url="http://fake", model="m", timeout=1.0)
    # Expects 3 (query + 2 docs), server returns 2
    payload = {"embeddings": [[1.0], [1.0]]}

    with patch("urllib.request.urlopen", side_effect=_make_urlopen_mock(payload)):
        with pytest.raises(RerankerError):
            r.rerank("q", [{"content": "a"}, {"content": "b"}])


def test_is_available_cached_on_success():
    payload = {"embeddings": [[1.0]]}
    r = OllamaReranker(base_url="http://fake", model="m", timeout=1.0)

    with patch("urllib.request.urlopen", side_effect=_make_urlopen_mock(payload)) as mock:
        assert r.is_available() is True
        # Second call must not re-hit the network
        assert r.is_available() is True
        assert mock.call_count == 1


def test_is_available_cached_on_failure():
    r = OllamaReranker(base_url="http://fake", model="m", timeout=1.0)

    def _broken(*args, **kwargs):
        raise OSError("connection refused")

    with patch("urllib.request.urlopen", side_effect=_broken) as mock:
        assert r.is_available() is False
        assert r.is_available() is False
        assert mock.call_count == 1


def test_base_url_strips_v1_suffix():
    r = OllamaReranker(base_url="http://host:11434/v1/", model="m", timeout=1.0)
    assert r.base_url == "http://host:11434"


# --- Integration ----------------------------------------------------------

@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_OLLAMA_INTEGRATION") != "1",
    reason="Set RUN_OLLAMA_INTEGRATION=1 to run (requires ollama.webtw.xyz reachable)",
)
def test_integration_real_ollama_rerank():
    """Hit real Ollama. Expects latency < 3s for ~6 docs."""
    import time
    r = OllamaReranker(
        base_url="http://ollama.webtw.xyz:11434",
        model="linux6200/bge-reranker-v2-m3:latest",
        timeout=10.0,
    )
    docs = [
        {"content": "煞車片磨耗檢查與更換程序"},
        {"content": "空調系統濾網更換"},
        {"content": "車門開關異常排除"},
        {"content": "引擎啟動困難診斷"},
        {"content": "輪胎磨耗檢查"},
    ]
    start = time.time()
    result = r.rerank("煞車異響", docs, top_n=3)
    elapsed = time.time() - start

    assert len(result.documents) == 3
    assert result.provider == "ollama"
    assert elapsed < 3.0, f"latency {elapsed:.2f}s exceeds 3s budget"
    # Most relevant should include 煞車片
    contents = [d["content"] for d in result.documents]
    assert any("煞車" in c for c in contents)
