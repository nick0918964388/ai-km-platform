"""Chat job runner — executes chat queries as background tasks."""
import json
import time
import logging

from app.models.schemas import ChatRequest
from app.services import rag
from app.services import chat_job_manager as jm

log = logging.getLogger(__name__)


async def run_chat_job(job_id: str, request_data: dict):
    """Run a chat query as a background job.

    Mirrors the same flow as chat.py's generate() function,
    but writes events to Redis instead of yielding SSE.
    """
    jm.set_status(job_id, "running")
    start_time = time.time()

    def emit(event_type: str, data=None):
        jm.append_event(job_id, {"type": event_type, "data": data})

    try:
        request = ChatRequest(**request_data)

        # Search for relevant documents
        sources = rag.search(
            query=request.query,
            image_base64=request.image_base64,
            top_k=request.top_k,
        )

        # Emit sources
        sources_data = [s.model_dump() for s in sources]
        emit("sources", sources_data)

        # Stream the answer
        total_tokens = None
        full_answer = ""

        for result in rag.chat_stream_with_metadata(
            query=request.query,
            sources=sources,
            image_base64=request.image_base64,
        ):
            if result.get("type") == "content":
                content_chunk = result["data"]
                full_answer += content_chunk
                emit("content", content_chunk)
            elif result.get("type") == "usage":
                total_tokens = result.get("data")

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Emit metadata
        metadata = {
            "model": "gpt-4o",
            "duration_ms": duration_ms,
            "tokens": total_tokens,
        }
        emit("metadata", metadata)

        # Emit done
        emit("done")

        # Generate follow-up questions
        try:
            follow_up_questions = rag.generate_follow_up_questions(
                query=request.query,
                answer=full_answer,
                max_questions=3,
            )
            if follow_up_questions:
                emit("follow_up", follow_up_questions)
        except Exception:
            pass

        # Complete job
        jm.complete_job(job_id, {
            "answer": full_answer,
            "sources": sources_data,
            "metadata": metadata,
            "duration_ms": duration_ms,
        })

    except Exception as e:
        log.exception(f"Chat job {job_id} failed: {e}")
        emit("error", str(e))
        jm.fail_job(job_id, str(e))
