"""Tests for the dual-score intent routing system.

Covers:
  1. _score_to_intent pure-function boundary conditions (acceptance criteria 1-5)
  2. intent_router default-no-keyword branch returns "hybrid" (AC 6)
  3. classify() with mocked LLM responses maps scores → correct final intent (AC 8)
  4. needs_clarification path produces CLARIFICATION intent
  5. Model parse-failure returns HYBRID (safe net)
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.intent_classifier import (
    IntentClassifierService,
    IntentResult,
    QueryIntent,
    _score_to_intent,
)
from app.services.intent_router import detect_intent


# ---------------------------------------------------------------------------
# 1-5: _score_to_intent boundary conditions
# ---------------------------------------------------------------------------

def test_score_to_intent_structured():
    """AC1: High SQL, low RAG → STRUCTURED."""
    assert _score_to_intent(0.9, 0.1) == QueryIntent.STRUCTURED


def test_score_to_intent_knowledge():
    """AC2: Low SQL, high RAG → KNOWLEDGE."""
    assert _score_to_intent(0.1, 0.9) == QueryIntent.KNOWLEDGE


def test_score_to_intent_both_high():
    """AC3: Both high → HYBRID."""
    assert _score_to_intent(0.8, 0.8) == QueryIntent.HYBRID


def test_score_to_intent_both_low():
    """AC4: Both low → HYBRID (safe net)."""
    assert _score_to_intent(0.2, 0.2) == QueryIntent.HYBRID


def test_score_to_intent_ambiguous_middle():
    """AC5: SQL dominant but RAG not below 0.3 → HYBRID."""
    assert _score_to_intent(0.75, 0.4) == QueryIntent.HYBRID


def test_score_to_intent_exact_boundary_structured():
    """Exactly at thresholds → STRUCTURED."""
    assert _score_to_intent(0.7, 0.29) == QueryIntent.STRUCTURED


def test_score_to_intent_exact_boundary_knowledge():
    """Exactly at thresholds → KNOWLEDGE."""
    assert _score_to_intent(0.29, 0.7) == QueryIntent.KNOWLEDGE


def test_score_to_intent_sql_high_rag_at_boundary():
    """sql >=0.7, rag exactly 0.3 → NOT structured (rag must be < 0.3)."""
    assert _score_to_intent(0.9, 0.3) == QueryIntent.HYBRID


# ---------------------------------------------------------------------------
# 6: intent_router default branch
# ---------------------------------------------------------------------------

def test_detect_intent_no_keyword_returns_hybrid():
    """AC6: Query with no known keywords → hybrid, not rag."""
    result = detect_intent("隨便問一句")
    assert result["intent"] == "hybrid"
    assert result["confidence"] <= 0.5


def test_detect_intent_no_keyword_custom():
    """Query with no SQL or RAG keywords → hybrid default (not rag)."""
    result = detect_intent("請問明天有空嗎")
    assert result["intent"] == "hybrid"


# ---------------------------------------------------------------------------
# 7: system prompt no longer contains banned phrases
# ---------------------------------------------------------------------------

def test_system_prompt_no_banned_phrases():
    """AC7: Old rule-heavy phrasing must be gone from SYSTEM_PROMPT."""
    from app.services.intent_classifier import SYSTEM_PROMPT
    banned = ["4 類別", "追問繼承", "hybrid 嚴格判準", "結構化比較"]
    for phrase in banned:
        assert phrase not in SYSTEM_PROMPT, f"Banned phrase still in SYSTEM_PROMPT: {phrase!r}"


# ---------------------------------------------------------------------------
# 8: classify() with mocked LLM — end-to-end score→intent mapping
# ---------------------------------------------------------------------------

def _make_mock_response(payload: dict) -> MagicMock:
    """Build an AsyncMock that returns a fake OpenAI chat completion."""
    msg = MagicMock()
    msg.content = json.dumps(payload)
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.fixture()
def classifier_anthropic_mocked(monkeypatch):
    """IntentClassifierService configured with anthropic provider, _call_anthropic mocked."""
    svc = object.__new__(IntentClassifierService)
    svc.provider = "anthropic"
    svc.model = "claude-haiku-test"
    svc.anthropic_key = "sk-test"
    svc.client = None
    return svc


@pytest.mark.asyncio
async def test_classify_sql_dominant(classifier_anthropic_mocked, monkeypatch):
    """AC8a: Model returns sql_score=0.9, rag_score=0.1 → STRUCTURED."""
    payload = {"sql_score": 0.9, "rag_score": 0.1, "entities": {}, "reasoning": "工單查詢"}
    monkeypatch.setattr(
        classifier_anthropic_mocked, "_call_anthropic",
        AsyncMock(return_value=json.dumps(payload)),
    )
    result = await classifier_anthropic_mocked.classify("列出最近工單")
    assert result.intent == QueryIntent.STRUCTURED
    assert result.sql_score == 0.9
    assert result.rag_score == 0.1


@pytest.mark.asyncio
async def test_classify_both_low_returns_hybrid(classifier_anthropic_mocked, monkeypatch):
    """AC8b: Model returns sql_score=0.1, rag_score=0.1 → HYBRID (safe net)."""
    payload = {"sql_score": 0.1, "rag_score": 0.1, "entities": {}, "reasoning": "不相關問題"}
    monkeypatch.setattr(
        classifier_anthropic_mocked, "_call_anthropic",
        AsyncMock(return_value=json.dumps(payload)),
    )
    result = await classifier_anthropic_mocked.classify("今天天氣如何")
    assert result.intent == QueryIntent.HYBRID
    assert result.sql_score == 0.1
    assert result.rag_score == 0.1


@pytest.mark.asyncio
async def test_classify_needs_clarification(classifier_anthropic_mocked, monkeypatch):
    """needs_clarification:true → CLARIFICATION intent with options."""
    payload = {
        "sql_score": 0.0,
        "rag_score": 0.0,
        "needs_clarification": True,
        "reasoning": "太模糊",
        "clarification_options": [{"label": "列出工單", "query": "列出工單"}],
    }
    monkeypatch.setattr(
        classifier_anthropic_mocked, "_call_anthropic",
        AsyncMock(return_value=json.dumps(payload)),
    )
    result = await classifier_anthropic_mocked.classify("工單")
    assert result.intent == QueryIntent.CLARIFICATION
    assert result.clarification_options is not None
    assert len(result.clarification_options) > 0


@pytest.mark.asyncio
async def test_classify_parse_failure_returns_hybrid(classifier_anthropic_mocked, monkeypatch):
    """Parse error → IntentResult with HYBRID and zero scores."""
    monkeypatch.setattr(
        classifier_anthropic_mocked, "_call_anthropic",
        AsyncMock(side_effect=RuntimeError("network error")),
    )
    result = await classifier_anthropic_mocked.classify("任何查詢")
    assert result.intent == QueryIntent.HYBRID
    assert result.sql_score == 0.0
    assert result.rag_score == 0.0


# ---------------------------------------------------------------------------
# IntentResult dataclass has the new fields
# ---------------------------------------------------------------------------

def test_intent_result_has_score_fields():
    r = IntentResult(
        intent=QueryIntent.HYBRID,
        confidence=0.5,
        entities={},
        reasoning="test",
        sql_score=0.4,
        rag_score=0.4,
    )
    assert r.sql_score == 0.4
    assert r.rag_score == 0.4


def test_intent_result_score_fields_default_zero():
    """Existing code that constructs IntentResult without sql/rag scores still works."""
    r = IntentResult(
        intent=QueryIntent.STRUCTURED,
        confidence=0.9,
        entities={},
        reasoning="ok",
    )
    assert r.sql_score == 0.0
    assert r.rag_score == 0.0
