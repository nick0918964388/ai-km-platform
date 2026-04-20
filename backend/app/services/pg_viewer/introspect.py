"""Introspection service for the pg_viewer feature (013-postgres-viewer).

Public API
----------
list_tables()
    Returns list[TableSummary] for every table/view in the public schema,
    including approximate row counts and a grant_missing flag.

get_schema(table)
    Returns TableSchema for a single table: ordered columns, ordered composite
    PK, indexes, foreign keys.

resolve_identifier(table, column=None)
    Validates that (table, optional column) exist in the whitelist derived from
    list_tables / get_schema.  Raises ValueError on unknown identifiers.
    Called by the T-012 query builder for every user-supplied identifier.

Caching
-------
Results are cached in a simple TTL dict keyed by function+args.  Default TTL is
5 minutes (300 s) to balance freshness against repeated info_schema queries.
The cache is process-level; an explicit invalidate_introspect_cache() call clears
it (used by tests and health checks).

Security notes
--------------
- Only reads information_schema / pg_catalog and issues LIMIT-0 probe SELECTs.
- Never returns raw user data.
- Table names used in probe SELECTs are double-quote escaped (safe: names come
  from information_schema.tables, not from user input).

Import strategy
---------------
All heavy imports (sqlalchemy, app.models.*) are deferred to function bodies so
this module is importable in environments where those packages are not installed
(e.g. running unit tests on the dev machine without a full Docker environment).
This mirrors the pattern established in engine.py.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    # Type-checker only — never executed at runtime.
    from app.models.pg_viewer_schemas import TableSchema, TableSummary

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Patchable DB session factory
#
# get_viewer_db is imported inside function bodies so the module is importable
# without sqlalchemy.  But to allow monkeypatching in tests we expose a
# module-level callable `_get_viewer_db` that forwards to the real function.
# Tests can replace introspect._get_viewer_db directly.
# ---------------------------------------------------------------------------

def _get_viewer_db():
    """Return the get_viewer_db async-generator factory.

    Deferred import keeps the module importable without sqlalchemy/asyncpg.
    Tests replace this module attribute directly to inject a fake generator.
    """
    from app.services.pg_viewer.engine import get_viewer_db  # noqa: PLC0415
    return get_viewer_db()


# ---------------------------------------------------------------------------
# TTL Cache — simple process-level dict, no third-party deps
# ---------------------------------------------------------------------------

_CACHE_TTL_SECONDS = 300  # 5 minutes

# Each entry: (timestamp_float, value)
_cache: dict[str, tuple[float, object]] = {}
_cache_lock = asyncio.Lock()


def _cache_get(key: str) -> object | None:
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.monotonic() - ts > _CACHE_TTL_SECONDS:
        del _cache[key]
        return None
    return value


def _cache_set(key: str, value: object) -> None:
    _cache[key] = (time.monotonic(), value)


def invalidate_introspect_cache() -> None:
    """Clear all cached introspection results.  Call from tests or admin endpoints."""
    _cache.clear()


# ---------------------------------------------------------------------------
# SQL query strings (plain strings — text() wrapper applied inside functions)
# ---------------------------------------------------------------------------

_LIST_TABLES_SQL_STR = """
    SELECT
        t.table_name,
        t.table_type,
        COALESCE(c.reltuples::bigint, 0) AS approx_row_count
    FROM information_schema.tables t
    LEFT JOIN pg_class c
           ON c.relname = t.table_name
          AND c.relnamespace = (
              SELECT oid FROM pg_namespace WHERE nspname = 'public'
          )
    WHERE t.table_schema = 'public'
    ORDER BY t.table_name
"""

_COLUMNS_SQL_STR = """
    SELECT
        c.column_name,
        c.data_type,
        c.is_nullable,
        c.column_default,
        pg_catalog.col_description(
            (
                SELECT oid FROM pg_class
                WHERE relname = :table AND relnamespace = (
                    SELECT oid FROM pg_namespace WHERE nspname = 'public'
                )
            ),
            c.ordinal_position
        ) AS comment,
        c.ordinal_position
    FROM information_schema.columns c
    WHERE c.table_schema = 'public'
      AND c.table_name  = :table
    ORDER BY c.ordinal_position
"""

_PK_SQL_STR = """
    SELECT kcu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
         ON  kcu.constraint_name  = tc.constraint_name
         AND kcu.table_schema     = tc.table_schema
         AND kcu.table_name       = tc.table_name
    WHERE tc.constraint_type = 'PRIMARY KEY'
      AND tc.table_schema    = 'public'
      AND tc.table_name      = :table
    ORDER BY kcu.ordinal_position
"""

_INDEXED_COLS_SQL_STR = """
    SELECT DISTINCT a.attname
    FROM pg_index i
    JOIN pg_class  c ON c.oid = i.indrelid
    JOIN pg_class  ic ON ic.oid = i.indexrelid
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey)
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relname = :table
      AND NOT i.indisprimary
"""

_INDEXES_SQL_STR = """
    SELECT
        i.relname       AS index_name,
        ix.indisunique  AS is_unique,
        pg_get_indexdef(ix.indexrelid) AS definition
    FROM pg_index ix
    JOIN pg_class t  ON t.oid  = ix.indrelid
    JOIN pg_class i  ON i.oid  = ix.indexrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'public'
      AND t.relname = :table
    ORDER BY i.relname
"""

_FK_SQL_STR = """
    SELECT
        kcu.column_name,
        ccu.table_name  AS foreign_table,
        ccu.column_name AS foreign_column
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
         ON kcu.constraint_name = tc.constraint_name
         AND kcu.table_schema   = tc.table_schema
    JOIN information_schema.constraint_column_usage ccu
         ON ccu.constraint_name = tc.constraint_name
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND tc.table_schema    = 'public'
      AND tc.table_name      = :table
    ORDER BY kcu.ordinal_position
"""

_APPROX_ROW_COUNT_SQL_STR = """
    SELECT COALESCE(reltuples::bigint, 0)
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relname = :table
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _table_kind(table_type: str) -> str:
    return "view" if table_type == "VIEW" else "table"


def _table_group(name: str) -> Optional[str]:
    """Derive a UI group prefix from the table name."""
    if name.startswith("maximo_"):
        return "maximo"
    if name.startswith("users") or name in ("sessions", "api_keys", "user_permissions"):
        return "users"
    return None


def _quote_ident(name: str) -> str:
    """Double-quote an identifier, escaping embedded double-quotes.

    Used only for probe SELECTs on names sourced from information_schema
    (i.e. already validated as existing table names in the public schema).
    """
    return '"' + name.replace('"', '""') + '"'


async def _probe_select(conn, table_name: str) -> bool:
    """Return True if aikm_viewer can SELECT from the table (LIMIT 0 — no data).

    Returns False if SQLSTATE 42501 (insufficient_privilege) is raised.
    Any other exception is re-raised.
    """
    from sqlalchemy import text  # noqa: PLC0415 — deferred for unit-test compat
    from sqlalchemy.exc import ProgrammingError  # noqa: PLC0415

    try:
        await conn.execute(
            text(f"SELECT 1 FROM {_quote_ident(table_name)} LIMIT 0")
        )
        return True
    except ProgrammingError as exc:
        pg_code = getattr(getattr(exc, "orig", None), "pgcode", None)
        err_str = str(exc).lower()
        if pg_code == "42501" or "42501" in err_str or "permission denied" in err_str:
            return False
        raise


# ---------------------------------------------------------------------------
# list_tables()
# ---------------------------------------------------------------------------

async def list_tables() -> list[TableSummary]:
    """Return a summary row for every table/view in the public schema.

    Results are cached for _CACHE_TTL_SECONDS seconds.
    """
    from sqlalchemy import text  # noqa: PLC0415
    from app.models.pg_viewer_schemas import TableSummary  # noqa: PLC0415

    cache_key = "list_tables"
    async with _cache_lock:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        result_rows: list[TableSummary] = []
        gen = _get_viewer_db()
        conn = await gen.__anext__()
        try:
            rows = (await conn.execute(text(_LIST_TABLES_SQL_STR))).fetchall()
            for row in rows:
                name: str = row[0]
                kind: str = _table_kind(row[1])
                approx: int = max(0, int(row[2]))
                can_select = await _probe_select(conn, name)
                result_rows.append(
                    TableSummary(
                        schema_name="public",
                        name=name,
                        kind=kind,
                        approx_row_count=approx,
                        group=_table_group(name),
                        grant_missing=not can_select,
                    )
                )
        finally:
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass

        _cache_set(cache_key, result_rows)
        return result_rows


# ---------------------------------------------------------------------------
# get_schema()
# ---------------------------------------------------------------------------

async def get_schema(table: str) -> TableSchema:
    """Return full schema for a single public-schema table/view.

    Results are cached for _CACHE_TTL_SECONDS seconds.
    Raises ValueError if the table does not exist in information_schema.
    """
    cache_key = f"get_schema:{table}"
    async with _cache_lock:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        schema_result = await _fetch_schema_uncached(table)
        _cache_set(cache_key, schema_result)
        return schema_result


async def _fetch_schema_uncached(table: str) -> TableSchema:
    """Internal: fetch schema from DB without touching cache."""
    from sqlalchemy import text  # noqa: PLC0415
    from app.models.pg_viewer_schemas import (  # noqa: PLC0415
        ColumnSummary,
        ForeignKeySummary,
        IndexSummary,
        TableSchema,
    )

    gen = _get_viewer_db()
    conn = await gen.__anext__()
    try:
        params = {"table": table}

        col_rows = (await conn.execute(text(_COLUMNS_SQL_STR), params)).fetchall()
        if not col_rows:
            raise ValueError(f"Table not found in public schema: {table!r}")

        pk_rows = (await conn.execute(text(_PK_SQL_STR), params)).fetchall()
        pk_set = {r[0] for r in pk_rows}
        pk_ordered = [r[0] for r in pk_rows]

        indexed_rows = (await conn.execute(text(_INDEXED_COLS_SQL_STR), params)).fetchall()
        indexed_set = {r[0] for r in indexed_rows}

        index_rows = (await conn.execute(text(_INDEXES_SQL_STR), params)).fetchall()
        fk_rows = (await conn.execute(text(_FK_SQL_STR), params)).fetchall()

        approx_row = (await conn.execute(text(_APPROX_ROW_COUNT_SQL_STR), params)).scalar()
        approx_count = max(0, int(approx_row or 0))

        columns = [
            ColumnSummary(
                name=r[0],
                data_type=r[1],
                nullable=(r[2] == "YES"),
                default=r[3],
                comment=r[4],
                is_pk=(r[0] in pk_set),
                is_indexed=(r[0] in indexed_set),
            )
            for r in col_rows
        ]

        indexes = [
            IndexSummary(name=r[0], unique=bool(r[1]), definition=r[2])
            for r in index_rows
        ]

        foreign_keys = [
            ForeignKeySummary(column=r[0], foreign_table=r[1], foreign_column=r[2])
            for r in fk_rows
        ]

        return TableSchema(
            schema_name="public",
            name=table,
            columns=columns,
            primary_key=pk_ordered,
            indexes=indexes,
            foreign_keys=foreign_keys,
            approx_row_count=approx_count,
        )
    finally:
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass


# ---------------------------------------------------------------------------
# resolve_identifier()
# ---------------------------------------------------------------------------

async def resolve_identifier(
    table: str,
    column: Optional[str] = None,
) -> tuple[str, Optional[str]]:
    """Validate that (table, optional column) exist in the public schema whitelist.

    The whitelist is derived from list_tables() (tables with grant_missing=False)
    and get_schema(table) column names.  Uses cache so repeated calls are cheap.

    Returns:
        (table, column) — validated identifiers, or (table, None) if column omitted.

    Raises:
        ValueError: if the table is not accessible (not in whitelist, or
                    grant_missing=True) or if the column does not exist.
    """
    tables = await list_tables()
    accessible = {t.name for t in tables if not t.grant_missing}
    if table not in accessible:
        raise ValueError(
            f"Unknown or inaccessible table: {table!r}. "
            "Table either does not exist or aikm_viewer lacks SELECT privilege."
        )

    if column is None:
        return (table, None)

    schema = await get_schema(table)
    known_cols = {c.name for c in schema.columns}
    if column not in known_cols:
        raise ValueError(
            f"Unknown column {column!r} on table {table!r}. "
            f"Known columns: {sorted(known_cols)}"
        )

    return (table, column)
