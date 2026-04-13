"""Chat and search router for RAG queries."""
import json
import time
import logging
import urllib.request
import urllib.error
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    SearchRequest,
    SearchResponse,
)
from app.services import rag
from app.services.intent_classifier import get_intent_classifier, QueryIntent
from app.services.intent_router import detect_intent, detect_ambiguity
from app.config import get_settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


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
        suggestions.append("用圖表顯示這個結果")
        suggestions.append("只看最近一個月的")
    if "工單" in query or "mxwo" in query.lower():
        suggestions.append("這些工單的車輛資訊？")
    if "故障" in query or "mxsr" in query.lower():
        suggestions.append("這些故障通報的處理情形？")
    if "資產" in query or "asset" in query.lower():
        suggestions.append("這些車輛的最近工單？")
    return suggestions[:3]


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

    async def generate():
        def sse_event(event_type, data=None):
            payload = {'type': event_type}
            if data is not None:
                payload['data'] = data
            return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        try:
            query = request.query

            # Intent detection with LLM
            yield sse_event('step', {'id': 'intent', 'label': '分析查詢意圖...', 'status': 'running'})

            classifier = get_intent_classifier()
            cls_result = await classifier.classify_with_fallback(query, context=request.context)

            INTENT_MAP = {
                QueryIntent.STRUCTURED: "sql",
                QueryIntent.KNOWLEDGE: "rag",
                QueryIntent.HYBRID: "hybrid",
                QueryIntent.CLARIFICATION: "clarification",
            }
            intent = INTENT_MAP.get(cls_result.intent, "rag")
            intent_result = {"intent": intent, "confidence": cls_result.confidence, "reason": cls_result.reasoning}

            log.info("Intent detected: %s (confidence=%.2f) for query: %s", intent, cls_result.confidence, query[:80])
            yield sse_event('step', {'id': 'intent', 'label': '意圖偵測：' + cls_result.reasoning, 'status': 'done'})

            sql_result = None

            # Clarification check: LLM-based first, then rule-based fallback for SQL
            if intent == "clarification" and cls_result.clarification_options:
                yield sse_event('clarification', {
                    "message": cls_result.reasoning,
                    "options": cls_result.clarification_options,
                })
                yield sse_event('done', {})
                return

            if intent in ("sql", "hybrid"):
                # Rule-based ambiguity as second layer (domain-specific Maximo disambiguation)
                ambiguity = detect_ambiguity(query, history=request.context)
                if ambiguity:
                    yield sse_event('clarification', ambiguity)
                    yield sse_event('done', {})
                    return

            if intent in ("sql", "hybrid"):
                # === NL→SQL Path with granular thinking steps ===
                yield sse_event('step', {'id': 'schema', 'label': '搜尋相關資料表與欄位...', 'status': 'running'})

                from app.services.maximo_nl2sql import MaximoNL2SQL
                from app.db.session import get_db_context

                try:
                    async with get_db_context() as db:
                        service = MaximoNL2SQL(db)

                        yield sse_event('step', {'id': 'schema', 'label': '搜尋相關資料表與欄位...', 'status': 'done'})
                        yield sse_event('step', {'id': 'sql_generate', 'label': '呼叫 AI 產生 SQL 語句...', 'status': 'running'})

                        # Extract SQL history from conversation context
                        sql_history = []
                        if request.context:
                            for m in request.context:
                                if m.get("intent") == "sql" and m.get("sql"):
                                    sql_history.append({"question": m.get("content", ""), "sql": m["sql"]})

                        sql_result = await service.query(query, mode="accurate", conversation_history=sql_history[-3:] if sql_history else None)

                        yield sse_event('step', {'id': 'sql_generate', 'label': '呼叫 AI 產生 SQL 語句...', 'status': 'done'})

                        iters = sql_result.get("iterations", 1)
                        if iters > 1:
                            yield sse_event('step', {'id': 'validate', 'label': f'驗證並修正查詢（{iters} 次迭代）...', 'status': 'done'})

                        if sql_result.get("success"):
                            yield sse_event('step', {'id': 'execute', 'label': '執行查詢並整理結果...', 'status': 'done'})
                except Exception as sql_err:
                    log.exception("NL→SQL error")
                    sql_result = {"success": False, "error": str(sql_err)}

                if sql_result.get("success"):
                    explanation = sql_result.get("explanation", "查詢完成")
                    yield sse_event('content', explanation)

                    sql_event_data = {
                        "success": True,
                        "sql": sql_result.get("sql"),
                        "explanation": sql_result.get("explanation"),
                        "columns": sql_result.get("columns", []),
                        "data": sql_result.get("data", [])[:50],
                        "row_count": sql_result.get("row_count", 0),
                        "execution_ms": sql_result.get("execution_ms"),
                        "llm_ms": sql_result.get("llm_ms"),
                        "model": sql_result.get("model"),
                        "confidence": sql_result.get("confidence"),
                        "chart_suggestion": sql_result.get("chart_suggestion"),
                        "cached": sql_result.get("cached", False),
                        "summary": sql_result.get("summary"),
                        "suggestions": sql_result.get("suggestions", []),
                        "column_labels": sql_result.get("column_labels"),
                    }
                    yield sse_event('sql_result', sql_event_data)

                    yield sse_event('metadata', {'model': sql_result.get('model', 'nl2sql'), 'duration_ms': sql_result.get('llm_ms', 0), 'sql': sql_result.get('sql'), 'intent': intent_result})

                    follow_ups = _generate_sql_follow_ups(query, sql_result)
                    if follow_ups:
                        yield sse_event('follow_up', follow_ups)

                    if intent == "sql":
                        yield sse_event('done', {})
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
                        short_error = raw_error.split('\n')[0][:150] if raw_error else "未知錯誤"
                        error_content = f"{friendly}\n\n🔧 **錯誤摘要：** `{short_error}`"
                        yield sse_event('content', error_content)
                        if sql_result.get("suggestions"):
                            yield sse_event('sql_result', sql_result)
                        yield sse_event('done', {})
                        return

            # === RAG Path (intent == "rag" or hybrid fallthrough) ===
            search_query = query
            if request.context and len(request.context) > 0:
                conv_parts = []
                for m in request.context[-3:]:
                    role = "用戶" if m.get("role") == "user" else "AI"
                    content = m.get("content", "")[:100]
                    conv_parts.append(f"{role}：{content}")
                if conv_parts:
                    search_query = f"對話背景：{'；'.join(conv_parts)}。\n當前問題：{query}"

            yield sse_event('step', {'id': 'search', 'label': '搜尋知識庫文件...', 'status': 'running'})
            all_sources = rag.search(
                query=search_query,
                image_base64=request.image_base64,
                top_k=request.top_k,
            )
            MIN_SCORE_THRESHOLD = 0.5
            sources = [s for s in all_sources if (s.score or 0) >= MIN_SCORE_THRESHOLD]
            yield sse_event('step', {'id': 'search', 'label': '搜尋知識庫文件...', 'status': 'done'})

            if sources:
                yield sse_event('step', {'id': 'rerank', 'label': '分析相關性排序...', 'status': 'running'})
                yield sse_event('step', {'id': 'rerank', 'label': '分析相關性排序...', 'status': 'done'})

            sources_data = [s.model_dump() for s in sources]
            yield sse_event('sources', sources_data)

            yield sse_event('step', {'id': 'generate', 'label': '組織回答內容...', 'status': 'running'})
            start_time = time.time()
            total_tokens = None
            full_answer = ""

            llm_query = query
            if request.context and len(request.context) > 0:
                conv_lines = []
                for m in request.context[-3:]:
                    role = "用戶" if m.get("role") == "user" else "AI"
                    conv_lines.append(f"{role}：{m.get('content', '')[:150]}")
                llm_query = "以下是之前的對話：\n" + "\n".join(conv_lines) + f"\n\n請根據以上對話脈絡回答：{query}"

            for result in rag.chat_stream_with_metadata(
                query=llm_query,
                sources=sources,
                image_base64=request.image_base64,
            ):
                if result.get("type") == "content":
                    content_chunk = result['data']
                    full_answer += content_chunk
                    yield sse_event('content', content_chunk)
                elif result.get("type") == "usage":
                    total_tokens = result.get("data")

            yield sse_event('step', {'id': 'generate', 'label': '組織回答內容...', 'status': 'done'})

            duration_ms = int((time.time() - start_time) * 1000)
            metadata = {
                "model": request.model or settings.ollama_chat_model,
                "duration_ms": duration_ms,
                "tokens": total_tokens,
            }
            if intent_result:
                metadata["intent"] = intent_result
            yield sse_event('metadata', metadata)
            yield sse_event('done', {})

            try:
                follow_up_questions = rag.generate_follow_up_questions(
                    query=request.query,
                    answer=full_answer,
                    max_questions=3,
                )
                if follow_up_questions:
                    yield sse_event('follow_up', follow_up_questions)
            except Exception:
                pass

        except Exception as e:
            log.exception("chat_stream error")
            yield sse_event('error', str(e))

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
