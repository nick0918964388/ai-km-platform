"""Query builder for pg_viewer SELECT statements (013-postgres-viewer).

Public API
----------
build_table_select(conn, *, table, columns, filters, order_by, order_dir,
                   limit, offset, pk_columns) -> tuple[str, list[Any]]
    Build a parameterised SELECT query string for asyncpg execution.

build_count_select(conn, *, table, filters) -> tuple[str, list[Any]]
    Build a parameterised SELECT count(*) query for asyncpg execution.

Security design
---------------
- Every identifier (table, column) is rendered via
  psycopg.sql.Identifier(name).as_string(None) — never via f-string or %
  formatting on user-supplied names.
- Every value is bound as asyncpg positional $N — never interpolated.
- psycopg.sql.Composed objects are NEVER passed to asyncpg; only rendered
  Python str values are embedded in the SQL text.
- Operator whitelist is enforced; unknown operators raise ValueError.
- Row limit and offset caps are enforced before any SQL is built.
- Column/table existence is validated via resolve_identifier() from T-011
  (introspect.py); unknown identifiers raise ValueError → 400 at router.
"""
from __future__ import annotations

import asyncio
from typing import Any, Literal

from pydantic import BaseModel

from app.config import get_settings

# ---------------------------------------------------------------------------
# Operator whitelist (FR-030)
# ---------------------------------------------------------------------------

_ALLOWED_OPS: frozenset[str] = frozenset(
    [
        "=",
        "!=",
        "<",
        "<=",
        ">",
        ">=",
        "LIKE",
        "ILIKE",
        "IN",
        "NOT IN",
        "IS NULL",
        "IS NOT NULL",
    ]
)

# Operators that bind no value (unary predicates)
_NULL_OPS: frozenset[str] = frozenset(["IS NULL", "IS NOT NULL"])

# Operators that bind a list of values (IN / NOT IN)
_LIST_OPS: frozenset[str] = frozenset(["IN", "NOT IN"])

# Offset safety cap — prevents pathological pagination
_OFFSET_CAP = 100_000


# ---------------------------------------------------------------------------
# FilterClause model
# ---------------------------------------------------------------------------

class FilterClause(BaseModel):
    """A single WHERE predicate.

    Fields
    ------
    column   : column name (validated via resolve_identifier before SQL build)
    op       : one of the 11 whitelisted operators (FR-030)
    value    : scalar, list (for IN/NOT IN), or None (for IS NULL/IS NOT NULL)
    wildcard : when True and op is LIKE/ILIKE, wraps value with %…%
    """

    column: str
    op: Literal[
        "=",
        "!=",
        "<",
        "<=",
        ">",
        ">=",
        "LIKE",
        "ILIKE",
        "IN",
        "NOT IN",
        "IS NULL",
        "IS NOT NULL",
    ]
    value: str | int | float | bool | list | None = None
    wildcard: bool = False


# ---------------------------------------------------------------------------
# psycopg Identifier bridge
# ---------------------------------------------------------------------------

def _ident(name: str) -> str:
    """Render an identifier as a properly ANSI-double-quoted string.

    Uses psycopg.sql.Identifier.as_string(None) which produces
    ANSI-compliant double-quote escaping without requiring a live connection
    (supported since psycopg v3.2).

    The result is a plain Python str such as '"users_public"' which is safe
    to embed directly in asyncpg query text.  Composed objects are NEVER
    returned or passed downstream.
    """
    from psycopg.sql import Identifier  # deferred for test-compat  # noqa: PLC0415

    result: str = Identifier(name).as_string(None)
    # Belt-and-suspenders: assert we always have a str, never Composed.
    assert isinstance(result, str), f"_ident must return str, got {type(result)}"
    return result


# ---------------------------------------------------------------------------
# Identifier validation helpers
# ---------------------------------------------------------------------------

def _validate_identifiers_sync(table: str, columns: list[str], filter_columns: list[str]) -> None:
    """Run async resolve_identifier for all identifiers, blocking via asyncio.

    Called synchronously from the build functions so callers (which may be
    sync or async at the router layer) don't need to be aware of the
    validation detail.

    Uses asyncio.run() to create a fresh event loop — compatible with Python
    3.10+ where get_event_loop() no longer auto-creates a loop in non-async
    contexts.  When called from inside a running event loop (e.g. FastAPI
    async handler), we fall back to a ThreadPoolExecutor to avoid nesting.
    """
    async def _validate_all() -> None:
        from app.services.pg_viewer.introspect import resolve_identifier  # noqa: PLC0415

        # Validate table
        await resolve_identifier(table)

        # Validate every requested output column
        for col in columns:
            await resolve_identifier(table, col)

        # Validate every filter column
        for col in filter_columns:
            await resolve_identifier(table, col)

    try:
        # Check if there's already a running loop (e.g. inside FastAPI)
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is not None and running_loop.is_running():
            # Inside async context: run in a worker thread to avoid nesting
            import concurrent.futures  # noqa: PLC0415
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(asyncio.run, _validate_all())
                future.result()
        else:
            # Synchronous context (tests, scripts): safe to use asyncio.run()
            asyncio.run(_validate_all())
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Identifier validation failed: {exc}") from exc


# ---------------------------------------------------------------------------
# WHERE clause builder
# ---------------------------------------------------------------------------

def _build_where(
    filters: list[FilterClause],
    param_start: int = 1,
) -> tuple[str, list[Any]]:
    """Build WHERE clause fragments and collect positional parameters.

    Parameters
    ----------
    filters     : validated FilterClause list
    param_start : first positional index ($N) to use; default 1

    Returns
    -------
    (where_sql, params)
        where_sql — SQL fragment starting with ' WHERE ...' or '' if no filters
        params    — list of values in $N order
    """
    if not filters:
        return ("", [])

    clauses: list[str] = []
    params: list[Any] = []
    idx = param_start

    for f in filters:
        col_ident = _ident(f.column)
        op = f.op

        if op not in _ALLOWED_OPS:
            raise ValueError(
                f"Operator {op!r} is not in the whitelist. "
                f"Allowed operators: {sorted(_ALLOWED_OPS)}"
            )

        if op in _NULL_OPS:
            # IS NULL / IS NOT NULL — no value bound
            clauses.append(f"{col_ident} {op}")

        elif op in _LIST_OPS:
            # IN / NOT IN — f.value must be a list
            if not isinstance(f.value, list) or len(f.value) == 0:
                raise ValueError(
                    f"Operator {op!r} requires a non-empty list value, "
                    f"got {f.value!r}"
                )
            placeholders = ", ".join(f"${idx + j}" for j in range(len(f.value)))
            clauses.append(f"{col_ident} {op} ({placeholders})")
            params.extend(f.value)
            idx += len(f.value)

        else:
            # Scalar value operators: =, !=, <, <=, >, >=, LIKE, ILIKE
            value = f.value
            if op in ("LIKE", "ILIKE") and f.wildcard:
                value = f"%{value}%"
            clauses.append(f"{col_ident} {op} ${idx}")
            params.append(value)
            idx += 1

    where_sql = " WHERE " + " AND ".join(clauses)
    return (where_sql, params)


# ---------------------------------------------------------------------------
# Public build functions
# ---------------------------------------------------------------------------

def build_table_select(
    conn: Any,  # psycopg Connection — accepted but not used; bridge uses None
    *,
    table: str,
    columns: list[str],
    filters: list[FilterClause],
    order_by: list[str] | None = None,
    order_dir: Literal["asc", "desc"] = "desc",
    limit: int,
    offset: int = 0,
    pk_columns: list[str] | None = None,
) -> tuple[str, list[Any]]:
    """Build a parameterised SELECT query for asyncpg .fetch(sql, *params).

    Parameters
    ----------
    conn        : psycopg Connection (accepted for API compatibility; identifier
                  rendering uses Identifier.as_string(None) per D-3 bridge rule)
    table       : target table name
    columns     : output columns; empty list → SELECT *
    filters     : WHERE predicates (operator-whitelisted; values bound as $N)
    order_by    : explicit ORDER BY columns; falls back to pk_columns if None
    order_dir   : 'asc' or 'desc' (applied to all ORDER BY columns)
    limit       : max rows; must not exceed settings.pg_viewer_row_limit (1000)
    offset      : skip first N rows; capped at 100,000
    pk_columns  : primary-key column list for default ORDER BY fallback

    Returns
    -------
    (sql_str, params_list)
        sql_str    — complete SELECT statement with $1, $2, … placeholders
        params_list — positional values matching the placeholders
    """
    settings = get_settings()
    row_limit = settings.pg_viewer_row_limit

    # --- Row limit cap ---
    if limit > row_limit:
        raise ValueError(f"row limit exceeded (max {row_limit})")

    # --- Offset cap ---
    if offset < 0:
        raise ValueError("offset must be non-negative")
    if offset > _OFFSET_CAP:
        raise ValueError(f"offset too large (max {_OFFSET_CAP})")

    # --- Operator whitelist check FIRST (before any async work) ---
    for f in filters:
        if f.op not in _ALLOWED_OPS:
            raise ValueError(
                f"Operator {f.op!r} not in whitelist. "
                f"Allowed: {sorted(_ALLOWED_OPS)}"
            )

    # --- Identifier validation via T-011 introspect ---
    filter_cols = [f.column for f in filters]
    _validate_identifiers_sync(table, columns, filter_cols)

    # Also validate explicit order_by columns
    if order_by:
        _validate_identifiers_sync(table, order_by, [])

    # --- Render identifiers (always via psycopg Identifier, never f-string) ---
    table_ident = _ident(table)

    if columns:
        col_list = ", ".join(_ident(c) for c in columns)
    else:
        col_list = "*"

    # --- WHERE clause ---
    where_sql, params = _build_where(filters, param_start=1)

    # --- ORDER BY ---
    order_dir_sql = order_dir.upper()  # "ASC" or "DESC"

    effective_order_cols: list[str] | None = order_by or pk_columns
    if effective_order_cols:
        order_parts = ", ".join(
            f"{_ident(c)} {order_dir_sql}" for c in effective_order_cols
        )
        order_sql = f" ORDER BY {order_parts}"
    else:
        order_sql = ""

    # --- LIMIT / OFFSET ---
    limit_sql = f" LIMIT {limit}"
    offset_sql = f" OFFSET {offset}"

    sql = (
        f"SELECT {col_list} FROM {table_ident}"
        f"{where_sql}"
        f"{order_sql}"
        f"{limit_sql}"
        f"{offset_sql}"
    )

    return (sql, params)


def build_count_select(
    conn: Any,  # psycopg Connection — accepted but not used
    *,
    table: str,
    filters: list[FilterClause],
) -> tuple[str, list[Any]]:
    """Build a parameterised SELECT count(*) query for asyncpg.

    Same identifier validation and operator whitelist as build_table_select.
    No LIMIT/OFFSET — count queries are always unbounded row-count.

    Returns
    -------
    (sql_str, params_list)
    """
    # Operator whitelist FIRST (before any async work)
    for f in filters:
        if f.op not in _ALLOWED_OPS:
            raise ValueError(
                f"Operator {f.op!r} not in whitelist. "
                f"Allowed: {sorted(_ALLOWED_OPS)}"
            )

    # Validate identifiers
    filter_cols = [f.column for f in filters]
    _validate_identifiers_sync(table, [], filter_cols)

    table_ident = _ident(table)
    where_sql, params = _build_where(filters, param_start=1)

    sql = f"SELECT count(*) FROM {table_ident}{where_sql}"
    return (sql, params)
