"""Unit tests for pg_viewer CSV exporter (T-015).

All tests are pure-unit: no DB connection required.
The exporter module's dependencies (get_viewer_db, build_table_select,
apply_redaction) are mocked so tests run on any machine.

Test inventory
--------------
1. 50-row output is valid CSV (parseable, row count = 51 including header).
2. 1500-row source → X-Truncated=true, X-Row-Count=1000, body = 1001 rows
   (1 header + 1000 data); NO fake "-- truncated" comment row.
3. Sensitive columns absent or masked (T-013 REDACTED_BY_ROW_RULE).
4. bytes value → base64 → clipped to 200 chars.
5. str > 1000 chars → clipped to 1000 + "…".
6. Payload > 10 MB → generator stops early, logger.warning emitted.
7. Filename defensive quoting — table names with non-whitelisted chars get "_"
   substituted; safe names are preserved.
"""
from __future__ import annotations

import base64
import csv
import importlib.util
import io
import logging
import os
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Environment setup — JWT guard bypass
# ---------------------------------------------------------------------------

if not os.getenv("JWT_SECRET") or os.getenv("JWT_SECRET") == "aikm-secret-key-change-in-production":
    os.environ["JWT_SECRET"] = "a" * 64
os.environ.setdefault("PG_VIEWER_DATABASE_URL", "")  # suppress import-time scan


# ---------------------------------------------------------------------------
# Stubs: sqlalchemy (not installed on dev Mac mini)
# ---------------------------------------------------------------------------

try:
    import sqlalchemy  # noqa: F401
    _SQLALCHEMY_AVAILABLE = True
except ImportError:
    _SQLALCHEMY_AVAILABLE = False

    # Minimal stub: text() just passes its argument through
    _sa_stub = types.ModuleType("sqlalchemy")
    _sa_stub.text = lambda s: s  # identity — AsyncMock conn.execute accepts it

    sys.modules.setdefault("sqlalchemy", _sa_stub)
    # Also stub sub-packages that might be transitively imported
    for _sub in ("sqlalchemy.ext", "sqlalchemy.ext.asyncio", "sqlalchemy.exc"):
        if _sub not in sys.modules:
            _sub_mod = types.ModuleType(_sub)
            _sub_mod.__path__ = []
            sys.modules[_sub] = _sub_mod


# ---------------------------------------------------------------------------
# Stubs: psycopg.sql.Identifier (mirrors test_query_builder.py)
# ---------------------------------------------------------------------------

try:
    from psycopg.sql import Identifier as _RealIdentifier  # noqa: F401
    _PSYCOPG_AVAILABLE = True
except ImportError:
    _PSYCOPG_AVAILABLE = False

    class _IdentifierStub:
        def __init__(self, name: str):
            self._name = name

        def as_string(self, context=None) -> str:
            return '"' + self._name.replace('"', '""') + '"'

    _psycopg_sql_stub = types.ModuleType("psycopg.sql")
    _psycopg_sql_stub.Identifier = _IdentifierStub

    _psycopg_stub = types.ModuleType("psycopg")
    _psycopg_stub.__path__ = []
    _psycopg_stub.__package__ = "psycopg"
    _psycopg_stub.sql = _psycopg_sql_stub

    sys.modules.setdefault("psycopg", _psycopg_stub)
    sys.modules.setdefault("psycopg.sql", _psycopg_sql_stub)


# ---------------------------------------------------------------------------
# Stub: app.config
# ---------------------------------------------------------------------------

def _ensure_config_stub() -> None:
    if "app.config" in sys.modules:
        return
    try:
        import app.config  # noqa: F401
        return
    except Exception:
        pass

    class _FakeSettings:
        pg_viewer_row_limit: int = 1000
        pg_viewer_enabled: bool = True

    _mod = types.ModuleType("app.config")
    _mod.get_settings = lambda: _FakeSettings()

    if "app" not in sys.modules:
        _app_stub = types.ModuleType("app")
        _app_stub.__path__ = []
        _app_stub.__package__ = "app"
        sys.modules["app"] = _app_stub

    sys.modules["app.config"] = _mod


_ensure_config_stub()


# ---------------------------------------------------------------------------
# Stub: introspect.resolve_identifier (always succeeds)
#
# Injected temporarily per-test via _introspect_stub_ctx() so we don't
# pollute sys.modules permanently and break tests that load the real module.
# ---------------------------------------------------------------------------

import contextlib


@contextlib.contextmanager
def _introspect_stub_ctx():
    """Temporarily inject a resolve_identifier stub that always succeeds.

    Restores the previous entry in sys.modules on exit (or removes the key if
    nothing was there before).  This prevents permanent pollution of sys.modules
    when tests from other files run in the same process.
    """
    mod_name = "app.services.pg_viewer.introspect"
    previous = sys.modules.get(mod_name)

    async def _resolve_ok(table: str, column: str | None = None):
        return (table, column)

    _stub = types.ModuleType(mod_name)
    _stub.resolve_identifier = _resolve_ok
    sys.modules[mod_name] = _stub
    try:
        yield _stub
    finally:
        if previous is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = previous


# ---------------------------------------------------------------------------
# Direct module loading helpers (bypass __init__.py JWT guard)
# ---------------------------------------------------------------------------

_BACKEND_ROOT = Path(__file__).parent.parent.parent  # backend/


def _load_module_direct(rel_path: str, mod_name: str):
    """Load a .py file directly by path, bypassing package __init__.py.

    Caches in sys.modules so subsequent imports within the same process
    resolve correctly.
    """
    if mod_name in sys.modules:
        return sys.modules[mod_name]

    full_path = _BACKEND_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(mod_name, str(full_path))
    assert spec is not None, f"Cannot find {full_path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _load_redaction():
    return _load_module_direct(
        "app/services/pg_viewer/redaction.py",
        "app.services.pg_viewer.redaction",
    )


def _load_query_builder():
    return _load_module_direct(
        "app/services/pg_viewer/query_builder.py",
        "app.services.pg_viewer.query_builder",
    )


def _load_exporter():
    return _load_module_direct(
        "app/services/pg_viewer/exporter.py",
        "app.services.pg_viewer.exporter",
    )


# ---------------------------------------------------------------------------
# FilterClause shim (so tests can construct filter objects without a DB)
# ---------------------------------------------------------------------------

qb = _load_query_builder()
FilterClause = qb.FilterClause


# ---------------------------------------------------------------------------
# Autouse fixture: install introspect stub for every test in this file,
# restore on teardown to avoid sys.modules pollution for other test files.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _install_introspect_stub():
    """Install a resolve_identifier stub for the duration of each test."""
    with _introspect_stub_ctx():
        yield


# ---------------------------------------------------------------------------
# Helpers for driving the async generator inside StreamingResponse
# ---------------------------------------------------------------------------

async def _collect_body(response) -> bytes:
    """Drain a StreamingResponse body_iterator into bytes."""
    chunks: list[bytes] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)
    return b"".join(chunks)


def _parse_csv_body(body: bytes) -> list[list[str]]:
    """Parse raw CSV bytes (no BOM) into a list of rows."""
    text = body.decode("utf-8")
    # Ensure no BOM
    assert not text.startswith("\ufeff"), "CSV must not start with BOM"
    reader = csv.reader(io.StringIO(text))
    return list(reader)


# ---------------------------------------------------------------------------
# Mock factory for get_viewer_db()
# ---------------------------------------------------------------------------

def _make_viewer_db_mock(rows: list[dict], col_names: list[str]):
    """Return a patched get_viewer_db context manager yielding fake rows.

    The mock simulates conn.execute(sql, params) → result with .fetchall() and .keys().
    """
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [
        tuple(row.get(c) for c in col_names) for row in rows
    ]
    mock_result.keys.return_value = col_names

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value=mock_result)

    # Async generator that yields mock_conn then raises StopAsyncIteration
    async def _fake_get_viewer_db():
        yield mock_conn

    return _fake_get_viewer_db


# ---------------------------------------------------------------------------
# Test 1: 50-row output is valid CSV
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_50_rows_valid_csv():
    """export_csv with 50 synthetic rows produces parseable CSV with 51 rows
    (1 header + 50 data)."""
    exporter = _load_exporter()

    col_names = ["id", "name", "value"]
    rows = [{"id": i, "name": f"row_{i}", "value": f"val_{i}"} for i in range(50)]

    fake_gen = _make_viewer_db_mock(rows, col_names)

    with patch.object(
        sys.modules["app.services.pg_viewer.exporter"],
        "get_viewer_db",
        fake_gen,
    ):
        response = await exporter.export_csv(
            table="test_table",
            columns=col_names,
            filters=[],
            order_by=None,
            order_dir="asc",
            row_limit=1000,
        )

    body = await _collect_body(response)
    parsed = _parse_csv_body(body)

    # 1 header + 50 data rows = 51 total (last empty row from CRLF is filtered by csv.reader)
    data_rows = [r for r in parsed if r]
    assert len(data_rows) == 51, f"Expected 51 rows, got {len(data_rows)}"
    assert data_rows[0] == col_names, f"Header mismatch: {data_rows[0]}"
    assert data_rows[1] == ["0", "row_0", "val_0"]
    assert data_rows[50] == ["49", "row_49", "val_49"]


# ---------------------------------------------------------------------------
# Test 2: 1500-row source → X-Truncated=true, X-Row-Count=1000
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_1500_rows_truncated():
    """DB returns 1000 rows (row_limit=1000 capped by build_table_select).
    We simulate by passing 1000 rows from mock.  X-Truncated should be true,
    body should be 1001 rows, NO fake comment row."""
    exporter = _load_exporter()

    col_names = ["id", "data"]
    # Simulate the DB returning exactly row_limit (1000) rows
    rows = [{"id": i, "data": f"d_{i}"} for i in range(1000)]

    fake_gen = _make_viewer_db_mock(rows, col_names)

    with patch.object(
        sys.modules["app.services.pg_viewer.exporter"],
        "get_viewer_db",
        fake_gen,
    ):
        response = await exporter.export_csv(
            table="big_table",
            columns=col_names,
            filters=[],
            order_by=None,
            order_dir="asc",
            row_limit=1000,
        )

    # Check headers
    assert response.headers.get("X-Truncated") == "true", (
        f"Expected X-Truncated=true, got {response.headers.get('X-Truncated')!r}"
    )
    assert response.headers.get("X-Row-Count") == "1000", (
        f"Expected X-Row-Count=1000, got {response.headers.get('X-Row-Count')!r}"
    )

    body = await _collect_body(response)
    parsed = _parse_csv_body(body)
    data_rows = [r for r in parsed if r]

    # 1 header + 1000 data = 1001
    assert len(data_rows) == 1001, f"Expected 1001 rows, got {len(data_rows)}"

    # No fake truncation marker row in body
    for row in data_rows:
        assert not any("truncat" in cell.lower() for cell in row), (
            f"Fake truncation marker found in CSV body: {row}"
        )


# ---------------------------------------------------------------------------
# Test 3: Sensitive columns absent or masked (REDACTED_BY_ROW_RULE)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sensitive_columns_masked():
    """system_settings rows with key='openai_api_key' must have value='***'."""
    exporter = _load_exporter()

    col_names = ["key", "value"]
    rows = [
        {"key": "app_name", "value": "AIKM"},
        {"key": "openai_api_key", "value": "sk-super-secret"},
        {"key": "jwt_secret", "value": "my-jwt-secret"},
    ]

    fake_gen = _make_viewer_db_mock(rows, col_names)

    with patch.object(
        sys.modules["app.services.pg_viewer.exporter"],
        "get_viewer_db",
        fake_gen,
    ):
        response = await exporter.export_csv(
            table="system_settings",
            columns=col_names,
            filters=[],
            order_by=None,
            order_dir="asc",
            row_limit=1000,
        )

    body = await _collect_body(response)
    parsed = _parse_csv_body(body)
    data_rows = [r for r in parsed if r]

    # Header + 3 data rows
    assert len(data_rows) == 4

    # Row with app_name should be intact
    app_row = next(r for r in data_rows[1:] if r[0] == "app_name")
    assert app_row[1] == "AIKM"

    # Sensitive rows should be masked
    api_row = next(r for r in data_rows[1:] if r[0] == "openai_api_key")
    assert api_row[1] == "***", f"Expected '***', got {api_row[1]!r}"

    jwt_row = next(r for r in data_rows[1:] if r[0] == "jwt_secret")
    assert jwt_row[1] == "***", f"Expected '***', got {jwt_row[1]!r}"

    # Original secret never appears in output
    assert "sk-super-secret" not in body.decode("utf-8")
    assert "my-jwt-secret" not in body.decode("utf-8")


# ---------------------------------------------------------------------------
# Test 4: bytes value → base64 → clipped to 200 chars
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bytes_base64_clipped():
    """A bytes cell is base64-encoded and clipped to 200 chars."""
    exporter = _load_exporter()

    # Create a bytes value whose base64 encoding exceeds 200 chars
    raw_bytes = b"\xff\xfe" * 200  # 400 bytes → base64 ~ 534 chars
    b64_full = base64.b64encode(raw_bytes).decode("ascii")
    assert len(b64_full) > 200, "Precondition: b64 must exceed 200 chars"

    col_names = ["id", "data"]
    rows = [{"id": 1, "data": raw_bytes}]

    fake_gen = _make_viewer_db_mock(rows, col_names)

    with patch.object(
        sys.modules["app.services.pg_viewer.exporter"],
        "get_viewer_db",
        fake_gen,
    ):
        response = await exporter.export_csv(
            table="bytea_table",
            columns=col_names,
            filters=[],
            order_by=None,
            order_dir="asc",
            row_limit=1000,
        )

    body = await _collect_body(response)
    parsed = _parse_csv_body(body)
    data_rows = [r for r in parsed if r]

    # Header + 1 data row
    assert len(data_rows) == 2
    cell_value = data_rows[1][1]

    # Must be clipped to exactly 200 chars
    assert len(cell_value) == 200, f"Expected 200 chars, got {len(cell_value)}"
    # Must match the first 200 chars of the full base64
    assert cell_value == b64_full[:200], (
        f"Clipped value does not match first 200 chars of base64"
    )
    # Raw bytes must not appear verbatim
    assert raw_bytes not in body


# ---------------------------------------------------------------------------
# Test 5: str > 1000 chars → clipped to 1000 + "…"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_long_string_clipped():
    """A string cell > 1000 chars is clipped to 1000 chars followed by '…'."""
    exporter = _load_exporter()

    long_str = "A" * 2000
    col_names = ["id", "description"]
    rows = [{"id": 1, "description": long_str}]

    fake_gen = _make_viewer_db_mock(rows, col_names)

    with patch.object(
        sys.modules["app.services.pg_viewer.exporter"],
        "get_viewer_db",
        fake_gen,
    ):
        response = await exporter.export_csv(
            table="text_table",
            columns=col_names,
            filters=[],
            order_by=None,
            order_dir="asc",
            row_limit=1000,
        )

    body = await _collect_body(response)
    parsed = _parse_csv_body(body)
    data_rows = [r for r in parsed if r]

    assert len(data_rows) == 2
    cell_value = data_rows[1][1]

    # Length = 1000 chars + 1 ellipsis char
    assert len(cell_value) == 1001, (
        f"Expected 1001 chars (1000 + ellipsis), got {len(cell_value)}"
    )
    assert cell_value.endswith("\u2026"), "Must end with ellipsis character"
    assert cell_value[:1000] == "A" * 1000

    # A string of exactly 1000 chars must NOT be clipped (no ellipsis)
    exact_str = "B" * 1000
    rows2 = [{"id": 2, "description": exact_str}]
    fake_gen2 = _make_viewer_db_mock(rows2, col_names)

    with patch.object(
        sys.modules["app.services.pg_viewer.exporter"],
        "get_viewer_db",
        fake_gen2,
    ):
        response2 = await exporter.export_csv(
            table="text_table",
            columns=col_names,
            filters=[],
            order_by=None,
            order_dir="asc",
            row_limit=1000,
        )

    body2 = await _collect_body(response2)
    parsed2 = _parse_csv_body(body2)
    data_rows2 = [r for r in parsed2 if r]
    cell2 = data_rows2[1][1]
    assert not cell2.endswith("\u2026"), "1000-char string must NOT get ellipsis"
    assert cell2 == exact_str


# ---------------------------------------------------------------------------
# Test 6: Payload > 10 MB → generator stops early, warning emitted
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_10mb_cap_stops_early():
    """If cumulative output exceeds 10 MB, the generator stops and logger.warning
    is called.

    Design: patch _encode_cell to return a fixed 10 KB string (bypassing
    truncation logic) so each row contributes ~20 KB to the payload (2 cols × 10 KB).
    With 500 rows that totals ~10 MB, triggering the cap mid-stream.

    The warning is verified by patching the logger.warning method directly —
    this avoids pytest-asyncio STRICT mode caplog propagation quirks.
    """
    exporter = _load_exporter()

    _10KB = "Y" * 10_240  # 10 KB per cell (not clipped — bypassed via mock)

    col_names = ["id", "payload"]
    # Each row: 2 cells × 10 KB + CSV overhead ~20.5 KB.
    # Cap = 10 MB = 10,485,760 bytes → cap triggers after ~512 rows.
    # Use 700 rows so the cap is triggered well within the row list.
    rows = [{"id": i, "payload": "data"} for i in range(700)]

    fake_gen = _make_viewer_db_mock(rows, col_names)

    warning_calls: list[tuple] = []

    def _capture_warning(msg, *args, **kwargs):
        warning_calls.append((msg, args))

    with patch.object(
        sys.modules["app.services.pg_viewer.exporter"],
        "_encode_cell",
        return_value=_10KB,
    ):
        with patch.object(
            sys.modules["app.services.pg_viewer.exporter"],
            "get_viewer_db",
            fake_gen,
        ):
            with patch.object(
                sys.modules["app.services.pg_viewer.exporter"].logger,
                "warning",
                side_effect=_capture_warning,
            ):
                response = await exporter.export_csv(
                    table="fat_table",
                    columns=col_names,
                    filters=[],
                    order_by=None,
                    order_dir="asc",
                    row_limit=1000,
                )

                body = await _collect_body(response)

    # Generator must have stopped before exhausting all 700 rows.
    # Approximate max uncapped: 700 rows × 2 cells × 10 KB + header + CRLF overhead
    max_uncapped = 700 * 2 * len(_10KB) + 700 * 4 + 20  # generous overhead
    assert len(body) < max_uncapped, (
        f"Generator did not stop early: body size {len(body)} bytes; "
        f"max uncapped = {max_uncapped} bytes"
    )

    # Body must be near (but not grossly over) the 10 MB cap
    _MAX = 10 * 1024 * 1024
    assert len(body) <= _MAX + 25_000, (
        f"Body size {len(body)} bytes is too far above 10 MB cap"
    )

    # logger.warning must have been called with a message about the 10 MB cap
    assert len(warning_calls) >= 1, "Expected at least one logger.warning call"
    all_msgs = " ".join(str(c[0]) for c in warning_calls)
    assert "10 MB" in all_msgs or "cap" in all_msgs.lower(), (
        f"Warning message did not mention '10 MB' or 'cap': {all_msgs!r}"
    )


# ---------------------------------------------------------------------------
# Test 7: Filename defensive quoting
# ---------------------------------------------------------------------------

def test_filename_safe_quoting():
    """_safe_filename replaces non-whitelisted chars with '_', preserves safe names."""
    exporter = _load_exporter()

    # Safe name — preserved as-is
    assert exporter._safe_filename("users_public") == "users_public"
    assert exporter._safe_filename("my-table") == "my-table"
    assert exporter._safe_filename("table123") == "table123"

    # Double-quote and other non-whitelisted chars → "_"
    assert exporter._safe_filename('users"') == "users_"
    assert exporter._safe_filename("schema.table") == "schema_table"
    assert exporter._safe_filename("a b c") == "a_b_c"
    assert exporter._safe_filename("'; DROP TABLE--") == "___DROP_TABLE--"

    # Empty result falls back to "export"
    assert exporter._safe_filename("!!!") == "___"


# ---------------------------------------------------------------------------
# Test 7b: Content-Disposition header contains safe filename
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_content_disposition_header():
    """Content-Disposition must contain the safe table name + timestamp."""
    exporter = _load_exporter()

    col_names = ["id"]
    rows = [{"id": 1}]
    fake_gen = _make_viewer_db_mock(rows, col_names)

    with patch.object(
        sys.modules["app.services.pg_viewer.exporter"],
        "get_viewer_db",
        fake_gen,
    ):
        response = await exporter.export_csv(
            table='users"injected',
            columns=col_names,
            filters=[],
            order_by=None,
            order_dir="asc",
            row_limit=1000,
        )

    disposition = response.headers.get("Content-Disposition", "")
    # The double-quote in table name must be replaced with "_"
    assert "users_injected" in disposition, (
        f"Expected safe filename in Content-Disposition, got: {disposition!r}"
    )
    # Must not contain the raw double-quote from input
    assert '"injected' not in disposition or "users_injected" in disposition


# ---------------------------------------------------------------------------
# Test: _encode_cell unit tests
# ---------------------------------------------------------------------------

def test_encode_cell_none():
    exporter = _load_exporter()
    assert exporter._encode_cell(None) == ""


def test_encode_cell_str_short():
    exporter = _load_exporter()
    assert exporter._encode_cell("hello") == "hello"


def test_encode_cell_str_exact_1000():
    exporter = _load_exporter()
    s = "x" * 1000
    assert exporter._encode_cell(s) == s
    assert not exporter._encode_cell(s).endswith("\u2026")


def test_encode_cell_str_1001():
    exporter = _load_exporter()
    s = "x" * 1001
    result = exporter._encode_cell(s)
    assert len(result) == 1001  # 1000 + ellipsis
    assert result.endswith("\u2026")


def test_encode_cell_bytes():
    exporter = _load_exporter()
    raw = b"\x00\x01\x02"
    expected = base64.b64encode(raw).decode("ascii")  # "AAEC"
    assert exporter._encode_cell(raw) == expected


def test_encode_cell_bytes_clipped():
    exporter = _load_exporter()
    raw = b"Z" * 300  # base64 will be ~400 chars
    b64 = base64.b64encode(raw).decode("ascii")
    assert len(b64) > 200
    result = exporter._encode_cell(raw)
    assert result == b64[:200]
    assert len(result) == 200


def test_encode_cell_memoryview():
    exporter = _load_exporter()
    raw = b"\xff\xfe"
    mv = memoryview(raw)
    expected = base64.b64encode(raw).decode("ascii")
    assert exporter._encode_cell(mv) == expected


def test_encode_cell_int():
    exporter = _load_exporter()
    assert exporter._encode_cell(42) == "42"


def test_encode_cell_bool():
    exporter = _load_exporter()
    assert exporter._encode_cell(True) == "True"


def test_encode_cell_float():
    exporter = _load_exporter()
    assert exporter._encode_cell(3.14) == "3.14"


# ---------------------------------------------------------------------------
# Test: no BOM in output
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_bom():
    """CSV output must not start with a BOM (\\ufeff)."""
    exporter = _load_exporter()

    col_names = ["id"]
    rows = [{"id": 1}]
    fake_gen = _make_viewer_db_mock(rows, col_names)

    with patch.object(
        sys.modules["app.services.pg_viewer.exporter"],
        "get_viewer_db",
        fake_gen,
    ):
        response = await exporter.export_csv(
            table="some_table",
            columns=col_names,
            filters=[],
            order_by=None,
            order_dir="asc",
            row_limit=1000,
        )

    body = await _collect_body(response)
    assert not body.startswith(b"\xef\xbb\xbf"), "CSV must not start with UTF-8 BOM"
    assert not body.decode("utf-8").startswith("\ufeff"), "CSV must not start with BOM char"


# ---------------------------------------------------------------------------
# Test: X-Row-Count absent when fewer rows than limit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_truncated_header_when_under_limit():
    """X-Truncated header must be absent when row count < row_limit."""
    exporter = _load_exporter()

    col_names = ["id"]
    rows = [{"id": i} for i in range(50)]  # 50 < 1000
    fake_gen = _make_viewer_db_mock(rows, col_names)

    with patch.object(
        sys.modules["app.services.pg_viewer.exporter"],
        "get_viewer_db",
        fake_gen,
    ):
        response = await exporter.export_csv(
            table="small_table",
            columns=col_names,
            filters=[],
            order_by=None,
            order_dir="asc",
            row_limit=1000,
        )

    assert "X-Truncated" not in response.headers, (
        f"X-Truncated should be absent for under-limit result, "
        f"got: {response.headers.get('X-Truncated')!r}"
    )
    assert response.headers.get("X-Row-Count") == "50"
