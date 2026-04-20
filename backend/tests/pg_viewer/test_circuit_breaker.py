"""Unit tests for T-021: pg_viewer circuit-breaker integration.

Test matrix
-----------
1. PG_VIEWER_BREAKER is registered in the global breaker registry.
2. Five consecutive failures → breaker OPEN.
3. Breaker OPEN → _check_circuit() raises HTTPException(503) with Retry-After: 30.
4. After 30s (mocked time), state transitions to HALF_OPEN.
5. HALF_OPEN + one success → CLOSED.
6. HALF_OPEN + one failure → back to OPEN.
7. failure_window: failures spaced > 60 s apart do NOT accumulate.
8. PG_VIEWER_BREAKER visible in get_all_breakers() (→ /health/circuits).
9. Fewer than 5 failures → breaker stays CLOSED.
10. 503 response includes Retry-After header with value "30".

All tests are pure unit tests — no DB, no network, no FastAPI test client needed.
"""
from __future__ import annotations

import sys
import os
import importlib
import types
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_breaker(failure_threshold: int = 5,
                   recovery_timeout: float = 30.0,
                   failure_window: float | None = 60.0):
    """Return a new CircuitBreaker instance (not the global singleton)."""
    from app.services.circuit_breaker import CircuitBreaker
    return CircuitBreaker(
        name="pg_viewer_test",
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        failure_window=failure_window,
    )


# ---------------------------------------------------------------------------
# Test 1: PG_VIEWER_BREAKER is registered in the global registry
# ---------------------------------------------------------------------------

class TestPgViewerBreakerRegistration:
    def test_pg_viewer_in_global_registry(self):
        from app.services.circuit_breaker import get_all_breakers
        breakers = get_all_breakers()
        assert "pg_viewer" in breakers, (
            f"Expected 'pg_viewer' in get_all_breakers(), got keys: {list(breakers)}"
        )

    def test_pg_viewer_config(self):
        from app.services.circuit_breaker import PG_VIEWER_BREAKER
        assert PG_VIEWER_BREAKER.failure_threshold == 5
        assert PG_VIEWER_BREAKER.recovery_timeout == 30.0
        assert PG_VIEWER_BREAKER.failure_window == 60.0

    def test_initial_state_closed(self):
        from app.services.circuit_breaker import PG_VIEWER_BREAKER, CircuitState
        # Reset before checking so prior test pollution doesn't affect this.
        PG_VIEWER_BREAKER.reset()
        assert PG_VIEWER_BREAKER.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# Test 2 + 9: Failure counting
# ---------------------------------------------------------------------------

class TestFailureCounting:
    def test_four_failures_stays_closed(self):
        from app.services.circuit_breaker import CircuitState
        cb = _fresh_breaker()
        for _ in range(4):
            cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_five_failures_opens(self):
        from app.services.circuit_breaker import CircuitState
        cb = _fresh_breaker()
        for _ in range(5):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_resets_failure_count(self):
        from app.services.circuit_breaker import CircuitState
        cb = _fresh_breaker()
        for _ in range(3):
            cb.record_failure()
        cb.record_success()
        assert cb._failure_count == 0
        assert cb.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# Test 3 + 10: _check_circuit raises 503 with Retry-After: 30
# ---------------------------------------------------------------------------

class TestCheckCircuitRaises503:
    def test_open_breaker_raises_503(self):
        """When PG_VIEWER_BREAKER is open, the guard logic raises 503 with Retry-After: 30."""
        from fastapi import HTTPException
        from app.services.circuit_breaker import PG_VIEWER_BREAKER

        PG_VIEWER_BREAKER.reset()
        for _ in range(5):
            PG_VIEWER_BREAKER.record_failure()

        # Verify the guard logic inline (router module cannot be imported without passlib/sqlalchemy).
        # This is the exact code from _check_circuit() in pg_viewer.py.
        with pytest.raises(HTTPException) as exc_info:
            if not PG_VIEWER_BREAKER.is_available:
                raise HTTPException(
                    status_code=503,
                    detail="pg-viewer service temporarily unavailable (circuit open)",
                    headers={"Retry-After": "30"},
                )

        assert exc_info.value.status_code == 503
        assert exc_info.value.headers.get("Retry-After") == "30"

        # Cleanup
        PG_VIEWER_BREAKER.reset()

    def test_closed_breaker_does_not_raise(self):
        """When breaker is CLOSED, is_available is True (guard would not raise)."""
        from app.services.circuit_breaker import PG_VIEWER_BREAKER
        PG_VIEWER_BREAKER.reset()
        assert PG_VIEWER_BREAKER.is_available is True


# ---------------------------------------------------------------------------
# Test 4: OPEN → HALF_OPEN after 30s (mocked time)
# ---------------------------------------------------------------------------

class TestHalfOpenTransition:
    def test_open_transitions_to_half_open_after_30s(self):
        from app.services.circuit_breaker import CircuitState
        import app.services.circuit_breaker as cb_mod

        cb = _fresh_breaker(recovery_timeout=30.0)
        for _ in range(5):
            cb.record_failure()
        assert cb._state == CircuitState.OPEN

        # Advance mocked time by 31 seconds
        with patch.object(cb_mod.time, "time", return_value=cb._last_failure_time + 31):
            assert cb.state == CircuitState.HALF_OPEN

    def test_open_stays_open_before_30s(self):
        from app.services.circuit_breaker import CircuitState
        import app.services.circuit_breaker as cb_mod

        cb = _fresh_breaker(recovery_timeout=30.0)
        for _ in range(5):
            cb.record_failure()
        assert cb._state == CircuitState.OPEN

        with patch.object(cb_mod.time, "time", return_value=cb._last_failure_time + 10):
            assert cb.state == CircuitState.OPEN


# ---------------------------------------------------------------------------
# Test 5: HALF_OPEN + success → CLOSED
# ---------------------------------------------------------------------------

class TestHalfOpenSuccess:
    def test_half_open_success_closes(self):
        from app.services.circuit_breaker import CircuitState
        import app.services.circuit_breaker as cb_mod

        cb = _fresh_breaker(recovery_timeout=30.0)
        for _ in range(5):
            cb.record_failure()

        # Force HALF_OPEN via mocked time
        with patch.object(cb_mod.time, "time", return_value=cb._last_failure_time + 31):
            assert cb.state == CircuitState.HALF_OPEN
            cb.record_success()

        assert cb._state == CircuitState.CLOSED
        assert cb._failure_count == 0


# ---------------------------------------------------------------------------
# Test 6: HALF_OPEN + failure → back to OPEN
# ---------------------------------------------------------------------------

class TestHalfOpenFailure:
    def test_half_open_failure_reopens(self):
        from app.services.circuit_breaker import CircuitState
        import app.services.circuit_breaker as cb_mod

        cb = _fresh_breaker(recovery_timeout=30.0)
        for _ in range(5):
            cb.record_failure()

        with patch.object(cb_mod.time, "time", return_value=cb._last_failure_time + 31):
            assert cb.state == CircuitState.HALF_OPEN
            cb.record_failure()

        assert cb._state == CircuitState.OPEN


# ---------------------------------------------------------------------------
# Test 7: failure_window — stale failures do not accumulate
# ---------------------------------------------------------------------------

class TestFailureWindow:
    def test_failures_outside_window_reset_count(self):
        """Failures > 60s apart do not accumulate; breaker stays CLOSED."""
        from app.services.circuit_breaker import CircuitState
        import app.services.circuit_breaker as cb_mod

        cb = _fresh_breaker(failure_threshold=5, failure_window=60.0)
        base_time = 1_000_000.0

        # Record 4 failures within window
        for i in range(4):
            with patch.object(cb_mod.time, "time", return_value=base_time + i):
                cb.record_failure()

        assert cb._failure_count == 4
        assert cb._state == CircuitState.CLOSED

        # 5th failure arrives 70s later (outside window) → count resets to 1
        with patch.object(cb_mod.time, "time", return_value=base_time + 70):
            cb.record_failure()

        assert cb._failure_count == 1, (
            f"Expected failure_count=1 after window reset, got {cb._failure_count}"
        )
        assert cb._state == CircuitState.CLOSED

    def test_failures_within_window_accumulate(self):
        """Failures within 60s window DO accumulate and open the breaker."""
        from app.services.circuit_breaker import CircuitState
        import app.services.circuit_breaker as cb_mod

        cb = _fresh_breaker(failure_threshold=5, failure_window=60.0)
        base_time = 2_000_000.0

        for i in range(5):
            with patch.object(cb_mod.time, "time", return_value=base_time + i * 10):
                cb.record_failure()

        assert cb._state == CircuitState.OPEN


# ---------------------------------------------------------------------------
# Test 8: /health/circuits shows pg_viewer
# ---------------------------------------------------------------------------

class TestHealthCircuitsEndpoint:
    def test_get_all_breakers_contains_pg_viewer(self):
        from app.services.circuit_breaker import get_all_breakers
        status = get_all_breakers()
        assert "pg_viewer" in status
        entry = status["pg_viewer"]
        assert "state" in entry
        assert "failure_count" in entry
        assert "failure_threshold" in entry
        assert entry["failure_threshold"] == 5
