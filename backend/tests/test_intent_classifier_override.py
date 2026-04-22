"""Unit tests for intent classifier post-processing override (Fix A3).

These tests do NOT hit any LLM — the LLM client is monkey-patched to return
a clarification response, and we verify the override logic fires (or doesn't).
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_openai_response(payload: dict):
    msg = MagicMock()
    msg.content = json.dumps(payload)
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


_CLARIFICATION_PAYLOAD = {
    "intent": "clarification",
    "confidence": 0.6,
    "entities": {},
    "reasoning": "查詢過於簡短",
    "clarification_options": [{"label": "所有工單列表", "query": "列出所有工單"}],
}


@pytest.fixture
def classifier(monkeypatch):
    from app.services import intent_classifier as ic

    monkeypatch.setattr(ic, "_intent_classifier", None)
    svc = ic.IntentClassifierService()
    svc.anthropic_key = None
    svc.client = MagicMock()
    svc.client.chat = MagicMock()
    svc.client.chat.completions = MagicMock()
    svc.client.chat.completions.create = AsyncMock(
        return_value=_fake_openai_response(_CLARIFICATION_PAYLOAD)
    )
    return svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_override_structured_vehicle_code(classifier):
    """25-char query with vehicle code + LLM clarification → intent=structured."""
    from app.services.intent_classifier import QueryIntent

    query = "TEMU2000 型車油壓避震器檢修紀錄"
    assert len(query) >= 20

    result = asyncio.run(classifier.classify(query))
    assert result.intent == QueryIntent.STRUCTURED
    assert result.confidence == 0.7
    assert result.clarification_options is None


def test_override_structured_keyword(classifier):
    """25-char query with 故障通報 keyword + LLM clarification → intent=structured."""
    from app.services.intent_classifier import QueryIntent

    query = "請問最近一個月的故障通報有哪些問題比較多"
    assert len(query) >= 20

    result = asyncio.run(classifier.classify(query))
    assert result.intent == QueryIntent.STRUCTURED
    assert result.confidence == 0.7


def test_override_knowledge_keyword(classifier):
    """25-char query with SOP keyword + LLM clarification → intent=knowledge."""
    from app.services.intent_classifier import QueryIntent

    query = "集電弓碳條更換SOP程序詳細說明在哪裡可以查到"
    assert len(query) >= 20

    result = asyncio.run(classifier.classify(query))
    assert result.intent == QueryIntent.KNOWLEDGE
    assert result.confidence == 0.7


def test_short_query_stays_clarification(classifier):
    """3-char query ('工單') with LLM clarification → stays clarification (len < 20)."""
    from app.services.intent_classifier import QueryIntent

    query = "工單"
    assert len(query) < 20

    result = asyncio.run(classifier.classify(query))
    assert result.intent == QueryIntent.CLARIFICATION


def test_high_confidence_clarification_not_overridden(classifier):
    """30-char query with LLM confidence=0.9 → override does NOT fire (trust LLM)."""
    from app.services.intent_classifier import QueryIntent

    high_conf_payload = {
        "intent": "clarification",
        "confidence": 0.9,
        "entities": {},
        "reasoning": "真的不明確",
        "clarification_options": [{"label": "工單列表", "query": "列出工單"}],
    }
    classifier.client.chat.completions.create = AsyncMock(
        return_value=_fake_openai_response(high_conf_payload)
    )

    query = "我想查詢一些有關工單的狀態資訊總覽以及最新更新情況"
    assert len(query) >= 20

    result = asyncio.run(classifier.classify(query))
    assert result.intent == QueryIntent.CLARIFICATION
    assert result.confidence == 0.9
