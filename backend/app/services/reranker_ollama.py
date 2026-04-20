"""Ollama BGE reranker adapter — GPU-backed, much faster than local CPU BGE.

Uses Ollama `/api/embed` to fetch embeddings for query + documents, then
computes cosine similarity as relevance score. Batch-embeds all inputs in a
single HTTP call for minimal latency.
"""
from __future__ import annotations

import json
import logging
import math
import time
import urllib.request
import urllib.error
from typing import Optional

from app.config import get_settings
from app.models.reranker import RerankerResult, RerankerError


logger = logging.getLogger(__name__)


# Max characters per document fed to Ollama embed (bge-reranker-v2-m3
# has a 512-token context window). ~2000 chars is a safe upper bound
# for CJK + mixed text without overflowing.
_MAX_DOC_CHARS = 2000


class OllamaReranker:
    """Ollama-backed reranker using BGE embeddings + cosine similarity."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        settings = get_settings()

        # Prefer dedicated reranker URL; fall back to ollama_base_url or
        # strip /v1 from the chat endpoint.
        raw_url = (
            base_url
            or getattr(settings, "ollama_reranker_url", "")
            or getattr(settings, "ollama_base_url", "")
            or settings.ollama_chat_url
        )
        self.base_url = raw_url.replace("/v1", "").rstrip("/")

        self.model = model or getattr(
            settings, "ollama_reranker_model", "linux6200/bge-reranker-v2-m3:latest"
        )
        self.timeout = timeout if timeout is not None else settings.reranker_timeout

        self._available: Optional[bool] = None

    @property
    def provider_name(self) -> str:
        return "ollama"

    # ---- HTTP helpers -------------------------------------------------

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Call Ollama `/api/embed` with a list of inputs; return embeddings."""
        payload = {
            "model": self.model,
            "input": texts,
            "keep_alive": -1,
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/embed",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
        except urllib.error.URLError as e:
            raise RerankerError(f"Ollama reranker HTTP error: {e}") from e
        except TimeoutError as e:  # pragma: no cover
            raise RerankerError(f"Ollama reranker timeout: {e}") from e

        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            raise RerankerError(f"Ollama reranker invalid JSON: {e}") from e

        embeddings = data.get("embeddings")
        if not embeddings or not isinstance(embeddings, list):
            raise RerankerError(
                f"Ollama reranker: no embeddings in response (keys={list(data.keys())})"
            )
        return embeddings

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = 0.0
        na = 0.0
        nb = 0.0
        for x, y in zip(a, b):
            dot += x * y
            na += x * x
            nb += y * y
        if na == 0.0 or nb == 0.0:
            return 0.0
        return dot / (math.sqrt(na) * math.sqrt(nb))

    @staticmethod
    def _normalize(score: float) -> float:
        """Map cosine similarity in [-1, 1] to [0, 1]."""
        return max(0.0, min(1.0, (score + 1.0) / 2.0))

    # ---- Public API ---------------------------------------------------

    def is_available(self) -> bool:
        """Check endpoint reachability + model availability (cached)."""
        if self._available is not None:
            return self._available
        try:
            embs = self._embed_batch(["ping"])
            self._available = bool(embs and embs[0])
        except Exception as e:
            logger.warning(f"[ollama_reranker] unavailable: {e}")
            self._available = False
        return self._available

    def rerank(
        self,
        query: str,
        documents: list[dict],
        top_n: Optional[int] = None,
        content_key: str = "content",
    ) -> RerankerResult:
        """Rerank docs by cosine similarity between query and doc embeddings."""
        if not documents:
            return RerankerResult(
                documents=[],
                provider=self.provider_name,
                latency_ms=0.0,
                fallback_used=False,
            )

        if not query or not query.strip():
            return self._original_order(documents, reason="empty_query")

        if len(documents) == 1:
            doc = documents[0].copy()
            doc["relevance_score"] = 1.0
            return RerankerResult(
                documents=[doc],
                provider=self.provider_name,
                latency_ms=0.0,
                fallback_used=False,
                original_ranks=[1],
            )

        settings = get_settings()
        top_n = top_n or settings.rerank_top_n

        # Extract doc texts with same fallback keys as BGE/Cohere
        doc_texts: list[str] = []
        for doc in documents:
            text = doc.get(content_key, "")
            if not text:
                text = doc.get("description", "") or doc.get("text", "") or ""
            # Truncate to protect reranker context window
            doc_texts.append(text[:_MAX_DOC_CHARS] if text else "")

        start = time.time()
        try:
            # Single batch call: [query, doc1, doc2, ...]
            all_inputs = [query] + doc_texts
            embeddings = self._embed_batch(all_inputs)

            if len(embeddings) != len(all_inputs):
                raise RerankerError(
                    f"Ollama reranker: expected {len(all_inputs)} embeddings, "
                    f"got {len(embeddings)}"
                )

            q_emb = embeddings[0]
            doc_embs = embeddings[1:]

            scored: list[tuple[int, float]] = []
            for idx, d_emb in enumerate(doc_embs):
                raw = self._cosine(q_emb, d_emb)
                scored.append((idx, self._normalize(raw)))

            scored.sort(key=lambda t: t[1], reverse=True)

            elapsed_ms = (time.time() - start) * 1000.0

            reranked_docs: list[dict] = []
            original_ranks: list[int] = []
            for original_idx, score in scored[:top_n]:
                doc = documents[original_idx].copy()
                doc["relevance_score"] = float(score)
                reranked_docs.append(doc)
                original_ranks.append(original_idx + 1)

            logger.info(
                f"Ollama rerank completed: query='{query[:50]}...', "
                f"docs={len(documents)}, top_n={top_n}, "
                f"latency={elapsed_ms:.1f}ms"
            )

            return RerankerResult(
                documents=reranked_docs,
                provider=self.provider_name,
                latency_ms=elapsed_ms,
                fallback_used=False,
                original_ranks=original_ranks,
            )

        except RerankerError:
            raise
        except Exception as e:
            logger.error(f"[ollama_reranker] rerank error: {e}")
            raise RerankerError(f"Ollama rerank failed: {e}") from e

    # ---- Helpers ------------------------------------------------------

    def _original_order(self, documents: list[dict], reason: str) -> RerankerResult:
        logger.debug(f"[ollama_reranker] original order: {reason}")
        reranked_docs: list[dict] = []
        original_ranks: list[int] = []
        for idx, doc in enumerate(documents):
            doc_copy = doc.copy()
            doc_copy["relevance_score"] = doc.get("score", 0.0)
            reranked_docs.append(doc_copy)
            original_ranks.append(idx + 1)
        return RerankerResult(
            documents=reranked_docs,
            provider=self.provider_name,
            latency_ms=0.0,
            fallback_used=False,
            original_ranks=original_ranks,
        )


# Global singleton
_ollama_reranker: Optional[OllamaReranker] = None


def get_ollama_reranker() -> OllamaReranker:
    """Get the global OllamaReranker instance."""
    global _ollama_reranker
    if _ollama_reranker is None:
        _ollama_reranker = OllamaReranker()
    return _ollama_reranker
