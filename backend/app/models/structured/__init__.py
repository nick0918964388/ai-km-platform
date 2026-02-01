"""
Structured data models for vehicle maintenance system.
"""

from .vehicle import Vehicle
from .fault_record import FaultRecord
from .maintenance import MaintenanceRecord
from .usage import UsageRecord
from .parts import PartsUsed, PartsInventory
from .cost import CostRecord

__all__ = [
    "Vehicle",
    "FaultRecord",
    "MaintenanceRecord",
    "UsageRecord",
    "PartsUsed",
    "PartsInventory",
    "CostRecord",
]
