"""
Dashboard Service - Statistics and aggregations for dashboard.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_context

import logging

logger = logging.getLogger(__name__)


async def _safe_count(session: AsyncSession, sql: str) -> int:
    """Execute a count query, return 0 if table doesn't exist."""
    try:
        result = await session.execute(text(sql))
        row = result.fetchone()
        return int(row[0]) if row else 0
    except Exception as e:
        logger.warning(f"Dashboard query failed (returning 0): {e}")
        return 0


class DashboardService:
    """Service for dashboard statistics"""

    def __init__(self, session: Optional[AsyncSession] = None):
        self.session = session

    async def get_summary(self) -> Dict[str, Any]:
        """Get dashboard summary statistics from real tables."""
        async with get_db_context() as session:
            total_documents = await _safe_count(
                session,
                "SELECT COUNT(*) FROM documents"
            )
            total_queries_today = await _safe_count(
                session,
                "SELECT COUNT(*) FROM query_audit_log WHERE created_at >= CURRENT_DATE"
            )
            total_vehicles = await _safe_count(
                session,
                "SELECT COUNT(*) FROM maximo_mxasset"
            )
            open_faults = await _safe_count(
                session,
                "SELECT COUNT(*) FROM maximo_mxsr WHERE status != 'CLOSE'"
            )
            pending_workorders = await _safe_count(
                session,
                "SELECT COUNT(*) FROM maximo_mxwo WHERE status IN ('WAPPR', 'APPR')"
            )

            return {
                "total_documents": total_documents,
                "total_queries_today": total_queries_today,
                "total_vehicles": total_vehicles,
                "open_faults": open_faults,
                "pending_workorders": pending_workorders,
            }

    async def get_recent_queries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent queries from query_audit_log."""
        async with get_db_context() as session:
            try:
                result = await session.execute(text(
                    "SELECT id, user_id, question, created_at "
                    "FROM query_audit_log "
                    "ORDER BY created_at DESC "
                    f"LIMIT {limit}"
                ))
                rows = result.fetchall()
                return [
                    {
                        "id": str(row[0]),
                        "user_id": row[1],
                        "question": row[2],
                        "created_at": row[3].isoformat() if row[3] else None,
                    }
                    for row in rows
                ]
            except Exception as e:
                logger.warning(f"Failed to fetch recent queries: {e}")
                return []


def get_dashboard_service(session: Optional[AsyncSession] = None) -> DashboardService:
    """Get dashboard service instance"""
    return DashboardService(session)
