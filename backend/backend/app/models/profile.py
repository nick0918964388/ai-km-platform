"""Profile-related Pydantic models for API validation."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


class ProfileUpdateRequest(BaseModel):
    """Request model for updating user profile."""

    display_name: str = Field(..., min_length=2, max_length=50, description="User's display name")

    @field_validator('display_name')
    @classmethod
    def validate_display_name(cls, v: str) -> str:
        """Validate display name is not empty after stripping whitespace."""
        stripped = v.strip()
        if not stripped:
            raise ValueError('Display name cannot be empty or whitespace only')
        if len(stripped) < 2:
            raise ValueError('Display name must be at least 2 characters')
        if len(stripped) > 50:
            raise ValueError('Display name cannot exceed 50 characters')
        return stripped


class UserProfile(BaseModel):
    """User profile response model."""

    id: str = Field(..., description="User unique identifier")
    email: str = Field(..., description="User email address")
    display_name: str = Field(..., description="User's display name")
    avatar_url: Optional[str] = Field(None, description="Relative URL to avatar image or null")
    account_level: str = Field(..., description="User subscription tier (free/pro/enterprise)")
    created_at: datetime = Field(..., description="Account creation timestamp")
    updated_at: datetime = Field(..., description="Last profile update timestamp")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "a3f2c9d4-5e6f-4a5b-8c9d-0e1f2a3b4c5d",
                "email": "user@example.com",
                "display_name": "John Doe",
                "avatar_url": "/api/avatars/user123_20260203.jpg",
                "account_level": "pro",
                "created_at": "2025-01-15T10:30:00Z",
                "updated_at": "2026-02-03T14:20:00Z",
            }
        }


class AvatarUploadResponse(BaseModel):
    """Response model for avatar upload."""

    avatar_url: str = Field(..., description="Relative URL to uploaded avatar image")
    message: str = Field(..., description="Success message")

    class Config:
        json_schema_extra = {
            "example": {
                "avatar_url": "/api/avatars/user123_20260203.jpg",
                "message": "Avatar uploaded successfully"
            }
        }
