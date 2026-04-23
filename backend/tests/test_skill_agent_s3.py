"""
S3 — Skill Agent Fallback Tests

7 acceptance criteria:

1. mock LLM 回 run_skill("count_emu_trains", {...}) → agent 實際呼叫 skill_runner → 回 rows
2. 第一輪 DELETE FROM ... → run_sql 回 error block → 第二輪 SELECT → 成功
3. 帶 history [{q:"EMU800 故障", sql:"...", row_count:10}] → context 含 prev_sql / prev_row_count
4. row_count=0 + validate_enabled=True → validate=no → 再跑一輪；flag off → 直接回 0 rows
5. row_count=5000, threshold_upper=10000 → 不觸發 validate，直接回結果
6. 10s 超時硬中斷 → partial + terminal_reason="timeout"
7. 帶 image_base64 → LLM messages 含 {type:"image", source:...} block，trace image_present=True

All tests are unit-level: no real LLM / DB / Qdrant calls.
"""
from __future__ import annotations

import asyncio
import base64
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.maximo_tools.base import UserContext
from app.services.skill_agent.loop import AgentResult, SkillAgentFallback, _build_user_content, detect_media_type
from app.services.skill_agent.context_builder import build_system_context
from app.services.skill_agent.validator import should_validate
from app.services.skill_agent.tools import _is_safe_select


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_user_ctx(**overrides) -> UserContext:
    defaults = dict(user_id="u-test", role="admin")
    defaults.update(overrides)
    return UserContext(**defaults)


def _text_block(text: str) -> MagicMock:
    b = MagicMock()
    b.type = "text"
    b.text = text
    return b


def _tool_use_block(name: str, input_data: dict, block_id: str = "tu_001") -> MagicMock:
    b = MagicMock()
    b.type = "tool_use"
    b.name = name
    b.input = input_data
    b.id = block_id
    return b


def _make_response(stop_reason: str, blocks: list) -> MagicMock:
    r = MagicMock()
    r.stop_reason = stop_reason
    r.content = blocks
    return r


def _end_turn_response(text: str = "完成") -> MagicMock:
    return _make_response("end_turn", [_text_block(text)])


# ---------------------------------------------------------------------------
# Test 1 — run_skill → skill_runner invoked → rows returned
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_skill_invokes_skill_runner():
    """
    LLM 回 tool_use run_skill("count_emu_trains", {...})
    → agent 呼叫 skill_runner
    → skill_runner 回 rows
    → AgentResult.rows 非空
    """
    skill_rows = [{"vehicle_type": "EMU", "count": 42}]

    async def fake_skill_runner(name: str, params: dict, user_ctx) -> dict:
        assert name == "count_emu_trains"
        # row_count represents the actual count value from the query (42),
        # not the number of result rows (which is 1, containing the aggregate)
        return {"rows": skill_rows, "row_count": 42}

    # Turn 1: LLM decides to call run_skill
    # Turn 2: LLM ends (after seeing tool result)
    call_count = [0]

    async def fake_llm(system: str, messages: list, tools: list) -> Any:
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_response("tool_use", [
                _tool_use_block("run_skill", {"name": "count_emu_trains", "params": {"vehicle_class": "EMU"}})
            ])
        return _end_turn_response("EMU 車組共 42 組")

    agent = SkillAgentFallback(
        llm_call=fake_llm,
        skill_runner=fake_skill_runner,
    )
    ctx = _make_user_ctx()

    with patch("app.services.skill_agent.loop.get_settings") as mock_settings:
        mock_settings.return_value.skill_agent_validate_enabled = False
        mock_settings.return_value.skill_agent_validate_threshold_upper = 10000
        result = await agent.run("EMU 車組有幾組", ctx)

    assert result.success is True
    assert result.rows == skill_rows
    assert result.row_count == 42
    assert result.turns_used >= 1
    # Verify skill tool trace recorded
    skill_traces = [t for t in result.tool_traces if t.name == "run_skill"]
    assert len(skill_traces) == 1
    assert skill_traces[0].input["name"] == "count_emu_trains"


# ---------------------------------------------------------------------------
# Test 2 — DELETE → error block → self-correct with SELECT → success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_error_self_corrects_to_select():
    """
    Turn 1: LLM produces run_sql("DELETE FROM maximo_assets")
    → _is_safe_select blocks → error tool_result returned to LLM
    Turn 2: LLM sees error, issues SELECT → success
    """
    select_rows = [{"assetnum": "A001", "status": "OPERATING"}]
    call_count = [0]

    async def fake_llm(system: str, messages: list, tools: list) -> Any:
        call_count[0] += 1
        if call_count[0] == 1:
            # First turn: DELETE (unsafe)
            return _make_response("tool_use", [
                _tool_use_block("run_sql", {"sql": "DELETE FROM maximo_assets WHERE status='DECOMMISSIONED'"}, "tu_001")
            ])
        if call_count[0] == 2:
            # Second turn: self-corrected SELECT
            return _make_response("tool_use", [
                _tool_use_block("run_sql", {"sql": "SELECT assetnum, status FROM maximo_assets WHERE status='OPERATING'"}, "tu_002")
            ])
        # Third call: end
        return _end_turn_response("查詢完成")

    # Mock DB pool — only called on the valid SELECT
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    # asyncpg row mock
    mock_row = MagicMock()
    mock_row.keys.return_value = ["assetnum", "status"]
    mock_row.__iter__ = lambda self: iter(["A001", "OPERATING"])
    mock_conn.fetch = AsyncMock(return_value=[mock_row])

    agent = SkillAgentFallback(llm_call=fake_llm, db_pool=mock_pool)
    ctx = _make_user_ctx()

    with patch("app.services.skill_agent.loop.get_settings") as mock_settings:
        mock_settings.return_value.skill_agent_validate_enabled = False
        mock_settings.return_value.skill_agent_validate_threshold_upper = 10000
        # Patch execute_run_sql to avoid real DB dependency
        with patch("app.services.skill_agent.loop.execute_run_sql") as mock_exec:
            # First call (DELETE): returns error
            # Second call (SELECT): returns rows
            mock_exec.side_effect = [
                {"error": "只允許 SELECT 查詢，收到：DELETE", "rows": [], "row_count": 0, "columns": []},
                {"rows": select_rows, "row_count": 1, "columns": ["assetnum", "status"]},
            ]
            result = await agent.run("查詢運行中的車輛", ctx)

    assert result.success is True
    # First tool call should be DELETE (error), second should be SELECT (rows)
    sql_traces = [t for t in result.tool_traces if t.name == "run_sql"]
    assert len(sql_traces) == 2
    assert "error" in sql_traces[0].output
    assert sql_traces[1].output["row_count"] == 1
    assert result.rows == select_rows


# ---------------------------------------------------------------------------
# Test 3 — conversation history → context contains prev_sql / prev_row_count
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conversation_history_injected_into_context():
    """
    帶 history [{q:"EMU800 故障", sql:"SELECT ...", row_count:10}]
    → build_system_context 產生的 context 含 prev_sql / prev_row_count
    """
    history = [
        {
            "q": "EMU800 故障",
            "sql": "SELECT ticketid FROM maximo_fault_reports WHERE vehicle_type='EMU800'",
            "row_count": 10,
            "intent": "query_fault_reports",
        }
    ]
    context = build_system_context(conversation_history=history)

    assert "prev_sql" in context
    assert "prev_row_count" in context
    assert "10" in context  # row_count value
    # SQL should be truncated but present
    assert "maximo_fault_reports" in context

    # The intent label (first 30 chars of q) is included as prev_intent — that's safe.
    # "EMU800 故障" is 9 chars, well within 30-char limit, so it appears as prev_intent value.
    assert "EMU800" in context  # intent label derived from q[:30]


@pytest.mark.asyncio
async def test_history_truncated_to_3_turns():
    """history > 3 turns → only last 3 kept."""
    history = [
        {"q": f"query {i}", "sql": f"SELECT {i}", "row_count": i}
        for i in range(6)
    ]
    context = build_system_context(conversation_history=history)
    # Only turns 3,4,5 should appear (last 3)
    assert "turn1" in context
    assert "turn2" in context
    assert "turn3" in context
    # Should NOT have turn4 (only 3 turns max)
    assert "turn4" not in context


@pytest.mark.asyncio
async def test_agent_injects_history_via_context_builder():
    """
    Full agent run with history → system prompt contains recent_context block.
    """
    history = [{"q": "EMU800 故障", "sql": "SELECT ...", "row_count": 10}]
    captured_system = [None]

    async def capturing_llm(system: str, messages: list, tools: list) -> Any:
        captured_system[0] = system
        return _end_turn_response("EMU3000 故障查詢完成")

    agent = SkillAgentFallback(llm_call=capturing_llm)
    ctx = _make_user_ctx()

    with patch("app.services.skill_agent.loop.get_settings") as mock_settings:
        mock_settings.return_value.skill_agent_validate_enabled = False
        mock_settings.return_value.skill_agent_validate_threshold_upper = 10000
        await agent.run("那 EMU3000 呢", ctx, conversation_history=history)

    assert captured_system[0] is not None
    assert "prev_sql" in captured_system[0] or "recent_context" in captured_system[0]
    assert "prev_row_count" in captured_system[0]


# ---------------------------------------------------------------------------
# Test 4 — row_count=0 + validate_enabled → validate=no → extra turn
#          flag off → directly returns 0 rows (no validate)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_triggers_on_zero_rows_flag_on():
    """
    row_count=0 + validate_enabled=True → validate called → no → extra turn
    """
    call_count = [0]

    async def fake_llm(system: str, messages: list, tools: list) -> Any:
        call_count[0] += 1
        if call_count[0] == 1:
            # Turn 1: run_sql returns 0 rows
            return _make_response("tool_use", [
                _tool_use_block("run_sql", {"sql": "SELECT * FROM maximo_assets WHERE vehicle_type='INVALID'"})
            ])
        # Turn 2+: end (after validate re-injection)
        return _end_turn_response("未找到資料，已嘗試修正")

    async def fake_llm_for_validate(system: str, messages: list, tools: list) -> Any:
        # Simulate validate returning "no"
        r = MagicMock()
        r.stop_reason = "end_turn"
        r.content = [_text_block("no\n這個結果無法回答問題")]
        return r

    with patch("app.services.skill_agent.loop.execute_run_sql") as mock_sql:
        mock_sql.return_value = {"rows": [], "row_count": 0, "columns": []}

        with patch("app.services.skill_agent.loop.run_validate") as mock_validate:
            mock_validate.return_value = (False, "no — 結果為空無法回答")

            with patch("app.services.skill_agent.loop.should_validate", return_value=True):
                agent = SkillAgentFallback(llm_call=fake_llm)
                ctx = _make_user_ctx()

                with patch("app.services.skill_agent.loop.get_settings") as mock_settings:
                    mock_settings.return_value.skill_agent_validate_enabled = True
                    mock_settings.return_value.skill_agent_validate_threshold_upper = 10000
                    result = await agent.run("EMU800 故障列表", ctx)

    assert result.validate_result == "no"
    # Agent should have used more than 1 turn (validate triggered extra turn)
    assert result.turns_used >= 2


@pytest.mark.asyncio
async def test_validate_skipped_when_flag_off():
    """
    validate_enabled=False → validate 不執行 → 直接回 0 rows，validate_result="skipped"
    """
    call_count = [0]

    async def fake_llm(system: str, messages: list, tools: list) -> Any:
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_response("tool_use", [
                _tool_use_block("run_sql", {"sql": "SELECT * FROM maximo_assets WHERE vehicle_type='GHOST'"})
            ])
        return _end_turn_response("查無資料")

    with patch("app.services.skill_agent.loop.execute_run_sql") as mock_sql:
        mock_sql.return_value = {"rows": [], "row_count": 0, "columns": []}

        with patch("app.services.skill_agent.loop.run_validate") as mock_validate:
            agent = SkillAgentFallback(llm_call=fake_llm)
            ctx = _make_user_ctx()

            with patch("app.services.skill_agent.loop.get_settings") as mock_settings:
                mock_settings.return_value.skill_agent_validate_enabled = False
                mock_settings.return_value.skill_agent_validate_threshold_upper = 10000
                result = await agent.run("查詢 GHOST 車型", ctx)

    mock_validate.assert_not_called()
    assert result.validate_result == "skipped"
    assert result.row_count == 0


# ---------------------------------------------------------------------------
# Test 5 — row_count=5000, threshold_upper=10000 → validate NOT triggered
# ---------------------------------------------------------------------------

def test_should_validate_within_threshold():
    """row_count=5000 < threshold_upper=10000 → should_validate returns False."""
    assert should_validate(5000, enabled=True, threshold_upper=10000) is False


def test_should_validate_above_threshold():
    """row_count=15000 > threshold_upper=10000 → should_validate returns True."""
    assert should_validate(15000, enabled=True, threshold_upper=10000) is True


def test_should_validate_zero():
    """row_count=0 + enabled → should_validate returns True."""
    assert should_validate(0, enabled=True, threshold_upper=10000) is True


def test_should_validate_disabled():
    """enabled=False → always False."""
    assert should_validate(0, enabled=False, threshold_upper=10000) is False
    assert should_validate(50000, enabled=False, threshold_upper=10000) is False


@pytest.mark.asyncio
async def test_validate_not_triggered_at_5000_rows():
    """
    Full agent run: row_count=5000, threshold_upper=10000
    → validate should NOT be called.
    """
    call_count = [0]

    async def fake_llm(system: str, messages: list, tools: list) -> Any:
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_response("tool_use", [
                _tool_use_block("run_sql", {"sql": "SELECT * FROM maximo_assets"})
            ])
        return _end_turn_response("查詢完成")

    with patch("app.services.skill_agent.loop.execute_run_sql") as mock_sql:
        mock_sql.return_value = {
            "rows": [{"assetnum": f"A{i}"} for i in range(5000)],
            "row_count": 5000,
            "columns": ["assetnum"],
        }
        with patch("app.services.skill_agent.loop.run_validate") as mock_validate:
            agent = SkillAgentFallback(llm_call=fake_llm)
            ctx = _make_user_ctx()

            with patch("app.services.skill_agent.loop.get_settings") as mock_settings:
                mock_settings.return_value.skill_agent_validate_enabled = True
                mock_settings.return_value.skill_agent_validate_threshold_upper = 10000
                result = await agent.run("列出所有車輛", ctx)

    mock_validate.assert_not_called()
    assert result.validate_result == "skipped"
    assert result.row_count == 5000


# ---------------------------------------------------------------------------
# Test 6 — 10s hard timeout → partial result + terminal_reason="timeout"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hard_timeout_returns_partial():
    """
    LLM call sleeps forever → asyncio.wait_for(total=10s) catches it.
    We patch total timeout to 0.05s so the test runs fast.
    terminal_reason="timeout", success=False.
    """
    async def slow_llm(system: str, messages: list, tools: list) -> Any:
        await asyncio.sleep(60)  # far exceeds any timeout

    agent = SkillAgentFallback(llm_call=slow_llm)
    ctx = _make_user_ctx()

    import app.services.skill_agent.loop as loop_module
    original = loop_module._TOTAL_TIMEOUT_SEC

    with patch("app.services.skill_agent.loop.get_settings") as mock_settings:
        mock_settings.return_value.skill_agent_validate_enabled = False
        mock_settings.return_value.skill_agent_validate_threshold_upper = 10000
        # Patch total timeout to tiny value for fast test
        with patch.object(loop_module, "_TOTAL_TIMEOUT_SEC", 0.05):
            result = await agent.run("長時間查詢", ctx)

    assert result.success is False
    assert result.terminal_reason == "timeout"
    assert result.elapsed_ms >= 0


@pytest.mark.asyncio
async def test_per_llm_timeout_returns_timeout():
    """
    Per-LLM-call timeout (5s) also triggers terminal_reason=timeout.
    We patch _PER_LLM_TIMEOUT_SEC to 0.05s.
    """
    async def slow_llm(system: str, messages: list, tools: list) -> Any:
        await asyncio.sleep(60)

    agent = SkillAgentFallback(llm_call=slow_llm)
    ctx = _make_user_ctx()

    import app.services.skill_agent.loop as loop_module

    with patch("app.services.skill_agent.loop.get_settings") as mock_settings:
        mock_settings.return_value.skill_agent_validate_enabled = False
        mock_settings.return_value.skill_agent_validate_threshold_upper = 10000
        with patch.object(loop_module, "_PER_LLM_TIMEOUT_SEC", 0.05):
            with patch.object(loop_module, "_TOTAL_TIMEOUT_SEC", 1.0):
                result = await agent.run("超時查詢", ctx)

    assert result.success is False
    assert result.terminal_reason == "timeout"


# ---------------------------------------------------------------------------
# Test 7 — image_base64 → LLM messages contain image block, trace image_present=True
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_image_base64_injected_into_messages():
    """
    image_base64 非空 → first user message 含 {type:"image", source:...} block
    → AgentResult.image_present=True
    """
    # 1x1 white JPEG base64
    fake_image_b64 = base64.b64encode(b"\xff\xd8\xff\xe0fake_jpeg_bytes").decode()

    captured_messages = [None]

    async def capturing_llm(system: str, messages: list, tools: list) -> Any:
        if captured_messages[0] is None:
            captured_messages[0] = messages
        return _end_turn_response("分析完成")

    agent = SkillAgentFallback(llm_call=capturing_llm)
    ctx = _make_user_ctx()

    with patch("app.services.skill_agent.loop.get_settings") as mock_settings:
        mock_settings.return_value.skill_agent_validate_enabled = False
        mock_settings.return_value.skill_agent_validate_threshold_upper = 10000
        result = await agent.run("這個圖片顯示什麼故障", ctx, image_base64=fake_image_b64)

    assert result.image_present is True

    # Check the first user message contains image block
    first_message = captured_messages[0][0]
    assert first_message["role"] == "user"
    content = first_message["content"]
    assert isinstance(content, list)

    image_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "image"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["source"]["type"] == "base64"
    assert image_blocks[0]["source"]["data"] == fake_image_b64

    # Text block also present
    text_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "text"]
    assert len(text_blocks) == 1
    assert "故障" in text_blocks[0]["text"]


def test_build_user_content_with_image():
    """_build_user_content with image_base64 → image block first, then text."""
    b64 = base64.b64encode(b"fake").decode()
    content = _build_user_content("查詢問題", b64)
    assert content[0]["type"] == "image"
    assert content[0]["source"]["data"] == b64
    assert content[1]["type"] == "text"
    assert content[1]["text"] == "查詢問題"


def test_build_user_content_without_image():
    """_build_user_content without image → only text block."""
    content = _build_user_content("查詢問題", None)
    assert len(content) == 1
    assert content[0]["type"] == "text"


# ---------------------------------------------------------------------------
# Additional unit tests — _is_safe_select, context_builder
# ---------------------------------------------------------------------------

def test_is_safe_select_blocks_delete():
    safe, reason = _is_safe_select("DELETE FROM maximo_assets")
    assert safe is False
    assert "SELECT" in reason or "DELETE" in reason


def test_is_safe_select_allows_select():
    safe, reason = _is_safe_select("SELECT * FROM maximo_assets WHERE status='OPERATING'")
    assert safe is True
    assert reason == ""


def test_is_safe_select_allows_unknown_table():
    """_is_safe_select (from maximo_nl2sql_tools) is keyword-only — table allowlist
    is NOT checked here (it's done by validate_sql / _run_security_gates).
    An unknown table name passes the static keyword guard.
    """
    safe, reason = _is_safe_select("SELECT * FROM secret_table")
    assert safe is True, (
        "maximo_nl2sql_tools._is_safe_select does not check table names; "
        f"got reason={reason!r}"
    )


def test_is_safe_select_blocks_semicolon():
    safe, reason = _is_safe_select("SELECT 1; DROP TABLE maximo_assets")
    assert safe is False


def test_is_safe_select_blocks_comment():
    safe, reason = _is_safe_select("SELECT * FROM maximo_assets -- comment")
    assert safe is False


def test_context_builder_no_history():
    """No history → no recent_context block, but schema present."""
    ctx = build_system_context(conversation_history=None)
    assert "maximo_assets" in ctx
    assert "recent_context" not in ctx


def test_context_builder_with_skills():
    """Matched skills injected into matched_skills block."""
    skills = [
        {"name": "count_emu_trains", "description": "計算 EMU 車組數量"},
        {"name": "query_faults", "description": "查詢故障通報"},
    ]
    ctx = build_system_context(matched_skills=skills)
    assert "count_emu_trains" in ctx
    assert "query_faults" in ctx
    assert "matched_skills" in ctx


# ---------------------------------------------------------------------------
# HIGH 3 — detect_media_type magic byte detection
# ---------------------------------------------------------------------------

def test_detect_media_type_png():
    """PNG magic bytes → image/png."""
    import base64
    png_bytes = b'\x89PNG\r\n\x1a\n' + b'\x00' * 20
    b64 = base64.b64encode(png_bytes).decode()
    assert detect_media_type(b64) == "image/png"


def test_detect_media_type_jpeg():
    """JPEG magic bytes → image/jpeg."""
    import base64
    jpeg_bytes = b'\xff\xd8\xff\xe0' + b'\x00' * 20
    b64 = base64.b64encode(jpeg_bytes).decode()
    assert detect_media_type(b64) == "image/jpeg"


def test_detect_media_type_webp():
    """WEBP magic bytes → image/webp."""
    import base64
    webp_bytes = b'RIFF\x00\x00\x00\x00WEBP' + b'\x00' * 4
    b64 = base64.b64encode(webp_bytes).decode()
    assert detect_media_type(b64) == "image/webp"


def test_detect_media_type_gif():
    """GIF89a magic bytes → image/gif."""
    import base64
    gif_bytes = b'GIF89a' + b'\x00' * 20
    b64 = base64.b64encode(gif_bytes).decode()
    assert detect_media_type(b64) == "image/gif"


def test_detect_media_type_unknown_fallback():
    """Unknown bytes → fallback image/jpeg."""
    import base64
    unknown = b'\x00\x01\x02\x03' * 10
    b64 = base64.b64encode(unknown).decode()
    assert detect_media_type(b64) == "image/jpeg"


def test_image_base64_uses_correct_media_type():
    """_build_user_content detects PNG and sets image/png, not hardcoded image/jpeg."""
    import base64
    png_bytes = b'\x89PNG\r\n\x1a\n' + b'\x00' * 20
    b64 = base64.b64encode(png_bytes).decode()
    content = _build_user_content("what is this", b64)
    image_block = content[0]
    assert image_block["source"]["media_type"] == "image/png"


# ---------------------------------------------------------------------------
# HIGH 4 — WITH CTE allowed by _is_safe_select (from maximo_nl2sql_tools)
# ---------------------------------------------------------------------------

def test_is_safe_select_allows_read_only_cte():
    """WITH x AS (SELECT ...) SELECT ... must pass _is_safe_select."""
    sql = "WITH recent AS (SELECT wonum FROM maximo_cm_workorders WHERE status='WAPPR') SELECT * FROM recent"
    safe, reason = _is_safe_select(sql)
    assert safe is True, f"Expected safe, got reason: {reason}"


def test_is_safe_select_blocks_writable_cte():
    """WITH x AS (DELETE ...) SELECT must be blocked."""
    sql = "WITH d AS (DELETE FROM maximo_assets WHERE 1=1) SELECT 1"
    safe, reason = _is_safe_select(sql)
    assert safe is False
    assert "CTE" in reason or "FORBIDDEN" in reason
