"""
Dashboard Service - Statistics and aggregations for dashboard.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, date, timedelta
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_context


@dataclass
class DashboardSummary:
    """Dashboard summary statistics"""
    total_vehicles: int
    active_vehicles: int
    open_faults: int
    critical_faults: int
    pending_maintenance: int
    low_stock_items: int
    total_cost_this_month: float
    fault_resolution_rate: float


@dataclass
class FaultTrend:
    """Fault trend data point"""
    date: str
    count: int
    fault_type: str


@dataclass
class CostDistribution:
    """Cost distribution by type"""
    cost_type: str
    amount: float
    percentage: float


class DashboardService:
    """Service for dashboard statistics"""
    
    def __init__(self, session: Optional[AsyncSession] = None):
        self.session = session
    
    async def get_summary(self) -> Dict[str, Any]:
        """Get dashboard summary statistics"""
        sql = """
        WITH vehicle_stats AS (
            SELECT 
                COUNT(*) as total_vehicles,
                COUNT(*) FILTER (WHERE status = 'active') as active_vehicles
            FROM vehicles
        ),
        fault_stats AS (
            SELECT 
                COUNT(*) FILTER (WHERE status = 'open') as open_faults,
                COUNT(*) FILTER (WHERE status = 'open' AND severity = 'critical') as critical_faults,
                CASE 
                    WHEN COUNT(*) > 0 
                    THEN ROUND(COUNT(*) FILTER (WHERE status = 'resolved')::numeric / COUNT(*) * 100, 1)
                    ELSE 0 
                END as resolution_rate
            FROM fault_records
            WHERE fault_date >= NOW() - INTERVAL '30 days'
        ),
        maintenance_stats AS (
            SELECT COUNT(*) as pending_maintenance
            FROM maintenance_records
            WHERE status = 'pending'
        ),
        inventory_stats AS (
            SELECT COUNT(*) as low_stock_items
            FROM parts_inventory
            WHERE quantity_on_hand <= minimum_quantity
        ),
        cost_stats AS (
            SELECT COALESCE(SUM(amount), 0) as total_cost_this_month
            FROM cost_records
            WHERE record_date >= DATE_TRUNC('month', CURRENT_DATE)
        )
        SELECT 
            v.total_vehicles,
            v.active_vehicles,
            f.open_faults,
            f.critical_faults,
            f.resolution_rate,
            m.pending_maintenance,
            i.low_stock_items,
            c.total_cost_this_month
        FROM vehicle_stats v, fault_stats f, maintenance_stats m, inventory_stats i, cost_stats c
        """
        
        async with get_db_context() as session:
            result = await session.execute(text(sql))
            row = result.fetchone()
            
            if row:
                return {
                    "total_vehicles": row[0],
                    "active_vehicles": row[1],
                    "open_faults": row[2],
                    "critical_faults": row[3],
                    "fault_resolution_rate": float(row[4]),
                    "pending_maintenance": row[5],
                    "low_stock_items": row[6],
                    "total_cost_this_month": float(row[7]),
                }
            
            return {
                "total_vehicles": 0,
                "active_vehicles": 0,
                "open_faults": 0,
                "critical_faults": 0,
                "fault_resolution_rate": 0,
                "pending_maintenance": 0,
                "low_stock_items": 0,
                "total_cost_this_month": 0,
            }
    
    async def get_fault_trends(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get fault trends by day and type"""
        sql = f"""
        SELECT 
            DATE(fault_date) as date,
            fault_type,
            COUNT(*) as count
        FROM fault_records
        WHERE fault_date >= NOW() - INTERVAL '{days} days'
        GROUP BY DATE(fault_date), fault_type
        ORDER BY date DESC, count DESC
        """
        
        async with get_db_context() as session:
            result = await session.execute(text(sql))
            rows = result.fetchall()
            
            return [
                {
                    "date": row[0].isoformat() if row[0] else None,
                    "fault_type": row[1],
                    "count": row[2],
                }
                for row in rows
            ]
    
    async def get_cost_distribution(self, months: int = 3) -> List[Dict[str, Any]]:
        """Get cost distribution by type"""
        sql = f"""
        SELECT 
            cost_type,
            SUM(amount) as amount
        FROM cost_records
        WHERE record_date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '{months} months'
        GROUP BY cost_type
        ORDER BY amount DESC
        """
        
        async with get_db_context() as session:
            result = await session.execute(text(sql))
            rows = result.fetchall()
            
            total = sum(row[1] for row in rows) or 1  # Avoid division by zero
            
            return [
                {
                    "cost_type": row[0],
                    "amount": float(row[1]),
                    "percentage": round(float(row[1]) / total * 100, 1),
                }
                for row in rows
            ]
    
    async def get_vehicle_fault_ranking(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get vehicles ranked by fault count"""
        sql = f"""
        SELECT 
            v.vehicle_code,
            v.vehicle_type,
            COUNT(f.id) as fault_count,
            COUNT(f.id) FILTER (WHERE f.status = 'open') as open_faults
        FROM vehicles v
        LEFT JOIN fault_records f ON v.id = f.vehicle_id
            AND f.fault_date >= NOW() - INTERVAL '90 days'
        GROUP BY v.id, v.vehicle_code, v.vehicle_type
        ORDER BY fault_count DESC
        LIMIT {limit}
        """
        
        async with get_db_context() as session:
            result = await session.execute(text(sql))
            rows = result.fetchall()
            
            return [
                {
                    "vehicle_code": row[0],
                    "vehicle_type": row[1],
                    "fault_count": row[2],
                    "open_faults": row[3],
                }
                for row in rows
            ]
    
    async def get_inventory_alerts(self) -> List[Dict[str, Any]]:
        """Get low stock inventory alerts"""
        sql = """
        SELECT 
            part_number,
            part_name,
            category,
            quantity_on_hand,
            minimum_quantity,
            (minimum_quantity - quantity_on_hand) as shortage
        FROM parts_inventory
        WHERE quantity_on_hand <= minimum_quantity
        ORDER BY shortage DESC
        """
        
        async with get_db_context() as session:
            result = await session.execute(text(sql))
            rows = result.fetchall()
            
            return [
                {
                    "part_number": row[0],
                    "part_name": row[1],
                    "category": row[2],
                    "quantity_on_hand": row[3],
                    "minimum_quantity": row[4],
                    "shortage": row[5],
                }
                for row in rows
            ]


def get_dashboard_service(session: Optional[AsyncSession] = None) -> DashboardService:
    """Get dashboard service instance"""
    return DashboardService(session)
