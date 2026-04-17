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
from app.services.context_manager import build_optimized_context, compress_context
from app.services.call_tracer import CallTracer, trace_llm_call
from app.services.result_budget import ResultBudget
from app.config import get_settings, get_active_llm_info
from app.db.session import get_db_context

log = logging.getLogger(__name__)


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
        from openai import AsyncOpenAI
        client = AsyncOpenAI(base_url=llm_url, api_key=settings.llm_api_key or "sk-unused")

        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=llm_model,
                messages=[{"role": "user", "content": f"/no_think\n{prompt}"}],
                temperature=0.3,
                max_tokens=500,
            ),
            timeout=10.0,
        )
        content = response.choices[0].message.content.strip()

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
async def chat_stream(request: ChatRequest):
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
                yield sse_event('step', {'id': 'schema', 'label': '搜尋相關資料...', 'status': 'running'})
                t0 = time.time()

                from app.services.maximo_nl2sql import MaximoNL2SQL
                from app.db.session import get_db_context

                try:
                    async with get_db_context() as db:
                        service = MaximoNL2SQL(db)
                        service._request_id = tracer.request_id
                        service._conversation_id = conversation_id
                        schema_ms = int((time.time() - t0) * 1000)

                        yield sse_event('step', {'id': 'schema', 'label': f'搜尋相關資料（{schema_ms}ms）', 'status': 'done'})
                        yield sse_event('step', {'id': 'sql_generate', 'label': '分析並查詢資料...', 'status': 'running'})
                        t0 = time.time()

                        # Extract SQL history from conversation context
                        sql_history = []
                        if request.context:
                            for m in request.context:
                                if m.get("intent") == "sql" and m.get("sql"):
                                    sql_history.append({"question": m.get("content", ""), "sql": m["sql"]})

                        sql_result = await service.query(query, mode="accurate",
                            conversation_history=sql_history[-3:] if sql_history else None,
                            prebuilt_schema=_speculative_schema_result)
                        sql_ms = int((time.time() - t0) * 1000)

                        # Detailed timing breakdown
                        llm_ms = sql_result.get("llm_ms")
                        verify_ms = sql_result.get("verify_ms")
                        exec_ms = sql_result.get("execution_ms")
                        iters = sql_result.get("iterations", 1)
                        timing_parts = [f'總計 {sql_ms}ms']
                        if llm_ms:
                            timing_parts.append(f'LLM {llm_ms}ms')
                        if verify_ms:
                            timing_parts.append(f'驗證 {verify_ms}ms')
                        if exec_ms:
                            timing_parts.append(f'執行 {exec_ms}ms')
                        timing_str = '，'.join(timing_parts)

                        trace_llm_call(tracer, "sql_generation", llm_url, sql_result.get("model") or llm_model,
                            [{"query": query}], sql_result.get("sql") or "", sql_ms,
                            status="ok" if sql_result.get("success") else "error",
                            error=(sql_result.get("error") or "")[:200])
                        yield sse_event('step', {'id': 'sql_generate', 'label': f'查詢完成（{sql_ms}ms）', 'status': 'done'})

                        if sql_result.get("success"):
                            row_count = len(sql_result.get("data", []))
                            yield sse_event('reasoning', {'phase': 'sql', 'text': f'查詢成功，取得 {row_count} 筆結果（{timing_str}）'})
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

                    sql_event_data = {
                        "success": True,
                        "explanation": _sanitize_explanation(sql_result.get("explanation")),
                        "columns": sql_result.get("columns", []),
                        "data": budgeted["data"],
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
                        yield sse_event('content', f'*（{friendly}改用知識庫搜尋）*\n\n')
                        intent = "rag"
                    else:
                        # === SQL-first recovery: rewrite → retry SQL → clarify → RAG (last resort) ===
                        yield sse_event('step', {'id': 'recovery', 'label': '重新理解您的需求...', 'status': 'running'})
                        yield sse_event('reasoning', {'phase': 'recovery', 'text': f'SQL 查詢失敗（{iters} 次），意圖明確為資料查詢，嘗試改寫問題後重試。'})

                        sql_recovered = False
                        recovery_options = []

                        # Layer 1: Rewrite query → retry SQL
                        try:
                            recovery_options = await _generate_sql_recovery_options(query, raw_error, request.context)
                            if recovery_options:
                                rewritten_query = recovery_options[0]["query"]
                                yield sse_event('reasoning', {'phase': 'recovery', 'text': f'改寫查詢：「{rewritten_query[:60]}」，重新嘗試 SQL。'})
                                yield sse_event('step', {'id': 'sql_retry', 'label': f'重試：{rewritten_query[:30]}...', 'status': 'running'})
                                t0 = time.time()

                                try:
                                    from app.services.maximo_nl2sql import MaximoNL2SQL
                                    async with get_db_context() as retry_db:
                                        retry_service = MaximoNL2SQL(retry_db)
                                        retry_result = await retry_service.query(
                                            rewritten_query, mode="accurate",
                                            conversation_history=sql_history[-3:] if sql_history else None,
                                            prebuilt_schema=_speculative_schema_result)
                                    retry_ms = int((time.time() - t0) * 1000)
                                    yield sse_event('step', {'id': 'sql_retry', 'label': f'重試完成（{retry_ms}ms）', 'status': 'done'})

                                    if retry_result.get("success"):
                                        yield sse_event('reasoning', {'phase': 'recovery', 'text': f'改寫後查詢成功！取得 {len(retry_result.get("data", []))} 筆結果。'})
                                        sql_result = retry_result
                                        sql_recovered = True
                                except Exception as retry_err:
                                    retry_ms = int((time.time() - t0) * 1000)
                                    yield sse_event('step', {'id': 'sql_retry', 'label': f'重試失敗（{retry_ms}ms）', 'status': 'done'})
                                    log.warning("SQL retry with rewritten query failed: %s", retry_err)
                        except Exception as e:
                            log.warning("SQL recovery rewrite failed: %s", e)

                        yield sse_event('step', {'id': 'recovery', 'label': '分析完成', 'status': 'done'})

                        if sql_recovered:
                            # Rewritten SQL succeeded — render result (reuse success path)
                            explanation = sql_result.get("explanation", "查詢完成")
                            yield sse_event('content', _sanitize_explanation(explanation))
                            budgeted = budget.allocate(
                                sql_result.get("data", []),
                                total_count=sql_result.get("row_count", 0),
                            )
                            sql_event_data = {
                                "success": True,
                                "explanation": _sanitize_explanation(sql_result.get("explanation")),
                                "columns": sql_result.get("columns", []),
                                "data": budgeted["data"],
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
                            yield sse_event('clarification', {
                                "message": f"{friendly} 請選擇更具體的查詢方式：",
                                "options": recovery_options,
                            }, terminal=TerminalState.CLARIFICATION)
                            asyncio.create_task(tracer.save())
                            yield sse_event('done', {}, terminal=TerminalState.CLARIFICATION)
                            return

                        # Layer 3: RAG as last resort
                        yield sse_event('reasoning', {'phase': 'recovery', 'text': 'SQL 改寫和釐清均未成功，最後嘗試知識庫搜尋。'})
                        yield sse_event('content', f'*（{friendly}最後改用知識庫搜尋相關資料）*\n\n')
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
async def get_models():
    settings = get_settings()

    # Anthropic provider — return Claude models
    if settings.llm_provider == "anthropic":
        return {
            "models": [
                {"name": "claude-haiku-4-5-20251001", "size": "快速"},
                {"name": "claude-sonnet-4-6", "size": "平衡"},
                {"name": "claude-opus-4-6", "size": "最強"},
            ],
            "current": settings.anthropic_model or "claude-haiku-4-5-20251001",
        }

    # OpenAI provider
    if settings.llm_provider == "openai":
        return {
            "models": [
                {"name": "gpt-4o-mini", "size": "快速"},
                {"name": "gpt-4o", "size": "強"},
                {"name": "gpt-4.1", "size": "最新"},
            ],
            "current": settings.openai_model or "gpt-4o",
        }

    # Ollama provider — fetch from API
    ollama_base = settings.ollama_chat_url.replace("/v1", "").rstrip("/")
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
            }
    except Exception:
        pass
    return {
        "models": [
            {"name": settings.ollama_chat_model, "size": ""},
            {"name": settings.ollama_light_model, "size": ""},
        ],
        "current": settings.ollama_chat_model,
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
