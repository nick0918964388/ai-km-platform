"""Reranker Factory for multi-provider support with fallback."""
import logging
import time
from typing import Optional

from app.config import get_settings
from app.models.reranker import RerankerResult, RerankerError
from app.services.reranker import CohereReranker, get_cohere_reranker
from app.services.reranker_bge import BGEReranker, get_bge_reranker


logger = logging.getLogger(__name__)


class RerankerFactory:
    """Factory for creating and managing reranker instances with fallback support."""

    def __init__(self):
        self._cohere: Optional[CohereReranker] = None
        self._bge: Optional[BGEReranker] = None

    def _get_cohere(self) -> CohereReranker:
        """Get Cohere reranker instance."""
        if self._cohere is None:
            self._cohere = get_cohere_reranker()
        return self._cohere

    def _get_bge(self) -> BGEReranker:
        """Get BGE reranker instance."""
        if self._bge is None:
            self._bge = get_bge_reranker()
        return self._bge

    def get_reranker(self) -> Optional[CohereReranker | BGEReranker]:
        """
        Get the configured reranker instance.

        Returns:
            Reranker instance based on RERANKER_PROVIDER config, or None if unavailable.

        Behavior:
            - "cohere": Returns CohereReranker if available
            - "bge": Returns BGEReranker if available
            - "auto": Returns CohereReranker if available, else BGEReranker
        """
        settings = get_settings()
        provider = settings.reranker_provider.lower()

        if provider == "cohere":
            reranker = self._get_cohere()
            if reranker.is_available():
                return reranker
            return None

        elif provider == "bge":
            reranker = self._get_bge()
            if reranker.is_available():
                return reranker
            return None

        elif provider == "auto":
            # Try Cohere first, then BGE
            cohere = self._get_cohere()
            if cohere.is_available():
                return cohere

            bge = self._get_bge()
            if bge.is_available():
                return bge

            return None

        else:
            logger.warning(f"Unknown reranker provider: {provider}, falling back to auto")
            return self.get_reranker()  # Recursive with auto

    def is_available(self) -> bool:
        """Check if any reranker is available."""
        return self.get_reranker() is not None

    def get_status(self) -> dict:
        """
        Get status of all reranker providers.

        Returns:
            {
                "cohere": {"available": bool, "reason": str | None},
                "bge": {"available": bool, "reason": str | None},
                "active_provider": str | None,
                "configured_provider": str
            }
        """
        settings = get_settings()

        cohere = self._get_cohere()
        bge = self._get_bge()

        cohere_available = cohere.is_available()
        bge_available = bge.is_available()

        # Determine active provider
        active_reranker = self.get_reranker()
        active_provider = active_reranker.provider_name if active_reranker else None

        return {
            "cohere": {
                "available": cohere_available,
                "reason": None if cohere_available else "API key not configured or invalid",
            },
            "bge": {
                "available": bge_available,
                "reason": None if bge_available else "Model failed to load",
            },
            "active_provider": active_provider,
            "configured_provider": settings.reranker_provider,
        }

    def rerank(
        self,
        query: str,
        documents: list[dict],
        top_n: Optional[int] = None,
        content_key: str = "content",
    ) -> RerankerResult:
        """
        Rerank documents with automatic fallback.

        Args:
            query: Search query string
            documents: List of document dicts with content
            top_n: Number of results to return (default: from config)
            content_key: Key to extract text from documents

        Returns:
            RerankerResult with reranked documents and metadata
        """
        settings = get_settings()

        if not documents:
            return RerankerResult(
                documents=[],
                provider="none",
                latency_ms=0.0,
                fallback_used=False,
            )

        # Skip reranking for empty query
        if not query or not query.strip():
            return self._return_original_order(documents, "none", "empty_query")

        # Get primary reranker
        reranker = self.get_reranker()

        if reranker is None:
            logger.warning("No reranker available, returning original order")
            return self._return_original_order(documents, "none", "no_reranker")

        # Try primary reranker
        try:
            start_time = time.time()
            result = self._rerank_with_timeout(
                reranker, query, documents, top_n, content_key
            )
            return result

        except RerankerError as e:
            logger.warning(f"Primary reranker ({reranker.provider_name}) failed: {e}")

            # Try fallback if enabled and in auto mode
            if settings.reranker_fallback_enabled and settings.reranker_provider == "auto":
                return self._try_fallback(
                    query, documents, top_n, content_key, reranker.provider_name
                )

            # Return original order
            return self._return_original_order(documents, "none", str(e), fallback_used=True)

        except Exception as e:
            logger.error(f"Unexpected reranker error: {e}")
            return self._return_original_order(documents, "none", str(e), fallback_used=True)

    def _rerank_with_timeout(
        self,
        reranker: CohereReranker | BGEReranker,
        query: str,
        documents: list[dict],
        top_n: Optional[int],
        content_key: str,
    ) -> RerankerResult:
        """
        Rerank with timeout handling.

        Note: For simplicity, we rely on the underlying reranker's timeout.
        More sophisticated timeout handling could use threading or asyncio.
        """
        settings = get_settings()
        start_time = time.time()

        result = reranker.rerank(query, documents, top_n, content_key)

        elapsed = time.time() - start_time
        if elapsed > settings.reranker_timeout:
            logger.warning(
                f"Reranker {reranker.provider_name} exceeded timeout "
                f"({elapsed:.2f}s > {settings.reranker_timeout}s)"
            )

        return result

    def _try_fallback(
        self,
        query: str,
        documents: list[dict],
        top_n: Optional[int],
        content_key: str,
        failed_provider: str,
    ) -> RerankerResult:
        """Try fallback reranker after primary fails."""
        # Determine fallback provider
        if failed_provider == "cohere":
            fallback = self._get_bge()
        else:
            fallback = self._get_cohere()

        if not fallback.is_available():
            logger.warning(f"Fallback reranker ({fallback.provider_name}) also unavailable")
            return self._return_original_order(documents, "none", "all_unavailable", fallback_used=True)

        try:
            logger.info(f"Falling back to {fallback.provider_name} reranker")
            result = fallback.rerank(query, documents, top_n, content_key)
            # Mark that fallback was used
            result.fallback_used = True
            return result

        except Exception as e:
            logger.error(f"Fallback reranker ({fallback.provider_name}) also failed: {e}")
            return self._return_original_order(documents, "none", str(e), fallback_used=True)

    def _return_original_order(
        self,
        documents: list[dict],
        provider: str,
        reason: str,
        fallback_used: bool = False,
    ) -> RerankerResult:
        """Return documents in original order (no reranking)."""
        logger.debug(f"Returning original order: {reason}")

        reranked_docs = []
        original_ranks = []
        for idx, doc in enumerate(documents):
            doc_copy = doc.copy()
            doc_copy["relevance_score"] = doc.get("score", 0.0)
            reranked_docs.append(doc_copy)
            original_ranks.append(idx + 1)

        return RerankerResult(
            documents=reranked_docs,
            provider=provider,
            latency_ms=0.0,
            fallback_used=fallback_used,
            original_ranks=original_ranks,
        )


# Global singleton
_reranker_factory: Optional[RerankerFactory] = None


def get_reranker_factory() -> RerankerFactory:
    """Get the global RerankerFactory instance."""
    global _reranker_factory
    if _reranker_factory is None:
        _reranker_factory = RerankerFactory()
    return _reranker_factory
