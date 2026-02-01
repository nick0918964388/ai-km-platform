"""Vector store service using Qdrant."""
import logging
import uuid
from datetime import datetime
from typing import Optional
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

from app.config import get_settings
from app.services.embedding import (
    get_text_embedding_dimension,
    get_image_embedding_dimension,
)

logger = logging.getLogger(__name__)

# Qdrant client (persistent or in-memory based on config)
_client: Optional[QdrantClient] = None

# Collection names
TEXT_COLLECTION = "text_chunks"
IMAGE_COLLECTION = "image_chunks"

# In-memory document storage (TODO: migrate to persistent storage)
_documents: dict[str, dict] = {}


def get_client() -> QdrantClient:
    """Get or create Qdrant client."""
    global _client
    if _client is None:
        settings = get_settings()
        qdrant_url = settings.qdrant_url

        if qdrant_url and qdrant_url != ":memory:":
            # Use persistent Qdrant
            logger.info(f"Connecting to Qdrant at {qdrant_url}")
            try:
                _client = QdrantClient(
                    url=qdrant_url,
                    api_key=settings.qdrant_api_key if settings.qdrant_api_key else None,
                )
                _ensure_collections()
            except Exception as e:
                logger.warning(f"Failed to connect to Qdrant at {qdrant_url}: {e}")
                logger.info("Falling back to in-memory Qdrant")
                _client = QdrantClient(":memory:")
                _initialize_collections()
        else:
            # Use in-memory Qdrant (development/testing)
            logger.info("Using in-memory Qdrant")
            _client = QdrantClient(":memory:")
            _initialize_collections()
    return _client


def _ensure_collections():
    """Ensure collections exist in persistent Qdrant."""
    client = _client
    collections = client.get_collections().collections
    collection_names = [c.name for c in collections]

    if TEXT_COLLECTION not in collection_names:
        logger.info(f"Creating collection: {TEXT_COLLECTION}")
        client.create_collection(
            collection_name=TEXT_COLLECTION,
            vectors_config=VectorParams(
                size=get_text_embedding_dimension(),
                distance=Distance.COSINE,
            ),
        )

    if IMAGE_COLLECTION not in collection_names:
        logger.info(f"Creating collection: {IMAGE_COLLECTION}")
        client.create_collection(
            collection_name=IMAGE_COLLECTION,
            vectors_config=VectorParams(
                size=get_image_embedding_dimension(),
                distance=Distance.COSINE,
            ),
        )


def _initialize_collections():
    """Initialize vector collections."""
    client = _client

    # Text collection
    client.create_collection(
        collection_name=TEXT_COLLECTION,
        vectors_config=VectorParams(
            size=get_text_embedding_dimension(),
            distance=Distance.COSINE,
        ),
    )

    # Image collection
    client.create_collection(
        collection_name=IMAGE_COLLECTION,
        vectors_config=VectorParams(
            size=get_image_embedding_dimension(),
            distance=Distance.COSINE,
        ),
    )


def add_document(
    document_id: str,
    filename: str,
    doc_type: str,
    file_size: int,
    chunk_count: int,
) -> None:
    """Add document metadata."""
    _documents[document_id] = {
        "id": document_id,
        "filename": filename,
        "doc_type": doc_type,
        "file_size": file_size,
        "chunk_count": chunk_count,
        "uploaded_at": datetime.utcnow().isoformat(),
    }


def get_document(document_id: str) -> Optional[dict]:
    """Get document by ID."""
    return _documents.get(document_id)


def list_documents() -> list[dict]:
    """List all documents."""
    return list(_documents.values())


def delete_document(document_id: str) -> bool:
    """Delete document and its chunks."""
    if document_id not in _documents:
        return False

    client = get_client()

    # Delete text chunks
    client.delete(
        collection_name=TEXT_COLLECTION,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="document_id",
                    match=MatchValue(value=document_id),
                )
            ]
        ),
    )

    # Delete image chunks
    client.delete(
        collection_name=IMAGE_COLLECTION,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="document_id",
                    match=MatchValue(value=document_id),
                )
            ]
        ),
    )

    del _documents[document_id]
    return True


def add_text_chunk(
    document_id: str,
    document_name: str,
    content: str,
    embedding: list[float],
    chunk_index: int,
    metadata: dict = None,
) -> str:
    """Add a text chunk to the vector store."""
    client = get_client()
    chunk_id = str(uuid.uuid4())

    payload = {
        "document_id": document_id,
        "document_name": document_name,
        "content": content,
        "chunk_index": chunk_index,
        "chunk_type": "text",
    }
    
    # Add metadata if provided
    if metadata:
        payload.update(metadata)

    client.upsert(
        collection_name=TEXT_COLLECTION,
        points=[
            PointStruct(
                id=chunk_id,
                vector=embedding,
                payload=payload,
            )
        ],
    )

    return chunk_id


def add_image_chunk(
    document_id: str,
    document_name: str,
    image_base64: str,
    embedding: list[float],
    description: str = "",
) -> str:
    """Add an image chunk to the vector store."""
    client = get_client()
    chunk_id = str(uuid.uuid4())

    client.upsert(
        collection_name=IMAGE_COLLECTION,
        points=[
            PointStruct(
                id=chunk_id,
                vector=embedding,
                payload={
                    "document_id": document_id,
                    "document_name": document_name,
                    "image_base64": image_base64,
                    "description": description,
                    "chunk_type": "image",
                },
            )
        ],
    )

    return chunk_id


def search_text(
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict]:
    """Search text chunks."""
    client = get_client()

    results = client.query_points(
        collection_name=TEXT_COLLECTION,
        query=query_embedding,
        limit=top_k,
    )

    return [
        {
            "id": str(r.id),
            "score": r.score,
            **r.payload,
        }
        for r in results.points
    ]


def search_images(
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict]:
    """Search image chunks."""
    client = get_client()

    results = client.query_points(
        collection_name=IMAGE_COLLECTION,
        query=query_embedding,
        limit=top_k,
    )

    return [
        {
            "id": str(r.id),
            "score": r.score,
            **r.payload,
        }
        for r in results.points
    ]


def get_stats() -> dict:
    """Get knowledge base statistics."""
    client = get_client()

    text_info = client.get_collection(TEXT_COLLECTION)
    image_info = client.get_collection(IMAGE_COLLECTION)

    doc_list = list_documents()
    pdf_count = sum(1 for d in doc_list if d["doc_type"] == "pdf")
    word_count = sum(1 for d in doc_list if d["doc_type"] == "word")
    excel_count = sum(1 for d in doc_list if d["doc_type"] == "excel")
    image_count = sum(1 for d in doc_list if d["doc_type"] == "image")

    return {
        "total_documents": len(doc_list),
        "total_chunks": text_info.points_count + image_info.points_count,
        "pdf_count": pdf_count,
        "word_count": word_count,
        "excel_count": excel_count,
        "image_count": image_count,
        "text_chunks": text_info.points_count,
        "image_chunks": image_info.points_count,
    }
