"""BGE Reranker service using local CrossEncoder model."""
import logging
import time
from typing import Optional

from app.config import get_settings
from app.models.reranker import RerankerResult, RerankerError, ModelLoadError


logger = logging.getLogger(__name__)


class BGEReranker:
    """Local BGE-Reranker implementation using sentence-transformers CrossEncoder."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        max_length: Optional[int] = None,
        batch_size: Optional[int] = None,
        device: Optional[str] = None,
    ):
        """
        Initialize BGE Reranker.

        Args:
            model_name: Hugging Face model identifier (default from config)
            max_length: Maximum token length (default from config)
            batch_size: Batch size for inference (default from config)
            device: "cpu", "cuda", or None for auto-detect
        """
        settings = get_settings()
        self._model_name = model_name or settings.bge_model_name
        self._max_length = max_length or settings.bge_max_length
        self._batch_size = batch_size or settings.bge_batch_size
        self._device = device

        self._model = None
        self._load_attempted: bool = False
        self._load_error: Optional[str] = None

    @property
    def provider_name(self) -> str:
        """Return provider identifier."""
        return "bge"

    def _load_model(self) -> bool:
        """
        Lazy load the CrossEncoder model.

        Returns:
            True if model loaded successfully, False otherwise.
        """
        if self._model is not None:
            return True

        if self._load_attempted:
            return False

        self._load_attempted = True

        try:
            from sentence_transformers import CrossEncoder

            logger.info(f"Loading BGE reranker model: {self._model_name}")
            start_time = time.time()

            self._model = CrossEncoder(
                self._model_name,
                max_length=self._max_length,
                device=self._device,
            )

            elapsed = time.time() - start_time
            logger.info(f"BGE reranker model loaded in {elapsed:.2f}s")
            return True

        except ImportError as e:
            self._load_error = f"sentence-transformers not installed: {e}"
            logger.error(self._load_error)
            return False

        except Exception as e:
            self._load_error = f"Failed to load BGE model: {e}"
            logger.error(self._load_error)
            return False

    def is_available(self) -> bool:
        """Check if BGE reranker is available (model loaded successfully)."""
        return self._load_model()

    def rerank(
        self,
        query: str,
        documents: list[dict],
        top_n: Optional[int] = None,
        content_key: str = "content",
    ) -> RerankerResult:
        """
        Rerank documents by relevance to query using BGE CrossEncoder.

        Args:
            query: Search query string
            documents: List of document dicts with content
            top_n: Number of results to return (default: from config)
            content_key: Key to extract text from documents

        Returns:
            RerankerResult with reranked documents and metadata

        Raises:
            ModelLoadError: If model cannot be loaded
            RerankerError: If reranking fails
        """
        # Handle edge cases
        if not documents:
            return RerankerResult(
                documents=[],
                provider=self.provider_name,
                latency_ms=0.0,
                fallback_used=False,
            )

        # Skip reranking for empty query
        if not query or not query.strip():
            logger.debug("Empty query, returning original order")
            return self._return_original_order(documents, reason="empty_query")

        # Skip reranking for single document
        if len(documents) == 1:
            logger.debug("Single document, skipping reranking")
            doc = documents[0].copy()
            doc["relevance_score"] = 1.0
            return RerankerResult(
                documents=[doc],
                provider=self.provider_name,
                latency_ms=0.0,
                fallback_used=False,
                original_ranks=[1],
            )

        # Load model
        if not self._load_model():
            raise ModelLoadError(self._load_error or "Failed to load BGE model")

        settings = get_settings()
        top_n = top_n or settings.rerank_top_n

        # Extract text content from documents
        doc_texts = []
        for doc in documents:
            text = doc.get(content_key, "")
            if not text:
                text = doc.get("description", "") or doc.get("text", "") or ""
            doc_texts.append(text)

        # Create query-document pairs
        pairs = [(query, text) for text in doc_texts]

        start_time = time.time()

        try:
            # Get scores from CrossEncoder
            scores = self._model.predict(
                pairs,
                batch_size=self._batch_size,
                show_progress_bar=False,
            )

            elapsed_ms = (time.time() - start_time) * 1000

            # Create list of (index, score) and sort by score descending
            scored_docs = list(enumerate(scores))
            scored_docs.sort(key=lambda x: x[1], reverse=True)

            # Build reranked result list
            reranked_docs = []
            original_ranks = []
            for rank, (original_idx, score) in enumerate(scored_docs[:top_n]):
                doc = documents[original_idx].copy()
                # Normalize score to 0-1 range (BGE scores can be negative)
                normalized_score = self._normalize_score(score)
                doc["relevance_score"] = normalized_score
                reranked_docs.append(doc)
                original_ranks.append(original_idx + 1)  # 1-indexed

            logger.info(
                f"BGE rerank completed: query='{query[:50]}...', "
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

        except Exception as e:
            logger.error(f"BGE rerank error: {e}")
            raise RerankerError(f"BGE rerank failed: {e}")

    def _normalize_score(self, score: float) -> float:
        """
        Normalize BGE score to 0-1 range using sigmoid.

        BGE scores can range from negative to positive.
        """
        import math
        try:
            return 1.0 / (1.0 + math.exp(-score))
        except OverflowError:
            return 0.0 if score < 0 else 1.0

    def _return_original_order(
        self,
        documents: list[dict],
        reason: str,
    ) -> RerankerResult:
        """Return documents in original order (no reranking)."""
        reranked_docs = []
        original_ranks = []
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
_bge_reranker: Optional[BGEReranker] = None


def get_bge_reranker() -> BGEReranker:
    """Get the global BGEReranker instance."""
    global _bge_reranker
    if _bge_reranker is None:
        _bge_reranker = BGEReranker()
    return _bge_reranker
