"""Chat and search router for RAG queries."""
from fastapi import APIRouter

from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    SearchRequest,
    SearchResponse,
)
from app.services import rag

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat with the knowledge base using RAG.

    Supports multimodal queries with text and/or images.
    Retrieves relevant documents and generates an answer using GPT-4o.
    """
    answer, sources = rag.chat(
        query=request.query,
        image_base64=request.image_base64,
        top_k=request.top_k,
    )

    return ChatResponse(
        answer=answer,
        sources=sources,
    )


@router.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """
    Search the knowledge base without generating an answer.

    Returns relevant document chunks based on the query.
    """
    results = rag.search(
        query=request.query,
        top_k=request.top_k,
    )

    return SearchResponse(
        results=results,
        total=len(results),
    )
