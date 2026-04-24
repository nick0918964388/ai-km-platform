"""Chat and search router for RAG queries."""
import asyncio
import json
import time
import logging
import urllib.request
import urllib.error
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    SearchRequest,
    SearchResponse,
    TerminalState,
)
from app.services import rag
from app.services.intent_classifier import get_intent_classifier, QueryIntent
from app.services.intent_router import detect_intent, detect_ambiguity
from app.services.input_guardrail import get_input_guardrail, GuardrailAction
from app.services.output_scanner import get_output_scanner, ScanAction
from app.middleware.rate_limit import check_rate_limit, record_guardrail_block
from app.services.context_manager import build_optimized_context, compress_context
from app.services.call_tracer import CallTracer, trace_llm_call
from app.services.result_budget import ResultBudget
from app.services.domain_mapper import translate_rows
from app.config import get_settings, get_active_llm_info
from app.db.session import get_db_context

log = logging.getLogger(__name__)

# GC guard for fire-and-forget tasks in the v2 branch (M3 fix).
# asyncio holds only weak-refs to tasks; keeping strong refs here prevents GC interruption.
_CHAT_TASKS: set[asyncio.Task] = set()


def _is_multi_facet_query(query: str) -> bool:
    """偵測查詢是否涉及多個資料面向（括號列舉 / 冒號列舉 / 多個頓號分隔的主題）。
    這類查詢單一 SQL 難以涵蓋，應路由到 hybrid 分解。
    """
    import re
    # 括號內含頓號分隔（如「(故障、檢修、成本)」）
    if re.search(r'[（(][^）)]*[、,，][^）)]*[、,，][^）)]*[）)]', query):
        return True
    # 冒號後含頓號分隔（如「資料：工單、故障、成本」）
    if re.search(r'[：:][^：:]*[、,，][^：:]*[、,，]', query):
        return True
    # 多個面向關鍵字同時出現（3 個以上）
    facets = ['故障', '工單', '成本', '檢修', '維修', '資產', '車輛', '零件', '庫存']
    hits = sum(1 for f in facets if f in query)
    if hits >= 3:
        return True
    return False


def _sanitize_explanation(text: str) -> str:
    """Remove internal table/column names from explanation text."""
    if not text:
        return text
    import re
    # Remove table name references like "maximo_xxx 表中" or standalone
    text = re.sub(r'maximo_\w+\s*表?中?', '', text)
    # Remove column references in parentheses like "(eq4)" or "(wonum)"
    text = re.sub(r'\s*\(\w{2,20}\)\s*', ' ', text)
    # Remove orphaned patterns from table name removal
    text = re.sub(r'從\s+中', '', text)            # 從 [removed] 中
    text = re.sub(r'從\s+查詢', '查詢', text)      # 從 [removed] 查詢
    text = re.sub(r'列出\s+中?的?', '列出', text)   # 列出 [removed] 中的
    text = re.sub(r'查詢\s+中', '查詢', text)       # 查詢 [removed] 中
    text = re.sub(r'查詢\s*，', '', text)            # 查詢 ，
    # Clean up
    text = re.sub(r'\s{2,}', ' ', text).strip()
    text = re.sub(r'^[，、。\s]+', '', text)
    return text
router = APIRouter(prefix="/api", tags=["chat"])


class ChatFeedback(BaseModel):
    message_id: str
    query: str
    rating: str  # "up" or "down"
    comment: Optional[str] = None
    sql_query: Optional[str] = None


class SourceFeedback(BaseModel):
    chunk_id: str
    document_id: Optional[str] = None
    question: Optional[str] = None
    rating: str  # "up" or "down"


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat with the knowledge base using RAG.

    Supports multimodal queries with text and/or images.
    Retrieves relevant documents and generates an answer using GPT-4o.
    """
    answer, sources = rag.chat(
        query=request.query,
        image_base64=request.image_base64,
        top_k=request.top_k,
    )

    return ChatResponse(
        answer=answer,
        sources=sources,
    )


def _generate_sql_follow_ups(query: str, result: dict) -> list:
    """Generate follow-up suggestions based on SQL query result."""
    suggestions = []
    if result.get("row_count", 0) > 0:
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


async def _write_rag_fallback_audit(query: str, rewrite_history: list,
                                    request_id: str = None, conversation_id: str = None,
                                    recovery_path: str = "rag_fallback"):
    """Write a query_audit_log entry for SQL-failed non-success paths."""
    try:
        async with get_db_context() as db:
            rw_hist_json = json.dumps(rewrite_history, ensure_ascii=False) if rewrite_history else None
            await db.execute(text("""
                INSERT INTO query_audit_log
                    (user_id, user_email, question, sql_generated, tables_accessed,
                     row_count, execution_ms, mode, request_id, conversation_id,
                     original_question, rewrite_history, recovery_path)
                VALUES
                    (NULL, NULL, :q, NULL, '{}', 0, NULL, 'nl2sql', :rid, :cid,
                     NULL, CAST(:rw_hist AS jsonb), :rec_path)
            """), {
                "q": query,
                "rid": request_id,
                "cid": conversation_id,
                "rw_hist": rw_hist_json,
                "rec_path": recovery_path,
            })
    except Exception as e:
        log.warning("寫入稽核日誌失敗 (recovery_path=%s): %s", recovery_path, e)


async def _generate_sql_recovery_options(query: str, error: str, context: list = None) -> list[dict]:
    """Generate clarification options when SQL query fails."""
    settings = get_settings()
    llm_url, llm_model = get_active_llm_info()

    context_str = ""
    if context:
        recent = context[-3:]
        context_str = "\n".join(f"{m.get('role','user')}: {m.get('content','')[:100]}" for m in recent)

    prompt = f"""使用者的查詢無法用 SQL 完成。請分析原因，並產生 2-3 個替代查詢建議。

使用者問題：{query}
錯誤原因：{error[:200]}
{"對話脈絡：" + context_str if context_str else ""}

可查詢的資料表：
- maximo_assets（資產/車輛）
- maximo_pm_workorders（預防保養工單）
- maximo_cm_workorders（矯正維修工單）
- maximo_fault_reports（故障通報）

請回傳 JSON 陣列，每個項目包含 label（中文顯示）和 query（改寫後的完整問題）：
[{{"label": "按機務段統計核簽中工單", "query": "核簽中的工單按機務段分布統計"}}, ...]

只回傳 JSON，不要其他文字。"""

    try:
        import re as _re
        _provider = getattr(settings, "llm_provider", "ollama")

        if _provider == "anthropic" and getattr(settings, "anthropic_api_key", None):
            import httpx
            async with httpx.AsyncClient() as _http:
                _resp = await asyncio.wait_for(
                    _http.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": settings.anthropic_api_key,
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json",
                        },
                        json={
                            "model": llm_model,
                            "max_tokens": 500,
                            "messages": [{"role": "user", "content": prompt}],
                        },
                        timeout=10.0,
                    ),
                    timeout=12.0,
                )
                _resp.raise_for_status()
                _data = _resp.json()
                text_blocks = [b.get("text", "") for b in _data.get("content", []) if b.get("type") == "text"]
                content = "".join(text_blocks).strip()
        else:
            from openai import AsyncOpenAI
            _api_key = (
                settings.openai_api_key if _provider == "openai" else
                getattr(settings, "ollama_chat_api_key", None)
            ) or "sk-unused"
            client = AsyncOpenAI(base_url=llm_url, api_key=_api_key)
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=llm_model,
                    messages=[{"role": "user", "content": f"/no_think\n{prompt}"}],
                    temperature=0.3,
                    max_tokens=500,
                ),
                timeout=10.0,
            )
            content = (response.choices[0].message.content or "").strip()

        content = _re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]

        start = content.find('[')
        end = content.rfind(']') + 1
        if start >= 0 and end > start:
            options = json.loads(content[start:end])
            valid = [o for o in options if isinstance(o, dict) and "label" in o and "query" in o]
            return valid[:3]
    except Exception as e:
        log.warning("Failed to generate recovery options: %s", e)

    return []


# --- Async Chat Job endpoints ---

@router.post("/chat/jobs")
async def submit_chat_job(request: ChatRequest):
    """Submit a chat query as an async background job. Returns job_id immediately."""
    from app.services import chat_job_manager as jm
    from app.services.chat_job_runner import run_chat_job
    job_id = jm.create_job(request.query)
    asyncio.create_task(run_chat_job(job_id, request.model_dump()))
    return {"job_id": job_id, "status": "pending"}


@router.get("/chat/jobs/{job_id}")
async def get_chat_job(job_id: str, after: int = 0):
    """Poll a chat job's status and events. Use ?after=N for incremental polling."""
    from app.services import chat_job_manager as jm
    status = jm.get_status(job_id)
    if not status:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    if after > 0:
        status["events"] = jm.get_events(job_id, after)
    return status


@router.post("/chat/jobs/{job_id}/cancel")
async def cancel_chat_job(job_id: str):
    """Cancel a running chat job."""
    from app.services import chat_job_manager as jm
    status = jm.get_status(job_id)
    if not status:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    jm.cancel_job(job_id)
    return {"success": True, "job_id": job_id}


@router.get("/chat/jobs/{job_id}/stream")
async def stream_chat_job(job_id: str):
    """Stream a chat job's events as SSE. Polls Redis every 300ms."""
    from app.services import chat_job_manager as jm

    async def event_stream():
        cursor = 0
        while True:
            status = jm.get_status(job_id)
            if not status:
                yield f"data: {json.dumps({'type': 'error', 'data': 'Job not found'})}\n\n"
                break
            events = jm.get_events(job_id, cursor)
            for event in events:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                cursor += 1
            if status.get("status") in ("done", "error"):
                break
            await asyncio.sleep(0.3)

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no",
    })


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, http_request: Request):
    """
    Streaming chat with the knowledge base using RAG.

    Returns Server-Sent Events (SSE) with streaming response.
    Event types:
    - sources: Retrieved document sources (sent first)
    - content: Streaming text content
    - metadata: Model info, duration, token usage (sent at end)
    - follow_up: Follow-up questions suggestions
    - done: Stream complete signal
    - error: Error message
    """
    settings = get_settings()
    llm_url, llm_model = get_active_llm_info()

    # === Security #5: Rate Limiting ===
    # conversation_id 是最可靠的使用者識別（同一 user 的多 conversation 仍應分限），
    # 無 conv_id 時退回 IP。Cache 斷線 fail-open。
    _rate_key = request.conversation_id or (http_request.client.host if http_request.client else "anonymous")
    try:
        check_rate_limit(_rate_key, endpoint="chat")
    except HTTPException:
        raise
    except Exception as _e:
        log.debug("rate_limit check error (fail-open): %s", _e)

    async def generate():
        def sse_event(event_type, data=None, terminal: TerminalState = None):
            payload = {'type': event_type}
            if data is not None:
                payload['data'] = data
            if terminal is not None:
                payload['terminal'] = terminal.value
            return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        try:
            query = request.query
            conversation_id = request.conversation_id
            total_start = time.time()
            tracer = CallTracer()
            budget = ResultBudget()  # Pattern 8: per-query 50, per-conversation 200

            # === Security #1: Input Guardrail ===
            # Topic classifier + Jailbreak detector. Off-topic / jailbreak 直接返回婉拒，
            # 不進入任何 LLM pipeline（省成本 + 防濫用）。
            guardrail = get_input_guardrail()
            gr_result = guardrail.check(query)
            if gr_result.action != GuardrailAction.ALLOW:
                log.warning(
                    "[chat_stream] guardrail blocked: action=%s reason=%s matches=%s",
                    gr_result.action.value, gr_result.reason, gr_result.matched_patterns,
                )
                # Security #5: 累計 guardrail block 次數，超過閾值觸發 alert
                # 僅針對「被拒絕」的情況記帳（greeting 不算異常）
                if gr_result.action in (
                    GuardrailAction.REFUSE_OFF_TOPIC,
                    GuardrailAction.REFUSE_JAILBREAK,
                ):
                    try:
                        record_guardrail_block(_rate_key)
                    except Exception:
                        pass
                # Audit via rag.log_search_metrics（既有機制）
                try:
                    asyncio.create_task(rag.log_search_metrics(
                        query=query,
                        search_query=None,
                        sources=[],
                        quality=f"guardrail_{gr_result.action.value}",
                        duration_ms=0,
                        intent="guardrail_block",
                        request_id=tracer.request_id,
                        conversation_id=conversation_id,
                    ))
                except Exception:
                    pass
                # 以正常 SSE 格式返回婉拒訊息（前端不需特殊處理）
                yield sse_event('content', gr_result.refusal_message)
                total_ms = int((time.time() - total_start) * 1000)
                yield sse_event('metadata', {
                    'duration_ms': total_ms,
                    'intent': {"intent": "guardrail_block", "reason": gr_result.reason},
                    'request_id': tracer.request_id,
                })
                yield sse_event('done', {'total_ms': total_ms, 'reason': 'guardrail_block'},
                                terminal=TerminalState.COMPLETED)
                return

            # Short follow-up merging: if query is very short, merge with previous
            # user query to provide context. Triggers when:
            # - Previous turn was clarification/failure, OR
            # - Previous turn was a successful SQL query (user refining results)
            if len(query) <= 15 and request.context and len(request.context) >= 2:
                prev_user = None
                prev_assistant = None
                prev_intent = None
                for m in reversed(request.context):
                    if m.get("role") == "assistant" and prev_assistant is None:
                        prev_assistant = m.get("content", "")
                        prev_intent = m.get("intent")
                    elif m.get("role") == "user" and prev_user is None:
                        prev_user = m.get("content", "")
                    if prev_user and prev_assistant:
                        break
                should_merge = False
                if prev_assistant:
                    is_clarification_or_fail = any(
                        kw in prev_assistant for kw in ["釐清", "澄清", "clarif", "未能成功", "查詢失敗", "需要澄清"]
                    )
                    is_sql_followup = prev_intent == "sql" or any(
                        m.get("intent") == "sql" for m in request.context[-4:]
                    )
                    should_merge = is_clarification_or_fail or is_sql_followup
                if prev_user and should_merge:
                    merged = f"{prev_user}，{query}"
                    log.info("Short follow-up merged: '%s' + '%s' → '%s'", prev_user[:30], query, merged)
                    query = merged

            # === Proactive Memory Prefetch ===
            memory_context = None
            if conversation_id:
                from app.services.memory_prefetch import prefetch_memory
                try:
                    async with get_db_context() as _db:
                        _row = await _db.execute(text("SELECT user_id FROM conversations WHERE id = :id"), {"id": conversation_id})
                        _conv_owner = _row.scalar()
                    if _conv_owner:
                        memory_context = await asyncio.wait_for(
                            prefetch_memory(query, _conv_owner, conversation_id),
                            timeout=3.0,
                        )
                        if memory_context:
                            yield sse_event('reasoning', {'phase': 'memory', 'text': '找到相關歷史對話記憶，已注入上下文。'})
                except asyncio.TimeoutError:
                    log.debug("Memory prefetch timed out")
                except Exception:
                    pass

            # === S0: Skills System Pipeline (feature flag) ===
            # Flag OFF (default) → fall through to original intent_classifier path below.
            # Flag ON + 5% grayscale (or image present) → run v2 pipeline.
            _use_v2 = False
            if settings.enable_skills_system:
                from app.services.chat_pipeline_v2 import _should_use_v2 as _v2_gate
                # Resolve the real user_id for stable grayscale bucketing.
                # Previous version queried conversations table, but prod has no such table.
                # Decode directly from Authorization: Bearer <jwt> → 'sub' claim instead.
                # Anonymous / no JWT → graceful fallback to None → v2 gate returns False.
                _grayscale_uid: str | None = None
                try:
                    _auth_header = http_request.headers.get("authorization", "")
                    if _auth_header.lower().startswith("bearer "):
                        _token = _auth_header[7:]
                        from app.auth import decode_token
                        _grayscale_uid = decode_token(_token).get("sub")
                except Exception as _e:
                    log.debug(f"Grayscale JWT decode failed: {_e}")
                    _grayscale_uid = None
                # image_base64 present → always use v2 (old path has no multimodal SQL support)
                _use_v2 = bool(request.image_base64) or _v2_gate(_grayscale_uid)

            if _use_v2:
                from app.services.chat_pipeline_v2 import (
                    run_pipeline_v2,
                    _emit_follow_up,
                )
                from app.services.domain_mapper import translate_rows as _translate_rows

                yield sse_event('step', {'id': 'skills', 'label': '技能系統分析...', 'status': 'running'})
                t0 = time.time()

                # Build Qdrant + embedder (best-effort; None → matcher skipped → agent_fallback)
                _qdrant = None
                _embedder = None
                try:
                    from qdrant_client import QdrantClient
                    from app.services.embedding import embed_text as _embed_text
                    _qdrant = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
                    _embedder = _embed_text
                except Exception:
                    pass

                # Extract conversation history for agent
                _v2_history = []
                if request.context:
                    for _m in request.context:
                        if _m.get("intent") == "sql" and _m.get("sql"):
                            _v2_history.append({
                                "q": _m.get("content", ""),
                                "sql": _m["sql"],
                                "row_count": _m.get("row_count", 0),
                                "intent": "sql",
                            })

                async with get_db_context() as _v2_db:
                    v2_result = await run_pipeline_v2(
                        query=query,
                        user_ctx={"id": _grayscale_uid or conversation_id or "anonymous", "role": "viewer"},
                        conversation_history=_v2_history[-3:] if _v2_history else None,
                        image_base64=request.image_base64,
                        request_id=tracer.request_id,
                        conversation_id=conversation_id,
                        qdrant_client=_qdrant,
                        embedder=_embedder,
                        db=_v2_db,
                    )

                skills_ms = int((time.time() - t0) * 1000)
                recovery = v2_result.recovery_path

                yield sse_event('step', {'id': 'skills', 'label': f'技能系統完成（{skills_ms}ms）', 'status': 'done'})

                # --- pre_filter_reject: no LLM, no SQL ---
                if recovery == "pre_filter_reject":
                    _pf_action = v2_result.pre_filter_action  # "chitchat" | "clarify" | "cost_block"
                    if _pf_action == "chitchat":
                        yield sse_event('content', '您好！我是 AI 知識管理平台，可以幫您查詢車輛維修、工單、故障資料。請問有什麼可以協助您？')
                        _pf_terminal = TerminalState.COMPLETED
                    elif _pf_action == "clarify":
                        yield sse_event('clarification', {
                            "message": "請提供更具體的查詢描述",
                            "options": [
                                {"label": "查詢工單狀態", "value": "查詢核簽中的工單"},
                                {"label": "查詢資產資訊", "value": "查詢 EMU800 的維修紀錄"},
                                {"label": "查詢故障報告", "value": "最近一週的故障報告"},
                            ],
                        }, terminal=TerminalState.CLARIFICATION)
                        _pf_terminal = TerminalState.CLARIFICATION
                    elif _pf_action == "cost_block":
                        yield sse_event('error', {
                            'message': '查詢會觸發大量資料掃描，請加上 WHERE 條件或指定欄位',
                            'code': 'cost_block',
                        }, terminal=TerminalState.ERROR)
                        return
                    else:
                        yield sse_event('content', v2_result.error or "請提供更具體的問題描述")
                        _pf_terminal = TerminalState.CLARIFICATION
                    total_ms = int((time.time() - total_start) * 1000)
                    yield sse_event('metadata', {'duration_ms': total_ms, 'request_id': tracer.request_id})
                    _pf_tracer_task = asyncio.create_task(tracer.save())
                    _CHAT_TASKS.add(_pf_tracer_task)
                    _pf_tracer_task.add_done_callback(_CHAT_TASKS.discard)
                    yield sse_event('done', {}, terminal=_pf_terminal)
                    return

                # --- error ---
                if v2_result.error and not v2_result.data and not v2_result.answer:
                    yield sse_event('error', v2_result.error or '查詢失敗', terminal=TerminalState.ERROR)
                    return

                # --- SQL result (skill_direct / agent_fallback / agent_fallback_image) ---
                if v2_result.data or v2_result.sql:
                    explanation = v2_result.explanation or (
                        f"（{recovery}）查詢完成，取得 {v2_result.row_count} 筆結果"
                    )
                    yield sse_event('content', explanation)
                    budgeted_v2 = _translate_rows(v2_result.data[:50])  # Pattern 8 budget
                    sql_event_v2 = {
                        "success": True,
                        "explanation": explanation,
                        "columns": v2_result.columns,
                        "data": budgeted_v2,
                        "row_count": v2_result.row_count,
                        "debug": {
                            "sql": v2_result.sql,
                            "recovery_path": recovery,
                        },
                    }
                    yield sse_event('sql_result', sql_event_v2)

                    follow_ups = _emit_follow_up(v2_result, query)
                    if follow_ups:
                        yield sse_event('follow_up', follow_ups)

                elif v2_result.answer:
                    # Pure RAG-style answer from agent
                    yield sse_event('content', v2_result.answer)
                    try:
                        _rag_fus = rag.generate_follow_up_questions(
                            query=query, answer=v2_result.answer, max_questions=3,
                        )
                        if _rag_fus:
                            yield sse_event('follow_up', _rag_fus)
                    except Exception:
                        pass

                total_ms = int((time.time() - total_start) * 1000)
                yield sse_event('metadata', {
                    'duration_ms': total_ms,
                    'request_id': tracer.request_id,
                    'intent': {'intent': 'skills_v2', 'recovery_path': recovery},
                })
                _v2_tracer_task = asyncio.create_task(tracer.save())
                _CHAT_TASKS.add(_v2_tracer_task)
                _v2_tracer_task.add_done_callback(_CHAT_TASKS.discard)
                yield sse_event('done', {}, terminal=TerminalState.COMPLETED)
                return

            # === Pattern 1: Speculative Execution ===
            # 平行啟動 intent classification + schema pre-build（推測可能是 SQL 查詢）
            # 如果最終不是 SQL，丟棄 schema 結果即可
            yield sse_event('step', {'id': 'intent', 'label': '理解您的問題...', 'status': 'running'})
            t0 = time.time()

            classifier = get_intent_classifier()

            # 同時啟動 intent 分類和 schema 預建
            async def _speculative_schema():
                """Speculatively pre-build schema in parallel with intent classification."""
                try:
                    from app.services.maximo_schema_rag import MaximoSchemaRAG
                    from app.db.session import get_db_context
                    async with get_db_context() as db:
                        rag_svc = MaximoSchemaRAG(db)
                        return await rag_svc.build_schema(query)
                except Exception as e:
                    log.debug("Speculative schema pre-build failed (non-critical): %s", e)
                    return ("", set())

            intent_task = asyncio.create_task(
                classifier.classify_with_fallback(query, context=request.context)
            )
            schema_task = asyncio.create_task(_speculative_schema())

            cls_result = await intent_task

            INTENT_MAP = {
                QueryIntent.STRUCTURED: "sql",
                QueryIntent.KNOWLEDGE: "rag",
                QueryIntent.HYBRID: "hybrid",
                QueryIntent.CLARIFICATION: "clarification",
            }
            intent = INTENT_MAP.get(cls_result.intent, "rag")
            intent_result = {"intent": intent, "confidence": cls_result.confidence, "reason": cls_result.reasoning}
            intent_ms = int((time.time() - t0) * 1000)

            # 如果不是 SQL/hybrid，取消 schema task
            if intent not in ("sql", "hybrid"):
                schema_task.cancel()
                _speculative_schema_result = None
            else:
                try:
                    _speculative_schema_result = await schema_task
                except asyncio.CancelledError:
                    _speculative_schema_result = None

            log.info("Intent detected: %s (confidence=%.2f) for query: %s", intent, cls_result.confidence, query[:80])
            trace_llm_call(tracer, "intent_classification", settings.intent_llm_url, settings.intent_llm_model,
                [{"query": query}], cls_result.reasoning, intent_ms)

            # 規則覆寫：多面向查詢（括號、冒號列舉多主題）必須走 hybrid 分解
            if intent == "sql" and _is_multi_facet_query(query):
                log.info("Override SQL → hybrid for multi-facet query: %s", query[:80])
                intent = "hybrid"
                intent_result["intent"] = "hybrid"
                intent_result["reason"] = f"[覆寫] 多面向查詢改用分解：{intent_result.get('reason','')}"

            yield sse_event('step', {'id': 'intent', 'label': f'理解您的問題（{intent_ms}ms）', 'status': 'done'})

            INTENT_LABEL = {"sql": "結構化資料查詢", "rag": "知識庫搜尋", "hybrid": "多面向查詢", "clarification": "需要釐清"}
            yield sse_event('reasoning', {
                'phase': 'intent',
                'text': f"判斷為「{INTENT_LABEL.get(intent, intent)}」（信心度 {cls_result.confidence:.0%}）。{cls_result.reasoning}",
            })

            sql_result = None

            # Clarification check: LLM-based first, then rule-based fallback for SQL
            if intent == "clarification" and cls_result.clarification_options and not request.skip_clarification:
                yield sse_event('clarification', {
                    "message": cls_result.reasoning,
                    "options": cls_result.clarification_options,
                }, terminal=TerminalState.CLARIFICATION)
                asyncio.create_task(tracer.save())
                asyncio.create_task(rag.log_search_metrics(
                    query=query, search_query=None, sources=[], quality="clarification",
                    duration_ms=intent_ms, intent="clarification", request_id=tracer.request_id,
                    conversation_id=conversation_id,
                ))
                yield sse_event('done', {}, terminal=TerminalState.CLARIFICATION)
                return

            # If skipping clarification or intent was clarification, fallback to keyword-based routing
            if intent == "clarification":
                kw = detect_intent(query, context=request.context)
                intent = kw["intent"]

            if intent == "sql" and not request.skip_clarification:
                # Rule-based ambiguity for SQL-only (hybrid goes to multi-agent which handles disambiguation)
                ambiguity = detect_ambiguity(query, history=request.context)
                if ambiguity:
                    yield sse_event('clarification', ambiguity, terminal=TerminalState.CLARIFICATION)
                    asyncio.create_task(tracer.save())
                    asyncio.create_task(rag.log_search_metrics(
                        query=query, search_query=None, sources=[], quality="clarification",
                        duration_ms=int((time.time() - total_start) * 1000), intent="clarification",
                        request_id=tracer.request_id, conversation_id=conversation_id,
                    ))
                    yield sse_event('done', {}, terminal=TerminalState.CLARIFICATION)
                    return

            # === Multi-Agent Path (for hybrid queries that need parallel sub-tasks) ===
            if intent == "hybrid":
                from app.services.orchestrator import decompose_query, run_parallel_agents, synthesize_results

                yield sse_event('step', {'id': 'decompose', 'label': '分析查詢範圍...', 'status': 'running'})
                t0 = time.time()
                decomposition = await decompose_query(query, context=request.context)
                dec_ms = int((time.time() - t0) * 1000)
                trace_llm_call(tracer, "query_decompose", llm_url, llm_model,
                    [{"query": query}], json.dumps([t.id for t in decomposition.sub_tasks], ensure_ascii=False), dec_ms)

                # If only 1 sub-task, fall through to sequential path
                if len(decomposition.sub_tasks) <= 1:
                    yield sse_event('step', {'id': 'decompose', 'label': f'直接查詢（{dec_ms}ms）', 'status': 'done'})
                    yield sse_event('reasoning', {'phase': 'decompose', 'text': '問題較單純，不需要拆解，直接查詢。'})
                    if decomposition.sub_tasks and decomposition.sub_tasks[0].type == "sql":
                        intent = "sql"
                    else:
                        intent = "rag"
                else:
                    task_labels = "、".join(t.label for t in decomposition.sub_tasks)
                    yield sse_event('step', {'id': 'decompose', 'label': f'分為 {len(decomposition.sub_tasks)} 個面向查詢（{dec_ms}ms）', 'status': 'done'})
                    yield sse_event('reasoning', {'phase': 'decompose', 'text': f'拆解為 {len(decomposition.sub_tasks)} 個子任務同時執行：{task_labels}'})

                    # Show running state for each sub-task
                    for st in decomposition.sub_tasks:
                        yield sse_event('step', {'id': st.id, 'label': f'{st.label}...', 'status': 'running'})

                    # Extract SQL history
                    sql_history = []
                    if request.context:
                        for m in request.context:
                            if m.get("intent") == "sql" and m.get("sql"):
                                sql_history.append({"question": m.get("content", ""), "sql": m["sql"]})

                    # Run sub-agents in parallel, stream results as they complete
                    all_results = []
                    all_sources = []
                    async for result in run_parallel_agents(
                        decomposition.sub_tasks, query, request.top_k,
                        sql_history=sql_history[-3:] if sql_history else None,
                        conversation_context=request.context,
                    ):
                        all_results.append(result)
                        task_id = result["task_id"]
                        dur = result.get("duration_ms", 0)

                        if result.get("error"):
                            if result.get("_suppressed"):
                                yield sse_event('step', {'id': task_id, 'label': f'略過（{dur}ms）', 'status': 'done'})
                            else:
                                yield sse_event('step', {'id': task_id, 'label': f'查詢失敗（{dur}ms）', 'status': 'done'})
                            continue

                        if result["type"] == "sql" and result.get("result", {}).get("success"):
                            sr = result["result"]
                            yield sse_event('step', {'id': task_id, 'label': f'找到 {sr.get("row_count", 0)} 筆資料（{dur}ms）', 'status': 'done'})
                            # Pattern 8: 使用 ResultBudget
                            budgeted_hybrid = budget.allocate(
                                sr.get("data", []),
                                total_count=sr.get("row_count", 0),
                            )
                            hybrid_sql_event = {
                                "success": True,
                                "explanation": _sanitize_explanation(sr.get("explanation")),
                                "columns": sr.get("columns", []),
                                "data": budgeted_hybrid["data"],
                                "row_count": sr.get("row_count", 0),
                                "chart_suggestion": sr.get("chart_suggestion"),
                                "summary": sr.get("summary"),
                                "column_labels": sr.get("column_labels"),
                                "source_label": task_id,
                                "budget": budgeted_hybrid.get("notice"),
                                "debug": {
                                    "sql": sr.get("sql"),
                                    "model": sr.get("model"),
                                    "llm_ms": sr.get("llm_ms"),
                                    "execution_ms": sr.get("execution_ms"),
                                    "confidence": sr.get("confidence"),
                                },
                            }
                            if budgeted_hybrid["truncated"]:
                                from app.services.result_spillover import should_spill, spill_result
                                from app.services.cache import get_redis_client
                                original_data = sr.get("data", [])
                                if should_spill(original_data):
                                    _redis = get_redis_client()
                                    if _redis:
                                        spill_info = spill_result(_redis, original_data, sr.get("columns", []))
                                        hybrid_sql_event["result_id"] = spill_info["result_id"]
                                        hybrid_sql_event["total_rows"] = spill_info["total_rows"]
                                        hybrid_sql_event["spilled"] = True
                            yield sse_event('sql_result', hybrid_sql_event)
                        elif result["type"] == "sql":
                            yield sse_event('step', {'id': task_id, 'label': f'查詢失敗（{dur}ms）', 'status': 'done'})
                        elif result["type"] == "rag" and result.get("sources"):
                            sources_list = result["sources"]
                            all_sources.extend(sources_list)
                            yield sse_event('step', {'id': task_id, 'label': f'找到 {len(sources_list)} 筆文件（{dur}ms）', 'status': 'done'})
                            yield sse_event('sources', [s.model_dump() for s in sources_list])
                        else:
                            yield sse_event('step', {'id': task_id, 'label': f'無相關結果（{dur}ms）', 'status': 'done'})

                    # Synthesize all results
                    yield sse_event('step', {'id': 'synthesize', 'label': '綜合分析結果...', 'status': 'running'})
                    t0 = time.time()
                    full_answer = ""
                    async for chunk in synthesize_results(query, all_results, decomposition.synthesis_instruction):
                        if chunk.get("type") == "content":
                            full_answer += chunk["data"]
                            yield sse_event('content', chunk["data"])
                    syn_ms = int((time.time() - t0) * 1000)
                    trace_llm_call(tracer, "synthesis", llm_url, llm_model,
                        [{"query": query, "sub_results": len(all_results)}], full_answer[:500], syn_ms)
                    yield sse_event('step', {'id': 'synthesize', 'label': f'綜合分析完成（{syn_ms}ms）', 'status': 'done'})

                    # Security #3: Output Scanner — 掃描 final answer
                    try:
                        _scan = get_output_scanner().scan(full_answer)
                        if _scan.action == ScanAction.BLOCK:
                            yield sse_event('content', '\n\n[系統安全機制] ' + _scan.cleaned_text)
                        elif _scan.action == ScanAction.REDACT and _scan.cleaned_text != full_answer:
                            yield sse_event('content', '\n\n[系統已將部分敏感資訊遮蔽]')
                    except Exception as _se:
                        log.debug("output scanner error (ignored): %s", _se)

                    total_ms = int((time.time() - total_start) * 1000)
                    metadata = {'duration_ms': total_ms, 'intent': {"intent": intent}, 'request_id': tracer.request_id}
                    yield sse_event('metadata', metadata)
                    asyncio.create_task(tracer.save())
                    yield sse_event('done', {}, terminal=TerminalState.COMPLETED)

                    try:
                        follow_ups = rag.generate_follow_up_questions(query=query, answer=full_answer, max_questions=3)
                        if follow_ups:
                            yield sse_event('follow_up', follow_ups)
                    except Exception:
                        pass
                    return

            if intent in ("sql",):
                # === NL→SQL Path with granular thinking steps ===
                # Fix A: Tool router first — if a specific Maximo tool matches, use it;
                # otherwise fall through to MaximoNL2SQL.
                yield sse_event('step', {'id': 'schema', 'label': '搜尋相關資料...', 'status': 'running'})
                t0 = time.time()

                from app.db.session import get_db_context

                try:
                    from app.services.maximo_tools.router_factory import build_router
                    from app.services.maximo_tools.base import UserContext
                    from app.services.orchestrator import _adapt_tool_result_to_nl2sql_shape

                    # Extract SQL history for the fallback fn closure
                    sql_history = []
                    if request.context:
                        for m in request.context:
                            if m.get("intent") == "sql" and m.get("sql"):
                                sql_history.append({"question": m.get("content", ""), "sql": m["sql"]})

                    # M1: tool router fallback — 獨立 audit 路徑，不經 recovery flow，recovery_path 由 inner service 自行寫入（預設 None/'direct'）
                    async def _chat_nl2sql_fallback(q: str, user_ctx: UserContext, query_id) -> dict:
                        from app.db.session import get_db_context
                        from app.services.maximo_nl2sql import MaximoNL2SQL
                        async with get_db_context() as _db:
                            _svc = MaximoNL2SQL(_db)
                            _svc._request_id = tracer.request_id
                            _svc._conversation_id = conversation_id
                            _nl2sql = await _svc.query(
                                q, mode="accurate",
                                conversation_history=sql_history[-3:] if sql_history else None,
                                prebuilt_schema=_speculative_schema_result,
                            )
                        rows = _nl2sql.get("data", [])
                        return {
                            "rows": rows,
                            "row_count": _nl2sql.get("row_count", 0),
                            "chart_hint": _nl2sql.get("chart_suggestion"),
                            "debug": {
                                "sql": _nl2sql.get("sql"),
                                "explanation": _nl2sql.get("explanation"),
                                "nl2sql_result": _nl2sql,
                            },
                        }

                    _user_ctx = UserContext(user_id="chat", role="admin")
                    _router = build_router(fallback_fn=_chat_nl2sql_fallback)
                    _router_result = await _router.route(query, _user_ctx)
                    _route_path = _router_result.get("route_path")

                    if _route_path == "tool":
                        sql_result = _adapt_tool_result_to_nl2sql_shape(_router_result)
                    elif _route_path == "fallback":
                        _nl2sql_inner = _router_result.get("debug", {}).get("nl2sql_result")
                        if _nl2sql_inner:
                            sql_result = _nl2sql_inner
                        else:
                            rows = _router_result.get("rows", [])
                            sql_result = {
                                "success": True,
                                "sql": _router_result.get("debug", {}).get("sql"),
                                "explanation": _router_result.get("debug", {}).get("explanation"),
                                "data": rows,
                                "columns": list(rows[0].keys()) if rows else [],
                                "row_count": _router_result.get("row_count", 0),
                                "execution_ms": _router_result.get("elapsed_ms", 0),
                            }
                    else:
                        sql_result = {
                            "success": False,
                            "error": _router_result.get("debug", {}).get("error", {}).get("message", "查詢失敗"),
                            "data": [], "columns": [], "row_count": 0,
                        }

                    schema_ms = int((time.time() - t0) * 1000)
                    sql_ms = schema_ms

                    yield sse_event('step', {'id': 'schema', 'label': f'搜尋相關資料（{schema_ms}ms）', 'status': 'done'})
                    yield sse_event('step', {'id': 'sql_generate', 'label': f'查詢完成（{sql_ms}ms）', 'status': 'done'})

                    exec_ms = sql_result.get("execution_ms")
                    llm_ms = sql_result.get("llm_ms")
                    verify_ms = sql_result.get("verify_ms")
                    timing_parts = [f'總計 {sql_ms}ms']
                    if llm_ms:
                        timing_parts.append(f'LLM {llm_ms}ms')
                    if verify_ms:
                        timing_parts.append(f'驗證 {verify_ms}ms')
                    if exec_ms:
                        timing_parts.append(f'執行 {exec_ms}ms')
                    timing_str = '，'.join(timing_parts)

                    _model_used = sql_result.get("model") or llm_model
                    trace_llm_call(tracer, "sql_generation", llm_url, _model_used,
                        [{"query": query}], sql_result.get("sql") or "", sql_ms,
                        status="ok" if sql_result.get("success") else "error",
                        error=(sql_result.get("error") or "")[:200])

                    if sql_result.get("success"):
                        row_count = len(sql_result.get("data", []))
                        _route_label = f"（工具：{sql_result.get('tool_name', _route_path)}）" if _route_path == "tool" else ""
                        yield sse_event('reasoning', {'phase': 'sql', 'text': f'查詢成功，取得 {row_count} 筆結果（{timing_str}）{_route_label}'})
                        yield sse_event('step', {'id': 'execute', 'label': '整理查詢結果...', 'status': 'done'})
                    else:
                        yield sse_event('reasoning', {'phase': 'sql', 'text': f'查詢失敗：{sql_result.get("error", "未知錯誤")[:80]}'})

                except Exception as sql_err:
                    log.exception("NL→SQL error")
                    sql_result = {"success": False, "error": str(sql_err)}

                if sql_result.get("success"):
                    explanation = sql_result.get("explanation", "查詢完成")
                    yield sse_event('content', _sanitize_explanation(explanation))

                    # Pattern 8: 使用 ResultBudget 控制行數
                    budgeted = budget.allocate(
                        sql_result.get("data", []),
                        total_count=sql_result.get("row_count", 0),
                    )

                    budgeted_data = translate_rows(budgeted["data"])
                    sql_event_data = {
                        "success": True,
                        "explanation": _sanitize_explanation(sql_result.get("explanation")),
                        "columns": sql_result.get("columns", []),
                        "data": budgeted_data,
                        "row_count": sql_result.get("row_count", 0),
                        "chart_suggestion": sql_result.get("chart_suggestion"),
                        "cached": sql_result.get("cached", False),
                        "summary": sql_result.get("summary"),
                        "suggestions": sql_result.get("suggestions", []),
                        "column_labels": sql_result.get("column_labels"),
                        "budget": budgeted.get("notice"),
                        "debug": {
                            "sql": sql_result.get("sql"),
                            "model": sql_result.get("model"),
                            "llm_ms": sql_result.get("llm_ms"),
                            "execution_ms": sql_result.get("execution_ms"),
                            "confidence": sql_result.get("confidence"),
                        },
                    }
                    if budgeted["truncated"]:
                        from app.services.result_spillover import should_spill, spill_result
                        from app.services.cache import get_redis_client
                        original_data = sql_result.get("data", [])
                        if should_spill(original_data):
                            _redis = get_redis_client()
                            if _redis:
                                spill_info = spill_result(_redis, original_data, sql_result.get("columns", []))
                                sql_event_data["result_id"] = spill_info["result_id"]
                                sql_event_data["total_rows"] = spill_info["total_rows"]
                                sql_event_data["spilled"] = True
                    yield sse_event('sql_result', sql_event_data)

                    total_ms = int((time.time() - total_start) * 1000)
                    yield sse_event('metadata', {'duration_ms': total_ms, 'intent': {"intent": intent}, 'request_id': tracer.request_id})

                    follow_ups = _generate_sql_follow_ups(query, sql_result)
                    if follow_ups:
                        yield sse_event('follow_up', follow_ups)

                    # 0-row fallback: pure SQL query returned no data → supplement with RAG
                    if intent == "sql" and sql_result.get("row_count", 0) == 0:
                        yield sse_event('reasoning', {'phase': 'fallback', 'text': 'SQL 查無資料，自動補充知識庫搜尋'})
                        yield sse_event('metadata', {'intent': {'intent': 'hybrid'}, 'fallback_reason': 'sql_zero_rows'})
                        intent = "hybrid"

                    if intent == "sql":
                        asyncio.create_task(tracer.save())
                        yield sse_event('done', {}, terminal=TerminalState.COMPLETED)
                        return

                    yield sse_event('content', '\n\n---\n\n**相關文件參考：**\n\n')

                else:
                    raw_error = sql_result.get("error", "查詢失敗")
                    iters = sql_result.get("iterations", 1)
                    friendly = f"查詢未能成功完成（已嘗試 {iters} 次）。"
                    if intent == "hybrid":
                        # 明確標示「處理中」避免使用者以為訊息結束
                        yield sse_event('content', f'⏳ _{friendly}改用知識庫搜尋中..._\n\n')
                        intent = "rag"
                    else:
                        # === SQL-first recovery: rewrite → retry SQL → clarify → RAG (last resort) ===
                        yield sse_event('step', {'id': 'recovery', 'label': '重新理解您的需求...', 'status': 'running'})
                        yield sse_event('reasoning', {'phase': 'recovery', 'text': f'SQL 查詢失敗（{iters} 次），意圖明確為資料查詢，嘗試改寫問題後重試。'})

                        sql_recovered = False
                        recovery_options = []
                        sql_rewrite_history = []
                        retry_attempted = False  # M2: 區分「有嘗試 retry 但失敗」與「未嘗試 retry（無 options 或 exception）」

                        # Layer 1: Rewrite query → retry SQL
                        try:
                            recovery_options = await _generate_sql_recovery_options(query, raw_error, request.context)
                            if recovery_options:
                                rewritten_query = recovery_options[0]["query"]
                                rewrite_reason = recovery_options[0].get("reason", "")
                                yield sse_event('reasoning', {'phase': 'recovery', 'text': f'改寫查詢：「{rewritten_query[:60]}」，重新嘗試 SQL。'})
                                yield sse_event('step', {'id': 'sql_retry', 'label': f'重試：{rewritten_query[:30]}...', 'status': 'running'})
                                t0 = time.time()

                                try:
                                    retry_attempted = True  # M2: 標記已實際呼叫 retry
                                    from app.services.maximo_nl2sql import MaximoNL2SQL
                                    async with get_db_context() as retry_db:
                                        retry_service = MaximoNL2SQL(retry_db)
                                        retry_service._request_id = tracer.request_id
                                        retry_service._conversation_id = conversation_id
                                        retry_result = await retry_service.query(
                                            rewritten_query, mode="accurate",
                                            conversation_history=sql_history[-3:] if sql_history else None,
                                            prebuilt_schema=_speculative_schema_result,
                                            original_question=query,
                                            skip_audit=True,
                                        )
                                    retry_ms = int((time.time() - t0) * 1000)
                                    yield sse_event('step', {'id': 'sql_retry', 'label': f'重試完成（{retry_ms}ms）', 'status': 'done'})

                                    retry_succeeded = retry_result.get("success", False)
                                    sql_rewrite_history = [{
                                        "attempt": 1,
                                        "query": rewritten_query,
                                        "reason": rewrite_reason,
                                        "success": retry_succeeded,
                                        "ms": retry_ms,
                                    }]
                                    if retry_succeeded:
                                        yield sse_event('reasoning', {'phase': 'recovery', 'text': f'改寫後查詢成功！取得 {len(retry_result.get("data", []))} 筆結果。'})
                                        sql_result = retry_result
                                        sql_recovered = True
                                except Exception as retry_err:
                                    retry_ms = int((time.time() - t0) * 1000)
                                    yield sse_event('step', {'id': 'sql_retry', 'label': f'重試失敗（{retry_ms}ms）', 'status': 'done'})
                                    log.warning("SQL retry with rewritten query failed: %s", retry_err)
                                    sql_rewrite_history = [{
                                        "attempt": 1,
                                        "query": rewritten_query,
                                        "reason": rewrite_reason,
                                        "success": False,
                                        "ms": retry_ms,
                                    }]
                        except Exception as e:
                            log.warning("SQL recovery rewrite failed: %s", e)

                        yield sse_event('step', {'id': 'recovery', 'label': '分析完成', 'status': 'done'})

                        if sql_recovered:
                            # Rewritten SQL succeeded — write audit (outer, single write) then render
                            await _write_rag_fallback_audit(
                                query=query,
                                rewrite_history=sql_rewrite_history,
                                request_id=tracer.request_id,
                                conversation_id=conversation_id,
                                recovery_path="sql_retry",
                            )
                            explanation = sql_result.get("explanation", "查詢完成")
                            yield sse_event('content', _sanitize_explanation(explanation))
                            budgeted = budget.allocate(
                                sql_result.get("data", []),
                                total_count=sql_result.get("row_count", 0),
                            )
                            budgeted_data = translate_rows(budgeted["data"])
                            sql_event_data = {
                                "success": True,
                                "explanation": _sanitize_explanation(sql_result.get("explanation")),
                                "columns": sql_result.get("columns", []),
                                "data": budgeted_data,
                                "row_count": sql_result.get("row_count", 0),
                                "chart_suggestion": sql_result.get("chart_suggestion"),
                                "cached": sql_result.get("cached", False),
                                "summary": sql_result.get("summary"),
                                "suggestions": sql_result.get("suggestions", []),
                                "column_labels": sql_result.get("column_labels"),
                                "budget": budgeted.get("notice"),
                                "debug": {
                                    "sql": sql_result.get("sql"),
                                    "model": sql_result.get("model"),
                                    "llm_ms": sql_result.get("llm_ms"),
                                    "execution_ms": sql_result.get("execution_ms"),
                                    "confidence": sql_result.get("confidence"),
                                },
                            }
                            yield sse_event('sql_result', sql_event_data)
                            total_ms = int((time.time() - total_start) * 1000)
                            yield sse_event('metadata', {'duration_ms': total_ms, 'intent': {"intent": intent}, 'request_id': tracer.request_id})
                            follow_ups = _generate_sql_follow_ups(query, sql_result)
                            if follow_ups:
                                yield sse_event('follow_up', follow_ups)
                            asyncio.create_task(tracer.save())
                            yield sse_event('done', {}, terminal=TerminalState.COMPLETED)
                            return

                        # Layer 2: Clarification options (SQL-focused)
                        if recovery_options and len(recovery_options) > 1:
                            yield sse_event('reasoning', {'phase': 'recovery', 'text': f'改寫重試也失敗，提供 {len(recovery_options)} 個替代建議。'})
                            yield sse_event('content', f'{friendly}\n\n我無法直接查詢，但您可以試試以下方式：\n\n')
                            # M3: audit 必須在 terminal=CLARIFICATION 之前落地，
                            # 避免前端收到 terminal 後立即關閉 SSE，generator 被 cancel 導致 audit 漏寫
                            await _write_rag_fallback_audit(
                                query=query,
                                rewrite_history=sql_rewrite_history,
                                request_id=tracer.request_id,
                                conversation_id=conversation_id,
                                recovery_path="clarification",
                            )
                            asyncio.create_task(tracer.save())
                            yield sse_event('clarification', {
                                "message": f"{friendly} 請選擇更具體的查詢方式：",
                                "options": recovery_options,
                            }, terminal=TerminalState.CLARIFICATION)
                            yield sse_event('done', {}, terminal=TerminalState.CLARIFICATION)
                            return

                        # Layer 3: RAG as last resort — 明確標示處理中
                        yield sse_event('reasoning', {'phase': 'recovery', 'text': 'SQL 改寫和釐清均未成功，改用知識庫搜尋中。'})
                        yield sse_event('content', f'⏳ _{friendly}改用知識庫搜尋相關資料中..._\n\n')

                        # M2: retry_attempted=True → 有執行 retry 但仍失敗才轉 RAG（rag_fallback）
                        #     retry_attempted=False → 無 options 或 exception 未嘗試 retry 就轉 RAG（sql_failed）
                        _retry_failed_path = "rag_fallback" if retry_attempted else "sql_failed"
                        await _write_rag_fallback_audit(
                            query=query,
                            rewrite_history=sql_rewrite_history,
                            request_id=tracer.request_id,
                            conversation_id=conversation_id,
                            recovery_path=_retry_failed_path,
                        )

                        intent = "rag"

            # === RAG Path (intent == "rag" or hybrid fallthrough) ===
            # Compress context with LLM summarization (async, falls back to truncation)
            optimized_context = await compress_context(request.context)

            search_query = query
            if optimized_context:
                conv_parts = []
                for m in optimized_context[-3:]:
                    role = "用戶" if m.get("role") == "user" else "AI"
                    content = m.get("content", "")[:100]
                    conv_parts.append(f"{role}：{content}")
                if conv_parts:
                    search_query = f"對話背景：{'；'.join(conv_parts)}。\n當前問題：{query}"

            # Search with self-reflection: retry with rewritten query if quality is low
            MAX_REWRITE_ATTEMPTS = 2
            MIN_SCORE_THRESHOLD = 0.5
            used_query = search_query
            rewrite_used = False

            yield sse_event('step', {'id': 'search', 'label': '搜尋相關文件...', 'status': 'running'})
            t0 = time.time()
            all_sources = rag.search(
                query=used_query,
                image_base64=request.image_base64,
                top_k=request.top_k,
            )
            # Evaluate quality on unfiltered results to avoid tautological threshold check
            quality = rag.evaluate_retrieval_quality(all_sources)
            sources = [s for s in all_sources if (s.score or 0) >= MIN_SCORE_THRESHOLD]
            best_all_sources = all_sources  # Track best unfiltered results across attempts
            search_ms = int((time.time() - t0) * 1000)
            yield sse_event('step', {'id': 'search', 'label': f'找到 {len(sources)} 筆相關文件（{search_ms}ms）', 'status': 'done'})

            # Self-reflection: if quality is low, rewrite query and retry
            if quality["quality"] in ("low", "none"):
                yield sse_event('reasoning', {'phase': 'reflection', 'text': f'初次搜尋品質 {quality["quality"]}（最高分 {quality["top_score"]:.2f}），嘗試改寫查詢提升檢索效果。'})
                for attempt in range(1, MAX_REWRITE_ATTEMPTS + 1):
                    yield sse_event('step', {'id': f'rewrite_{attempt}', 'label': '優化搜尋條件...', 'status': 'running'})
                    t0 = time.time()
                    rewritten = rag.rewrite_query(query, attempt=attempt)
                    if not rewritten:
                        rw_ms = int((time.time() - t0) * 1000)
                        yield sse_event('step', {'id': f'rewrite_{attempt}', 'label': f'調整搜尋（{rw_ms}ms）', 'status': 'done'})
                        break

                    yield sse_event('reasoning', {'phase': 'rewrite', 'text': f'第 {attempt} 次改寫：「{rewritten[:60]}」'})
                    log.info("Query rewrite attempt %d: '%s' → '%s'", attempt, query[:50], rewritten[:50])
                    new_sources = rag.search(query=rewritten, image_base64=request.image_base64, top_k=request.top_k)
                    new_quality = rag.evaluate_retrieval_quality(new_sources)
                    new_filtered = [s for s in new_sources if (s.score or 0) >= MIN_SCORE_THRESHOLD]
                    rw_ms = int((time.time() - t0) * 1000)

                    # Accept if quality improved (check both score and count)
                    better = (new_quality["quality"] == "good"
                              or (new_quality["top_score"] > quality["top_score"] + 0.05 and len(new_filtered) >= len(sources)))
                    if better:
                        sources = new_filtered
                        best_all_sources = new_sources
                        quality = new_quality
                        used_query = rewritten
                        rewrite_used = True
                        yield sse_event('step', {'id': f'rewrite_{attempt}', 'label': f'調整搜尋（{rw_ms}ms）', 'status': 'done'})
                        if new_quality["quality"] == "good":
                            break
                    else:
                        yield sse_event('step', {'id': f'rewrite_{attempt}', 'label': f'調整搜尋（{rw_ms}ms）', 'status': 'done'})

            if sources:
                yield sse_event('step', {'id': 'rerank', 'label': '分析相關性排序...', 'status': 'running'})
                yield sse_event('step', {'id': 'rerank', 'label': '分析相關性排序...', 'status': 'done'})

            # If still no good results after retries, add a notice and use best available
            if quality["quality"] in ("low", "none") and not sources:
                yield sse_event('content', '⚠️ **知識庫中未找到高度相關的文件。** 以下結果僅供參考，建議嘗試換個關鍵字或更具體的描述。\n\n')
                sources = best_all_sources[:request.top_k] if best_all_sources else []

            # Log RAG search metrics in background
            asyncio.create_task(rag.log_search_metrics(
                query=query,
                search_query=used_query,
                sources=sources,
                quality=quality.get("quality", "unknown"),
                rewrite_used=rewrite_used,
                rewrite_query=used_query if rewrite_used else None,
                duration_ms=int((time.time() - total_start) * 1000),
                intent=intent,
                request_id=tracer.request_id,
                conversation_id=conversation_id,
            ))

            sources_data = [s.model_dump() for s in sources]
            yield sse_event('sources', sources_data)

            yield sse_event('step', {'id': 'generate', 'label': '生成回答...', 'status': 'running'})
            start_time = time.time()
            total_tokens = None
            full_answer = ""

            llm_query = query
            if optimized_context:
                conv_lines = []
                for m in optimized_context:
                    role = "用戶" if m.get("role") == "user" else "AI"
                    conv_lines.append(f"{role}：{m.get('content', '')[:150]}")
                llm_query = "以下是之前的對話：\n" + "\n".join(conv_lines) + f"\n\n請根據以上對話脈絡回答：{query}"

            for result in rag.chat_stream_with_metadata(
                query=llm_query,
                sources=sources,
                image_base64=request.image_base64,
                model=request.model,
                memory_context=memory_context,
            ):
                if result.get("type") == "content":
                    content_chunk = rag.strip_context_fences(result['data'])
                    full_answer += content_chunk
                    yield sse_event('content', content_chunk)
                elif result.get("type") == "usage":
                    total_tokens = result.get("data")

            gen_ms = int((time.time() - start_time) * 1000)
            trace_llm_call(tracer, "rag_answer", llm_url, request.model or llm_model,
                [{"query": llm_query, "sources_count": len(sources)}], full_answer[:500], gen_ms)
            yield sse_event('step', {'id': 'generate', 'label': f'回答完成（{gen_ms}ms）', 'status': 'done'})

            # Security #3: Output Scanner — 掃描 final answer
            try:
                _scan = get_output_scanner().scan(full_answer)
                if _scan.action == ScanAction.BLOCK:
                    yield sse_event('content', '\n\n[系統安全機制] ' + _scan.cleaned_text)
                elif _scan.action == ScanAction.REDACT and _scan.cleaned_text != full_answer:
                    yield sse_event('content', '\n\n[系統已將部分敏感資訊遮蔽]')
            except Exception as _se:
                log.debug("output scanner error (ignored): %s", _se)

            duration_ms = gen_ms
            total_ms = int((time.time() - total_start) * 1000)
            metadata = {
                "duration_ms": total_ms,
                "request_id": tracer.request_id,
            }
            if intent_result:
                metadata["intent"] = {"intent": intent}
            yield sse_event('metadata', metadata)
            asyncio.create_task(tracer.save())
            yield sse_event('done', {}, terminal=TerminalState.COMPLETED)

            try:
                follow_up_questions = rag.generate_follow_up_questions(
                    query=request.query,
                    answer=full_answer,
                    max_questions=3,
                    model=request.model,
                )
                if follow_up_questions:
                    yield sse_event('follow_up', follow_up_questions)
            except Exception:
                pass

        except Exception as e:
            log.exception("chat_stream error")
            yield sse_event('error', str(e), terminal=TerminalState.ERROR)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/models")
async def get_models(provider: Optional[str] = None, ollama_url: Optional[str] = None):
    """
    List available models for a provider.

    Query params let Settings UI preview an Ollama URL before saving it
    (avoids browser CORS to external Ollama hosts).
    - ?provider=anthropic|openai|ollama  (defaults to saved settings.llm_provider)
    - ?ollama_url=<override>             (only for ollama provider)
    """
    settings = get_settings()
    effective = (provider or settings.llm_provider or "ollama").lower()

    # Anthropic provider — return Claude models
    if effective == "anthropic":
        return {
            "models": [
                {"name": "claude-haiku-4-5-20251001", "size": "快速"},
                {"name": "claude-sonnet-4-6", "size": "平衡"},
                {"name": "claude-opus-4-6", "size": "最強"},
            ],
            "current": settings.anthropic_model or "claude-haiku-4-5-20251001",
        }

    # OpenAI provider
    if effective == "openai":
        return {
            "models": [
                {"name": "gpt-4o-mini", "size": "快速"},
                {"name": "gpt-4o", "size": "強"},
                {"name": "gpt-4.1", "size": "最新"},
            ],
            "current": settings.openai_model or "gpt-4o",
        }

    # Ollama provider — fetch live from the host (UI-supplied or saved)
    base_src = ollama_url or settings.ollama_chat_url
    ollama_base = base_src.replace("/v1", "").rstrip("/")
    try:
        req = urllib.request.Request(f"{ollama_base}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            models = [
                {"name": m["name"], "size": m.get("details", {}).get("parameter_size", "")}
                for m in data.get("models", [])
            ]
            return {
                "models": models,
                "current": settings.ollama_chat_model,
                "source": ollama_base,
            }
    except Exception as e:
        log.warning("[models] ollama fetch failed from %s: %s", ollama_base, e)
    return {
        "models": [
            {"name": settings.ollama_chat_model, "size": ""},
            {"name": settings.ollama_light_model, "size": ""},
        ],
        "current": settings.ollama_chat_model,
        "source": ollama_base,
        "error": "ollama host unreachable",
    }


@router.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """
    Search the knowledge base without generating an answer.

    Returns relevant document chunks based on the query.
    """
    results = rag.search(
        query=request.query,
        top_k=request.top_k,
    )

    return SearchResponse(
        results=results,
        total=len(results),
    )


@router.post("/chat/feedback")
async def submit_feedback(feedback: ChatFeedback):
    """Submit user feedback for a RAG response."""
    async with get_db_context() as session:
        await session.execute(
            text("""
                INSERT INTO rag_feedback (message_id, query, rating, comment)
                VALUES (:message_id, :query, :rating, :comment)
            """),
            {
                "message_id": feedback.message_id,
                "query": feedback.query,
                "rating": feedback.rating,
                "comment": feedback.comment,
            },
        )

    result = {"status": "ok"}

    if feedback.rating == "up" and feedback.sql_query:
        from app.services.sql_guard import scan_sql
        is_safe, reason = scan_sql(feedback.sql_query)
        if is_safe:
            async with get_db_context() as session:
                row = await session.execute(
                    text("""
                        INSERT INTO pending_sql_examples (question, sql_query, submitted_by)
                        VALUES (:q, :sql, :by)
                        RETURNING id
                    """),
                    {"q": feedback.query, "sql": feedback.sql_query, "by": feedback.message_id},
                )
                example_id = row.scalar()
            result["promoted"] = True
            result["example_id"] = example_id
        else:
            log.warning("SQL guard rejected feedback SQL: %s", reason)
            result["promoted"] = False
            result["guard_reason"] = reason

    return result


@router.post("/sources/feedback")
async def source_feedback(feedback: SourceFeedback):
    """Submit feedback on a single source chunk. Used to boost helpful chunks in future searches."""
    if feedback.rating not in ("up", "down"):
        return JSONResponse({"error": "Invalid rating"}, status_code=400)
    async with get_db_context() as session:
        await session.execute(
            text("""
                INSERT INTO source_feedback (chunk_id, document_id, question, rating)
                VALUES (:chunk_id, :document_id, :question, :rating)
            """),
            {
                "chunk_id": feedback.chunk_id,
                "document_id": feedback.document_id,
                "question": feedback.question,
                "rating": feedback.rating,
            },
        )
    # Invalidate in-memory boost cache so new votes take effect quickly
    try:
        from app.services import rag as rag_svc
        rag_svc.invalidate_boost_cache()
    except Exception:
        pass
    return {"status": "ok"}


@router.post("/chat/explore")
async def explore_chat(request: ChatRequest):
    """Explore mode — Agent with LLM function calling for multi-step reasoning."""
    from app.services.agent_explorer import run_agent_loop

    async def generate():
        memory_context = None
        if request.conversation_id:
            try:
                from app.services.memory_prefetch import prefetch_memory
                async with get_db_context() as db:
                    row = await db.execute(text("SELECT user_id FROM conversations WHERE id = :id"), {"id": request.conversation_id})
                    owner = row.scalar()
                if owner:
                    memory_context = await asyncio.wait_for(
                        prefetch_memory(request.query, owner, request.conversation_id),
                        timeout=3.0,
                    )
            except Exception:
                pass

        async for event in run_agent_loop(
            query=request.query,
            context=request.context,
            memory_context=memory_context,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'data': {}}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chat/results/{result_id}")
async def get_spilled_result(result_id: str, offset: int = 0, limit: int = 100):
    from app.services.result_spillover import fetch_spilled_result
    from app.services.cache import get_redis_client

    redis = get_redis_client()
    if not redis:
        raise HTTPException(status_code=503, detail="Redis not available")

    result = fetch_spilled_result(redis, result_id, offset, limit)
    if not result:
        raise HTTPException(status_code=404, detail="Result expired or not found")
    return result
