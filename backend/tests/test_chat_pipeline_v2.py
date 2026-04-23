"""
S0 Chat Pipeline v2 unit tests.

Test coverage:
  A. Flag OFF  → _should_use_v2 / flag check without hitting v2 code
  B. Flag ON   → run_pipeline_v2 各路徑

All external I/O (DB, Qdrant, Anthropic) is mocked.
"""
from __future__ import annotations

import asyncio
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chat_pipeline_v2 import (
    _should_use_v2,
    run_pipeline_v2,
    PipelineResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid_with_hash(target_mod: int) -> str:
    """Return a uid whose MD5[:8] % 20 == target_mod (brute-force search)."""
    for i in range(10_000):
        uid = f"user_{i}"
        h = int(hashlib.md5(uid.encode()).hexdigest()[:8], 16)
        if h % 20 == target_mod:
            return uid
    raise RuntimeError(f"Could not find uid with hash % 20 == {target_mod}")


_UID_IN  = _uid_with_hash(0)   # will be routed to v2
_UID_OUT = _uid_with_hash(1)   # will NOT be routed to v2


# ---------------------------------------------------------------------------
# A. Flag OFF — _should_use_v2
# ---------------------------------------------------------------------------

class TestGrayscale:
    def test_uid_in_5pct(self):
        """UID that hashes to 0 mod 20 → should use v2."""
        assert _should_use_v2(_UID_IN) is True

    def test_uid_out_of_5pct(self):
        """UID that hashes to non-0 mod 20 → should NOT use v2."""
        assert _should_use_v2(_UID_OUT) is False

    def test_same_uid_stable(self):
        """Same UID always returns same decision (deterministic hash)."""
        uid = "some-fixed-user-uuid"
        decisions = [_should_use_v2(uid) for _ in range(10)]
        assert len(set(decisions)) == 1

    def test_none_returns_false(self):
        """user_id=None (anonymous/no conversation) → False."""
        assert _should_use_v2(None) is False

    def test_empty_string_returns_false(self):
        """Empty string user_id → False."""
        assert _should_use_v2("") is False


# ---------------------------------------------------------------------------
# B. run_pipeline_v2 paths
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(fetchall=lambda: []))
    return db


@pytest.mark.asyncio
async def test_pre_filter_reject_chitchat(mock_db):
    """'你好' → pre_filter_reject."""
    result = await run_pipeline_v2(
        query="你好",
        user_ctx={"id": "u1"},
        db=mock_db,
    )
    assert result.recovery_path == "pre_filter_reject"
    assert result.error is not None


@pytest.mark.asyncio
async def test_pre_filter_reject_too_short(mock_db):
    """'?' → pre_filter_reject (len=1 < 5)."""
    result = await run_pipeline_v2(
        query="?",
        user_ctx={"id": "u1"},
        db=mock_db,
    )
    assert result.recovery_path == "pre_filter_reject"


@pytest.mark.asyncio
async def test_terminology_applied(mock_db):
    """'核簽工單有幾張' → normalized_query contains '核簽中工單', applied_terms non-empty."""
    import pathlib
    # Force reload terminology from the correct path for tests run from repo root
    # tests/ parent[0] → tests, parent[1] → backend, then data/
    yml_path = pathlib.Path(__file__).resolve().parents[1] / "data" / "terminology.yml"
    from app.services.terminology_normalizer.normalizer import reload as _reload
    if yml_path.exists():
        _reload(str(yml_path))

    # Let SkillMatcher miss (no qdrant) → agent_fallback; we patch the agent to avoid LLM call
    with patch(
        "app.services.chat_pipeline_v2._build_skill_agent",
    ) as mock_build:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=MagicMock(
            rows=[], row_count=0, answer="mock answer",
            elapsed_ms=10, tool_traces=[],
        ))
        mock_build.return_value = mock_agent

        result = await run_pipeline_v2(
            query="核簽工單有幾張",
            user_ctx={"id": "u1"},
            db=mock_db,
        )

    assert "核簽中工單" in result.normalized_query
    assert len(result.applied_terms) > 0


@pytest.mark.asyncio
async def test_agent_fallback_path(mock_db):
    """No Qdrant → matcher skipped → agent_fallback."""
    with patch("app.services.chat_pipeline_v2._build_skill_agent") as mock_build:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=MagicMock(
            rows=[{"wonum": "WO001", "status": "APPR"}],
            row_count=1,
            answer="",
            elapsed_ms=500,
            tool_traces=[MagicMock(name="run_sql", input={"sql": "SELECT 1"}, latency_ms=100)],
        ))
        mock_build.return_value = mock_agent

        result = await run_pipeline_v2(
            query="目前核簽中的工單",
            user_ctx={"id": "u1"},
            db=mock_db,
        )

    assert result.recovery_path == "agent_fallback"
    assert result.row_count == 1


@pytest.mark.asyncio
async def test_image_bypass_agent_fallback_image(mock_db):
    """image_base64 present → agent_fallback_image, skips PreFilter."""
    with patch("app.services.chat_pipeline_v2._build_skill_agent") as mock_build:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=MagicMock(
            rows=[], row_count=0, answer="圖片分析結果",
            elapsed_ms=800, tool_traces=[],
        ))
        mock_build.return_value = mock_agent

        result = await run_pipeline_v2(
            query="這個圖片裡的工單是什麼",
            user_ctx={"id": "u1"},
            image_base64="ZmFrZWltYWdl",  # base64 "fakeimage"
            db=mock_db,
        )

    assert result.recovery_path == "agent_fallback_image"
    assert result.image_present is True


@pytest.mark.asyncio
async def test_skill_direct_path(mock_db):
    """SkillMatcher returns hit with score ≥ 0.85 + skill_exec succeeds → skill_direct."""
    mock_qdrant = MagicMock()
    hit = MagicMock()
    hit.score = 0.92
    hit.id = "skill-uuid-001"
    hit.payload = {
        "skill_id": "skill-uuid-001",
        "name": "count_emu_trains",
        "version": 1,
        "is_current": True,
        "active": True,
    }
    mock_qdrant.search = MagicMock(return_value=[hit])

    def mock_embed(text: str) -> list[float]:
        return [0.1] * 384

    with patch("app.services.chat_pipeline_v2._exec_skill") as mock_exec:
        mock_exec.return_value = {
            "sql": "SELECT COUNT(*) FROM maximo_assets WHERE eq4 = 'EMU800'",
            "data": [{"count": 240}],
            "row_count": 1,
            "columns": ["count"],
        }

        result = await run_pipeline_v2(
            query="EMU800 有幾組車組",
            user_ctx={"id": "u1"},
            qdrant_client=mock_qdrant,
            embedder=mock_embed,
            db=mock_db,
        )

    assert result.recovery_path == "skill_direct"
    assert result.row_count == 1
    assert result.skill_name == "count_emu_trains"
    assert result.total_llm_ms == 0


@pytest.mark.asyncio
async def test_skill_exec_failure_falls_back_to_agent(mock_db):
    """skill_exec fails → falls through to agent_fallback."""
    mock_qdrant = MagicMock()
    hit = MagicMock()
    hit.score = 0.90
    hit.id = "skill-uuid-002"
    hit.payload = {
        "skill_id": "skill-uuid-002",
        "name": "failing_skill",
        "version": 1,
        "is_current": True,
        "active": True,
    }
    mock_qdrant.search = MagicMock(return_value=[hit])

    def mock_embed(text: str) -> list[float]:
        return [0.1] * 384

    with patch("app.services.chat_pipeline_v2._exec_skill", return_value=None), \
         patch("app.services.chat_pipeline_v2._build_skill_agent") as mock_build:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=MagicMock(
            rows=[], row_count=0, answer="fallback answer",
            elapsed_ms=300, tool_traces=[],
        ))
        mock_build.return_value = mock_agent

        result = await run_pipeline_v2(
            query="EMU800 有幾組車組",
            user_ctx={"id": "u1"},
            qdrant_client=mock_qdrant,
            embedder=mock_embed,
            db=mock_db,
        )

    assert result.recovery_path == "agent_fallback"


@pytest.mark.asyncio
async def test_total_llm_ms_set_for_agent_fallback(mock_db):
    """total_llm_ms is set from agent elapsed_ms when using agent_fallback."""
    with patch("app.services.chat_pipeline_v2._build_skill_agent") as mock_build:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=MagicMock(
            rows=[], row_count=0, answer="some answer",
            elapsed_ms=1234, tool_traces=[],
        ))
        mock_build.return_value = mock_agent

        result = await run_pipeline_v2(
            query="目前核簽中的工單有哪些",
            user_ctx={"id": "u1"},
            db=mock_db,
        )

    assert result.total_llm_ms == 1234


# ---------------------------------------------------------------------------
# C. _emit_follow_up
# ---------------------------------------------------------------------------

def test_emit_follow_up_sql_result():
    from app.services.chat_pipeline_v2 import _emit_follow_up
    result = PipelineResult(
        recovery_path="skill_direct",
        sql="SELECT ...",
        data=[{"wonum": "WO1"}],
        row_count=1,
    )
    fus = _emit_follow_up(result, "核簽中的工單有幾張")
    assert isinstance(fus, list)


def test_emit_follow_up_no_sql():
    from app.services.chat_pipeline_v2 import _emit_follow_up
    result = PipelineResult(recovery_path="agent_fallback")
    fus = _emit_follow_up(result, "你好")
    assert fus == []
