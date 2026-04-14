"""Dynamic Context Manager — token budget management + context compression."""
import logging
from typing import Optional

log = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    return int(len(text) * 1.5)


def estimate_context_tokens(context: list[dict]) -> int:
    return sum(estimate_tokens(m.get("content", "")) for m in context)


MAX_CONTEXT_TOKENS = 4000


def build_optimized_context(context: list[dict], max_tokens: int = MAX_CONTEXT_TOKENS) -> list[dict]:
    """Build optimized conversation context within token budget.
    Keep recent 2 turns in full, compress older turns to first 50 chars.
    """
    if not context:
        return []

    recent_count = min(4, len(context))
    recent = context[-recent_count:]
    older = context[:-recent_count] if len(context) > recent_count else []

    recent_tokens = estimate_context_tokens(recent)
    if recent_tokens >= max_tokens:
        truncated = []
        for m in recent:
            if len(m.get("content", "")) > 200:
                truncated.append({**m, "content": m["content"][:200] + "..."})
            else:
                truncated.append(m)
        return truncated[-4:]

    remaining_budget = max_tokens - recent_tokens

    compressed = []
    for m in older:
        content = m.get("content", "")
        summary = {
            "role": m.get("role", "user"),
            "content": content[:50] + ("..." if len(content) > 50 else ""),
        }
        if m.get("intent"):
            summary["intent"] = m["intent"]
        if m.get("sql"):
            summary["sql"] = m["sql"]

        tokens = estimate_tokens(summary["content"])
        if tokens <= remaining_budget:
            compressed.append(summary)
            remaining_budget -= tokens
        else:
            break

    return compressed + recent


class TaskFocusState:
    """Track user intent across turns."""
    def __init__(self):
        self.goal: str = ""
        self.recent_goals: list[str] = []
        self.active_artifacts: list[str] = []

    def update(self, query: str, intent: str = "", artifacts: list[str] = None):
        self.goal = query[:100]
        self.recent_goals.append(self.goal)
        if len(self.recent_goals) > 5:
            self.recent_goals = self.recent_goals[-5:]
        if artifacts:
            self.active_artifacts = (self.active_artifacts + artifacts)[-8:]

    def to_context_hint(self) -> str:
        if not self.recent_goals:
            return ""
        return f"使用者最近關注：{'、'.join(self.recent_goals[-3:])}"
