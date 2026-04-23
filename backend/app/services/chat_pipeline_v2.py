"""
Chat Pipeline v2 — Skills System Pipeline (S0).

Flow:
  image_base64 present  →  agent_fallback_image (skip PreFilter/Terminology/SkillMatcher)
  otherwise             →  PreFilter → TerminologyNormalizer → SkillMatcher
                            → skill_exec (score ≥ 0.85, 0 LLM cost)
                            → agent_fallback (score < 0.85 or exec fails)
                            → follow_up → audit → done

Feature flag: settings.enable_skills_system=False keeps old pipeline active.
Grayscale: user_id % 20 == 0 → 5%; images bypass grayscale when flag is on.

NOT wired to chat.py yet — imported by S0 modifications there.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.config import get_settings
from app.services.pre_filter import get_pre_filter
from app.services.terminology_normalizer.normalizer import normalize as terminology_normalize
from app.services.skills.matcher import SkillMatcher, MATCH_THRESHOLD

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Audit task GC guard (M3)
# asyncio only holds a weak-ref to tasks; keep strong refs here until done.
# ---------------------------------------------------------------------------
_AUDIT_TASKS: set[asyncio.Task] = set()


def _fire_audit(coro) -> asyncio.Task:
    """Create audit task with strong ref to prevent GC."""
    task = asyncio.create_task(coro)
    _AUDIT_TASKS.add(task)
    task.add_done_callback(_AUDIT_TASKS.discard)
    return task


# ---------------------------------------------------------------------------
# Grayscale helper
# ---------------------------------------------------------------------------

def _should_use_v2(user_id: str | None) -> bool:
    """5% grayscale — real user_id UUID hash % 20 == 0.
    Returns False for anonymous / None (never assume bucket membership)."""
    if not user_id:
        return False
    h = int(hashlib.md5(str(user_id).encode()).hexdigest()[:8], 16)
    return h % 20 == 0


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    """Unified result from the v2 pipeline."""
    recovery_path: str  # skill_direct | agent_fallback | agent_fallback_image | pre_filter_reject
    # SQL result fields (present when recovery_path in skill_direct / agent_fallback)
    sql: str | None = None
    data: list[dict] = field(default_factory=list)
    row_count: int = 0
    columns: list[str] = field(default_factory=list)
    explanation: str = ""
    # RAG / text answer (present when agent returned pure RAG result)
    answer: str = ""
    sources: list[Any] = field(default_factory=list)
    # Metadata
    normalized_query: str = ""
    applied_terms: list[tuple] = field(default_factory=list)
    skill_name: str | None = None
    skill_score: float = 0.0
    total_llm_ms: int = 0
    estimated_tokens: int = 0
    error: str | None = None
    # Agent trace (agent_fallback paths)
    agent_trace: list[dict] = field(default_factory=list)
    image_present: bool = False
    # pre_filter_reject sub-type (structured enum, avoids string-in checks in chat.py)
    pre_filter_action: str | None = None  # "chitchat" | "clarify" | "cost_block"


# ---------------------------------------------------------------------------
# Skill execution (score ≥ 0.85, 0 LLM cost)
# ---------------------------------------------------------------------------

async def _exec_skill(skill_hit: dict, normalized_query: str, db) -> dict | None:
    """
    Execute the sql_template from the matched skill.
    Returns a dict with rows/row_count/columns/sql on success, None on failure.
    """
    from app.services.skills.repository import get_skill_by_id
    from app.services.maximo_nl2sql_tools import _is_safe_select
    from uuid import UUID

    try:
        skill_id = skill_hit.get("skill_id")
        skill = await get_skill_by_id(db, UUID(str(skill_id)))
        if not skill:
            return None

        sql_template = skill.get("sql_template") or ""
        if not sql_template or not _is_safe_select(sql_template):
            log.warning("skill_exec: unsafe or missing SQL template for skill=%s", skill_id)
            return None

        from sqlalchemy import text as _text
        result = await db.execute(_text(sql_template))
        rows = [dict(r._mapping) for r in result.fetchall()]
        columns = list(rows[0].keys()) if rows else []
        return {
            "sql": sql_template,
            "data": rows,
            "row_count": len(rows),
            "columns": columns,
        }
    except Exception as exc:
        log.warning("skill_exec failed for skill=%s: %s", skill_hit.get("skill_id"), exc)
        return None


# ---------------------------------------------------------------------------
# Agent fallback builder
# ---------------------------------------------------------------------------

def _build_skill_agent(db):
    """Build a SkillAgentFallback instance wired to Anthropic SDK."""
    from app.services.skill_agent.loop import SkillAgentFallback
    from app.config import get_settings
    import anthropic

    settings = get_settings()
    api_key = settings.anthropic_api_key or ""
    model = settings.anthropic_model or "claude-sonnet-4-6"

    client = anthropic.AsyncAnthropic(api_key=api_key) if api_key else None

    async def llm_call(system: str, messages: list[dict], tools: list[dict]) -> Any:
        if client is None:
            raise RuntimeError("anthropic_api_key not set; cannot run SkillAgent")
        resp = await client.messages.create(
            model=model,
            max_tokens=1024,
            system=system,
            tools=tools,
            messages=messages,
        )
        return resp

    return SkillAgentFallback(llm_call=llm_call, db_pool=db)


# ---------------------------------------------------------------------------
# Audit writer
# ---------------------------------------------------------------------------

async def _write_audit(
    *,
    user_id: str | None,
    user_email: str | None,
    question: str,
    sql_generated: str | None,
    tables_accessed: list[str],
    row_count: int,
    execution_ms: int | None,
    recovery_path: str,
    total_llm_ms: int,
    estimated_tokens: int,
    request_id: str | None,
    conversation_id: str | None,
) -> None:
    """Fire-and-forget audit write. Never blocks the main response."""
    try:
        from app.db.session import get_db_context
        from sqlalchemy import text as _text

        tables_arr = tables_accessed or []
        async with get_db_context() as db:
            await db.execute(
                _text("""
                    INSERT INTO query_audit_log
                        (user_id, user_email, question, sql_generated, tables_accessed,
                         row_count, execution_ms, mode, request_id, conversation_id,
                         recovery_path, total_llm_ms, estimated_tokens)
                    VALUES
                        (:uid, :email, :q, :sql, :tables,
                         :row_count, :exec_ms, 'nl2sql', :rid, :cid,
                         :rec_path, :llm_ms, :est_tokens)
                """),
                {
                    "uid": user_id,
                    "email": user_email,
                    "q": question,
                    "sql": sql_generated,
                    "tables": tables_arr,
                    "row_count": row_count,
                    "exec_ms": execution_ms,
                    "rid": request_id,
                    "cid": conversation_id,
                    "rec_path": recovery_path,
                    "llm_ms": total_llm_ms,
                    "est_tokens": estimated_tokens,
                },
            )
    except Exception as e:
        log.warning("v2 audit write failed (non-blocking): %s", e)


# ---------------------------------------------------------------------------
# Follow-up generator
# ---------------------------------------------------------------------------

def _emit_follow_up(result: PipelineResult, query: str) -> list:
    """Return follow-up suggestions based on result type."""
    if result.sql and result.data:
        # Inline version of _generate_sql_follow_ups (avoids circular import with chat.py)
        suggestions = []
        if result.row_count > 0:
            suggestions.append("只看最近一個月的")
        if "工單" in query or "mxwo" in query.lower():
            suggestions.append("這些工單的車輛資訊？")
            suggestions.append("這些工單的相關 SOP？")
        if "故障" in query or "mxsr" in query.lower():
            suggestions.append("這些故障通報的處理情形？")
            suggestions.append("相關故障的維修 SOP？")
        if "資產" in query or "asset" in query.lower():
            suggestions.append("這些車輛的最近工單？")
        return suggestions[:3]
    return []


# ---------------------------------------------------------------------------
# Main pipeline entry
# ---------------------------------------------------------------------------

async def run_pipeline_v2(
    *,
    query: str,
    user_ctx: dict,
    conversation_history: list[dict] | None = None,
    image_base64: str | None = None,
    request_id: str | None = None,
    conversation_id: str | None = None,
    qdrant_client=None,
    embedder=None,
    db=None,
) -> PipelineResult:
    """
    Run the v2 Skills System pipeline.

    Steps:
      1. Image bypass → agent_fallback_image
      2. PreFilter → chitchat / clarify / cost_block → pre_filter_reject
      3. TerminologyNormalizer → normalized_query
      4. SkillMatcher (top_k=5, threshold=0.85)
         a. Hit  → skill_exec → skill_direct
         b. Miss → agent_fallback
      5. Audit (fire-and-forget)

    Raises: nothing (errors captured in PipelineResult.error)
    """
    from app.services.maximo_tools.base import UserContext

    pipeline_start = time.monotonic()

    # ------------------------------------------------------------------
    # Step 0: Image bypass
    # ------------------------------------------------------------------
    if image_base64:
        log.info("[v2] image_base64 present → agent_fallback_image")
        t0 = time.monotonic()
        try:
            agent = _build_skill_agent(db)
            user_ctx_obj = UserContext(
                user_id=str(user_ctx.get("id", "chat")),
                role=user_ctx.get("role", "viewer"),
            )
            agent_result = await agent.run(
                query=query,
                user_ctx=user_ctx_obj,
                conversation_history=conversation_history,
                image_base64=image_base64,
            )
            agent_llm_ms = agent_result.elapsed_ms
            traces = [
                {"name": t.name, "input": t.input, "latency_ms": t.latency_ms}
                for t in agent_result.tool_traces
            ]
            pipeline_ms = int((time.monotonic() - pipeline_start) * 1000)
            result = PipelineResult(
                recovery_path="agent_fallback_image",
                sql=None,
                data=agent_result.rows,
                row_count=agent_result.row_count,
                columns=list(agent_result.rows[0].keys()) if agent_result.rows else [],
                answer=agent_result.answer,
                total_llm_ms=agent_llm_ms,
                image_present=True,
                agent_trace=traces,
            )
            _fire_audit(_write_audit(
                user_id=str(user_ctx.get("id")),
                user_email=user_ctx.get("email"),
                question=query,
                sql_generated=None,
                tables_accessed=[],
                row_count=agent_result.row_count,
                execution_ms=pipeline_ms,
                recovery_path="agent_fallback_image",
                total_llm_ms=agent_llm_ms,
                estimated_tokens=0,
                request_id=request_id,
                conversation_id=conversation_id,
            ))
            return result
        except Exception as exc:
            log.exception("v2 agent_fallback_image failed")
            return PipelineResult(
                recovery_path="agent_fallback_image",
                image_present=True,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Step 1: PreFilter
    # ------------------------------------------------------------------
    pre_filter = get_pre_filter()
    verdict = pre_filter.check(query)
    log.debug("[v2] pre_filter verdict=%s for %r", verdict.action, query[:60])

    if verdict.action != "allow":
        _fire_audit(_write_audit(
            user_id=str(user_ctx.get("id")),
            user_email=user_ctx.get("email"),
            question=query,
            sql_generated=None,
            tables_accessed=[],
            row_count=0,
            execution_ms=0,
            recovery_path="pre_filter_reject",
            total_llm_ms=0,
            estimated_tokens=0,
            request_id=request_id,
            conversation_id=conversation_id,
        ))
        return PipelineResult(
            recovery_path="pre_filter_reject",
            error=verdict.reason,
            pre_filter_action=verdict.action,  # "chitchat" | "clarify" | "cost_block"
        )

    # ------------------------------------------------------------------
    # Step 2: TerminologyNormalizer
    # ------------------------------------------------------------------
    try:
        normalized_query, applied_terms = terminology_normalize(query)
    except Exception:
        normalized_query, applied_terms = query, []
    log.debug("[v2] terminology: applied=%d terms", len(applied_terms))

    # ------------------------------------------------------------------
    # Step 3: SkillMatcher
    # ------------------------------------------------------------------
    skill_hits: list[dict] = []
    if qdrant_client is not None and embedder is not None:
        try:
            matcher = SkillMatcher(qdrant=qdrant_client, embedder=embedder)
            skill_hits = matcher.match(normalized_query, top_k=5)
        except Exception as exc:
            log.warning("[v2] SkillMatcher failed (non-blocking): %s", exc)

    top_hit = skill_hits[0] if skill_hits else None
    use_skill_exec = (
        top_hit is not None
        and top_hit.get("score", 0.0) >= MATCH_THRESHOLD
    )

    # ------------------------------------------------------------------
    # Step 4a: Skill Exec (0 LLM cost)
    # ------------------------------------------------------------------
    if use_skill_exec and db is not None:
        t0 = time.monotonic()
        exec_result = await _exec_skill(top_hit, normalized_query, db)
        exec_ms = int((time.monotonic() - t0) * 1000)

        if exec_result:
            log.info("[v2] skill_direct: skill=%s score=%.3f rows=%d",
                     top_hit["name"], top_hit["score"], exec_result["row_count"])
            result = PipelineResult(
                recovery_path="skill_direct",
                sql=exec_result["sql"],
                data=exec_result["data"],
                row_count=exec_result["row_count"],
                columns=exec_result["columns"],
                explanation=f"技能直接執行（{top_hit['name']}）",
                normalized_query=normalized_query,
                applied_terms=applied_terms,
                skill_name=top_hit["name"],
                skill_score=top_hit["score"],
                total_llm_ms=0,
                estimated_tokens=0,
            )
            _fire_audit(_write_audit(
                user_id=str(user_ctx.get("id")),
                user_email=user_ctx.get("email"),
                question=query,
                sql_generated=exec_result["sql"],
                tables_accessed=[],
                row_count=exec_result["row_count"],
                execution_ms=exec_ms,
                recovery_path="skill_direct",
                total_llm_ms=0,
                estimated_tokens=0,
                request_id=request_id,
                conversation_id=conversation_id,
            ))
            return result
        # skill_exec failed → fall through to agent_fallback
        log.info("[v2] skill_exec failed, falling back to agent")

    # ------------------------------------------------------------------
    # Step 4b: Agent Fallback
    # ------------------------------------------------------------------
    t0 = time.monotonic()
    try:
        agent = _build_skill_agent(db)
        user_ctx_obj = UserContext(
            user_id=str(user_ctx.get("id", "chat")),
            role=user_ctx.get("role", "viewer"),
        )
        agent_result = await agent.run(
            query=normalized_query,
            user_ctx=user_ctx_obj,
            conversation_history=conversation_history,
            image_base64=None,
        )
        agent_ms = int((time.monotonic() - t0) * 1000)
        traces = [
            {"name": t.name, "input": t.input, "latency_ms": t.latency_ms}
            for t in agent_result.tool_traces
        ]

        # Determine if agent result is SQL or RAG
        has_sql_result = bool(agent_result.rows)
        result_sql = None
        # Extract SQL from tool traces
        for trace in agent_result.tool_traces:
            if trace.name == "run_sql" and trace.input.get("sql"):
                result_sql = trace.input["sql"]
                break

        result = PipelineResult(
            recovery_path="agent_fallback",
            sql=result_sql,
            data=agent_result.rows,
            row_count=agent_result.row_count,
            columns=list(agent_result.rows[0].keys()) if agent_result.rows else [],
            answer=agent_result.answer,
            normalized_query=normalized_query,
            applied_terms=applied_terms,
            total_llm_ms=agent_result.elapsed_ms,
            estimated_tokens=0,
            agent_trace=traces,
        )
        _fire_audit(_write_audit(
            user_id=str(user_ctx.get("id")),
            user_email=user_ctx.get("email"),
            question=query,
            sql_generated=result_sql,
            tables_accessed=[],
            row_count=agent_result.row_count,
            execution_ms=agent_ms,
            recovery_path="agent_fallback",
            total_llm_ms=agent_result.elapsed_ms,
            estimated_tokens=0,
            request_id=request_id,
            conversation_id=conversation_id,
        ))
        return result

    except Exception as exc:
        log.exception("[v2] agent_fallback failed")
        agent_ms = int((time.monotonic() - t0) * 1000)
        _fire_audit(_write_audit(
            user_id=str(user_ctx.get("id")),
            user_email=user_ctx.get("email"),
            question=query,
            sql_generated=None,
            tables_accessed=[],
            row_count=0,
            execution_ms=agent_ms,
            recovery_path="agent_fallback",
            total_llm_ms=0,
            estimated_tokens=0,
            request_id=request_id,
            conversation_id=conversation_id,
        ))
        return PipelineResult(
            recovery_path="agent_fallback",
            normalized_query=normalized_query,
            applied_terms=applied_terms,
            error=str(exc),
        )
