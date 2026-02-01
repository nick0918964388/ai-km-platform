"""
Export API - Download data as CSV/Excel files.
"""

from typing import Optional, List
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import io

from app.db.session import get_db
from app.services.structured_query import get_structured_query_service
from app.services.export_service import get_export_service, EXPORT_LABELS


router = APIRouter(prefix="/export", tags=["Export"])


def create_csv_response(csv_bytes: bytes, filename: str) -> StreamingResponse:
    """Create streaming response for CSV download"""
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/csv; charset=utf-8",
        }
    )


@router.get("/vehicles")
async def export_vehicles(
    depot: Optional[str] = Query(None),
    vehicle_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Export vehicles list to CSV"""
    service = get_structured_query_service(db)
    result = await service.get_vehicles(
        depot=depot,
        vehicle_type=vehicle_type,
        status=status,
        limit=10000
    )
    
    if not result.success:
        return {"error": result.error}
    
    export = get_export_service()
    csv_bytes = export.to_csv_bytes(result.data, result.columns)
    filename = export.generate_filename("vehicles")
    
    return create_csv_response(csv_bytes, filename)


@router.get("/vehicles/{vehicle_code}/faults")
async def export_vehicle_faults(
    vehicle_code: str,
    status: Optional[str] = Query(None),
    fault_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Export vehicle fault records to CSV"""
    service = get_structured_query_service(db)
    result = await service.get_vehicle_faults(
        vehicle_code=vehicle_code,
        status=status,
        fault_type=fault_type,
        limit=10000
    )
    
    if not result.success:
        return {"error": result.error}
    
    export = get_export_service()
    csv_bytes = export.to_csv_bytes(result.data, result.columns)
    filename = export.generate_filename(f"faults_{vehicle_code}")
    
    return create_csv_response(csv_bytes, filename)


@router.get("/vehicles/{vehicle_code}/maintenance")
async def export_vehicle_maintenance(
    vehicle_code: str,
    status: Optional[str] = Query(None),
    maintenance_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Export vehicle maintenance records to CSV"""
    service = get_structured_query_service(db)
    result = await service.get_vehicle_maintenance(
        vehicle_code=vehicle_code,
        status=status,
        maintenance_type=maintenance_type,
        limit=10000
    )
    
    if not result.success:
        return {"error": result.error}
    
    export = get_export_service()
    csv_bytes = export.to_csv_bytes(result.data, result.columns)
    filename = export.generate_filename(f"maintenance_{vehicle_code}")
    
    return create_csv_response(csv_bytes, filename)


@router.get("/vehicles/{vehicle_code}/costs")
async def export_vehicle_costs(
    vehicle_code: str,
    cost_type: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Export vehicle cost records to CSV"""
    service = get_structured_query_service(db)
    result = await service.get_vehicle_costs(
        vehicle_code=vehicle_code,
        cost_type=cost_type,
        start_date=start_date,
        end_date=end_date,
        limit=10000
    )
    
    if not result.success:
        return {"error": result.error}
    
    export = get_export_service()
    csv_bytes = export.to_csv_bytes(result.data, result.columns)
    filename = export.generate_filename(f"costs_{vehicle_code}")
    
    return create_csv_response(csv_bytes, filename)


@router.get("/inventory")
async def export_inventory(
    category: Optional[str] = Query(None),
    low_stock_only: bool = Query(False),
    db: AsyncSession = Depends(get_db)
):
    """Export parts inventory to CSV"""
    service = get_structured_query_service(db)
    result = await service.get_parts_inventory(
        category=category,
        low_stock_only=low_stock_only,
        limit=10000
    )
    
    if not result.success:
        return {"error": result.error}
    
    export = get_export_service()
    csv_bytes = export.to_csv_bytes(result.data, result.columns)
    filename = export.generate_filename("inventory")
    
    return create_csv_response(csv_bytes, filename)
