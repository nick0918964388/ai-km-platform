"""
Rate Limiting + 告警 (Security #5)

策略：
- Per-user/IP 每分鐘 N 次 request（預設 30）→ 429
- 10 分鐘內被 guardrail 擋 >= 3 次 → 寫 SECURITY_ALERT log（未來接 Slack/Email）

實作：Redis-backed counters，key TTL = window + 緩衝。
Cache 斷線 fail-open（不 block 正常流量）。
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import HTTPException, status

from app.services import cache as cache_service

logger = logging.getLogger(__name__)

# 預設 limits
RATE_LIMIT_PER_MIN = 30
ABUSE_WINDOW_MIN = 10          # 觀察窗 10 分鐘
ABUSE_THRESHOLD = 3             # 10 分鐘內 3 次 guardrail block → alert


def _current_minute_bucket() -> str:
    return datetime.utcnow().strftime("%Y%m%d%H%M")


def _current_10min_bucket() -> str:
    # 把分鐘十位數當桶（例：14:23 → 1420；14:28 → 1420；14:30 → 1430）
    now = datetime.utcnow().strftime("%Y%m%d%H%M")
    return now[:-1] + "0"


def _redis_incr(key: str, ttl_seconds: int) -> int | None:
    """Redis INCR + EXPIRE。失敗回傳 None（fail-open）。"""
    client = cache_service.get_redis_client()
    if client is None:
        return None
    try:
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl_seconds)
        results = pipe.execute()
        return int(results[0])
    except Exception as e:
        logger.warning("[rate_limit] redis incr failed: %s", e)
        return None


def check_rate_limit(
    user_id: str,
    endpoint: str = "chat",
    limit_per_min: int = RATE_LIMIT_PER_MIN,
) -> None:
    """
    在 handler 最前面呼叫。超限 raise HTTPException 429。
    Cache 不可用時 fail-open（僅警告）。
    """
    if not user_id:
        user_id = "anonymous"

    key = f"ratelimit:{endpoint}:{user_id}:{_current_minute_bucket()}"
    count = _redis_incr(key, ttl_seconds=70)

    if count is None:
        # Redis 不可用：fail-open，但 log 一次
        logger.debug("[rate_limit] cache unavailable, fail-open for user=%s", user_id)
        return

    if count > limit_per_min:
        logger.warning(
            "[rate_limit] EXCEEDED: endpoint=%s user=%s count=%s limit=%s",
            endpoint, user_id, count, limit_per_min,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"請求過於頻繁，每分鐘最多 {limit_per_min} 次，請稍後再試。",
        )


def record_guardrail_block(user_id: str) -> int:
    """
    使用者被 guardrail 擋時呼叫。
    回傳 10 分鐘內累積次數；> threshold 時觸發 alert log。
    """
    if not user_id:
        user_id = "anonymous"

    window_key = f"guardrail_blocks:{user_id}:{_current_10min_bucket()}"
    count = _redis_incr(window_key, ttl_seconds=ABUSE_WINDOW_MIN * 60 + 30)

    if count is None:
        return 0

    if count >= ABUSE_THRESHOLD:
        # 觸發告警 — 目前僅 log，未來可串 webhook / email / Slack
        logger.error(
            "[SECURITY_ALERT] user=%s had %s guardrail blocks in %s min — possible abuse",
            user_id, count, ABUSE_WINDOW_MIN,
        )

    return count
