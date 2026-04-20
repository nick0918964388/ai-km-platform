import pytest
from pydantic import ValidationError

from app.services.maximo_tools.base import (
    RouterDecision,
    Tool,
    ToolDefinition,
    ToolResult,
    UserContext,
    validate_tool_schema,
)


# ---------------------------------------------------------------------------
# UserContext
# ---------------------------------------------------------------------------


class TestUserContext:
    def test_valid_admin_role(self):
        ctx = UserContext(user_id="u-001", role="admin")
        assert ctx.role == "admin"
        assert ctx.user_id == "u-001"

    def test_valid_all_roles(self):
        valid_roles = ["admin", "maint_manager", "maint_tech", "analyst", "viewer"]
        for role in valid_roles:
            ctx = UserContext(user_id="u-001", role=role)
            assert ctx.role == role

    def test_invalid_role_raises_validation_error(self):
        with pytest.raises(ValidationError):
            UserContext(user_id="u-001", role="superuser")

    def test_nullable_fields_default_to_none(self):
        ctx = UserContext(user_id="u-001", role="viewer")
        assert ctx.section is None
        assert ctx.workshop is None
        assert ctx.email is None

    def test_nullable_fields_accept_values(self):
        ctx = UserContext(
            user_id="u-001",
            role="maint_tech",
            section="S01",
            workshop="W02",
            email="tech@example.com",
        )
        assert ctx.section == "S01"
        assert ctx.workshop == "W02"
        assert ctx.email == "tech@example.com"


# ---------------------------------------------------------------------------
# ToolDefinition
# ---------------------------------------------------------------------------


class TestToolDefinition:
    def test_basic_construction(self):
        defn = ToolDefinition(
            name="get_vehicle_info",
            description="查詢單一車輛的基本資料",
            input_schema={"type": "object", "properties": {"asset_num": {"type": "string"}}},
        )
        assert defn.name == "get_vehicle_info"
        assert defn.description == "查詢單一車輛的基本資料"
        assert "properties" in defn.input_schema

    def test_empty_schema_dict_accepted(self):
        defn = ToolDefinition(
            name="list_all",
            description="列出全部",
            input_schema={"type": "object", "properties": {}},
        )
        assert defn.input_schema["type"] == "object"


# ---------------------------------------------------------------------------
# ToolResult
# ---------------------------------------------------------------------------


class TestToolResult:
    def test_default_values(self):
        result = ToolResult(success=True)
        assert result.rows == []
        assert result.row_count == 0
        assert result.chart_hint is None
        assert result.error is None
        assert result.error_code is None
        assert result.elapsed_ms == 0

    def test_success_with_rows(self):
        rows = [{"asset_num": "A12345", "status": "運行中"}]
        result = ToolResult(success=True, rows=rows, row_count=1, elapsed_ms=123)
        assert result.row_count == 1
        assert result.rows[0]["asset_num"] == "A12345"
        assert result.elapsed_ms == 123

    def test_failure_with_error_code(self):
        result = ToolResult(
            success=False,
            error="資料庫查詢失敗",
            error_code="TOOL_EXECUTION_ERROR",
        )
        assert not result.success
        assert result.error_code == "TOOL_EXECUTION_ERROR"

    def test_not_frozen_allows_mutation(self):
        result = ToolResult(success=True)
        result.elapsed_ms = 500
        assert result.elapsed_ms == 500


# ---------------------------------------------------------------------------
# Tool ABC
# ---------------------------------------------------------------------------


class TestToolABC:
    def test_cannot_instantiate_abstract_class(self):
        with pytest.raises(TypeError):
            Tool()  # type: ignore[abstract]

    def test_concrete_subclass_without_execute_raises(self):
        class IncompleteToolNoExecute(Tool):
            definition = ToolDefinition(
                name="incomplete",
                description="未完成",
                input_schema={},
            )

        with pytest.raises(TypeError):
            IncompleteToolNoExecute()  # type: ignore[abstract]

    def test_concrete_subclass_with_execute_instantiates(self):
        class ConcreteTool(Tool):
            definition = ToolDefinition(
                name="concrete_tool",
                description="具體 tool",
                input_schema={"type": "object", "properties": {}},
            )

            async def execute(self, params: dict, user_ctx: UserContext) -> ToolResult:
                return ToolResult(success=True, row_count=0)

        tool = ConcreteTool()
        assert tool.definition.name == "concrete_tool"

    @pytest.mark.asyncio
    async def test_execute_returns_tool_result(self):
        class EchoTool(Tool):
            definition = ToolDefinition(
                name="echo_tool",
                description="回傳固定結果",
                input_schema={"type": "object", "properties": {}},
            )

            async def execute(self, params: dict, user_ctx: UserContext) -> ToolResult:
                return ToolResult(success=True, rows=[params], row_count=1)

        ctx = UserContext(user_id="u-001", role="admin")
        tool = EchoTool()
        result = await tool.execute({"key": "val"}, ctx)
        assert result.success
        assert result.rows == [{"key": "val"}]


# ---------------------------------------------------------------------------
# validate_tool_schema
# ---------------------------------------------------------------------------


class TestValidateToolSchema:
    def test_flat_schema_passes(self):
        schema = {
            "type": "object",
            "properties": {
                "asset_num": {"type": "string", "description": "車輛資產編號"},
                "date_range": {
                    "type": "string",
                    "enum": ["last_7d", "last_30d", "last_90d"],
                },
            },
            "required": ["asset_num"],
        }
        validate_tool_schema(schema)  # should not raise

    def test_schema_with_defs_raises(self):
        schema = {
            "type": "object",
            "$defs": {"MyType": {"type": "string"}},
            "properties": {"field": {"$ref": "#/$defs/MyType"}},
        }
        with pytest.raises(ValueError, match=r"\$defs"):
            validate_tool_schema(schema)

    def test_schema_with_ref_raises(self):
        schema = {
            "type": "object",
            "properties": {"field": {"$ref": "#/definitions/SomeType"}},
        }
        with pytest.raises(ValueError, match=r"\$ref"):
            validate_tool_schema(schema)

    def test_schema_with_one_of_raises(self):
        schema = {
            "type": "object",
            "properties": {
                "date": {"oneOf": [{"type": "string"}, {"type": "null"}]},
            },
        }
        with pytest.raises(ValueError, match="oneOf"):
            validate_tool_schema(schema)

    def test_schema_with_all_of_raises(self):
        schema = {
            "allOf": [{"type": "object"}, {"properties": {"x": {"type": "string"}}}]
        }
        with pytest.raises(ValueError, match="allOf"):
            validate_tool_schema(schema)

    def test_schema_with_any_of_raises(self):
        schema = {
            "type": "object",
            "properties": {
                "value": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
            },
        }
        with pytest.raises(ValueError, match="anyOf"):
            validate_tool_schema(schema)

    def test_schema_with_enum_and_default_passes(self):
        schema = {
            "type": "object",
            "properties": {
                "level": {
                    "type": "string",
                    "enum": ["A", "B", "C"],
                    "default": "A",
                    "description": "故障等級",
                },
            },
        }
        validate_tool_schema(schema)  # should not raise

    def test_description_value_containing_forbidden_word_passes(self):
        """Value strings like '$ref' in description must NOT trigger validation error.
        Only dict keys are checked — this guards against the old str(schema) false-positive."""
        schema = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Use $ref or oneOf patterns in your query string",
                },
            },
            "required": ["query"],
        }
        validate_tool_schema(schema)  # must not raise — value, not key
