"""
Maximo query router using Claude tool_use (Function Calling).

Flow:
1. Check feature flag — if disabled, fallback immediately.
2. Check circuit breaker — if open (not available), fallback immediately.
3. Call Claude with tools, single-turn only.
4. Parse response:
   - stop_reason='tool_use' + exactly 1 tool_use block → dispatch tool → return result
   - else (end_turn / max_tokens / >1 tool_use / refusal / schema decode fail) → fallback
5. Fallback calls injected fallback_fn with original user query (not rewritten).
6. Record telemetry for every path.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable
from uuid import UUID, uuid4

from app.services.maximo_tools.base import (
    RouterDecision,
    Tool,
    ToolResult,
    UserContext,
)
from app.services.maximo_tools.feature_flag import is_tool_router_enabled
from app.services.maximo_tools.registry import ToolRegistry
from app.services.maximo_tools.telemetry import (
    FALLBACK_REASON_CIRCUIT_OPEN,
    FALLBACK_REASON_FEATURE_FLAG_DISABLED,
    FALLBACK_REASON_INVOCATION_ERROR,
    FALLBACK_REASON_LLM_TIMEOUT,
    FALLBACK_REASON_NO_TOOL,
    FALLBACK_REASON_TOOL_EXECUTION_ERROR,
    ToolCallRecord,
    record_tool_call,
)

logger = logging.getLogger(__name__)

# Fallback function signature:
#   async def fallback(query: str, user_ctx: UserContext, query_id: UUID) -> dict
# Returns dict with keys: rows, row_count, chart_hint (None), debug (dict with sql etc.)
FallbackFn = Callable[[str, UserContext, UUID], Awaitable[dict]]

# Anthropic call signature (injectable for test):
#   async def llm_tool_use(system: str, user_query: str, tools: list[dict]) -> AnthropicResponse
#   AnthropicResponse has: stop_reason, content (list of blocks)
LLMCallFn = Callable[[str, str, list[dict]], Awaitable[Any]]

_SYSTEM_PROMPT = (
    "你是 AI-KM Platform 的 Maximo 查詢助理。你可以使用下列工具回答車輛、工單、故障通報相關查詢。\n"
    "規則：\n"
    "1. 只在使用者問的問題明確對應到某個工具時才呼叫。\n"
    "2. 如果問題涉及跨工具組合、複雜條件、或工具清單未涵蓋的情境，不要呼叫任何工具，直接回覆 \"NO_TOOL\"。\n"
    "3. 參數要從使用者問題中抽取，不要自行推測不存在的資訊。\n"
)

_LLM_TIMEOUT_SECONDS = 10.0

# ---------------------------------------------------------------------------
# Error sanitization — never expose raw exception messages to callers
# ---------------------------------------------------------------------------
_SAFE_ERROR_MESSAGES: dict[str, str] = {
    "OperationalError": "資料庫連線或操作失敗",
    "ProgrammingError": "SQL 執行錯誤",
    "IntegrityError": "資料完整性違規",
    "DataError": "資料格式錯誤",
    "TimeoutError": "操作超時",
    "asyncio.TimeoutError": "執行超時",
    "ValueError": "參數驗證失敗",
    "KeyError": "遺失必要參數",
    "ConnectionError": "連線錯誤",
    "RuntimeError": "系統執行錯誤",
}


def _safe_error_message(exc: Exception) -> tuple[str, str]:
    """Return (code, user_facing_message). Never exposes raw exc args (may leak DB details)."""
    code = type(exc).__name__
    message = _SAFE_ERROR_MESSAGES.get(code, "系統執行錯誤")
    return code, message


class MaximoQueryRouter:
    def __init__(
        self,
        registry: ToolRegistry,
        llm_call: LLMCallFn,
        fallback_fn: FallbackFn,
        circuit_breaker=None,  # Optional: 既有 CircuitBreaker instance
        db_pool=None,
    ):
        self._registry = registry
        self._llm_call = llm_call
        self._fallback_fn = fallback_fn
        self._circuit_breaker = circuit_breaker
        self._db_pool = db_pool

    async def route(
        self,
        query: str,
        user_ctx: UserContext,
        audit_log_id: int | None = None,
    ) -> dict:
        """Main entry. Returns dict matching contracts/tool-api.md response shape."""
        query_id = uuid4()
        start = time.monotonic()

        # 1. Feature flag
        if not is_tool_router_enabled():
            return await self._do_fallback(
                query, user_ctx, query_id, FALLBACK_REASON_FEATURE_FLAG_DISABLED,
                audit_log_id, start,
            )

        # 2. Circuit breaker
        if self._is_circuit_open():
            return await self._do_fallback(
                query, user_ctx, query_id, FALLBACK_REASON_CIRCUIT_OPEN,
                audit_log_id, start,
            )

        # 3. Call LLM
        try:
            decision = await asyncio.wait_for(
                self._ask_llm(query),
                timeout=_LLM_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return await self._do_fallback(
                query, user_ctx, query_id, FALLBACK_REASON_LLM_TIMEOUT,
                audit_log_id, start,
            )
        except Exception:
            logger.exception("LLM call failed, fallback", extra={"query_id": str(query_id)})
            return await self._do_fallback(
                query, user_ctx, query_id, FALLBACK_REASON_INVOCATION_ERROR,
                audit_log_id, start,
            )

        # 4. Dispatch tool or fallback
        if decision.route_path == "fallback":
            return await self._do_fallback(
                query, user_ctx, query_id, decision.fallback_reason or FALLBACK_REASON_NO_TOOL,
                audit_log_id, start,
            )

        # tool_use path — look up the tool
        tool = self._registry.get(decision.tool_name)
        if tool is None:
            return await self._do_fallback(
                query, user_ctx, query_id, FALLBACK_REASON_INVOCATION_ERROR,
                audit_log_id, start,
            )

        try:
            result: ToolResult = await tool.execute(decision.tool_input, user_ctx)
        except Exception as e:
            logger.exception(
                "Tool execute failed: %s", decision.tool_name,
                extra={"query_id": str(query_id), "tool_name": decision.tool_name},
            )
            _err_code, _err_msg = _safe_error_message(e)
            elapsed = int((time.monotonic() - start) * 1000)
            await self._record(ToolCallRecord(
                query_id=query_id, audit_log_id=audit_log_id,
                user_id=user_ctx.user_id, tool_name=decision.tool_name,
                params=decision.tool_input or {}, route_path="error",
                latency_ms=elapsed, success=False, row_count=None,
                fallback_reason=FALLBACK_REASON_TOOL_EXECUTION_ERROR,
                error_message=_err_msg,
            ))
            return {
                "query_id": str(query_id),
                "route_path": "error",
                "tool_name": decision.tool_name,
                "tool_input": decision.tool_input,
                "rows": [],
                "row_count": 0,
                "chart_hint": None,
                "elapsed_ms": elapsed,
                "debug": {"error": {"code": _err_code, "message": _err_msg}},
            }

        elapsed = int((time.monotonic() - start) * 1000)
        await self._record(ToolCallRecord(
            query_id=query_id, audit_log_id=audit_log_id,
            user_id=user_ctx.user_id, tool_name=decision.tool_name,
            params=decision.tool_input or {}, route_path="tool",
            latency_ms=elapsed, success=result.success,
            row_count=result.row_count, fallback_reason=None,
            error_message=None,
        ))

        return {
            "query_id": str(query_id),
            "route_path": "tool",
            "tool_name": decision.tool_name,
            "tool_input": decision.tool_input,
            "rows": result.rows,
            "row_count": result.row_count,
            "chart_hint": result.chart_hint,
            "elapsed_ms": elapsed,
            "debug": {
                "llm_stop_reason": decision.llm_stop_reason,
            },
        }

    # -- internal ---------------------------------------------------------

    async def _ask_llm(self, query: str) -> RouterDecision:
        """
        Single-turn LLM call, parse response into RouterDecision.
        Rules (from research.md R7):
          - stop_reason='tool_use' + exactly 1 tool_use block → route_path=tool
          - else → route_path=fallback
        """
        tool_schemas = [
            {
                "name": d.name,
                "description": d.description,
                "input_schema": d.input_schema,
            }
            for d in self._registry.list_definitions()
        ]

        response = await self._llm_call(_SYSTEM_PROMPT, query, tool_schemas)
        stop_reason = getattr(response, "stop_reason", "unknown")

        # Count tool_use blocks
        blocks = getattr(response, "content", []) or []
        tool_use_blocks = [b for b in blocks if getattr(b, "type", None) == "tool_use"]

        if stop_reason == "tool_use" and len(tool_use_blocks) == 1:
            block = tool_use_blocks[0]
            return RouterDecision(
                route_path="tool",
                tool_name=getattr(block, "name", None),
                tool_input=getattr(block, "input", {}),
                llm_stop_reason=stop_reason,
            )

        # Any other case → fallback
        reason = FALLBACK_REASON_NO_TOOL if stop_reason == "end_turn" else FALLBACK_REASON_INVOCATION_ERROR
        return RouterDecision(
            route_path="fallback",
            fallback_reason=reason,
            llm_stop_reason=stop_reason,
        )

    async def _do_fallback(
        self, query: str, user_ctx: UserContext, query_id: UUID,
        reason: str, audit_log_id: int | None, start: float,
    ) -> dict:
        """Call injected fallback_fn with ORIGINAL query (not rewritten)."""
        try:
            fb_result = await self._fallback_fn(query, user_ctx, query_id)
        except Exception as e:
            logger.exception("Fallback also failed", extra={"query_id": str(query_id)})
            _err_code, _err_msg = _safe_error_message(e)
            elapsed = int((time.monotonic() - start) * 1000)
            await self._record(ToolCallRecord(
                query_id=query_id, audit_log_id=audit_log_id,
                user_id=user_ctx.user_id, tool_name=None, params={},
                route_path="error", latency_ms=elapsed, success=False,
                row_count=None, fallback_reason=reason,
                error_message=_err_msg,
            ))
            return {
                "query_id": str(query_id),
                "route_path": "error",
                "rows": [],
                "row_count": 0,
                "chart_hint": None,
                "elapsed_ms": elapsed,
                "debug": {
                    "error": {"code": _err_code, "message": _err_msg},
                    "fallback_reason": reason,
                },
            }

        elapsed = int((time.monotonic() - start) * 1000)
        await self._record(ToolCallRecord(
            query_id=query_id, audit_log_id=audit_log_id,
            user_id=user_ctx.user_id, tool_name=None, params={},
            route_path="fallback", latency_ms=elapsed, success=True,
            row_count=fb_result.get("row_count"),
            fallback_reason=reason, error_message=None,
        ))
        return {
            "query_id": str(query_id),
            "route_path": "fallback",
            "tool_name": None,
            "tool_input": None,
            "rows": fb_result.get("rows", []),
            "row_count": fb_result.get("row_count", 0),
            "chart_hint": fb_result.get("chart_hint"),
            "elapsed_ms": elapsed,
            "debug": {**fb_result.get("debug", {}), "fallback_reason": reason},
        }

    def _is_circuit_open(self) -> bool:
        """
        Returns True when the circuit breaker is not available (i.e., circuit is open).
        Delegates to injected circuit_breaker; tolerant to None.

        Expects duck-typed `is_available` property (bool or callable):
          - CLOSED / HALF_OPEN with quota → is_available=True → circuit NOT open
          - OPEN                           → is_available=False → circuit IS open
        """
        cb = self._circuit_breaker
        if cb is None:
            return False
        try:
            is_available = cb.is_available
            available = is_available() if callable(is_available) else bool(is_available)
            return not available
        except Exception:
            logger.exception("circuit breaker introspection failed, treating as closed")
            return False

    async def _record(self, record: ToolCallRecord) -> None:
        """Fire-and-forget telemetry write. Skipped when db_pool is None."""
        if self._db_pool is None:
            return  # skip telemetry if no pool injected (test setups)
        try:
            await record_tool_call(record, self._db_pool)
        except Exception:
            logger.exception(
                "router telemetry write unexpectedly raised",
                extra={"query_id": str(record.query_id), "tool_name": record.tool_name},
            )
