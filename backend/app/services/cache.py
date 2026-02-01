"""Redis cache service for query results."""
import hashlib
import json
import logging
from typing import Optional, Any
import redis

from app.config import get_settings

logger = logging.getLogger(__name__)

# Redis client singleton
_redis_client: Optional[redis.Redis] = None
_cache_enabled: bool = True

# Cache statistics (in-memory, reset on restart)
_cache_stats = {
    "hits": 0,
    "misses": 0,
}


def get_redis_client() -> Optional[redis.Redis]:
    """Get or create Redis client."""
    global _redis_client, _cache_enabled

    if not _cache_enabled:
        return None

    if _redis_client is None:
        settings = get_settings()
        try:
            _redis_client = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            # Test connection
            _redis_client.ping()
            logger.info(f"Connected to Redis at {settings.redis_url}")
        except redis.ConnectionError as e:
            logger.warning(f"Failed to connect to Redis: {e}")
            logger.info("Cache disabled - falling back to direct search")
            _cache_enabled = False
            _redis_client = None
        except Exception as e:
            logger.error(f"Unexpected Redis error: {e}")
            _cache_enabled = False
            _redis_client = None

    return _redis_client


def is_cache_available() -> bool:
    """Check if cache is available."""
    client = get_redis_client()
    if client is None:
        return False
    try:
        client.ping()
        return True
    except Exception:
        return False


def normalize_query(query: str) -> str:
    """Normalize query for cache key generation."""
    # Remove extra whitespace
    normalized = " ".join(query.split())
    # Lowercase English parts (keep Chinese as-is)
    # Simple approach: just strip and lower
    return normalized.strip().lower()


def generate_cache_key(query: str, top_k: int) -> str:
    """Generate cache key from query and parameters."""
    normalized = normalize_query(query)
    # Create hash of normalized query
    query_hash = hashlib.md5(normalized.encode("utf-8")).hexdigest()[:16]
    return f"query:{query_hash}:top_k:{top_k}"


def get_cached_results(query: str, top_k: int) -> Optional[list[dict]]:
    """Get cached search results."""
    global _cache_stats
    import time

    client = get_redis_client()
    if client is None:
        return None

    cache_key = generate_cache_key(query, top_k)
    start_time = time.time()

    try:
        cached = client.get(cache_key)
        elapsed_ms = (time.time() - start_time) * 1000

        if cached:
            _cache_stats["hits"] += 1
            # Update hit count
            client.hincrby(f"{cache_key}:meta", "hit_count", 1)
            results = json.loads(cached)
            logger.info(
                f"Cache HIT: query='{query[:50]}...', "
                f"results={len(results)}, latency={elapsed_ms:.1f}ms"
            )
            return results
        else:
            _cache_stats["misses"] += 1
            logger.info(
                f"Cache MISS: query='{query[:50]}...', latency={elapsed_ms:.1f}ms"
            )
            return None
    except Exception as e:
        logger.error(f"Cache get error: {e}")
        _cache_stats["misses"] += 1
        return None


def set_cached_results(
    query: str,
    top_k: int,
    results: list[dict],
    ttl: Optional[int] = None,
) -> bool:
    """Cache search results with TTL."""
    client = get_redis_client()
    if client is None:
        return False

    settings = get_settings()
    cache_ttl = ttl or settings.cache_ttl
    cache_key = generate_cache_key(query, top_k)

    try:
        # Store results
        client.setex(
            cache_key,
            cache_ttl,
            json.dumps(results),
        )

        # Store metadata
        meta_key = f"{cache_key}:meta"
        client.hset(meta_key, mapping={
            "query": query,
            "top_k": str(top_k),
            "hit_count": "0",
        })
        client.expire(meta_key, cache_ttl)

        logger.debug(f"Cached results for query: {query[:50]}... (TTL: {cache_ttl}s)")
        return True
    except Exception as e:
        logger.error(f"Cache set error: {e}")
        return False


def invalidate_cache(pattern: Optional[str] = None, document_id: Optional[str] = None) -> int:
    """Invalidate cache entries."""
    client = get_redis_client()
    if client is None:
        return 0

    deleted = 0

    try:
        if pattern:
            # Delete by pattern
            cursor = 0
            while True:
                cursor, keys = client.scan(cursor, match=pattern, count=100)
                if keys:
                    deleted += client.delete(*keys)
                if cursor == 0:
                    break
        elif document_id:
            # For document-based invalidation, we need to clear all query caches
            # since we don't track which queries reference which documents
            # In production, consider using tags or a reverse index
            cursor = 0
            while True:
                cursor, keys = client.scan(cursor, match="query:*", count=100)
                if keys:
                    deleted += client.delete(*keys)
                if cursor == 0:
                    break
        else:
            # Clear all query caches
            cursor = 0
            while True:
                cursor, keys = client.scan(cursor, match="query:*", count=100)
                if keys:
                    deleted += client.delete(*keys)
                if cursor == 0:
                    break

        logger.info(f"Invalidated {deleted} cache entries")
        return deleted
    except Exception as e:
        logger.error(f"Cache invalidation error: {e}")
        return 0


def get_cache_stats() -> dict:
    """Get cache statistics."""
    client = get_redis_client()

    stats = {
        "total_keys": 0,
        "query_cache_count": 0,
        "task_cache_count": 0,
        "memory_usage_bytes": 0,
        "hit_rate": 0.0,
        "total_hits": _cache_stats["hits"],
        "total_misses": _cache_stats["misses"],
    }

    if client is None:
        return stats

    try:
        # Count keys by pattern
        query_count = 0
        task_count = 0

        cursor = 0
        while True:
            cursor, keys = client.scan(cursor, match="query:*", count=100)
            # Count only main keys, not meta keys
            query_count += sum(1 for k in keys if not k.endswith(":meta"))
            if cursor == 0:
                break

        cursor = 0
        while True:
            cursor, keys = client.scan(cursor, match="task:*", count=100)
            task_count += len(keys)
            if cursor == 0:
                break

        stats["query_cache_count"] = query_count
        stats["task_cache_count"] = task_count
        stats["total_keys"] = query_count + task_count

        # Calculate hit rate
        total = _cache_stats["hits"] + _cache_stats["misses"]
        if total > 0:
            stats["hit_rate"] = _cache_stats["hits"] / total

        # Get memory info
        try:
            info = client.info("memory")
            stats["memory_usage_bytes"] = info.get("used_memory", 0)
        except Exception:
            pass

        return stats
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        return stats


def clear_all_cache() -> int:
    """Clear all cache entries."""
    return invalidate_cache(pattern="*")
