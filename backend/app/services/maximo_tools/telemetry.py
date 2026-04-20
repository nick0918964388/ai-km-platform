"""
Telemetry DAO for maximo_tool_calls table.

Fire-and-forget write via asyncio.to_thread + 200ms timeout (R3 decision).
Failures are logged + counted but never propagated to the caller.

Usage (FastAPI route):
    background_tasks.add_task(record_tool_call, record, db_pool=app.state.db_pool)

Usage (fire-and-forget task):
    asyncio.create_task(record_tool_call(record, db_pool=pool))
"""

import asyncio
import json
import logging
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fallback reason constants — single source of truth shared with router.py
# ---------------------------------------------------------------------------
FALLBACK_REASON_NO_TOOL = "no_tool_selected"
FALLBACK_REASON_INVOCATION_ERROR = "tool_invocation_error"
FALLBACK_REASON_CIRCUIT_OPEN = "llm_circuit_open"
FALLBACK_REASON_LLM_TIMEOUT = "llm_timeout"
FALLBACK_REASON_TOOL_EXECUTION_ERROR = "tool_execution_error"
FALLBACK_REASON_FEATURE_FLAG_DISABLED = "feature_flag_disabled"

ALL_FALLBACK_REASONS = (
    FALLBACK_REASON_NO_TOOL,
    FALLBACK_REASON_INVOCATION_ERROR,
    FALLBACK_REASON_CIRCUIT_OPEN,
    FALLBACK_REASON_LLM_TIMEOUT,
    FALLBACK_REASON_TOOL_EXECUTION_ERROR,
    FALLBACK_REASON_FEATURE_FLAG_DISABLED,
)

# Simple counters — expose via get_counters() for monitoring / tests.
# Replace with Prometheus inc() calls when metrics integration is added.
_timeout_counter: int = 0
_failed_counter: int = 0

# R3 decision: 200ms write timeout so background writes don't pile up
_WRITE_TIMEOUT_SECONDS: float = 0.2

_INSERT_SQL = """
INSERT INTO maximo_tool_calls
    (query_id, audit_log_id, user_id, tool_name, params, route_path,
     latency_ms, success, row_count, fallback_reason, error_message, created_at)
VALUES
    (%(query_id)s, %(audit_log_id)s, %(user_id)s, %(tool_name)s, %(params)s,
     %(route_path)s, %(latency_ms)s, %(success)s, %(row_count)s,
     %(fallback_reason)s, %(error_message)s, NOW())
"""


class ToolCallRecord(BaseModel):
    """Insertable record matching maximo_tool_calls schema. Immutable."""

    model_config = ConfigDict(frozen=True)

    query_id: UUID = Field(default_factory=uuid4)
    audit_log_id: int | None = None
    user_id: str | None = None
    tool_name: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    route_path: Literal["tool", "fallback", "error"]
    latency_ms: int
    success: bool
    row_count: int | None = None
    fallback_reason: Literal[
        "no_tool_selected",
        "tool_invocation_error",
        "llm_circuit_open",
        "llm_timeout",
        "tool_execution_error",
        "feature_flag_disabled",
    ] | None = None
    error_message: str | None = None


async def record_tool_call(
    record: ToolCallRecord,
    db_pool: Any,
) -> None:
    """
    Fire-and-forget telemetry write.

    - In FastAPI routes: pass to BackgroundTasks.add_task()
    - Elsewhere: asyncio.create_task(record_tool_call(record, db_pool=pool))
    - Never raises — failures are logged + counted only.
    - 200ms timeout: if DB is slow, the write is abandoned.

    Args:
        record:  ToolCallRecord to persist.
        db_pool: psycopg2 pool with getconn()/putconn() interface. Must not be None.
    """
    if db_pool is None:
        raise TypeError(
            "record_tool_call requires a db_pool; got None. "
            "Pass app.state.db_pool from the FastAPI lifespan context."
        )
    global _timeout_counter, _failed_counter
    try:
        async with asyncio.timeout(_WRITE_TIMEOUT_SECONDS):
            await asyncio.to_thread(_sync_insert, record, db_pool)
    except asyncio.TimeoutError:
        _timeout_counter += 1
        logger.warning(
            "telemetry write timeout",
            extra={
                "query_id": str(record.query_id),
                "tool_name": record.tool_name,
                "route_path": record.route_path,
            },
        )
    except Exception:
        _failed_counter += 1
        logger.exception(
            "telemetry write failed",
            extra={
                "query_id": str(record.query_id),
                "tool_name": record.tool_name,
            },
        )


def _sync_insert(record: ToolCallRecord, db_pool: Any) -> None:
    """
    Synchronous psycopg2 INSERT, runs on thread pool via asyncio.to_thread.

    Uses pool.getconn() / pool.putconn() interface.
    """
    params = {
        "query_id": str(record.query_id),
        "audit_log_id": record.audit_log_id,
        "user_id": record.user_id,
        "tool_name": record.tool_name,
        "params": json.dumps(record.params, ensure_ascii=False),
        "route_path": record.route_path,
        "latency_ms": record.latency_ms,
        "success": record.success,
        "row_count": record.row_count,
        "fallback_reason": record.fallback_reason,
        "error_message": record.error_message,
    }

    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(_INSERT_SQL, params)
        conn.commit()
    finally:
        db_pool.putconn(conn)


def get_counters() -> dict[str, int]:
    """Return current telemetry write counters for monitoring / tests."""
    return {"timeout": _timeout_counter, "failed": _failed_counter}


def reset_counters() -> None:
    """Reset counters to zero. For use in tests only."""
    global _timeout_counter, _failed_counter
    _timeout_counter = 0
    _failed_counter = 0
