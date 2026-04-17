"""Conversation persistence API endpoints."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import get_db
from app.auth import get_current_user

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class CreateConversationRequest(BaseModel):
    id: Optional[str] = None
    title: str = "新對話"


class UpdateConversationRequest(BaseModel):
    title: str


class AddMessageRequest(BaseModel):
    id: Optional[str] = None
    role: str
    content: str = ""
    metadata: dict = Field(default_factory=dict)


@router.get("")
async def list_conversations(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    user_id = user["id"]
    result = await db.execute(text("""
        SELECT c.id, c.title, c.updated_at, c.created_at,
               COUNT(m.id) AS message_count
        FROM conversations c
        LEFT JOIN conversation_messages m ON m.conversation_id = c.id
        WHERE c.user_id = :user_id
        GROUP BY c.id
        ORDER BY c.updated_at DESC
        LIMIT :limit
    """), {"user_id": user_id, "limit": limit})
    rows = result.fetchall()
    return [
        {
            "id": r.id,
            "title": r.title,
            "updatedAt": r.updated_at.isoformat() if r.updated_at else None,
            "createdAt": r.created_at.isoformat() if r.created_at else None,
            "messageCount": r.message_count,
        }
        for r in rows
    ]


@router.get("/search")
async def search_conversations(
    q: str,
    limit: int = 5,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    user_id = user["id"]

    # Try FTS first
    fts_result = await db.execute(text("""
        WITH matches AS (
            SELECT m.conversation_id, m.content, m.created_at,
                   ROW_NUMBER() OVER (PARTITION BY m.conversation_id ORDER BY m.created_at) AS rn
            FROM conversation_messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE m.content_tsv @@ plainto_tsquery('simple', :q)
              AND c.user_id = :user_id
        ),
        grouped AS (
            SELECT m.conversation_id,
                   COUNT(*) OVER (PARTITION BY m.conversation_id) AS match_count,
                   m.content AS preview,
                   m.rn
            FROM matches m
        )
        SELECT g.conversation_id, c.title, c.updated_at, g.match_count,
               LEFT(g.preview, 200) AS preview
        FROM grouped g
        JOIN conversations c ON c.id = g.conversation_id
        WHERE g.rn = 1
        ORDER BY g.match_count DESC
        LIMIT :limit
    """), {"q": q, "user_id": user_id, "limit": limit})
    rows = fts_result.fetchall()

    # Fallback to ILIKE if FTS returns nothing
    if not rows:
        like_result = await db.execute(text("""
            WITH matches AS (
                SELECT m.conversation_id, m.content, m.created_at,
                       ROW_NUMBER() OVER (PARTITION BY m.conversation_id ORDER BY m.created_at) AS rn
                FROM conversation_messages m
                JOIN conversations c ON c.id = m.conversation_id
                WHERE m.content ILIKE :pattern
                  AND c.user_id = :user_id
            ),
            grouped AS (
                SELECT m.conversation_id,
                       COUNT(*) OVER (PARTITION BY m.conversation_id) AS match_count,
                       m.content AS preview,
                       m.rn
                FROM matches m
            )
            SELECT g.conversation_id, c.title, c.updated_at, g.match_count,
                   LEFT(g.preview, 200) AS preview
            FROM grouped g
            JOIN conversations c ON c.id = g.conversation_id
            WHERE g.rn = 1
            ORDER BY g.match_count DESC
            LIMIT :limit
        """), {"pattern": f"%{q}%", "user_id": user_id, "limit": limit})
        rows = like_result.fetchall()

    return [
        {
            "conversationId": r.conversation_id,
            "title": r.title,
            "updatedAt": r.updated_at.isoformat() if r.updated_at else None,
            "preview": r.preview,
            "matchCount": r.match_count,
        }
        for r in rows
    ]


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    user_id = user["id"]
    result = await db.execute(text(
        "SELECT id, title, created_at, updated_at FROM conversations WHERE id = :id AND user_id = :user_id"
    ), {"id": conversation_id, "user_id": user_id})
    conv = result.fetchone()
    if not conv:
        raise HTTPException(status_code=404, detail="對話不存在")

    msgs = await db.execute(text("""
        SELECT id, role, content, created_at, metadata
        FROM conversation_messages
        WHERE conversation_id = :conv_id
        ORDER BY created_at ASC
    """), {"conv_id": conversation_id})
    messages = msgs.fetchall()

    return {
        "id": conv.id,
        "title": conv.title,
        "createdAt": conv.created_at.isoformat() if conv.created_at else None,
        "updatedAt": conv.updated_at.isoformat() if conv.updated_at else None,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "timestamp": m.created_at.isoformat() if m.created_at else None,
                **(m.metadata if isinstance(m.metadata, dict) else {}),
            }
            for m in messages
        ],
    }


@router.post("")
async def create_conversation(
    req: CreateConversationRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    user_id = user["id"]
    conv_id = req.id or str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    await db.execute(text("""
        INSERT INTO conversations (id, user_id, title, created_at, updated_at)
        VALUES (:id, :user_id, :title, :created_at, :updated_at)
        ON CONFLICT (id) DO NOTHING
    """), {
        "id": conv_id, "user_id": user_id, "title": req.title,
        "created_at": now, "updated_at": now,
    })
    return {"id": conv_id, "title": req.title}


@router.put("/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    req: UpdateConversationRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    user_id = user["id"]
    result = await db.execute(text(
        "UPDATE conversations SET title = :title, updated_at = NOW() WHERE id = :id AND user_id = :user_id RETURNING id"
    ), {"title": req.title, "id": conversation_id, "user_id": user_id})
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="對話不存在")
    return {"success": True}


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    user_id = user["id"]
    result = await db.execute(text(
        "DELETE FROM conversations WHERE id = :id AND user_id = :user_id RETURNING id"
    ), {"id": conversation_id, "user_id": user_id})
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="對話不存在")
    return {"success": True}


@router.post("/{conversation_id}/messages")
async def add_message(
    conversation_id: str,
    req: AddMessageRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    user_id = user["id"]
    # Verify ownership
    check = await db.execute(text(
        "SELECT id FROM conversations WHERE id = :id AND user_id = :user_id"
    ), {"id": conversation_id, "user_id": user_id})
    if not check.fetchone():
        raise HTTPException(status_code=404, detail="對話不存在")

    msg_id = req.id or str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    await db.execute(text("""
        INSERT INTO conversation_messages (id, conversation_id, role, content, created_at, metadata)
        VALUES (:id, :conv_id, :role, :content, :created_at, :metadata::jsonb)
        ON CONFLICT (id) DO UPDATE SET content = :content, metadata = :metadata::jsonb
    """), {
        "id": msg_id, "conv_id": conversation_id, "role": req.role,
        "content": req.content, "created_at": now,
        "metadata": __import__("json").dumps(req.metadata, ensure_ascii=False),
    })

    await db.execute(text(
        "UPDATE conversations SET updated_at = :now WHERE id = :id"
    ), {"now": now, "id": conversation_id})

    return {"id": msg_id}
