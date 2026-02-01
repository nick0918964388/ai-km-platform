"""File storage service for original document files."""
import logging
import mimetypes
from pathlib import Path
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

# MIME type mapping for Content-Disposition
INLINE_MIME_TYPES = {
    "application/pdf",
}

MIME_TYPE_MAP = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


def get_storage_dir() -> Path:
    """Get the storage directory path."""
    settings = get_settings()
    storage_path = Path(settings.storage_dir)
    storage_path.mkdir(parents=True, exist_ok=True)
    return storage_path


def save_file(document_id: str, filename: str, content: bytes) -> str:
    """
    Save original file to storage.

    Args:
        document_id: Unique document identifier
        filename: Original filename (with extension)
        content: File content as bytes

    Returns:
        Full path to saved file
    """
    storage_dir = get_storage_dir()
    doc_dir = storage_dir / document_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize filename (remove path separators)
    safe_filename = Path(filename).name
    file_path = doc_dir / safe_filename

    file_path.write_bytes(content)
    logger.info(f"Saved file: {file_path}")

    return str(file_path)


def get_file_path(document_id: str) -> Optional[Path]:
    """
    Get the file path for a document.

    Args:
        document_id: Document identifier

    Returns:
        Path to the file, or None if not found
    """
    storage_dir = get_storage_dir()
    doc_dir = storage_dir / document_id

    if not doc_dir.exists():
        return None

    # Find the first file in the directory
    files = list(doc_dir.iterdir())
    if not files:
        return None

    return files[0]


def get_file_info(document_id: str) -> Optional[dict]:
    """
    Get file information including filename and content type.

    Args:
        document_id: Document identifier

    Returns:
        Dict with 'filename', 'content_type', and 'is_inline' keys,
        or None if file not found
    """
    file_path = get_file_path(document_id)
    if not file_path:
        return None

    filename = file_path.name
    suffix = file_path.suffix.lower()

    # Determine content type
    content_type = MIME_TYPE_MAP.get(suffix)
    if not content_type:
        content_type, _ = mimetypes.guess_type(filename)
        if not content_type:
            content_type = "application/octet-stream"

    # Determine if should be displayed inline (PDF) or as attachment (others)
    is_inline = content_type in INLINE_MIME_TYPES

    return {
        "filename": filename,
        "content_type": content_type,
        "is_inline": is_inline,
        "file_path": str(file_path),
    }


def file_exists(document_id: str) -> bool:
    """
    Check if original file exists for a document.

    Args:
        document_id: Document identifier

    Returns:
        True if file exists, False otherwise
    """
    return get_file_path(document_id) is not None


def delete_file(document_id: str) -> bool:
    """
    Delete stored file for a document.

    Args:
        document_id: Document identifier

    Returns:
        True if deleted, False if not found
    """
    storage_dir = get_storage_dir()
    doc_dir = storage_dir / document_id

    if not doc_dir.exists():
        return False

    # Delete all files in the directory
    for file_path in doc_dir.iterdir():
        file_path.unlink()

    # Remove the directory
    doc_dir.rmdir()
    logger.info(f"Deleted document files: {document_id}")

    return True
