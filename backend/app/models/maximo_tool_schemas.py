"""
API request/response schemas for Maximo query endpoint (012-maximo-query-tools).

Request reuses existing POST /api/maximo/nl2sql endpoint but adds:
- Response now has route_path, tool_name, tool_input, chart_hint
- debug field is stripped for non-admin/analyst users (FR-010)
"""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# 可看 debug 的 role（FR-010）
DEBUG_ALLOWED_ROLES = frozenset({"admin", "analyst"})


class MaximoQueryRequest(BaseModel):
    """POST /api/maximo/nl2sql body."""
    model_config = ConfigDict(extra="allow")  # 保留既有 client 額外欄位相容性

    query: str = Field(..., min_length=1, max_length=2000, description="使用者問題原文")
    conversation_id: str | None = Field(None, max_length=64, description="對話 ID（延續既有機制）")
    mode: Literal["accurate", "fast"] | None = Field(None, description="查詢模式（NL→SQL 既有參數）")


class DebugError(BaseModel):
    code: str
    message: str


class DebugInfo(BaseModel):
    """debug 欄位：admin/analyst only。其他 role 這個欄位不會出現在 response。"""
    sql: str | None = None
    llm_stop_reason: str | None = None
    fallback_reason: str | None = None
    error: DebugError | None = None
    user_facing_message: str | None = None


class MaximoQueryResponse(BaseModel):
    """
    POST /api/maximo/nl2sql response.

    Backward compat: 舊 client 取 rows / row_count / elapsed_ms 仍正常。
    新欄位: route_path / tool_name / tool_input / chart_hint / debug（optional）
    """
    model_config = ConfigDict(extra="forbid")

    query_id: UUID
    route_path: Literal["tool", "fallback", "error"]
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    chart_hint: dict[str, Any] | None = None
    elapsed_ms: int
    # debug 只在 admin/analyst 的 response 出現；序列化時由 backend 決定是否塞入
    debug: DebugInfo | None = None
    # user_facing_message 給錯誤情境的人讀訊息
    user_facing_message: str | None = None


def serialize_response(
    raw: dict,
    user_role: Literal["admin", "maint_manager", "maint_tech", "analyst", "viewer"],
) -> dict:
    """
    把 router 回傳的 dict 序列化成 response，根據 role 決定是否保留 debug 欄位。

    Args:
        raw: router.route() 回傳的 dict
        user_role: 從 UserContext 來的 role

    Returns:
        dict suitable for JSON response.
    """
    # Pydantic validation（確保 shape 正確）
    response = MaximoQueryResponse.model_validate(raw)
    # 統一 model_dump，產 dict
    data = response.model_dump(mode="json", exclude_none=False)

    # 非 admin/analyst：移除 debug 欄位（FR-010 權限規則）
    if user_role not in DEBUG_ALLOWED_ROLES:
        data.pop("debug", None)
    elif data.get("debug") is None:
        # admin/analyst 但 debug 本來就是 None：移除 key，避免洩漏 null 感知
        data.pop("debug", None)

    return data


# Admin-only endpoints schemas ----------------------------------------------

class ToolAnalyticsItem(BaseModel):
    tool_name: str
    total_calls: int
    success_calls: int
    failed_calls: int
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    avg_row_count: float | None = None
    last_used_at: str | None = None  # ISO timestamp


class FallbackReasonItem(BaseModel):
    fallback_reason: str
    count: int
    pct: float


class DailyHitRateItem(BaseModel):
    day: str  # ISO date
    tool_hits: int
    fallbacks: int
    hit_rate_pct: float


class MaximoToolAnalyticsResponse(BaseModel):
    """GET /api/maximo/tools/analytics"""
    period_days: int
    total_queries: int
    tool_hits: int
    fallbacks: int
    hit_rate_pct: float
    tools: list[ToolAnalyticsItem]
    fallback_reasons: list[FallbackReasonItem]
    daily_hit_rate: list[DailyHitRateItem]


class ToolCallLogItem(BaseModel):
    id: int
    query_id: UUID
    user_id: str | None
    tool_name: str | None
    params: dict[str, Any]
    route_path: Literal["tool", "fallback", "error"]
    latency_ms: int
    success: bool
    row_count: int | None
    fallback_reason: str | None
    error_message: str | None
    created_at: str  # ISO timestamp


class MaximoToolCallsResponse(BaseModel):
    """GET /api/maximo/tools/calls"""
    total: int
    limit: int
    offset: int
    items: list[ToolCallLogItem]
