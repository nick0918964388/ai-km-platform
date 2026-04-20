"""Unit tests for pg_viewer startup JWT guard.

Strategy: we call _assert_jwt_secret_safe() directly (it's public enough to
test) after patching app.config.get_settings and the JWT_SECRET env var.
We also verify the module-level execution via importlib.reload so that
"runs at import time" is covered by at least one case.

T-002 adds PG_VIEWER_ENABLED to app.config.Settings. Until that lands, we
stub get_settings() via monkeypatch so the tests pass independently.
"""
import importlib
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings(pg_viewer_enabled: bool) -> MagicMock:
    """Return a minimal Settings-like mock with pg_viewer_enabled set."""
    s = MagicMock()
    s.pg_viewer_enabled = pg_viewer_enabled
    return s


def _ensure_app_config_in_sys_modules():
    """Make sure app.config is importable (real or stub).

    conftest.py adds backend/ to sys.path, so 'app' should be importable.
    If for some reason it is not (e.g. missing heavy deps), fall back to a stub.
    """
    if "app.config" in sys.modules:
        return
    try:
        import app.config  # noqa: F401
    except Exception:
        # Build a minimal stub: app (package) + app.config (module)
        if "app" not in sys.modules:
            app_pkg = types.ModuleType("app")
            app_pkg.__path__ = []  # mark as package
            app_pkg.__package__ = "app"
            sys.modules["app"] = app_pkg

        fake_config = types.ModuleType("app.config")
        fake_config.get_settings = lambda: _make_settings(False)  # type: ignore[attr-defined]
        sys.modules["app.config"] = fake_config
        sys.modules["app"].config = fake_config  # type: ignore[attr-defined]


def _call_guard(monkeypatch, pg_viewer_enabled: bool, jwt_secret: str):
    """Set up env + settings stub, then call _assert_jwt_secret_safe directly.

    This is faster and more reliable than importlib.reload because it avoids
    cascading import failures from heavy dependencies (sqlalchemy, etc.).
    """
    _ensure_app_config_in_sys_modules()

    mock_settings = _make_settings(pg_viewer_enabled)
    monkeypatch.setattr("app.config.get_settings", lambda: mock_settings)

    if jwt_secret:
        monkeypatch.setenv("JWT_SECRET", jwt_secret)
    else:
        monkeypatch.delenv("JWT_SECRET", raising=False)

    # Import the guard module (first time may run; subsequent calls use cache)
    # Ensure a clean slate for the module so the import-time side effect is tested
    # via the direct call path below.
    import app.services.pg_viewer as pg_viewer_module  # noqa: PLC0415
    # Re-invoke the guard with current patches (direct call is the unit under test)
    pg_viewer_module._assert_jwt_secret_safe()


def _reload_guard(monkeypatch, pg_viewer_enabled: bool, jwt_secret: str):
    """Full reload path — only used for Case 1 to prove import-time execution."""
    _ensure_app_config_in_sys_modules()

    mock_settings = _make_settings(pg_viewer_enabled)
    monkeypatch.setattr("app.config.get_settings", lambda: mock_settings)

    if jwt_secret:
        monkeypatch.setenv("JWT_SECRET", jwt_secret)
    else:
        monkeypatch.delenv("JWT_SECRET", raising=False)

    # Remove cached module so reload triggers the guard at module level
    for key in list(sys.modules.keys()):
        if key == "app.services.pg_viewer":
            del sys.modules[key]

    import app.services.pg_viewer as pg_viewer_module  # noqa: PLC0415
    return pg_viewer_module


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestStartupGuard:
    """Four acceptance cases from task T-002.5."""

    def test_case1_enabled_empty_secret_raises(self, monkeypatch):
        """Case 1: PG_VIEWER_ENABLED=True + JWT_SECRET="" → RuntimeError.

        Also exercises the import-time path via reload.
        """
        with pytest.raises(RuntimeError, match="pg_viewer refuses to start"):
            _reload_guard(monkeypatch, pg_viewer_enabled=True, jwt_secret="")

    def test_case2_enabled_insecure_secret_raises(self, monkeypatch):
        """Case 2: PG_VIEWER_ENABLED=True + JWT_SECRET=insecure default → RuntimeError."""
        with pytest.raises(RuntimeError, match="pg_viewer refuses to start"):
            _call_guard(monkeypatch, pg_viewer_enabled=True,
                        jwt_secret="aikm-secret-key-change-in-production")

    def test_case3_enabled_real_secret_no_raise(self, monkeypatch):
        """Case 3: PG_VIEWER_ENABLED=True + real 64-char hex secret → no raise."""
        real_secret = "a" * 64
        _call_guard(monkeypatch, pg_viewer_enabled=True, jwt_secret=real_secret)

    def test_case4_disabled_empty_secret_no_raise(self, monkeypatch):
        """Case 4: PG_VIEWER_ENABLED=False + JWT_SECRET="" → no raise (feature off)."""
        _call_guard(monkeypatch, pg_viewer_enabled=False, jwt_secret="")
