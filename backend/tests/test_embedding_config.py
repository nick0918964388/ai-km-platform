"""Embedding provider/model resolution tests.

Guards against regressing back to the hardcoded `text-embedding-3-small`.
No network calls — we monkey-patch both the OpenAI client and requests.post.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_openai_embedding_model_respects_settings(monkeypatch):
    """embed_text() must use settings.openai_embedding_model, not a hardcoded string."""
    from app.services import embedding as emb
    from app.config import get_settings

    # Flip to openai provider with a custom model
    settings = get_settings()
    monkeypatch.setattr(settings, "embedding_provider", "openai", raising=False)
    monkeypatch.setattr(settings, "openai_embedding_model", "text-embedding-3-large", raising=False)
    monkeypatch.setattr(settings, "openai_embedding_base_url", "", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    # Reset lazy client
    monkeypatch.setattr(emb, "_openai_client", None)
    monkeypatch.setattr(emb, "_openai_client_key", None)
    monkeypatch.setattr(emb, "_logged_embedding_config", False)

    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp.data = [MagicMock(embedding=[0.1, 0.2], index=0)]
    fake_client.embeddings.create.return_value = fake_resp

    with patch.object(emb, "get_openai_client", return_value=fake_client):
        out = emb.embed_text("hello")

    assert out == [0.1, 0.2]
    fake_client.embeddings.create.assert_called_once()
    _, kwargs = fake_client.embeddings.create.call_args
    assert kwargs["model"] == "text-embedding-3-large"  # from settings, NOT hardcoded


def test_embedding_info_reports_settings_model(monkeypatch):
    from app.services import embedding as emb
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "embedding_provider", "openai", raising=False)
    monkeypatch.setattr(settings, "openai_embedding_model", "text-embedding-3-large", raising=False)
    monkeypatch.setattr(settings, "openai_embedding_base_url", "https://api.example.com/v1", raising=False)

    info = emb.get_embedding_info()
    assert info["provider"] == "openai"
    assert info["model"] == "text-embedding-3-large"
    assert info["base_url"] == "https://api.example.com/v1"


def test_embedding_info_ollama_unchanged(monkeypatch):
    """Default (ollama) behaviour must not change."""
    from app.services import embedding as emb
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "embedding_provider", "ollama", raising=False)
    info = emb.get_embedding_info()
    assert info["provider"] == "ollama"
    assert info["base_url"] == settings.ollama_base_url
    assert info["model"] == settings.ollama_embedding_model


def test_embed_text_ollama_path(monkeypatch):
    """Ollama provider path must still work."""
    from app.services import embedding as emb
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "embedding_provider", "ollama", raising=False)
    monkeypatch.setattr(emb, "_logged_embedding_config", False)

    fake_resp = MagicMock()
    fake_resp.json.return_value = {"embeddings": [[0.1, 0.2, 0.3]]}
    fake_resp.raise_for_status = MagicMock()

    with patch.object(emb.requests, "post", return_value=fake_resp) as mpost:
        vec = emb.embed_text("hi")

    assert vec == [0.1, 0.2, 0.3]
    mpost.assert_called_once()


def test_no_hardcoded_model_in_module():
    """Module must not reintroduce the hardcoded OPENAI_EMBEDDING_MODEL constant."""
    from app.services import embedding as emb

    assert not hasattr(emb, "OPENAI_EMBEDDING_MODEL"), (
        "embed_text must not reference a hardcoded OPENAI_EMBEDDING_MODEL — use settings.openai_embedding_model"
    )
