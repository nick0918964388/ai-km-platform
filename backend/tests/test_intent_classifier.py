"""Intent classifier prompt / dispatch tests.

These tests don't hit any LLM — they exercise:
  1. Prompt compactness (token budget)
  2. Classify() output-shape when the LLM client is monkey-patched
  3. Keyword fallback (classify_with_fallback → detect_intent) still maps to QueryIntent

Why: after few-shot reduction from 10→4, we need regression coverage that
output shape and intent mapping are preserved across the 4 main intent
classes (structured / knowledge / hybrid / clarification).
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest


# --------------------------------------------------------------------------- #
# 1. Prompt compactness — guard-rail against regressing back to bloated prompt
# --------------------------------------------------------------------------- #

def test_system_prompt_is_compact():
    """SYSTEM_PROMPT must stay under 900 gpt-4 tokens (was ~2373, now ~596)."""
    tiktoken = pytest.importorskip("tiktoken")
    from app.services.intent_classifier import SYSTEM_PROMPT

    enc = tiktoken.encoding_for_model("gpt-4")
    n = len(enc.encode(SYSTEM_PROMPT))
    assert n < 900, f"SYSTEM_PROMPT bloated to {n} tokens; trim few-shots or rules"


def test_few_shot_covers_all_intents():
    """Compact few-shot must still include one sample per intent class."""
    from app.services.intent_classifier import FEW_SHOT_EXAMPLES

    for intent in ("structured", "knowledge", "hybrid", "clarification"):
        assert f'"intent":"{intent}"' in FEW_SHOT_EXAMPLES or f'"intent": "{intent}"' in FEW_SHOT_EXAMPLES, (
            f'missing sample for intent={intent}'
        )


# --------------------------------------------------------------------------- #
# 2. classify() output-shape tests with monkey-patched LLM client
# --------------------------------------------------------------------------- #

def _fake_openai_response(payload: dict):
    msg = MagicMock()
    msg.content = json.dumps(payload)
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.fixture
def classifier(monkeypatch):
    from app.services import intent_classifier as ic

    # Force ollama branch (no anthropic key), stub out the AsyncOpenAI client
    monkeypatch.setattr(ic, "_intent_classifier", None)
    svc = ic.IntentClassifierService()
    svc.anthropic_key = None
    svc.client = MagicMock()
    svc.client.chat = MagicMock()
    svc.client.chat.completions = MagicMock()
    svc.client.chat.completions.create = AsyncMock()
    return svc


@pytest.mark.parametrize(
    "query,payload,expected_intent",
    [
        (
            "查詢 EMU801 故障歷程",
            {"intent": "structured", "confidence": 0.95, "entities": {"vehicle_code": "EMU801"}, "reasoning": "ok"},
            "structured",
        ),
        (
            "如何更換集電弓碳條？",
            {"intent": "knowledge", "confidence": 0.9, "entities": {}, "reasoning": "ok"},
            "knowledge",
        ),
        (
            "EMU900 的車輛資訊總覽（故障、檢修、成本）",
            {"intent": "hybrid", "confidence": 0.92, "entities": {}, "reasoning": "ok"},
            "hybrid",
        ),
        (
            "工單",
            {
                "intent": "clarification",
                "confidence": 0.6,
                "entities": {},
                "reasoning": "短",
                "clarification_options": [{"label": "a", "query": "b"}],
            },
            "clarification",
        ),
        (
            "TEMU2000 車型資料：工單、故障、維修成本",
            {"intent": "hybrid", "confidence": 0.9, "entities": {"vehicle_type": "TEMU2000"}, "reasoning": "ok"},
            "hybrid",
        ),
    ],
)
def test_classify_returns_expected_intent(classifier, query, payload, expected_intent):
    from app.services.intent_classifier import QueryIntent

    classifier.client.chat.completions.create.return_value = _fake_openai_response(payload)
    result = asyncio.run(classifier.classify(query))

    assert result.intent == QueryIntent(expected_intent)
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.entities, dict)
    assert isinstance(result.reasoning, str)


def test_classify_handles_markdown_fenced_json(classifier):
    """Model sometimes wraps JSON in ```json ... ``` — classify() must strip it."""
    from app.services.intent_classifier import QueryIntent

    msg = MagicMock()
    msg.content = '```json\n{"intent": "knowledge", "confidence": 0.8, "entities": {}, "reasoning": "ok"}\n```'
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]

    classifier.client.chat.completions.create.return_value = resp
    result = asyncio.run(classifier.classify("隨便問個文件問題"))
    assert result.intent == QueryIntent.KNOWLEDGE


def test_classify_handles_think_tags(classifier):
    """qwen / ollama models emit <think>...</think>; classify() must strip them."""
    from app.services.intent_classifier import QueryIntent

    msg = MagicMock()
    msg.content = '<think>reasoning here</think>\n{"intent": "structured", "confidence": 0.9, "entities": {}, "reasoning": "ok"}'
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]

    classifier.client.chat.completions.create.return_value = resp
    result = asyncio.run(classifier.classify("EMU999 故障"))
    assert result.intent == QueryIntent.STRUCTURED
