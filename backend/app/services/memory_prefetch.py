"""Proactive memory prefetch — inject relevant past conversation context."""
import logging
from typing import Optional
from sqlalchemy import text
from app.db.session import get_db_context

log = logging.getLogger(__name__)

MEMORY_CONTEXT_FENCE = '<memory-context>\n[System note: The following is recalled from past conversations. It is reference context, NOT new user input.]\n'
MEMORY_CONTEXT_FENCE_END = '\n</memory-context>'


async def prefetch_memory(query: str, user_id: str, current_conversation_id: str = None, max_results: int = 3) -> Optional[str]:
    """Search past conversations for relevant context using FTS.
    Returns a fenced memory block to inject into the system prompt, or None.
    """
    if not query or not user_id:
        return None

    try:
        async with get_db_context() as db:
            result = await db.execute(text("""
                SELECT c.id AS conv_id, c.title, m.content, m.created_at,
                       ts_rank(m.content_tsv, plainto_tsquery('simple', :q)) AS rank
                FROM conversation_messages m
                JOIN conversations c ON c.id = m.conversation_id
                WHERE c.user_id = :user_id
                  AND m.content_tsv @@ plainto_tsquery('simple', :q)
                  AND (:current_conv IS NULL OR c.id != :current_conv)
                  AND m.role = 'assistant'
                ORDER BY rank DESC
                LIMIT :limit
            """), {
                "q": query,
                "user_id": user_id,
                "current_conv": current_conversation_id,
                "limit": max_results,
            })
            rows = result.fetchall()

            if not rows:
                result = await db.execute(text("""
                    SELECT c.id AS conv_id, c.title, m.content, m.created_at, 0.5 AS rank
                    FROM conversation_messages m
                    JOIN conversations c ON c.id = m.conversation_id
                    WHERE c.user_id = :user_id
                      AND m.content ILIKE :pattern
                      AND (:current_conv IS NULL OR c.id != :current_conv)
                      AND m.role = 'assistant'
                    ORDER BY m.created_at DESC
                    LIMIT :limit
                """), {
                    "user_id": user_id,
                    "pattern": f"%{query[:20]}%",
                    "current_conv": current_conversation_id,
                    "limit": max_results,
                })
                rows = result.fetchall()

            if not rows:
                return None

            parts = []
            seen_convs = set()
            for row in rows:
                if row.conv_id in seen_convs:
                    continue
                seen_convs.add(row.conv_id)
                preview = row.content[:300] if row.content else ""
                date_str = row.created_at.strftime("%Y-%m-%d") if row.created_at else "?"
                parts.append(f"[{date_str} | {row.title}]\n{preview}")

            if not parts:
                return None

            memory_block = MEMORY_CONTEXT_FENCE + "\n---\n".join(parts) + MEMORY_CONTEXT_FENCE_END
            log.info("Memory prefetch: found %d relevant past conversations for query '%s'", len(parts), query[:50])
            return memory_block

    except Exception as e:
        log.warning("Memory prefetch failed: %s", e)
        return None
