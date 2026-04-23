"""
Terminology normalizer — 最長片段優先替換（防污染版本）。

核心策略：
  1. 按 key 長度 DESC 排序，確保長片段優先匹配。
  2. 替換後的 canonical 內容以 placeholder 保護，避免被後續較短 term 二次命中。
  3. 所有替換完成後還原 placeholder。

用法：
    from backend.app.services.terminology.normalizer import normalize, reload

    normalized, applied = normalize("核簽工單有幾張")
    # normalized == "核簽中工單有幾張"
    # applied == [("核簽工單", "核簽中工單")]
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from .loader import load_terminology

logger = logging.getLogger(__name__)

_sorted_terms: List[Tuple[str, str]] = []
_terms_dict: Dict[str, str] = {}
_loaded: bool = False

# Placeholder template must be something that will never appear in real input
_PH_PREFIX = "\x00TERM"
_PH_SUFFIX = "\x00"


def _ensure_loaded() -> None:
    global _loaded
    if not _loaded:
        reload()


def reload(path: str | None = None) -> None:
    """(Re)load terminology from YAML. Exposed for tests and startup hooks."""
    global _sorted_terms, _terms_dict, _loaded
    _terms_dict = load_terminology(path)
    _sorted_terms = sorted(_terms_dict.items(), key=lambda kv: len(kv[0]), reverse=True)
    _loaded = True
    logger.debug("Terminology normalizer loaded %d terms", len(_terms_dict))


def normalize(query: str) -> Tuple[str, List[Tuple[str, str]]]:
    """
    Replace source terms with canonical forms using longest-match-first strategy.

    Each source term is replaced at most once per occurrence; once replaced,
    the canonical text is protected from subsequent shorter-term substitutions.

    Args:
        query: raw user input string

    Returns:
        (normalized_query, applied_terms)
        applied_terms: list of (source, canonical) for every replacement applied.
    """
    _ensure_loaded()

    if not _sorted_terms:
        return query, []

    # Work buffer starts with the original query.
    # After replacing a source term, the canonical is encoded as a placeholder
    # so shorter overlapping terms cannot re-match it.
    buf = query
    applied: List[Tuple[str, str]] = []
    placeholders: List[str] = []  # index i → actual canonical string

    for source, canonical in _sorted_terms:
        if source in buf:
            ph_idx = len(placeholders)
            placeholder = f"{_PH_PREFIX}{ph_idx}{_PH_SUFFIX}"
            placeholders.append(canonical)
            buf = buf.replace(source, placeholder)
            applied.append((source, canonical))

    # Restore all placeholders in reverse registration order (doesn't matter
    # directionally since placeholders are unique, but explicit is better).
    for i, canonical in enumerate(placeholders):
        ph = f"{_PH_PREFIX}{i}{_PH_SUFFIX}"
        buf = buf.replace(ph, canonical)

    return buf, applied
