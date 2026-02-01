"""AI KM Platform - Multimodal RAG Backend."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import kb, chat, upload_ws
from app.config import get_settings


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

    yield

    # Shutdown
    print("👋 Shutting down...")


# Create FastAPI app
app = FastAPI(
    title="AI KM Platform",
    description="Multimodal RAG Knowledge Management Platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS configuration - allow all origins in development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(kb.router)
app.include_router(chat.router)
app.include_router(upload_ws.router)


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
