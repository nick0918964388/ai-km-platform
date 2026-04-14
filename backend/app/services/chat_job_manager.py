"""Chat job manager — Redis-backed job state and event storage."""
import json
import uuid
import time
import logging
import redis

from app.config import get_settings

log = logging.getLogger(__name__)


def _get_redis():
    settings = get_settings()
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def create_job(query: str) -> str:
    job_id = str(uuid.uuid4())[:8] + "-" + str(int(time.time()))
    r = _get_redis()
    r.hset(f"chat_job:{job_id}", mapping={
        "status": "pending",
        "query": query,
        "created_at": str(time.time()),
    })
    r.expire(f"chat_job:{job_id}", 7200)  # 2 hour TTL
    return job_id


def append_event(job_id: str, event: dict):
    r = _get_redis()
    r.rpush(f"chat_job:{job_id}:events", json.dumps(event, ensure_ascii=False, default=str))
    r.expire(f"chat_job:{job_id}:events", 7200)


def set_status(job_id: str, status: str):
    r = _get_redis()
    r.hset(f"chat_job:{job_id}", "status", status)


def get_status(job_id: str) -> dict | None:
    r = _get_redis()
    data = r.hgetall(f"chat_job:{job_id}")
    if not data:
        return None
    events = r.lrange(f"chat_job:{job_id}:events", 0, -1)
    data["events"] = [json.loads(e) for e in events]
    data["event_count"] = len(events)
    return data


def get_events(job_id: str, after: int = 0) -> list[dict]:
    r = _get_redis()
    events = r.lrange(f"chat_job:{job_id}:events", after, -1)
    return [json.loads(e) for e in events]


def complete_job(job_id: str, result: dict):
    r = _get_redis()
    r.hset(f"chat_job:{job_id}", mapping={
        "status": "done",
        "completed_at": str(time.time()),
    })
    r.set(
        f"chat_job:{job_id}:result",
        json.dumps(result, ensure_ascii=False, default=str),
        ex=7200,
    )


def fail_job(job_id: str, error: str):
    r = _get_redis()
    r.hset(f"chat_job:{job_id}", mapping={
        "status": "error",
        "error": error[:500],
    })
