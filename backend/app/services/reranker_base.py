"""Base protocol for reranker implementations."""
from typing import Protocol, Optional

from app.models.reranker import RerankerResult


class Reranker(Protocol):
    """Protocol for reranker implementations."""

    @property
    def provider_name(self) -> str:
        """Return provider identifier: 'cohere' | 'bge'"""
        ...

    def is_available(self) -> bool:
        """Check if this reranker is ready to use."""
        ...

    def rerank(
        self,
        query: str,
        documents: list[dict],
        top_n: Optional[int] = None,
        content_key: str = "content",
    ) -> RerankerResult:
        """
        Rerank documents by relevance to query.

        Args:
            query: Search query string
            documents: List of document dicts with content
            top_n: Number of results to return (default: from config)
            content_key: Key to extract text from documents

        Returns:
            RerankerResult with reranked documents and metadata
        """
        ...
