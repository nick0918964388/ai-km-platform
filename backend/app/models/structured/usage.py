"""
UsageRecord model - 使用歷程
"""

from datetime import datetime, date
from typing import Optional, TYPE_CHECKING
from uuid import uuid4, UUID as PyUUID

from sqlalchemy import String, Integer, Numeric, Date, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from .vehicle import Vehicle


class UsageRecord(Base):
    """使用歷程表"""
    
    __tablename__ = "usage_records"

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
    record_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="記錄日期"
    )
    mileage: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="里程數 (公里)"
    )
    operating_hours: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="運轉時數"
    )
    trips_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="班次數"
    )
    route: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="運行路線"
    )
    fuel_consumption: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="燃料消耗 (公升)"
    )
    electricity_consumption: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="電力消耗 (度)"
    )
    notes: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="備註"
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
    vehicle: Mapped["Vehicle"] = relationship(back_populates="usage_records")

    __table_args__ = (
        Index("idx_usage_vehicle_date", "vehicle_id", "record_date"),
    )

    def __repr__(self) -> str:
        return f"<UsageRecord(vehicle={self.vehicle_id}, date={self.record_date})>"
