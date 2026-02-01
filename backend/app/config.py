"""Application configuration."""
import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings."""

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Embedding models
    text_embedding_model: str = "all-MiniLM-L6-v2"
    clip_model: str = "openai/clip-vit-base-patch32"

    # Qdrant
    qdrant_collection_name: str = "knowledge_base"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379"
    cache_ttl: int = 3600  # 1 hour default

    # Cohere Reranker
    cohere_api_key: str = ""
    cohere_model: str = "rerank-v3.5"
    rerank_top_n: int = 10

    # Backup
    backup_dir: str = "./backups"

    # CORS
    cors_origins: list[str] = [
        "http://localhost:3001", 
        "http://localhost:3000",
        "https://*.trycloudflare.com",  # Cloudflare Tunnel
        "*"  # Allow all origins in development
    ]

    # Upload
    upload_dir: str = "./uploads"
    max_file_size: int = 50 * 1024 * 1024  # 50MB

    # Document Storage (for original file preview)
    storage_dir: str = "./storage/documents"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings."""
    return Settings()
