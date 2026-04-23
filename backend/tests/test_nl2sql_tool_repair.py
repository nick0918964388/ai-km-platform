"""Tests for SQL error-aware repair loop (P2 task).

Acceptance criteria (7):
  AC1  SQL_REPAIR_TOOLS is list[dict], len==3, each has name/description/input_schema
  AC2  exec_inspect_schema success path: mock db → dict with 'columns' list
  AC3  exec_execute_sql rejects non-SELECT
  AC4  exec_execute_sql / exec_sample_rows reject table_name with special chars
  AC5  repair_with_tools full flow: tool_use → tool_result → end_turn → {success, sql}
  AC6  max_tool_calls limit: LLM keeps returning tool_use → stop, return {success: False}
  AC7  anthropic_api_key absent: repair returns {success: False, error: 'no anthropic client'}
       without raising an exception (main flow continues)

Security acceptance criteria (C2 / critic findings):
  SC1  DELETE statement → rejected with FORBIDDEN in error
  SC2  Writable CTE (WITH d AS (DELETE...) SELECT ...) → rejected
  SC3  Multi-statement (SELECT 1; DROP TABLE x) → rejected
  SC4  SQL comment (--) → rejected
  SC5  pg_catalog / information_schema reference → rejected
  SC6  Normal CTE (WITH x AS (SELECT ...) SELECT ...) → allowed
"""
from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.maximo_nl2sql_tools import (
    SQL_REPAIR_TOOLS,
    _is_safe_select,
    exec_execute_sql,
    exec_inspect_schema,
    exec_sample_rows,
    repair_with_tools,
)
from app.services.maximo_nl2sql import MaximoNL2SQL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(rows=None, cols=None, error=None):
    """Build a minimal async SQLAlchemy session mock."""
    db = AsyncMock()

    # begin_nested returns an async context manager
    sp = AsyncMock()
    sp.__aenter__ = AsyncMock(return_value=sp)
    sp.__aexit__ = AsyncMock(return_value=False)
    db.begin_nested = MagicMock(return_value=sp)

    if error:
        db.execute = AsyncMock(side_effect=Exception(error))
    else:
        result_mock = MagicMock()
        result_mock.keys = MagicMock(return_value=list(cols or []))
        result_mock.fetchall = MagicMock(return_value=list(rows or []))
        result_mock.scalar = MagicMock(return_value=len(rows or []))
        db.execute = AsyncMock(return_value=result_mock)

    return db


def _make_anthropic_client(turns: list[dict]) -> AsyncMock:
    """Build a mock Anthropic client that returns each turn in sequence."""
    client = AsyncMock()
    messages_mock = AsyncMock()
    client.messages = messages_mock

    responses = []
    for turn in turns:
        resp = MagicMock()
        resp.stop_reason = turn["stop_reason"]
        content_blocks = []
        for block in turn.get("content", []):
            b = MagicMock()
            b.type = block["type"]
            if block["type"] == "text":
                b.text = block["text"]
            elif block["type"] == "tool_use":
                b.id = block.get("id", "tu_001")
                b.name = block["name"]
                b.input = block.get("input", {})
            content_blocks.append(b)
        resp.content = content_blocks
        responses.append(resp)

    client.messages.create = AsyncMock(side_effect=responses)
    return client


# ---------------------------------------------------------------------------
# AC1: SQL_REPAIR_TOOLS schema validation
# ---------------------------------------------------------------------------


def test_sql_repair_tools_structure():
    """AC1: SQL_REPAIR_TOOLS must be list[dict] of length 3, each with required keys."""
    assert isinstance(SQL_REPAIR_TOOLS, list)
    assert len(SQL_REPAIR_TOOLS) == 3
    required_keys = {"name", "description", "input_schema"}
    for tool in SQL_REPAIR_TOOLS:
        assert isinstance(tool, dict), f"Tool must be dict: {tool}"
        for key in required_keys:
            assert key in tool, f"Tool missing '{key}': {tool}"


def test_sql_repair_tools_names():
    """All three tool names are present."""
    names = {t["name"] for t in SQL_REPAIR_TOOLS}
    assert names == {"inspect_schema", "sample_rows", "execute_sql"}


# ---------------------------------------------------------------------------
# AC2: exec_inspect_schema success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exec_inspect_schema_success():
    """AC2: Mock db returning 2 columns → result contains 'columns' list."""
    # information_schema query → col_name / data_type rows
    # COUNT(*) → scalar 10
    # SELECT * LIMIT 2 → sample rows
    col_rows = [("assetnum", "character varying"), ("status", "character varying")]
    sample_rows_data = [("A001", "OPERATING"), ("A002", "INACTIVE")]

    db = AsyncMock()
    sp = AsyncMock()
    sp.__aenter__ = AsyncMock(return_value=sp)
    sp.__aexit__ = AsyncMock(return_value=False)
    db.begin_nested = MagicMock(return_value=sp)

    call_count = 0

    async def mock_execute(stmt, params=None):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            # information_schema columns query
            result.fetchall = MagicMock(return_value=col_rows)
        elif call_count == 2:
            # COUNT(*)
            result.scalar = MagicMock(return_value=10)
        else:
            # sample rows
            result.keys = MagicMock(return_value=["assetnum", "status"])
            result.fetchall = MagicMock(return_value=sample_rows_data)
        return result

    db.execute = mock_execute

    result = await exec_inspect_schema(db, "maximo_assets")

    assert "columns" in result
    assert isinstance(result["columns"], list)
    assert len(result["columns"]) == 2
    assert result["columns"][0]["name"] == "assetnum"
    assert result["columns"][1]["name"] == "status"


# ---------------------------------------------------------------------------
# AC3: exec_execute_sql rejects non-SELECT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exec_execute_sql_rejects_delete():
    """AC3: DELETE statement → {success: False, error contains 'SELECT'}."""
    db = _make_db()
    result = await exec_execute_sql(db, "DELETE FROM maximo_assets WHERE 1=1")
    assert result["success"] is False
    assert "SELECT" in result["error"]


@pytest.mark.asyncio
async def test_exec_execute_sql_rejects_insert():
    """AC3b: INSERT statement → rejected."""
    db = _make_db()
    result = await exec_execute_sql(db, "INSERT INTO foo VALUES (1)")
    assert result["success"] is False
    assert "SELECT" in result["error"]


@pytest.mark.asyncio
async def test_exec_execute_sql_rejects_update():
    """AC3c: UPDATE statement → rejected."""
    db = _make_db()
    result = await exec_execute_sql(db, "UPDATE foo SET bar=1")
    assert result["success"] is False
    assert "SELECT" in result["error"]


# ---------------------------------------------------------------------------
# AC4: table_name injection prevention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exec_execute_sql_select_allowed():
    """AC3d: Valid SELECT passes whitelist check and reaches db."""
    db = _make_db(rows=[("A001",)], cols=["assetnum"])
    result = await exec_execute_sql(db, "SELECT assetnum FROM maximo_assets LIMIT 1")
    assert result["success"] is True


@pytest.mark.asyncio
async def test_exec_inspect_schema_rejects_injection():
    """AC4: table_name with semicolon → raises / returns error without executing."""
    db = _make_db()
    result = await exec_inspect_schema(db, "maximo_assets; DROP TABLE foo--")
    assert "error" in result
    assert result.get("columns") == [] or result.get("columns") is None
    # DB should NOT have been called with the malicious name
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_exec_sample_rows_rejects_injection():
    """AC4b: table_name with spaces → raises / returns error."""
    db = _make_db()
    result = await exec_sample_rows(db, "maximo_assets WHERE 1=1--")
    assert "error" in result
    db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# AC5: repair_with_tools full flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repair_with_tools_full_flow():
    """AC5: tool_use turn (inspect_schema) → tool_result → end_turn with FIXED_SQL."""
    # DB mock for inspect_schema execution
    db = AsyncMock()
    sp = AsyncMock()
    sp.__aenter__ = AsyncMock(return_value=sp)
    sp.__aexit__ = AsyncMock(return_value=False)
    db.begin_nested = MagicMock(return_value=sp)

    call_idx = 0

    async def mock_execute(stmt, params=None):
        nonlocal call_idx
        call_idx += 1
        result = MagicMock()
        result.fetchall = MagicMock(return_value=[("assetnum", "character varying")])
        result.scalar = MagicMock(return_value=1)
        result.keys = MagicMock(return_value=["assetnum"])
        return result

    db.execute = mock_execute

    # Anthropic client: first turn = tool_use(inspect_schema), second turn = end_turn with SQL
    client = _make_anthropic_client([
        {
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tu_001",
                    "name": "inspect_schema",
                    "input": {"table_name": "maximo_assets"},
                }
            ],
        },
        {
            "stop_reason": "end_turn",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "I found the correct column name.\n\n"
                        "FIXED_SQL:\n"
                        "SELECT assetnum FROM maximo_assets LIMIT 10"
                    ),
                }
            ],
        },
    ])

    result = await repair_with_tools(
        db=db,
        question="列出所有資產",
        last_sql="SELECT asset_num FROM maximo_assets LIMIT 10",
        last_error='column "asset_num" does not exist',
        schema_ctx="maximo_assets: assetnum VARCHAR(30)",
        anthropic_client=client,
        model="claude-sonnet-4-6",
        max_tool_calls=3,
    )

    assert result["success"] is True
    assert result["sql"] == "SELECT assetnum FROM maximo_assets LIMIT 10"
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["tool"] == "inspect_schema"


# ---------------------------------------------------------------------------
# AC6: max_tool_calls limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repair_max_tool_calls_limit():
    """AC6: LLM keeps returning tool_use → stop at max_tool_calls, return {success: False}."""
    db = AsyncMock()
    sp = AsyncMock()
    sp.__aenter__ = AsyncMock(return_value=sp)
    sp.__aexit__ = AsyncMock(return_value=False)
    db.begin_nested = MagicMock(return_value=sp)
    result_mock = MagicMock()
    result_mock.fetchall = MagicMock(return_value=[])
    result_mock.scalar = MagicMock(return_value=0)
    result_mock.keys = MagicMock(return_value=[])
    db.execute = AsyncMock(return_value=result_mock)

    # Every Anthropic turn returns tool_use — this should be capped
    infinite_turns = [
        {
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "tool_use",
                    "id": f"tu_{i:03d}",
                    "name": "inspect_schema",
                    "input": {"table_name": "maximo_assets"},
                }
            ],
        }
        for i in range(10)  # more than max_tool_calls
    ]
    client = _make_anthropic_client(infinite_turns)

    result = await repair_with_tools(
        db=db,
        question="test",
        last_sql="SELECT x FROM t",
        last_error="column x does not exist",
        schema_ctx="",
        anthropic_client=client,
        model="claude-sonnet-4-6",
        max_tool_calls=2,
    )

    assert result["success"] is False
    assert "max_tool_calls" in (result.get("error") or "")
    # Must have stopped at the limit (at most max_tool_calls tool executions)
    assert len(result["tool_calls"]) <= 2


# ---------------------------------------------------------------------------
# AC7: no anthropic client → graceful failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repair_no_anthropic_client():
    """AC7: anthropic_client=None → {success: False, error: 'no anthropic client'}, no exception."""
    db = _make_db()
    result = await repair_with_tools(
        db=db,
        question="test",
        last_sql="SELECT x FROM t",
        last_error="error",
        schema_ctx="",
        anthropic_client=None,
        model="claude-sonnet-4-6",
    )
    assert result["success"] is False
    assert "no anthropic client" in (result.get("error") or "")
    assert result["tool_calls"] == []


# ---------------------------------------------------------------------------
# Additional happy path: exec_execute_sql WITH clause allowed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exec_execute_sql_with_clause_allowed():
    """WITH ... SELECT is a valid SELECT-equivalent and must be accepted."""
    db = _make_db(rows=[("X",)], cols=["val"])
    result = await exec_execute_sql(
        db,
        "WITH cte AS (SELECT 1 AS val) SELECT * FROM cte",
    )
    assert result["success"] is True


# ---------------------------------------------------------------------------
# exec_sample_rows n cap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exec_sample_rows_n_capped():
    """n > 5 must be capped to 5."""
    db = AsyncMock()
    sp = AsyncMock()
    sp.__aenter__ = AsyncMock(return_value=sp)
    sp.__aexit__ = AsyncMock(return_value=False)
    db.begin_nested = MagicMock(return_value=sp)

    captured_params: list = []

    async def mock_execute(stmt, params=None):
        if params:
            captured_params.append(params)
        result = MagicMock()
        result.keys = MagicMock(return_value=["id"])
        result.fetchall = MagicMock(return_value=[(1,), (2,), (3,)])
        return result

    db.execute = mock_execute

    await exec_sample_rows(db, "maximo_assets", n=100)
    # Verify the n value passed to DB was capped at 5
    assert any(p.get("n", 0) <= 5 for p in captured_params)


# ---------------------------------------------------------------------------
# SC: Security acceptance criteria (C2 / critic findings)
# ---------------------------------------------------------------------------


def test_is_safe_select_rejects_delete():
    """SC1: DELETE → rejected, error contains FORBIDDEN."""
    ok, err = _is_safe_select("DELETE FROM maximo_assets WHERE 1=1")
    assert not ok
    assert "FORBIDDEN" in err


def test_is_safe_select_rejects_writable_cte():
    """SC2: WITH d AS (DELETE ...) SELECT ... → rejected (writable CTE)."""
    ok, err = _is_safe_select(
        "WITH d AS (DELETE FROM maximo_assets RETURNING *) SELECT * FROM d"
    )
    assert not ok
    assert "FORBIDDEN" in err


def test_is_safe_select_rejects_writable_cte_update():
    """SC2b: WITH u AS (UPDATE ...) SELECT ... → rejected."""
    ok, err = _is_safe_select(
        "WITH u AS (UPDATE maximo_assets SET status='X' RETURNING *) SELECT * FROM u"
    )
    assert not ok
    assert "FORBIDDEN" in err


def test_is_safe_select_rejects_multi_statement():
    """SC3: SELECT 1; DROP TABLE x → rejected (multi-statement)."""
    ok, err = _is_safe_select("SELECT 1; DROP TABLE maximo_assets")
    assert not ok
    assert "FORBIDDEN" in err


def test_is_safe_select_rejects_comment_dashdash():
    """SC4: -- comment → rejected."""
    ok, err = _is_safe_select("SELECT * FROM maximo_assets -- WHERE 1=0")
    assert not ok
    assert "FORBIDDEN" in err


def test_is_safe_select_rejects_comment_block():
    """SC4b: /* comment */ → rejected."""
    ok, err = _is_safe_select("SELECT /* evil */ * FROM maximo_assets")
    assert not ok
    assert "FORBIDDEN" in err


def test_is_safe_select_rejects_pg_catalog():
    """SC5: pg_catalog reference → rejected (forbidden keyword pg_)."""
    ok, err = _is_safe_select("SELECT * FROM pg_catalog.pg_authid")
    assert not ok
    assert "FORBIDDEN" in err


def test_is_safe_select_rejects_information_schema():
    """SC5b: information_schema reference → rejected."""
    ok, err = _is_safe_select("SELECT * FROM information_schema.tables")
    assert not ok
    assert "FORBIDDEN" in err


def test_is_safe_select_allows_normal_cte():
    """SC6: Normal read-only CTE → allowed."""
    ok, err = _is_safe_select(
        "WITH stats AS (SELECT COUNT(*) AS cnt FROM maximo_assets) SELECT * FROM stats"
    )
    assert ok, f"Expected ok but got err={err}"
    assert err == ""


def test_is_safe_select_allows_plain_select():
    """SC6b: Plain SELECT → allowed."""
    ok, err = _is_safe_select("SELECT assetnum, status FROM maximo_assets LIMIT 10")
    assert ok, f"Expected ok but got err={err}"


@pytest.mark.asyncio
async def test_exec_execute_sql_rejects_writable_cte():
    """SC2 via exec_execute_sql: writable CTE → {success: False, error contains FORBIDDEN}."""
    db = _make_db()
    result = await exec_execute_sql(
        db,
        "WITH d AS (DELETE FROM maximo_assets RETURNING *) SELECT * FROM d",
    )
    assert result["success"] is False
    assert "FORBIDDEN" in result["error"]
    # DB must NOT have been called
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_exec_execute_sql_rejects_multi_statement():
    """SC3 via exec_execute_sql: multi-statement → {success: False, error contains FORBIDDEN}."""
    db = _make_db()
    result = await exec_execute_sql(db, "SELECT 1; DROP TABLE maximo_assets")
    assert result["success"] is False
    assert "FORBIDDEN" in result["error"]
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_exec_execute_sql_rejects_comment():
    """SC4 via exec_execute_sql: SQL comment → rejected."""
    db = _make_db()
    result = await exec_execute_sql(
        db, "SELECT * FROM maximo_assets -- bypass"
    )
    assert result["success"] is False
    assert "FORBIDDEN" in result["error"]
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_exec_execute_sql_rejects_pg_catalog():
    """SC5 via exec_execute_sql: pg_catalog reference → rejected."""
    db = _make_db()
    result = await exec_execute_sql(db, "SELECT * FROM pg_catalog.pg_authid")
    assert result["success"] is False
    assert "FORBIDDEN" in result["error"]
    db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# H2: Mixed text+tool_use block in repair_with_tools
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Bug 6: _strip_markdown_sql strips code fence before security gate
# ---------------------------------------------------------------------------


def test_strip_markdown_sql_strips_fence():
    """Bug 6: SQL wrapped in ```sql fence must be unwrapped."""
    fenced = "```sql\nSELECT 1\n```"
    assert MaximoNL2SQL._strip_markdown_sql(fenced) == "SELECT 1"


def test_strip_markdown_sql_strips_plain_fence():
    """Bug 6b: Plain ``` fence (no language tag) must also be unwrapped."""
    fenced = "```\nSELECT assetnum FROM maximo_assets LIMIT 5\n```"
    result = MaximoNL2SQL._strip_markdown_sql(fenced)
    assert result == "SELECT assetnum FROM maximo_assets LIMIT 5"


def test_strip_markdown_sql_passthrough_plain():
    """Bug 6c: SQL without fences passes through unchanged."""
    sql = "SELECT 1"
    assert MaximoNL2SQL._strip_markdown_sql(sql) == "SELECT 1"


def test_strip_markdown_sql_then_security_gate_passes():
    """Bug 6d: ```sql\\nSELECT 1\\n``` → strip → _is_safe_select accepts it."""
    fenced = "```sql\nSELECT 1\n```"
    stripped = MaximoNL2SQL._strip_markdown_sql(fenced)
    ok, err = _is_safe_select(stripped)
    assert ok, f"Expected safe after strip but got: {err}"


@pytest.mark.asyncio
async def test_repair_mixed_text_and_tool_use_blocks():
    """H2: LLM returns tool_use stop_reason but also includes FIXED_SQL in a text block."""
    db = _make_db(rows=[("A001",)], cols=["assetnum"])

    client = _make_anthropic_client([
        {
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "I can fix this directly.\n\n"
                        "FIXED_SQL:\n"
                        "SELECT assetnum FROM maximo_assets LIMIT 5"
                    ),
                },
                {
                    "type": "tool_use",
                    "id": "tu_001",
                    "name": "inspect_schema",
                    "input": {"table_name": "maximo_assets"},
                },
            ],
        },
    ])

    result = await repair_with_tools(
        db=db,
        question="列出資產",
        last_sql="SELECT asset_id FROM maximo_assets",
        last_error='column "asset_id" does not exist',
        schema_ctx="",
        anthropic_client=client,
        model="claude-sonnet-4-6",
        max_tool_calls=3,
    )

    assert result["success"] is True
    assert result["sql"] == "SELECT assetnum FROM maximo_assets LIMIT 5"
