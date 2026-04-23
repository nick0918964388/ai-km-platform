"""Pydantic models for the Skills system."""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None
    triggers: list[str] = Field(default_factory=list)
    sql_template: Optional[str] = None
    params_schema: dict[str, Any] = Field(default_factory=dict)
    security: dict[str, Any] = Field(default_factory=dict)
    stats: dict[str, Any] = Field(default_factory=dict)
    active: bool = False


class SkillUpdate(BaseModel):
    description: Optional[str] = None
    triggers: Optional[list[str]] = None
    sql_template: Optional[str] = None
    params_schema: Optional[dict[str, Any]] = None
    security: Optional[dict[str, Any]] = None
    stats: Optional[dict[str, Any]] = None
    active: Optional[bool] = None
    reason: Optional[str] = None
    changed_by: Optional[str] = None


class SkillRead(BaseModel):
    id: UUID
    name: str
    version: int
    is_current: bool
    description: Optional[str]
    triggers: list[str]
    sql_template: Optional[str]
    params_schema: dict[str, Any]
    security: dict[str, Any]
    stats: dict[str, Any]
    active: bool

    model_config = {"from_attributes": True}


class SkillMatchResult(BaseModel):
    skill_id: str
    name: str
    version: int
    score: float
    sql_template: Optional[str]
    params_schema: dict[str, Any]
    triggers: list[str]


class FeedbackCreate(BaseModel):
    skill_id: UUID
    skill_version: int
    message_id: Optional[str] = None
    rating: str = Field(..., pattern="^(up|down)$")
    comment: Optional[str] = None
    user_id: Optional[str] = None
