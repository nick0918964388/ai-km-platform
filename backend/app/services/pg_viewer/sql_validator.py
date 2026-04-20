"""SQL static-analysis validator for pg_viewer (Layer-9 pre-DB guard).

Pure function — no DB, no network, no filesystem I/O.
Requires: sqlparse>=0.4.4 (listed in requirements.txt).

Public API
----------
validate_select_sql(raw: str, *, max_len: int = 8000) -> WrappedSql

Always wraps the sanitized SQL:
    SELECT * FROM (<sanitized>) _limited LIMIT 1000

User-supplied top-level LIMIT > settings.PG_VIEWER_ROW_LIMIT → LimitExceededError (reject, not clamp).
"""
from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple

import sqlparse
import sqlparse.sql as sql_mod
import sqlparse.tokens as T


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------

class WrappedSql(NamedTuple):
    wrapped_sql: str       # "SELECT * FROM (<sanitized>) _limited LIMIT 1000"
    original_sql: str
    wrap_applied: bool


# ---------------------------------------------------------------------------
# Typed exception hierarchy
# ---------------------------------------------------------------------------

class EmptyInputError(ValueError):
    def __init__(self) -> None:
        super().__init__("SQL input is empty")


class TooLongError(ValueError):
    def __init__(self, length: int, max_len: int) -> None:
        super().__init__(f"SQL too long: {length} > {max_len}")


class MultiStatementError(ValueError):
    def __init__(self) -> None:
        super().__init__("multiple statements are not allowed")


class NotSelectError(ValueError):
    def __init__(self) -> None:
        super().__init__("only SELECT (or WITH … SELECT) statements are allowed")


class ForbiddenKeywordError(ValueError):
    def __init__(self, keyword: str) -> None:
        self.keyword = keyword
        super().__init__(f"forbidden keyword: {keyword}")


class ForbiddenFunctionError(ValueError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"forbidden function: {name}")


class LimitExceededError(ValueError):
    def __init__(self, limit: int, cap: int) -> None:
        super().__init__(f"row limit exceeded (server-side cap {cap}); got {limit}")


class ParseError(ValueError):
    def __init__(self, msg: str) -> None:
        super().__init__(f"SQL parse error: {msg}")


# ---------------------------------------------------------------------------
# Forbidden sets
# ---------------------------------------------------------------------------

_FORBIDDEN_KEYWORDS: frozenset[str] = frozenset({
    "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE",
    "GRANT", "REVOKE", "CREATE", "ALTER", "COPY",
    "CALL", "VACUUM", "ANALYZE", "REINDEX", "CLUSTER",
    "COMMENT", "LOCK", "SECURITY",
})

_FORBIDDEN_FUNCTIONS: frozenset[str] = frozenset({
    "dblink", "dblink_exec", "dblink_connect_u",
    "pg_read_file", "pg_read_server_files", "pg_ls_dir",
    "pg_stat_activity", "pg_sleep",
    "pg_terminate_backend", "pg_cancel_backend", "pg_reload_conf",
    "lo_import", "lo_export",
})

# Regex for scanning comment text for forbidden keywords (word-boundary match)
_FORBIDDEN_KW_IN_COMMENT_RE = re.compile(
    r"\b(" + "|".join(re.escape(kw) for kw in _FORBIDDEN_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_comment_token(ttype: T) -> bool:
    return ttype in (T.Comment.Single, T.Comment.Multiline)


def _walk_keywords(stmt: sqlparse.sql.Statement) -> str | None:
    """Walk all flattened tokens; return the first forbidden keyword name, or None.

    Also scans comment tokens for forbidden keyword text (catches SQL hidden
    inside comments like '-- DROP\\nSELECT 1' or '/*! DROP */ SELECT 1').

    Skips string literals (Token.Literal.*) so that
    ``SELECT 'DROP TABLE users' AS x`` is accepted.
    """
    for tok in stmt.flatten():
        ttype = tok.ttype

        # String literals are safe — skip entirely
        if ttype is not None and str(ttype).startswith("Token.Literal.String"):
            continue

        # Comment tokens: scan raw text for forbidden keywords
        if _is_comment_token(ttype):
            m = _FORBIDDEN_KW_IN_COMMENT_RE.search(tok.value)
            if m:
                return m.group(1).upper()
            continue

        # Keyword / DML / DDL / DCL tokens
        if ttype in (T.Keyword, T.Keyword.DML, T.Keyword.DDL, T.Keyword.DCL, T.Keyword.CTE):
            name = tok.normalized.upper()
            if name in _FORBIDDEN_KEYWORDS:
                return name

    return None


def _walk_functions(stmt: sqlparse.sql.Statement) -> str | None:
    """Walk tokens looking for forbidden function names.

    Two detection passes:
    1. sqlparse Function nodes → get_real_name() (e.g. pg_sleep(30))
    2. Flat Token.Name tokens → direct identifier (e.g. pg_stat_activity used
       as a table/view reference without parentheses)

    Returns the first matched name (lower-case), or None.
    """
    return _walk_functions_recursive(stmt.tokens)


def _walk_functions_recursive(tokens: list) -> str | None:
    for tok in tokens:
        if isinstance(tok, sql_mod.Function):
            fname = tok.get_real_name()
            if fname and fname.lower() in _FORBIDDEN_FUNCTIONS:
                return fname.lower()
            # Also descend inside the function arguments
            result = _walk_functions_recursive(tok.tokens)
            if result:
                return result
        elif hasattr(tok, "tokens"):
            result = _walk_functions_recursive(tok.tokens)
            if result:
                return result
        else:
            # Flat Token.Name — catches view/table references like pg_stat_activity
            if tok.ttype is T.Name and tok.value.lower() in _FORBIDDEN_FUNCTIONS:
                return tok.value.lower()
    return None


def _find_top_level_limit(stmt: sqlparse.sql.Statement) -> int | None:
    """Return the integer value of the top-level LIMIT clause, or None.

    Only inspects the direct token list of the statement (not nested
    parenthesised subqueries), so subquery LIMITs are ignored.
    """
    tokens = stmt.tokens
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        # Check for LIMIT keyword at the top level
        if tok.ttype is T.Keyword and tok.normalized.upper() == "LIMIT":
            # Scan forward for the integer value (skip whitespace)
            j = i + 1
            while j < len(tokens):
                ntok = tokens[j]
                if ntok.ttype in (T.Text.Whitespace, T.Text.Whitespace.Newline):
                    j += 1
                    continue
                if ntok.ttype is T.Literal.Number.Integer:
                    return int(ntok.value)
                # Non-whitespace non-integer — stop searching (e.g. LIMIT ALL)
                break
            break
        i += 1
    return None


# ---------------------------------------------------------------------------
# Public validator
# ---------------------------------------------------------------------------

def validate_select_sql(raw: str, *, max_len: int = 8000) -> WrappedSql:
    """Validate *raw* SQL and return a wrapped WrappedSql.

    Steps (Layer-9 static analysis):
    1. Pre-clean: strip BOM, .strip(), NFC-normalize unicode.
    2. Length check: > max_len → TooLongError; empty → EmptyInputError.
    3. Tolerate one trailing ';': strip it. Multiple statements → MultiStatementError.
    4. Parse with sqlparse: len(parsed) != 1 → MultiStatementError.
    5. psql meta-command check: Token.Generic.Command first token → ParseError.
    6. Statement type: first meaningful token must be SELECT or WITH → else NotSelectError.
    7. Keyword walker: check all tokens (inc. inside CTEs) for forbidden keywords.
       Also scans comment bodies for forbidden keyword text.
    8. Function walker: check Function nodes and Token.Name identifiers.
    9. Top-level LIMIT check: > PG_VIEWER_ROW_LIMIT → LimitExceededError.
    10. Wrap and return.

    Args:
        raw: User-supplied SQL string.
        max_len: Maximum allowed character length (default 8000).

    Returns:
        WrappedSql namedtuple with wrapped_sql, original_sql, wrap_applied=True.

    Raises:
        EmptyInputError: Input is empty or whitespace-only.
        TooLongError: Input exceeds max_len.
        MultiStatementError: More than one SQL statement detected.
        NotSelectError: Statement is not SELECT or WITH…SELECT.
        ForbiddenKeywordError: A forbidden keyword was found.
        ForbiddenFunctionError: A forbidden function was found.
        LimitExceededError: Top-level LIMIT exceeds PG_VIEWER_ROW_LIMIT.
        ParseError: SQL could not be parsed (e.g. psql meta-commands).
    """
    # --- Step 1: Pre-clean ---
    cleaned = raw
    # Strip BOM (U+FEFF)
    cleaned = cleaned.lstrip("\ufeff")
    # NFC normalize
    cleaned = unicodedata.normalize("NFC", cleaned)
    # Strip surrounding whitespace
    cleaned = cleaned.strip()

    # --- Step 2: Length / empty check ---
    if not cleaned:
        raise EmptyInputError()
    if len(cleaned) > max_len:
        raise TooLongError(len(cleaned), max_len)

    # --- Step 3: Tolerate one trailing ';' ---
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].rstrip()

    # --- Step 4: Parse ---
    parsed = sqlparse.parse(cleaned)
    if len(parsed) != 1:
        raise MultiStatementError()

    stmt = parsed[0]

    # --- Step 5: psql meta-command check ---
    # sqlparse assigns Token.Generic.Command to '\copy', '\set', etc.
    for tok in stmt.flatten():
        ttype = tok.ttype
        if ttype in (T.Text.Whitespace, T.Text.Whitespace.Newline,
                     T.Comment.Single, T.Comment.Multiline):
            continue
        if ttype is T.Generic.Command:
            raise ParseError(f"psql meta-command not allowed: {tok.value!r}")
        break  # only check first meaningful token for commands

    # --- Step 6: Keyword walker (before first-token check) ---
    # Run this BEFORE the SELECT/WITH check so that e.g. 'DROP TABLE users'
    # raises ForbiddenKeywordError (more informative) rather than NotSelectError.
    # Also scans comment bodies for forbidden keyword text.
    forbidden_kw = _walk_keywords(stmt)
    if forbidden_kw:
        raise ForbiddenKeywordError(forbidden_kw)

    # --- Step 7: Statement type ---
    # Valid: DML SELECT or CTE WITH (leading to SELECT).
    # Runs after keyword check so that write statements with a leading comment
    # (e.g. '/* note */ INSERT …') still get ForbiddenKeywordError, not
    # NotSelectError, when the actual keyword is in the denylist.
    first_meaningful = None
    for tok in stmt.flatten():
        ttype = tok.ttype
        if ttype in (T.Text.Whitespace, T.Text.Whitespace.Newline,
                     T.Comment.Single, T.Comment.Multiline):
            continue
        first_meaningful = tok
        break

    if first_meaningful is None:
        raise EmptyInputError()

    is_select = (
        first_meaningful.ttype is T.Keyword.DML
        and first_meaningful.normalized.upper() == "SELECT"
    )
    is_with = (
        first_meaningful.ttype is T.Keyword.CTE
        and first_meaningful.normalized.upper() == "WITH"
    )
    if not (is_select or is_with):
        raise NotSelectError()

    # --- Step 8: Function walker ---
    forbidden_fn = _walk_functions(stmt)
    if forbidden_fn:
        raise ForbiddenFunctionError(forbidden_fn)

    # --- Step 9: Top-level LIMIT check ---
    from app.config import get_settings  # deferred to avoid circular import in tests
    row_limit = get_settings().pg_viewer_row_limit

    top_limit = _find_top_level_limit(stmt)
    if top_limit is not None and top_limit > row_limit:
        raise LimitExceededError(top_limit, row_limit)

    # --- Step 10: Wrap ---
    wrapped = f"SELECT * FROM ({cleaned}) _limited LIMIT {row_limit}"

    return WrappedSql(
        wrapped_sql=wrapped,
        original_sql=raw,
        wrap_applied=True,
    )
