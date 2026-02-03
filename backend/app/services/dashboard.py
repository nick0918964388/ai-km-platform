"""Dashboard service for user activity metrics and analytics."""

import logging
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Try to import Redis (optional dependency)
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available - dashboard caching disabled")

# Try to import Qdrant (for activity logs)
try:
    from app.services import vector_store
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    logger.warning("Qdrant not available - activity logs disabled")


# Redis configuration
REDIS_URL = "redis://localhost:6379"
CACHE_TTL = 60  # 60 seconds
redis_client: Optional[redis.Redis] = None


async def get_redis_client() -> Optional[redis.Redis]:
    """Get or create Redis client."""
    global redis_client

    if not REDIS_AVAILABLE:
        return None

    if redis_client is None:
        try:
            redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            await redis_client.ping()
            logger.info("Redis client connected")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}")
            return None

    return redis_client


async def get_document_count(db: AsyncSession, user_id: str) -> int:
    """
    Get total document count for a user.

    Args:
        db: Database session
        user_id: User ID

    Returns:
        Document count (0 if error or no documents table)
    """
    try:
        # Import Document model
        from app.models.document import Document

        # Count documents (no user_id filter in current schema)
        # TODO: Add user_id column to documents table for multi-user support
        result = await db.execute(
            select(func.count(Document.id))
        )
        count = result.scalar() or 0
        return count

    except Exception as e:
        logger.error(f"Error fetching document count for user {user_id}: {e}")
        return 0


async def get_query_count(db: AsyncSession, user_id: str) -> int:
    """
    Get total query count for a user.

    Args:
        db: Database session
        user_id: User ID

    Returns:
        Query count (0 if error or no queries table)
    """
    try:
        # Check if queries table exists
        # Since we don't have a Query model yet, return 0 for now
        # TODO: Create Query model and track user queries
        logger.info(f"Query count requested for user {user_id} - not implemented yet")
        return 0

    except Exception as e:
        logger.error(f"Error fetching query count for user {user_id}: {e}")
        return 0


async def get_recent_activity(user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Get recent activity entries for a user from Qdrant.

    Args:
        user_id: User ID
        limit: Maximum number of activity entries to return

    Returns:
        List of activity entries (newest first)
    """
    if not QDRANT_AVAILABLE:
        logger.warning("Qdrant not available - returning empty activity list")
        return []

    try:
        # Get Qdrant client
        client = vector_store.get_client()

        # Check if activity_logs collection exists
        collections = client.get_collections().collections
        collection_names = [c.name for c in collections]

        if "activity_logs" not in collection_names:
            logger.info("activity_logs collection doesn't exist yet")
            return []

        # Scroll through activity logs for this user
        # Note: Qdrant scroll doesn't support filtering by user_id directly
        # For MVP, return all activities (limit to 20)
        # TODO: Implement proper filtering by user_id using metadata
        records, _ = client.scroll(
            collection_name="activity_logs",
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

        # Format activity entries
        activities = []
        for record in records:
            payload = record.payload or {}
            activities.append({
                "action_type": payload.get("action_type", "unknown"),
                "timestamp": payload.get("timestamp", datetime.now().isoformat()),
                "metadata": payload.get("metadata", {}),
            })

        # Sort by timestamp (newest first)
        activities.sort(key=lambda x: x["timestamp"], reverse=True)

        return activities[:limit]

    except Exception as e:
        logger.error(f"Error fetching recent activity for user {user_id}: {e}")
        return []


async def get_top_topics(db: AsyncSession, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Get top searched topics for a user.

    Args:
        db: Database session
        user_id: User ID
        limit: Number of top topics to return

    Returns:
        List of topic entries with query_text and count
    """
    try:
        # Since we don't have a Query model yet, return empty list
        # TODO: Implement query tracking and GROUP BY aggregation
        logger.info(f"Top topics requested for user {user_id} - not implemented yet")
        return []

    except Exception as e:
        logger.error(f"Error fetching top topics for user {user_id}: {e}")
        return []


async def get_metrics(
    db: AsyncSession,
    user_id: str,
    refresh: bool = False
) -> Dict[str, Any]:
    """
    Get complete dashboard metrics for a user.

    Aggregates:
    - Document count
    - Query count
    - Recent activity (last 20)
    - Top topics (top 5)
    - User profile info

    Uses Redis caching with 60s TTL (unless refresh=True).

    Args:
        db: Database session
        user_id: User ID
        refresh: If True, bypass cache and fetch fresh data

    Returns:
        Dashboard metrics dictionary
    """
    cache_key = f"dashboard:{user_id}"

    # Try to get from cache (unless refresh requested)
    if not refresh:
        redis_conn = await get_redis_client()
        if redis_conn:
            try:
                cached_data = await redis_conn.get(cache_key)
                if cached_data:
                    logger.info(f"Dashboard cache hit for user {user_id}")
                    return json.loads(cached_data)
            except Exception as e:
                logger.warning(f"Redis cache read error: {e}")

    # Fetch fresh data
    logger.info(f"Fetching fresh dashboard metrics for user {user_id}")

    try:
        # Get user profile
        from app.services.profile import get_user_profile
        profile = await get_user_profile(db, user_id)

        if not profile:
            raise ValueError(f"User {user_id} not found")

        # Fetch all metrics in parallel (where possible)
        document_count = await get_document_count(db, user_id)
        query_count = await get_query_count(db, user_id)
        recent_activity = await get_recent_activity(user_id, limit=20)
        top_topics = await get_top_topics(db, user_id, limit=5)

        # Build metrics response
        metrics = {
            "user_id": user_id,
            "display_name": profile.display_name,
            "account_level": profile.account_level,
            "created_at": profile.created_at.isoformat() if profile.created_at else None,
            "document_count": document_count,
            "query_count": query_count,
            "recent_activity": recent_activity,
            "top_topics": top_topics,
        }

        # Cache the result
        redis_conn = await get_redis_client()
        if redis_conn:
            try:
                await redis_conn.setex(
                    cache_key,
                    CACHE_TTL,
                    json.dumps(metrics)
                )
                logger.info(f"Dashboard metrics cached for user {user_id}")
            except Exception as e:
                logger.warning(f"Redis cache write error: {e}")

        return metrics

    except Exception as e:
        logger.error(f"Error fetching dashboard metrics for user {user_id}: {e}")
        raise
