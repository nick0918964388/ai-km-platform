"""AI KM Platform - Multimodal RAG Backend."""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.routers import kb, chat, upload_ws, structured, query, export, dashboard, profile
from app.config import get_settings

# API Key for authentication
API_KEY = os.getenv("AIKM_API_KEY", "")

# Allowed origins for CORS
ALLOWED_ORIGINS = [
    "https://aikm.nickai.cc",
    "http://localhost:3000",
    "http://localhost:3001",
]


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware to verify API key for protected endpoints."""
    
    # Endpoints that don't require API key
    PUBLIC_PATHS = ["/", "/health", "/docs", "/openapi.json", "/redoc"]
    
    async def dispatch(self, request: Request, call_next):
        # Skip API key check for public paths
        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)
        
        # Skip if no API key is configured (development mode)
        if not API_KEY:
            return await call_next(request)
        
        # Check API key in header
        request_api_key = request.headers.get("X-API-Key")
        if request_api_key != API_KEY:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
        
        return await call_next(request)


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
