"""Document model for persistent document metadata storage."""

from datetime import datetime
from sqlalchemy import Column, String, BigInteger, Integer, DateTime
from sqlalchemy.sql import func

from app.db import Base


class Document(Base):
    """SQLAlchemy model for document metadata."""
    
    __tablename__ = "documents"
    
    id = Column(String(36), primary_key=True)
    filename = Column(String(255), nullable=False)
    doc_type = Column(String(20), nullable=False)
    file_size = Column(BigInteger, nullable=False, default=0)
    chunk_count = Column(Integer, nullable=False, default=0)
    uploaded_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    
    def to_dict(self) -> dict:
        """Convert model to dictionary."""
        return {
            "id": self.id,
            "filename": self.filename,
            "doc_type": self.doc_type,
            "file_size": self.file_size,
            "chunk_count": self.chunk_count,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
