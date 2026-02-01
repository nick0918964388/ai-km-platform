"""
Structured Data API Routes - Vehicle maintenance structured queries.
"""

from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.session import get_db
from app.services.structured_query import get_structured_query_service, QueryResult


router = APIRouter(prefix="/structured", tags=["Structured Data"])


# Response models
class VehicleResponse(BaseModel):
    id: str
    vehicle_code: str
    vehicle_type: str
    manufacturer: Optional[str]
    manufacture_year: Optional[int]
    status: str
    depot: Optional[str]
    last_maintenance_date: Optional[str]
    open_faults: int = 0


class FaultRecordResponse(BaseModel):
    id: str
    fault_code: str
    fault_date: str
    fault_type: str
    severity: str
    status: str
    description: Optional[str]
    resolution: Optional[str]
    resolved_at: Optional[str]
    reported_by: Optional[str]
    vehicle_code: str
    vehicle_type: str


class MaintenanceRecordResponse(BaseModel):
    id: str
    maintenance_code: str
    maintenance_type: str
    maintenance_date: str
    completed_date: Optional[str]
    status: str
    description: Optional[str]
    work_performed: Optional[str]
    labor_hours: Optional[float]
    labor_cost: Optional[float]
    technician: Optional[str]
    supervisor: Optional[str]
    vehicle_code: str
    vehicle_type: str


class CostRecordResponse(BaseModel):
    id: str
    record_date: str
    cost_type: str
    category: Optional[str]
    description: Optional[str]
    amount: float
    currency: str
    vendor: Optional[str]
    vehicle_code: str
    vehicle_type: str


class PartInventoryResponse(BaseModel):
    id: str
    part_number: str
    part_name: str
    category: str
    quantity_on_hand: int
    minimum_quantity: int
    unit_price: Optional[float]
    supplier: Optional[str]
    location: Optional[str]
    is_low_stock: bool


class QueryResultResponse(BaseModel):
    success: bool
    data: list
    row_count: int
    columns: list
    execution_time_ms: float
    error: Optional[str] = None


def query_result_to_response(result: QueryResult) -> QueryResultResponse:
    """Convert QueryResult to response model"""
    return QueryResultResponse(
        success=result.success,
        data=result.data,
        row_count=result.row_count,
        columns=result.columns,
        execution_time_ms=result.execution_time_ms,
        error=result.error
    )


@router.get("/vehicles", response_model=QueryResultResponse)
async def get_vehicles(
    depot: Optional[str] = Query(None, description="Filter by depot"),
    vehicle_type: Optional[str] = Query(None, description="Filter by vehicle type"),
    status: Optional[str] = Query(None, description="Filter by status (active/maintenance/retired)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of vehicles with optional filters.
    
    Returns vehicles with basic info and open fault count.
    """
    service = get_structured_query_service(db)
    result = await service.get_vehicles(
        depot=depot,
        vehicle_type=vehicle_type,
        status=status,
        limit=limit
    )
    return query_result_to_response(result)


@router.get("/vehicles/{vehicle_code}", response_model=QueryResultResponse)
async def get_vehicle(
    vehicle_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific vehicle by code.
    """
    service = get_structured_query_service(db)
    result = await service.get_vehicles(limit=1)
    
    # Filter to specific vehicle
    sql = """
    SELECT 
        v.id,
        v.vehicle_code,
        v.vehicle_type,
        v.manufacturer,
        v.manufacture_year,
        v.status,
        v.depot,
        v.last_maintenance_date,
        (SELECT COUNT(*) FROM fault_records f WHERE f.vehicle_id = v.id AND f.status = 'open') as open_faults
    FROM vehicles v
    WHERE v.vehicle_code = :vehicle_code
    """
    result = await service.execute_sql(sql, {"vehicle_code": vehicle_code})
    
    if result.row_count == 0:
        raise HTTPException(status_code=404, detail=f"Vehicle {vehicle_code} not found")
    
    return query_result_to_response(result)


@router.get("/vehicles/{vehicle_code}/faults", response_model=QueryResultResponse)
async def get_vehicle_faults(
    vehicle_code: str,
    status: Optional[str] = Query(None, description="Filter by status (open/in_progress/resolved)"),
    fault_type: Optional[str] = Query(None, description="Filter by fault type"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get fault records for a specific vehicle.
    
    Returns fault history ordered by date (newest first).
    """
    service = get_structured_query_service(db)
    result = await service.get_vehicle_faults(
        vehicle_code=vehicle_code,
        status=status,
        fault_type=fault_type,
        limit=limit
    )
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    
    return query_result_to_response(result)


@router.get("/vehicles/{vehicle_code}/maintenance", response_model=QueryResultResponse)
async def get_vehicle_maintenance(
    vehicle_code: str,
    status: Optional[str] = Query(None, description="Filter by status (pending/in_progress/completed)"),
    maintenance_type: Optional[str] = Query(None, description="Filter by type (scheduled/unscheduled/emergency)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get maintenance records for a specific vehicle.
    
    Returns maintenance history ordered by date (newest first).
    """
    service = get_structured_query_service(db)
    result = await service.get_vehicle_maintenance(
        vehicle_code=vehicle_code,
        status=status,
        maintenance_type=maintenance_type,
        limit=limit
    )
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    
    return query_result_to_response(result)


@router.get("/vehicles/{vehicle_code}/costs", response_model=QueryResultResponse)
async def get_vehicle_costs(
    vehicle_code: str,
    cost_type: Optional[str] = Query(None, description="Filter by cost type (labor/parts/external/other)"),
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get cost records for a specific vehicle.
    
    Returns cost history ordered by date (newest first).
    """
    service = get_structured_query_service(db)
    result = await service.get_vehicle_costs(
        vehicle_code=vehicle_code,
        cost_type=cost_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    
    return query_result_to_response(result)


@router.get("/inventory", response_model=QueryResultResponse)
async def get_inventory(
    category: Optional[str] = Query(None, description="Filter by category"),
    low_stock_only: bool = Query(False, description="Only show low stock items"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get parts inventory with optional filters.
    
    Returns inventory list with stock status.
    """
    service = get_structured_query_service(db)
    result = await service.get_parts_inventory(
        category=category,
        low_stock_only=low_stock_only,
        limit=limit
    )
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    
    return query_result_to_response(result)
