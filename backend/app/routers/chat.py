"""Chat and search router for RAG queries."""
import json
import time
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
from app.config import get_settings

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
            # Step 1: search
            yield f"data: {json.dumps({'type': 'step', 'data': {'id': 'search', 'label': '查詢知識庫', 'status': 'running'}})}\n\n"
            all_sources = rag.search(
                query=request.query,
                image_base64=request.image_base64,
                top_k=request.top_k,
            )
            MIN_SCORE_THRESHOLD = 0.5
            sources = [s for s in all_sources if (s.score or 0) >= MIN_SCORE_THRESHOLD]
            yield f"data: {json.dumps({'type': 'step', 'data': {'id': 'search', 'label': '查詢知識庫', 'status': 'done'}})}\n\n"

            # Step 2: rerank (already done inside search, just report)
            if sources:
                yield f"data: {json.dumps({'type': 'step', 'data': {'id': 'rerank', 'label': '重排序結果', 'status': 'running'}})}\n\n"
                yield f"data: {json.dumps({'type': 'step', 'data': {'id': 'rerank', 'label': '重排序結果', 'status': 'done'}})}\n\n"

            # Send sources
            sources_data = [s.model_dump() for s in sources]
            yield f"data: {json.dumps({'type': 'sources', 'data': sources_data})}\n\n"

            # Step 3: generate
            yield f"data: {json.dumps({'type': 'step', 'data': {'id': 'generate', 'label': '生成回答', 'status': 'running'}})}\n\n"
            start_time = time.time()
            total_tokens = None
            full_answer = ""

            for result in rag.chat_stream_with_metadata(
                query=request.query,
                sources=sources,
                image_base64=request.image_base64,
            ):
                if result.get("type") == "content":
                    content_chunk = result['data']
                    full_answer += content_chunk
                    yield f"data: {json.dumps({'type': 'content', 'data': content_chunk})}\n\n"
                elif result.get("type") == "usage":
                    total_tokens = result.get("data")

            yield f"data: {json.dumps({'type': 'step', 'data': {'id': 'generate', 'label': '生成回答', 'status': 'done'}})}\n\n"

            duration_ms = int((time.time() - start_time) * 1000)
            metadata = {
                "model": request.model or settings.ollama_chat_model,
                "duration_ms": duration_ms,
                "tokens": total_tokens,
            }
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
