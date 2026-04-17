"""Cohere Reranker service implementing the Reranker protocol."""
import logging
import time
from typing import Optional
import cohere

from app.config import get_settings
from app.models.reranker import RerankerResult, RerankerError


logger = logging.getLogger(__name__)


class CohereReranker:
    """Cohere Rerank API implementation."""

    def __init__(self):
        self._client: Optional[cohere.Client] = None
        self._enabled: bool = True
        self._init_attempted: bool = False

    @property
    def provider_name(self) -> str:
        """Return provider identifier."""
        return "cohere"

    def _get_client(self) -> Optional[cohere.Client]:
        """Get or create Cohere client."""
        if not self._enabled:
            return None

        if self._client is None and not self._init_attempted:
            self._init_attempted = True
            settings = get_settings()
            api_key = settings.cohere_api_key

            if not api_key:
                logger.warning("Cohere API key not configured. Cohere reranker disabled.")
                self._enabled = False
                return None

            try:
                self._client = cohere.Client(api_key=api_key)
                logger.info("Cohere client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Cohere client: {e}")
                self._enabled = False
                return None

        return self._client

    def is_available(self) -> bool:
        """Check if Cohere reranker is available."""
        return self._get_client() is not None

    def rerank(
        self,
        query: str,
        documents: list[dict],
        top_n: Optional[int] = None,
        content_key: str = "content",
    ) -> RerankerResult:
        """
        Rerank search results using Cohere Rerank API.

        Args:
            query: The search query
            documents: List of document dicts containing at least a content field
            top_n: Number of top results to return (default from config)
            content_key: Key to extract document text from

        Returns:
            RerankerResult with reranked documents and metadata
        """
        if not documents:
            return RerankerResult(
                documents=[],
                provider=self.provider_name,
                latency_ms=0.0,
                fallback_used=False,
            )

        client = self._get_client()
        if client is None:
            raise RerankerError("Cohere reranker is not available")

        settings = get_settings()
        top_n = top_n or settings.rerank_top_n
        model = settings.cohere_model

        # Extract text content from documents
        doc_texts = []
        for doc in documents:
            text = doc.get(content_key, "")
            if not text:
                text = doc.get("description", "") or doc.get("text", "") or str(doc)
            doc_texts.append(text)

        start_time = time.time()

        try:
            response = client.rerank(
                model=model,
                query=query,
                documents=doc_texts,
                top_n=min(top_n, len(documents)),
                return_documents=False,
            )

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                f"Cohere rerank completed: query='{query[:50]}...', "
                f"docs={len(documents)}, top_n={top_n}, "
                f"latency={elapsed_ms:.1f}ms"
            )

            # Build reranked result list
            reranked_docs = []
            original_ranks = []
            for result in response.results:
                doc_index = result.index
                doc = documents[doc_index].copy()
                doc["relevance_score"] = result.relevance_score
                reranked_docs.append(doc)
                original_ranks.append(doc_index + 1)  # 1-indexed

            return RerankerResult(
                documents=reranked_docs,
                provider=self.provider_name,
                latency_ms=elapsed_ms,
                fallback_used=False,
                original_ranks=original_ranks,
            )

        except cohere.errors.TooManyRequestsError as e:
            logger.warning(f"Cohere rate limit exceeded: {e}")
            raise RerankerError(f"Rate limit exceeded: {e}")

        except cohere.errors.UnauthorizedError as e:
            logger.error(f"Cohere authentication failed: {e}")
            self._enabled = False
            raise RerankerError(f"Authentication failed: {e}")

        except Exception as e:
            logger.error(f"Cohere rerank error: {e}")
            raise RerankerError(f"Rerank failed: {e}")


# Global singleton for backward compatibility
_cohere_reranker: Optional[CohereReranker] = None


def get_cohere_reranker() -> CohereReranker:
    """Get the global CohereReranker instance."""
    global _cohere_reranker
    if _cohere_reranker is None:
        _cohere_reranker = CohereReranker()
    return _cohere_reranker


# Legacy function wrappers for backward compatibility
def is_reranker_available() -> bool:
    """Check if reranker is available (legacy wrapper)."""
    return get_cohere_reranker().is_available()


def rerank(
    query: str,
    documents: list[dict],
    top_n: Optional[int] = None,
    content_key: str = "content",
) -> list[dict]:
    """
    Rerank search results (legacy wrapper).

    Returns list[dict] for backward compatibility.
    """
    reranker = get_cohere_reranker()
    if not reranker.is_available():
        logger.debug("Reranker unavailable, returning original order")
        return documents

    try:
        result = reranker.rerank(query, documents, top_n, content_key)
        return result.documents
    except RerankerError as e:
        logger.warning(f"Reranker fallback activated: {e}")
        # Add fallback indicator
        for doc in documents:
            doc["rerank_fallback"] = True
            doc["relevance_score"] = doc.get("score", 0.0)
        return documents
