"""Unit tests for maximo_tool_schemas (012-maximo-query-tools)."""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.models.maximo_tool_schemas import (
    DEBUG_ALLOWED_ROLES,
    DebugError,
    DebugInfo,
    DailyHitRateItem,
    FallbackReasonItem,
    MaximoQueryRequest,
    MaximoQueryResponse,
    MaximoToolAnalyticsResponse,
    MaximoToolCallsResponse,
    ToolAnalyticsItem,
    ToolCallLogItem,
    serialize_response,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_UUID = str(uuid.uuid4())


def _minimal_raw(*, debug=None) -> dict:
    """最小合法 raw dict，可供 serialize_response 使用。"""
    return {
        "query_id": _VALID_UUID,
        "route_path": "tool",
        "tool_name": "get_vehicle_info",
        "tool_input": {"asset_num": "A12345"},
        "rows": [],
        "row_count": 0,
        "chart_hint": None,
        "elapsed_ms": 100,
        "debug": debug,
        "user_facing_message": None,
    }


# ---------------------------------------------------------------------------
# MaximoQueryRequest
# ---------------------------------------------------------------------------


class TestMaximoQueryRequest:
    def test_valid_minimal(self):
        req = MaximoQueryRequest(query="A12345 故障?")
        assert req.query == "A12345 故障?"
        assert req.conversation_id is None
        assert req.mode is None

    def test_empty_string_rejected(self):
        with pytest.raises(ValidationError):
            MaximoQueryRequest(query="")

    def test_too_long_rejected(self):
        with pytest.raises(ValidationError):
            MaximoQueryRequest(query="x" * 2001)

    def test_max_length_accepted(self):
        req = MaximoQueryRequest(query="x" * 2000)
        assert len(req.query) == 2000

    def test_mode_accurate(self):
        req = MaximoQueryRequest(query="q", mode="accurate")
        assert req.mode == "accurate"

    def test_mode_fast(self):
        req = MaximoQueryRequest(query="q", mode="fast")
        assert req.mode == "fast"

    def test_mode_null(self):
        req = MaximoQueryRequest(query="q", mode=None)
        assert req.mode is None

    def test_invalid_mode_rejected(self):
        with pytest.raises(ValidationError):
            MaximoQueryRequest(query="q", mode="turbo")

    def test_extra_fields_allowed(self):
        """extra='allow' — 舊 client 額外欄位不報錯。"""
        req = MaximoQueryRequest(query="q", legacy_param="old_value")
        assert req.query == "q"

    def test_conversation_id_max_length(self):
        with pytest.raises(ValidationError):
            MaximoQueryRequest(query="q", conversation_id="x" * 65)

    def test_conversation_id_accepted(self):
        req = MaximoQueryRequest(query="q", conversation_id="x" * 64)
        assert len(req.conversation_id) == 64


# ---------------------------------------------------------------------------
# MaximoQueryResponse
# ---------------------------------------------------------------------------


class TestMaximoQueryResponse:
    def _base(self, **overrides) -> dict:
        base = {
            "query_id": _VALID_UUID,
            "route_path": "tool",
            "elapsed_ms": 500,
        }
        base.update(overrides)
        return base

    def test_valid_minimal(self):
        resp = MaximoQueryResponse(**self._base())
        assert resp.route_path == "tool"
        assert resp.rows == []
        assert resp.row_count == 0

    def test_route_path_fallback(self):
        resp = MaximoQueryResponse(**self._base(route_path="fallback"))
        assert resp.route_path == "fallback"

    def test_route_path_error(self):
        resp = MaximoQueryResponse(**self._base(route_path="error"))
        assert resp.route_path == "error"

    def test_invalid_route_path_rejected(self):
        with pytest.raises(ValidationError):
            MaximoQueryResponse(**self._base(route_path="unknown"))

    def test_query_id_must_be_uuid(self):
        with pytest.raises(ValidationError):
            MaximoQueryResponse(**self._base(query_id="not-a-uuid"))

    def test_query_id_valid_uuid_string(self):
        resp = MaximoQueryResponse(**self._base(query_id=_VALID_UUID))
        assert str(resp.query_id) == _VALID_UUID

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            MaximoQueryResponse(**self._base(unknown_field="bad"))

    def test_debug_none_by_default(self):
        resp = MaximoQueryResponse(**self._base())
        assert resp.debug is None

    def test_debug_populated(self):
        debug = DebugInfo(sql="SELECT 1", llm_stop_reason="tool_use")
        resp = MaximoQueryResponse(**self._base(debug=debug))
        assert resp.debug.sql == "SELECT 1"

    def test_rows_and_row_count(self):
        rows = [{"col": "val"}]
        resp = MaximoQueryResponse(**self._base(rows=rows, row_count=1))
        assert resp.row_count == 1
        assert resp.rows[0]["col"] == "val"


# ---------------------------------------------------------------------------
# DebugInfo / DebugError nested validation
# ---------------------------------------------------------------------------


class TestDebugInfo:
    def test_all_none_valid(self):
        d = DebugInfo()
        assert d.sql is None
        assert d.error is None

    def test_with_sql(self):
        d = DebugInfo(sql="SELECT * FROM foo")
        assert d.sql == "SELECT * FROM foo"

    def test_nested_error(self):
        err = DebugError(code="NOT_FOUND", message="查不到")
        d = DebugInfo(error=err)
        assert d.error.code == "NOT_FOUND"
        assert d.error.message == "查不到"

    def test_nested_error_from_dict(self):
        d = DebugInfo(error={"code": "TOOL_EXECUTION_ERROR", "message": "DB 錯"})
        assert d.error.code == "TOOL_EXECUTION_ERROR"

    def test_fallback_reason(self):
        d = DebugInfo(fallback_reason="no_tool_selected", llm_stop_reason="end_turn")
        assert d.fallback_reason == "no_tool_selected"
        assert d.llm_stop_reason == "end_turn"

    def test_user_facing_message(self):
        d = DebugInfo(user_facing_message="查不到這個車號的資料")
        assert d.user_facing_message == "查不到這個車號的資料"


# ---------------------------------------------------------------------------
# serialize_response — 核心行為測試（FR-010 debug 權限）
# ---------------------------------------------------------------------------


class TestSerializeResponse:
    def test_admin_gets_debug_key(self):
        debug = {"sql": "SELECT 1", "llm_stop_reason": "tool_use"}
        raw = _minimal_raw(debug=debug)
        data = serialize_response(raw, user_role="admin")
        assert "debug" in data
        assert data["debug"]["sql"] == "SELECT 1"

    def test_analyst_gets_debug_key(self):
        debug = {"sql": "SELECT 2", "fallback_reason": "no_tool_selected"}
        raw = _minimal_raw(debug=debug)
        data = serialize_response(raw, user_role="analyst")
        assert "debug" in data
        assert data["debug"]["fallback_reason"] == "no_tool_selected"

    def test_maint_manager_no_debug_key(self):
        raw = _minimal_raw(debug={"sql": "SECRET"})
        data = serialize_response(raw, user_role="maint_manager")
        assert "debug" not in data

    def test_maint_tech_no_debug_key(self):
        raw = _minimal_raw(debug={"sql": "SECRET"})
        data = serialize_response(raw, user_role="maint_tech")
        assert "debug" not in data

    def test_viewer_no_debug_key(self):
        raw = _minimal_raw(debug={"sql": "SECRET"})
        data = serialize_response(raw, user_role="viewer")
        assert "debug" not in data

    def test_admin_no_debug_in_raw_key_absent(self):
        """raw 無 debug 時，admin 也不應出現 debug=None key。"""
        raw = _minimal_raw(debug=None)
        data = serialize_response(raw, user_role="admin")
        assert "debug" not in data

    def test_analyst_no_debug_in_raw_key_absent(self):
        """raw 無 debug 時，analyst 也不應出現 debug=None key。"""
        raw = _minimal_raw(debug=None)
        data = serialize_response(raw, user_role="analyst")
        assert "debug" not in data

    def test_backward_compat_rows_always_present(self):
        """舊 client 只看 rows — 任何 role 都拿得到。"""
        raw = _minimal_raw()
        raw["rows"] = [{"ticket": "SR001"}]
        raw["row_count"] = 1
        for role in ("admin", "analyst", "maint_manager", "maint_tech", "viewer"):
            data = serialize_response(raw, user_role=role)
            assert "rows" in data
            assert data["row_count"] == 1

    def test_invalid_raw_raises_validation_error(self):
        """shape 不合法時應拋出 ValidationError。"""
        with pytest.raises(Exception):
            serialize_response({"route_path": "tool"}, user_role="admin")

    def test_debug_allowed_roles_constant(self):
        assert "admin" in DEBUG_ALLOWED_ROLES
        assert "analyst" in DEBUG_ALLOWED_ROLES
        assert "viewer" not in DEBUG_ALLOWED_ROLES
        assert "maint_tech" not in DEBUG_ALLOWED_ROLES
        assert "maint_manager" not in DEBUG_ALLOWED_ROLES


# ---------------------------------------------------------------------------
# Admin endpoint schemas — 基本驗證
# ---------------------------------------------------------------------------


class TestToolAnalyticsItem:
    def _item(self, **overrides) -> dict:
        base = {
            "tool_name": "get_vehicle_info",
            "total_calls": 150,
            "success_calls": 148,
            "failed_calls": 2,
            "avg_latency_ms": 620.0,
            "p50_latency_ms": 580.0,
            "p95_latency_ms": 1100.0,
        }
        base.update(overrides)
        return base

    def test_valid(self):
        item = ToolAnalyticsItem(**self._item())
        assert item.tool_name == "get_vehicle_info"
        assert item.avg_row_count is None
        assert item.last_used_at is None

    def test_with_optional_fields(self):
        item = ToolAnalyticsItem(**self._item(
            avg_row_count=1.0,
            last_used_at="2026-04-20T09:12:00+08:00",
        ))
        assert item.avg_row_count == 1.0
        assert item.last_used_at == "2026-04-20T09:12:00+08:00"

    def test_missing_required_field_raises(self):
        d = self._item()
        del d["tool_name"]
        with pytest.raises(ValidationError):
            ToolAnalyticsItem(**d)


class TestFallbackReasonItem:
    def test_valid(self):
        item = FallbackReasonItem(fallback_reason="no_tool_selected", count=720, pct=92.5)
        assert item.pct == 92.5

    def test_missing_field_raises(self):
        with pytest.raises(ValidationError):
            FallbackReasonItem(fallback_reason="x", count=1)


class TestDailyHitRateItem:
    def test_valid(self):
        item = DailyHitRateItem(day="2026-04-20", tool_hits=45, fallbacks=78, hit_rate_pct=36.59)
        assert item.day == "2026-04-20"


class TestMaximoToolAnalyticsResponse:
    def test_valid_empty_lists(self):
        resp = MaximoToolAnalyticsResponse(
            period_days=30,
            total_queries=1234,
            tool_hits=456,
            fallbacks=778,
            hit_rate_pct=36.95,
            tools=[],
            fallback_reasons=[],
            daily_hit_rate=[],
        )
        assert resp.period_days == 30
        assert resp.tools == []

    def test_with_nested_items(self):
        tool_item = ToolAnalyticsItem(
            tool_name="get_vehicle_info",
            total_calls=10,
            success_calls=10,
            failed_calls=0,
            avg_latency_ms=500.0,
            p50_latency_ms=480.0,
            p95_latency_ms=900.0,
        )
        resp = MaximoToolAnalyticsResponse(
            period_days=7,
            total_queries=100,
            tool_hits=40,
            fallbacks=60,
            hit_rate_pct=40.0,
            tools=[tool_item],
            fallback_reasons=[],
            daily_hit_rate=[],
        )
        assert len(resp.tools) == 1
        assert resp.tools[0].tool_name == "get_vehicle_info"


class TestToolCallLogItem:
    def _item(self, **overrides) -> dict:
        base = {
            "id": 9876,
            "query_id": _VALID_UUID,
            "user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "tool_name": "search_faults_by_vehicle",
            "params": {"asset_num": "A12345"},
            "route_path": "tool",
            "latency_ms": 850,
            "success": True,
            "row_count": 3,
            "fallback_reason": None,
            "error_message": None,
            "created_at": "2026-04-20T09:12:00+08:00",
        }
        base.update(overrides)
        return base

    def test_valid(self):
        item = ToolCallLogItem(**self._item())
        assert item.success is True
        assert item.route_path == "tool"

    def test_invalid_route_path(self):
        with pytest.raises(ValidationError):
            ToolCallLogItem(**self._item(route_path="invalid"))

    def test_query_id_must_be_uuid(self):
        with pytest.raises(ValidationError):
            ToolCallLogItem(**self._item(query_id="not-uuid"))

    def test_nullable_fields(self):
        item = ToolCallLogItem(**self._item(user_id=None, tool_name=None, row_count=None))
        assert item.user_id is None
        assert item.tool_name is None
        assert item.row_count is None


class TestMaximoToolCallsResponse:
    def test_valid_empty(self):
        resp = MaximoToolCallsResponse(total=0, limit=50, offset=0, items=[])
        assert resp.total == 0
        assert resp.items == []

    def test_missing_required_raises(self):
        with pytest.raises(ValidationError):
            MaximoToolCallsResponse(total=0, limit=50, items=[])
