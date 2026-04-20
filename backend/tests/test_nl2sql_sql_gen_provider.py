"""Tests for Batch 2-C SQL generation provider feature flag.

Verifies `MaximoNL2SQL.__init__` selects the correct LLM provider based on
the `sql_generation_provider` setting (default: anthropic, unchanged behavior;
opt-in: nvidia/ollama).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.maximo_nl2sql import MaximoNL2SQL


def _make_settings(**overrides):
    """Build a mock Settings-like object with the attrs MaximoNL2SQL reads."""
    defaults = {
        # SQL gen feature flag
        "sql_generation_provider": "anthropic",
        "sql_generation_model": "",
        # NVIDIA
        "nvidia_api_key": "",
        "nvidia_base_url": "https://integrate.api.nvidia.com/v1",
        "nvidia_sql_model": "minimaxai/minimax-m2.7",
        # Main LLM provider
        "llm_provider": "anthropic",
        "anthropic_api_key": "sk-ant-test",
        "anthropic_model": "claude-sonnet-4-6",
        # OpenAI
        "openai_api_key": "",
        "openai_model": "gpt-4o",
        # Ollama
        "ollama_chat_url": "http://ollama.webtw.xyz:11434/v1",
        "ollama_chat_api_key": "ollama",
        "ollama_chat_model": "qwen3.5:397b-cloud",
        "ollama_light_model": "gemma4:31b-cloud",
        # Reflection (unrelated, but constructor may read)
        "nl2sql_max_retries": 1,
        "nl2sql_skip_reflection_on_rule_pass": True,
        "nl2sql_reflection_confidence_threshold": 0.3,
    }
    defaults.update(overrides)
    s = MagicMock()
    for k, v in defaults.items():
        setattr(s, k, v)
    return s


def _build_nl2sql(settings):
    """Construct MaximoNL2SQL with patched get_settings."""
    fake_db = MagicMock()
    with patch("app.config.get_settings", return_value=settings):
        return MaximoNL2SQL(fake_db)


# ── Default behavior: anthropic ───────────────────────────────────────────

def test_feature_flag_default_anthropic():
    """Default sql_generation_provider='anthropic' + anthropic key present
    → provider=anthropic, model=claude-sonnet-4-6 (no behavior change)."""
    s = _make_settings()
    svc = _build_nl2sql(s)
    assert svc.provider == "anthropic"
    assert svc.model == "claude-sonnet-4-6"
    assert svc.anthropic_key == "sk-ant-test"
    assert svc.client is None  # anthropic uses httpx, not OpenAI SDK
    assert svc.nvidia_key is None


# ── Nvidia opt-in ─────────────────────────────────────────────────────────

def test_feature_flag_nvidia():
    """sql_generation_provider='nvidia' with nvidia_api_key set → provider=nvidia."""
    s = _make_settings(
        sql_generation_provider="nvidia",
        nvidia_api_key="nvapi-test",
    )
    svc = _build_nl2sql(s)
    assert svc.provider == "nvidia"
    assert svc.model == "minimaxai/minimax-m2.7"
    assert svc.nvidia_key == "nvapi-test"
    assert svc.nvidia_base_url == "https://integrate.api.nvidia.com/v1"
    assert svc.client is not None  # uses AsyncOpenAI client pointed at NVIDIA


def test_feature_flag_nvidia_model_override():
    """sql_generation_model overrides the default nvidia_sql_model."""
    s = _make_settings(
        sql_generation_provider="nvidia",
        nvidia_api_key="nvapi-test",
        sql_generation_model="some-other-model",
    )
    svc = _build_nl2sql(s)
    assert svc.provider == "nvidia"
    assert svc.model == "some-other-model"


def test_feature_flag_nvidia_without_key_falls_back():
    """sql_generation_provider='nvidia' but no key → fall through to llm_provider."""
    s = _make_settings(
        sql_generation_provider="nvidia",
        nvidia_api_key="",  # missing
    )
    svc = _build_nl2sql(s)
    # Falls through to llm_provider=anthropic default
    assert svc.provider == "anthropic"


# ── Ollama opt-in ─────────────────────────────────────────────────────────

def test_feature_flag_ollama():
    """sql_generation_provider='ollama' → use ollama chat endpoint."""
    s = _make_settings(sql_generation_provider="ollama")
    svc = _build_nl2sql(s)
    assert svc.provider == "ollama"
    assert svc.model in ("gemma4:31b-cloud", "qwen3.5:397b-cloud")


# ── Explicit anthropic override (e.g. when llm_provider=ollama globally) ─

def test_feature_flag_anthropic_explicit():
    """sql_generation_provider='anthropic' forces SQL gen to Anthropic even
    if the global llm_provider is something else."""
    s = _make_settings(
        sql_generation_provider="anthropic",
        llm_provider="ollama",  # global default differs
        anthropic_api_key="sk-ant-test",
    )
    svc = _build_nl2sql(s)
    assert svc.provider == "anthropic"
    assert svc.anthropic_key == "sk-ant-test"


# ── Empty flag falls through to llm_provider ──────────────────────────────

def test_empty_flag_uses_llm_provider():
    """Empty string sql_generation_provider → respect llm_provider."""
    s = _make_settings(
        sql_generation_provider="",
        llm_provider="anthropic",
        anthropic_api_key="sk-ant-x",
    )
    svc = _build_nl2sql(s)
    assert svc.provider == "anthropic"


def test_empty_flag_llm_provider_ollama():
    """Empty flag + llm_provider=ollama → ollama."""
    s = _make_settings(
        sql_generation_provider="",
        llm_provider="ollama",
        anthropic_api_key="",
    )
    svc = _build_nl2sql(s)
    assert svc.provider == "ollama"
