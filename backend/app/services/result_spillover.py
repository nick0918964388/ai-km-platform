"""Large result spillover — store full results in Redis, keep preview in context."""
import json
import uuid
import logging
from typing import Optional

log = logging.getLogger(__name__)

SPILLOVER_THRESHOLD_CHARS = 50000
PREVIEW_ROWS = 20
SPILLOVER_TTL = 86400


def should_spill(data: list) -> bool:
    return len(json.dumps(data, ensure_ascii=False)) > SPILLOVER_THRESHOLD_CHARS


def spill_result(redis_client, data: list, columns: list, metadata: dict = None) -> dict:
    result_id = f"spill:{uuid.uuid4().hex[:16]}"
    full_payload = json.dumps({
        "data": data,
        "columns": columns,
        "total": len(data),
        "metadata": metadata or {},
    }, ensure_ascii=False)

    redis_client.set(result_id, full_payload, ex=SPILLOVER_TTL)
    log.info("Spilled %d rows (%d chars) to Redis key %s (TTL %ds)",
             len(data), len(full_payload), result_id, SPILLOVER_TTL)

    preview_data = data[:PREVIEW_ROWS]
    return {
        "result_id": result_id,
        "preview_data": preview_data,
        "preview_rows": len(preview_data),
        "total_rows": len(data),
        "spilled": True,
        "expires_in": SPILLOVER_TTL,
    }


def fetch_spilled_result(redis_client, result_id: str, offset: int = 0, limit: int = 100) -> Optional[dict]:
    raw = redis_client.get(result_id)
    if not raw:
        return None
    payload = json.loads(raw)
    data = payload["data"]
    page = data[offset:offset + limit]
    return {
        "data": page,
        "columns": payload["columns"],
        "total": payload["total"],
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < len(data),
    }
