"""Unit tests for backend/app/services/pg_viewer/query_builder.py (T-012).

Test strategy
-------------
- All 12 required tests per the task spec.
- No live DB required: resolve_identifier is mocked to return (table, column)
  without hitting Postgres.
- psycopg.sql.Identifier is available in the container; on a machine without it
  a stub is injected (mirrors the sqlalchemy stub pattern in test_introspect.py).

Run::

    pytest backend/tests/pg_viewer/test_query_builder.py -v

Tests
-----
1.  Equality filter
2.  IN filter
3.  IS NULL filter
4.  LIKE with wildcard
5.  Unknown operator raises ValueError
6.  Unknown column (resolve_identifier raises) → build fails
7.  limit > PG_VIEWER_ROW_LIMIT → ValueError
8.  Composite PK default ORDER BY
9.  Identifier rendering via psycopg for EVERY identifier
10. Composed NEVER leaked (return type is str, not Composed)
11. build_count_select basic
12. Offset cap raises ValueError
"""
from __future__ import annotations

import importlib
import os
import sys
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# JWT guard bypass (mirrors test_introspect.py)
# ---------------------------------------------------------------------------
if not os.getenv("JWT_SECRET") or os.getenv("JWT_SECRET") == "aikm-secret-key-change-in-production":
    os.environ["JWT_SECRET"] = "a" * 64


# ---------------------------------------------------------------------------
# psycopg stub — injected when psycopg is not installed on the dev machine
# ---------------------------------------------------------------------------
try:
    import psycopg  # noqa: F401
    from psycopg.sql import Identifier  # noqa: F401
    _PSYCOPG_AVAILABLE = True
except ImportError:
    _PSYCOPG_AVAILABLE = False

    # Build a minimal psycopg.sql stub so that
    #   from psycopg.sql import Identifier
    # inside query_builder.py succeeds.
    def _make_identifier_stub():
        """Return a stub Identifier class that produces ANSI quoting."""
        class _Identifier:
            def __init__(self, name: str):
                self._name = name

            def as_string(self, context=None) -> str:
                # ANSI double-quote escaping
                return '"' + self._name.replace('"', '""') + '"'

        return _Identifier

    _psycopg_sql = types.ModuleType("psycopg.sql")
    _psycopg_sql.Identifier = _make_identifier_stub()

    _psycopg = types.ModuleType("psycopg")
    _psycopg.__path__ = []
    _psycopg.__package__ = "psycopg"
    _psycopg.sql = _psycopg_sql

    sys.modules.setdefault("psycopg", _psycopg)
    sys.modules.setdefault("psycopg.sql", _psycopg_sql)


# ---------------------------------------------------------------------------
# app.config stub — provides get_settings() with pg_viewer_row_limit=1000
# ---------------------------------------------------------------------------
def _ensure_config_stub():
    """Inject a minimal app.config stub unless the real one is already importable."""
    if "app.config" in sys.modules:
        return
    try:
        import app.config  # noqa: F401
        return
    except Exception:
        pass

    class _FakeSettings:
        pg_viewer_row_limit: int = 1000

    _config_mod = types.ModuleType("app.config")
    _config_mod.get_settings = lambda: _FakeSettings()

    # Also stub app package if missing
    if "app" not in sys.modules:
        _app = types.ModuleType("app")
        _app.__path__ = []
        _app.__package__ = "app"
        sys.modules["app"] = _app

    sys.modules["app.config"] = _config_mod


_ensure_config_stub()


# ---------------------------------------------------------------------------
# Import query_builder directly (bypass pg_viewer __init__.py JWT guard)
# ---------------------------------------------------------------------------

def _import_query_builder():
    mod_name = "app.services.pg_viewer.query_builder"
    if mod_name in sys.modules:
        return sys.modules[mod_name]

    import pathlib
    for path_entry in sys.path:
        candidate = (
            pathlib.Path(path_entry)
            / "app" / "services" / "pg_viewer" / "query_builder.py"
        )
        if candidate.exists():
            spec = importlib.util.spec_from_file_location(mod_name, str(candidate))
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            return mod
    raise ImportError("Cannot locate app/services/pg_viewer/query_builder.py")


qb = _import_query_builder()
FilterClause = qb.FilterClause
build_table_select = qb.build_table_select
build_count_select = qb.build_count_select


# ---------------------------------------------------------------------------
# Mock for resolve_identifier — returns (table, column) without DB
# ---------------------------------------------------------------------------

def _mock_resolve_identifier_ok(table: str, column: str | None = None):
    """Always resolves successfully — used as the default happy-path mock."""
    async def _inner(t, c=None):
        return (t, c)
    return _inner(table, column)


def _make_resolve_ok_mock():
    return AsyncMock(side_effect=lambda t, c=None: (t, c))


def _make_resolve_fail_mock(message="Unknown column"):
    async def _fail(t, c=None):
        if c is not None:
            raise ValueError(message)
        return (t, None)
    return AsyncMock(side_effect=_fail)


# ---------------------------------------------------------------------------
# Helper: patch resolve_identifier inside query_builder module
# ---------------------------------------------------------------------------

def _patch_resolve(mock_fn):
    """Context manager: replaces resolve_identifier inside the qb module's introspect."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        # query_builder imports resolve_identifier from introspect inside
        # _validate_all() as a deferred import; we need to pre-register the
        # introspect module in sys.modules with our mock resolve_identifier.
        fake_introspect = types.ModuleType("app.services.pg_viewer.introspect")
        fake_introspect.resolve_identifier = mock_fn
        sys.modules["app.services.pg_viewer.introspect"] = fake_introspect
        try:
            yield
        finally:
            sys.modules.pop("app.services.pg_viewer.introspect", None)

    return _ctx()


# ---------------------------------------------------------------------------
# Test 1: Equality filter
# ---------------------------------------------------------------------------

def test_equality_filter():
    """SQL contains "email" = $1, params=["a@b.c"], ORDER BY pk DESC, LIMIT/OFFSET correct."""
    with _patch_resolve(_make_resolve_ok_mock()):
        sql, params = build_table_select(
            None,
            table="users_public",
            columns=["id", "email"],
            filters=[FilterClause(column="email", op="=", value="a@b.c")],
            limit=10,
            pk_columns=["id"],
        )

    assert isinstance(sql, str), "Return type MUST be str, not Composed"
    assert '"email" = $1' in sql
    assert params == ["a@b.c"]
    # Default order dir is desc
    assert '"id" DESC' in sql
    assert "LIMIT 10" in sql
    assert "OFFSET 0" in sql


# ---------------------------------------------------------------------------
# Test 2: IN filter
# ---------------------------------------------------------------------------

def test_in_filter():
    """IN filter expands to ($1, $2), params has both values."""
    with _patch_resolve(_make_resolve_ok_mock()):
        sql, params = build_table_select(
            None,
            table="users_public",
            columns=["id"],
            filters=[FilterClause(column="account_level", op="IN", value=["free", "pro"])],
            limit=20,
            pk_columns=["id"],
        )

    assert isinstance(sql, str)
    assert '"account_level" IN ($1, $2)' in sql
    assert params == ["free", "pro"]


# ---------------------------------------------------------------------------
# Test 3: IS NULL filter
# ---------------------------------------------------------------------------

def test_is_null_filter():
    """IS NULL produces no bound param; SQL contains IS NULL fragment."""
    with _patch_resolve(_make_resolve_ok_mock()):
        sql, params = build_table_select(
            None,
            table="users_public",
            columns=["id"],
            filters=[FilterClause(column="last_login", op="IS NULL", value=None)],
            limit=5,
            pk_columns=["id"],
        )

    assert isinstance(sql, str)
    assert '"last_login" IS NULL' in sql
    assert params == []  # no param for IS NULL


# ---------------------------------------------------------------------------
# Test 4: LIKE with wildcard
# ---------------------------------------------------------------------------

def test_like_wildcard():
    """wildcard=True wraps value with %, param is %joe%, SQL has LIKE $1."""
    with _patch_resolve(_make_resolve_ok_mock()):
        sql, params = build_table_select(
            None,
            table="users_public",
            columns=["id"],
            filters=[
                FilterClause(
                    column="display_name", op="LIKE", value="joe", wildcard=True
                )
            ],
            limit=5,
            pk_columns=["id"],
        )

    assert isinstance(sql, str)
    assert '"display_name" LIKE $1' in sql
    assert params == ["%joe%"]


# ---------------------------------------------------------------------------
# Test 5: Unknown operator raises ValueError
# ---------------------------------------------------------------------------

def test_unknown_operator_raises():
    """An operator not in the whitelist must raise an error (Pydantic or ValueError).

    Pydantic v2 raises ValidationError (a subclass of ValueError) when the Literal
    constraint on FilterClause.op is violated.  Both are acceptable — the key
    invariant is that the invalid operator never reaches the SQL builder.
    """
    from pydantic import ValidationError  # noqa: PLC0415

    with _patch_resolve(_make_resolve_ok_mock()):
        # Pydantic catches the bad op at model construction time
        with pytest.raises((ValidationError, ValueError)):
            FilterClause(column="x", op="≈", value="y")  # type: ignore[arg-type]


def test_unknown_operator_via_build():
    """Double-check: injecting an invalid op past Pydantic still raises in build."""
    # Bypass Pydantic by constructing a plain object
    class _BadFilter:
        column = "x"
        op = "INJECT"
        value = "y"
        wildcard = False

    with _patch_resolve(_make_resolve_ok_mock()):
        with pytest.raises(ValueError, match="not in the whitelist|whitelist|Operator"):
            build_table_select(
                None,
                table="users_public",
                columns=["id"],
                filters=[_BadFilter()],  # type: ignore[list-item]
                limit=5,
                pk_columns=["id"],
            )


# ---------------------------------------------------------------------------
# Test 6: Unknown column → resolve_identifier raises → build fails
# ---------------------------------------------------------------------------

def test_unknown_column_raises():
    """When resolve_identifier raises, build_table_select must propagate ValueError."""
    with _patch_resolve(_make_resolve_fail_mock("Unknown column 'evil' on table")):
        with pytest.raises(ValueError, match="Unknown column|Identifier validation"):
            build_table_select(
                None,
                table="users_public",
                columns=["evil"],
                filters=[],
                limit=5,
                pk_columns=["id"],
            )


# ---------------------------------------------------------------------------
# Test 7: limit > PG_VIEWER_ROW_LIMIT raises ValueError
# ---------------------------------------------------------------------------

def test_limit_too_large():
    """limit=10000 with default row_limit=1000 raises ValueError."""
    with _patch_resolve(_make_resolve_ok_mock()):
        with pytest.raises(ValueError, match="row limit exceeded"):
            build_table_select(
                None,
                table="users_public",
                columns=[],
                filters=[],
                limit=10_000,
                pk_columns=["id"],
            )


# ---------------------------------------------------------------------------
# Test 8: Composite PK default ORDER BY
# ---------------------------------------------------------------------------

def test_composite_pk_order_by():
    """When pk_columns=[user_id, section], ORDER BY has both columns DESC."""
    with _patch_resolve(_make_resolve_ok_mock()):
        sql, _ = build_table_select(
            None,
            table="user_permissions",
            columns=[],
            filters=[],
            limit=10,
            pk_columns=["user_id", "section"],
        )

    assert isinstance(sql, str)
    assert '"user_id" DESC' in sql
    assert '"section" DESC' in sql
    # Both appear in the ORDER BY clause (verify ordering)
    order_start = sql.index("ORDER BY")
    order_clause = sql[order_start:]
    assert '"user_id" DESC' in order_clause
    assert '"section" DESC' in order_clause


# ---------------------------------------------------------------------------
# Test 9: Identifier rendering via psycopg (Identifier.as_string called for EVERY ident)
# ---------------------------------------------------------------------------

def test_identifier_via_psycopg_for_every_name():
    """Every identifier (table + columns + filter cols) goes through _ident()."""
    call_log: list[str] = []

    original_ident = qb._ident

    def _tracking_ident(name: str) -> str:
        call_log.append(name)
        return original_ident(name)

    with _patch_resolve(_make_resolve_ok_mock()):
        with patch.object(qb, "_ident", side_effect=_tracking_ident):
            build_table_select(
                None,
                table="users_public",
                columns=["id", "email"],
                filters=[FilterClause(column="status", op="=", value="active")],
                limit=5,
                pk_columns=["id"],
            )

    # Table, each column, filter column, and PK column must all appear
    assert "users_public" in call_log, "_ident must be called for table name"
    assert "id" in call_log, "_ident must be called for output column"
    assert "email" in call_log, "_ident must be called for output column"
    assert "status" in call_log, "_ident must be called for filter column"


# ---------------------------------------------------------------------------
# Test 10: Composed NEVER leaked to asyncpg
# ---------------------------------------------------------------------------

def test_return_type_is_str_not_composed():
    """First return value must be a plain str (Composed would cause asyncpg to error)."""
    with _patch_resolve(_make_resolve_ok_mock()):
        result = build_table_select(
            None,
            table="users_public",
            columns=["id"],
            filters=[FilterClause(column="status", op="=", value="active")],
            limit=5,
            pk_columns=["id"],
        )

    sql, params = result
    assert type(sql) is str, (
        f"build_table_select must return plain str, got {type(sql).__name__}"
    )
    assert isinstance(params, list)

    # Verify count too
    with _patch_resolve(_make_resolve_ok_mock()):
        count_sql, count_params = build_count_select(
            None,
            table="users_public",
            filters=[FilterClause(column="status", op="=", value="active")],
        )
    assert type(count_sql) is str, (
        f"build_count_select must return plain str, got {type(count_sql).__name__}"
    )


# ---------------------------------------------------------------------------
# Test 11: build_count_select basic
# ---------------------------------------------------------------------------

def test_count_select():
    """build_count_select returns SELECT count(*) FROM "users_public" WHERE "status" = $1."""
    with _patch_resolve(_make_resolve_ok_mock()):
        sql, params = build_count_select(
            None,
            table="users_public",
            filters=[FilterClause(column="status", op="=", value="active")],
        )

    assert isinstance(sql, str)
    assert sql.startswith("SELECT count(*) FROM")
    assert '"users_public"' in sql
    assert '"status" = $1' in sql
    assert params == ["active"]


# ---------------------------------------------------------------------------
# Test 12: Offset cap raises ValueError
# ---------------------------------------------------------------------------

def test_offset_cap():
    """offset=10_000_000 (above 100_000 cap) raises ValueError."""
    with _patch_resolve(_make_resolve_ok_mock()):
        with pytest.raises(ValueError, match="offset too large"):
            build_table_select(
                None,
                table="users_public",
                columns=[],
                filters=[],
                limit=10,
                offset=10_000_000,
                pk_columns=["id"],
            )


# ---------------------------------------------------------------------------
# Bonus: SQL injection in value is safely bound (not interpolated)
# ---------------------------------------------------------------------------

def test_value_sql_injection_is_bound_not_interpolated():
    """Malicious value is bound as $1, never embedded in the SQL string."""
    evil = "'; DROP TABLE users; --"
    with _patch_resolve(_make_resolve_ok_mock()):
        sql, params = build_table_select(
            None,
            table="users_public",
            columns=["id"],
            filters=[FilterClause(column="email", op="=", value=evil)],
            limit=5,
            pk_columns=["id"],
        )

    assert evil not in sql, "Evil value must NOT appear in SQL text"
    assert "$1" in sql, "Positional placeholder must appear in SQL"
    assert params == [evil], "Evil value safely in params list"


# ---------------------------------------------------------------------------
# Bonus: NOT IN filter
# ---------------------------------------------------------------------------

def test_not_in_filter():
    """NOT IN expands correctly, placeholder count matches value list."""
    with _patch_resolve(_make_resolve_ok_mock()):
        sql, params = build_table_select(
            None,
            table="users_public",
            columns=["id"],
            filters=[FilterClause(column="status", op="NOT IN", value=["banned", "deleted"])],
            limit=5,
            pk_columns=["id"],
        )

    assert '"status" NOT IN ($1, $2)' in sql
    assert params == ["banned", "deleted"]


# ---------------------------------------------------------------------------
# Bonus: IS NOT NULL filter
# ---------------------------------------------------------------------------

def test_is_not_null_filter():
    """IS NOT NULL produces no bound param."""
    with _patch_resolve(_make_resolve_ok_mock()):
        sql, params = build_table_select(
            None,
            table="users_public",
            columns=["id"],
            filters=[FilterClause(column="email", op="IS NOT NULL", value=None)],
            limit=5,
            pk_columns=["id"],
        )

    assert '"email" IS NOT NULL' in sql
    assert params == []


# ---------------------------------------------------------------------------
# Bonus: ASC order direction
# ---------------------------------------------------------------------------

def test_asc_order_direction():
    """order_dir='asc' produces ASC in ORDER BY."""
    with _patch_resolve(_make_resolve_ok_mock()):
        sql, _ = build_table_select(
            None,
            table="users_public",
            columns=[],
            filters=[],
            limit=5,
            order_dir="asc",
            pk_columns=["id"],
        )

    assert '"id" ASC' in sql
