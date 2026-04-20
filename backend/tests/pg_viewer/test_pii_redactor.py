"""Unit tests for pg_viewer.pii_redactor — pure functions, no DB required.

Run with::

    pytest backend/tests/pg_viewer/test_pii_redactor.py -v

Import strategy: we import ``pii_redactor`` via importlib so that the
package-level ``__init__.py`` startup guard (JWT_SECRET check) does not fire
during test collection on a dev machine without env vars configured.
"""
from __future__ import annotations

import importlib
import importlib.util
import re
import sys

import pytest

# ---------------------------------------------------------------------------
# Import pii_redactor without triggering the pg_viewer package __init__ guard.
# We load the module directly from its file path and inject it into sys.modules
# under a test-private name so other imports don't collide with the real module.
# ---------------------------------------------------------------------------

def _import_pii_redactor():
    spec = importlib.util.spec_from_file_location(
        "app.services.pg_viewer.pii_redactor",
        # Resolve relative to this test file's location
        __file__.replace(
            "tests/pg_viewer/test_pii_redactor.py",
            "app/services/pg_viewer/pii_redactor.py",
        ),
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["app.services.pg_viewer.pii_redactor"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _import_pii_redactor()
redact_sql_for_audit = _mod.redact_sql_for_audit
sanitize_pg_error = _mod.sanitize_pg_error


# ===========================================================================
# Helpers — lightweight fake exception classes (no asyncpg needed)
# ===========================================================================

class _FakeAsyncpgError(Exception):
    """Minimal stand-in for asyncpg.exceptions.PostgresError."""

    def __init__(self, message: str, sqlstate: str | None = None):
        super().__init__(message)
        self.sqlstate = sqlstate


class _FakeSAError(Exception):
    """Minimal stand-in for sqlalchemy.exc.DBAPIError wrapping asyncpg."""

    def __init__(self, message: str, orig_sqlstate: str | None = None):
        super().__init__(message)
        self.orig = _FakeAsyncpgError(message, sqlstate=orig_sqlstate)


# ===========================================================================
# redact_sql_for_audit — pattern tests
# ===========================================================================


class TestRedactSqlForAudit:

    def test_ghp_token_redacted(self):
        sql = "SELECT 'ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789AB' AS tok"
        result = redact_sql_for_audit(sql)
        assert "[REDACTED_GHP]" in result
        assert "ghp_" not in result

    def test_github_pat_redacted(self):
        # github_pat_ + 82 alphanum/underscore chars
        pat = "github_pat_" + "A" * 82
        sql = f"SELECT '{pat}' AS tok"
        result = redact_sql_for_audit(sql)
        assert "[REDACTED_GITHUB_PAT]" in result
        assert "github_pat_" not in result

    def test_sk_key_redacted(self):
        sql = "INSERT INTO cfg VALUES ('sk-abcdefghijklmnopqrstu')"
        result = redact_sql_for_audit(sql)
        assert "[REDACTED_SK]" in result
        assert "sk-" not in result

    def test_bearer_token_redacted_case_insensitive(self):
        sql = "WHERE Authorization = 'Bearer abc123.def456.ghi789012345678'"
        result = redact_sql_for_audit(sql)
        # The Bearer prefix should remain but the token must be gone
        assert "Bearer [REDACTED_BEARER]" in result
        assert "abc123" not in result

    def test_bearer_lower_case_redacted(self):
        sql = "SET header = 'bearer abc123.def456.ghi789012345678'"
        result = redact_sql_for_audit(sql)
        assert "[REDACTED_BEARER]" in result

    def test_aws_key_redacted(self):
        sql = "SELECT 'AKIAIOSFODNN7EXAMPLE' AS k"  # 20 uppercase alphanum after AKIA
        result = redact_sql_for_audit(sql)
        assert "[REDACTED_AWS_KEY]" in result
        assert "AKIA" not in result

    def test_hex40_redacted(self):
        hex40 = "a" * 40
        sql = f"WHERE commit_hash = '{hex40}'"
        result = redact_sql_for_audit(sql)
        assert "[REDACTED_HEX40]" in result
        assert hex40 not in result

    def test_hex_under_40_not_redacted(self):
        hex39 = "a" * 39
        sql = f"WHERE id = '{hex39}'"
        result = redact_sql_for_audit(sql)
        # 39-char hex should NOT be redacted
        assert hex39 in result

    def test_password_hash_literal_redacted(self):
        sql = "SELECT password_hash = 'bcrypt$2b$12$somethinglong' FROM x"
        result = redact_sql_for_audit(sql)
        assert "[REDACTED_LITERAL]" in result
        assert "bcrypt" not in result
        # Column name must still be present
        assert "password_hash" in result

    def test_token_literal_redacted(self):
        sql = "UPDATE users SET token = 'super_secret_token_value' WHERE id = 1"
        result = redact_sql_for_audit(sql)
        assert "[REDACTED_LITERAL]" in result
        assert "super_secret_token_value" not in result

    def test_api_key_literal_redacted(self):
        # Spec pattern: key = 'value' — positional INSERT is outside spec scope
        sql = "UPDATE cfg SET api_key = 'my-api-key-here' WHERE id = 1"
        result = redact_sql_for_audit(sql)
        assert "[REDACTED_LITERAL]" in result
        assert "my-api-key-here" not in result

    def test_secret_literal_redacted(self):
        sql = "SET secret = 'topsecret123'"
        result = redact_sql_for_audit(sql)
        assert "[REDACTED_LITERAL]" in result

    def test_credential_literal_redacted(self):
        sql = "WHERE credential = 'mysupersecretcredential'"
        result = redact_sql_for_audit(sql)
        assert "[REDACTED_LITERAL]" in result

    def test_truncation_to_8000(self):
        sql = "x" * 10_000
        result = redact_sql_for_audit(sql)
        assert len(result) == 8000

    def test_safe_sql_unchanged(self):
        sql = "SELECT id, name FROM users WHERE active = true LIMIT 10"
        result = redact_sql_for_audit(sql)
        assert result == sql

    def test_empty_string(self):
        assert redact_sql_for_audit("") == ""

    def test_exactly_8000_chars_unchanged_length(self):
        sql = "SELECT 1; " * 800  # exactly 8000 chars
        result = redact_sql_for_audit(sql)
        assert len(result) == 8000


# ===========================================================================
# sanitize_pg_error — SQLSTATE mapping tests
# ===========================================================================


class TestSanitizePgError:

    def test_57014_query_canceled(self):
        exc = _FakeAsyncpgError("canceling statement due to statement timeout", "57014")
        status, msg = sanitize_pg_error(exc)
        assert status == 408
        assert "timed out" in msg

    def test_42P01_undefined_table(self):
        exc = _FakeAsyncpgError('relation "foo" does not exist', "42P01")
        status, msg = sanitize_pg_error(exc)
        assert status == 422
        assert "exist" in msg

    def test_42703_undefined_column(self):
        exc = _FakeAsyncpgError('column "bar" does not exist', "42703")
        status, msg = sanitize_pg_error(exc)
        assert status == 422
        assert "exist" in msg

    def test_42501_insufficient_privilege_no_role_name(self):
        exc = _FakeAsyncpgError(
            'permission denied for table users, role "aikm_viewer"', "42501"
        )
        status, msg = sanitize_pg_error(exc)
        assert status == 403
        assert "grant missing" in msg
        # Role name MUST NOT appear in the safe message
        assert "aikm_viewer" not in msg
        assert '"' not in msg or "role" not in msg.lower()

    def test_53300_too_many_connections(self):
        exc = _FakeAsyncpgError("too many connections for database", "53300")
        status, msg = sanitize_pg_error(exc)
        assert status == 503
        assert "busy" in msg

    def test_22P02_invalid_text_representation(self):
        exc = _FakeAsyncpgError('invalid input syntax for type integer: "abc"', "22P02")
        status, msg = sanitize_pg_error(exc)
        assert status == 422
        assert "invalid" in msg

    def test_23514_check_violation(self):
        exc = _FakeAsyncpgError("new row for relation violates check constraint", "23514")
        status, msg = sanitize_pg_error(exc)
        assert status == 422
        assert "constraint" in msg

    def test_P0001_user_raise(self):
        exc = _FakeAsyncpgError("custom business rule violation", "P0001")
        status, msg = sanitize_pg_error(exc)
        assert status == 422
        assert "business rule" in msg

    def test_default_bucket_unknown_sqlstate(self):
        exc = _FakeAsyncpgError("some unknown postgres error", "99999")
        status, msg = sanitize_pg_error(exc)
        assert status == 500
        assert msg == "internal database error"

    def test_sqlalchemy_wrapped_exception(self):
        """SQLAlchemy DBAPIError wraps asyncpg in .orig — must still work."""
        exc = _FakeSAError("(asyncpg.InsufficientPrivilegeError) ...", "42501")
        status, msg = sanitize_pg_error(exc)
        assert status == 403

    def test_plain_exception_default(self):
        exc = Exception("something went wrong")
        status, msg = sanitize_pg_error(exc)
        assert status == 500
        assert msg == "internal database error"

    # -----------------------------------------------------------------------
    # Safety assertions — output must NEVER leak internals
    # -----------------------------------------------------------------------

    def _assert_safe_message(self, msg: str) -> None:
        """Probe the message for dangerous patterns that must NOT appear."""
        # No role name patterns
        assert not re.search(r'\brole\s+"[^"]+"', msg, re.IGNORECASE), (
            f"Role name leaked in message: {msg!r}"
        )
        # No connection strings
        assert not re.search(r"postgres(?:ql)?://", msg, re.IGNORECASE), (
            f"Connection string leaked in message: {msg!r}"
        )
        # No file paths ending in .sql / .py / .log
        assert not re.search(r"/[\w./\-]+\.(sql|py|log)", msg), (
            f"File path leaked in message: {msg!r}"
        )
        # No DETAIL / HINT / CONTEXT sections
        assert not re.search(r"\b(DETAIL|HINT|CONTEXT)\s*:", msg, re.IGNORECASE), (
            f"DETAIL/HINT/CONTEXT leaked in message: {msg!r}"
        )

    def test_no_role_leak_42501(self):
        exc = _FakeAsyncpgError('role "superuser" permission denied', "42501")
        _, msg = sanitize_pg_error(exc)
        self._assert_safe_message(msg)

    def test_no_connstr_leak_default(self):
        exc = _FakeAsyncpgError(
            "could not connect to postgres://aikm:password@localhost:5432/aikm", None
        )
        _, msg = sanitize_pg_error(exc)
        self._assert_safe_message(msg)

    def test_no_filepath_leak_default(self):
        exc = _FakeAsyncpgError("error at /app/backend/migrations/001.sql line 42", None)
        _, msg = sanitize_pg_error(exc)
        self._assert_safe_message(msg)

    def test_no_detail_hint_leak_P0001(self):
        exc = _FakeAsyncpgError(
            "validation failed\nDETAIL: row violates constraint xyz\nHINT: check your input",
            "P0001",
        )
        _, msg = sanitize_pg_error(exc)
        self._assert_safe_message(msg)

    def test_all_sqlstates_produce_safe_messages(self):
        """Enumerate all mapped SQLSTATEs and verify output safety."""
        cases = [
            ("57014", "query timed out"),
            ("42P01", "relation error"),
            ("42703", "column error"),
            ("42501", 'permission denied role "aikm_viewer"'),
            ("53300", "too many connections"),
            ("22P02", "invalid integer"),
            ("23514", "check constraint"),
            ("P0001", "user raised DETAIL: secret hint"),
        ]
        for sqlstate, raw_msg in cases:
            exc = _FakeAsyncpgError(raw_msg, sqlstate)
            _, msg = sanitize_pg_error(exc)
            self._assert_safe_message(msg)
