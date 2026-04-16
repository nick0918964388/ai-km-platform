"""Chat job runner — executes chat queries as background tasks.

Consumes the same generate() async generator from chat.py,
writing events to Redis instead of SSE streaming.
"""
import json
import re
import time
import logging

from app.models.schemas import ChatRequest, TerminalState
from app.services import chat_job_manager as jm

log = logging.getLogger(__name__)

THINK_TAG_RE = re.compile(r'<think>[\s\S]*?</think>')


def _strip_think(text: str) -> str:
    """Remove <think>...</think> tags from LLM output."""
    return THINK_TAG_RE.sub('', text).strip()


async def run_chat_job(job_id: str, request_data: dict):
    """Run a chat query as a background job using the full Agentic RAG pipeline.

    Imports and calls the same generate() logic from chat.py,
    consuming events and writing them to Redis.
    """
    jm.set_status(job_id, "running")
    start_time = time.time()

    try:
        # Import here to avoid circular imports
        from app.routers.chat import chat_stream
        from app.config import get_settings

        request = ChatRequest(**request_data)
        settings = get_settings()

        # Call chat_stream to get the StreamingResponse, then consume its body_iterator
        response = await chat_stream(request)

        full_answer = ""
        async for chunk_bytes in response.body_iterator:
            chunk = chunk_bytes if isinstance(chunk_bytes, str) else chunk_bytes.decode()
            # Parse SSE lines
            for line in chunk.strip().split('\n'):
                if not line.startswith('data: '):
                    continue
                try:
                    event = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type")
                event_data = event.get("data")

                # Strip think tags from content
                if event_type == "content" and isinstance(event_data, str):
                    cleaned = _strip_think(event_data)
                    if cleaned:
                        event["data"] = cleaned
                        full_answer += cleaned
                    else:
                        continue  # Skip empty content after stripping

                # Write event to Redis
                jm.append_event(job_id, event)

                # Detect terminal state from SSE event
                terminal = event.get("terminal")
                if event_type == "done" or terminal in (TerminalState.ERROR.value, TerminalState.CLARIFICATION.value):
                    break

        duration_ms = int((time.time() - start_time) * 1000)
        terminal = "completed"
        # Check last event's terminal state
        if event and event.get("terminal") == TerminalState.ERROR.value:
            jm.fail_job(job_id, full_answer or "pipeline error")
        else:
            jm.complete_job(job_id, {
                "answer": full_answer,
                "duration_ms": duration_ms,
                "terminal": event.get("terminal", TerminalState.COMPLETED.value),
            })

    except Exception as e:
        log.exception(f"Chat job {job_id} failed: {e}")
        jm.append_event(job_id, {"type": "error", "data": str(e), "terminal": TerminalState.ERROR.value})
        jm.fail_job(job_id, str(e))
