"""Tests for pg_viewer audit writer (T-014).

Test matrix:
  1. Row insert          — live DB (integration, skipped when DB unavailable)
  2. Independent tx      — outer tx rollback; audit row must persist
  3. INSERT via Core     — compiled SQL uses sqlalchemy.insert(), not f-string
  4. SQL injection       — injection payload is parameterized; users table intact
  5. PII redaction       — ghp_ token in raw_sql → [REDACTED_GHP] in audit row
  6. Sanitized error log — connection error → logger.error with sanitized msg
  7. Partition miss      — SQLSTATE 23514 → spillover INSERT + logger.warning
  8. Append-only proof   — UPDATE on audit log denied (superuser env → xfail)
  9. XFF trust           — trusted proxy → accept XFF; untrusted → use peer IP

Tests 1, 2, 4, 5b, 8 require a live DB; they carry ``@pytest.mark.integration``
and skip automatically when ``DATABASE_URL`` is not set.

Tests 3, 5a, 6, 7, 9 are pure unit tests (no DB, no sqlalchemy at runtime)
and always run.

Run unit-only::

    pytest backend/tests/pg_viewer/test_audit.py -v -m "not integration"

Run all (requires live DB)::

    pytest backend/tests/pg_viewer/test_audit.py -v
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio  # noqa: F401


# ---------------------------------------------------------------------------
# Load modules directly from file paths — avoids package __init__ guard
# (JWT_SECRET check) and avoids requiring sqlalchemy at import time.
# ---------------------------------------------------------------------------


def _direct_load(module_name: str, rel_path: str) -> types.ModuleType:
    """Load a .py file directly and register under module_name in sys.modules."""
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


# Load pii_redactor first (pure stdlib — always safe).
_pii_mod = _direct_load(
    "app.services.pg_viewer.pii_redactor",
    "../../app/services/pg_viewer/pii_redactor.py",
)

# Load audit module (deferred sqlalchemy imports — importable without SA).
_audit_mod = _direct_load(
    "app.services.pg_viewer.audit",
    "../../app/services/pg_viewer/audit.py",
)

write_audit = _audit_mod.write_audit
_resolve_ip = _audit_mod._resolve_ip

# ---------------------------------------------------------------------------
# Integration skip condition
# ---------------------------------------------------------------------------

_DB_URL = os.getenv("DATABASE_URL", "")

_integration_mark = pytest.mark.skipif(
    not _DB_URL,
    reason="DATABASE_URL not set — integration tests skipped",
)

# ---------------------------------------------------------------------------
# Fake table objects (mimic enough of sqlalchemy.Table for the audit code)
# ---------------------------------------------------------------------------


class _FakeTable:
    """Minimal stand-in for sqlalchemy.Table with .name attribute."""

    def __init__(self, name: str):
        self.name = name


_FAKE_AUDIT_TABLE = _FakeTable("pg_viewer_audit_log")
_FAKE_SPILLOVER_TABLE = _FakeTable("pg_viewer_audit_log_spillover")


# ---------------------------------------------------------------------------
# Fake exception helpers (no asyncpg required)
# ---------------------------------------------------------------------------


class _FakeAsyncpgError(Exception):
    def __init__(self, msg: str, sqlstate: str | None = None):
        super().__init__(msg)
        self.sqlstate = sqlstate


class _FakeSAIntegrityError(Exception):
    """Minimal stand-in for sqlalchemy.exc.IntegrityError."""

    def __init__(self, msg: str, orig_sqlstate: str | None = None):
        super().__init__(msg)
        self.orig = _FakeAsyncpgError(msg, sqlstate=orig_sqlstate)


# ---------------------------------------------------------------------------
# Common write_audit kwargs
# ---------------------------------------------------------------------------


def _default_kwargs(**overrides):
    base = dict(
        user_id="test-user",
        query_type="sql_editor",
        resource=None,
        raw_sql="SELECT 1",
        row_count=1,
        elapsed_ms=42,
        status="ok",
        error_message=None,
        ip="127.0.0.1",
        ua="pytest/1.0",
        request=None,
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Context manager: inject all fakes needed for a pure-unit write_audit call
# ---------------------------------------------------------------------------


class _UnitEnv:
    """Context manager that injects fakes into sys.modules for one write_audit call.

    Sets up:
      - fake sqlalchemy (with a spy insert)
      - fake sqlalchemy.exc (with a fake IntegrityError class)
      - fake app.db.session (with mock engine)
      - fake app.config (with configurable trusted proxy list)
      - pre-seeded _audit_table / _spillover_table in the audit module
        (so _get_tables() returns immediately without importing real SA)

    ``execute_side_effect``: coroutine called instead of default noop for
    conn.execute(). If None, executed stmts are appended to self.executed.
    ``insert_side_effect``: callable invoked instead of default tracking insert.
    ``trusted_ips``: list of trusted proxy IPs for XFF config.
    ``integrity_error_class``: the IntegrityError class injected as
    sqlalchemy.exc.IntegrityError (defaults to _FakeSAIntegrityError).
    """

    def __init__(
        self,
        *,
        execute_side_effect=None,
        insert_side_effect=None,
        trusted_ips: list[str] | None = None,
        integrity_error_class=None,
    ):
        self._execute_side_effect = execute_side_effect
        self._insert_side_effect = insert_side_effect
        self._trusted_ips = trusted_ips or []
        self._integrity_error_class = integrity_error_class or _FakeSAIntegrityError

        self.executed: list = []   # stmts passed to conn.execute()
        self.inserted: list = []   # table names passed to fake insert()
        self.insert_values: list[dict] = []  # .values(**kw) dicts captured

        self._prev: dict[str, types.ModuleType | None] = {}

    # ------------------------------------------------------------------
    # Fake insert factory
    # ------------------------------------------------------------------

    def _make_fake_insert(self):
        insert_values_list = self.insert_values
        inserted_list = self.inserted
        user_side_effect = self._insert_side_effect

        class _CapturingStmt:
            def __init__(self, table_name: str):
                self.table_name = table_name

            def values(self, **kwargs):
                insert_values_list.append(dict(kwargs))
                return self

            def __repr__(self):
                return f"INSERT INTO {self.table_name}"

        def fake_insert(table, *args, **kwargs):
            name = getattr(table, "name", str(table))
            inserted_list.append(name)
            if user_side_effect is not None:
                return user_side_effect(table, *args, **kwargs)
            return _CapturingStmt(name)

        return fake_insert

    # ------------------------------------------------------------------
    # Fake execute
    # ------------------------------------------------------------------

    def _make_execute(self):
        executed_list = self.executed
        user_side_effect = self._execute_side_effect

        async def execute(stmt, *args, **kwargs):
            executed_list.append(stmt)
            if user_side_effect is not None:
                return await user_side_effect(stmt, *args, **kwargs)

        return execute

    # ------------------------------------------------------------------
    # Enter / exit
    # ------------------------------------------------------------------

    def __enter__(self):
        # --- mock engine ---
        execute = self._make_execute()
        mock_conn = AsyncMock()
        mock_conn.execute = execute
        self.mock_conn = mock_conn

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin = MagicMock(return_value=mock_cm)
        self.mock_engine = mock_engine

        # --- fake sqlalchemy module ---
        fake_sa = types.ModuleType("sqlalchemy")
        fake_sa.insert = self._make_fake_insert()  # type: ignore[attr-defined]

        # --- fake sqlalchemy.exc ---
        IE = self._integrity_error_class
        fake_sa_exc = types.ModuleType("sqlalchemy.exc")
        fake_sa_exc.IntegrityError = IE  # type: ignore[attr-defined]

        # --- fake app.db.session ---
        fake_session = types.ModuleType("app.db.session")
        fake_session.engine = mock_engine  # type: ignore[attr-defined]

        # --- fake app.config ---
        trusted = list(self._trusted_ips)

        class _FakeSettings:
            pg_viewer_trusted_proxy_ips = trusted

        fake_config = types.ModuleType("app.config")
        fake_config.get_settings = lambda: _FakeSettings()  # type: ignore[attr-defined]

        # Snapshot & inject
        for key in ("sqlalchemy", "sqlalchemy.exc", "app.db.session", "app.config"):
            self._prev[key] = sys.modules.get(key)
        sys.modules["sqlalchemy"] = fake_sa
        sys.modules["sqlalchemy.exc"] = fake_sa_exc
        sys.modules["app.db.session"] = fake_session
        sys.modules["app.config"] = fake_config

        # Pre-seed table singletons so _get_tables() returns without importing SA.
        self._orig_audit_table = _audit_mod._audit_table
        self._orig_spillover_table = _audit_mod._spillover_table
        _audit_mod._audit_table = _FAKE_AUDIT_TABLE
        _audit_mod._spillover_table = _FAKE_SPILLOVER_TABLE

        return self

    def __exit__(self, *args):
        # Restore sys.modules
        for key, prev in self._prev.items():
            if prev is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = prev
        # Restore table singletons
        _audit_mod._audit_table = self._orig_audit_table
        _audit_mod._spillover_table = self._orig_spillover_table


# ===========================================================================
# Test 1: Row insert (integration)
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
@_integration_mark
async def test_row_insert_persists():
    """write_audit() inserts a row with all expected fields into audit log."""
    from app.db.session import engine as main_engine  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    await write_audit(**_default_kwargs(
        user_id="audit-test-user",
        query_type="table_browse",
        resource="maximo_assets",
        raw_sql=None,
        status="ok",
        row_count=10,
        elapsed_ms=99,
    ))

    async with main_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT user_id, query_type, resource, row_count, elapsed_ms, status "
                "FROM pg_viewer_audit_log "
                "WHERE user_id = 'audit-test-user' "
                "ORDER BY logged_at DESC LIMIT 1"
            )
        )
        row = result.fetchone()

    assert row is not None, "Audit row was not inserted"
    assert row.user_id == "audit-test-user"
    assert row.query_type == "table_browse"
    assert row.resource == "maximo_assets"
    assert row.row_count == 10
    assert row.elapsed_ms == 99
    assert row.status == "ok"


# ===========================================================================
# Test 2: Independent transaction
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
@_integration_mark
async def test_independent_tx_survives_outer_rollback():
    """Audit row committed independently; outer tx rollback doesn't affect it."""
    from app.db.session import engine as main_engine, async_session_maker  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    outer_raised = False
    try:
        async with async_session_maker() as outer_session:
            await write_audit(**_default_kwargs(
                user_id="indep-tx-test",
                query_type="sql_editor",
                status="error",
                error_message="outer error",
            ))
            raise RuntimeError("outer handler failed — should roll back outer tx")
    except RuntimeError:
        outer_raised = True

    assert outer_raised, "Test setup error: RuntimeError was not raised"

    async with main_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT COUNT(*) FROM pg_viewer_audit_log "
                "WHERE user_id = 'indep-tx-test'"
            )
        )
        count = result.scalar()

    assert count >= 1, (
        f"Audit row not found after outer tx rollback (count={count}). "
        "Check that write_audit() uses engine.begin() not the outer session."
    )


# ===========================================================================
# Test 3: INSERT compiled via sqlalchemy.insert() — no f-string SQL
# ===========================================================================


@pytest.mark.asyncio
async def test_insert_uses_sqlalchemy_core_not_fstring():
    """INSERT must be built by sqlalchemy.insert(), never via f-string.

    Two-part check:
      A) Static source scan: audit.py must contain no f-string patterns that
         embed user-controlled input into SQL keyword strings.
      B) Runtime spy: insert() is called with the audit table object, NOT a
         raw SQL string.
    """
    # --- Part A: source scan ---
    audit_src_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "../../app/services/pg_viewer/audit.py")
    )
    with open(audit_src_path) as fh:
        source = fh.read()

    dangerous = [
        'f"SELECT', 'f"INSERT', 'f"UPDATE', 'f"DELETE',
        "f'SELECT", "f'INSERT", "f'UPDATE", "f'DELETE",
    ]
    for pat in dangerous:
        assert pat not in source, (
            f"Dangerous f-string SQL pattern found in audit.py: {pat!r}"
        )

    # --- Part B: runtime spy via _UnitEnv ---
    with _UnitEnv() as env:
        await write_audit(**_default_kwargs())

    assert len(env.inserted) >= 1, (
        "sqlalchemy.insert() was not called during write_audit(). "
        "INSERT was not built with Core insert()."
    )
    assert "pg_viewer_audit_log" in env.inserted[0], (
        f"First insert call targeted wrong table: {env.inserted[0]!r}"
    )


# ===========================================================================
# Test 4: SQL injection immunity
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
@_integration_mark
async def test_sql_injection_parameterized():
    """Injection payload in raw_sql is parameterized — users table survives."""
    from app.db.session import engine as main_engine  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    injection = "'; DROP TABLE users; --"

    async with main_engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM users"))
        count_before = result.scalar()

    await write_audit(**_default_kwargs(
        user_id="injection-test",
        raw_sql=injection,
        status="ok",
    ))

    async with main_engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM users"))
        count_after = result.scalar()

    assert count_after == count_before, (
        f"users table row count changed after injection test! "
        f"before={count_before}, after={count_after}"
    )

    async with main_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT raw_sql FROM pg_viewer_audit_log "
                "WHERE user_id = 'injection-test' ORDER BY logged_at DESC LIMIT 1"
            )
        )
        row = result.fetchone()

    assert row is not None, "Audit row not inserted for injection test"


# ===========================================================================
# Test 5a: PII redaction (pure unit — no DB)
# ===========================================================================


@pytest.mark.asyncio
async def test_pii_redaction_unit():
    """raw_sql with ghp_ token → insert values contain [REDACTED_GHP]."""
    token_sql = "SELECT 'ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789AB' AS tok"

    with _UnitEnv() as env:
        await write_audit(**_default_kwargs(raw_sql=token_sql))

    assert len(env.insert_values) >= 1, "No INSERT .values() call captured"
    stored_sql = env.insert_values[0].get("raw_sql", "")
    assert "[REDACTED_GHP]" in stored_sql, (
        f"ghp_ token not redacted. Got: {stored_sql!r}"
    )
    assert "ghp_" not in stored_sql, (
        f"Raw ghp_ token still present. Got: {stored_sql!r}"
    )


# ===========================================================================
# Test 5b: PII redaction (integration)
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
@_integration_mark
async def test_pii_redaction_db():
    """Integration: ghp_ token stored as [REDACTED_GHP] in the actual audit table."""
    from app.db.session import engine as main_engine  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    token_sql = "SELECT 'ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789AB' AS tok"

    await write_audit(**_default_kwargs(
        user_id="pii-redact-db-test",
        raw_sql=token_sql,
    ))

    async with main_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT raw_sql FROM pg_viewer_audit_log "
                "WHERE user_id = 'pii-redact-db-test' ORDER BY logged_at DESC LIMIT 1"
            )
        )
        row = result.fetchone()

    assert row is not None, "Audit row not inserted"
    assert "[REDACTED_GHP]" in row.raw_sql, (
        f"ghp_ token not redacted in DB. Got: {row.raw_sql!r}"
    )


# ===========================================================================
# Test 6: Sanitized error log on audit failure
# ===========================================================================


@pytest.mark.asyncio
async def test_audit_failure_logs_sanitized_error_no_reraise():
    """Connection error during audit write → logger.error with sanitized msg; no raise."""
    boom = Exception("could not connect postgres://aikm:pass@localhost:5432/aikm")

    # engine.begin() raises boom — simulates a connection failure.
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(side_effect=boom)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_engine = MagicMock()
    mock_engine.begin = MagicMock(return_value=mock_cm)

    error_calls: list[str] = []

    def capture_error(msg, *args, **kwargs):
        try:
            rendered = msg % args if args else str(msg)
        except Exception:
            rendered = str(msg)
        error_calls.append(rendered)

    # Patch the logger directly on the loaded module object.
    orig_error = _audit_mod.logger.error
    _audit_mod.logger.error = capture_error  # type: ignore[method-assign]

    fake_session = types.ModuleType("app.db.session")
    fake_session.engine = mock_engine  # type: ignore[attr-defined]

    # Pre-seed tables so _get_tables() doesn't need real SA.
    orig_at = _audit_mod._audit_table
    orig_st = _audit_mod._spillover_table
    _audit_mod._audit_table = _FAKE_AUDIT_TABLE
    _audit_mod._spillover_table = _FAKE_SPILLOVER_TABLE

    # Also need fake sqlalchemy + sqlalchemy.exc for the deferred imports.
    class _FakeIE(Exception):
        pass

    fake_sa = types.ModuleType("sqlalchemy")
    fake_sa.insert = MagicMock()  # type: ignore[attr-defined]
    fake_sa_exc = types.ModuleType("sqlalchemy.exc")
    fake_sa_exc.IntegrityError = _FakeIE  # type: ignore[attr-defined]

    prev_session = sys.modules.get("app.db.session")
    prev_sa = sys.modules.get("sqlalchemy")
    prev_sa_exc = sys.modules.get("sqlalchemy.exc")
    sys.modules["app.db.session"] = fake_session
    sys.modules["sqlalchemy"] = fake_sa
    sys.modules["sqlalchemy.exc"] = fake_sa_exc

    try:
        result = await write_audit(**_default_kwargs(status="error"))
    finally:
        _audit_mod.logger.error = orig_error  # type: ignore[method-assign]
        _audit_mod._audit_table = orig_at
        _audit_mod._spillover_table = orig_st
        if prev_session is None:
            sys.modules.pop("app.db.session", None)
        else:
            sys.modules["app.db.session"] = prev_session
        if prev_sa is None:
            sys.modules.pop("sqlalchemy", None)
        else:
            sys.modules["sqlalchemy"] = prev_sa
        if prev_sa_exc is None:
            sys.modules.pop("sqlalchemy.exc", None)
        else:
            sys.modules["sqlalchemy.exc"] = prev_sa_exc

    assert result is None, "write_audit must return None even on failure"
    assert len(error_calls) >= 1, "logger.error was not called on audit failure"

    logged = " ".join(error_calls)
    assert "postgres://" not in logged, (
        f"Connection string leaked in error log: {logged!r}"
    )
    assert "pass@" not in logged, (
        f"Password leaked in error log: {logged!r}"
    )


# ===========================================================================
# Test 7: Partition miss fallback
# ===========================================================================


@pytest.mark.asyncio
async def test_partition_miss_fallback_to_spillover():
    """SQLSTATE 23514 on primary insert → spillover INSERT + logger.warning."""

    call_count = 0

    class _PartitionMissIE(Exception):
        """Fake IntegrityError with SQLSTATE 23514."""
        def __init__(self, *args, **kwargs):
            super().__init__("check constraint violation")
            self.orig = _FakeAsyncpgError("check constraint", sqlstate="23514")

    async def execute_with_partition_miss(stmt, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise _PartitionMissIE()
        # Second call (spillover) succeeds — just append.

    with _UnitEnv(
        execute_side_effect=execute_with_partition_miss,
        integrity_error_class=_PartitionMissIE,
    ) as env:
        # Capture warnings
        warning_calls: list[str] = []
        orig_warning = _audit_mod.logger.warning
        _audit_mod.logger.warning = lambda msg, *a, **kw: warning_calls.append(msg)  # type: ignore[method-assign]

        try:
            result = await write_audit(**_default_kwargs())
        finally:
            _audit_mod.logger.warning = orig_warning  # type: ignore[method-assign]

    assert result is None, "write_audit must return None"
    # Second call must have targeted the spillover table.
    assert len(env.inserted) >= 2, (
        f"Expected 2 insert() calls (primary + spillover), got {env.inserted}"
    )
    assert "spillover" in env.inserted[1], (
        f"Second insert targeted wrong table: {env.inserted[1]!r}"
    )
    assert len(warning_calls) >= 1, "logger.warning not emitted on partition miss"
    assert "spillover" in warning_calls[0].lower(), (
        f"Warning doesn't mention spillover: {warning_calls[0]!r}"
    )


# ===========================================================================
# Test 8: Append-only proof
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
@_integration_mark
@pytest.mark.xfail(
    reason=(
        "T-003 deploy note: aikm is currently SUPERUSER in the dev environment "
        "so UPDATE is not denied. This test is expected to fail until the role "
        "is downgraded to a non-superuser in production. "
        "See T-003 for the migration that REVOKES UPDATE from aikm."
    ),
    strict=False,
)
async def test_append_only_update_denied():
    """UPDATE on pg_viewer_audit_log via aikm session must be permission denied."""
    from app.db.session import engine as main_engine  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415
    from sqlalchemy.exc import ProgrammingError  # noqa: PLC0415

    with pytest.raises(ProgrammingError) as exc_info:
        async with main_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE pg_viewer_audit_log SET status = 'ok' "
                    "WHERE 1 = 0"
                )
            )

    err = str(exc_info.value).lower()
    assert (
        "permission denied" in err
        or "42501" in err
        or "insufficient_privilege" in err
    ), f"Expected permission denied, got: {exc_info.value}"


# ===========================================================================
# Test 9: X-Forwarded-For trust (pure unit — no DB, no sqlalchemy)
# ===========================================================================


class _FakeClient:
    def __init__(self, host: str):
        self.host = host


class _FakeRequest:
    """Minimal stand-in for fastapi.Request."""

    def __init__(self, peer_ip: str, xff: str | None = None, ua: str | None = None):
        self.client = _FakeClient(peer_ip)
        _headers: dict[str, str] = {}
        if xff is not None:
            _headers["x-forwarded-for"] = xff
        if ua is not None:
            _headers["user-agent"] = ua
        self.headers = _headers


class _FakeSettings:
    def __init__(self, trusted_ips: list[str]):
        self.pg_viewer_trusted_proxy_ips = trusted_ips


def _with_fake_config(trusted_ips: list[str]):
    """Context manager: inject a fake app.config with given trusted IPs."""
    import contextlib

    @contextlib.contextmanager
    def _cm():
        fake_config = types.ModuleType("app.config")
        fake_config.get_settings = lambda: _FakeSettings(trusted_ips)  # type: ignore[attr-defined]
        prev = sys.modules.get("app.config")
        sys.modules["app.config"] = fake_config
        try:
            yield
        finally:
            if prev is None:
                sys.modules.pop("app.config", None)
            else:
                sys.modules["app.config"] = prev

    return _cm()


def test_xff_trusted_proxy_uses_xff_value():
    """Trusted proxy peer → XFF first IP is used as resolved IP."""
    request = _FakeRequest(peer_ip="10.0.0.5", xff="1.2.3.4")
    with _with_fake_config(["10.0.0.5"]):
        resolved_ip, _ = _resolve_ip(ip=None, ua=None, request=request)
    assert resolved_ip == "1.2.3.4", f"Expected '1.2.3.4', got {resolved_ip!r}"


def test_xff_untrusted_proxy_uses_peer_ip():
    """Untrusted proxy peer → direct peer IP is used, XFF ignored."""
    request = _FakeRequest(peer_ip="10.0.0.5", xff="1.2.3.4")
    with _with_fake_config([]):  # empty = never trust
        resolved_ip, _ = _resolve_ip(ip=None, ua=None, request=request)
    assert resolved_ip == "10.0.0.5", f"Expected '10.0.0.5', got {resolved_ip!r}"


def test_xff_multi_hop_takes_first_ip():
    """Multi-hop XFF 'a, b, c' → only the first IP ('a') is used."""
    request = _FakeRequest(peer_ip="10.0.0.5", xff="1.2.3.4, 5.6.7.8, 9.10.11.12")
    with _with_fake_config(["10.0.0.5"]):
        resolved_ip, _ = _resolve_ip(ip=None, ua=None, request=request)
    assert resolved_ip == "1.2.3.4", f"Expected '1.2.3.4', got {resolved_ip!r}"


def test_no_request_returns_explicit_ip():
    """No request object → explicit ip argument passed through unchanged."""
    resolved_ip, resolved_ua = _resolve_ip(ip="192.168.1.1", ua="curl/7.0", request=None)
    assert resolved_ip == "192.168.1.1"
    assert resolved_ua == "curl/7.0"


def test_xff_without_xff_header_uses_peer_ip():
    """Request with no XFF header → direct peer IP used."""
    request = _FakeRequest(peer_ip="10.0.0.5", xff=None)
    with _with_fake_config(["10.0.0.5"]):
        resolved_ip, _ = _resolve_ip(ip=None, ua=None, request=request)
    assert resolved_ip == "10.0.0.5"


@pytest.mark.asyncio
async def test_write_audit_xff_end_to_end():
    """write_audit() with a trusted-proxy request logs the XFF IP."""
    request = _FakeRequest(peer_ip="172.17.0.2", xff="203.0.113.7")

    with _UnitEnv(trusted_ips=["172.17.0.2"]) as env:
        await write_audit(**_default_kwargs(ip=None, ua=None, request=request))

    assert len(env.insert_values) >= 1, "No INSERT .values() call captured"
    assert env.insert_values[0].get("ip") == "203.0.113.7", (
        f"Expected XFF IP '203.0.113.7', got {env.insert_values[0].get('ip')!r}"
    )
