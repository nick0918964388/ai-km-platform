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


    async def get_maximo_stats(self) -> Dict[str, Any]:
        """Get real-time Maximo dashboard statistics."""
        async with get_db_context() as session:
            # Summary counts
            total_wo = await _safe_count(session, "SELECT COUNT(*) FROM maximo_mxwo")
            active_wo = await _safe_count(
                session,
                "SELECT COUNT(*) FROM maximo_mxwo WHERE status NOT IN ('檢修完成', '工單退回')"
            )
            total_faults = await _safe_count(session, "SELECT COUNT(*) FROM maximo_mxsr")
            total_assets = await _safe_count(session, "SELECT COUNT(*) FROM maximo_mxasset")
            open_faults = await _safe_count(
                session,
                "SELECT COUNT(*) FROM maximo_mxsr WHERE status NOT IN ('結案', '取消')"
            )

            # Work orders by status
            try:
                result = await session.execute(text(
                    "SELECT status, COUNT(*) as count FROM maximo_mxwo "
                    "GROUP BY status ORDER BY count DESC"
                ))
                wo_by_status = [{"status": r[0] or "未知", "count": r[1]} for r in result.fetchall()]
            except Exception as e:
                logger.warning(f"wo_by_status failed: {e}")
                wo_by_status = []

            # Fault trend (last 30 days)
            try:
                result = await session.execute(text(
                    "SELECT DATE(zz_entrydate::timestamp) as date, COUNT(*) as count "
                    "FROM maximo_mxsr "
                    "WHERE zz_entrydate IS NOT NULL "
                    "AND zz_entrydate::timestamp >= NOW() - INTERVAL '30 days' "
                    "GROUP BY DATE(zz_entrydate::timestamp) "
                    "ORDER BY date"
                ))
                fault_trend = [
                    {"date": r[0].isoformat() if r[0] else None, "count": r[1]}
                    for r in result.fetchall()
                ]
            except Exception as e:
                logger.warning(f"fault_trend failed: {e}")
                fault_trend = []

            # Faults by status
            try:
                result = await session.execute(text(
                    "SELECT status, COUNT(*) as count FROM maximo_mxsr "
                    "GROUP BY status ORDER BY count DESC"
                ))
                fault_by_status = [{"status": r[0] or "未知", "count": r[1]} for r in result.fetchall()]
            except Exception as e:
                logger.warning(f"fault_by_status failed: {e}")
                fault_by_status = []

            # Work orders by depot
            try:
                result = await session.execute(text(
                    "SELECT a.eq2 as depot, COUNT(*) as count "
                    "FROM maximo_mxwo w JOIN maximo_mxasset a ON w.assetnum = a.assetnum "
                    "WHERE a.eq2 IS NOT NULL "
                    "GROUP BY a.eq2 ORDER BY count DESC"
                ))
                wo_by_depot = [{"depot": r[0], "count": r[1]} for r in result.fetchall()]
            except Exception as e:
                logger.warning(f"wo_by_depot failed: {e}")
                wo_by_depot = []

            # Recent faults
            try:
                result = await session.execute(text(
                    "SELECT ticketid, description, status, zz_entrydate "
                    "FROM maximo_mxsr ORDER BY zz_entrydate::timestamp DESC LIMIT 5"
                ))
                recent_faults = [
                    {
                        "id": r[0],
                        "description": (r[1] or "")[:100],
                        "status": r[2] or "未知",
                        "date": r[3] if r[3] else None,
                    }
                    for r in result.fetchall()
                ]
            except Exception as e:
                logger.warning(f"recent_faults failed: {e}")
                recent_faults = []

            return {
                "summary": {
                    "total_workorders": total_wo,
                    "active_workorders": active_wo,
                    "total_faults": total_faults,
                    "total_assets": total_assets,
                    "open_faults": open_faults,
                },
                "workorder_by_status": wo_by_status,
                "fault_trend": fault_trend,
                "fault_by_status": fault_by_status,
                "workorder_by_depot": wo_by_depot,
                "recent_faults": recent_faults,
            }


def get_dashboard_service(session: Optional[AsyncSession] = None) -> DashboardService:
    """Get dashboard service instance"""
    return DashboardService(session)
