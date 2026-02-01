"""
Parts models - 零件相關
Including: PartsUsed (用料歷程) and PartsInventory (零件庫存)
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import uuid4, UUID as PyUUID

from sqlalchemy import String, Integer, Numeric, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from .maintenance import MaintenanceRecord


class PartsInventory(Base):
    """零件庫存表"""
    
    __tablename__ = "parts_inventory"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    part_number: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="零件編號"
    )
    part_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="零件名稱"
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="零件類別"
    )
    quantity_on_hand: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="庫存數量"
    )
    minimum_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="最低庫存量"
    )
    unit_price: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="單價"
    )
    supplier: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment="供應商"
    )
    location: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="存放位置"
    )
    last_restock_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="最後補貨日期"
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
    parts_used: Mapped[list["PartsUsed"]] = relationship(
        back_populates="part",
        lazy="selectin"
    )

    __table_args__ = (
        Index("idx_parts_low_stock", "quantity_on_hand", "minimum_quantity"),
    )

    @property
    def is_low_stock(self) -> bool:
        """Check if stock is below minimum"""
        return self.quantity_on_hand <= self.minimum_quantity

    def __repr__(self) -> str:
        return f"<PartsInventory(number={self.part_number}, qty={self.quantity_on_hand})>"


class PartsUsed(Base):
    """用料歷程表"""
    
    __tablename__ = "parts_used"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    maintenance_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maintenance_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    part_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("parts_inventory.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    part_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="零件編號 (冗餘欄位)"
    )
    part_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="零件名稱 (冗餘欄位)"
    )
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="使用數量"
    )
    unit_cost: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="單價"
    )
    total_cost: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="總價"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    # Relationships
    maintenance_record: Mapped["MaintenanceRecord"] = relationship(back_populates="parts_used")
    part: Mapped[Optional["PartsInventory"]] = relationship(back_populates="parts_used")

    def __repr__(self) -> str:
        return f"<PartsUsed(part={self.part_number}, qty={self.quantity})>"
