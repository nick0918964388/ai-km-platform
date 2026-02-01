"""Cohere Reranker service for improving search result relevance."""
import logging
import time
from typing import Optional
import cohere

from app.config import get_settings

logger = logging.getLogger(__name__)

# Cohere client singleton
_cohere_client: Optional[cohere.Client] = None
_reranker_enabled: bool = True


def get_cohere_client() -> Optional[cohere.Client]:
    """Get or create Cohere client."""
    global _cohere_client, _reranker_enabled

    if not _reranker_enabled:
        return None

    if _cohere_client is None:
        settings = get_settings()
        api_key = settings.cohere_api_key

        if not api_key:
            logger.warning("Cohere API key not configured. Reranker disabled.")
            _reranker_enabled = False
            return None

        try:
            _cohere_client = cohere.Client(api_key=api_key)
            logger.info("Cohere client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Cohere client: {e}")
            _reranker_enabled = False
            return None

    return _cohere_client


def is_reranker_available() -> bool:
    """Check if reranker is available."""
    return get_cohere_client() is not None


def rerank(
    query: str,
    documents: list[dict],
    top_n: Optional[int] = None,
    content_key: str = "content",
) -> list[dict]:
    """
    Rerank search results using Cohere Rerank API.

    Args:
        query: The search query
        documents: List of document dicts containing at least a content field
        top_n: Number of top results to return (default from config)
        content_key: Key to extract document text from

    Returns:
        Reranked list of documents with added relevance_score
    """
    if not documents:
        return []

    client = get_cohere_client()
    if client is None:
        # Fallback: return original order
        logger.debug("Reranker unavailable, returning original order")
        return documents

    settings = get_settings()
    top_n = top_n or settings.rerank_top_n
    model = settings.cohere_model

    # Extract text content from documents
    doc_texts = []
    for doc in documents:
        text = doc.get(content_key, "")
        if not text:
            # Try alternative keys
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
            f"Rerank completed: query='{query[:50]}...', "
            f"docs={len(documents)}, top_n={top_n}, "
            f"latency={elapsed_ms:.1f}ms"
        )

        # Build reranked result list
        reranked = []
        for result in response.results:
            doc_index = result.index
            doc = documents[doc_index].copy()
            doc["relevance_score"] = result.relevance_score
            reranked.append(doc)

        return reranked

    except cohere.errors.TooManyRequestsError as e:
        logger.warning(f"Cohere rate limit exceeded: {e}")
        return _fallback_with_warning(documents, "Rate limit exceeded")

    except cohere.errors.UnauthorizedError as e:
        logger.error(f"Cohere authentication failed: {e}")
        global _reranker_enabled
        _reranker_enabled = False
        return _fallback_with_warning(documents, "Authentication failed")

    except Exception as e:
        logger.error(f"Rerank error: {e}")
        return _fallback_with_warning(documents, str(e))


def _fallback_with_warning(documents: list[dict], reason: str) -> list[dict]:
    """Return original documents with fallback warning."""
    logger.warning(f"Reranker fallback activated: {reason}")
    # Add indicator that these are not reranked
    for doc in documents:
        doc["rerank_fallback"] = True
        doc["relevance_score"] = doc.get("score", 0.0)
    return documents


def rerank_batch(
    queries: list[str],
    documents_list: list[list[dict]],
    top_n: Optional[int] = None,
    content_key: str = "content",
) -> list[list[dict]]:
    """
    Rerank multiple query-document pairs.

    Args:
        queries: List of search queries
        documents_list: List of document lists (one per query)
        top_n: Number of top results per query
        content_key: Key to extract document text

    Returns:
        List of reranked document lists
    """
    results = []
    for query, docs in zip(queries, documents_list):
        reranked = rerank(query, docs, top_n, content_key)
        results.append(reranked)
    return results
