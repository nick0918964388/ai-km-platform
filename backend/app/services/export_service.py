"""
Export Service - Generate CSV/Excel exports from query results.
"""

import csv
import io
from typing import List, Dict, Any, Optional
from datetime import datetime


class ExportService:
    """Service for exporting data to various formats"""
    
    def to_csv(
        self,
        data: List[Dict[str, Any]],
        columns: Optional[List[str]] = None,
        include_header: bool = True
    ) -> str:
        """
        Export data to CSV string.
        
        Args:
            data: List of row dictionaries
            columns: Column order (uses dict keys if not specified)
            include_header: Whether to include header row
            
        Returns:
            CSV string
        """
        if not data:
            return ""
        
        # Determine columns
        if columns is None:
            columns = list(data[0].keys())
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        if include_header:
            writer.writerow(columns)
        
        # Write data rows
        for row in data:
            writer.writerow([self._format_value(row.get(col)) for col in columns])
        
        return output.getvalue()
    
    def to_csv_bytes(
        self,
        data: List[Dict[str, Any]],
        columns: Optional[List[str]] = None,
        include_header: bool = True,
        encoding: str = "utf-8-sig"  # BOM for Excel compatibility
    ) -> bytes:
        """Export data to CSV bytes (for download)"""
        csv_str = self.to_csv(data, columns, include_header)
        return csv_str.encode(encoding)
    
    def _format_value(self, value: Any) -> str:
        """Format value for CSV export"""
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(value, bool):
            return "是" if value else "否"
        return str(value)
    
    def generate_filename(
        self,
        prefix: str,
        extension: str = "csv"
    ) -> str:
        """Generate timestamped filename"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{prefix}_{timestamp}.{extension}"


# Column label mapping for exports
EXPORT_LABELS = {
    "id": "ID",
    "vehicle_code": "車輛編號",
    "vehicle_type": "車型",
    "manufacturer": "製造商",
    "manufacture_year": "製造年份",
    "status": "狀態",
    "depot": "機務段",
    "last_maintenance_date": "最後保養日期",
    "fault_code": "故障編號",
    "fault_date": "故障日期",
    "fault_type": "故障類型",
    "severity": "嚴重程度",
    "description": "描述",
    "resolution": "處理方式",
    "resolved_at": "解決時間",
    "reported_by": "回報人",
    "maintenance_code": "檢修編號",
    "maintenance_type": "檢修類型",
    "maintenance_date": "檢修日期",
    "completed_date": "完成日期",
    "technician": "技師",
    "supervisor": "督導",
    "labor_hours": "工時",
    "labor_cost": "人工費用",
    "amount": "金額",
    "cost_type": "成本類型",
    "category": "分類",
    "record_date": "記錄日期",
    "part_number": "零件編號",
    "part_name": "零件名稱",
    "quantity_on_hand": "庫存量",
    "minimum_quantity": "最低庫存",
    "unit_price": "單價",
    "supplier": "供應商",
    "is_low_stock": "庫存警示",
    "open_faults": "未處理故障",
}


def get_export_service() -> ExportService:
    """Get export service instance"""
    return ExportService()
