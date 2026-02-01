"""
Structured Query Service - Execute validated SQL and return results.
"""

import os
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_context


@dataclass
class QueryResult:
    """Query execution result"""
    success: bool
    data: List[Dict[str, Any]]
    row_count: int
    columns: List[str]
    execution_time_ms: float
    error: Optional[str] = None


class StructuredQueryService:
    """Service for executing structured queries"""
    
    def __init__(self, session: Optional[AsyncSession] = None):
        self.session = session
    
    async def execute_sql(self, sql: str, params: Optional[Dict] = None) -> QueryResult:
        """
        Execute a validated SQL query.
        
        Args:
            sql: Validated SQL query
            params: Optional query parameters
            
        Returns:
            QueryResult with data and metadata
        """
        start_time = datetime.now()
        
        try:
            if self.session:
                result = await self._execute_with_session(self.session, sql, params)
            else:
                async with get_db_context() as session:
                    result = await self._execute_with_session(session, sql, params)
            
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return QueryResult(
                success=True,
                data=result["data"],
                row_count=len(result["data"]),
                columns=result["columns"],
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            return QueryResult(
                success=False,
                data=[],
                row_count=0,
                columns=[],
                execution_time_ms=execution_time,
                error=str(e)
            )
    
    async def _execute_with_session(
        self, 
        session: AsyncSession, 
        sql: str, 
        params: Optional[Dict]
    ) -> Dict[str, Any]:
        """Execute query with given session"""
        result = await session.execute(text(sql), params or {})
        
        # Get column names
        columns = list(result.keys()) if result.returns_rows else []
        
        # Fetch all rows and convert to dicts
        rows = result.fetchall() if result.returns_rows else []
        data = [self._row_to_dict(row, columns) for row in rows]
        
        return {"data": data, "columns": columns}
    
    def _row_to_dict(self, row, columns: List[str]) -> Dict[str, Any]:
        """Convert a row to a JSON-serializable dict"""
        result = {}
        for i, col in enumerate(columns):
            value = row[i]
            result[col] = self._serialize_value(value)
        return result
    
    def _serialize_value(self, value: Any) -> Any:
        """Convert value to JSON-serializable type"""
        if value is None:
            return None
        if isinstance(value, (UUID,)):
            return str(value)
        if isinstance(value, (datetime,)):
            return value.isoformat()
        if isinstance(value, (date,)):
            return value.isoformat()
        if isinstance(value, (Decimal,)):
            return float(value)
        if isinstance(value, bytes):
            return value.decode('utf-8', errors='replace')
        return value
    
    async def get_vehicle_faults(
        self,
        vehicle_code: str,
        status: Optional[str] = None,
        fault_type: Optional[str] = None,
        limit: int = 100
    ) -> QueryResult:
        """
        Get fault records for a specific vehicle.
        
        Args:
            vehicle_code: Vehicle code (e.g., EMU801)
            status: Optional status filter
            fault_type: Optional fault type filter
            limit: Maximum rows to return
            
        Returns:
            QueryResult with fault records
        """
        sql = """
        SELECT 
            f.id,
            f.fault_code,
            f.fault_date,
            f.fault_type,
            f.severity,
            f.status,
            f.description,
            f.resolution,
            f.resolved_at,
            f.reported_by,
            v.vehicle_code,
            v.vehicle_type
        FROM fault_records f
        JOIN vehicles v ON f.vehicle_id = v.id
        WHERE v.vehicle_code = :vehicle_code
        """
        
        params = {"vehicle_code": vehicle_code}
        
        if status:
            sql += " AND f.status = :status"
            params["status"] = status
        
        if fault_type:
            sql += " AND f.fault_type = :fault_type"
            params["fault_type"] = fault_type
        
        sql += f" ORDER BY f.fault_date DESC LIMIT {limit}"
        
        return await self.execute_sql(sql, params)
    
    async def get_vehicle_maintenance(
        self,
        vehicle_code: str,
        status: Optional[str] = None,
        maintenance_type: Optional[str] = None,
        limit: int = 100
    ) -> QueryResult:
        """Get maintenance records for a specific vehicle."""
        sql = """
        SELECT 
            m.id,
            m.maintenance_code,
            m.maintenance_type,
            m.maintenance_date,
            m.completed_date,
            m.status,
            m.description,
            m.work_performed,
            m.labor_hours,
            m.labor_cost,
            m.technician,
            m.supervisor,
            v.vehicle_code,
            v.vehicle_type
        FROM maintenance_records m
        JOIN vehicles v ON m.vehicle_id = v.id
        WHERE v.vehicle_code = :vehicle_code
        """
        
        params = {"vehicle_code": vehicle_code}
        
        if status:
            sql += " AND m.status = :status"
            params["status"] = status
        
        if maintenance_type:
            sql += " AND m.maintenance_type = :maintenance_type"
            params["maintenance_type"] = maintenance_type
        
        sql += f" ORDER BY m.maintenance_date DESC LIMIT {limit}"
        
        return await self.execute_sql(sql, params)
    
    async def get_vehicle_costs(
        self,
        vehicle_code: str,
        cost_type: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100
    ) -> QueryResult:
        """Get cost records for a specific vehicle."""
        sql = """
        SELECT 
            c.id,
            c.record_date,
            c.cost_type,
            c.category,
            c.description,
            c.amount,
            c.currency,
            c.vendor,
            v.vehicle_code,
            v.vehicle_type
        FROM cost_records c
        JOIN vehicles v ON c.vehicle_id = v.id
        WHERE v.vehicle_code = :vehicle_code
        """
        
        params = {"vehicle_code": vehicle_code}
        
        if cost_type:
            sql += " AND c.cost_type = :cost_type"
            params["cost_type"] = cost_type
        
        if start_date:
            sql += " AND c.record_date >= :start_date"
            params["start_date"] = start_date
        
        if end_date:
            sql += " AND c.record_date <= :end_date"
            params["end_date"] = end_date
        
        sql += f" ORDER BY c.record_date DESC LIMIT {limit}"
        
        return await self.execute_sql(sql, params)
    
    async def get_vehicles(
        self,
        depot: Optional[str] = None,
        vehicle_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> QueryResult:
        """Get list of vehicles with optional filters."""
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
        WHERE 1=1
        """
        
        params = {}
        
        if depot:
            sql += " AND v.depot = :depot"
            params["depot"] = depot
        
        if vehicle_type:
            sql += " AND v.vehicle_type = :vehicle_type"
            params["vehicle_type"] = vehicle_type
        
        if status:
            sql += " AND v.status = :status"
            params["status"] = status
        
        sql += f" ORDER BY v.vehicle_code LIMIT {limit}"
        
        return await self.execute_sql(sql, params)
    
    async def get_parts_inventory(
        self,
        category: Optional[str] = None,
        low_stock_only: bool = False,
        limit: int = 100
    ) -> QueryResult:
        """Get parts inventory with optional filters."""
        sql = """
        SELECT 
            p.id,
            p.part_number,
            p.part_name,
            p.category,
            p.quantity_on_hand,
            p.minimum_quantity,
            p.unit_price,
            p.supplier,
            p.location,
            CASE WHEN p.quantity_on_hand <= p.minimum_quantity THEN true ELSE false END as is_low_stock
        FROM parts_inventory p
        WHERE 1=1
        """
        
        params = {}
        
        if category:
            sql += " AND p.category = :category"
            params["category"] = category
        
        if low_stock_only:
            sql += " AND p.quantity_on_hand <= p.minimum_quantity"
        
        sql += f" ORDER BY p.part_number LIMIT {limit}"
        
        return await self.execute_sql(sql, params)


# Factory function
def get_structured_query_service(session: Optional[AsyncSession] = None) -> StructuredQueryService:
    """Get structured query service instance"""
    return StructuredQueryService(session)
