"""Pydantic schemas for API requests and responses."""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class DocumentType(str, Enum):
    """Document type enum."""
    PDF = "pdf"
    WORD = "word"
    EXCEL = "excel"
    IMAGE = "image"


class ChunkType(str, Enum):
    """Chunk type enum."""
    TEXT = "text"
    IMAGE = "image"


class TaskStatus(str, Enum):
    """Processing task status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProcessingStep(str, Enum):
    """Processing step enum."""
    UPLOADING = "uploading"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    DONE = "done"


class BackupStatus(str, Enum):
    """Backup status enum."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


# Request schemas
class ChatRequest(BaseModel):
    """Chat request schema."""
    query: str = Field(..., min_length=1, description="User query")
    image_base64: Optional[str] = Field(None, description="Base64 encoded image for multimodal query")
    top_k: int = Field(5, ge=1, le=20, description="Number of documents to retrieve")


class SearchRequest(BaseModel):
    """Search request schema."""
    query: str = Field(..., min_length=1, description="Search query")
    top_k: int = Field(5, ge=1, le=20, description="Number of results")


# Response schemas
class DocumentInfo(BaseModel):
    """Document information."""
    id: str
    filename: str
    doc_type: DocumentType
    chunk_count: int
    uploaded_at: datetime
    file_size: int


class DocumentListResponse(BaseModel):
    """Document list response."""
    documents: list[DocumentInfo]
    total: int


class UploadResponse(BaseModel):
    """Upload response."""
    success: bool
    document_id: str
    filename: str
    doc_type: DocumentType
    chunk_count: int
    message: str


class SearchResult(BaseModel):
    """Single search result."""
    id: str
    content: str
    doc_type: ChunkType
    document_id: str
    document_name: str
    score: float
    image_base64: Optional[str] = None
    file_url: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat response."""
    answer: str
    sources: list[SearchResult]


class SearchResponse(BaseModel):
    """Search response."""
    results: list[SearchResult]
    total: int


class StatsResponse(BaseModel):
    """Knowledge base statistics."""
    total_documents: int
    total_chunks: int
    pdf_count: int
    word_count: int
    excel_count: int
    image_count: int
    text_chunks: int
    image_chunks: int


class DeleteResponse(BaseModel):
    """Delete response."""
    success: bool
    message: str


class ErrorResponse(BaseModel):
    """Error response."""
    detail: str


# New schemas for RAG optimization
class ProcessingTask(BaseModel):
    """Document processing task."""
    id: str
    document_id: str
    filename: str
    file_size: int
    status: TaskStatus = TaskStatus.PENDING
    step: ProcessingStep = ProcessingStep.UPLOADING
    progress: int = Field(ge=0, le=100, default=0)
    chunk_count: int = 0
    message: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class BackupRecord(BaseModel):
    """Backup record for vector database."""
    id: str
    collection_name: str
    snapshot_name: str
    file_path: str = ""
    file_size: int = 0
    vector_count: int = 0
    status: BackupStatus = BackupStatus.PENDING
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class BackupListResponse(BaseModel):
    """Backup list response."""
    backups: list[BackupRecord]
    total: int


class ProgressMessage(BaseModel):
    """WebSocket progress message."""
    task_id: str
    status: TaskStatus
    step: ProcessingStep
    progress: int = Field(ge=0, le=100)
    message: str
    chunk_count: int = 0
    error: Optional[str] = None


class CacheStats(BaseModel):
    """Cache statistics."""
    total_keys: int
    query_cache_count: int
    task_cache_count: int
    memory_usage_bytes: int = 0
    hit_rate: float = 0.0
    total_hits: int = 0
    total_misses: int = 0


class CacheClearRequest(BaseModel):
    """Cache clear request."""
    pattern: Optional[str] = None
    document_id: Optional[str] = None


class CacheClearResponse(BaseModel):
    """Cache clear response."""
    deleted_count: int
    message: str
