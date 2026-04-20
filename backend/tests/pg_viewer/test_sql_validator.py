"""Unit tests for pg_viewer.sql_validator — pure function, no DB required.

Run with::

    pytest backend/tests/pg_viewer/test_sql_validator.py -v

Import strategy: we load sql_validator directly from file path (same pattern
as test_pii_redactor.py) to bypass the pg_viewer package __init__.py startup
guard (JWT_SECRET check) and the app.config deferred import inside
validate_select_sql. The config import is patched via a lightweight fake
settings module so no .env file is required.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Minimal fake settings — patches app.config before loading sql_validator
# ---------------------------------------------------------------------------

def _install_fake_config(row_limit: int = 1000) -> None:
    """Inject a minimal app.config stub into sys.modules."""
    if "app.config" in sys.modules:
        return
    fake_settings = MagicMock()
    fake_settings.pg_viewer_row_limit = row_limit

    fake_config = types.ModuleType("app.config")
    fake_config.get_settings = lambda: fake_settings  # type: ignore[attr-defined]

    # Also stub parent packages so the deferred import works
    if "app" not in sys.modules:
        sys.modules["app"] = types.ModuleType("app")

    sys.modules["app.config"] = fake_config


_install_fake_config()


# ---------------------------------------------------------------------------
# Load sql_validator directly (bypasses pg_viewer __init__ guard)
# ---------------------------------------------------------------------------

def _load_sql_validator():
    spec = importlib.util.spec_from_file_location(
        "app.services.pg_viewer.sql_validator",
        __file__.replace(
            "tests/pg_viewer/test_sql_validator.py",
            "app/services/pg_viewer/sql_validator.py",
        ),
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["app.services.pg_viewer.sql_validator"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load_sql_validator()

validate_select_sql = _mod.validate_select_sql
WrappedSql = _mod.WrappedSql
EmptyInputError = _mod.EmptyInputError
TooLongError = _mod.TooLongError
MultiStatementError = _mod.MultiStatementError
NotSelectError = _mod.NotSelectError
ForbiddenKeywordError = _mod.ForbiddenKeywordError
ForbiddenFunctionError = _mod.ForbiddenFunctionError
LimitExceededError = _mod.LimitExceededError
ParseError = _mod.ParseError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WRAP_PREFIX = "SELECT * FROM ("
_WRAP_SUFFIX = ") _limited LIMIT 1000"


def _assert_wrapped(result: WrappedSql, expected_inner: str | None = None) -> None:
    """Assert that the result is a properly wrapped WrappedSql."""
    assert result.wrap_applied is True
    assert result.wrapped_sql.startswith(_WRAP_PREFIX)
    assert result.wrapped_sql.endswith(_WRAP_SUFFIX)
    if expected_inner is not None:
        inner = result.wrapped_sql[len(_WRAP_PREFIX): -len(_WRAP_SUFFIX)]
        assert inner == expected_inner


# ===========================================================================
# Positive cases — must all accept
# ===========================================================================

class TestPositiveCases:

    def test_select_1(self):
        result = validate_select_sql("SELECT 1")
        _assert_wrapped(result, "SELECT 1")
        assert result.original_sql == "SELECT 1"

    def test_select_lowercase_with_limit(self):
        result = validate_select_sql("select * from users_public limit 5")
        _assert_wrapped(result, "select * from users_public limit 5")

    def test_cte_select(self):
        sql = "WITH cte AS (SELECT 1) SELECT * FROM cte"
        result = validate_select_sql(sql)
        _assert_wrapped(result, sql)

    def test_trailing_semicolon_tolerated(self):
        """Single trailing ';' must be stripped and accepted."""
        result = validate_select_sql("SELECT 1;")
        # semicolon stripped from inner
        _assert_wrapped(result, "SELECT 1")

    def test_wrap_applied_true(self):
        result = validate_select_sql("SELECT 42")
        assert result.wrap_applied is True

    def test_original_sql_preserved(self):
        raw = "  SELECT 1  "
        result = validate_select_sql(raw)
        assert result.original_sql == raw


# ===========================================================================
# Multi-statement rejection
# ===========================================================================

class TestMultiStatement:

    def test_two_selects(self):
        with pytest.raises(MultiStatementError):
            validate_select_sql("SELECT 1; SELECT 2")

    def test_select_then_drop(self):
        with pytest.raises(MultiStatementError):
            validate_select_sql("SELECT 1; DROP TABLE users")

    def test_select_semicolon_comment(self):
        """SELECT 1; /*x*/; — spec requires MultiStatementError.

        After stripping the trailing ';', sqlparse produces two statements
        ('SELECT 1;' and '/*x*/'), so this correctly raises MultiStatementError.
        """
        with pytest.raises(MultiStatementError):
            validate_select_sql("SELECT 1; /*x*/;")


# ===========================================================================
# Keyword denylist
# ===========================================================================

class TestForbiddenKeywords:

    def test_drop_table(self):
        with pytest.raises(ForbiddenKeywordError) as exc_info:
            validate_select_sql("DROP TABLE users")
        assert exc_info.value.keyword == "DROP"

    def test_insert_into(self):
        with pytest.raises(ForbiddenKeywordError) as exc_info:
            validate_select_sql("INSERT INTO users VALUES (1)")
        assert exc_info.value.keyword == "INSERT"

    def test_update(self):
        with pytest.raises(ForbiddenKeywordError) as exc_info:
            validate_select_sql("UPDATE users SET name='x'")
        assert exc_info.value.keyword == "UPDATE"

    def test_delete(self):
        with pytest.raises(ForbiddenKeywordError) as exc_info:
            validate_select_sql("DELETE FROM users")
        assert exc_info.value.keyword == "DELETE"

    def test_truncate(self):
        with pytest.raises(ForbiddenKeywordError) as exc_info:
            validate_select_sql("TRUNCATE users")
        assert exc_info.value.keyword == "TRUNCATE"

    def test_grant(self):
        with pytest.raises(ForbiddenKeywordError) as exc_info:
            validate_select_sql("GRANT ALL ON users TO someone")
        assert exc_info.value.keyword == "GRANT"

    def test_copy(self):
        with pytest.raises(ForbiddenKeywordError) as exc_info:
            validate_select_sql("COPY users FROM stdin")
        assert exc_info.value.keyword == "COPY"

    def test_create_table(self):
        with pytest.raises(ForbiddenKeywordError) as exc_info:
            validate_select_sql("CREATE TABLE foo (id int)")
        assert exc_info.value.keyword == "CREATE"

    def test_alter_table(self):
        with pytest.raises(ForbiddenKeywordError) as exc_info:
            validate_select_sql("ALTER TABLE users ADD COLUMN x int")
        assert exc_info.value.keyword == "ALTER"

    def test_vacuum(self):
        with pytest.raises(ForbiddenKeywordError) as exc_info:
            validate_select_sql("VACUUM")
        assert exc_info.value.keyword == "VACUUM"

    def test_call(self):
        with pytest.raises(ForbiddenKeywordError) as exc_info:
            validate_select_sql("CALL proc()")
        assert exc_info.value.keyword == "CALL"

    def test_security_label(self):
        with pytest.raises(ForbiddenKeywordError) as exc_info:
            validate_select_sql("SECURITY LABEL ...")
        assert exc_info.value.keyword == "SECURITY"

    def test_copy_to_program(self):
        """COPY (SELECT 1) TO PROGRAM 'nc ...' — COPY in keyword list."""
        with pytest.raises(ForbiddenKeywordError) as exc_info:
            validate_select_sql("COPY (SELECT 1) TO PROGRAM 'nc ...'")
        assert exc_info.value.keyword == "COPY"

    def test_case_insensitive(self):
        """DrOp tAbLe users — denylist is case-insensitive."""
        with pytest.raises(ForbiddenKeywordError) as exc_info:
            validate_select_sql("DrOp tAbLe users")
        assert exc_info.value.keyword == "DROP"


# ===========================================================================
# CTE-headed write
# ===========================================================================

class TestCteWrite:

    def test_cte_with_delete(self):
        """WITH foo AS (DELETE FROM users RETURNING *) SELECT * FROM foo."""
        with pytest.raises(ForbiddenKeywordError) as exc_info:
            validate_select_sql(
                "WITH foo AS (DELETE FROM users RETURNING *) SELECT * FROM foo"
            )
        assert exc_info.value.keyword == "DELETE"


# ===========================================================================
# Comment tricks
# ===========================================================================

class TestCommentTricks:

    def test_block_comment_before_drop(self):
        """/* hidden */ DROP TABLE users — comment precedes actual DROP → reject."""
        with pytest.raises(ForbiddenKeywordError) as exc_info:
            validate_select_sql("/* hidden */ DROP TABLE users")
        assert exc_info.value.keyword == "DROP"

    def test_line_comment_contains_drop(self):
        """-- DROP\\nSELECT 1 — forbidden keyword inside line comment → reject.

        sqlparse tokenizes '-- DROP\\n' as Comment.Single (not a Keyword token),
        so the keyword walker skips it. However, our secondary comment-body scan
        finds 'DROP' inside the comment text and raises ForbiddenKeywordError.

        This is a conservative design: any SQL that contains a forbidden keyword
        anywhere (including comments) is rejected, preventing obfuscation attempts.
        """
        with pytest.raises(ForbiddenKeywordError) as exc_info:
            validate_select_sql("-- DROP\nSELECT 1")
        assert exc_info.value.keyword == "DROP"

    def test_nested_comment_drop(self):
        """/* /* */ DROP */ SELECT 1 — sqlparse sees DROP as a keyword → reject."""
        with pytest.raises(ForbiddenKeywordError) as exc_info:
            validate_select_sql("/* /* */ DROP */ SELECT 1")
        assert exc_info.value.keyword == "DROP"

    def test_mysql_hint_comment(self):
        """/*! DROP */ SELECT 1 — MySQL hint comment body scanned → reject.

        sqlparse treats '/*! DROP */' as Token.Comment.Multiline.
        Our secondary comment-body scan finds 'DROP' → ForbiddenKeywordError.
        """
        with pytest.raises(ForbiddenKeywordError) as exc_info:
            validate_select_sql("/*! DROP */ SELECT 1")
        assert exc_info.value.keyword == "DROP"


# ===========================================================================
# Quoted string NOT flagged
# ===========================================================================

class TestQuotedString:

    def test_drop_in_string_literal_accepted(self):
        """SELECT 'DROP TABLE users' AS x — literal string value, not keyword token.

        sqlparse tokenizes 'DROP TABLE users' as Token.Literal.String.Single.
        The keyword walker skips string literals → ACCEPT.
        """
        result = validate_select_sql("SELECT 'DROP TABLE users' AS x")
        assert result.wrap_applied is True

    def test_insert_in_string_accepted(self):
        result = validate_select_sql("SELECT 'INSERT is a bad word' AS msg")
        assert result.wrap_applied is True


# ===========================================================================
# DoS functions
# ===========================================================================

class TestForbiddenFunctions:

    def test_pg_sleep(self):
        with pytest.raises(ForbiddenFunctionError) as exc_info:
            validate_select_sql("SELECT pg_sleep(30)")
        assert exc_info.value.name == "pg_sleep"

    def test_pg_terminate_backend(self):
        with pytest.raises(ForbiddenFunctionError) as exc_info:
            validate_select_sql("SELECT pg_terminate_backend(1)")
        assert exc_info.value.name == "pg_terminate_backend"

    def test_dblink_exec(self):
        with pytest.raises(ForbiddenFunctionError) as exc_info:
            validate_select_sql("SELECT dblink_exec('SELECT 1')")
        assert exc_info.value.name == "dblink_exec"

    def test_lo_import(self):
        with pytest.raises(ForbiddenFunctionError) as exc_info:
            validate_select_sql("SELECT lo_import('/etc/passwd')")
        assert exc_info.value.name == "lo_import"

    def test_pg_read_file(self):
        with pytest.raises(ForbiddenFunctionError) as exc_info:
            validate_select_sql("SELECT pg_read_file('/etc/passwd')")
        assert exc_info.value.name == "pg_read_file"

    def test_pg_ls_dir(self):
        with pytest.raises(ForbiddenFunctionError) as exc_info:
            validate_select_sql("SELECT pg_ls_dir('.')")
        assert exc_info.value.name == "pg_ls_dir"

    def test_pg_stat_activity_as_view(self):
        """SELECT pg_stat_activity — referenced as a view/table, not a function call.

        sqlparse tokenizes this as Token.Name. Our function walker also checks
        flat Token.Name identifiers against the forbidden function set → reject.
        """
        with pytest.raises(ForbiddenFunctionError) as exc_info:
            validate_select_sql("SELECT pg_stat_activity")
        assert exc_info.value.name == "pg_stat_activity"


# ===========================================================================
# psql meta-command
# ===========================================================================

class TestPsqlMetaCommand:

    def test_backslash_copy(self):
        r"""\\copy (SELECT 1) TO '/tmp/x' — psql meta-command → ParseError.

        sqlparse assigns Token.Generic.Command to '\\copy'. Our validator
        detects this and raises ParseError rather than NotSelectError, per spec.
        """
        with pytest.raises(ParseError):
            validate_select_sql(r"\copy (SELECT 1) TO '/tmp/x'")


# ===========================================================================
# Empty / whitespace / oversize
# ===========================================================================

class TestInputBounds:

    def test_empty_string(self):
        with pytest.raises(EmptyInputError):
            validate_select_sql("")

    def test_whitespace_only(self):
        with pytest.raises(EmptyInputError):
            validate_select_sql("   ")

    def test_oversize(self):
        with pytest.raises(TooLongError):
            validate_select_sql("a" * 9000)

    def test_exactly_max_len_accepted(self):
        """SQL of exactly max_len chars does not raise TooLongError."""
        # Build a valid SELECT that is exactly 8000 chars by padding a comment
        padding = "-- " + "x" * (8000 - len("SELECT 1 -- ") - 1) + "\n"
        sql = "SELECT 1 " + padding
        sql = sql[:8000]
        # We only care that TooLongError is NOT raised; other errors may occur
        # if the padding makes it syntactically weird, so we catch broadly.
        try:
            validate_select_sql(sql, max_len=8000)
        except TooLongError:
            pytest.fail("TooLongError raised for exactly max_len input")
        except Exception:
            pass  # other validation errors are fine for this test


# ===========================================================================
# BOM and Unicode normalization
# ===========================================================================

class TestUnicodeNormalization:

    def test_bom_stripped_accepted(self):
        """\ufeffSELECT 1 — BOM stripped → accepted."""
        result = validate_select_sql("\ufeffSELECT 1")
        assert result.wrap_applied is True
        assert result.wrapped_sql == "SELECT * FROM (SELECT 1) _limited LIMIT 1000"

    def test_cyrillic_select_rejected(self):
        """'ЅELECT 1' using Cyrillic Ѕ (U+0405) → NotSelectError.

        sqlparse tokenizes 'ЅELECT' as Token.Name (not DML SELECT), so the
        first-token check fails → NotSelectError.
        """
        with pytest.raises(NotSelectError):
            validate_select_sql("ЅELECT 1")


# ===========================================================================
# LIMIT logic
# ===========================================================================

class TestLimitLogic:

    def test_limit_within_cap_wrapped(self):
        """SELECT * FROM t LIMIT 50 — within cap → wrap applied."""
        result = validate_select_sql("SELECT * FROM t LIMIT 50")
        _assert_wrapped(result, "SELECT * FROM t LIMIT 50")

    def test_limit_exceeds_cap_rejected(self):
        """SELECT * FROM t LIMIT 5000 — exceeds cap 1000 → LimitExceededError."""
        with pytest.raises(LimitExceededError):
            validate_select_sql("SELECT * FROM t LIMIT 5000")

    def test_no_limit_wrapped(self):
        """SELECT * FROM t — no LIMIT → wrap applied."""
        result = validate_select_sql("SELECT * FROM t")
        _assert_wrapped(result, "SELECT * FROM t")

    def test_subquery_limit_accepted(self):
        """SELECT * FROM (SELECT * FROM t LIMIT 5) s — subquery LIMIT, not top-level → accept."""
        sql = "SELECT * FROM (SELECT * FROM t LIMIT 5) s"
        result = validate_select_sql(sql)
        assert result.wrap_applied is True

    def test_limit_with_offset_accepted(self):
        """SELECT * FROM t LIMIT 10 OFFSET 20 — within cap → accept."""
        result = validate_select_sql("SELECT * FROM t LIMIT 10 OFFSET 20")
        _assert_wrapped(result, "SELECT * FROM t LIMIT 10 OFFSET 20")

    def test_limit_exactly_cap_accepted(self):
        """SELECT * FROM t LIMIT 1000 — equal to cap → accept (not reject)."""
        result = validate_select_sql("SELECT * FROM t LIMIT 1000")
        assert result.wrap_applied is True

    def test_limit_1001_rejected(self):
        """SELECT * FROM t LIMIT 1001 — one over cap → LimitExceededError."""
        with pytest.raises(LimitExceededError):
            validate_select_sql("SELECT * FROM t LIMIT 1001")


# ===========================================================================
# Exception attributes
# ===========================================================================

class TestExceptionAttributes:

    def test_forbidden_keyword_error_has_keyword(self):
        try:
            validate_select_sql("DROP TABLE x")
        except ForbiddenKeywordError as e:
            assert e.keyword == "DROP"
            assert "DROP" in str(e)
        else:
            pytest.fail("ForbiddenKeywordError not raised")

    def test_forbidden_function_error_has_name(self):
        try:
            validate_select_sql("SELECT pg_sleep(5)")
        except ForbiddenFunctionError as e:
            assert e.name == "pg_sleep"
            assert "pg_sleep" in str(e)
        else:
            pytest.fail("ForbiddenFunctionError not raised")

    def test_too_long_error_message(self):
        try:
            validate_select_sql("x" * 9000)
        except TooLongError as e:
            assert "9000" in str(e)
        else:
            pytest.fail("TooLongError not raised")


# ===========================================================================
# Return type verification
# ===========================================================================

class TestReturnType:

    def test_returns_named_tuple(self):
        result = validate_select_sql("SELECT 1")
        assert isinstance(result, tuple)
        assert hasattr(result, "wrapped_sql")
        assert hasattr(result, "original_sql")
        assert hasattr(result, "wrap_applied")

    def test_wrap_format_exact(self):
        result = validate_select_sql("SELECT id FROM t")
        expected = "SELECT * FROM (SELECT id FROM t) _limited LIMIT 1000"
        assert result.wrapped_sql == expected
