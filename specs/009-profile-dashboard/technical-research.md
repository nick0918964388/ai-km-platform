# Technical Research: Profile Settings & Dashboard Feature

**Feature**: 009-profile-dashboard
**Date**: 2026-02-03
**Status**: Complete
**Prepared for**: Implementation team

## Executive Summary

This document provides comprehensive technical research for implementing the Profile Settings & Dashboard feature in the AI Knowledge Management Platform. The research covers five critical areas: SQLite schema design, avatar upload/processing, Qdrant collections strategy, dashboard metrics aggregation, and frontend state management.

**Key Decisions**:
- **Database**: Use existing PostgreSQL with SQLAlchemy async ORM (not SQLite - platform already standardized on PostgreSQL)
- **Avatar Storage**: Local filesystem with Pillow processing, 200x200px optimization
- **Dashboard Metrics**: Hybrid approach - PostgreSQL for counts, Qdrant for activity logs, Redis caching with 60s TTL
- **State Management**: Extend existing Zustand store with profile slice
- **Image Processing**: Pillow 12.1.0 (already installed) with async file I/O

---

## 1. SQLite Schema Design for User Profiles

### Decision: Use PostgreSQL (Not SQLite) with SQLAlchemy Async ORM

**Rationale**:
After examining the codebase, the platform has **already standardized on PostgreSQL** with async SQLAlchemy:
- Existing database setup in `/backend/app/db/session.py` uses `asyncpg` driver
- Connection string: `postgresql+asyncpg://aikm:aikm@localhost:5432/aikm`
- All structured data models use async SQLAlchemy (see `/backend/app/models/structured/`)
- `Base = declarative_base()` pattern already established in `/backend/app/db/__init__.py`

**Why not SQLite**:
- Would introduce **dual database system** (PostgreSQL for structured data, SQLite for profiles) - violates consistency
- SQLite async support is limited (would need `aiosqlite` wrapper, adding complexity)
- PostgreSQL already provides ACID compliance, concurrent access handling, and production-ready infrastructure
- Existing models (Document, Vehicle, FaultRecord, etc.) all use PostgreSQL

**Schema Design** (extends PostgreSQL, not SQLite):

```python
# backend/app/models/user.py (NEW FILE)
from sqlalchemy import Column, String, DateTime, Integer
from sqlalchemy.sql import func
from app.db import Base

class User(Base):
    """User profile model with avatar and account information."""

    __tablename__ = "users"

    # Primary key
    id = Column(String(36), primary_key=True)  # UUID format

    # Authentication (existing fields - may already exist in auth system)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)  # Optional if using OAuth

    # Profile fields (NEW)
    display_name = Column(String(50), nullable=False, default="")
    avatar_url = Column(String(255), nullable=True)  # Path relative to storage dir
    account_level = Column(String(20), nullable=False, default="free")  # free/pro/enterprise

    # Audit fields
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    last_login = Column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        """Convert model to dictionary for API responses."""
        return {
            "id": self.id,
            "email": self.email,
            "display_name": self.display_name,
            "avatar_url": self.avatar_url,
            "account_level": self.account_level,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }
```

**Migration Strategy**:
```python
# backend/alembic/versions/xxx_add_user_profile_fields.py
"""Add user profile fields

Revision ID: xxx
Revises: yyy
Create Date: 2026-02-03
"""

def upgrade():
    # If users table doesn't exist, create it
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(255), nullable=True),
        sa.Column('display_name', sa.String(50), nullable=False, server_default=''),
        sa.Column('avatar_url', sa.String(255), nullable=True),
        sa.Column('account_level', sa.String(20), nullable=False, server_default='free'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=func.now()),
        sa.Column('last_login', sa.DateTime, nullable=True),
    )

    # Add indexes
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_users_id', 'users', ['id'])

def downgrade():
    op.drop_index('idx_users_id')
    op.drop_index('idx_users_email')
    op.drop_table('users')
```

**Indexing Strategy**:
- Primary key on `id` (automatic unique index)
- Unique index on `email` (for login lookups)
- No index on `display_name` or `account_level` (not frequently queried independently)
- Composite index not needed (profile queries always by user_id)

**Alternatives Considered**:
1. **SQLite with aiosqlite**: Rejected - introduces dual database complexity, async support limited
2. **MongoDB/NoSQL**: Rejected - platform standardized on SQL, no compelling reason to add NoSQL for simple user profiles
3. **Separate profile microservice**: Rejected - over-engineering for MVP, adds network latency

**Implementation Notes**:
- Use existing `get_db()` dependency from `/backend/app/db/session.py`
- Follow pattern from existing models (Document, Vehicle, etc.) - see `/backend/app/models/document.py`
- Use `async with get_db_context()` for service layer queries
- Implement `to_dict()` method for consistent API responses (matches Document model pattern)

---

## 2. Avatar Upload & Processing

### Decision: FastAPI UploadFile with Pillow Processing

**Rationale**:
- **FastAPI UploadFile**: Already used in `/backend/app/routers/kb.py` for document uploads - consistent pattern
- **Pillow 12.1.0**: Already installed in environment (`pip list` shows pillow 12.1.0) - zero new dependencies
- **Local Filesystem**: Existing pattern in `/backend/app/services/file_storage.py` for document storage - reuse same approach
- **Async I/O**: FastAPI `UploadFile.read()` is async-compatible

**Image Upload Handling** (FastAPI multipart/form-data):

```python
# backend/app/routers/profile.py (NEW FILE)
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.services import avatar_service

router = APIRouter(prefix="/api/profile", tags=["profile"])

@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload user avatar image.

    - Accepts: JPG, PNG, GIF (< 5MB)
    - Processes: Resize to 200x200px, convert to JPEG, optimize
    - Returns: Avatar URL path
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only images (JPG, PNG, GIF) are allowed."
        )

    # Read file content
    content = await file.read()

    # Validate file size (5MB limit)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="File size exceeds 5MB limit."
        )

    # Process and save avatar (service layer)
    try:
        # TODO: Get user_id from JWT auth
        user_id = "demo-user-123"  # Replace with auth middleware
        avatar_path = await avatar_service.save_avatar(
            user_id=user_id,
            image_content=content,
            filename=file.filename,
        )

        # Update user profile in database
        await avatar_service.update_user_avatar(db, user_id, avatar_path)

        return {
            "success": True,
            "avatar_url": f"/api/avatars/{avatar_path.split('/')[-1]}",
            "message": "Avatar uploaded successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Avatar upload failed: {str(e)}")
```

**Image Processing Service** (Pillow implementation):

```python
# backend/app/services/avatar_service.py (NEW FILE)
import io
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
from PIL import Image, ImageOps
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User

logger = logging.getLogger(__name__)

def get_avatar_storage_dir() -> Path:
    """Get avatar storage directory path."""
    settings = get_settings()
    # Store avatars in ./storage/avatars/
    storage_path = Path(settings.storage_dir).parent / "avatars"

    if not storage_path.is_absolute():
        # Resolve relative to backend directory
        backend_dir = Path(__file__).resolve().parent.parent.parent
        storage_path = backend_dir / storage_path

    storage_path.mkdir(parents=True, exist_ok=True)
    return storage_path


async def save_avatar(
    user_id: str,
    image_content: bytes,
    filename: str,
) -> str:
    """
    Process and save avatar image.

    Steps:
    1. Validate image format using Pillow
    2. Resize to 200x200px (thumbnail, maintain aspect ratio)
    3. Convert to JPEG (universally supported)
    4. Optimize quality (85% quality, progressive)
    5. Save to filesystem with unique name

    Args:
        user_id: User ID (for unique filename)
        image_content: Raw image bytes
        filename: Original filename (for extension detection)

    Returns:
        Relative path to saved avatar (e.g., "user123_20260203_abc.jpg")

    Raises:
        ValueError: If image is invalid or cannot be processed
    """
    storage_dir = get_avatar_storage_dir()

    # Validate and open image
    try:
        img = Image.open(io.BytesIO(image_content))
    except Exception as e:
        raise ValueError(f"Invalid image file: {str(e)}")

    # Verify format (only allow JPEG, PNG, GIF)
    if img.format not in ("JPEG", "PNG", "GIF"):
        raise ValueError(f"Unsupported format: {img.format}. Only JPG, PNG, GIF allowed.")

    # Convert to RGB (handles RGBA, palette modes)
    if img.mode in ("RGBA", "LA", "P"):
        # Create white background for transparency
        rgb_img = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        rgb_img.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        img = rgb_img
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Resize to 200x200 (thumbnail mode maintains aspect ratio, centers and crops)
    img = ImageOps.fit(img, (200, 200), Image.Resampling.LANCZOS)

    # Generate unique filename
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    content_hash = hashlib.md5(image_content).hexdigest()[:8]
    new_filename = f"{user_id}_{timestamp}_{content_hash}.jpg"
    file_path = storage_dir / new_filename

    # Save optimized JPEG
    img.save(
        file_path,
        format="JPEG",
        quality=85,  # Good balance between quality and size
        optimize=True,  # Enable Pillow optimizer
        progressive=True,  # Progressive JPEG (better for web)
    )

    logger.info(f"Saved avatar: {file_path} ({file_path.stat().st_size} bytes)")
    return new_filename


async def update_user_avatar(db: AsyncSession, user_id: str, avatar_filename: str) -> None:
    """
    Update user's avatar_url in database and delete old avatar.

    Args:
        db: Database session
        user_id: User ID
        avatar_filename: New avatar filename
    """
    # Get current user to find old avatar
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise ValueError(f"User {user_id} not found")

    old_avatar = user.avatar_url

    # Update database
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(avatar_url=avatar_filename)
    )
    await db.commit()

    # Delete old avatar file if exists
    if old_avatar:
        try:
            old_path = get_avatar_storage_dir() / old_avatar
            if old_path.exists():
                old_path.unlink()
                logger.info(f"Deleted old avatar: {old_path}")
        except Exception as e:
            logger.warning(f"Failed to delete old avatar: {e}")


def delete_avatar(user_id: str, avatar_filename: str) -> bool:
    """
    Delete avatar file from filesystem.

    Args:
        user_id: User ID (for validation)
        avatar_filename: Avatar filename to delete

    Returns:
        True if deleted, False if not found
    """
    storage_dir = get_avatar_storage_dir()
    file_path = storage_dir / avatar_filename

    # Security check: ensure filename matches user_id
    if not avatar_filename.startswith(user_id):
        logger.warning(f"Avatar filename {avatar_filename} does not match user_id {user_id}")
        return False

    if file_path.exists():
        file_path.unlink()
        logger.info(f"Deleted avatar: {file_path}")
        return True

    return False
```

**Serving Avatars** (static file endpoint):

```python
# backend/app/routers/profile.py (add to existing router)

@router.get("/avatars/{filename}")
async def get_avatar(filename: str):
    """
    Serve avatar image.

    - Security: Only serves files from avatars directory
    - Content-Type: image/jpeg
    - Caching: 1 hour (avatars rarely change)
    """
    from app.services import avatar_service

    storage_dir = avatar_service.get_avatar_storage_dir()
    file_path = storage_dir / filename

    # Security: Prevent directory traversal
    if not file_path.is_relative_to(storage_dir):
        raise HTTPException(status_code=403, detail="Access denied")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Avatar not found")

    return FileResponse(
        path=str(file_path),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=3600",  # 1 hour cache
        },
    )
```

**Account Initials Generation** (client-side):

```typescript
// frontend/src/lib/utils.ts (add to existing file)

/**
 * Generate account initials from display name.
 *
 * Rules:
 * - Single word: First letter (e.g., "Alice" → "A")
 * - Multiple words: First letter of first and last word (e.g., "John Doe" → "JD")
 * - Empty string: "??"
 * - Handles CJK, emoji, special characters gracefully
 *
 * @param displayName - User's display name
 * @returns Uppercase initials (max 2 characters)
 */
export function generateInitials(displayName: string): string {
  // Trim and filter empty strings
  const words = displayName.trim().split(/\s+/).filter(Boolean);

  if (words.length === 0) {
    return "??";
  }

  if (words.length === 1) {
    // Single word: take first character
    const firstChar = words[0][0];
    return firstChar ? firstChar.toUpperCase() : "?";
  }

  // Multiple words: first + last
  const firstChar = words[0][0] || "?";
  const lastChar = words[words.length - 1][0] || "?";
  return (firstChar + lastChar).toUpperCase();
}

// Test cases (run in Jest):
// generateInitials("John Doe") → "JD"
// generateInitials("Alice") → "A"
// generateInitials("Bob Smith Jr") → "BJ"
// generateInitials("張三 李四") → "張李"
// generateInitials("🎉 Party") → "🎉P"
// generateInitials("") → "??"
// generateInitials("  ") → "??"
```

**Security Best Practices**:
- ✅ **File type validation**: Check `content_type` AND Pillow format (prevents malicious file uploads)
- ✅ **Size limit**: 5MB enforced before processing (prevents DoS via large files)
- ✅ **Path sanitization**: Use `Path` object, check `is_relative_to()` to prevent directory traversal
- ✅ **Unique filenames**: Use timestamp + content hash (prevents filename collisions)
- ✅ **Content validation**: Pillow opens and validates image structure (catches corrupted files)
- ✅ **Format restriction**: Only JPEG, PNG, GIF allowed (blocks executable formats)

**Alternatives Considered**:
1. **ImageMagick**: Rejected - requires external binary, Pillow is pure Python and already installed
2. **Sharp (Node.js)**: Rejected - would require separate Node.js service, adds complexity
3. **Cloud Storage (S3/CloudFlare)**: Rejected for MVP - adds cost and complexity, can migrate later
4. **Base64 in database**: Rejected - 33% size overhead, poor query performance

**Implementation Notes**:
- Follow existing file storage pattern from `/backend/app/services/file_storage.py`
- Reuse `get_settings()` for storage directory configuration
- Use `FileResponse` pattern from `/backend/app/routers/kb.py:145` (document file serving)
- Add `AVATAR_STORAGE_DIR = "./storage/avatars"` to `app/config.py` Settings class

---

## 3. Qdrant Collections for Dashboard Metrics

### Decision: Reuse Existing Collections + Add Activity Metadata

**Rationale**:
After examining the codebase:
- Existing Qdrant setup in `/backend/app/services/vector_store.py` defines two collections:
  - `TEXT_COLLECTION = "text_chunks"` (line 32)
  - `IMAGE_COLLECTION = "image_chunks"` (line 33)
- Both collections store metadata in `payload` field (see `add_text_chunk` line 209, `add_image_chunk` line 247)
- **Do NOT create new collections** - leverage existing metadata capabilities

**Activity Logging Strategy**:

Instead of creating new Qdrant collections, **store activity metadata in existing chunk payloads**:

```python
# Modify existing add_text_chunk function (backend/app/services/vector_store.py)

def add_text_chunk(
    document_id: str,
    document_name: str,
    content: str,
    embedding: list[float],
    chunk_index: int,
    metadata: dict = None,
    user_id: str = None,  # NEW: Track who uploaded
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
        "user_id": user_id,  # NEW: For filtering by user
        "created_at": datetime.utcnow().isoformat(),  # NEW: For timeline
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
```

**Query History Tracking** (separate lightweight collection):

For query history (needed for "top topics"), create a **dedicated lightweight collection**:

```python
# backend/app/services/activity_tracker.py (NEW FILE)
from qdrant_client.models import PointStruct, VectorParams, Distance
from app.services.vector_store import get_client

ACTIVITY_COLLECTION = "user_activity"  # NEW collection

def ensure_activity_collection():
    """Create activity collection if not exists."""
    client = get_client()
    collections = client.get_collections().collections
    collection_names = [c.name for c in collections]

    if ACTIVITY_COLLECTION not in collection_names:
        # Use dummy 1-dimensional vector (we only need metadata, not search)
        client.create_collection(
            collection_name=ACTIVITY_COLLECTION,
            vectors_config=VectorParams(size=1, distance=Distance.COSINE),
        )


def log_user_activity(
    user_id: str,
    activity_type: str,  # "query", "upload", "delete", "login"
    metadata: dict = None,
):
    """
    Log user activity for dashboard.

    Args:
        user_id: User ID
        activity_type: Type of activity
        metadata: Additional context (e.g., query_text, document_id)
    """
    import uuid
    from datetime import datetime

    client = get_client()
    ensure_activity_collection()

    payload = {
        "user_id": user_id,
        "activity_type": activity_type,
        "timestamp": datetime.utcnow().isoformat(),
        **(metadata or {}),
    }

    client.upsert(
        collection_name=ACTIVITY_COLLECTION,
        points=[
            PointStruct(
                id=str(uuid.uuid4()),
                vector=[0.0],  # Dummy vector (we don't search by vector)
                payload=payload,
            )
        ],
    )


def get_user_activity(user_id: str, limit: int = 20) -> list[dict]:
    """
    Get recent activity for user.

    Returns list sorted by timestamp DESC (newest first).
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    client = get_client()

    # Scroll to get all matching records (Qdrant doesn't support ORDER BY directly)
    results = client.scroll(
        collection_name=ACTIVITY_COLLECTION,
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="user_id",
                    match=MatchValue(value=user_id),
                )
            ]
        ),
        limit=1000,  # Get up to 1000 records
    )

    # Extract payloads and sort by timestamp
    activities = [record.payload for record in results[0]]
    activities.sort(key=lambda x: x["timestamp"], reverse=True)

    return activities[:limit]


def get_top_topics(user_id: str, limit: int = 5) -> list[dict]:
    """
    Get top searched topics for user.

    Returns list of {query_text: str, count: int} sorted by count DESC.
    """
    from collections import Counter
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    client = get_client()

    # Get all query activities
    results = client.scroll(
        collection_name=ACTIVITY_COLLECTION,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                FieldCondition(key="activity_type", match=MatchValue(value="query")),
            ]
        ),
        limit=1000,
    )

    # Count query texts
    queries = [r.payload.get("query_text", "") for r in results[0]]
    query_counts = Counter(queries).most_common(limit)

    return [{"query_text": q, "count": c} for q, c in query_counts]
```

**When to Log Activity**:

```python
# backend/app/routers/chat.py (modify existing endpoint)
from app.services import activity_tracker

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    # ... existing chat logic ...

    # Log query activity
    activity_tracker.log_user_activity(
        user_id="demo-user-123",  # Replace with auth user_id
        activity_type="query",
        metadata={"query_text": request.query},
    )

    # ... return response ...
```

**Performance Optimization**:

- **Batch Queries**: Use `scroll()` instead of repeated `query()` calls
- **Limit Results**: Always specify `limit` parameter to prevent memory overflow
- **Filter Early**: Use Qdrant `Filter` to reduce data transfer (filter by user_id on server side)
- **Cache Aggregations**: Cache top topics in Redis (recalculate every 5 minutes)

**Collection Schema Summary**:

| Collection | Purpose | Vector Dim | Payload Fields |
|------------|---------|------------|----------------|
| `text_chunks` (existing) | Document search | 384 | +`user_id`, +`created_at` |
| `image_chunks` (existing) | Image search | 512 | +`user_id`, +`created_at` |
| `user_activity` (NEW) | Activity tracking | 1 (dummy) | `user_id`, `activity_type`, `timestamp`, `query_text`, etc. |

**Alternatives Considered**:
1. **PostgreSQL for activity logs**: Rejected - Qdrant already in use, no need for second database for simple append-only logs
2. **Separate time-series database (InfluxDB)**: Rejected - over-engineering for MVP, adds infrastructure complexity
3. **Store all in PostgreSQL**: Rejected - Qdrant better suited for high-volume append operations

**Implementation Notes**:
- Follow existing Qdrant client pattern from `/backend/app/services/vector_store.py`
- Use `get_client()` singleton (lines 36-62)
- Reuse existing `VectorParams`, `PointStruct` imports (lines 7-13)
- Add `ensure_activity_collection()` call in app startup (modify `/backend/app/main.py` lifespan handler)

---

## 4. Dashboard Metrics Aggregation

### Decision: Hybrid SQL + Qdrant + Redis Caching

**Rationale**:
- **PostgreSQL**: Use for document counts, user counts (simple COUNT queries extremely fast)
- **Qdrant**: Use for activity timeline, top topics (already storing logs there)
- **Redis**: Cache aggregated results with 60-second TTL (balance between real-time and performance)
- **Target**: Dashboard load time < 3s (per success criteria)

**Dashboard Service Implementation**:

```python
# backend/app/services/dashboard_service.py (NEW FILE)
import json
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.document import Document
from app.services import activity_tracker, cache as cache_service

logger = logging.getLogger(__name__)

class DashboardMetrics:
    """Dashboard metrics data class."""

    def __init__(
        self,
        user_id: str,
        display_name: str,
        account_level: str,
        created_at: str,
        document_count: int,
        query_count: int,
        recent_activity: list[dict],
        top_topics: list[dict],
    ):
        self.user_id = user_id
        self.display_name = display_name
        self.account_level = account_level
        self.created_at = created_at
        self.document_count = document_count
        self.query_count = query_count
        self.recent_activity = recent_activity
        self.top_topics = top_topics

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "display_name": self.display_name,
            "account_level": self.account_level,
            "created_at": self.created_at,
            "document_count": self.document_count,
            "query_count": self.query_count,
            "recent_activity": self.recent_activity,
            "top_topics": self.top_topics,
        }


async def get_dashboard_metrics(
    db: AsyncSession,
    user_id: str,
    use_cache: bool = True,
) -> DashboardMetrics:
    """
    Get comprehensive dashboard metrics for user.

    Uses hybrid approach:
    1. PostgreSQL for user profile + document count
    2. Qdrant for activity timeline + top topics
    3. Redis for caching (60s TTL)

    Args:
        db: Database session
        user_id: User ID
        use_cache: Whether to use Redis cache

    Returns:
        DashboardMetrics object

    Raises:
        ValueError: If user not found
    """
    # Check cache first
    if use_cache:
        cache_key = f"dashboard:{user_id}"
        cached = cache_service.get_redis_client()
        if cached:
            try:
                cached_data = cached.get(cache_key)
                if cached_data:
                    data = json.loads(cached_data)
                    logger.info(f"Dashboard cache hit for user {user_id}")
                    return DashboardMetrics(**data)
            except Exception as e:
                logger.warning(f"Cache read error: {e}")

    # Fetch user profile
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise ValueError(f"User {user_id} not found")

    # Count documents uploaded by user
    # Note: Document model doesn't have user_id yet - add in migration
    # For now, count all documents (TODO: filter by user_id when available)
    doc_count_result = await db.execute(select(func.count(Document.id)))
    document_count = doc_count_result.scalar() or 0

    # Get activity timeline from Qdrant
    recent_activity = activity_tracker.get_user_activity(user_id, limit=20)

    # Count total queries
    query_count = sum(1 for a in recent_activity if a["activity_type"] == "query")

    # Get top topics from Qdrant
    top_topics = activity_tracker.get_top_topics(user_id, limit=5)

    # Build metrics object
    metrics = DashboardMetrics(
        user_id=user.id,
        display_name=user.display_name,
        account_level=user.account_level,
        created_at=user.created_at.isoformat() if user.created_at else "",
        document_count=document_count,
        query_count=query_count,
        recent_activity=recent_activity,
        top_topics=top_topics,
    )

    # Cache for 60 seconds
    if use_cache:
        cache_key = f"dashboard:{user_id}"
        cached = cache_service.get_redis_client()
        if cached:
            try:
                cached.setex(cache_key, 60, json.dumps(metrics.to_dict()))
                logger.info(f"Cached dashboard metrics for user {user_id} (TTL: 60s)")
            except Exception as e:
                logger.warning(f"Cache write error: {e}")

    return metrics


def invalidate_dashboard_cache(user_id: str) -> None:
    """
    Invalidate dashboard cache for user.

    Call this when:
    - User uploads new document
    - User updates profile
    - User performs new query
    """
    cache_key = f"dashboard:{user_id}"
    cached = cache_service.get_redis_client()
    if cached:
        try:
            cached.delete(cache_key)
            logger.info(f"Invalidated dashboard cache for user {user_id}")
        except Exception as e:
            logger.warning(f"Cache invalidation error: {e}")
```

**Dashboard API Endpoint**:

```python
# backend/app/routers/dashboard.py (MODIFY EXISTING FILE)
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.services import dashboard_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("/metrics")
async def get_dashboard_metrics(
    db: AsyncSession = Depends(get_db),
    # TODO: Get user_id from JWT auth
):
    """
    Get dashboard metrics for current user.

    Returns:
    - User profile info (name, account level, join date)
    - Document count (total documents uploaded)
    - Query count (total queries performed)
    - Recent activity timeline (last 20 actions)
    - Top topics (5 most queried topics)
    """
    try:
        # TODO: Replace with auth user_id
        user_id = "demo-user-123"

        metrics = await dashboard_service.get_dashboard_metrics(db, user_id)
        return metrics.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch dashboard: {str(e)}")
```

**Performance Benchmarks** (target: < 3s):

| Operation | Estimated Time | Optimization |
|-----------|----------------|--------------|
| PostgreSQL COUNT | 10-50ms | Indexed query |
| Qdrant scroll (1000 records) | 100-200ms | Use `limit` parameter |
| Python aggregation (top topics) | 5-10ms | Counter is O(n) |
| Redis cache read | 1-2ms | Network latency |
| **Total (cache miss)** | ~200-300ms | Well under 3s target |
| **Total (cache hit)** | ~2-5ms | Instant |

**Cache Invalidation Strategy**:

```python
# When to invalidate cache:

# 1. After uploading document
@router.post("/kb/upload")
async def upload_document(...):
    # ... upload logic ...
    dashboard_service.invalidate_dashboard_cache(user_id)

# 2. After performing query
@router.post("/chat")
async def chat_endpoint(...):
    # ... chat logic ...
    dashboard_service.invalidate_dashboard_cache(user_id)

# 3. After updating profile
@router.put("/profile")
async def update_profile(...):
    # ... update logic ...
    dashboard_service.invalidate_dashboard_cache(user_id)
```

**Real-Time vs Cached Trade-off**:
- Cache TTL: 60 seconds (meets < 5s delay tolerance from requirements)
- Acceptable delay: Dashboard shows data up to 60s old
- Immediate invalidation on user actions (upload, query, profile update)

**Alternatives Considered**:
1. **No caching**: Rejected - unnecessary database load on high-traffic dashboards
2. **Pre-computed materialized views**: Rejected - SQLite doesn't support, PostgreSQL overkill for simple counts
3. **Client-side polling**: Rejected - server-side caching more efficient
4. **WebSocket real-time updates**: Rejected - over-engineering for MVP, 60s delay acceptable

**Implementation Notes**:
- Follow existing cache pattern from `/backend/app/services/cache.py`
- Reuse `get_redis_client()` singleton (line 23)
- Use existing `cache_service` module (already imported in routers)
- Add dashboard cache keys to existing Redis instance (no new infrastructure)

---

## 5. Frontend State Management

### Decision: Extend Existing Zustand Store

**Rationale**:
- Zustand already in use: `/frontend/src/store/useStore.ts` (line 1: `import { create } from 'zustand'`)
- Current store manages: user, conversations, UI state (sidebar)
- Profile data is **global state** (used across app: navbar avatar, profile page, dashboard)
- TypeScript-first: Existing store properly typed (line 58: `interface AppState`)

**Extend Store with Profile Slice**:

```typescript
// frontend/src/store/useStore.ts (MODIFY EXISTING FILE)

import { create } from 'zustand';
import { User, Conversation, Message, GlobalSettings, UserProfile, DashboardMetrics } from '@/types';

// Add to existing helper functions
const PROFILE_STORAGE_KEY = 'user_profile';
const loadStoredProfile = (): UserProfile | null => {
  if (typeof window === 'undefined') return null;
  try {
    const stored = localStorage.getItem(PROFILE_STORAGE_KEY);
    return stored ? JSON.parse(stored) : null;
  } catch {
    return null;
  }
};

const saveStoredProfile = (profile: UserProfile | null) => {
  if (typeof window === 'undefined') return;
  if (profile) {
    localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(profile));
  } else {
    localStorage.removeItem(PROFILE_STORAGE_KEY);
  }
};

interface AppState {
  // ... existing user/conversations/UI state ...

  // Profile state (NEW)
  profile: UserProfile | null;
  profileLoading: boolean;
  profileError: string | null;
  setProfile: (profile: UserProfile) => void;
  updateProfile: (updates: Partial<UserProfile>) => void;
  clearProfile: () => void;

  // Dashboard state (NEW)
  dashboardMetrics: DashboardMetrics | null;
  dashboardLoading: boolean;
  dashboardError: string | null;
  setDashboardMetrics: (metrics: DashboardMetrics) => void;
  refreshDashboard: () => Promise<void>;

  // Avatar upload state (NEW)
  avatarUploading: boolean;
  avatarUploadProgress: number;
  setAvatarUploading: (uploading: boolean, progress?: number) => void;
}

export const useStore = create<AppState>((set, get) => ({
  // ... existing state ...

  // Profile state
  profile: loadStoredProfile(),
  profileLoading: false,
  profileError: null,

  setProfile: (profile) => {
    saveStoredProfile(profile);
    set({ profile, profileError: null });
  },

  updateProfile: (updates) => {
    const currentProfile = get().profile;
    if (!currentProfile) return;

    const updatedProfile = { ...currentProfile, ...updates };
    saveStoredProfile(updatedProfile);
    set({ profile: updatedProfile });
  },

  clearProfile: () => {
    saveStoredProfile(null);
    set({ profile: null, dashboardMetrics: null });
  },

  // Dashboard state
  dashboardMetrics: null,
  dashboardLoading: false,
  dashboardError: null,

  setDashboardMetrics: (metrics) => {
    set({ dashboardMetrics: metrics, dashboardError: null });
  },

  refreshDashboard: async () => {
    set({ dashboardLoading: true, dashboardError: null });
    try {
      const response = await fetch('/api/dashboard/metrics');
      if (!response.ok) throw new Error('Failed to fetch dashboard');
      const metrics = await response.json();
      set({ dashboardMetrics: metrics, dashboardLoading: false });
    } catch (error) {
      set({
        dashboardError: error instanceof Error ? error.message : 'Unknown error',
        dashboardLoading: false
      });
    }
  },

  // Avatar upload state
  avatarUploading: false,
  avatarUploadProgress: 0,

  setAvatarUploading: (uploading, progress = 0) => {
    set({ avatarUploading: uploading, avatarUploadProgress: progress });
  },
}));
```

**TypeScript Types** (add to `/frontend/src/types/index.ts`):

```typescript
// frontend/src/types/index.ts (MODIFY EXISTING FILE)

export interface UserProfile {
  id: string;
  email: string;
  display_name: string;
  avatar_url: string | null;
  account_level: 'free' | 'pro' | 'enterprise';
  created_at: string;  // ISO 8601 format
  updated_at: string;
}

export interface DashboardMetrics {
  user_id: string;
  display_name: string;
  account_level: string;
  created_at: string;
  document_count: number;
  query_count: number;
  recent_activity: ActivityItem[];
  top_topics: TopicItem[];
}

export interface ActivityItem {
  activity_type: 'query' | 'upload' | 'delete' | 'login';
  timestamp: string;
  metadata?: Record<string, any>;
}

export interface TopicItem {
  query_text: string;
  count: number;
}
```

**Avatar Upload Progress Hook**:

```typescript
// frontend/src/hooks/useAvatarUpload.ts (NEW FILE)
import { useState, useCallback } from 'react';
import { useStore } from '@/store/useStore';

interface UploadResult {
  success: boolean;
  avatar_url?: string;
  error?: string;
}

export function useAvatarUpload() {
  const { setAvatarUploading, updateProfile } = useStore();
  const [error, setError] = useState<string | null>(null);

  const uploadAvatar = useCallback(async (file: File): Promise<UploadResult> => {
    // Validate file size
    if (file.size > 5 * 1024 * 1024) {
      const error = 'File size exceeds 5MB limit';
      setError(error);
      return { success: false, error };
    }

    // Validate file type
    if (!file.type.startsWith('image/')) {
      const error = 'Only image files are allowed';
      setError(error);
      return { success: false, error };
    }

    setError(null);
    setAvatarUploading(true, 0);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch('/api/profile/avatar', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Upload failed');
      }

      const result = await response.json();

      // Update profile store with new avatar URL
      updateProfile({ avatar_url: result.avatar_url });

      setAvatarUploading(false, 100);
      return { success: true, avatar_url: result.avatar_url };
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Upload failed';
      setError(errorMessage);
      setAvatarUploading(false, 0);
      return { success: false, error: errorMessage };
    }
  }, [setAvatarUploading, updateProfile]);

  return {
    uploadAvatar,
    error,
  };
}
```

**Optimistic Updates Pattern**:

```typescript
// Example: Profile form with optimistic updates
function ProfileForm() {
  const { profile, updateProfile } = useStore();
  const [localDisplayName, setLocalDisplayName] = useState(profile?.display_name || '');

  const handleSave = async () => {
    // 1. Optimistic update (immediate UI feedback)
    updateProfile({ display_name: localDisplayName });

    try {
      // 2. API call
      const response = await fetch('/api/profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: localDisplayName }),
      });

      if (!response.ok) throw new Error('Update failed');

      const updatedProfile = await response.json();

      // 3. Confirm with server data (in case of server-side modifications)
      updateProfile(updatedProfile);
    } catch (error) {
      // 4. Rollback on error
      updateProfile({ display_name: profile?.display_name || '' });
      alert('Failed to update profile');
    }
  };

  return (
    <Form>
      <TextInput
        value={localDisplayName}
        onChange={(e) => setLocalDisplayName(e.target.value)}
      />
      <Button onClick={handleSave}>Save</Button>
    </Form>
  );
}
```

**Where to Store Profile Data**:
- ✅ **Global Zustand store**: Profile used in multiple places (navbar avatar, profile page, dashboard header)
- ✅ **LocalStorage persistence**: Survive page refreshes, reduce API calls on app load
- ❌ **NOT component-local state**: Would require prop drilling, inconsistent across components
- ❌ **NOT React Context**: Zustand more performant, better TypeScript support, already in use

**Avatar Upload Progress Tracking**:
- Store `avatarUploading` boolean and `avatarUploadProgress` (0-100) in Zustand
- Update from `useAvatarUpload` hook during upload
- Show progress bar in UI: `{avatarUploadProgress}%`
- Clear progress on success/error

**Alternatives Considered**:
1. **Redux Toolkit**: Rejected - Zustand already in use, Redux adds boilerplate
2. **React Query**: Rejected - overkill for simple profile CRUD, Zustand sufficient
3. **Component-local state**: Rejected - profile needed globally (navbar, settings, dashboard)
4. **React Context**: Rejected - Zustand more performant, better DevTools

**Implementation Notes**:
- Follow existing Zustand patterns from `/frontend/src/store/useStore.ts`
- Reuse localStorage helpers (lines 4-56 show existing pattern)
- Add types to `/frontend/src/types/index.ts` (existing User interface at line 3)
- Use existing `Message`, `Conversation` type patterns as reference

---

## Technology Stack Summary

| Component | Technology | Version | Rationale |
|-----------|-----------|---------|-----------|
| **Backend Framework** | FastAPI | 0.109+ | Already in use, async support, OpenAPI docs |
| **Database** | PostgreSQL | (via asyncpg) | **Correction**: Not SQLite - platform standardized on PostgreSQL |
| **ORM** | SQLAlchemy | 2.0+ (async) | Already in use for structured data models |
| **Image Processing** | Pillow | 12.1.0 | Already installed, robust, async-compatible |
| **Vector Database** | Qdrant | 1.7+ | Already in use for embeddings, good for activity logs |
| **Caching** | Redis | 5.0+ | Already in use for query cache, fast in-memory |
| **Frontend Framework** | Next.js + React | 16.1.6 + 19 | Already in use, TypeScript strict mode |
| **UI Library** | IBM Carbon | 1.100+ | Already in use, WCAG compliant, consistent design |
| **State Management** | Zustand | 5.0+ | Already in use, TypeScript-first, minimal boilerplate |
| **Styling** | Tailwind CSS | v4 | Already in use for custom layouts, responsive utilities |

**Dependencies to Add**: NONE - all required libraries already installed

**New Files to Create**:
- Backend: `user.py` (model), `avatar_service.py`, `activity_tracker.py`, `dashboard_service.py`, `profile.py` (router)
- Frontend: `useAvatarUpload.ts`, `Avatar.tsx`, `ProfileForm.tsx`, `MetricCard.tsx`, etc.

---

## Risk Analysis & Mitigation

### High Priority Risks ⚠️

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **Concurrent profile updates** | Data loss, race conditions | Medium | Use optimistic locking with `updated_at` timestamp check |
| **Large activity logs (10k+ records)** | Slow dashboard load | Medium | Implement pagination (show 20, load more on demand), cache aggregations |
| **Avatar storage growth** | Disk space exhaustion | Low | Set up log rotation, monitor disk usage, implement cleanup job for deleted users |

### Medium Priority Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **Cache invalidation bugs** | Stale data on dashboard | Medium | Comprehensive testing, manual refresh button as fallback |
| **Image upload security** | Malicious file upload | Low | Validate file type via Pillow (not just extension), size limit enforcement |
| **Database migration failure** | Broken deployment | Low | Test migrations in staging, implement rollback plan |

### Resolved Risks ✅

- **Database choice**: Resolved - Use existing PostgreSQL (not SQLite)
- **Image processing library**: Resolved - Pillow already installed
- **State management**: Resolved - Zustand already in use
- **Avatar serving performance**: Resolved - Use FileResponse with caching headers

---

## Performance Targets & Validation

| Metric | Target | Measurement Method | Pass Criteria |
|--------|--------|-------------------|---------------|
| Avatar upload | < 10s | Frontend timer (upload start to completion) | 95th percentile < 10s |
| Dashboard load | < 3s | Backend API response time + frontend render | 95th percentile < 3s |
| Profile update | < 30s from login | User flow timing (login to seeing updated name) | Median < 30s |
| Image size (processed) | < 50KB | File size after Pillow optimization | Average < 50KB |
| Redis cache hit rate | > 70% | Redis INFO stats | Overall hit rate > 70% |

**Testing Strategy**:
- **Unit Tests**: Avatar processing, initials generation, cache logic
- **Integration Tests**: API endpoints with database
- **E2E Tests** (optional): Full upload flow, dashboard load
- **Performance Tests**: Load test dashboard endpoint (100 concurrent users)

---

## Next Steps (Implementation Roadmap)

### Phase 0: Research ✅ COMPLETE
- Technical decisions documented
- Architecture reviewed
- Risks identified

### Phase 1: Design & Contracts (Next)
1. **Create data-model.md**: User, UserProfile, DashboardMetrics entities
2. **Generate API contracts**: `profile-api.yaml`, `dashboard-api.yaml`
3. **Create quickstart.md**: Developer setup for profile feature
4. **Update CLAUDE.md**: Add profile/dashboard context

### Phase 2: Implementation
1. **Database**: Create User model, run migrations
2. **Backend Services**: Avatar processing, activity tracking, dashboard aggregation
3. **API Endpoints**: Profile CRUD, avatar upload, dashboard metrics
4. **Frontend Components**: Avatar display, profile form, dashboard page
5. **State Management**: Extend Zustand store, create hooks

### Phase 3: Testing & Validation
1. **Unit Tests**: Service layer, utility functions
2. **Integration Tests**: API endpoints
3. **E2E Tests**: Critical flows (upload avatar, view dashboard)
4. **Performance Testing**: Dashboard load under concurrent users

### Phase 4: Documentation & Deployment
1. **API Documentation**: OpenAPI spec updates
2. **User Guide**: Profile settings and dashboard usage
3. **Deployment**: Migration plan, rollback procedure

---

## References & Resources

### Existing Codebase Patterns
- **Database Models**: `/backend/app/models/document.py` (SQLAlchemy async pattern)
- **File Storage**: `/backend/app/services/file_storage.py` (local filesystem pattern)
- **API Routers**: `/backend/app/routers/kb.py` (UploadFile handling, FileResponse)
- **Qdrant Usage**: `/backend/app/services/vector_store.py` (client singleton, collections)
- **Redis Caching**: `/backend/app/services/cache.py` (get/set pattern, TTL)
- **Zustand Store**: `/frontend/src/store/useStore.ts` (state management pattern)

### External Documentation
- [FastAPI File Uploads](https://fastapi.tiangolo.com/tutorial/request-files/)
- [Pillow Documentation](https://pillow.readthedocs.io/)
- [Qdrant Filtering](https://qdrant.tech/documentation/concepts/filtering/)
- [Carbon Design System](https://carbondesignsystem.com/components/overview)
- [Zustand Documentation](https://github.com/pmndrs/zustand)
- [PostgreSQL Async SQLAlchemy](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)

---

**Research Status**: ✅ COMPLETE
**Ready for Phase 1**: Yes
**Approver**: Development Team Lead
**Date**: 2026-02-03
