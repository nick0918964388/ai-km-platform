"""Pre-filter: lightweight rule + embedding gate before SkillMatcher.

Rules (v2.1, revised order):
  1. chitchat detection (embedding cosine sim ≥ 0.88 when use_embedding=True,
                         otherwise fast string exact/bigram match vs seeds)
                        → chitchat   [BEFORE length rule so "你好" is chitchat]
  2. len(query.strip()) < 5  → clarify
  3. cost block regex (SELECT * workorder without WHERE)  → cost_block
  4. else  → allow

Note on ordering: chitchat comes first so that short but clearly conversational
inputs (e.g. "你好" len=2) are routed as chitchat rather than clarify.
Inputs that are short but NOT recognised as chitchat (e.g. "hi" is NOT in seeds,
"?" is not matched) fall through to the length rule and become clarify.

Performance target: P95 < 20ms.

Embedding mode (`use_embedding=True`):
  - Seed vectors are preloaded at __init__ via embed_texts().
  - Each check() call does ONE embed_text(query) then cosine sim over seeds.
  - Suitable when embedding provider is local (in-process / localhost Ollama).
  - On remote providers the network RTT will exceed 20ms; keep use_embedding=False.

String mode (default, use_embedding=False):
  - Exact lowercase match OR bigram-overlap ≥ 0.8 against CHITCHAT_SEEDS.
  - P95 < 0.01ms.  Zero external I/O.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Literal

from app.services.pre_filter_seeds import CHITCHAT_SEEDS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cost-block regex
# Fires on: SELECT * FROM <workorder-ish table> with nothing after (no WHERE).
# Conservative: requires the statement to END after the table name / whitespace.
# Does NOT fire when WHERE / LIMIT / etc. follow.
# ---------------------------------------------------------------------------
_COST_BLOCK_RE = re.compile(
    r"select\s+\*\s+from\s+\S*workorder\S*\s*$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Pre-computed seed data for string-based chitchat detection
# ---------------------------------------------------------------------------
_SEEDS_LOWER: frozenset[str] = frozenset(s.lower() for s in CHITCHAT_SEEDS)

_SEEDS_BIGRAMS: frozenset[str] = frozenset(
    s[i:i + 2]
    for s in CHITCHAT_SEEDS
    for i in range(len(s) - 1)
)


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _is_chitchat_string(query: str) -> tuple[bool, float]:
    """Fast string-based chitchat check.  Returns (matched, confidence)."""
    q = query.strip().lower()

    # Exact match against seed set
    if q in _SEEDS_LOWER:
        return True, 1.0

    # Bigram overlap ≥ 0.8 (handles partial matches like "哈哈哈" ⊃ "哈哈")
    if len(q) >= 2:
        q_bigrams = frozenset(q[i:i + 2] for i in range(len(q) - 1))
        overlap = len(q_bigrams & _SEEDS_BIGRAMS) / max(len(q_bigrams), 1)
        if overlap >= 0.8:
            return True, overlap

    return False, 0.0


@dataclass
class Verdict:
    action: Literal["allow", "chitchat", "clarify", "cost_block"]
    reason: str
    clarification_options: list[dict] | None = field(default=None)


class PreFilter:
    """Stateful pre-filter; optionally uses embedding for chitchat detection.

    Parameters
    ----------
    use_embedding:
        When True, seed vectors are loaded at construction and each check()
        call embeds the query for cosine similarity (accurate but requires a
        fast local embedding provider to meet the P95 < 20ms target).
        When False (default), uses fast string exact/bigram matching.
    """

    CHITCHAT_THRESHOLD: float = 0.88

    def __init__(self, use_embedding: bool = False) -> None:
        self._use_embedding = use_embedding
        self._seed_vectors: list[list[float]] = []

        if use_embedding:
            from app.services.embedding import embed_texts
            logger.info("[pre_filter] loading %d seed embeddings…", len(CHITCHAT_SEEDS))
            self._seed_vectors = embed_texts(CHITCHAT_SEEDS)
            logger.info("[pre_filter] seed embeddings ready (embedding mode)")
        else:
            logger.info(
                "[pre_filter] initialised in string mode (%d seeds, %d bigrams)",
                len(_SEEDS_LOWER),
                len(_SEEDS_BIGRAMS),
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(self, query: str, *, has_history: bool = False) -> Verdict:
        """Evaluate *query* and return a routing Verdict.

        Parameters
        ----------
        query: 使用者輸入
        has_history: 對話前有上一輪 SQL 結果。為 True 時放寬「過短」門檻，
                    讓「共有幾筆?」「那 EMU800 呢?」等追問通過 PreFilter 進
                    入 agent，agent 會根據前輪 context 補完語意。
        """
        stripped = query.strip()

        # Rule 1: chitchat detection (before length so "你好" → chitchat not clarify)
        if self._use_embedding:
            from app.services.embedding import embed_text
            query_vec = embed_text(stripped)
            max_sim = max(
                _cosine_sim(query_vec, sv) for sv in self._seed_vectors
            )
            if max_sim >= self.CHITCHAT_THRESHOLD:
                return Verdict(
                    action="chitchat",
                    reason=f"偵測到閒聊輸入（embedding similarity={max_sim:.3f}）",
                )
        else:
            matched, conf = _is_chitchat_string(stripped)
            if matched:
                return Verdict(
                    action="chitchat",
                    reason=f"偵測到閒聊輸入（string match confidence={conf:.2f}）",
                )

        # Rule 2: too short — has_history=True 時放寬到 < 2 (允許追問)
        min_len = 2 if has_history else 5
        if len(stripped) < min_len:
            return Verdict(
                action="clarify",
                reason=f"查詢過短（{len(stripped)} 字元），請提供更多細節",
                clarification_options=[
                    {"label": "查詢工單狀態", "value": "查詢核簽中的工單"},
                    {"label": "查詢資產資訊", "value": "查詢 EMU800 的維修紀錄"},
                    {"label": "查詢故障報告", "value": "最近一週的故障報告"},
                ],
            )

        # Rule 3: cost block
        if _COST_BLOCK_RE.search(stripped):
            logger.warning("[pre_filter] cost_block triggered: %r", stripped[:120])
            return Verdict(
                action="cost_block",
                reason="查詢包含無 WHERE 條件的全表掃描，已攔截以保護效能",
            )

        # Rule 4: allow
        return Verdict(action="allow", reason="pass")


# ---------------------------------------------------------------------------
# Module-level singleton (lazy, created on first access)
# ---------------------------------------------------------------------------

_instance: PreFilter | None = None


def get_pre_filter() -> PreFilter:
    """Return the module-level PreFilter singleton (string mode)."""
    global _instance
    if _instance is None:
        _instance = PreFilter()
    return _instance
