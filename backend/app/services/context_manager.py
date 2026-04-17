"""Dynamic Context Manager — token budget management + context compression."""
import logging
import re
from typing import Optional

import tiktoken

log = logging.getLogger(__name__)

_ENCODING = tiktoken.get_encoding("cl100k_base")


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_ENCODING.encode(text))


def estimate_context_tokens(context: list[dict]) -> int:
    return sum(estimate_tokens(m.get("content", "")) for m in context)


MAX_CONTEXT_TOKENS = 4000

MODEL_CONTEXT_LIMITS = {
    "default": 16000,
    "gpt-4o": 120000,
    "claude-sonnet": 180000,
    "claude-opus": 180000,
}

OUTPUT_TOKEN_RESERVE = 4000


def preflight_check(
    messages: list[dict],
    system_prompt: str = "",
    schema_text: str = "",
    model: str = "default",
) -> dict:
    """Check if request fits within model's context window."""
    msg_tokens = estimate_context_tokens(messages)
    sys_tokens = estimate_tokens(system_prompt)
    schema_tokens = estimate_tokens(schema_text)

    total = msg_tokens + sys_tokens + schema_tokens + OUTPUT_TOKEN_RESERVE

    limit = MODEL_CONTEXT_LIMITS.get(model, MODEL_CONTEXT_LIMITS["default"])

    result = {
        "ok": total <= limit,
        "used": total,
        "limit": limit,
        "available": limit - total,
        "breakdown": {
            "messages": msg_tokens,
            "system_prompt": sys_tokens,
            "schema": schema_tokens,
            "output_reserve": OUTPUT_TOKEN_RESERVE,
        },
    }

    if not result["ok"]:
        log.warning(
            "Preflight budget exceeded: %d/%d tokens (messages=%d, system=%d, schema=%d)",
            total, limit, msg_tokens, sys_tokens, schema_tokens,
        )

    return result


def sanitize_tool_pairs(messages: list[dict]) -> list[dict]:
    """Fix orphaned tool_use/tool_result pairs after context trimming.

    Rules:
    - Orphan tool_result (result exists, its assistant tool_call doesn't): DROP
    - Orphan tool_call (assistant call exists, result doesn't): INSERT stub result
    """
    tool_call_ids: set[str] = set()
    tool_result_ids: set[str] = set()

    for msg in messages:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls", []) or []:
                tool_call_ids.add(tc.get("id", ""))
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_call_ids.add(block.get("id", ""))
        elif msg.get("role") == "tool":
            tool_result_ids.add(msg.get("tool_call_id", ""))
        elif msg.get("role") == "user" and isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tool_result_ids.add(block.get("tool_use_id", ""))

    orphan_results = tool_result_ids - tool_call_ids
    orphan_calls = tool_call_ids - tool_result_ids

    result = []
    for msg in messages:
        if msg.get("role") == "tool" and msg.get("tool_call_id", "") in orphan_results:
            log.debug("Dropping orphan tool_result: %s", msg.get("tool_call_id"))
            continue
        if msg.get("role") == "user" and isinstance(msg.get("content"), list):
            filtered_blocks = [
                b for b in msg["content"]
                if not (isinstance(b, dict) and b.get("type") == "tool_result"
                        and b.get("tool_use_id", "") in orphan_results)
            ]
            if filtered_blocks != msg["content"]:
                msg = {**msg, "content": filtered_blocks}
                if not msg["content"]:
                    continue
        result.append(msg)

    if orphan_calls:
        for call_id in orphan_calls:
            result.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": "[Result from earlier conversation — see context summary above]",
            })
        log.debug("Inserted %d stub tool_results for orphan calls", len(orphan_calls))

    return result


def _align_trim_boundary(messages: list[dict], boundary_idx: int) -> int:
    """Push boundary forward past any orphaned tool_result messages."""
    while boundary_idx < len(messages):
        msg = messages[boundary_idx]
        if msg.get("role") == "tool":
            boundary_idx += 1
        elif (msg.get("role") == "user" and isinstance(msg.get("content"), list)
              and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in msg["content"])):
            boundary_idx += 1
        else:
            break
    return boundary_idx


def build_optimized_context(
    context: list[dict],
    max_tokens: int = MAX_CONTEXT_TOKENS,
    system_tokens: int = 0,
    schema_tokens: int = 0,
) -> list[dict]:
    """Build optimized conversation context within token budget.
    Keep recent 2 turns in full, compress older turns to first 50 chars.
    """
    if not context:
        return []

    effective_max = max_tokens - system_tokens - schema_tokens - OUTPUT_TOKEN_RESERVE
    if effective_max < 1000:
        log.warning("Effective context budget very low: %d tokens, using minimum 1000", effective_max)
        effective_max = 1000

    recent_count = min(4, len(context))
    split_idx = len(context) - recent_count
    split_idx = _align_trim_boundary(context, split_idx)
    recent = context[split_idx:]
    older = context[:split_idx]

    recent_tokens = estimate_context_tokens(recent)
    if recent_tokens >= effective_max:
        truncated = []
        for m in recent:
            if len(m.get("content", "")) > 200:
                truncated.append({**m, "content": m["content"][:200] + "..."})
            else:
                truncated.append(m)
        return truncated[-4:]

    remaining_budget = effective_max - recent_tokens

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

    optimized = compressed + recent
    return sanitize_tool_pairs(optimized)


async def compress_context(
    messages: list[dict],
    max_tokens: int = MAX_CONTEXT_TOKENS,
    system_tokens: int = 0,
    schema_tokens: int = 0,
) -> list[dict]:
    """Compress conversation context using LLM summarization.

    Strategy (inspired by Hermes context_compressor):
    - Protect head (first 2 messages) and tail (last 6 messages)
    - Summarize middle section using cheap LLM
    - Summary budget: max(500, content_tokens * 0.20)
    - Preserve tool-call pairing
    """
    if not messages:
        return []

    effective_max = max_tokens - system_tokens - schema_tokens - OUTPUT_TOKEN_RESERVE
    if effective_max < 1000:
        effective_max = 1000

    total_tokens = estimate_context_tokens(messages)

    if total_tokens <= effective_max:
        return sanitize_tool_pairs(messages)

    PROTECT_HEAD = 2
    PROTECT_TAIL = 6

    if len(messages) <= PROTECT_HEAD + PROTECT_TAIL:
        return sanitize_tool_pairs(_truncate_messages(messages, effective_max))

    head = messages[:PROTECT_HEAD]
    tail = messages[-PROTECT_TAIL:]
    middle = messages[PROTECT_HEAD:-PROTECT_TAIL]

    if not middle:
        return sanitize_tool_pairs(head + tail)

    middle_text = "\n".join(
        f"{m.get('role', 'user')}: {m.get('content', '')[:500]}"
        for m in middle
    )
    middle_tokens = estimate_tokens(middle_text)
    summary_budget = max(500, int(middle_tokens * 0.20))

    try:
        summary = await _llm_summarize(middle_text, summary_budget)
    except Exception as e:
        log.warning("LLM summarization failed, falling back to truncation: %s", e)
        summary = _naive_summarize(middle)

    summary_msg = {
        "role": "assistant",
        "content": f"[以下是先前對話的摘要]\n{summary}\n[摘要結束 — 請根據以下最新對話回應]",
    }

    compressed = head + [summary_msg] + tail
    return sanitize_tool_pairs(compressed)


def _naive_summarize(messages: list[dict]) -> str:
    """Fallback: extract key points without LLM."""
    parts = []
    for m in messages:
        content = m.get("content", "")
        role = "用戶" if m.get("role") == "user" else "AI"
        summary = content[:80]
        if m.get("intent"):
            summary += f" [intent: {m['intent']}]"
        if m.get("sql"):
            summary += f" [SQL: {m['sql'][:60]}]"
        parts.append(f"{role}: {summary}")
    return "\n".join(parts)


async def _llm_summarize(text: str, max_tokens: int = 500) -> str:
    """Summarize conversation text using cheap/fast LLM."""
    import asyncio
    from openai import AsyncOpenAI
    from app.config import get_settings, get_active_llm_info

    settings = get_settings()
    llm_url, llm_model = get_active_llm_info()

    prompt = f"""請用中文摘要以下對話，保留：
1. 使用者問了什麼問題（保留關鍵字）
2. 系統回答的重點結論
3. 任何 SQL 查詢結果的關鍵數字
4. 使用者表達的偏好或修正

摘要需精簡，不超過 {max_tokens} tokens。

對話內容：
{text[:3000]}"""

    client = AsyncOpenAI(base_url=llm_url, api_key=settings.llm_api_key or "sk-unused")
    response = await asyncio.wait_for(
        client.chat.completions.create(
            model=llm_model,
            messages=[{"role": "user", "content": f"/no_think\n{prompt}"}],
            temperature=0.1,
            max_tokens=max_tokens,
        ),
        timeout=15.0,
    )
    content = response.choices[0].message.content.strip()
    content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
    return content


def _truncate_messages(messages: list[dict], max_tokens: int) -> list[dict]:
    """Truncate message contents to fit within token budget."""
    result = []
    budget = max_tokens
    for m in reversed(messages):
        tokens = estimate_tokens(m.get("content", ""))
        if tokens <= budget:
            result.insert(0, m)
            budget -= tokens
        else:
            truncated = {**m, "content": m.get("content", "")[:200] + "..."}
            result.insert(0, truncated)
            budget -= estimate_tokens(truncated["content"])
        if budget <= 0:
            break
    return result


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
