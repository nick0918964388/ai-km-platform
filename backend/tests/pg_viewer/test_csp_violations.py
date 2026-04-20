"""Tests for CSP violation reporter endpoint (T-046).

Test matrix
-----------
1. Legacy format POST → 204; 1 row stored with populated fields.
2. Modern array format POST → 204; N rows stored (one per report object).
3. GET same URL → 405 Method Not Allowed.
4. Oversize body (>16 KB) → 413.
5. Malformed JSON → 400, no stack trace in response body.
6. IP captured (trust XFF from allowlist; else use request.client.host).
7. No JWT / auth cookie column in the stored row (schema assertion).

Tests 1 and 2 are integration tests requiring a live DB (DATABASE_URL env).
Tests 3-7 are pure unit tests; they always run.

Run unit-only::
    pytest backend/tests/pg_viewer/test_csp_violations.py -v -m "not integration"

Run all (requires live DB)::
    pytest backend/tests/pg_viewer/test_csp_violations.py -v
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — ensure 'app' is importable from tests
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# ---------------------------------------------------------------------------
# Skip markers
# ---------------------------------------------------------------------------
INTEGRATION_SKIP = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set — live-DB tests skipped",
)
integration = pytest.mark.integration


# ---------------------------------------------------------------------------
# Direct-load helper (avoids package __init__ JWT guard)
# ---------------------------------------------------------------------------

def _direct_load(module_name: str, rel_path: str) -> types.ModuleType:
    """Load a .py file directly by absolute path."""
    if module_name in sys.modules:
        return sys.modules[module_name]
    abs_path = os.path.join(_BACKEND_DIR, rel_path)
    spec = importlib.util.spec_from_file_location(module_name, abs_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_router() -> types.ModuleType:
    return _direct_load(
        "app.routers.csp_violations",
        "app/routers/csp_violations.py",
    )


# ---------------------------------------------------------------------------
# Minimal FastAPI test client setup (no DB required for unit tests)
# ---------------------------------------------------------------------------

def _make_test_client(*, rate_limit_pass: bool = True):
    """Build a TestClient with the csp_violations router mounted at /api.

    ``rate_limit_pass`` — when True (default), the rate-limiter is stubbed to
    always allow requests (no Redis required for unit tests).  Pass False to
    simulate rate-limit rejection.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    csp_mod = _load_router()

    # Stub _check_rate so unit tests never need Redis (H-3 fix wires it for real).
    # The real _check_rate is tested separately in test_rate_limiter.py.
    async def _fake_check_rate(bucket: str, key: str, limit: int) -> None:
        if not rate_limit_pass:
            from fastapi import HTTPException
            raise HTTPException(status_code=429, detail="rate limited")

    # Inject into the module-level import used by receive_csp_violation.
    _rate_limiter_mod = types.ModuleType("app.services.pg_viewer.rate_limiter")
    _rate_limiter_mod._check_rate = _fake_check_rate  # type: ignore[attr-defined]
    _prev = sys.modules.get("app.services.pg_viewer.rate_limiter")
    sys.modules["app.services.pg_viewer.rate_limiter"] = _rate_limiter_mod

    app = FastAPI()
    app.include_router(csp_mod.router, prefix="/api")
    client = TestClient(app, raise_server_exceptions=False)

    # Restore after building (the router already captured the import path; the
    # deferred import inside receive_csp_violation will re-import on each call,
    # so we leave the fake in place for the lifetime of this client).
    # NOTE: this is acceptable because each test creates a fresh client.
    return client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LEGACY_BODY = json.dumps({
    "csp-report": {
        "blocked-uri": "https://evil.example.com/script.js",
        "effective-directive": "script-src",
        "original-policy": "default-src 'self'",
        "document-uri": "http://localhost:3000/admin/pg-viewer/tables",
        "violated-directive": "script-src",
        "source-file": "http://localhost:3000/admin/pg-viewer/tables",
        "line-number": 42,
        "status-code": 200,
    }
}).encode()

_MODERN_BODY = json.dumps([
    {
        "type": "csp-violation",
        "age": 10,
        "url": "http://localhost:3000/admin/pg-viewer/tables",
        "userAgent": "Mozilla/5.0",
        "body": {
            "blockedURL": "https://evil.example.com/a.js",
            "effectiveDirective": "script-src",
            "originalPolicy": "default-src 'self'",
            "documentURL": "http://localhost:3000/admin/pg-viewer/tables",
            "violatedDirective": "script-src",
            "sourceFile": "http://localhost:3000/admin/pg-viewer/tables",
            "lineNumber": 7,
            "statusCode": 200,
        },
    },
    {
        "type": "csp-violation",
        "age": 11,
        "url": "http://localhost:3000/admin/pg-viewer/tables",
        "userAgent": "Mozilla/5.0",
        "body": {
            "blockedURL": "https://evil.example.com/b.js",
            "effectiveDirective": "img-src",
            "originalPolicy": "default-src 'self'",
            "documentURL": "http://localhost:3000/admin/pg-viewer/tables",
            "violatedDirective": "img-src",
        },
    },
]).encode()


# ---------------------------------------------------------------------------
# Test 3: GET → 405 (unit, no DB)
# ---------------------------------------------------------------------------

class TestGetNotAllowed:
    def test_get_returns_405(self):
        client = _make_test_client()
        # Mock _insert_row so the test never touches a DB
        csp_mod = _load_router()
        with patch.object(csp_mod, "_insert_row", new=AsyncMock()):
            resp = client.get("/api/csp-violations")
        assert resp.status_code == 405


# ---------------------------------------------------------------------------
# Test 4: Oversize body → 413 (unit, no DB)
# ---------------------------------------------------------------------------

class TestOversizeBody:
    def test_oversize_returns_413(self):
        client = _make_test_client()
        oversize = b"x" * (16 * 1024 + 1)
        resp = client.post(
            "/api/csp-violations",
            content=oversize,
            headers={"Content-Type": "application/csp-report"},
        )
        assert resp.status_code == 413

    def test_exact_limit_accepted(self):
        """A body exactly at the limit must not be rejected for size alone."""
        csp_mod = _load_router()
        client = _make_test_client()
        # Build a body that is exactly _MAX_BODY_BYTES long.
        # Use a raw bytes payload equal to the limit — valid JSON padded to fit.
        limit = 16 * 1024
        prefix = b'{"csp-report": {"source-file": "'
        suffix = b'"}}'
        # padding fills the gap between prefix+suffix and the limit
        pad_len = limit - len(prefix) - len(suffix)
        body = prefix + b"x" * pad_len + suffix
        assert len(body) == limit
        with patch.object(csp_mod, "_insert_row", new=AsyncMock()):
            resp = client.post(
                "/api/csp-violations",
                content=body,
                headers={"Content-Type": "application/csp-report"},
            )
        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Test 5: Malformed JSON → 400, no stack trace (unit, no DB)
# ---------------------------------------------------------------------------

class TestMalformedJson:
    def test_malformed_returns_400(self):
        client = _make_test_client()
        resp = client.post(
            "/api/csp-violations",
            content=b"{not valid json!!!",
            headers={"Content-Type": "application/csp-report"},
        )
        assert resp.status_code == 400

    def test_no_stack_trace_in_response(self):
        """Response body must not contain 'Traceback' or exception class names."""
        client = _make_test_client()
        resp = client.post(
            "/api/csp-violations",
            content=b"<not json>",
            headers={"Content-Type": "application/csp-report"},
        )
        body_text = resp.text
        assert "Traceback" not in body_text
        assert "JSONDecodeError" not in body_text
        assert "Exception" not in body_text

    def test_non_object_non_array_returns_400(self):
        """A bare JSON number is syntactically valid but structurally wrong."""
        client = _make_test_client()
        csp_mod = _load_router()
        with patch.object(csp_mod, "_insert_row", new=AsyncMock()):
            resp = client.post(
                "/api/csp-violations",
                content=b"42",
                headers={"Content-Type": "application/csp-report"},
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Test 6: IP captured with XFF trust logic (unit, no DB)
# ---------------------------------------------------------------------------

class TestIpResolution:
    def test_untrusted_peer_uses_client_host(self):
        """When the peer is NOT in the trusted list, use request.client.host."""
        csp_mod = _load_router()
        captured: list[str | None] = []

        async def fake_insert(fields, ip, ua):
            captured.append(ip)

        client = _make_test_client()
        with patch.object(csp_mod, "_insert_row", new=fake_insert):
            # TestClient peer = 127.0.0.1 (not in trusted list by default)
            resp = client.post(
                "/api/csp-violations",
                content=_LEGACY_BODY,
                headers={
                    "Content-Type": "application/csp-report",
                    "X-Forwarded-For": "10.0.0.1",
                },
            )
        assert resp.status_code == 204
        # Should NOT use XFF 10.0.0.1 since peer is not trusted
        assert captured[0] != "10.0.0.1"

    def test_trusted_peer_uses_xff(self):
        """When the peer IS in the trusted list, use the first XFF IP."""
        csp_mod = _load_router()
        captured: list[str | None] = []

        async def fake_insert(fields, ip, ua):
            captured.append(ip)

        # get_settings is imported lazily inside _resolve_client_ip → patch at
        # the app.config module level (which is where the symbol actually lives).
        mock_settings = MagicMock()
        mock_settings.pg_viewer_trusted_proxy_ips = ["127.0.0.1", "testclient"]

        client = _make_test_client()
        with patch("app.config.get_settings", return_value=mock_settings), \
             patch.object(csp_mod, "_insert_row", new=fake_insert):
            resp = client.post(
                "/api/csp-violations",
                content=_LEGACY_BODY,
                headers={
                    "Content-Type": "application/csp-report",
                    "X-Forwarded-For": "203.0.113.5",
                },
            )
        assert resp.status_code == 204
        assert captured[0] == "203.0.113.5"


# ---------------------------------------------------------------------------
# Test 7: No JWT / auth cookie column in schema (unit — schema assertion)
# ---------------------------------------------------------------------------

class TestNoAuthColumnInSchema:
    """The csp_violation_log DDL must not contain auth-related columns."""

    def test_migration_has_no_jwt_or_cookie_column(self):
        """Read the migration SQL and assert it stores no auth data."""
        migration_path = os.path.join(
            _BACKEND_DIR, "scripts", "pg_viewer_migrate_003_csp_violation_log.sql"
        )
        assert os.path.exists(migration_path), "Migration 003 file not found"
        sql = open(migration_path).read().lower()

        forbidden_columns = ["jwt", "cookie", "token", "password", "auth", "session"]
        # Narrow check: we look for column definitions (not just any mention)
        import re
        # Extract column definition lines: lines between CREATE TABLE parens
        col_section = re.search(
            r"create table if not exists csp_violation_log\s*\((.*?)\);",
            sql,
            re.DOTALL,
        )
        assert col_section, "Could not find CREATE TABLE block in migration 003"
        col_text = col_section.group(1)

        for forbidden in forbidden_columns:
            assert forbidden not in col_text, (
                f"csp_violation_log has forbidden column reference '{forbidden}'"
            )

    def test_router_stores_only_defined_fields(self):
        """_insert_row SQL INSERT statement must not reference auth fields."""
        csp_mod = _load_router()
        import inspect
        import re
        src = inspect.getsource(csp_mod._insert_row)

        # Extract only the SQL string passed to text() — skip import lines and
        # module-path identifiers like "app.db.session".
        sql_match = re.search(r'text\(\s*"""(.*?)"""\s*\)', src, re.DOTALL)
        assert sql_match, "_insert_row must contain a text(\"\"\"...\"\"\") block"
        sql_text = sql_match.group(1).lower()

        for forbidden in ("jwt", "cookie", "token", "password", "session"):
            assert forbidden not in sql_text, (
                f"_insert_row SQL references forbidden field '{forbidden}'"
            )


# ---------------------------------------------------------------------------
# Test 1 + 2: Integration — live DB (skipped when DATABASE_URL not set)
# ---------------------------------------------------------------------------

@pytest.mark.integration
@INTEGRATION_SKIP
class TestLegacyFormatIntegration:
    """Test 1: Legacy format → 204, 1 row stored with populated fields."""

    @pytest.mark.asyncio
    async def test_legacy_post_stores_row(self):
        from httpx import AsyncClient, ASGITransport
        from fastapi import FastAPI

        csp_mod = _load_router()
        app = FastAPI()
        app.include_router(csp_mod.router, prefix="/api")

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post(
                "/api/csp-violations",
                content=_LEGACY_BODY,
                headers={"Content-Type": "application/csp-report"},
            )
        assert resp.status_code == 204

        # Verify row in DB
        from sqlalchemy import text
        from app.db.session import get_db_context

        async with get_db_context() as db:
            row = (await db.execute(
                text(
                    "SELECT blocked_uri, effective_directive FROM csp_violation_log "
                    "ORDER BY created_at DESC LIMIT 1"
                )
            )).fetchone()

        assert row is not None
        assert row[0] == "https://evil.example.com/script.js"
        assert row[1] == "script-src"


@pytest.mark.integration
@INTEGRATION_SKIP
class TestModernArrayFormatIntegration:
    """Test 2: Modern array format → 204, N rows stored."""

    @pytest.mark.asyncio
    async def test_modern_post_stores_multiple_rows(self):
        from httpx import AsyncClient, ASGITransport
        from fastapi import FastAPI
        from sqlalchemy import text
        from app.db.session import get_db_context

        csp_mod = _load_router()
        app = FastAPI()
        app.include_router(csp_mod.router, prefix="/api")

        # Record count before
        async with get_db_context() as db:
            count_before = (await db.execute(
                text("SELECT COUNT(*) FROM csp_violation_log")
            )).scalar()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post(
                "/api/csp-violations",
                content=_MODERN_BODY,
                headers={"Content-Type": "application/reports+json"},
            )
        assert resp.status_code == 204

        # Should have inserted 2 new rows
        async with get_db_context() as db:
            count_after = (await db.execute(
                text("SELECT COUNT(*) FROM csp_violation_log")
            )).scalar()

        assert count_after == count_before + 2
