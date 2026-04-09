"""Embedding service for text and images."""
import base64
import json
import os
from io import BytesIO
from pathlib import Path
from typing import Optional

import requests
from PIL import Image

# Lazy loading for clients
_openai_client = None
_jina_api_key = None
_local_model = None

# Embedding provider configuration
EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "local")  # "openai", "ollama", or "local"

# OpenAI embedding model
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
OPENAI_EMBEDDING_DIMENSION = 1536

# Ollama embedding configuration
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://192.168.1.161:11434")
OLLAMA_EMBEDDING_MODEL = os.environ.get("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text:latest")
OLLAMA_EMBEDDING_DIMENSION = int(os.environ.get("OLLAMA_EMBEDDING_DIMENSION", "768"))

# Local sentence-transformers embedding
LOCAL_EMBEDDING_MODEL = os.environ.get("TEXT_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
LOCAL_EMBEDDING_DIMENSION = 384  # all-MiniLM-L6-v2 dimension

# Jina CLIP model
JINA_CLIP_MODEL = "jina-clip-v1"
JINA_CLIP_DIMENSION = 768
JINA_API_URL = "https://api.jina.ai/v1/embeddings"


def get_openai_client():
    """Get or initialize OpenAI client."""
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


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


def embed_text_ollama(text: str) -> list[float]:
    """Embed text using Ollama API."""
    response = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={
            "model": OLLAMA_EMBEDDING_MODEL,
            "input": text
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    return data["embeddings"][0]


def embed_texts_ollama(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts using Ollama API."""
    if not texts:
        return []
    response = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={
            "model": OLLAMA_EMBEDDING_MODEL,
            "input": texts
        },
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    return data["embeddings"]


def embed_text_openai(text: str) -> list[float]:
    """Embed text using OpenAI API."""
    client = get_openai_client()
    response = client.embeddings.create(
        input=text,
        model=OPENAI_EMBEDDING_MODEL
    )
    return response.data[0].embedding


def embed_texts_openai(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts using OpenAI API."""
    if not texts:
        return []
    client = get_openai_client()
    response = client.embeddings.create(
        input=texts,
        model=OPENAI_EMBEDDING_MODEL
    )
    # Sort by index to maintain order
    sorted_embeddings = sorted(response.data, key=lambda x: x.index)
    return [item.embedding for item in sorted_embeddings]


def get_local_model():
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer
        _local_model = SentenceTransformer(LOCAL_EMBEDDING_MODEL)
    return _local_model


def embed_text_local(text: str) -> list[float]:
    model = get_local_model()
    return model.encode(text).tolist()


def embed_texts_local(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = get_local_model()
    return model.encode(texts).tolist()


def embed_text(text: str) -> list[float]:
    """Embed text using configured provider."""
    if EMBEDDING_PROVIDER == "local":
        return embed_text_local(text)
    elif EMBEDDING_PROVIDER == "ollama":
        return embed_text_ollama(text)
    else:
        return embed_text_openai(text)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts using configured provider."""
    if EMBEDDING_PROVIDER == "local":
        return embed_texts_local(texts)
    elif EMBEDDING_PROVIDER == "ollama":
        return embed_texts_ollama(texts)
    else:
        return embed_texts_openai(texts)


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
    if EMBEDDING_PROVIDER == "local":
        return LOCAL_EMBEDDING_DIMENSION  # all-MiniLM-L6-v2
    elif EMBEDDING_PROVIDER == "ollama":
        return OLLAMA_EMBEDDING_DIMENSION  # Qwen3 embedding
    else:
        return OPENAI_EMBEDDING_DIMENSION  # text-embedding-3-small


def get_image_embedding_dimension() -> int:
    """Get image embedding dimension."""
    return JINA_CLIP_DIMENSION  # Jina CLIP v1
