"""
Skill Agent Implicit Validator — S3

Performs a single yes/no LLM call to check if a result answers the user's question.
Config-driven: only runs when settings.skill_agent_validate_enabled=True.
Trigger conditions:
  - row_count == 0
  - row_count > settings.skill_agent_validate_threshold_upper
Single call must complete < 1s (enforced by caller timeout).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable

log = logging.getLogger(__name__)

# Validate prompt — deliberately short to stay < 1s
_VALIDATE_PROMPT_TEMPLATE = (
    "使用者問：{question}\n"
    "執行 SQL 後得到 {row_count} 筆結果。\n"
    "這個結果能回答使用者的問題嗎？請回覆 yes 或 no，後面加一行簡短原因（不超過 20 字）。"
)

# Timeout for the validate LLM call
_VALIDATE_TIMEOUT_SEC = 1.0


def should_validate(row_count: int, enabled: bool, threshold_upper: int) -> bool:
    """
    Return True if validate step should run.

    Triggers:
      - row_count == 0
      - row_count > threshold_upper

    threshold_upper default 10000: conservative coverage for dashboard queries.
    Note: validate=no does NOT mean SQL is wrong — it means the agent should
    re-evaluate whether a refinement is needed.
    """
    if not enabled:
        return False
    return row_count == 0 or row_count > threshold_upper


async def run_validate(
    question: str,
    row_count: int,
    llm_call: Callable[[str, str, list], Awaitable[Any]],
) -> tuple[bool, str]:
    """
    Ask LLM: does this result answer the question?
    Returns (ok: bool, reason: str).
    ok=True  → result is acceptable, return to caller
    ok=False → agent should try another turn
    Times out after _VALIDATE_TIMEOUT_SEC → treat as ok=True (fail open, don't block).
    """
    prompt = _VALIDATE_PROMPT_TEMPLATE.format(
        question=question,
        row_count=row_count,
    )
    try:
        response = await asyncio.wait_for(
            llm_call(
                "你是查詢品質評估員。只回覆 yes/no + 一行原因。",
                prompt,
                [],  # no tools for validate call
            ),
            timeout=_VALIDATE_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        log.debug("validate call timed out after %.1fs — treating as ok", _VALIDATE_TIMEOUT_SEC)
        return True, "timeout_treat_as_ok"
    except Exception as e:
        log.warning("validate call failed: %s — treating as ok", e)
        return True, f"error_treat_as_ok: {type(e).__name__}"

    # Parse response — extract text from Anthropic response
    raw_text = _extract_text(response)
    first_line = raw_text.strip().lower().split("\n")[0]
    reason = raw_text.strip()

    if first_line.startswith("yes"):
        return True, reason
    if first_line.startswith("no"):
        return False, reason

    # Ambiguous — treat as ok (fail open)
    log.debug("validate ambiguous response %r — treating as ok", raw_text[:80])
    return True, f"ambiguous: {reason}"


def _extract_text(response: Any) -> str:
    """Extract text content from Anthropic API response or plain string."""
    if isinstance(response, str):
        return response
    # Anthropic SDK response object
    content = getattr(response, "content", None)
    if content and isinstance(content, list):
        for block in content:
            if getattr(block, "type", None) == "text":
                return getattr(block, "text", "") or ""
    return ""
