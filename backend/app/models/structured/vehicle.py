"""
Vehicle model - 車輛基本資料
"""

from datetime import datetime, date
from typing import Optional, TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import String, Integer, Date, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from .fault_record import FaultRecord
    from .maintenance import MaintenanceRecord
    from .usage import UsageRecord
    from .cost import CostRecord


class Vehicle(Base):
    """車輛基本資料表"""
    
    __tablename__ = "vehicles"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    vehicle_code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
        comment="車輛編號 (如 EMU801)"
    )
    vehicle_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="車型 (如 EMU800 系列)"
    )
    manufacturer: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="製造商"
    )
    manufacture_year: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="製造年份"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="狀態: active/maintenance/retired"
    )
    depot: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="所屬機務段"
    )
    last_maintenance_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        comment="最後保養日期"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationships
    fault_records: Mapped[list["FaultRecord"]] = relationship(
        back_populates="vehicle",
        lazy="selectin"
    )
    maintenance_records: Mapped[list["MaintenanceRecord"]] = relationship(
        back_populates="vehicle",
        lazy="selectin"
    )
    usage_records: Mapped[list["UsageRecord"]] = relationship(
        back_populates="vehicle",
        lazy="selectin"
    )
    cost_records: Mapped[list["CostRecord"]] = relationship(
        back_populates="vehicle",
        lazy="selectin"
    )

    __table_args__ = (
        Index("idx_vehicles_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<Vehicle(code={self.vehicle_code}, type={self.vehicle_type})>"
