"""Chat and search router for RAG queries."""
import json
import time
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    SearchRequest,
    SearchResponse,
)
from app.services import rag

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
    async def generate():
        try:
            # First, search for relevant documents and send sources
            all_sources = rag.search(
                query=request.query,
                image_base64=request.image_base64,
                top_k=request.top_k,
            )

            # Filter sources with score >= 0.5 for relevance
            MIN_SCORE_THRESHOLD = 0.5
            relevant_sources = [s for s in all_sources if (s.score or 0) >= MIN_SCORE_THRESHOLD]
            
            # Only use relevant sources - don't fall back to low-score sources
            sources = relevant_sources

            # Send sources first (only if there are relevant ones)
            sources_data = [s.model_dump() for s in sources]
            yield f"data: {json.dumps({'type': 'sources', 'data': sources_data})}\n\n"

            # Track timing and tokens
            start_time = time.time()
            total_tokens = None
            full_answer = ""

            # Then stream the answer (using only relevant sources for context)
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

            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)

            # Send metadata
            metadata = {
                "model": "gpt-4o",
                "duration_ms": duration_ms,
                "tokens": total_tokens,
            }
            yield f"data: {json.dumps({'type': 'metadata', 'data': metadata})}\n\n"

            # Signal completion first (so sources show immediately)
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

            # Generate and send follow-up questions (after done, so it doesn't block UI)
            try:
                follow_up_questions = rag.generate_follow_up_questions(
                    query=request.query,
                    answer=full_answer,
                    max_questions=3,
                )
                if follow_up_questions:
                    yield f"data: {json.dumps({'type': 'follow_up', 'data': follow_up_questions})}\n\n"
            except Exception as e:
                # Don't fail the whole request if follow-up generation fails
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
