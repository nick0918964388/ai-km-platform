"""
Dashboard API - Statistics and aggregations for dashboard views.
"""

from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.session import get_db
from app.services.dashboard_service import get_dashboard_service


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


class SummaryResponse(BaseModel):
    """Dashboard summary response"""
    total_vehicles: int
    active_vehicles: int
    open_faults: int
    critical_faults: int
    fault_resolution_rate: float
    pending_maintenance: int
    low_stock_items: int
    total_cost_this_month: float


class FaultTrendResponse(BaseModel):
    """Fault trend data"""
    date: Optional[str]
    fault_type: str
    count: int


class CostDistributionResponse(BaseModel):
    """Cost distribution data"""
    cost_type: str
    amount: float
    percentage: float


class VehicleFaultRankResponse(BaseModel):
    """Vehicle fault ranking"""
    vehicle_code: str
    vehicle_type: str
    fault_count: int
    open_faults: int


class InventoryAlertResponse(BaseModel):
    """Inventory alert"""
    part_number: str
    part_name: str
    category: str
    quantity_on_hand: int
    minimum_quantity: int
    shortage: int


@router.get("/summary", response_model=SummaryResponse)
async def get_summary():
    """
    Get dashboard summary statistics.
    
    Returns key metrics including:
    - Total and active vehicles
    - Open and critical faults
    - Pending maintenance
    - Low stock alerts
    - Monthly cost total
    """
    service = get_dashboard_service()
    return await service.get_summary()


@router.get("/fault-trends", response_model=List[FaultTrendResponse])
async def get_fault_trends(
    days: int = Query(30, ge=1, le=365, description="Number of days to look back")
):
    """
    Get fault trends over time by type.
    
    Returns daily fault counts grouped by fault type.
    """
    service = get_dashboard_service()
    return await service.get_fault_trends(days)


@router.get("/cost-distribution", response_model=List[CostDistributionResponse])
async def get_cost_distribution(
    months: int = Query(3, ge=1, le=12, description="Number of months to look back")
):
    """
    Get cost distribution by type.
    
    Returns total costs and percentages by cost type.
    """
    service = get_dashboard_service()
    return await service.get_cost_distribution(months)


@router.get("/vehicle-fault-ranking", response_model=List[VehicleFaultRankResponse])
async def get_vehicle_fault_ranking(
    limit: int = Query(10, ge=1, le=100, description="Number of vehicles to return")
):
    """
    Get vehicles ranked by fault count.
    
    Returns top vehicles with highest fault counts in the last 90 days.
    """
    service = get_dashboard_service()
    return await service.get_vehicle_fault_ranking(limit)


@router.get("/inventory-alerts", response_model=List[InventoryAlertResponse])
async def get_inventory_alerts():
    """
    Get low stock inventory alerts.
    
    Returns all parts where quantity on hand is at or below minimum.
    """
    service = get_dashboard_service()
    return await service.get_inventory_alerts()
