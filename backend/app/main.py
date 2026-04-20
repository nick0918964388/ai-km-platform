"""AI KM Platform - Multimodal RAG Backend."""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

from app.routers import kb, chat, upload_ws, structured, query, export, dashboard, profile, maximo, admin, conversations
from app.routers.auth import router as auth_router
from app.routers.pg_viewer import router as pg_viewer_router
from app.routers.csp_violations import router as csp_violations_router
from app.config import get_settings

# API Key for authentication
API_KEY = os.getenv("AIKM_API_KEY", "")

# Allowed origins for CORS
ALLOWED_ORIGINS = [
    "https://aikm.nickai.cc",
    "https://trc-ai-km.nickai.cc",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://192.168.1.11:3000",
    "http://192.168.1.11:3001",
]


class APIKeyMiddleware:
    """Pure ASGI middleware for API key verification (avoids BaseHTTPMiddleware SSE blocking)."""

    PUBLIC_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc", "/api/auth/", "/api/csp-violations")

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Skip public paths
        if path == "/" or any(path.startswith(p) for p in self.PUBLIC_PREFIXES):
            await self.app(scope, receive, send)
            return

        # Skip if no API key configured
        if not API_KEY:
            await self.app(scope, receive, send)
            return

        # Check API key in headers
        headers = dict(scope.get("headers", []))
        api_key = headers.get(b"x-api-key", b"").decode()
        if api_key != API_KEY:
            response = JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup: Initialize vector store
    from app.services import vector_store
    client = vector_store.get_client()
    settings = get_settings()
    if settings.qdrant_url and settings.qdrant_url != ":memory:":
        print(f"✅ Vector store connected to Qdrant: {settings.qdrant_url}")
    else:
        print("✅ Vector store initialized (in-memory mode)")
    
    # Startup: Initialize database (structured data)
    try:
        from app.db.session import init_db
        await init_db()
        print("✅ PostgreSQL database initialized")
    except Exception as e:
        print(f"⚠️ PostgreSQL not available: {e}")

    # pg_viewer feature-flag check
    if settings.pg_viewer_enabled and not settings.pg_viewer_database_url:
        logger.warning(
            "pg_viewer enabled but PG_VIEWER_DATABASE_URL unset — viewer endpoints will 503"
        )

    # Maximo tag column migration
    try:
        from app.db.session import get_db_context
        from sqlalchemy import text
        async with get_db_context() as db:
            await db.execute(text(
                "ALTER TABLE maximo_field_metadata ADD COLUMN IF NOT EXISTS tag VARCHAR(50) DEFAULT 'general'"
            ))
            await db.execute(text(
                "ALTER TABLE nl_sql_examples ADD COLUMN IF NOT EXISTS tag VARCHAR(50) DEFAULT 'general'"
            ))
        print("✅ Maximo tag columns ensured")
    except Exception as e:
        print(f"⚠️ Maximo tag migration skipped: {e}")

    # Pending SQL examples table
    try:
        from app.db.session import get_db_context
        from sqlalchemy import text
        async with get_db_context() as db:
            await db.execute(text("""
                CREATE TABLE IF NOT EXISTS pending_sql_examples (
                    id SERIAL PRIMARY KEY,
                    question TEXT NOT NULL,
                    sql_query TEXT NOT NULL,
                    submitted_by VARCHAR(100) NOT NULL,
                    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    status VARCHAR(20) DEFAULT 'pending',
                    reviewed_by VARCHAR(100),
                    reviewed_at TIMESTAMP WITH TIME ZONE,
                    notes TEXT
                )
            """))
            await db.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_pending_sql_status ON pending_sql_examples(status)"
            ))
        print("✅ pending_sql_examples table ensured")
    except Exception as e:
        print(f"⚠️ pending_sql_examples migration skipped: {e}")

    # Permission tables migration
    try:
        from app.db.session import get_db_context
        from sqlalchemy import text as _text
        import pathlib
        migration_path = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "maximo_migrate_005_permissions.sql"
        if migration_path.exists():
            sql_content = migration_path.read_text()
            async with get_db_context() as db:
                for stmt in sql_content.split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        await db.execute(_text(stmt))
            print("✅ Permission tables ensured")
    except Exception as e:
        print(f"⚠️ Permission migration skipped: {e}")

    # Conversations tables migration
    try:
        from app.db.session import get_db_context
        from sqlalchemy import text as _text
        import pathlib
        conv_sql = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "conversations_migration.sql"
        if conv_sql.exists():
            sql_content = conv_sql.read_text()
            async with get_db_context() as db:
                for stmt in sql_content.split(";"):
                    stmt = stmt.strip()
                    if stmt and not stmt.startswith("--"):
                        await db.execute(_text(stmt))
            print("✅ Conversations tables ensured")
    except Exception as e:
        print(f"⚠️ Conversations migration skipped: {e}")

    # Conversations FTS migration
    try:
        from app.db.session import get_db_context
        from sqlalchemy import text as _text
        import pathlib
        fts_sql = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "conversations_fts_migration.sql"
        if fts_sql.exists():
            sql_content = fts_sql.read_text()
            async with get_db_context() as db:
                for stmt in sql_content.split(";"):
                    stmt = stmt.strip()
                    if stmt and not stmt.startswith("--"):
                        await db.execute(_text(stmt))
            print("✅ Conversations FTS index ensured")
    except Exception as e:
        print(f"⚠️ Conversations FTS migration skipped: {e}")

    # System settings table migration
    try:
        from app.db.session import get_db_context
        from sqlalchemy import text as _text
        import pathlib
        settings_sql = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "system_settings.sql"
        if settings_sql.exists():
            sql_content = settings_sql.read_text()
            async with get_db_context() as db:
                for stmt in sql_content.split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        await db.execute(_text(stmt))
            print("✅ System settings table ensured")
    except Exception as e:
        print(f"⚠️ System settings migration skipped: {e}")

    # Audit conversation_id migration
    try:
        from app.db.session import get_db_context
        from sqlalchemy import text as _text
        import pathlib
        audit_sql = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "audit_conversation_id_migration.sql"
        if audit_sql.exists():
            sql_content = audit_sql.read_text()
            async with get_db_context() as db:
                for stmt in sql_content.split(";"):
                    stmt = stmt.strip()
                    if stmt and not stmt.startswith("--"):
                        await db.execute(_text(stmt))
            print("✅ Audit conversation_id columns ensured")
    except Exception as e:
        print(f"⚠️ Audit conversation_id migration skipped: {e}")

    # Load domain code→Chinese mappings
    try:
        from app.services.domain_mapper import load_domain_cache
        await load_domain_cache()
        print("✅ Domain mapper cache loaded")
    except Exception as e:
        print(f"⚠️ Domain mapper cache skipped: {e}")

    # Load DB settings and override config singleton
    try:
        from app.services import settings_service
        await settings_service.load_settings()
        db_settings = await settings_service.get_all_settings()
        settings = get_settings()
        override_keys = [
            'llm_provider', 'ollama_chat_url', 'ollama_chat_api_key', 'ollama_chat_model',
            'ollama_light_model', 'intent_llm_url', 'intent_llm_model',
            'intent_provider', 'anthropic_api_key', 'anthropic_model', 'intent_anthropic_model',
            'openai_api_key',
        ]
        for key in override_keys:
            if db_settings.get(key):
                setattr(settings, key, db_settings[key])
        print(f"✅ DB settings loaded: {len(db_settings)} keys")
    except Exception as e:
        print(f"⚠️ DB settings load skipped: {e}")

    yield

    # Shutdown
    try:
        from app.db.session import close_db
        await close_db()
    except Exception:
        pass
    print("👋 Shutting down...")


# Create FastAPI app
app = FastAPI(
    title="AI KM Platform",
    description="Multimodal RAG Knowledge Management Platform",
    version="0.1.0",
    lifespan=lifespan,
)

# API Key middleware (must be added before CORS)
app.add_middleware(APIKeyMiddleware)

# CORS configuration - restrict to allowed origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-API-Key"],  # Allow API key header
)

# Include routers
app.include_router(kb.router)
app.include_router(chat.router)
app.include_router(upload_ws.router)
app.include_router(structured.router, prefix="/api")
app.include_router(query.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(profile.router)  # Already includes /api/profile prefix
app.include_router(profile.avatar_router)  # Avatar static files at /api/avatars
app.include_router(maximo.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(conversations.router)
app.include_router(pg_viewer_router, prefix="/api/pg-viewer")
app.include_router(csp_violations_router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "AI KM Platform",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/health/reranker")
async def health_reranker():
    """Reranker status endpoint."""
    from app.services.reranker_factory import get_reranker_factory
    factory = get_reranker_factory()
    return factory.get_status()


@app.get("/health/circuits")
async def health_circuits():
    """Circuit breaker status endpoint."""
    from app.services.circuit_breaker import get_all_breakers
    return get_all_breakers()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
