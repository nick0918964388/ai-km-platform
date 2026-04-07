"""Reranker models and exceptions."""
from dataclasses import dataclass, field
from typing import Optional


# --- Exceptions ---

class RerankerError(Exception):
    """Base exception for reranker errors."""
    pass


class RerankerTimeoutError(RerankerError):
    """Raised when reranking exceeds timeout."""
    pass


class RerankerUnavailableError(RerankerError):
    """Raised when no reranker is available."""
    pass


class ModelLoadError(RerankerError):
    """Raised when BGE model fails to load."""
    pass


# --- Data Classes ---

@dataclass
class RerankerResult:
    """Result from a reranking operation."""

    documents: list[dict]
    """Reranked documents with 'relevance_score' added."""

    provider: str
    """Provider name: 'cohere' | 'bge' | 'none'"""

    latency_ms: float
    """Processing time in milliseconds."""

    fallback_used: bool = False
    """True if this result came from a fallback provider."""

    original_ranks: list[int] = field(default_factory=list)
    """Original positions before reranking (1-indexed)."""
