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
        try:
            query = request.query

            # Intent detection
            intent_result = detect_intent(query, context=request.context)
            intent = intent_result["intent"]
            log.info("Intent detected: %s (confidence=%.2f) for query: %s",
                     intent, intent_result["confidence"], query[:80])

            reason = intent_result["reason"]
            yield f"data: {json.dumps({'type': 'step', 'data': {'id': 'intent', 'label': '意圖偵測：' + reason, 'status': 'done'}}, ensure_ascii=False)}\n\n"

            sql_result = None

            # Check for ambiguity (only for SQL intent)
            if intent in ("sql", "hybrid"):
                ambiguity = detect_ambiguity(query, history=request.context)
                if ambiguity:
                    yield f"data: {json.dumps({'type': 'clarification', 'data': ambiguity}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return

            if intent in ("sql", "hybrid"):
                # === NL→SQL Path with granular thinking steps ===
                yield f"data: {json.dumps({'type': 'step', 'data': {'id': 'schema', 'label': '搜尋相關資料表與欄位...', 'status': 'running'}}, ensure_ascii=False)}\n\n"

                from app.services.maximo_nl2sql import MaximoNL2SQL
                from app.db.session import get_db_context

                try:
                    async with get_db_context() as db:
                        service = MaximoNL2SQL(db)

                        yield f"data: {json.dumps({'type': 'step', 'data': {'id': 'schema', 'label': '搜尋相關資料表與欄位...', 'status': 'done'}}, ensure_ascii=False)}\n\n"
                        yield f"data: {json.dumps({'type': 'step', 'data': {'id': 'sql_generate', 'label': '呼叫 AI 產生 SQL 語句...', 'status': 'running'}}, ensure_ascii=False)}\n\n"

                        # Extract SQL history from conversation context
                        sql_history = []
                        if request.context:
                            for m in request.context:
                                if m.get("intent") == "sql" and m.get("sql"):
                                    sql_history.append({"question": m.get("content", ""), "sql": m["sql"]})

                        sql_result = await service.query(query, mode="fast", conversation_history=sql_history[-3:] if sql_history else None)

                        yield f"data: {json.dumps({'type': 'step', 'data': {'id': 'sql_generate', 'label': '呼叫 AI 產生 SQL 語句...', 'status': 'done'}}, ensure_ascii=False)}\n\n"

                        if sql_result.get("success"):
                            yield f"data: {json.dumps({'type': 'step', 'data': {'id': 'execute', 'label': '執行查詢並整理結果...', 'status': 'done'}}, ensure_ascii=False)}\n\n"
                except Exception as sql_err:
                    log.exception("NL→SQL error")
                    sql_result = {"success": False, "error": str(sql_err)}

                if sql_result.get("success"):
                    # Send brief explanation as content (for message text)
                    explanation = sql_result.get("explanation", "查詢完成")
                    yield f"data: {json.dumps({'type': 'content', 'data': explanation}, ensure_ascii=False)}\n\n"

                    # Send full structured result for rich rendering
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
                    yield f"data: {json.dumps({'type': 'sql_result', 'data': sql_event_data}, ensure_ascii=False)}\n\n"

                    # Metadata
                    yield f"data: {json.dumps({'type': 'metadata', 'data': {'model': sql_result.get('model', 'nl2sql'), 'duration_ms': sql_result.get('llm_ms', 0), 'sql': sql_result.get('sql'), 'intent': intent_result}}, ensure_ascii=False)}\n\n"

                    # SQL follow-up suggestions
                    follow_ups = _generate_sql_follow_ups(query, sql_result)
                    if follow_ups:
                        yield f"data: {json.dumps({'type': 'follow_up', 'data': follow_ups}, ensure_ascii=False)}\n\n"

                    # Related docs search is handled by SqlResultCard's RelatedDocsPanel on the frontend

                    if intent == "sql":
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                        return

                    # hybrid: add separator before RAG section
                    yield f"data: {json.dumps({'type': 'content', 'data': '\\n\\n---\\n\\n**相關文件參考：**\\n\\n'}, ensure_ascii=False)}\n\n"

                else:
                    error_msg = sql_result.get("error", "查詢失敗")
                    if intent == "hybrid":
                        yield f"data: {json.dumps({'type': 'content', 'data': f'*（資料查詢：{error_msg}，改用知識庫搜尋）*\\n\\n'}, ensure_ascii=False)}\n\n"
                        intent = "rag"
                    else:
                        yield f"data: {json.dumps({'type': 'content', 'data': f'查詢失敗：{error_msg}'}, ensure_ascii=False)}\n\n"
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                        return

            # === RAG Path (intent == "rag" or hybrid fallthrough) ===
            # Enhance search query with conversation context
            search_query = query
            if request.context and len(request.context) > 0:
                conv_parts = []
                for m in request.context[-3:]:
                    role = "用戶" if m.get("role") == "user" else "AI"
                    content = m.get("content", "")[:100]
                    conv_parts.append(f"{role}：{content}")
                if conv_parts:
                    search_query = f"對話背景：{'；'.join(conv_parts)}。\n當前問題：{query}"

            # Step 1: search
            yield f"data: {json.dumps({'type': 'step', 'data': {'id': 'search', 'label': '搜尋知識庫文件...', 'status': 'running'}})}\n\n"
            all_sources = rag.search(
                query=search_query,
                image_base64=request.image_base64,
                top_k=request.top_k,
            )
            MIN_SCORE_THRESHOLD = 0.5
            sources = [s for s in all_sources if (s.score or 0) >= MIN_SCORE_THRESHOLD]
            yield f"data: {json.dumps({'type': 'step', 'data': {'id': 'search', 'label': '搜尋知識庫文件...', 'status': 'done'}})}\n\n"

            # Step 2: rerank
            if sources:
                yield f"data: {json.dumps({'type': 'step', 'data': {'id': 'rerank', 'label': '分析相關性排序...', 'status': 'running'}})}\n\n"
                yield f"data: {json.dumps({'type': 'step', 'data': {'id': 'rerank', 'label': '分析相關性排序...', 'status': 'done'}})}\n\n"

            # Send sources
            sources_data = [s.model_dump() for s in sources]
            yield f"data: {json.dumps({'type': 'sources', 'data': sources_data})}\n\n"

            # Step 3: generate
            yield f"data: {json.dumps({'type': 'step', 'data': {'id': 'generate', 'label': '組織回答內容...', 'status': 'running'}})}\n\n"
            start_time = time.time()
            total_tokens = None
            full_answer = ""

            # Build LLM query with conversation context
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
                    yield f"data: {json.dumps({'type': 'content', 'data': content_chunk})}\n\n"
                elif result.get("type") == "usage":
                    total_tokens = result.get("data")

            yield f"data: {json.dumps({'type': 'step', 'data': {'id': 'generate', 'label': '組織回答內容...', 'status': 'done'}})}\n\n"

            duration_ms = int((time.time() - start_time) * 1000)
            metadata = {
                "model": request.model or settings.ollama_chat_model,
                "duration_ms": duration_ms,
                "tokens": total_tokens,
            }
            if intent_result:
                metadata["intent"] = intent_result
            yield f"data: {json.dumps({'type': 'metadata', 'data': metadata})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

            try:
                follow_up_questions = rag.generate_follow_up_questions(
                    query=request.query,
                    answer=full_answer,
                    max_questions=3,
                )
                if follow_up_questions:
                    yield f"data: {json.dumps({'type': 'follow_up', 'data': follow_up_questions})}\n\n"
            except Exception:
                pass

        except Exception as e:
            log.exception("chat_stream error")
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"

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
