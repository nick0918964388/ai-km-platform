"""
FaultRecord model - 故障歷程
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import uuid4, UUID as PyUUID

from sqlalchemy import String, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from .vehicle import Vehicle


class FaultRecord(Base):
    """故障歷程表"""
    
    __tablename__ = "fault_records"

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
    fault_code: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="故障編號"
    )
    fault_date: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
        comment="故障發生時間"
    )
    fault_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="故障類型 (如 轉向架、煞車、電氣)"
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="嚴重程度: critical/major/minor"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="open",
        comment="處理狀態: open/in_progress/resolved"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="故障描述"
    )
    resolution: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="處理方式"
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="解決時間"
    )
    reported_by: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="回報人員"
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
    vehicle: Mapped["Vehicle"] = relationship(back_populates="fault_records")

    __table_args__ = (
        Index("idx_fault_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<FaultRecord(code={self.fault_code}, type={self.fault_type})>"
