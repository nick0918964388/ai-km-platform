"""Integration tests for the pg_viewer engine + get_viewer_db dependency.

These tests require:
  - PG_VIEWER_DATABASE_URL env var pointing to a live Postgres instance
  - Migration 001 applied (aikm_viewer role exists, users_public view exists)
  - Migration 002 applied (maximo_tool_calls + related objects)

All tests are skipped when PG_VIEWER_DATABASE_URL is not set in the environment.

Run with::

    pytest backend/tests/pg_viewer/test_engine.py -v -m integration

Mark: @pytest.mark.integration (registered in pytest.ini / pyproject.toml)
"""
from __future__ import annotations

import os
import time

import pytest
import pytest_asyncio  # noqa: F401 — required for async test support

# ---------------------------------------------------------------------------
# Skip condition — applied module-wide via pytestmark
# ---------------------------------------------------------------------------

_PG_URL = os.getenv("PG_VIEWER_DATABASE_URL", "")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _PG_URL,
        reason="PG_VIEWER_DATABASE_URL not set — integration tests skipped",
    ),
]


# ---------------------------------------------------------------------------
# Fixture: live connection via get_viewer_db()
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def viewer_conn():
    """Yield one AsyncConnection from get_viewer_db() for each test.

    We manually drive the async generator rather than using FastAPI's Depends
    so the tests don't need a running ASGI app.
    """
    from app.services.pg_viewer.engine import get_viewer_db

    gen = get_viewer_db()
    conn = await gen.__anext__()
    yield conn
    # Drain the generator so the transaction is committed/rolled-back cleanly.
    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass


# ---------------------------------------------------------------------------
# Test 1: SELECT 1 smoke
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_select_1_smoke(viewer_conn):
    """get_viewer_db yields a working connection; SELECT 1 returns 1."""
    from sqlalchemy import text

    result = await viewer_conn.execute(text("SELECT 1"))
    scalar = result.scalar()
    assert scalar == 1, f"Expected 1, got {scalar!r}"


# ---------------------------------------------------------------------------
# Test 2: CREATE TABLE denied (L5 read-only role)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_table_denied(viewer_conn):
    """aikm_viewer is a read-only role; CREATE TABLE must raise a privilege error."""
    from sqlalchemy import text
    from sqlalchemy.exc import ProgrammingError

    with pytest.raises(ProgrammingError) as exc_info:
        await viewer_conn.execute(text("CREATE TABLE _pg_viewer_test_should_fail (id int)"))

    # asyncpg surfaces SQLSTATE 42501 (insufficient_privilege).
    # SQLAlchemy wraps it in ProgrammingError; the SQLSTATE is in the orig.
    err_str = str(exc_info.value).lower()
    assert (
        "42501" in err_str
        or "permission denied" in err_str
        or "insufficient_privilege" in err_str
        or "must be owner" in err_str
    ), f"Expected privilege error, got: {exc_info.value}"


# ---------------------------------------------------------------------------
# Test 3: Three-layer timeout — SELECT pg_sleep(30) must be cancelled < 11 s
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_three_layer_timeout(viewer_conn):
    """SET LOCAL statement_timeout = '10s' must cancel pg_sleep(30) < 11 s."""
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError, OperationalError

    start = time.monotonic()
    with pytest.raises((DBAPIError, OperationalError, Exception)) as exc_info:
        await viewer_conn.execute(text("SELECT pg_sleep(30)"))
    elapsed = time.monotonic() - start

    # Wall-clock must be well under 11 seconds.
    assert elapsed < 11.0, (
        f"Query was not cancelled within 11 s (elapsed={elapsed:.2f}s). "
        "Check that SET LOCAL statement_timeout is applied in get_viewer_db()."
    )

    # Confirm it's actually a cancellation / timeout, not some other error.
    err_str = str(exc_info.value).lower()
    assert (
        "canceling" in err_str          # PostgreSQL's spelling
        or "cancelled" in err_str
        or "cancel" in err_str
        or "timeout" in err_str
        or "statement_timeout" in err_str
    ), f"Expected cancellation error, got: {exc_info.value}"


# ---------------------------------------------------------------------------
# Test 4: users table denied (REVOKEd from aikm_viewer)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_users_table_denied(viewer_conn):
    """Direct SELECT on users table must be denied for aikm_viewer."""
    from sqlalchemy import text
    from sqlalchemy.exc import ProgrammingError

    with pytest.raises(ProgrammingError) as exc_info:
        await viewer_conn.execute(text("SELECT * FROM users LIMIT 1"))

    err_str = str(exc_info.value).lower()
    assert (
        "42501" in err_str
        or "permission denied" in err_str
        or "insufficient_privilege" in err_str
    ), f"Expected permission denied on users, got: {exc_info.value}"


# ---------------------------------------------------------------------------
# Test 5: users_public view accessible (may return 0 rows, but no error)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_users_public_ok(viewer_conn):
    """SELECT on users_public view should succeed (0+ rows, no permission error)."""
    from sqlalchemy import text

    result = await viewer_conn.execute(text("SELECT * FROM users_public LIMIT 1"))
    # Fetch all rows — may be empty, that's fine.
    rows = result.fetchall()
    # No exception == pass.  rows may be [] if no users exist yet.
    assert isinstance(rows, list)
