"""Audit writer for pg_viewer.

Writes rows to ``pg_viewer_audit_log`` (or spillover) using the MAIN aikm
async engine in a fully independent transaction.  The audit commit is
isolated from the outer request-handler transaction so it persists even
when the handler rolls back.

Security notes
--------------
* ``raw_sql`` and ``error_message`` are passed through ``redact_sql_for_audit``
  BEFORE they reach the INSERT so secrets never appear in the audit log.
* INSERTs use SQLAlchemy ``insert()`` with bind-parameters only.
  String concatenation of user input into SQL is FORBIDDEN.
* X-Forwarded-For is trusted ONLY when the direct peer IP is in the
  ``pg_viewer_trusted_proxy_ips`` allowlist (default: empty = never trust).
* On any audit failure the error is logged via ``sanitize_pg_error``
  (no role names, DSNs, or file paths) and the function returns None.
  The outer request handler is never disrupted by audit failures.

SQLAlchemy / asyncpg imports are deferred to function bodies so that this
module is importable in unit-test environments where those packages are not
installed.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import fastapi
    from sqlalchemy import Table

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level table singletons — built lazily on first use.
# This avoids importing sqlalchemy at module load time so that the module is
# importable in test environments that don't have sqlalchemy installed.
# ---------------------------------------------------------------------------

_audit_table: "Table | None" = None
_spillover_table: "Table | None" = None


def _get_tables():
    """Return (audit_table, spillover_table), creating them on first call."""
    global _audit_table, _spillover_table
    if _audit_table is not None:
        return _audit_table, _spillover_table

    from sqlalchemy import Column, Integer, MetaData, String, Table, Text  # noqa: PLC0415

    _metadata = MetaData()

    _audit_table = Table(
        "pg_viewer_audit_log",
        _metadata,
        Column("user_id", String),
        Column("query_type", String),
        Column("resource", String, nullable=True),
        Column("raw_sql", Text, nullable=True),
        Column("row_count", Integer, nullable=True),
        Column("elapsed_ms", Integer),
        Column("status", String),
        Column("error_message", Text, nullable=True),
        Column("ip", String, nullable=True),
        Column("ua", Text, nullable=True),
        # logged_at has a server-side DEFAULT NOW() — omitted from INSERT.
    )

    _spillover_table = Table(
        "pg_viewer_audit_log_spillover",
        _metadata,
        Column("user_id", String),
        Column("query_type", String),
        Column("resource", String, nullable=True),
        Column("raw_sql", Text, nullable=True),
        Column("row_count", Integer, nullable=True),
        Column("elapsed_ms", Integer),
        Column("status", String),
        Column("error_message", Text, nullable=True),
        Column("ip", String, nullable=True),
        Column("ua", Text, nullable=True),
    )

    return _audit_table, _spillover_table


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_ip(
    ip: "str | None",
    ua: "str | None",
    request: "fastapi.Request | None",
) -> "tuple[str | None, str | None]":
    """Return (resolved_ip, resolved_ua) applying XFF trust logic.

    XFF is trusted only when ``request.client.host`` appears in the
    ``pg_viewer_trusted_proxy_ips`` allowlist.  Default allowlist is empty
    (never trust).  This prevents a remote attacker from spoofing their IP by
    setting the X-Forwarded-For header directly.
    """
    if request is None:
        return ip, ua

    # Resolve UA from request if not provided explicitly.
    if ua is None:
        ua = request.headers.get("user-agent")

    # Resolve IP — check XFF trust gate.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        from app.config import get_settings  # noqa: PLC0415

        trusted: list[str] = get_settings().pg_viewer_trusted_proxy_ips
        peer = getattr(request.client, "host", None) if request.client else None
        if peer and peer in trusted:
            # Take only the first IP from a comma-separated XFF header.
            resolved = xff.split(",")[0].strip()
            return resolved, ua
        # Peer not in allowlist — use the direct peer IP (not the XFF value).
        if peer:
            return peer, ua

    # No XFF or not trusted — use request.client.host if available, else
    # fall through to whatever the caller passed as ``ip``.
    peer = getattr(request.client, "host", None) if request.client else None
    return peer or ip, ua


def _get_sqlstate(exc: Exception) -> "str | None":
    """Extract SQLSTATE from a SQLAlchemy IntegrityError (or similar).

    SQLAlchemy wraps asyncpg in ``exc.orig``; asyncpg exposes ``.sqlstate``.
    Falls back to ``exc.pgcode`` (psycopg2 compat) and a regex scan.
    """
    import re  # noqa: PLC0415 — stdlib, deferred for clarity

    orig = getattr(exc, "orig", None)
    if orig is not None:
        sqlstate = getattr(orig, "sqlstate", None)
        if sqlstate:
            return str(sqlstate)

    pgcode = getattr(exc, "pgcode", None)
    if pgcode:
        return str(pgcode)

    # Last resort: scan the first 200 chars of the str representation.
    head = str(exc)[:200]
    m = re.search(r"\b([0-9A-Z]{5})\b", head)
    if m:
        return m.group(1)

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def write_audit(
    *,
    user_id: str,
    query_type: "Literal['table_browse', 'schema', 'sql_editor']",
    resource: "str | None",
    raw_sql: "str | None",
    row_count: "int | None",
    elapsed_ms: int,
    status: "Literal['ok', 'error', 'timeout', 'denied', 'rate_limited']",
    error_message: "str | None",
    ip: "str | None",
    ua: "str | None",
    request: "fastapi.Request | None" = None,
) -> None:
    """Write a row to ``pg_viewer_audit_log`` in an independent transaction.

    - Uses the main aikm async engine (NOT the viewer engine).
    - Opens a NEW connection/transaction, INSERTs via ``sqlalchemy.insert()``,
      commits, closes.  The outer request-handler transaction is unaffected.
    - On SQLSTATE 23514 (check violation = partition miss), retries against
      ``pg_viewer_audit_log_spillover`` and emits ``logger.warning``.
    - Any other exception is logged via ``sanitize_pg_error`` (no internals)
      and silently swallowed.  The outer request handler MUST NOT crash if
      audit fails.
    - PII redaction: ``raw_sql`` and ``error_message`` are passed through
      ``redact_sql_for_audit()`` BEFORE the INSERT.
    - ``raw_sql`` / ``error_message`` are NEVER concatenated into SQL strings.
    """
    # Deferred imports keep the module importable in unit-test environments
    # that lack SQLAlchemy / asyncpg.
    from sqlalchemy import insert  # noqa: PLC0415
    from sqlalchemy.exc import IntegrityError  # noqa: PLC0415

    from app.db.session import engine as main_engine  # noqa: PLC0415
    from app.services.pg_viewer.pii_redactor import (  # noqa: PLC0415
        redact_sql_for_audit,
        sanitize_pg_error,
    )

    audit_table, spillover_table = _get_tables()

    # --- XFF / UA resolution ---
    resolved_ip, resolved_ua = _resolve_ip(ip, ua, request)

    # --- PII redaction (must happen BEFORE the values dict is built) ---
    safe_sql: "str | None" = redact_sql_for_audit(raw_sql) if raw_sql is not None else None
    safe_err: "str | None" = (
        redact_sql_for_audit(error_message) if error_message is not None else None
    )

    # --- Build the values dict once; reused for spillover if needed ---
    values: dict = {
        "user_id": user_id,
        "query_type": query_type,
        "resource": resource,
        "raw_sql": safe_sql,
        "row_count": row_count,
        "elapsed_ms": elapsed_ms,
        "status": status,
        "error_message": safe_err,
        "ip": resolved_ip,
        "ua": resolved_ua,
    }

    # --- Independent transaction via main engine ---
    try:
        async with main_engine.begin() as conn:
            primary_stmt = insert(audit_table).values(**values)
            try:
                await conn.execute(primary_stmt)
            except IntegrityError as integrity_exc:
                sqlstate = _get_sqlstate(integrity_exc)
                if sqlstate == "23514":
                    # Partition miss — target row falls outside all defined
                    # partition ranges.  Write to the spillover table instead.
                    spillover_stmt = insert(spillover_table).values(**values)
                    await conn.execute(spillover_stmt)
                    logger.warning(
                        "pg_viewer audit partition miss — wrote to spillover",
                        extra={
                            "user_id": user_id,
                            "query_type": query_type,
                            "status": status,
                        },
                    )
                else:
                    raise
    except Exception as exc:
        # Sanitize before logging — must not leak role names, DSNs, or paths.
        _, safe_msg = sanitize_pg_error(exc)
        logger.error(
            "pg_viewer audit write failed: %s",
            safe_msg,
            extra={
                "user_id": user_id,
                "query_type": query_type,
                "status": status,
            },
        )
        # INTENTIONALLY no re-raise — audit failures MUST NOT surface to callers.
