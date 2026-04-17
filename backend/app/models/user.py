"""User model for user account and profile management."""

from datetime import datetime
from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func

from app.db import Base


class User(Base):
    """SQLAlchemy model for user accounts and profiles."""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=True)
    display_name = Column(String(50), nullable=False, server_default='')
    avatar_url = Column(String(255), nullable=True)
    account_level = Column(String(20), nullable=False, server_default='free')
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    last_login = Column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        """Convert model to dictionary."""
        return {
            "id": self.id,
            "email": self.email,
            "display_name": self.display_name,
            "avatar_url": self.avatar_url,
            "account_level": self.account_level,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }
