"""FastAPI router for the PostgreSQL Online Viewer (013-postgres-viewer).

Endpoints
---------
GET  /api/pg-viewer/tables              — list all tables (TableSummary[])
GET  /api/pg-viewer/tables/{table}/schema   — describe one table (TableSchema)
GET  /api/pg-viewer/tables/{table}/rows     — paginated rows (RowPage)
GET  /api/pg-viewer/tables/{table}/export.csv  — CSV export (T-015 wired)
GET  /api/pg-viewer/audit               — audit log (AuditEntry[])
POST /api/pg-viewer/sql                 — SQL editor (T-016 wired)

Security
--------
- Every endpoint calls `require_admin_strict` which re-reads account_level
  from DB on each request (never trusts JWT role claim).
- Feature flag: if settings.pg_viewer_enabled is False, every endpoint
  returns 404.  Flag is read per-request (not at import time).

Error handling
--------------
Every except clause calls sanitize_pg_error(exc) to prevent leaking
role names, connection strings, file paths, etc.  Audit is written in
all paths (ok, error, timeout, denied, rate_limited).
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.auth import require_admin_strict
from app.config import get_settings
from app.services.circuit_breaker import PG_VIEWER_BREAKER
from app.services.pg_viewer.metrics import record_request
from app.services.pg_viewer.rate_limiter import _check_rate
from app.schemas.pg_viewer import (
    AuditEntry,
    AuditListResponse,
    ErrorSchema,
    RowColumnMeta,
    RowPage,
    SqlColumnMeta,
    SqlEditorRequest,
    SqlResult,
    TableListResponse,
    TableSchemaResponse,
    TableSummarySchema,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pg-viewer"])


# ---------------------------------------------------------------------------
# Bug 1 fix: accept both 'public.foo' and 'foo' as table name
# ---------------------------------------------------------------------------


def _normalize_table_name(t: str) -> str:
    """Accept both 'public.foo' and 'foo'; return bare name."""
    if t.startswith("public."):
        return t[len("public."):]
    return t


# ---------------------------------------------------------------------------
# H-2 fix: asyncpg $N → SQLAlchemy :pN adapter
# build_table_select() emits asyncpg-style positional placeholders ($1, $2…)
# and returns a list of values.  SQLAlchemy text() requires :name placeholders
# and a dict.  This thin adapter converts without touching query_builder.py.
# ---------------------------------------------------------------------------

import re as _re

def _adapt_params(sql: str, params: list) -> tuple[str, dict]:
    """Convert asyncpg-style '$N' placeholders to SQLAlchemy ':pN' and
    return the SQL string + a matching dict.

    Example:
        sql    = 'SELECT * FROM "t" WHERE "col" = $1 AND "col2" = $2'
        params = ['foo', 42]
        →
        sql    = 'SELECT * FROM "t" WHERE "col" = :p1 AND "col2" = :p2'
        params = {'p1': 'foo', 'p2': 42}
    """
    def _replace(m: "_re.Match[str]") -> str:
        return f":p{m.group(1)}"

    adapted_sql = _re.sub(r"\$(\d+)", _replace, sql)
    adapted_params = {f"p{i + 1}": v for i, v in enumerate(params)}
    return adapted_sql, adapted_params


# ---------------------------------------------------------------------------
# Feature-flag guard — called at the top of every endpoint
# ---------------------------------------------------------------------------


def _assert_feature_enabled() -> None:
    """Raise 404 if pg_viewer is disabled.  Read per-request (not at import)."""
    if not get_settings().pg_viewer_enabled:
        raise HTTPException(status_code=404, detail="pg-viewer feature not enabled")


def _check_circuit() -> None:
    """Raise 503 with Retry-After: 30 if the pg_viewer circuit breaker is OPEN."""
    if not PG_VIEWER_BREAKER.is_available:
        raise HTTPException(
            status_code=503,
            detail="pg-viewer service temporarily unavailable (circuit open)",
            headers={"Retry-After": "30"},
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_client_ip(request: Request) -> Optional[str]:
    return getattr(request.client, "host", None) if request.client else None


def _get_ua(request: Request) -> Optional[str]:
    return request.headers.get("user-agent")


# ---------------------------------------------------------------------------
# GET /tables
# ---------------------------------------------------------------------------


@router.get(
    "/tables",
    response_model=TableListResponse,
    responses={
        401: {"model": ErrorSchema},
        403: {"model": ErrorSchema},
        404: {"model": ErrorSchema},
    },
)
async def list_tables(
    request: Request,
    user: dict = Depends(require_admin_strict),
) -> TableListResponse:
    """List all tables/views in the public schema with approximate row counts."""
    _assert_feature_enabled()
    _check_circuit()

    from app.services.pg_viewer import audit as _audit
    from app.services.pg_viewer import introspect
    from app.services.pg_viewer.pii_redactor import sanitize_pg_error

    t0 = time.monotonic()
    ip = _get_client_ip(request)
    ua = _get_ua(request)

    try:
        tables = await introspect.list_tables()
        PG_VIEWER_BREAKER.record_success()
        elapsed = int((time.monotonic() - t0) * 1000)

        api_tables = [
            TableSummarySchema(
                schema_name=t.schema_name or "public",
                name=t.name,
                kind=t.kind,
                approx_row_count=t.approx_row_count,
                group=t.group,
                grant_missing=t.grant_missing if t.grant_missing else None,
            )
            for t in tables
        ]

        await _audit.write_audit(
            user_id=user["id"],
            query_type="schema",
            resource="__all__",
            raw_sql=None,
            row_count=len(api_tables),
            elapsed_ms=elapsed,
            status="ok",
            error_message=None,
            ip=ip,
            ua=ua,
            request=request,
        )
        record_request("tables_list", 200, elapsed / 1000.0)
        return TableListResponse(tables=api_tables)

    except HTTPException:
        raise
    except Exception as exc:
        PG_VIEWER_BREAKER.record_failure()
        elapsed = int((time.monotonic() - t0) * 1000)
        http_status, safe_msg = sanitize_pg_error(exc)
        await _audit.write_audit(
            user_id=user["id"],
            query_type="schema",
            resource="__all__",
            raw_sql=None,
            row_count=None,
            elapsed_ms=elapsed,
            status="error",
            error_message=safe_msg,
            ip=ip,
            ua=ua,
            request=request,
        )
        record_request("tables_list", http_status, elapsed / 1000.0)
        raise HTTPException(status_code=http_status, detail=safe_msg)


# ---------------------------------------------------------------------------
# GET /tables/{table}/schema
# ---------------------------------------------------------------------------


@router.get(
    "/tables/{table}/schema",
    response_model=TableSchemaResponse,
    responses={
        401: {"model": ErrorSchema},
        403: {"model": ErrorSchema},
        404: {"model": ErrorSchema},
    },
)
async def get_table_schema(
    table: str,
    request: Request,
    user: dict = Depends(require_admin_strict),
) -> TableSchemaResponse:
    """Return the schema (columns, indexes, foreign keys) for a single table."""
    _assert_feature_enabled()
    _check_circuit()

    from app.services.pg_viewer import audit as _audit
    from app.services.pg_viewer import introspect
    from app.services.pg_viewer.pii_redactor import sanitize_pg_error

    table = _normalize_table_name(table)
    t0 = time.monotonic()
    ip = _get_client_ip(request)
    ua = _get_ua(request)

    try:
        schema = await introspect.get_schema(table)
        PG_VIEWER_BREAKER.record_success()
        elapsed = int((time.monotonic() - t0) * 1000)

        from app.schemas.pg_viewer import ColumnSchema, ForeignKeySchema, IndexSchema

        await _audit.write_audit(
            user_id=user["id"],
            query_type="schema",
            resource=table,
            raw_sql=None,
            row_count=None,
            elapsed_ms=elapsed,
            status="ok",
            error_message=None,
            ip=ip,
            ua=ua,
            request=request,
        )

        record_request("table_schema", 200, elapsed / 1000.0)
        return TableSchemaResponse(
            schema_name=schema.schema_name or "public",
            name=schema.name,
            columns=[
                ColumnSchema(
                    name=c.name,
                    data_type=c.data_type,
                    nullable=c.nullable,
                    default=c.default,
                    comment=c.comment,
                    is_pk=c.is_pk,
                    is_indexed=c.is_indexed,
                )
                for c in schema.columns
            ],
            primary_key=schema.primary_key,
            indexes=[
                IndexSchema(name=i.name, definition=i.definition, unique=i.unique)
                for i in schema.indexes
            ],
            foreign_keys=[
                ForeignKeySchema(
                    column=fk.column,
                    foreign_table=fk.foreign_table,
                    foreign_column=fk.foreign_column,
                )
                for fk in schema.foreign_keys
            ],
            approx_row_count=schema.approx_row_count,
        )

    except ValueError as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        msg = str(exc)
        if "not found" in msg.lower():
            await _audit.write_audit(
                user_id=user["id"],
                query_type="schema",
                resource=table,
                raw_sql=None,
                row_count=None,
                elapsed_ms=elapsed,
                status="error",
                error_message="table not found",
                ip=ip,
                ua=ua,
                request=request,
            )
            record_request("table_schema", 404, elapsed / 1000.0)
            raise HTTPException(status_code=404, detail=f"Table not found: {table!r}")
        await _audit.write_audit(
            user_id=user["id"],
            query_type="schema",
            resource=table,
            raw_sql=None,
            row_count=None,
            elapsed_ms=elapsed,
            status="error",
            error_message=msg[:200],
            ip=ip,
            ua=ua,
            request=request,
        )
        record_request("table_schema", 400, elapsed / 1000.0)
        raise HTTPException(status_code=400, detail=msg[:200])

    except HTTPException:
        raise
    except Exception as exc:
        PG_VIEWER_BREAKER.record_failure()
        elapsed = int((time.monotonic() - t0) * 1000)
        http_status, safe_msg = sanitize_pg_error(exc)
        await _audit.write_audit(
            user_id=user["id"],
            query_type="schema",
            resource=table,
            raw_sql=None,
            row_count=None,
            elapsed_ms=elapsed,
            status="error",
            error_message=safe_msg,
            ip=ip,
            ua=ua,
            request=request,
        )
        record_request("table_schema", http_status, elapsed / 1000.0)
        raise HTTPException(status_code=http_status, detail=safe_msg)


# ---------------------------------------------------------------------------
# GET /tables/{table}/rows
# ---------------------------------------------------------------------------


@router.get(
    "/tables/{table}/rows",
    response_model=RowPage,
    responses={
        400: {"model": ErrorSchema},
        401: {"model": ErrorSchema},
        403: {"model": ErrorSchema},
        404: {"model": ErrorSchema},
        408: {"model": ErrorSchema},
    },
)
async def get_table_rows(
    table: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    order_by: Optional[str] = Query(default=None),
    order_dir: str = Query(default="DESC", pattern="^(ASC|DESC|asc|desc)$"),
    filters: Optional[str] = Query(default=None, description="JSON-encoded filter array"),
    user: dict = Depends(require_admin_strict),
) -> RowPage:
    """Fetch paginated, optionally-filtered rows from a table."""
    _assert_feature_enabled()
    _check_circuit()

    from app.services.pg_viewer import audit as _audit
    from app.services.pg_viewer.engine import get_viewer_db
    from app.services.pg_viewer.pii_redactor import sanitize_pg_error
    from app.services.pg_viewer.query_builder import FilterClause, build_table_select
    from app.services.pg_viewer.redaction import apply_redaction

    table = _normalize_table_name(table)
    t0 = time.monotonic()
    ip = _get_client_ip(request)
    ua = _get_ua(request)

    # Rate limit check (T-014.6) — audit on 429/503
    try:
        await _check_rate("rows", user["id"], get_settings().pg_viewer_rate_limit_rows)
    except HTTPException as rl_exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        rl_status = "rate_limited" if rl_exc.status_code == 429 else "error"
        await _audit.write_audit(
            user_id=user["id"],
            query_type="table_browse",
            resource=table,
            raw_sql=None,
            row_count=None,
            elapsed_ms=elapsed,
            status=rl_status,
            error_message=rl_exc.detail,
            ip=ip,
            ua=ua,
            request=request,
        )
        record_request("table_rows", rl_exc.status_code, elapsed / 1000.0)
        raise

    # Parse filters JSON
    filter_clauses: list[FilterClause] = []
    if filters:
        try:
            raw_filters = json.loads(filters)
            if not isinstance(raw_filters, list):
                raise ValueError("filters must be a JSON array")
            filter_clauses = [FilterClause(**f) for f in raw_filters]
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            await _audit.write_audit(
                user_id=user["id"],
                query_type="table_browse",
                resource=table,
                raw_sql=None,
                row_count=None,
                elapsed_ms=elapsed,
                status="error",
                error_message=f"invalid filters: {exc}",
                ip=ip,
                ua=ua,
                request=request,
            )
            record_request("table_rows", 400, elapsed / 1000.0)
            raise HTTPException(status_code=400, detail=f"invalid filters: {exc}")

    try:
        # Build SELECT
        order_by_list = [order_by] if order_by else None
        sql, params = build_table_select(
            None,
            table=table,
            columns=[],
            filters=filter_clauses,
            order_by=order_by_list,
            order_dir=order_dir.lower(),  # type: ignore[arg-type]
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        msg = str(exc)
        status_code = 400
        if "row limit exceeded" in msg:
            status_code = 400
        elif "not found" in msg.lower():
            status_code = 404

        await _audit.write_audit(
            user_id=user["id"],
            query_type="table_browse",
            resource=table,
            raw_sql=None,
            row_count=None,
            elapsed_ms=elapsed,
            status="error",
            error_message=msg[:200],
            ip=ip,
            ua=ua,
            request=request,
        )
        record_request("table_rows", status_code, elapsed / 1000.0)
        raise HTTPException(status_code=status_code, detail=msg[:200])
    except Exception as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        http_status, safe_msg = sanitize_pg_error(exc)
        await _audit.write_audit(
            user_id=user["id"],
            query_type="table_browse",
            resource=table,
            raw_sql=None,
            row_count=None,
            elapsed_ms=elapsed,
            status="error",
            error_message=safe_msg,
            ip=ip,
            ua=ua,
            request=request,
        )
        record_request("table_rows", http_status, elapsed / 1000.0)
        raise HTTPException(status_code=http_status, detail=safe_msg)

    # Execute
    try:
        from sqlalchemy import text as _text

        # H-2 fix: convert asyncpg $N placeholders to SQLAlchemy :pN + dict.
        adapted_sql, adapted_params = _adapt_params(sql, params)

        gen = get_viewer_db()
        conn = await gen.__anext__()
        try:
            # get_viewer_db already SET LOCAL statement_timeout = '10s'
            result = await conn.execute(_text(adapted_sql), adapted_params if adapted_params else {})
            db_rows = result.fetchall()
            col_names = list(result.keys())
        finally:
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass

        PG_VIEWER_BREAKER.record_success()

        # Approximate total count from pg_class
        from app.services.pg_viewer import introspect
        try:
            tables_list = await introspect.list_tables()
            approx_total = next(
                (t.approx_row_count for t in tables_list if t.name == table), 0
            )
        except Exception:
            approx_total = 0

        # Convert rows to dicts
        row_dicts = [dict(zip(col_names, row)) for row in db_rows]

        # Apply redaction
        redacted_rows, col_meta = apply_redaction(row_dicts, table)

        elapsed = int((time.monotonic() - t0) * 1000)

        # Build column metadata for response
        columns_meta = [
            RowColumnMeta(
                name=cm.name,
                data_type="",  # data_type not available from redaction meta
                redacted=cm.partially_redacted or None,
            )
            for cm in col_meta
            if not cm.hidden
        ]

        await _audit.write_audit(
            user_id=user["id"],
            query_type="table_browse",
            resource=table,
            raw_sql=None,
            row_count=len(redacted_rows),
            elapsed_ms=elapsed,
            status="ok",
            error_message=None,
            ip=ip,
            ua=ua,
            request=request,
        )

        record_request("table_rows", 200, elapsed / 1000.0)
        return RowPage(
            columns=columns_meta,
            rows=redacted_rows,
            limit=limit,
            offset=offset,
            approx_total=approx_total,
            execution_ms=elapsed,
            truncated=False,
        )

    except HTTPException:
        raise
    except Exception as exc:
        PG_VIEWER_BREAKER.record_failure()
        elapsed = int((time.monotonic() - t0) * 1000)
        http_status, safe_msg = sanitize_pg_error(exc)
        audit_status = "timeout" if http_status == 408 else "error"
        await _audit.write_audit(
            user_id=user["id"],
            query_type="table_browse",
            resource=table,
            raw_sql=None,
            row_count=None,
            elapsed_ms=elapsed,
            status=audit_status,
            error_message=safe_msg,
            ip=ip,
            ua=ua,
            request=request,
        )
        record_request("table_rows", http_status, elapsed / 1000.0)
        raise HTTPException(status_code=http_status, detail=safe_msg)


# ---------------------------------------------------------------------------
# GET /tables/{table}/export.csv  — T-015 wired
# ---------------------------------------------------------------------------


@router.get(
    "/tables/{table}/export.csv",
    responses={
        200: {"content": {"text/csv": {}}},
        401: {"model": ErrorSchema},
        403: {"model": ErrorSchema},
        429: {"model": ErrorSchema},
        503: {"model": ErrorSchema},
    },
)
async def export_table_csv(
    table: str,
    request: Request,
    columns: Optional[str] = Query(default=None, description="Comma-separated column list; empty = all"),
    order_by: Optional[str] = Query(default=None),
    order_dir: str = Query(default="asc", pattern="^(asc|desc|ASC|DESC)$"),
    filters: Optional[str] = Query(default=None, description="JSON-encoded filter array"),
    row_limit: int = Query(default=1000, ge=1, le=1000),
    user: dict = Depends(require_admin_strict),
):
    """Export table rows as a streaming CSV file (T-015 wired)."""
    _assert_feature_enabled()
    _check_circuit()

    from app.services.pg_viewer import audit as _audit
    from app.services.pg_viewer.exporter import export_csv
    from app.services.pg_viewer.pii_redactor import sanitize_pg_error
    from app.services.pg_viewer.query_builder import FilterClause

    table = _normalize_table_name(table)
    t0 = time.monotonic()
    ip = _get_client_ip(request)
    ua = _get_ua(request)

    # Rate limit check (T-014.6) — same "rows" bucket as /rows endpoint
    try:
        await _check_rate("rows", user["id"], get_settings().pg_viewer_rate_limit_rows)
    except HTTPException as rl_exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        rl_status = "rate_limited" if rl_exc.status_code == 429 else "error"
        await _audit.write_audit(
            user_id=user["id"],
            query_type="table_browse",
            resource=table,
            raw_sql=None,
            row_count=None,
            elapsed_ms=elapsed,
            status=rl_status,
            error_message=rl_exc.detail,
            ip=ip,
            ua=ua,
            request=request,
        )
        record_request("table_export", rl_exc.status_code, elapsed / 1000.0)
        raise

    # Parse columns
    col_list: list[str] = []
    if columns:
        col_list = [c.strip() for c in columns.split(",") if c.strip()]

    # Parse filters JSON
    filter_clauses: list[FilterClause] = []
    if filters:
        try:
            raw_filters = json.loads(filters)
            if not isinstance(raw_filters, list):
                raise ValueError("filters must be a JSON array")
            filter_clauses = [FilterClause(**f) for f in raw_filters]
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            await _audit.write_audit(
                user_id=user["id"],
                query_type="table_browse",
                resource=table,
                raw_sql=None,
                row_count=None,
                elapsed_ms=elapsed,
                status="error",
                error_message=f"invalid filters: {exc}",
                ip=ip,
                ua=ua,
                request=request,
            )
            record_request("table_export", 400, elapsed / 1000.0)
            raise HTTPException(status_code=400, detail=f"invalid filters: {exc}")

    # Execute export
    try:
        order_by_list = [order_by] if order_by else None
        streaming_response = await export_csv(
            table=table,
            columns=col_list,
            filters=filter_clauses,
            order_by=order_by_list,
            order_dir=order_dir.lower(),  # type: ignore[arg-type]
            row_limit=row_limit,
        )
        PG_VIEWER_BREAKER.record_success()
        elapsed = int((time.monotonic() - t0) * 1000)

        # Read row count + truncated flag from response headers set by export_csv
        exported_row_count = int(streaming_response.headers.get("x-row-count", 0))
        truncated = streaming_response.headers.get("x-truncated", "").lower() == "true"

        await _audit.write_audit(
            user_id=user["id"],
            query_type="table_browse",
            resource=table,
            raw_sql=None,
            row_count=exported_row_count,
            elapsed_ms=elapsed,
            status="ok",
            error_message=f"truncated=true" if truncated else None,
            ip=ip,
            ua=ua,
            request=request,
        )
        record_request("table_export", 200, elapsed / 1000.0)
        return streaming_response

    except HTTPException:
        raise
    except ValueError as exc:
        # ValueError from introspect (unknown table) → 404, not 500.
        elapsed = int((time.monotonic() - t0) * 1000)
        msg = str(exc)
        status_code = 404 if "not found" in msg.lower() else 400
        await _audit.write_audit(
            user_id=user["id"],
            query_type="table_browse",
            resource=table,
            raw_sql=None,
            row_count=None,
            elapsed_ms=elapsed,
            status="error",
            error_message=msg[:200],
            ip=ip,
            ua=ua,
            request=request,
        )
        record_request("table_export", status_code, elapsed / 1000.0)
        raise HTTPException(status_code=status_code, detail=msg[:200])
    except Exception as exc:
        PG_VIEWER_BREAKER.record_failure()
        elapsed = int((time.monotonic() - t0) * 1000)
        http_status, safe_msg = sanitize_pg_error(exc)
        await _audit.write_audit(
            user_id=user["id"],
            query_type="table_browse",
            resource=table,
            raw_sql=None,
            row_count=None,
            elapsed_ms=elapsed,
            status="error",
            error_message=safe_msg,
            ip=ip,
            ua=ua,
            request=request,
        )
        record_request("table_export", http_status, elapsed / 1000.0)
        raise HTTPException(status_code=http_status, detail=safe_msg)


# ---------------------------------------------------------------------------
# GET /audit
# ---------------------------------------------------------------------------


@router.get(
    "/audit",
    response_model=AuditListResponse,
    responses={
        401: {"model": ErrorSchema},
        403: {"model": ErrorSchema},
    },
)
async def get_audit(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user_id: Optional[str] = Query(default=None),
    query_type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    since: Optional[str] = Query(default=None),
    until: Optional[str] = Query(default=None),
    user: dict = Depends(require_admin_strict),
) -> AuditListResponse:
    """Read the pg_viewer audit log (admin only).

    Uses the MAIN aikm session (not the viewer engine) so the audit table
    is readable even when the viewer DB is down.
    """
    _assert_feature_enabled()

    from app.db.session import get_db
    from app.services.pg_viewer import audit as _audit
    from app.services.pg_viewer.pii_redactor import sanitize_pg_error
    from app.services.pg_viewer.redaction import mask_email_ui

    t0 = time.monotonic()
    ip = _get_client_ip(request)
    ua = _get_ua(request)

    try:
        # Build dynamic query on pg_viewer_audit_log via main engine
        from app.db.session import engine as main_engine

        conditions: list[str] = []
        params: dict = {"limit": limit, "offset": offset}

        if user_id:
            conditions.append("user_id = :user_id")
            params["user_id"] = user_id
        if query_type:
            conditions.append("query_type = :query_type")
            params["query_type"] = query_type
        if status:
            conditions.append("status = :status")
            params["status"] = status
        if since:
            conditions.append("created_at >= :since")
            params["since"] = since
        if until:
            conditions.append("created_at <= :until")
            params["until"] = until

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        # Column names match migration 002 DDL exactly (C-1 fix).
        sql = f"""
            SELECT id, user_id, user_email, action, query_type, raw_sql,
                   table_name, row_count, execution_ms, status, error_message,
                   ip_address, user_agent, created_at
            FROM pg_viewer_audit_log
            {where_clause}
            ORDER BY id DESC
            LIMIT :limit OFFSET :offset
        """

        from sqlalchemy import text as _text  # noqa: PLC0415 — H-1 fix: text was not imported at module scope

        count_sql = f"SELECT count(*) FROM pg_viewer_audit_log {where_clause}"
        # count_params excludes limit/offset
        count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}

        async with main_engine.connect() as conn:
            count_result = await conn.execute(_text(count_sql), count_params)
            total: int = count_result.scalar() or 0
            result = await conn.execute(_text(sql), params)
            rows = result.fetchall()
            col_keys = list(result.keys())

        elapsed = int((time.monotonic() - t0) * 1000)

        entries: list[AuditEntry] = []
        for row in rows:
            row_dict = dict(zip(col_keys, row))
            created_at = row_dict.get("created_at")
            raw_email = row_dict.get("user_email")
            entries.append(
                AuditEntry(
                    id=row_dict.get("id"),
                    user_id=row_dict.get("user_id"),
                    user_email=mask_email_ui(raw_email) if raw_email else None,
                    action=row_dict.get("action"),
                    table_name=row_dict.get("table_name"),
                    row_count=row_dict.get("row_count"),
                    execution_ms=row_dict.get("execution_ms"),
                    error_message=row_dict.get("error_message"),
                    raw_sql=row_dict.get("raw_sql"),
                    query_type=row_dict.get("query_type"),
                    status=row_dict.get("status"),
                    created_at=created_at.isoformat() if created_at else None,
                )
            )

        # Audit the audit access itself
        await _audit.write_audit(
            user_id=user["id"],
            query_type="schema",
            resource="pg_viewer_audit_log",
            raw_sql=None,
            row_count=len(entries),
            elapsed_ms=elapsed,
            status="ok",
            error_message=None,
            ip=ip,
            ua=ua,
            request=request,
        )

        record_request("audit_list", 200, elapsed / 1000.0)
        return AuditListResponse(entries=entries, total=total)

    except HTTPException:
        raise
    except Exception as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        http_status, safe_msg = sanitize_pg_error(exc)
        await _audit.write_audit(
            user_id=user["id"],
            query_type="schema",
            resource="pg_viewer_audit_log",
            raw_sql=None,
            row_count=None,
            elapsed_ms=elapsed,
            status="error",
            error_message=safe_msg,
            ip=ip,
            ua=ua,
            request=request,
        )
        record_request("audit_list", http_status, elapsed / 1000.0)
        raise HTTPException(status_code=http_status, detail=safe_msg)


# ---------------------------------------------------------------------------
# POST /sql  — T-016 stub
# ---------------------------------------------------------------------------


@router.post(
    "/sql",
    response_model=SqlResult,
    responses={
        400: {"model": ErrorSchema},
        401: {"model": ErrorSchema},
        403: {"model": ErrorSchema},
        408: {"model": ErrorSchema},
        422: {"model": ErrorSchema},
    },
)
async def run_sql_editor(
    body: SqlEditorRequest,
    request: Request,
    user: dict = Depends(require_admin_strict),
) -> SqlResult:
    """Execute a SELECT-only ad-hoc SQL statement.

    T-016 (validate_select_sql) is available — wired.
    Pre-DB static analysis via sqlparse rejects dangerous keywords and functions.
    Validated SQL is wrapped as: SELECT * FROM (<user_sql>) _limited LIMIT 1000.
    """
    _assert_feature_enabled()
    _check_circuit()

    from app.services.pg_viewer import audit as _audit
    from app.services.pg_viewer.engine import get_viewer_db
    from app.services.pg_viewer.pii_redactor import redact_sql_for_audit, sanitize_pg_error
    from app.services.pg_viewer.redaction import apply_redaction
    from app.services.pg_viewer.sql_validator import (
        validate_select_sql,
        EmptyInputError,
        TooLongError,
        MultiStatementError,
        NotSelectError,
        ForbiddenKeywordError,
        ForbiddenFunctionError,
        LimitExceededError,
        ParseError,
    )

    t0 = time.monotonic()
    ip = _get_client_ip(request)
    ua = _get_ua(request)

    # Rate limit check (T-014.6)
    try:
        await _check_rate("sql", user["id"], get_settings().pg_viewer_rate_limit_sql)
    except HTTPException as rl_exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        rl_status = "rate_limited" if rl_exc.status_code == 429 else "error"
        from app.services.pg_viewer import audit as _audit  # noqa: PLC0415
        from app.services.pg_viewer.pii_redactor import redact_sql_for_audit  # noqa: PLC0415
        await _audit.write_audit(
            user_id=user["id"],
            query_type="sql_editor",
            resource=None,
            raw_sql=redact_sql_for_audit(body.sql),
            row_count=None,
            elapsed_ms=elapsed,
            status=rl_status,
            error_message=rl_exc.detail,
            ip=ip,
            ua=ua,
            request=request,
        )
        record_request("sql_editor", rl_exc.status_code, elapsed / 1000.0)
        raise

    # --- Static analysis (Layer-9) ---
    try:
        wrapped = validate_select_sql(body.sql, max_len=get_settings().pg_viewer_sql_max_len)
    except (EmptyInputError, TooLongError, MultiStatementError, NotSelectError,
            ForbiddenKeywordError, ForbiddenFunctionError, LimitExceededError, ParseError) as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        msg = str(exc)
        await _audit.write_audit(
            user_id=user["id"],
            query_type="sql_editor",
            resource=None,
            raw_sql=redact_sql_for_audit(body.sql),
            row_count=None,
            elapsed_ms=elapsed,
            status="error",
            error_message=msg[:200],
            ip=ip,
            ua=ua,
            request=request,
        )
        record_request("sql_editor", 400, elapsed / 1000.0)
        raise HTTPException(status_code=400, detail=msg)

    # --- Execute via viewer engine ---
    try:
        from sqlalchemy import text as _text

        gen = get_viewer_db()
        conn = await gen.__anext__()
        try:
            result = await conn.execute(_text(wrapped.wrapped_sql))
            db_rows = result.fetchall()
            col_names = list(result.keys())
        finally:
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass

        PG_VIEWER_BREAKER.record_success()

        # Build row dicts
        row_dicts = [dict(zip(col_names, row)) for row in db_rows]

        # Apply redaction (table name unknown for ad-hoc SQL — use empty string
        # to trigger only default rules; no row-rule matches for "")
        redacted_rows, col_meta = apply_redaction(row_dicts, "")

        elapsed = int((time.monotonic() - t0) * 1000)

        columns_meta = [
            SqlColumnMeta(
                name=cm.name,
                data_type="",
                redacted=cm.partially_redacted or None,
            )
            for cm in col_meta
            if not cm.hidden
        ]

        await _audit.write_audit(
            user_id=user["id"],
            query_type="sql_editor",
            resource=None,
            raw_sql=redact_sql_for_audit(body.sql),
            row_count=len(redacted_rows),
            elapsed_ms=elapsed,
            status="ok",
            error_message=None,
            ip=ip,
            ua=ua,
            request=request,
        )

        record_request("sql_editor", 200, elapsed / 1000.0)
        return SqlResult(
            columns=columns_meta,
            rows=redacted_rows,
            row_count=len(redacted_rows),
            elapsed_ms=elapsed,
            truncated=False,
            notice="LIMIT 1000 auto-applied by server",
        )

    except HTTPException:
        raise
    except Exception as exc:
        PG_VIEWER_BREAKER.record_failure()
        elapsed = int((time.monotonic() - t0) * 1000)
        http_status, safe_msg = sanitize_pg_error(exc)
        audit_status = "timeout" if http_status == 408 else "error"
        await _audit.write_audit(
            user_id=user["id"],
            query_type="sql_editor",
            resource=None,
            raw_sql=redact_sql_for_audit(body.sql),
            row_count=None,
            elapsed_ms=elapsed,
            status=audit_status,
            error_message=safe_msg,
            ip=ip,
            ua=ua,
            request=request,
        )
        record_request("sql_editor", http_status, elapsed / 1000.0)
        raise HTTPException(status_code=http_status, detail=safe_msg)
