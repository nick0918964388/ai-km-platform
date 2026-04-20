"""Embedding service for text and images."""
import base64
import json
import logging
import os
from io import BytesIO
from pathlib import Path
from typing import Optional

import requests
from PIL import Image

from app.config import get_settings

logger = logging.getLogger(__name__)

# Lazy loading for clients
_openai_client = None
_openai_client_key = None  # remembers (api_key, base_url) used to build _openai_client
_jina_api_key = None
_logged_embedding_config = False

# Fallback defaults (used only when settings lack a value).
OPENAI_EMBEDDING_MODEL_DEFAULT = "text-embedding-3-small"
OPENAI_EMBEDDING_DIMENSION_DEFAULT = 1536

# Jina CLIP model
JINA_CLIP_MODEL = "jina-clip-v1"
JINA_CLIP_DIMENSION = 768
JINA_API_URL = "https://api.jina.ai/v1/embeddings"


def get_embedding_provider() -> str:
    """Get the configured embedding provider."""
    return get_settings().embedding_provider


def _openai_embedding_model() -> str:
    return getattr(get_settings(), "openai_embedding_model", "") or OPENAI_EMBEDDING_MODEL_DEFAULT


def _openai_embedding_base_url() -> str:
    """Optional base_url override (empty string → OpenAI default)."""
    return getattr(get_settings(), "openai_embedding_base_url", "") or ""


def _log_embedding_config_once() -> None:
    """Log active embedding config on first call only."""
    global _logged_embedding_config
    if _logged_embedding_config:
        return
    _logged_embedding_config = True
    settings = get_settings()
    provider = settings.embedding_provider
    if provider == "ollama":
        logger.info(
            "[embedding] provider=%s model=%s endpoint=%s",
            provider, settings.ollama_embedding_model, settings.ollama_base_url,
        )
    else:
        logger.info(
            "[embedding] provider=%s model=%s endpoint=%s",
            provider, _openai_embedding_model(), _openai_embedding_base_url() or "https://api.openai.com",
        )


def get_openai_client():
    """Get or initialize OpenAI client (respects optional base_url override, rebuilds on config change)."""
    global _openai_client, _openai_client_key
    from openai import OpenAI
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    base_url = _openai_embedding_base_url()
    key = (api_key, base_url)
    if _openai_client is None or _openai_client_key != key:
        _openai_client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
        _openai_client_key = key
    return _openai_client


def _ollama_embed(texts: list[str], batch_size: int = 5) -> list[list[float]]:
    """Embed texts using Ollama API with batching to avoid timeouts."""
    _log_embedding_config_once()
    settings = get_settings()
    url = f"{settings.ollama_base_url}/api/embed"
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        logger.info(f"Embedding batch {i // batch_size + 1}/{(len(texts) + batch_size - 1) // batch_size} ({len(batch)} texts)")
        resp = requests.post(
            url,
            json={"model": settings.ollama_embedding_model, "input": batch},
            timeout=180,
        )
        resp.raise_for_status()
        data = resp.json()
        all_embeddings.extend(data["embeddings"])
    return all_embeddings


def get_jina_api_key() -> str:
    """Get Jina API key from secrets file."""
    global _jina_api_key
    if _jina_api_key is None:
        # Try environment variable first
        _jina_api_key = os.environ.get("JINA_API_KEY")
        if not _jina_api_key:
            # Try secrets file
            secrets_path = Path(__file__).parent.parent.parent.parent / ".secrets" / "jina.json"
            if secrets_path.exists():
                with open(secrets_path) as f:
                    secrets = json.load(f)
                    _jina_api_key = secrets.get("api_key")
        if not _jina_api_key:
            raise ValueError("JINA_API_KEY not found in environment or secrets file")
    return _jina_api_key


def embed_text(text: str) -> list[float]:
    """Embed text using configured provider (OpenAI or Ollama)."""
    if get_embedding_provider() == "ollama":
        return _ollama_embed([text])[0]
    _log_embedding_config_once()
    client = get_openai_client()
    response = client.embeddings.create(
        input=text,
        model=_openai_embedding_model(),
    )
    return response.data[0].embedding


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts using configured provider (OpenAI or Ollama)."""
    if not texts:
        return []
    if get_embedding_provider() == "ollama":
        return _ollama_embed(texts)
    _log_embedding_config_once()
    client = get_openai_client()
    response = client.embeddings.create(
        input=texts,
        model=_openai_embedding_model(),
    )
    # Sort by index to maintain order
    sorted_embeddings = sorted(response.data, key=lambda x: x.index)
    return [item.embedding for item in sorted_embeddings]


def embed_image_jina(image_base64: str) -> list[float]:
    """Embed image using Jina CLIP API."""
    api_key = get_jina_api_key()
    
    response = requests.post(
        JINA_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": JINA_CLIP_MODEL,
            "input": [{"image": image_base64}],
        },
        timeout=30,
    )
    response.raise_for_status()
    
    data = response.json()
    return data["data"][0]["embedding"]


def embed_text_jina(text: str) -> list[float]:
    """Embed text using Jina CLIP API (for multimodal search)."""
    api_key = get_jina_api_key()
    
    response = requests.post(
        JINA_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": JINA_CLIP_MODEL,
            "input": [{"text": text}],
        },
        timeout=30,
    )
    response.raise_for_status()
    
    data = response.json()
    return data["data"][0]["embedding"]


def embed_image(image: Image.Image) -> list[float]:
    """Embed image using Jina CLIP API."""
    # Convert PIL Image to base64
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    image_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return embed_image_jina(image_base64)


def embed_image_from_base64(image_base64: str) -> list[float]:
    """Embed image from base64 string."""
    return embed_image_jina(image_base64)


def embed_image_from_bytes(image_bytes: bytes) -> list[float]:
    """Embed image from bytes."""
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    return embed_image_jina(image_base64)


def get_text_embedding_dimension() -> int:
    """Get text embedding dimension based on configured provider."""
    settings = get_settings()
    if get_embedding_provider() == "ollama":
        return settings.ollama_embedding_dimension
    return getattr(settings, "openai_embedding_dimension", OPENAI_EMBEDDING_DIMENSION_DEFAULT)


def get_embedding_info() -> dict:
    """Get current embedding model info."""
    settings = get_settings()
    provider = settings.embedding_provider
    if provider == "ollama":
        return {
            "provider": "ollama",
            "model": settings.ollama_embedding_model,
            "dimension": settings.ollama_embedding_dimension,
            "base_url": settings.ollama_base_url,
        }
    return {
        "provider": "openai",
        "model": _openai_embedding_model(),
        "dimension": getattr(settings, "openai_embedding_dimension", OPENAI_EMBEDDING_DIMENSION_DEFAULT),
        "base_url": _openai_embedding_base_url() or "https://api.openai.com",
    }


def get_image_embedding_dimension() -> int:
    """Get image embedding dimension."""
    return JINA_CLIP_DIMENSION  # Jina CLIP v1
