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

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    intent_anthropic_model: str = "claude-haiku-4-5-20251001"

    # Ollama Chat / OpenAI-compatible LLM endpoint
    ollama_chat_url: str = "http://ollama.webtw.xyz:11434/v1"
    ollama_chat_api_key: str = "ollama"
    ollama_chat_model: str = "qwen3.5:397b-cloud"
    ollama_light_model: str = "gemma4:31b-cloud"

    # NVIDIA API (Batch 2-C: SQL generation alternative provider)
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_sql_model: str = "minimaxai/minimax-m2.7"

    # SQL Generation feature flag (Batch 2-C)
    # "anthropic" (default, no behavior change) | "nvidia" | "ollama"
    sql_generation_provider: str = "anthropic"
    # Override SQL generation model; empty = use provider's default
    sql_generation_model: str = ""

    # Self-Reflection thresholds (Batch 2-B)
    # max retries for non-hybrid path (was 3, now 1 to cap latency)
    nl2sql_max_retries: int = 1
    # skip reflection when rule validator passes and row_count > 0
    nl2sql_skip_reflection_on_rule_pass: bool = True
    # only trigger reflection retry when confidence below this (very low)
    nl2sql_reflection_confidence_threshold: float = 0.3

    # Intent classification
    intent_provider: str = "ollama"  # "ollama", "anthropic", or "openai"
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

    # OpenAI Embedding (used only when embedding_provider=openai)
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimension: int = 1536
    openai_embedding_base_url: str = ""  # optional override (e.g. Azure / proxy). empty → default OpenAI endpoint

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
    reranker_provider: str = "auto"  # "cohere" | "bge" | "ollama" | "auto"
    reranker_timeout: float = 5.0  # seconds
    reranker_fallback_enabled: bool = True

    # BGE Reranker Configuration
    bge_model_name: str = "BAAI/bge-reranker-v2-m3"
    bge_max_length: int = 512
    bge_batch_size: int = 32

    # Ollama Reranker (BGE reranker v2-m3 via Ollama /api/embed, GPU-backed)
    ollama_reranker_url: str = ""  # empty → fall back to ollama_base_url / ollama_chat_url (strip /v1)
    ollama_reranker_model: str = "linux6200/bge-reranker-v2-m3:latest"

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

    # PostgreSQL Viewer (013)
    pg_viewer_enabled: bool = True
    pg_viewer_database_url: str = ""
    pg_viewer_row_limit: int = 1000
    pg_viewer_stmt_timeout_ms: int = 10000
    pg_viewer_sql_max_len: int = 8000
    pg_viewer_audit_retention_days: int = 180
    pg_viewer_rate_limit_sql: int = 30   # per-minute
    pg_viewer_rate_limit_rows: int = 60  # per-minute
    pg_viewer_password: str = ""
    pg_viewer_audit_purger_password: str = ""
    pg_viewer_trusted_proxy_ips: list[str] = []

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings."""
    return Settings()


def get_active_llm_info() -> tuple[str, str]:
    """回傳目前實際使用的 (llm_url, model_name)，依 llm_provider 設定。"""
    s = get_settings()
    if s.llm_provider == "anthropic" and s.anthropic_api_key:
        return "https://api.anthropic.com", s.anthropic_model or "claude-sonnet-4-6"
    if s.llm_provider == "openai" and s.openai_api_key:
        return "https://api.openai.com", s.openai_model or "gpt-4o"
    return s.ollama_chat_url, s.ollama_chat_model


def invalidate_settings():
    """Clear lru_cache so next get_settings() returns fresh instance."""
    get_settings.cache_clear()


_on_change_callbacks = []


def on_settings_change(callback):
    _on_change_callbacks.append(callback)


def _notify_change(key: str, value):
    for cb in _on_change_callbacks:
        try:
            cb(key, value)
        except Exception:
            pass
