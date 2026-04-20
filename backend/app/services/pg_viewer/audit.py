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
    """Return (audit_table, spillover_table), creating them on first call.

    Column names MUST match the deployed migration 002 DDL exactly.
    Source of truth: backend/scripts/pg_viewer_migrate_002_audit_table.sql
    """
    global _audit_table, _spillover_table
    if _audit_table is not None:
        return _audit_table, _spillover_table

    from sqlalchemy import Column, Float, Integer, MetaData, String, Table, Text  # noqa: PLC0415

    _metadata = MetaData()

    # Column set aligned to migration 002 (post-critic C-1 fix).
    # id and created_at have server-side defaults — omitted from INSERT.
    _shared_columns = [
        Column("user_id", String),
        Column("user_email", String, nullable=True),
        Column("action", String),
        Column("query_type", String),
        Column("raw_sql", Text, nullable=True),
        Column("table_name", String, nullable=True),
        Column("filters_json", Text, nullable=True),       # JSONB stored as text
        Column("order_by", String, nullable=True),
        Column("order_dir", String, nullable=True),
        Column("limit_val", Integer, nullable=True),
        Column("offset_val", Integer, nullable=True),
        Column("row_count", Integer, nullable=True),
        Column("execution_ms", Float, nullable=True),
        Column("status", String),
        Column("error_message", Text, nullable=True),
        Column("ip_address", String, nullable=True),       # INET stored as text
        Column("user_agent", Text, nullable=True),
    ]

    _audit_table = Table(
        "pg_viewer_audit_log",
        _metadata,
        *_shared_columns,
    )

    _spillover_table = Table(
        "pg_viewer_audit_log_spillover",
        _metadata,
        *[c.copy() for c in _shared_columns],
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
    status: "Literal['ok', 'error', 'timeout', 'denied', 'rate_limited', 'forbidden']",
    error_message: "str | None",
    ip: "str | None",
    ua: "str | None",
    request: "fastapi.Request | None" = None,
    # Extended fields that map to migration 002 columns.
    # All are optional to keep existing call sites working unchanged.
    user_email: "str | None" = None,
    action: "str | None" = None,
    filters_json: "str | None" = None,
    order_by: "str | None" = None,
    order_dir: "str | None" = None,
    limit_val: "int | None" = None,
    offset_val: "int | None" = None,
    truncated: "bool | None" = None,
) -> None:
    """Write a row to ``pg_viewer_audit_log`` in an independent transaction.

    Column mapping (migration 002 source of truth):
    - ``resource``   → ``table_name``
    - ``elapsed_ms`` → ``execution_ms``
    - ``ip``         → ``ip_address``  (after XFF resolution)
    - ``ua``         → ``user_agent``  (after header resolution)
    - ``action``     → derived from ``query_type`` when not supplied explicitly

    External call-site signature is kept stable — existing callers that pass
    only the original parameters (resource, elapsed_ms, ip, ua) continue to
    work without changes.

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

    # --- Derive action from query_type when not explicitly provided ---
    # Mapping satisfies chk_action_query_type CHECK constraint in migration 002.
    if action is None:
        if query_type == "schema":
            action = "schema"
        elif query_type == "sql_editor":
            action = "sql_editor"
        else:
            # table_browse — pick a more specific sub-action based on context.
            if filters_json:
                action = "filter"
            elif safe_sql is None:
                action = "browse"
            else:
                action = "browse"

    # Normalise order_dir to uppercase (DB CHECK: 'ASC' or 'DESC' or NULL).
    norm_order_dir = order_dir.upper() if order_dir else None

    # --- Build the values dict once; reused for spillover if needed ---
    # Keys match migration 002 column names exactly.
    values: dict = {
        "user_id": user_id,
        "user_email": user_email,
        "action": action,
        "query_type": query_type,
        "raw_sql": safe_sql,
        "table_name": resource,            # resource → table_name
        "filters_json": filters_json,
        "order_by": order_by,
        "order_dir": norm_order_dir,
        "limit_val": limit_val,
        "offset_val": offset_val,
        "row_count": row_count if row_count is not None else 0,
        "execution_ms": float(elapsed_ms),  # elapsed_ms → execution_ms (REAL)
        "status": status,
        "error_message": safe_err,
        "ip_address": resolved_ip,         # ip → ip_address
        "user_agent": resolved_ua,          # ua → user_agent
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
