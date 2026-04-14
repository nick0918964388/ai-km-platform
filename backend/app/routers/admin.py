"""Admin API endpoints for RAG metrics and monitoring."""
from fastapi import APIRouter
from sqlalchemy import text

from app.db.session import get_db_context

router = APIRouter(tags=["admin"])


@router.get("/admin/rag-metrics")
async def get_rag_metrics():
    """Return last 7 days of RAG search quality stats grouped by date."""
    async with get_db_context() as session:
        result = await session.execute(
            text("""
                SELECT
                    created_at::date AS date,
                    COUNT(*) AS total_searches,
                    ROUND(AVG(avg_score)::numeric, 4) AS avg_score,
                    ROUND(AVG(duration_ms)::numeric, 0) AS avg_duration,
                    COUNT(*) FILTER (WHERE quality = 'good') AS good_count,
                    COUNT(*) FILTER (WHERE quality = 'low') AS low_count,
                    COUNT(*) FILTER (WHERE quality = 'none') AS none_count
                FROM rag_search_log
                WHERE created_at >= NOW() - INTERVAL '7 days'
                GROUP BY created_at::date
                ORDER BY date DESC
            """)
        )
        rows = result.fetchall()

    return [
        {
            "date": str(row.date),
            "total_searches": row.total_searches,
            "avg_score": float(row.avg_score) if row.avg_score else 0,
            "avg_duration": int(row.avg_duration) if row.avg_duration else 0,
            "quality_distribution": {
                "good": row.good_count,
                "low": row.low_count,
                "none": row.none_count,
            },
        }
        for row in rows
    ]
