"""PII / secret redactor and PG error sanitizer for pg_viewer.

Two pure functions — no DB, no network, no filesystem I/O.
Only stdlib ``re`` is required at import time; asyncpg / SQLAlchemy exception
classes are imported lazily inside ``sanitize_pg_error`` so that unit tests
run without those packages installed.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_AUDIT_MAX_CHARS = 8000

# ---------------------------------------------------------------------------
# Compiled patterns for redact_sql_for_audit
# Each tuple: (compiled_pattern, replacement_string, use_group_replace)
# use_group_replace=True  → replace only the captured group 2 (literal value)
# use_group_replace=False → replace the entire match
# ---------------------------------------------------------------------------

# Pattern order matters — first match wins (applied sequentially via sub, not
# alternation, so each pattern runs independently in order).

_REDACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # GitHub legacy PAT  ghp_<36+ alphanum>
    (re.compile(r"ghp_[A-Za-z0-9]{36,}"), "[REDACTED_GHP]"),
    # GitHub fine-grained PAT  github_pat_<82+ alphanum/underscore>
    (re.compile(r"github_pat_[A-Za-z0-9_]{82,}"), "[REDACTED_GITHUB_PAT]"),
    # OpenAI / generic sk- key  sk-<20+ alphanum>
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "[REDACTED_SK]"),
    # HTTP Bearer token (case-insensitive)  Bearer <20+ safe chars>
    (
        re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}", re.IGNORECASE),
        "Bearer [REDACTED_BEARER]",
    ),
    # AWS access key ID  AKIA<16 uppercase alphanum>
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    # Loose hex ≥40 chars — only when NOT part of a longer hex run.
    # Uses a non-hex negative lookbehind/ahead so we don't split 80-char hashes
    # into multiple replacements.  Pattern is linear — no backtracking risk.
    (
        re.compile(r"(?<![A-Fa-f0-9])[A-Fa-f0-9]{40,}(?![A-Fa-f0-9])"),
        "[REDACTED_HEX40]",
    ),
]

# Sensitive-column literal pattern — replaces only the quoted value, not the
# column name.  Group 1 = column name, group 2 = literal value.
_SENSITIVE_LITERAL_RE = re.compile(
    r"\b(password|password_hash|token|api_key|secret|credential)\s*=\s*'([^']{0,2000})'",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Strip patterns for sanitize_pg_error
# ---------------------------------------------------------------------------

_ROLE_RE = re.compile(r'\brole\s+"[^"]{0,200}"', re.IGNORECASE)
_CONNSTR_RE = re.compile(r"postgres(?:ql)?://[^\s]{0,500}")
_FILEPATH_RE = re.compile(r"/[\w./\-]{1,500}\.(sql|py|log)")
_DETAIL_RE = re.compile(
    r"\b(DETAIL|HINT|CONTEXT)\s*:.*?(?=\n(?:DETAIL|HINT|CONTEXT|ERROR|WARNING)\s*:|$)",
    re.IGNORECASE | re.DOTALL,
)


def _strip_pg_internals(msg: str) -> str:
    """Remove role names, connection strings, file paths, DETAIL/HINT/CONTEXT lines."""
    msg = _ROLE_RE.sub("[role]", msg)
    msg = _CONNSTR_RE.sub("[dsn]", msg)
    msg = _FILEPATH_RE.sub("[path]", msg)
    # Remove DETAIL / HINT / CONTEXT blocks (multi-line)
    msg = re.sub(
        r"(\bDETAIL\b|\bHINT\b|\bCONTEXT\b)\s*:.*",
        "",
        msg,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return msg.strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def redact_sql_for_audit(sql: str) -> str:
    """Scrub obvious secrets from *sql* before writing to the audit log.

    Patterns are applied in order; each is independent (all patterns run, not
    first-match-stops). The sensitive-column literal pattern replaces only the
    quoted value. Result is truncated to 8 000 chars.

    Args:
        sql: Raw SQL string provided by the user.

    Returns:
        Redacted SQL string, at most 8 000 characters.
    """
    result = sql

    # Apply each secret pattern in order
    for pattern, replacement in _REDACT_PATTERNS:
        result = pattern.sub(replacement, result)

    # Redact literals adjacent to sensitive column names
    result = _SENSITIVE_LITERAL_RE.sub(r"\1 = '[REDACTED_LITERAL]'", result)

    # Truncate
    return result[:_AUDIT_MAX_CHARS]


def sanitize_pg_error(exc: Exception) -> tuple[int, str]:
    """Map a Postgres / asyncpg / SQLAlchemy exception to (http_status, safe_message).

    The returned *safe_message* contains NO role name, NO connection string,
    NO file path, NO DETAIL, NO HINT, NO CONTEXT sections.

    SQLSTATE mapping:
        57014 → 408  query timed out
        42P01 → 422  column/relation does not exist
        42703 → 422  column/relation does not exist
        42501 → 403  grant missing (role name stripped)
        53300 → 503  database busy
        22P02 → 422  invalid input value
        P0001 → 422  exc.args[0][:200] (user-raised — safe by convention)
        23514 → 422  constraint violated
        *     → 500  internal database error

    Args:
        exc: Any exception, typically from asyncpg or SQLAlchemy.

    Returns:
        Tuple of (http_status_code, safe_message_string).
    """
    sqlstate = _extract_sqlstate(exc)

    _SQLSTATE_MAP: dict[str, tuple[int, str]] = {
        "57014": (408, "query timed out after 10 seconds"),
        "42P01": (422, "column/relation does not exist"),
        "42703": (422, "column/relation does not exist"),
        "42501": (403, "grant missing: contact operator"),
        "53300": (503, "database busy"),
        "22P02": (422, "invalid input value"),
        "23514": (422, "constraint violated"),
    }

    if sqlstate == "P0001":
        # User-raised exception via PL/pgSQL RAISE — args[0] is the message
        # text written by the developer, considered safe for user-facing output.
        raw_msg = str(exc.args[0])[:200] if exc.args else "operation rejected"
        return (422, _strip_pg_internals(raw_msg))

    if sqlstate in _SQLSTATE_MAP:
        status, msg = _SQLSTATE_MAP[sqlstate]
        return (status, msg)

    # Unknown / unrecognised error — return generic message, no internals.
    return (500, "internal database error")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_sqlstate(exc: Exception) -> str | None:
    """Best-effort SQLSTATE extraction from asyncpg, SQLAlchemy, or raw exceptions.

    Returns a string like "42501" / "P0001", or None if not determinable.
    """
    # 1. asyncpg exceptions expose .sqlstate directly
    sqlstate = getattr(exc, "sqlstate", None)
    if sqlstate:
        return str(sqlstate)

    # 2. SQLAlchemy DBAPIError wraps asyncpg in .orig
    orig = getattr(exc, "orig", None)
    if orig is not None:
        sqlstate = getattr(orig, "sqlstate", None)
        if sqlstate:
            return str(sqlstate)

    # 3. Some wrappers expose .pgcode (psycopg2 compatibility)
    pgcode = getattr(exc, "pgcode", None)
    if pgcode:
        return str(pgcode)

    # 4. Last resort — scan the string representation for a SQLSTATE pattern.
    # SQLSTATE is 5 chars: uppercase letters + digits.  We only scan the first
    # 500 chars to prevent ReDoS on pathologically large exception messages.
    msg_head = str(exc)[:500]
    match = re.search(r"\b([0-9A-Z]{5})\b", msg_head)
    if match:
        candidate = match.group(1)
        # Only return if it looks like a known PG SQLSTATE prefix
        known_prefixes = {"42", "57", "53", "22", "23", "P0"}
        if any(candidate.startswith(p) for p in known_prefixes):
            return candidate

    return None
