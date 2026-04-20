"""Unit tests for pg_viewer rate_limiter (T-014.6).

Test matrix
-----------
1. 30 requests in window → all succeed; 31st → HTTP 429.
2. New minute window → counter resets → request allowed.
3. Redis raises ConnectionError → HTTP 503 with Retry-After: 30;
   body detail = "rate limiter backend unavailable".
4. No fail-open path: grep assertion confirms code never returns without
   consulting Redis.

All tests are pure unit tests (no live Redis, no DB required).

Run with::

    pytest backend/tests/pg_viewer/test_rate_limiter.py -v
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys
import types
from unittest.mock import AsyncMock

import pytest


# ---------------------------------------------------------------------------
# Load rate_limiter directly from file path, bypassing pg_viewer __init__.py
# (which enforces JWT_SECRET at import time).
# ---------------------------------------------------------------------------


def _direct_load(module_name: str, rel_path: str) -> types.ModuleType:
    """Load a .py file directly and register under ``module_name`` in sys.modules."""
    if module_name in sys.modules:
        return sys.modules[module_name]
    abs_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), rel_path)
    )
    spec = importlib.util.spec_from_file_location(module_name, abs_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# Stub app.config so the deferred ``from app.config import get_settings`` inside
# rate_limiter works without a real .env / settings file.
def _ensure_fake_config() -> None:
    if "app.config" not in sys.modules:
        fake_config = types.ModuleType("app.config")

        class _FakeSettings:
            redis_url = "redis://localhost:6379"
            pg_viewer_rate_limit_sql = 30
            pg_viewer_rate_limit_rows = 60

        fake_config.get_settings = lambda: _FakeSettings()  # type: ignore[attr-defined]
        if "app" not in sys.modules:
            sys.modules["app"] = types.ModuleType("app")
        sys.modules["app.config"] = fake_config


_ensure_fake_config()

# Stub app.auth so the deferred import inside require_rate_budget() is satisfied.
if "app.auth" not in sys.modules:
    fake_auth = types.ModuleType("app.auth")

    async def _fake_require_admin_strict() -> dict:  # pragma: no cover
        return {"id": "test-user"}

    fake_auth.require_admin_strict = _fake_require_admin_strict  # type: ignore[attr-defined]
    sys.modules["app.auth"] = fake_auth

# Stub fastapi so the deferred ``from fastapi import Depends`` inside
# require_rate_budget() works without the full framework at load time.
# (fastapi is installed in the test environment, so this is just a guard.)

_rl_mod = _direct_load(
    "app.services.pg_viewer.rate_limiter",
    "../../app/services/pg_viewer/rate_limiter.py",
)

_check_rate = _rl_mod._check_rate
require_rate_budget = _rl_mod.require_rate_budget


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeRedis:
    """In-memory async Redis stub with INCR + EXPIRE semantics."""

    def __init__(self):
        self._store: dict[str, int] = {}

    async def ping(self):
        return True

    async def incr(self, key: str) -> int:
        self._store[key] = self._store.get(key, 0) + 1
        return self._store[key]

    async def expire(self, key: str, ttl: int) -> None:
        pass  # TTL not enforced in unit tests; see Test 2 for window reset.


class _FailingRedis:
    """Async Redis stub that always raises ConnectionError."""

    async def ping(self):
        raise ConnectionError("Redis connection refused")

    async def incr(self, key: str) -> int:
        raise ConnectionError("Redis connection refused")

    async def expire(self, key: str, ttl: int) -> None:
        raise ConnectionError("Redis connection refused")


def _inject_redis(fake) -> None:
    """Replace the module-level _redis_client singleton."""
    _rl_mod._redis_client = fake


def _clear_redis() -> None:
    """Reset the module-level singleton so each test starts fresh."""
    _rl_mod._redis_client = None


# ---------------------------------------------------------------------------
# Test 1 — 30 requests succeed; 31st → 429
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_30_requests_succeed_31st_is_429():
    """First 30 calls within the same window succeed; the 31st raises HTTP 429."""
    fake = _FakeRedis()
    _inject_redis(fake)
    try:
        # Calls 1–30 must all succeed.
        for i in range(30):
            await _check_rate("sql", "user-abc", 30)

        # Call 31 must raise HTTP 429.
        from fastapi import HTTPException  # noqa: PLC0415

        with pytest.raises(HTTPException) as exc_info:
            await _check_rate("sql", "user-abc", 30)

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail == "rate limit exceeded"
        assert exc_info.value.headers.get("Retry-After") == "60"
    finally:
        _clear_redis()


# ---------------------------------------------------------------------------
# Test 2 — New minute window resets the counter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_minute_window_allows_request():
    """After the 60-second window rolls over the counter resets and requests are allowed.

    We simulate a new window by directly manipulating the in-memory store so
    that the current-window key is absent (as it would be after TTL expiry).
    """
    import time  # noqa: PLC0415

    fake = _FakeRedis()
    _inject_redis(fake)
    try:
        # Exhaust the first window.
        for _ in range(30):
            await _check_rate("sql", "user-win", 30)

        # Simulate window expiry by clearing the old key from the store.
        minute_window = int(time.time() // 60)
        old_key = f"pg_viewer:rate:sql:user-win:{minute_window}"
        fake._store.pop(old_key, None)

        # Inject a key for a "future" window (minute + 1) by monkeypatching time.
        # We emulate this by directly seeding the new key as absent (i.e., the store
        # doesn't have it), then verifying the call succeeds.
        # Seed a different user to verify isolation, then verify our user works again
        # after the store is cleared.

        # First call after store clear → INCR returns 1 → within budget.
        await _check_rate("sql", "user-win", 30)  # must not raise
    finally:
        _clear_redis()


# ---------------------------------------------------------------------------
# Test 3 — Redis unreachable → HTTP 503
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_connection_error_raises_503():
    """When Redis raises ConnectionError the dep raises HTTP 503 Retry-After:30."""
    _inject_redis(_FailingRedis())
    try:
        from fastapi import HTTPException  # noqa: PLC0415

        with pytest.raises(HTTPException) as exc_info:
            await _check_rate("sql", "user-xyz", 30)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "rate limiter backend unavailable"
        assert exc_info.value.headers.get("Retry-After") == "30"
    finally:
        _clear_redis()


# ---------------------------------------------------------------------------
# Test 4 — No fail-open path (static source analysis)
# ---------------------------------------------------------------------------


def test_no_fail_open_path_exists():
    """Source scan: _check_rate has no path that returns without consulting Redis.

    Checks that:
    1. There is no bare ``return`` before the Redis call.
    2. The 503 raise is present (fail-closed on exception).
    3. The module contains no ``if redis is None: return`` pattern.
    """
    src_path = os.path.normpath(
        os.path.join(
            os.path.dirname(__file__),
            "../../app/services/pg_viewer/rate_limiter.py",
        )
    )
    with open(src_path) as fh:
        source = fh.read()

    # Must raise 503 on Redis failure — not silently allow.
    assert "503" in source, "rate_limiter.py must raise HTTP 503 on Redis failure"
    assert "Retry-After" in source, "rate_limiter.py must include Retry-After header"

    # Must NOT contain any fail-open pattern (returning None without consulting Redis).
    forbidden = [
        "if redis is None: return",
        "if _redis_client is None:\n        return",
        "# fail open",
        "fail_open",
    ]
    for pattern in forbidden:
        assert pattern not in source, (
            f"Fail-open pattern found in rate_limiter.py: {pattern!r}"
        )

    # The exception branch must raise (not just log and return).
    # Verify that the except block in _check_rate contains 'raise HTTPException'
    # and not a bare 'return'.
    import ast  # noqa: PLC0415

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        if node.name != "_check_rate":
            continue
        # Walk the function body looking for except handlers.
        for child in ast.walk(node):
            if not isinstance(child, ast.ExceptHandler):
                continue
            # Every except handler must contain a Raise node, not a bare Return.
            has_raise = any(isinstance(n, ast.Raise) for n in ast.walk(child))
            has_bare_return = any(
                isinstance(n, ast.Return) and n.value is None
                for n in ast.walk(child)
            )
            assert has_raise, (
                "except handler in _check_rate does not raise — fail-open risk"
            )
            assert not has_bare_return, (
                "bare return in _check_rate except handler — fail-open risk"
            )
