from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class UserContext(BaseModel):
    """Row filter / 權限注入用。從既有 auth middleware 組裝。"""

    user_id: str  # VARCHAR(36)
    role: Literal["admin", "maint_manager", "maint_tech", "analyst", "viewer"]
    section: str | None = None
    workshop: str | None = None
    email: str | None = None


class ToolDefinition(BaseModel):
    """供 Anthropic tool_use API 使用的 tool metadata。"""

    name: str  # snake_case, e.g. "get_vehicle_info"
    description: str  # 給 LLM 讀，述明用途
    input_schema: dict[str, Any]  # JSON Schema dict


class ToolResult(BaseModel):
    """所有 Tool.execute() 的統一回傳型別。"""

    model_config = ConfigDict(frozen=False)

    success: bool
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    chart_hint: dict[str, Any] | None = None
    error: str | None = None
    error_code: str | None = None  # NOT_FOUND / TOOL_EXECUTION_ERROR / ...
    elapsed_ms: int = 0


class RouterDecision(BaseModel):
    route_path: Literal["tool", "fallback", "error"]
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    fallback_reason: str | None = None
    llm_stop_reason: str | None = None
    raw_response: dict[str, Any] | None = None


class Tool(ABC):
    """所有 Maximo 查詢 tool 的抽象基類。"""

    definition: ToolDefinition  # class-level attribute

    @abstractmethod
    async def execute(self, params: dict, user_ctx: UserContext) -> ToolResult:
        ...


_FORBIDDEN_KEYS = frozenset({"$defs", "$ref", "oneOf", "allOf", "anyOf"})


def validate_tool_schema(schema: dict) -> None:
    """
    強制 Anthropic tool_use 相容的 flat schema（只檢查 dict keys，不看 values）：
    - 任意深度禁出現 $defs / $ref / oneOf / allOf / anyOf 作為 key
    - description 等 value 含此文字不受影響
    Raise ValueError 若違規。
    """
    def _walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in _FORBIDDEN_KEYS:
                    raise ValueError(
                        f"Tool input_schema contains forbidden key '{key}'. "
                        "Use flat schema only (primitive + Literal enum)."
                    )
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(schema)
