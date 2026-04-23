"""
Skill Agent Fallback Loop — S3

SkillAgentFallback: multi-turn tool_use agent loop.

Architecture (forked from maximo_tools/router.py, adapted for multi-turn):
  - Single-turn tool_use in router.py → multi-turn (max 3) here
  - Each turn: LLM call → parse tool_use → dispatch → append tool_result → next turn
  - Hard limits: 3 turns, 10s total, 5s per LLM call, 5 tool_use calls total
  - Validate step (config-driven): row_count==0 or >threshold_upper → re-evaluate
  - Image input: if image_base64 provided → inject as image block in first user message
  - Conversation history: inject structured summaries via context_builder (no raw text)

Security:
  - run_sql always passes _is_safe_select + _run_security_gates
  - SQL failures return error tool_result blocks (LLM self-corrects, no raise)

Not wired to chat.py (S0 task).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from app.config import get_settings
from app.services.maximo_tools.base import UserContext
from app.services.skill_agent.tools import (
    AGENT_TOOLS,
    execute_inspect_schema,
    execute_run_skill,
    execute_run_sql,
    execute_search_docs,
)
from app.services.skill_agent.context_builder import build_system_context
from app.services.skill_agent.validator import run_validate, should_validate

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hard limits
# ---------------------------------------------------------------------------
_MAX_TURNS = 3
_TOTAL_TIMEOUT_SEC = 10.0
_PER_LLM_TIMEOUT_SEC = 5.0
_MAX_TOOL_USES = 5

_SYSTEM_PROMPT_BASE = (
    "你是 AI-KM Platform 的 Maximo 智慧查詢 Agent。"
    "你可以使用工具查詢車輛、工單、故障紀錄，以及搜尋技術文件。\n"
    "規則：\n"
    "1. 只呼叫與問題直接相關的工具。\n"
    "2. run_sql 只能用 SELECT，若 SQL 失敗請修正後重試。\n"
    "3. 工具結果已包含你需要的資料，請根據結果直接回答，不要憑空捏造。\n"
    "4. 若無法取得有用資料，誠實說明原因。\n"
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ToolTrace:
    name: str
    input: dict
    output: dict
    latency_ms: int


@dataclass
class AgentResult:
    success: bool
    rows: list[dict] = field(default_factory=list)
    row_count: int = 0
    answer: str = ""
    terminal_reason: str = "done"  # done | max_turns | timeout | error
    turns_used: int = 0
    tool_traces: list[ToolTrace] = field(default_factory=list)
    validate_result: str | None = None   # "yes" | "no" | "skipped" | None
    image_present: bool = False
    elapsed_ms: int = 0


# ---------------------------------------------------------------------------
# LLM call type
# ---------------------------------------------------------------------------
LLMCallFn = Callable[[str, list[dict], list[dict]], Awaitable[Any]]


# ---------------------------------------------------------------------------
# Main agent class
# ---------------------------------------------------------------------------

class SkillAgentFallback:
    """
    Multi-turn tool_use agent.

    Parameters
    ----------
    llm_call:
        async (system: str, messages: list[dict], tools: list[dict]) -> AnthropicResponse
        Note: this signature differs from router.py's single-arg user_query pattern —
        we pass full messages list to support multi-turn conversation.
    db_pool:
        asyncpg connection pool (optional — passed through to run_sql executor).
    skill_runner:
        async (name: str, params: dict, user_ctx: UserContext) -> dict
        Called by run_skill tool executor.
    rag_search_fn:
        Callable passed to execute_search_docs. Default: rag.search (lazy import).
    """

    def __init__(
        self,
        llm_call: LLMCallFn,
        db_pool=None,
        skill_runner=None,
        rag_search_fn=None,
    ):
        self._llm_call = llm_call
        self._db_pool = db_pool
        self._skill_runner = skill_runner
        self._rag_search_fn = rag_search_fn

    async def run(
        self,
        query: str,
        user_ctx: UserContext,
        conversation_history: list[dict[str, Any]] | None = None,
        image_base64: str | None = None,
    ) -> AgentResult:
        """
        Entry point. Runs the multi-turn tool_use loop.

        Parameters
        ----------
        query: User's natural language question.
        user_ctx: Auth/permission context.
        conversation_history:
            List of previous turn dicts. Each may contain:
            {q, sql, row_count, intent}.
            Raw question text (q) is summarized into prev_intent only (no raw text forwarded).
            Max 3 turns; older turns truncated.
        image_base64:
            Base64-encoded image. If provided, injected as image block in the first
            user message. tools are unchanged. trace records image_present=True.
        """
        total_start = time.monotonic()
        image_present = bool(image_base64)

        # Build system prompt with context
        context_block = build_system_context(
            conversation_history=conversation_history,
        )
        system_prompt = _SYSTEM_PROMPT_BASE + "\n\n" + context_block

        # Build initial user message
        user_content = _build_user_content(query, image_base64)
        messages: list[dict] = [{"role": "user", "content": user_content}]

        tool_traces: list[ToolTrace] = []
        tool_use_count = 0
        turns = 0
        last_rows: list[dict] = []
        last_row_count = 0
        terminal_reason = "done"

        try:
            result = await asyncio.wait_for(
                self._loop(
                    query=query,
                    system_prompt=system_prompt,
                    messages=messages,
                    user_ctx=user_ctx,
                    tool_traces=tool_traces,
                    tool_use_count_ref=[tool_use_count],
                    turns_ref=[turns],
                    last_rows_ref=[last_rows],
                    last_row_count_ref=[last_row_count],
                    terminal_reason_ref=[terminal_reason],
                ),
                timeout=_TOTAL_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            elapsed = int((time.monotonic() - total_start) * 1000)
            log.warning("SkillAgentFallback total timeout after %.1fs", _TOTAL_TIMEOUT_SEC)
            return AgentResult(
                success=False,
                rows=last_rows,
                row_count=last_row_count,
                answer="查詢超時，部分結果如上",
                terminal_reason="timeout",
                turns_used=turns,
                tool_traces=tool_traces,
                image_present=image_present,
                elapsed_ms=elapsed,
            )

        elapsed = int((time.monotonic() - total_start) * 1000)
        result.elapsed_ms = elapsed
        result.image_present = image_present
        return result

    async def _loop(
        self,
        query: str,
        system_prompt: str,
        messages: list[dict],
        user_ctx: UserContext,
        tool_traces: list[ToolTrace],
        tool_use_count_ref: list[int],
        turns_ref: list[int],
        last_rows_ref: list[list],
        last_row_count_ref: list[int],
        terminal_reason_ref: list[str],
    ) -> AgentResult:
        """Inner loop — wrapped by asyncio.wait_for for total timeout."""
        settings = get_settings()

        turns = 0
        tool_use_count = 0
        last_rows: list[dict] = []
        last_row_count = 0
        last_answer = ""
        validate_result: str | None = None

        while turns < _MAX_TURNS:
            turns += 1
            turns_ref[0] = turns

            # Per-LLM-call timeout
            try:
                response = await asyncio.wait_for(
                    self._llm_call(system_prompt, messages, AGENT_TOOLS),
                    timeout=_PER_LLM_TIMEOUT_SEC,
                )
            except asyncio.TimeoutError:
                terminal_reason_ref[0] = "timeout"
                return AgentResult(
                    success=False,
                    rows=last_rows,
                    row_count=last_row_count,
                    answer="LLM 呼叫超時",
                    terminal_reason="timeout",
                    turns_used=turns,
                    tool_traces=tool_traces,
                    validate_result=validate_result,
                )

            stop_reason = getattr(response, "stop_reason", "end_turn")
            content_blocks = getattr(response, "content", []) or []

            # Append assistant message to conversation
            messages.append({"role": "assistant", "content": content_blocks})

            # Extract text answer (if any)
            for block in content_blocks:
                if getattr(block, "type", None) == "text":
                    last_answer = getattr(block, "text", "") or ""

            # Find tool_use blocks
            tool_use_blocks = [
                b for b in content_blocks
                if getattr(b, "type", None) == "tool_use"
            ]

            if stop_reason == "end_turn" or not tool_use_blocks:
                # LLM finished without tools — done
                terminal_reason_ref[0] = "done"
                break

            if stop_reason != "tool_use":
                # Unexpected stop — treat as done
                terminal_reason_ref[0] = "done"
                break

            # Process all tool_use blocks in this turn
            tool_results: list[dict] = []
            for block in tool_use_blocks:
                if tool_use_count >= _MAX_TOOL_USES:
                    # Inject hard limit error
                    tool_results.append(_make_tool_result_block(
                        getattr(block, "id", "unknown"),
                        {"error": "已達工具呼叫上限（5 次）"},
                    ))
                    continue

                tool_name = getattr(block, "name", "")
                tool_input = getattr(block, "input", {}) or {}
                tool_start = time.monotonic()

                output = await self._dispatch_tool(tool_name, tool_input, user_ctx)
                tool_latency = int((time.monotonic() - tool_start) * 1000)
                tool_use_count += 1
                tool_use_count_ref[0] = tool_use_count

                # Update last SQL result for validate step
                if tool_name in ("run_sql", "run_skill") and "rows" in output:
                    last_rows = output.get("rows", [])
                    last_row_count = output.get("row_count", 0)
                    last_rows_ref[0] = last_rows
                    last_row_count_ref[0] = last_row_count

                tool_traces.append(ToolTrace(
                    name=tool_name,
                    input=tool_input,
                    output=output,
                    latency_ms=tool_latency,
                ))
                tool_results.append(_make_tool_result_block(
                    getattr(block, "id", f"tool_{tool_use_count}"),
                    output,
                ))

            # Append tool results to messages
            messages.append({
                "role": "user",
                "content": tool_results,
            })

        else:
            # Exhausted _MAX_TURNS
            terminal_reason_ref[0] = "max_turns"

        # ---------------------------------------------------------------------------
        # Validate step (config-driven)
        # ---------------------------------------------------------------------------
        validate_enabled = getattr(settings, "skill_agent_validate_enabled", True)
        # threshold_upper default 10000 保守涵蓋儀表板類查詢（< 10000 筆視為合理）
        # 也注意：validate=no 不代表 SQL 錯，只是「讓 agent 再評估一輪是否要 refine」
        threshold_upper = getattr(settings, "skill_agent_validate_threshold_upper", 10000)

        if should_validate(last_row_count, validate_enabled, threshold_upper):
            ok, reason = await run_validate(query, last_row_count, self._llm_call_for_validate)
            validate_result = "yes" if ok else "no"
            log.debug("validate result=%s reason=%r row_count=%d", validate_result, reason, last_row_count)

            if not ok and turns < _MAX_TURNS:
                # Re-run one more turn to let LLM refine
                turns += 1
                turns_ref[0] = turns
                # Inject validate feedback as user message
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "text",
                        "text": (
                            f"上一個查詢回傳 {last_row_count} 筆結果，"
                            "但這可能不足以回答問題，請重新考慮是否需要修改查詢條件。"
                        ),
                    }],
                })
                try:
                    response = await asyncio.wait_for(
                        self._llm_call(system_prompt, messages, AGENT_TOOLS),
                        timeout=_PER_LLM_TIMEOUT_SEC,
                    )
                except asyncio.TimeoutError:
                    pass
                else:
                    content_blocks = getattr(response, "content", []) or []
                    for block in content_blocks:
                        if getattr(block, "type", None) == "text":
                            last_answer = getattr(block, "text", "") or last_answer
                    # Process any new tool_use from validate re-run
                    tool_use_blocks = [
                        b for b in content_blocks
                        if getattr(b, "type", None) == "tool_use"
                    ]
                    if tool_use_blocks and tool_use_count < _MAX_TOOL_USES:
                        messages.append({"role": "assistant", "content": content_blocks})
                        tool_results = []
                        for block in tool_use_blocks:
                            if tool_use_count >= _MAX_TOOL_USES:
                                break
                            tool_name = getattr(block, "name", "")
                            tool_input = getattr(block, "input", {}) or {}
                            tool_start = time.monotonic()
                            output = await self._dispatch_tool(tool_name, tool_input, user_ctx)
                            tool_use_count += 1
                            tool_latency = int((time.monotonic() - tool_start) * 1000)
                            if tool_name in ("run_sql", "run_skill") and "rows" in output:
                                last_rows = output.get("rows", [])
                                last_row_count = output.get("row_count", 0)
                            tool_traces.append(ToolTrace(
                                name=tool_name,
                                input=tool_input,
                                output=output,
                                latency_ms=tool_latency,
                            ))
                            tool_results.append(_make_tool_result_block(
                                getattr(block, "id", f"tool_{tool_use_count}"),
                                output,
                            ))
                        messages.append({"role": "user", "content": tool_results})
        else:
            validate_result = "skipped"

        return AgentResult(
            success=True,
            rows=last_rows,
            row_count=last_row_count,
            answer=last_answer,
            terminal_reason=terminal_reason_ref[0],
            turns_used=turns,
            tool_traces=tool_traces,
            validate_result=validate_result,
        )

    async def _dispatch_tool(
        self,
        tool_name: str,
        tool_input: dict,
        user_ctx: UserContext,
    ) -> dict:
        """Dispatch tool call to the appropriate executor. Never raises — returns error dict."""
        try:
            if tool_name == "run_sql":
                return await execute_run_sql(tool_input, user_ctx, self._db_pool)
            elif tool_name == "search_docs":
                return await execute_search_docs(tool_input, self._rag_search_fn)
            elif tool_name == "inspect_schema":
                return await execute_inspect_schema(tool_input)
            elif tool_name == "run_skill":
                return await execute_run_skill(tool_input, user_ctx, self._skill_runner)
            else:
                return {"error": f"未知工具：{tool_name}"}
        except Exception as e:
            log.exception("_dispatch_tool unexpected error tool=%s", tool_name)
            return {"error": f"工具執行錯誤：{type(e).__name__}"}

    async def _llm_call_for_validate(
        self,
        system: str,
        prompt: str,
        tools: list[dict],
    ) -> Any:
        """
        Adapter: validator.run_validate calls llm_call(system, prompt, tools) —
        same signature as the injected llm_call but messages are plain str.
        We convert to messages list format here.
        """
        messages = [{"role": "user", "content": prompt}]
        return await asyncio.wait_for(
            self._llm_call(system, messages, tools),
            timeout=0.9,  # slightly under validate's 1.0s budget
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def detect_media_type(b64_data: str) -> str:
    """Detect image media type from base64 data via magic bytes."""
    import base64 as _b64
    try:
        head = _b64.b64decode(b64_data[:16], validate=False)[:12]
    except Exception:
        return "image/jpeg"
    if head.startswith(b'\x89PNG\r\n\x1a\n'):
        return "image/png"
    if head.startswith(b'\xff\xd8\xff'):
        return "image/jpeg"
    if head.startswith(b'RIFF') and b'WEBP' in head:
        return "image/webp"
    if head.startswith(b'GIF87a') or head.startswith(b'GIF89a'):
        return "image/gif"
    return "image/jpeg"


def _build_user_content(query: str, image_base64: str | None) -> list[dict]:
    """Build the user message content list, with optional image block."""
    content: list[dict] = []
    if image_base64:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": detect_media_type(image_base64),
                "data": image_base64,
            },
        })
    content.append({"type": "text", "text": query})
    return content


def _make_tool_result_block(tool_use_id: str, output: dict) -> dict:
    """Format a tool_result content block for Anthropic messages API."""
    import json
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(output, ensure_ascii=False, default=str),
    }
