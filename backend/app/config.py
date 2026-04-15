"""Application configuration."""
import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings."""

    # LLM Provider
    llm_provider: str = "ollama"  # "ollama" or "openai"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Ollama Chat / OpenAI-compatible LLM endpoint
    ollama_chat_url: str = "http://ollama.webtw.xyz:11434/v1"
    ollama_chat_api_key: str = "ollama"
    ollama_chat_model: str = "qwen3.5:397b-cloud"
    ollama_light_model: str = "gemma4:31b-cloud"

    # Fast local LLM for intent classification (low latency, smaller model)
    intent_llm_url: str = "http://ollama.webtw.xyz:11434/v1"
    intent_llm_model: str = "gemma4:31b-cloud"

    # Embedding models
    text_embedding_model: str = "all-MiniLM-L6-v2"
    clip_model: str = "openai/clip-vit-base-patch32"
    
    # Ollama Embedding
    embedding_provider: str = "ollama"  # "openai" or "ollama"
    ollama_base_url: str = "http://ollama.webtw.xyz:11434"
    ollama_embedding_model: str = "qwen3-embedding:latest"
    ollama_embedding_dimension: int = 4096

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

    # Multi-Provider Reranker Configuration
    reranker_provider: str = "auto"  # "cohere" | "bge" | "auto"
    reranker_timeout: float = 5.0  # seconds
    reranker_fallback_enabled: bool = True

    # BGE Reranker Configuration
    bge_model_name: str = "BAAI/bge-reranker-v2-m3"
    bge_max_length: int = 512
    bge_batch_size: int = 32

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
