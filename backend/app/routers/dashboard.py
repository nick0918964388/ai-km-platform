"""
Dashboard API - Statistics and aggregations for dashboard views.
"""

from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services.dashboard_service import get_dashboard_service


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


class SummaryResponse(BaseModel):
    """Dashboard summary response"""
    total_documents: int
    total_queries_today: int
    total_vehicles: int
    open_faults: int
    pending_workorders: int


class RecentQueryResponse(BaseModel):
    """Recent query item"""
    id: str
    user_id: Optional[str] = None
    question: Optional[str] = None
    created_at: Optional[str] = None


@router.get("/summary", response_model=SummaryResponse)
async def get_summary():
    """Get dashboard summary statistics."""
    service = get_dashboard_service()
    return await service.get_summary()


@router.get("/recent-queries", response_model=List[RecentQueryResponse])
async def get_recent_queries(
    limit: int = Query(10, ge=1, le=50, description="Number of recent queries")
):
    """Get recent queries from audit log."""
    service = get_dashboard_service()
    return await service.get_recent_queries(limit)
