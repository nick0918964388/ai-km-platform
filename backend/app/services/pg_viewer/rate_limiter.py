"""Token-bucket rate limiter for pg_viewer endpoints.

Design
------
* Key format: ``pg_viewer:rate:{bucket_name}:{user_id}:{minute_window}``
  where ``minute_window = int(time.time() // 60)``.
* INCR on the key; if the resulting value is 1 (new key), set TTL 60 s.
* If value > limit → HTTP 429 ``Retry-After: 60``.
* If Redis is unreachable for **any** reason → HTTP 503 ``Retry-After: 30``
  (fail-closed — no request is allowed through without consulting Redis).

Public API
----------
``require_rate_budget(bucket_name, limit_per_min)``
    FastAPI dep factory.  Returns an async dep function that resolves to
    ``None`` on success.  Wire as ``Depends(require_rate_budget(...))``.

Prometheus counter
------------------
``pg_viewer_rate_limiter_redis_down_total`` is incremented whenever Redis is
unreachable.  If ``prometheus_client`` is not installed, a no-op stub is used.

Fail-closed guarantee
---------------------
``_check_rate`` has no code path that returns without either (a) successfully
consulting Redis, or (b) raising HTTP 503.  The only exception is the Redis
operation itself raising — which is caught and re-raised as 503.
"""
from __future__ import annotations

import logging
import time
from typing import Callable

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prometheus counter — stub when library absent
# ---------------------------------------------------------------------------

try:
    from prometheus_client import Counter as _Counter  # type: ignore[import]

    _redis_down_counter = _Counter(
        "pg_viewer_rate_limiter_redis_down_total",
        "Number of times the rate-limiter Redis backend was unreachable",
    )

    def _inc_redis_down() -> None:
        _redis_down_counter.inc()

except ImportError:
    def _inc_redis_down() -> None:  # type: ignore[misc]
        pass


# ---------------------------------------------------------------------------
# Async Redis client singleton
# ---------------------------------------------------------------------------

_redis_client = None


async def _get_async_redis():
    """Return a connected async Redis client.

    Creates the singleton on first call.  Raises ``redis.ConnectionError``
    (or any ``redis.RedisError``) on failure so the caller can fail closed.

    Import of ``redis.asyncio`` is deferred so the module is importable in
    unit-test environments that stub ``redis.asyncio`` in ``sys.modules``.
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    import redis.asyncio as aioredis  # noqa: PLC0415

    from app.config import get_settings  # noqa: PLC0415

    settings = get_settings()
    client = aioredis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
    )
    await client.ping()
    _redis_client = client
    return _redis_client


# ---------------------------------------------------------------------------
# Core rate-check (extracted for unit-test access)
# ---------------------------------------------------------------------------


async def _check_rate(
    bucket_name: str,
    user_id: str,
    limit: int,
) -> None:
    """Enforce the token-bucket for ``user_id`` in ``bucket_name``.

    Fail-closed contract
    ~~~~~~~~~~~~~~~~~~~~
    This function MUST consult Redis for every invocation.  It either:
      * Returns normally (request is within budget), or
      * Raises ``HTTPException(429)`` (over limit), or
      * Raises ``HTTPException(503)`` (Redis unreachable).

    There is NO path that silently allows the request when Redis is down.

    Parameters
    ----------
    bucket_name:
        Logical bucket identifier (e.g. ``"sql"``, ``"rows"``).
    user_id:
        The authenticated user's ID string.
    limit:
        Maximum requests allowed per 60-second window.
    """
    minute_window = int(time.time() // 60)
    key = f"pg_viewer:rate:{bucket_name}:{user_id}:{minute_window}"

    try:
        redis = await _get_async_redis()
        count = await redis.incr(key)
        if count == 1:
            # New key for this window — set TTL so Redis cleans it up.
            await redis.expire(key, 60)
    except Exception as exc:
        _inc_redis_down()
        logger.warning(
            "pg_viewer rate limiter: Redis unavailable (%s). Failing closed.",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="rate limiter backend unavailable",
            headers={"Retry-After": "30"},
        ) from exc

    if count > limit:
        logger.info(
            "pg_viewer rate limit exceeded: bucket=%s user=%s count=%d limit=%d",
            bucket_name,
            user_id,
            count,
            limit,
        )
        raise HTTPException(
            status_code=429,
            detail="rate limit exceeded",
            headers={"Retry-After": "60"},
        )


# ---------------------------------------------------------------------------
# Dep factory
# ---------------------------------------------------------------------------


def require_rate_budget(bucket_name: str, limit_per_min: int) -> Callable:
    """Return a FastAPI dependency that enforces a per-user per-minute rate limit.

    The returned dep injects ``user`` via ``Depends(require_admin_strict)``
    (deferred import — no cycle at module load time).

    Usage (T-020 router wiring)::

        from app.services.pg_viewer.rate_limiter import require_rate_budget
        from app.config import get_settings

        _settings = get_settings()

        @router.post("/sql")
        async def sql_endpoint(
            _rl: None = Depends(
                require_rate_budget("sql", _settings.pg_viewer_rate_limit_sql)
            ),
            user: dict = Depends(require_admin_strict),
        ):
            ...

    The user extracted from ``require_admin_strict`` (key ``"id"``) becomes
    the rate-limit subject.

    Returns ``None`` on success.
    """
    from app.auth import require_admin_strict  # noqa: PLC0415 — deferred to avoid import cycle

    from fastapi import Depends  # noqa: PLC0415

    async def _dep(user: dict = Depends(require_admin_strict)) -> None:
        user_id: str = user.get("id") or "anonymous"
        await _check_rate(bucket_name, user_id, limit_per_min)

    # Give the inner function a unique name so FastAPI's dep cache works
    # correctly when multiple buckets are registered.
    _dep.__name__ = f"rate_budget_{bucket_name}_{limit_per_min}"
    _dep.__qualname__ = f"rate_budget_{bucket_name}_{limit_per_min}"

    return _dep


__all__ = ["require_rate_budget", "_check_rate"]
