"""
CostRecord model - 維修成本
"""

from datetime import datetime, date
from typing import Optional, TYPE_CHECKING
from uuid import uuid4, UUID as PyUUID

from sqlalchemy import String, Numeric, Date, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from .vehicle import Vehicle


class CostRecord(Base):
    """維修成本表"""
    
    __tablename__ = "cost_records"

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
    cost_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="成本類型: labor/parts/external/other"
    )
    category: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="成本分類"
    )
    description: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="費用說明"
    )
    amount: Mapped[float] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        comment="金額"
    )
    currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="TWD",
        comment="幣別"
    )
    reference_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="參考單號 (如檢修單號)"
    )
    vendor: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment="廠商"
    )
    invoice_number: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="發票號碼"
    )
    approved_by: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="核准人"
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
    vehicle: Mapped["Vehicle"] = relationship(back_populates="cost_records")

    __table_args__ = (
        Index("idx_cost_type_date", "cost_type", "record_date"),
        Index("idx_cost_vehicle_date", "vehicle_id", "record_date"),
    )

    def __repr__(self) -> str:
        return f"<CostRecord(type={self.cost_type}, amount={self.amount})>"
