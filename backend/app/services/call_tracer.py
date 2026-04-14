"""Call Tracer — records LLM and API calls for audit purposes."""
import time
import json
import logging
import asyncio
from dataclasses import dataclass, field, asdict
from typing import Optional
from sqlalchemy import text
from app.db.session import get_db_context

log = logging.getLogger(__name__)


@dataclass
class CallRecord:
    step: str           # e.g., "intent_classification", "sql_generation", "sql_verification", "rag_answer", "query_decompose", "synthesis"
    url: str            # API endpoint URL
    model: str          # Model name
    request_body: str   # Truncated request (first 2000 chars of messages)
    response_body: str  # Truncated response (first 2000 chars)
    duration_ms: int
    status: str = "ok"  # "ok" or "error"
    error: str = ""


class CallTracer:
    """Collects call records during a single request lifecycle."""

    def __init__(self, request_id: str = None):
        self.request_id = request_id or str(int(time.time() * 1000))
        self.records: list[CallRecord] = []

    def add(self, record: CallRecord):
        self.records.append(record)
        log.debug("Trace [%s] %s: %s %dms", self.request_id, record.step, record.model, record.duration_ms)

    def to_list(self) -> list[dict]:
        return [asdict(r) for r in self.records]

    async def save(self):
        """Save all trace records to database."""
        if not self.records:
            return
        try:
            async with get_db_context() as session:
                for r in self.records:
                    await session.execute(
                        text("""
                            INSERT INTO call_traces
                                (request_id, step, url, model, request_body, response_body, duration_ms, status, error)
                            VALUES
                                (:request_id, :step, :url, :model, :request_body, :response_body, :duration_ms, :status, :error)
                        """),
                        {
                            "request_id": self.request_id,
                            "step": r.step,
                            "url": r.url,
                            "model": r.model,
                            "request_body": r.request_body[:3000],
                            "response_body": r.response_body[:3000],
                            "duration_ms": r.duration_ms,
                            "status": r.status,
                            "error": r.error[:500],
                        },
                    )
        except Exception as e:
            log.error("Failed to save call traces: %s", e)


def trace_llm_call(tracer: Optional['CallTracer'], step: str, url: str, model: str, messages: list, response_content: str, duration_ms: int, status: str = "ok", error: str = ""):
    """Helper to record an LLM call in the tracer."""
    if tracer is None:
        return
    # Truncate messages for storage
    req_body = json.dumps(messages, ensure_ascii=False, default=str)[:2000]
    tracer.add(CallRecord(
        step=step,
        url=url,
        model=model,
        request_body=req_body,
        response_body=response_content[:2000],
        duration_ms=duration_ms,
        status=status,
        error=error,
    ))
