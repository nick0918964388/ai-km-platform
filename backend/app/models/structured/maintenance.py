"""
MaintenanceRecord model - 檢修歷程
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import uuid4, UUID as PyUUID

from sqlalchemy import String, Text, DateTime, Numeric, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from .vehicle import Vehicle
    from .parts import PartsUsed


class MaintenanceRecord(Base):
    """檢修歷程表"""
    
    __tablename__ = "maintenance_records"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    vehicle_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    maintenance_code: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="檢修編號"
    )
    maintenance_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="檢修類型: scheduled/unscheduled/emergency"
    )
    maintenance_date: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
        comment="檢修日期"
    )
    completed_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="完成日期"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="狀態: pending/in_progress/completed"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="檢修描述"
    )
    work_performed: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="執行工作內容"
    )
    labor_hours: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="工時"
    )
    labor_cost: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="人工費用"
    )
    technician: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="維修技師"
    )
    supervisor: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="督導"
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
    vehicle: Mapped["Vehicle"] = relationship(back_populates="maintenance_records")
    parts_used: Mapped[list["PartsUsed"]] = relationship(
        back_populates="maintenance_record",
        lazy="selectin"
    )

    __table_args__ = (
        Index("idx_maintenance_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<MaintenanceRecord(code={self.maintenance_code}, type={self.maintenance_type})>"
