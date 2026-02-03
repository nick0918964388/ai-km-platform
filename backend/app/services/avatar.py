"""Avatar management service for processing and storing user avatars."""

import os
import uuid
import logging
from pathlib import Path
from typing import Optional
from PIL import Image
import io

logger = logging.getLogger(__name__)

# Avatar storage configuration
AVATAR_STORAGE_DIR = Path("storage/avatars")
AVATAR_SIZE = (200, 200)  # Standard avatar size
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB in bytes
ALLOWED_FORMATS = {"JPEG", "PNG", "GIF"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif"}

# Magic numbers for file type validation (first few bytes)
FILE_SIGNATURES = {
    b"\xff\xd8\xff": "JPEG",
    b"\x89PNG\r\n\x1a\n": "PNG",
    b"GIF87a": "GIF",
    b"GIF89a": "GIF",
}


def validate_image_file(file_content: bytes, filename: str) -> tuple[bool, Optional[str]]:
    """
    Validate image file by checking magic numbers, size, and format.

    Args:
        file_content: Raw file bytes
        filename: Original filename

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check file size
    if len(file_content) > MAX_FILE_SIZE:
        return False, f"File size exceeds maximum allowed size of 5MB"

    # Check file extension
    file_ext = Path(filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        return False, f"Invalid file extension. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"

    # Check magic numbers (file signature)
    file_type = None
    for signature, ftype in FILE_SIGNATURES.items():
        if file_content.startswith(signature):
            file_type = ftype
            break

    if not file_type:
        return False, "Invalid or corrupted image file"

    # Verify the file can be opened as an image
    try:
        image = Image.open(io.BytesIO(file_content))
        image.verify()

        # Check format matches
        if image.format not in ALLOWED_FORMATS:
            return False, f"Unsupported image format: {image.format}"

    except Exception as e:
        return False, f"Failed to validate image: {str(e)}"

    return True, None


async def process_avatar(
    user_id: str,
    file_content: bytes,
    filename: str
) -> tuple[str, str]:
    """
    Process and save user avatar image.
    - Validates file format and size
    - Resizes to 200x200px
    - Converts to JPEG for consistency
    - Saves with unique filename

    Args:
        user_id: User ID for organizing storage
        file_content: Raw image file bytes
        filename: Original filename

    Returns:
        Tuple of (avatar_url, saved_filename)

    Raises:
        ValueError: If validation fails
        IOError: If file operations fail
    """
    # Validate image file
    is_valid, error_msg = validate_image_file(file_content, filename)
    if not is_valid:
        raise ValueError(error_msg)

    try:
        # Open and process image
        image = Image.open(io.BytesIO(file_content))

        # Convert RGBA to RGB if needed (for PNG with transparency)
        if image.mode in ("RGBA", "LA", "P"):
            # Create white background
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        # Resize to standard size with high-quality resampling
        image.thumbnail(AVATAR_SIZE, Image.Resampling.LANCZOS)

        # Create final image with exact dimensions (center crop if needed)
        final_image = Image.new("RGB", AVATAR_SIZE, (255, 255, 255))
        offset = ((AVATAR_SIZE[0] - image.size[0]) // 2,
                  (AVATAR_SIZE[1] - image.size[1]) // 2)
        final_image.paste(image, offset)

        # Generate unique filename
        file_ext = ".jpg"  # Always save as JPEG
        unique_filename = f"{user_id}_{uuid.uuid4().hex}{file_ext}"

        # Ensure storage directory exists
        AVATAR_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

        # Save processed image
        file_path = AVATAR_STORAGE_DIR / unique_filename
        final_image.save(file_path, "JPEG", quality=90, optimize=True)

        # Generate URL path (relative to API)
        avatar_url = f"/api/avatars/{unique_filename}"

        logger.info(f"Avatar processed and saved for user {user_id}: {unique_filename}")
        return avatar_url, unique_filename

    except Exception as e:
        logger.error(f"Error processing avatar for user {user_id}: {e}")
        raise IOError(f"Failed to process avatar image: {str(e)}")


async def delete_avatar(avatar_url: Optional[str]) -> bool:
    """
    Delete avatar file from storage.

    Args:
        avatar_url: Avatar URL path (e.g., "/api/avatars/filename.jpg")

    Returns:
        True if deletion successful, False if file not found
    """
    if not avatar_url:
        return False

    try:
        # Extract filename from URL
        filename = Path(avatar_url).name
        file_path = AVATAR_STORAGE_DIR / filename

        # Check if file exists and delete
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Avatar deleted: {filename}")
            return True
        else:
            logger.warning(f"Avatar file not found: {filename}")
            return False

    except Exception as e:
        logger.error(f"Error deleting avatar {avatar_url}: {e}")
        return False


def get_avatar_path(filename: str) -> Optional[Path]:
    """
    Get full filesystem path for avatar file.

    Args:
        filename: Avatar filename

    Returns:
        Path object if file exists, None otherwise
    """
    file_path = AVATAR_STORAGE_DIR / filename
    return file_path if file_path.exists() else None
