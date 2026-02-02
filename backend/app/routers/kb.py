"""Knowledge base router for upload and document management."""
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from app.models.schemas import (
    DocumentType,
    DocumentInfo,
    DocumentListResponse,
    UploadResponse,
    DeleteResponse,
    StatsResponse,
    BackupRecord,
    BackupListResponse,
    CacheStats,
    CacheClearRequest,
    CacheClearResponse,
    EvaluationRequest,
    EvaluationResponse,
    EvaluationMetricsResponse,
    EvaluationMetricInfo,
)
from app.services import document_processor, vector_store
from app.services import backup as backup_service
from app.services import cache as cache_service
from app.services import file_storage
from app.services import evaluation as evaluation_service

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


@router.post("/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """
    Upload a document (PDF or image) to the knowledge base.

    The document will be processed, embedded, and stored in the vector database.
    """
    # Validate file type
    file_type = document_processor.get_file_type(file.filename)
    if not file_type:
        raise HTTPException(
            status_code=400,
            detail="不支援的檔案格式。請上傳 PDF、Word (.docx)、Excel (.xlsx, .xls) 或圖片檔案。",
        )

    # Read file content
    content = await file.read()

    # Check file size (50MB limit)
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="檔案大小超過 50MB 限制。",
        )

    try:
        if file_type == "pdf":
            doc_id, chunk_count = await document_processor.process_pdf(content, file.filename)
            doc_type = DocumentType.PDF
        elif file_type == "word":
            doc_id, chunk_count = await document_processor.process_word(content, file.filename)
            doc_type = DocumentType.WORD
        elif file_type == "excel":
            doc_id, chunk_count = await document_processor.process_excel(content, file.filename)
            doc_type = DocumentType.EXCEL
        else:
            doc_id, chunk_count = await document_processor.process_image(content, file.filename)
            doc_type = DocumentType.IMAGE

        return UploadResponse(
            success=True,
            document_id=doc_id,
            filename=file.filename,
            doc_type=doc_type,
            chunk_count=chunk_count,
            message=f"成功上傳並處理 {file.filename}，產生 {chunk_count} 個向量區塊。",
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"處理檔案時發生錯誤: {str(e)}",
        )


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents():
    """List all documents in the knowledge base."""
    docs = await vector_store.list_documents()

    documents = [
        DocumentInfo(
            id=doc["id"],
            filename=doc["filename"],
            doc_type=DocumentType(doc["doc_type"]),
            chunk_count=doc["chunk_count"],
            uploaded_at=datetime.fromisoformat(doc["uploaded_at"]),
            file_size=doc["file_size"],
        )
        for doc in docs
    ]

    return DocumentListResponse(
        documents=documents,
        total=len(documents),
    )


@router.delete("/documents/{document_id}", response_model=DeleteResponse)
async def delete_document(document_id: str):
    """Delete a document and its chunks from the knowledge base."""
    success = await vector_store.delete_document(document_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"找不到文件 ID: {document_id}",
        )

    # Invalidate related cache entries
    cache_service.invalidate_cache(document_id=document_id)

    return DeleteResponse(
        success=True,
        message=f"成功刪除文件 {document_id}",
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get knowledge base statistics."""
    stats = await vector_store.get_stats()
    return StatsResponse(**stats)


# ============================================================================
# Document File Preview/Download
# ============================================================================

@router.get("/documents/{document_id}/file")
async def get_document_file(document_id: str):
    """
    Get the original document file for preview or download.

    - PDF files: Displayed inline in browser (Content-Disposition: inline)
    - Word/Image files: Trigger download (Content-Disposition: attachment)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    file_info = file_storage.get_file_info(document_id)

    if not file_info:
        logger.error(f"File not found for document_id: {document_id}")
        raise HTTPException(
            status_code=404,
            detail="找不到原始檔案",
        )

    # Verify file actually exists
    file_path = Path(file_info["file_path"])
    if not file_path.exists():
        logger.error(f"File path does not exist: {file_path}")
        raise HTTPException(
            status_code=404,
            detail=f"檔案不存在: {file_info['filename']}",
        )

    # Determine content disposition based on file type
    # Use RFC 5987 encoding for non-ASCII filenames
    filename = file_info["filename"]
    # URL encode the filename for UTF-8 support in Content-Disposition header
    encoded_filename = quote(filename, safe='')
    
    if file_info["is_inline"]:
        # PDF - display inline in browser
        content_disposition = f"inline; filename*=UTF-8''{encoded_filename}"
    else:
        # Word, images - trigger download
        content_disposition = f"attachment; filename*=UTF-8''{encoded_filename}"

    logger.info(f"Serving file: {file_path} as {file_info['content_type']}")
    
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=file_info["content_type"],
        headers={"Content-Disposition": content_disposition},
    )


# ============================================================================
# Backup Endpoints
# ============================================================================

@router.post("/backups", response_model=BackupRecord, status_code=202)
async def create_backup(collection_name: str = "text_chunks"):
    """Create a new backup of the vector database collection."""
    try:
        record = backup_service.create_backup(collection_name)
        return record
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"備份失敗: {str(e)}",
        )


@router.get("/backups", response_model=BackupListResponse)
async def list_backups():
    """List all backup records."""
    backups = backup_service.list_backups()
    return BackupListResponse(backups=backups, total=len(backups))


@router.get("/backups/{backup_id}", response_model=BackupRecord)
async def get_backup(backup_id: str):
    """Get a specific backup record."""
    record = backup_service.get_backup(backup_id)
    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"找不到備份 ID: {backup_id}",
        )
    return record


@router.post("/backups/{backup_id}/restore", status_code=202)
async def restore_backup(backup_id: str):
    """Restore from a backup."""
    try:
        record = backup_service.restore_backup(backup_id)
        return {
            "message": f"成功從備份 {backup_id} 恢復資料",
            "backup_id": backup_id,
            "collection": record.collection_name,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"恢復失敗: {str(e)}",
        )


@router.delete("/backups/{backup_id}", status_code=204)
async def delete_backup(backup_id: str):
    """Delete a backup record and its snapshot file."""
    success = backup_service.delete_backup(backup_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"找不到備份 ID: {backup_id}",
        )
    return None


@router.get("/backups/{backup_id}/download")
async def download_backup(backup_id: str):
    """Download a backup snapshot file."""
    file_path = backup_service.get_backup_file_path(backup_id)
    if not file_path:
        raise HTTPException(
            status_code=404,
            detail=f"找不到備份檔案: {backup_id}",
        )
    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type="application/octet-stream",
    )


# ============================================================================
# Cache Endpoints
# ============================================================================

@router.get("/cache/stats", response_model=CacheStats)
async def get_cache_stats():
    """Get cache statistics."""
    stats = cache_service.get_cache_stats()
    return CacheStats(**stats)


@router.post("/cache/clear", response_model=CacheClearResponse)
async def clear_cache(request: CacheClearRequest = None):
    """Clear cache entries."""
    if request is None:
        request = CacheClearRequest()

    deleted = cache_service.invalidate_cache(
        pattern=request.pattern,
        document_id=request.document_id,
    )
    return CacheClearResponse(
        deleted_count=deleted,
        message=f"已清除 {deleted} 筆快取",
    )


# ============================================================================
# Evaluation Endpoints
# ============================================================================

@router.get("/evaluate/metrics", response_model=EvaluationMetricsResponse)
async def get_evaluation_metrics():
    """Get available evaluation metrics and their descriptions."""
    metrics = evaluation_service.get_available_metrics()
    return EvaluationMetricsResponse(
        metrics=[EvaluationMetricInfo(**m) for m in metrics]
    )


@router.post("/evaluate", response_model=EvaluationResponse)
async def run_evaluation(request: EvaluationRequest = None):
    """
    Run RAGAS evaluation on the RAG system.

    This endpoint evaluates the quality of the RAG system using RAGAS metrics:
    - **Context Recall**: Measures if retrieved context contains all relevant information
    - **Faithfulness**: Measures if the response is faithful to the retrieved context
    - **Factual Correctness**: Measures factual accuracy compared to reference

    If no test_data is provided, uses built-in sample data for EMU800 maintenance domain.

    Note: This operation can take several minutes depending on the number of test cases.
    """
    if request is None:
        request = EvaluationRequest()

    # Convert test data to dict format if provided
    test_data = None
    if request.test_data:
        test_data = [
            {"user_input": tc.user_input, "reference": tc.reference}
            for tc in request.test_data
        ]

    try:
        result = evaluation_service.run_evaluation(
            test_data=test_data,
            top_k=request.top_k,
            metrics=request.metrics,
        )
        return EvaluationResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"評測執行失敗: {str(e)}",
        )
