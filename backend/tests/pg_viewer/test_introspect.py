"""Unit / integration tests for backend/app/services/pg_viewer/introspect.py.

Test strategy
-------------
- Pure-unit tests (no DB): mock get_viewer_db to inject fake rows; these always
  run and prove the logic layer independently of the database.
- Integration tests: require PG_VIEWER_DATABASE_URL and a live Postgres instance
  with Migration 001 applied (aikm_viewer role, users_public view, user_permissions
  composite-PK table).  Skipped automatically when the env var is absent.

Run unit tests only::

    pytest backend/tests/pg_viewer/test_introspect.py -v -k "not integration"

Run all (requires live DB)::

    PG_VIEWER_DATABASE_URL=... pytest backend/tests/pg_viewer/test_introspect.py -v

Import strategy
---------------
app.models.__init__ re-exports SQLAlchemy ORM models, which requires sqlalchemy
installed.  On a dev machine without full Docker deps, importing via that package
init would fail.  We bypass this by importing pg_viewer_schemas directly using
importlib, and by importing introspect directly (which defers its own heavy deps).
The pg_viewer __init__.py guard also runs at import time — we set JWT_SECRET before
any import to satisfy it.
"""
from __future__ import annotations

import importlib
import os
import sys
import types

# The pg_viewer __init__.py guard runs _assert_jwt_secret_safe() at import time.
# Set a real-looking secret BEFORE importing anything from app.services.pg_viewer
# so the guard does not raise in unit-test environments where JWT_SECRET is absent.
if not os.getenv("JWT_SECRET") or os.getenv("JWT_SECRET") == "aikm-secret-key-change-in-production":
    os.environ["JWT_SECRET"] = "a" * 64  # 64-char hex — passes the guard

# ---------------------------------------------------------------------------
# SQLAlchemy stub — injected when sqlalchemy is not installed on the dev machine.
#
# introspect.py defers `from sqlalchemy import text` / `from sqlalchemy.exc import
# ProgrammingError` to function bodies.  Those imports still run when the function
# executes; stub them out so unit tests work without the real package.
# ---------------------------------------------------------------------------
try:
    import sqlalchemy  # noqa: F401 — real package available (Docker / CI)
    _SQLALCHEMY_AVAILABLE = True
except ImportError:
    _SQLALCHEMY_AVAILABLE = False
    # Build a minimal sqlalchemy stub so that deferred `from sqlalchemy import text`
    # and `from sqlalchemy.exc import ProgrammingError` inside introspect.py succeed.
    # We use __path__ = [] to mark it as a package so sub-module imports work.
    _sa = types.ModuleType("sqlalchemy")
    _sa.__path__ = []
    _sa.__package__ = "sqlalchemy"
    _sa.text = lambda s: s  # text(sql_str) → returns sql_str unchanged (mocked conn ignores it)
    sys.modules.setdefault("sqlalchemy", _sa)

    _sa_exc = types.ModuleType("sqlalchemy.exc")
    _sa_exc.__package__ = "sqlalchemy"

    class _ProgrammingError(Exception):
        def __init__(self, statement=None, params=None, orig=None, **kw):
            super().__init__(statement)
            self.orig = orig

    _sa_exc.ProgrammingError = _ProgrammingError
    sys.modules.setdefault("sqlalchemy.exc", _sa_exc)
    _sa.exc = _sa_exc

from unittest.mock import AsyncMock, MagicMock

import pytest

_PG_URL = os.getenv("PG_VIEWER_DATABASE_URL", "")


def _import_pg_viewer_schemas():
    """Import pg_viewer_schemas directly, bypassing app.models.__init__.

    app.models.__init__ re-exports SQLAlchemy ORM models which require sqlalchemy.
    pg_viewer_schemas.py itself only needs pydantic (available on dev machine).

    Pre-registers the module in sys.modules so that later deferred imports inside
    introspect.py (`from app.models.pg_viewer_schemas import ...`) find it in the
    cache and never trigger app.models.__init__.
    """
    mod_name = "app.models.pg_viewer_schemas"
    if mod_name in sys.modules:
        return sys.modules[mod_name]

    import pathlib
    # backend/ is in sys.path (set by conftest.py)
    for path_entry in sys.path:
        candidate = pathlib.Path(path_entry) / "app" / "models" / "pg_viewer_schemas.py"
        if candidate.exists():
            spec = importlib.util.spec_from_file_location(mod_name, str(candidate))
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            return mod
    raise ImportError("Cannot locate app/models/pg_viewer_schemas.py")


# Pre-register pg_viewer_schemas in sys.modules NOW so that any later deferred
# `from app.models.pg_viewer_schemas import ...` calls (inside introspect.py
# function bodies) find it immediately without traversing app.models.__init__.
_import_pg_viewer_schemas()


def _import_introspect():
    """Import introspect module directly, bypassing app.services.pg_viewer.__init__.

    The pg_viewer __init__.py runs _assert_jwt_secret_safe() at import time.
    We bypass this by importing the module file directly.
    """
    mod_name = "app.services.pg_viewer.introspect"
    if mod_name in sys.modules:
        return sys.modules[mod_name]

    import pathlib
    for path_entry in sys.path:
        candidate = pathlib.Path(path_entry) / "app" / "services" / "pg_viewer" / "introspect.py"
        if candidate.exists():
            spec = importlib.util.spec_from_file_location(mod_name, str(candidate))
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            return mod
    raise ImportError("Cannot locate app/services/pg_viewer/introspect.py")


# ---------------------------------------------------------------------------
# Helpers — fake AsyncConnection + fake async generator
# ---------------------------------------------------------------------------

def _make_fake_conn(query_map: dict) -> AsyncMock:
    """Build an AsyncMock connection whose execute() dispatches by SQL substring."""
    conn = AsyncMock()

    async def _execute(stmt, params=None):
        sql = str(stmt).lower() if not isinstance(stmt, str) else stmt.lower()
        for key, rows in query_map.items():
            if key.lower() in sql:
                result = MagicMock()
                result.fetchall.return_value = rows
                result.scalar.return_value = rows[0] if rows else 0
                return result
        result = MagicMock()
        result.fetchall.return_value = []
        result.scalar.return_value = 0
        return result

    conn.execute = _execute
    return conn


def _make_gen_factory(conn: AsyncMock):
    """Return a no-arg callable that yields conn as an async generator."""
    async def _gen():
        yield conn
    return _gen


# ---------------------------------------------------------------------------
# Unit tests — list_tables()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tables_basic(monkeypatch):
    """list_tables() returns TableSummary objects for each row in info_schema."""
    introspect = _import_introspect()
    introspect.invalidate_introspect_cache()

    fake_rows = [
        ("maximo_mxwo", "BASE TABLE", 10742),
        ("users_public", "VIEW", 5),
    ]
    conn = _make_fake_conn({"information_schema.tables": fake_rows})

    monkeypatch.setattr(introspect, "_probe_select", AsyncMock(return_value=True))
    monkeypatch.setattr(introspect, "_get_viewer_db", _make_gen_factory(conn))

    result = await introspect.list_tables()

    names = [t.name for t in result]
    assert "maximo_mxwo" in names
    assert "users_public" in names

    for t in result:
        assert t.schema_name == "public"
        assert not t.grant_missing

    maximo = next(t for t in result if t.name == "maximo_mxwo")
    assert maximo.group == "maximo"
    assert maximo.approx_row_count == 10742

    users_pub = next(t for t in result if t.name == "users_public")
    assert users_pub.kind == "view"


@pytest.mark.asyncio
async def test_list_tables_grant_missing(monkeypatch):
    """list_tables() sets grant_missing=True for tables that raise 42501 on probe."""
    introspect = _import_introspect()
    introspect.invalidate_introspect_cache()

    fake_info_rows = [
        ("hidden_secrets", "BASE TABLE", 0),
        ("users_public", "VIEW", 3),
    ]
    conn = _make_fake_conn({"information_schema.tables": fake_info_rows})

    async def _probe_side_effect(conn, table_name):
        return table_name != "hidden_secrets"

    monkeypatch.setattr(introspect, "_probe_select", _probe_side_effect)
    monkeypatch.setattr(introspect, "_get_viewer_db", _make_gen_factory(conn))

    result = await introspect.list_tables()

    hidden = next(t for t in result if t.name == "hidden_secrets")
    assert hidden.grant_missing is True

    visible = next(t for t in result if t.name == "users_public")
    assert visible.grant_missing is False


# ---------------------------------------------------------------------------
# Unit tests — get_schema()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_schema_composite_pk(monkeypatch):
    """get_schema() returns primary_key=['user_id','section'] in ordinal order."""
    introspect = _import_introspect()
    introspect.invalidate_introspect_cache()

    col_rows = [
        ("user_id", "character varying", "NO", None, None, 1),
        ("section", "character varying", "NO", None, None, 2),
        ("can_read", "boolean", "YES", "true", None, 3),
    ]
    pk_rows = [("user_id",), ("section",)]

    async def _execute(stmt, params=None):
        sql = str(stmt).lower() if not isinstance(stmt, str) else stmt.lower()
        result = MagicMock()
        if "information_schema.columns" in sql:
            result.fetchall.return_value = col_rows
        elif "constraint_type = 'primary key'" in sql:
            result.fetchall.return_value = pk_rows
        elif "not i.indisprimary" in sql:
            result.fetchall.return_value = []
        elif "pg_get_indexdef" in sql:
            result.fetchall.return_value = []
        elif "constraint_type = 'foreign key'" in sql:
            result.fetchall.return_value = []
        elif "reltuples" in sql:
            result.scalar.return_value = 0
            result.fetchall.return_value = [(0,)]
        else:
            result.fetchall.return_value = []
            result.scalar.return_value = 0
        return result

    conn = AsyncMock()
    conn.execute = _execute

    monkeypatch.setattr(introspect, "_get_viewer_db", _make_gen_factory(conn))

    schema = await introspect.get_schema("user_permissions")

    assert schema.name == "user_permissions"
    assert schema.primary_key == ["user_id", "section"], (
        f"Expected ['user_id','section'] but got {schema.primary_key}"
    )
    col_names = [c.name for c in schema.columns]
    assert col_names == ["user_id", "section", "can_read"]

    pk_cols = [c for c in schema.columns if c.is_pk]
    assert {c.name for c in pk_cols} == {"user_id", "section"}


@pytest.mark.asyncio
async def test_get_schema_unknown_table(monkeypatch):
    """get_schema() raises ValueError for a table not in information_schema."""
    introspect = _import_introspect()
    introspect.invalidate_introspect_cache()

    async def _execute(stmt, params=None):
        result = MagicMock()
        result.fetchall.return_value = []
        result.scalar.return_value = 0
        return result

    conn = AsyncMock()
    conn.execute = _execute

    monkeypatch.setattr(introspect, "_get_viewer_db", _make_gen_factory(conn))

    with pytest.raises(ValueError, match="not found in public schema"):
        await introspect.get_schema("totally_unknown_table")


# ---------------------------------------------------------------------------
# Unit tests — resolve_identifier()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_identifier_valid(monkeypatch):
    """resolve_identifier('users_public', 'email') returns ('users_public', 'email')."""
    schemas = _import_pg_viewer_schemas()
    introspect = _import_introspect()
    introspect.invalidate_introspect_cache()

    TableSummary = schemas.TableSummary
    ColumnSummary = schemas.ColumnSummary
    TableSchema = schemas.TableSchema

    fake_tables = [
        TableSummary(schema_name="public", name="users_public", kind="view",
                     approx_row_count=5, grant_missing=False),
    ]
    fake_schema = TableSchema(
        schema_name="public",
        name="users_public",
        columns=[
            ColumnSummary(name="id", data_type="character varying", nullable=False, is_pk=True),
            ColumnSummary(name="email", data_type="character varying", nullable=False),
            ColumnSummary(name="display_name", data_type="character varying", nullable=False),
        ],
        primary_key=["id"],
    )

    async def _mock_list_tables():
        return fake_tables

    async def _mock_get_schema(table):
        return fake_schema

    monkeypatch.setattr(introspect, "list_tables", _mock_list_tables)
    monkeypatch.setattr(introspect, "get_schema", _mock_get_schema)

    result = await introspect.resolve_identifier("users_public", "email")
    assert result == ("users_public", "email")


@pytest.mark.asyncio
async def test_resolve_identifier_bogus_column(monkeypatch):
    """resolve_identifier('users_public', 'bogus') raises ValueError."""
    schemas = _import_pg_viewer_schemas()
    introspect = _import_introspect()
    introspect.invalidate_introspect_cache()

    TableSummary = schemas.TableSummary
    ColumnSummary = schemas.ColumnSummary
    TableSchema = schemas.TableSchema

    fake_tables = [
        TableSummary(schema_name="public", name="users_public", kind="view",
                     approx_row_count=5, grant_missing=False),
    ]
    fake_schema = TableSchema(
        schema_name="public",
        name="users_public",
        columns=[
            ColumnSummary(name="id", data_type="character varying", nullable=False, is_pk=True),
            ColumnSummary(name="email", data_type="character varying", nullable=False),
        ],
        primary_key=["id"],
    )

    async def _mock_list_tables():
        return fake_tables

    async def _mock_get_schema(table):
        return fake_schema

    monkeypatch.setattr(introspect, "list_tables", _mock_list_tables)
    monkeypatch.setattr(introspect, "get_schema", _mock_get_schema)

    with pytest.raises(ValueError, match="bogus"):
        await introspect.resolve_identifier("users_public", "bogus")


@pytest.mark.asyncio
async def test_resolve_identifier_inaccessible_table(monkeypatch):
    """resolve_identifier('users', 'anything') raises ValueError — users not in whitelist."""
    schemas = _import_pg_viewer_schemas()
    introspect = _import_introspect()
    introspect.invalidate_introspect_cache()

    TableSummary = schemas.TableSummary

    fake_tables = [
        TableSummary(schema_name="public", name="users", kind="table",
                     approx_row_count=10, grant_missing=True),
        TableSummary(schema_name="public", name="users_public", kind="view",
                     approx_row_count=5, grant_missing=False),
    ]

    async def _mock_list_tables():
        return fake_tables

    monkeypatch.setattr(introspect, "list_tables", _mock_list_tables)

    with pytest.raises(ValueError, match="users"):
        await introspect.resolve_identifier("users", "anything")


@pytest.mark.asyncio
async def test_resolve_identifier_unknown_table(monkeypatch):
    """resolve_identifier('nonexistent', None) raises ValueError."""
    schemas = _import_pg_viewer_schemas()
    introspect = _import_introspect()
    introspect.invalidate_introspect_cache()

    TableSummary = schemas.TableSummary

    async def _mock_list_tables():
        return [
            TableSummary(schema_name="public", name="users_public", kind="view",
                         approx_row_count=5, grant_missing=False),
        ]

    monkeypatch.setattr(introspect, "list_tables", _mock_list_tables)

    with pytest.raises(ValueError, match="nonexistent"):
        await introspect.resolve_identifier("nonexistent", None)


# ---------------------------------------------------------------------------
# Unit test — 5-minute TTL cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_ttl(monkeypatch):
    """Results are returned from cache on second call (DB not queried again)."""
    introspect = _import_introspect()
    introspect.invalidate_introspect_cache()

    call_count = {"n": 0}
    fake_rows = [("users_public", "VIEW", 3)]

    async def _execute(stmt, params=None):
        sql = str(stmt).lower() if not isinstance(stmt, str) else stmt.lower()
        result = MagicMock()
        if "information_schema.tables" in sql:
            call_count["n"] += 1
            result.fetchall.return_value = fake_rows
        else:
            result.fetchall.return_value = []
        result.scalar.return_value = 0
        return result

    conn = AsyncMock()
    conn.execute = _execute

    monkeypatch.setattr(introspect, "_probe_select", AsyncMock(return_value=True))
    monkeypatch.setattr(introspect, "_get_viewer_db", _make_gen_factory(conn))

    # First call — hits DB
    await introspect.list_tables()
    first_db_calls = call_count["n"]
    assert first_db_calls >= 1

    # Second call — should use cache, NOT hit DB again
    await introspect.list_tables()
    assert call_count["n"] == first_db_calls, (
        "Second call should have used the cache, not re-queried the DB."
    )

    # After invalidation — hits DB again
    introspect.invalidate_introspect_cache()

    conn2 = AsyncMock()
    conn2.execute = _execute
    monkeypatch.setattr(introspect, "_get_viewer_db", _make_gen_factory(conn2))
    await introspect.list_tables()
    assert call_count["n"] > first_db_calls


# ---------------------------------------------------------------------------
# Integration tests — require live DB
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not _PG_URL,
    reason="PG_VIEWER_DATABASE_URL not set — integration tests skipped",
)
async def test_integration_list_tables_contains_users_public():
    """list_tables() returns users_public (not users) on a live DB."""
    from app.services.pg_viewer.introspect import invalidate_introspect_cache, list_tables

    invalidate_introspect_cache()
    tables = await list_tables()
    names = [t.name for t in tables]

    assert "users_public" in names, f"users_public missing from {names}"
    for t in tables:
        if t.name == "users":
            assert t.grant_missing is True, (
                "users table must not be directly readable by aikm_viewer"
            )


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not _PG_URL,
    reason="PG_VIEWER_DATABASE_URL not set — integration tests skipped",
)
async def test_integration_list_tables_maximo_present():
    """list_tables() includes maximo_* tables."""
    from app.services.pg_viewer.introspect import invalidate_introspect_cache, list_tables

    invalidate_introspect_cache()
    tables = await list_tables()
    maximo_tables = [t for t in tables if t.name.startswith("maximo_")]
    assert maximo_tables, "Expected at least one maximo_* table"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not _PG_URL,
    reason="PG_VIEWER_DATABASE_URL not set — integration tests skipped",
)
async def test_integration_get_schema_composite_pk():
    """get_schema('user_permissions') returns primary_key=['user_id','section']."""
    from app.services.pg_viewer.introspect import get_schema, invalidate_introspect_cache

    invalidate_introspect_cache()
    schema = await get_schema("user_permissions")

    assert schema.primary_key == ["user_id", "section"], (
        f"Expected composite PK ['user_id','section'], got {schema.primary_key}"
    )


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not _PG_URL,
    reason="PG_VIEWER_DATABASE_URL not set — integration tests skipped",
)
async def test_integration_resolve_identifier_valid():
    """resolve_identifier('users_public', 'email') succeeds on live DB."""
    from app.services.pg_viewer.introspect import invalidate_introspect_cache, resolve_identifier

    invalidate_introspect_cache()
    result = await resolve_identifier("users_public", "email")
    assert result == ("users_public", "email")


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not _PG_URL,
    reason="PG_VIEWER_DATABASE_URL not set — integration tests skipped",
)
async def test_integration_resolve_identifier_bogus_column():
    """resolve_identifier('users_public', 'bogus') raises ValueError on live DB."""
    from app.services.pg_viewer.introspect import invalidate_introspect_cache, resolve_identifier

    invalidate_introspect_cache()
    with pytest.raises(ValueError):
        await resolve_identifier("users_public", "bogus")


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not _PG_URL,
    reason="PG_VIEWER_DATABASE_URL not set — integration tests skipped",
)
async def test_integration_resolve_identifier_users_denied():
    """resolve_identifier('users', 'anything') raises ValueError on live DB."""
    from app.services.pg_viewer.introspect import invalidate_introspect_cache, resolve_identifier

    invalidate_introspect_cache()
    with pytest.raises(ValueError):
        await resolve_identifier("users", "anything")
