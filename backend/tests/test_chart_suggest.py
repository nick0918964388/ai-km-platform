"""Unit tests for _suggest_chart intent-validation layer (P1 task).

All tests are pure unit tests — no DB, no async required.
MaximoNL2SQL._suggest_chart is called via an unbound-style call by passing
a minimal stub instance (db=None is fine since _suggest_chart never touches self.db).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from app.services.maximo_nl2sql import MaximoNL2SQL, detect_chart_intent


def make_svc() -> MaximoNL2SQL:
    """Return a MaximoNL2SQL instance without a real DB session."""
    svc = MaximoNL2SQL.__new__(MaximoNL2SQL)
    svc.db = None
    return svc


# ── detect_chart_intent helper ───────────────────────────────────────────────

def test_detect_chart_intent_aggregation():
    r = detect_chart_intent("各車型數量分布")
    assert r["expects_aggregation"] is True
    assert r["suggested_viz"] == "pie"


def test_detect_chart_intent_trend():
    r = detect_chart_intent("月份趨勢變化")
    assert r["expects_aggregation"] is True
    assert r["suggested_viz"] == "line"


def test_detect_chart_intent_no_agg():
    r = detect_chart_intent("EMU900 工單列表")
    assert r["expects_aggregation"] is False
    assert r["suggested_viz"] is None


# ── Acceptance case 1 ────────────────────────────────────────────────────────
# Q has aggregation keyword, SQL has no GROUP BY → warning about GROUP BY

def test_case1_agg_keyword_no_group_by():
    svc = make_svc()
    result = {
        "columns": ["assetnum", "vehicle_type"],
        "rows": [{"assetnum": "A001", "vehicle_type": "EMU900"}] * 10,
        "row_count": 10,
    }
    sql = "SELECT * FROM mxasset LIMIT 10"
    out = svc._suggest_chart("各車型數量分布", sql, result)
    assert out is not None
    assert out["type"] == "none"
    assert "GROUP BY" in out["warning"]


# ── Acceptance case 2 ────────────────────────────────────────────────────────
# Q has no aggregation keyword, SQL has no GROUP BY → None (no suggestion)

def test_case2_plain_query_no_agg_keyword():
    svc = make_svc()
    result = {
        "columns": ["wonum"],
        "rows": [{"wonum": "WO001"}] * 5,
        "row_count": 5,
    }
    sql = "SELECT wonum FROM mxwo WHERE assetnum LIKE 'EMU900%'"
    out = svc._suggest_chart("EMU900 工單", sql, result)
    assert out is None


# ── Acceptance case 3 ────────────────────────────────────────────────────────
# Q has agg keyword, SQL has GROUP BY, rows=12 → bar (not pie, >10)

def test_case3_group_by_12_rows_gives_bar():
    svc = make_svc()
    rows = [{"status": f"S{i}", "cnt": i + 1} for i in range(12)]
    result = {
        "columns": ["status", "cnt"],
        "rows": rows,
        "row_count": 12,
    }
    sql = "SELECT status, COUNT(*) AS cnt FROM mxwo GROUP BY status"
    out = svc._suggest_chart("狀態分布", sql, result)
    assert out is not None
    assert out["type"] == "bar"


# ── Acceptance case 4 ────────────────────────────────────────────────────────
# Q has agg keyword, SQL has GROUP BY, rows=5 but one value is NULL → warning NULL

def test_case4_pie_null_value_blocked():
    svc = make_svc()
    rows = [
        {"status": "WAPPR", "cnt": 10},
        {"status": "APPR", "cnt": 5},
        {"status": "WSCH", "cnt": 3},
        {"status": "INPRG", "cnt": 2},
        {"status": "COMP", "cnt": None},  # NULL here
    ]
    result = {
        "columns": ["status", "cnt"],
        "rows": rows,
        "row_count": 5,
    }
    sql = "SELECT status, COUNT(*) AS cnt FROM mxwo GROUP BY status"
    out = svc._suggest_chart("狀態分布", sql, result)
    assert out is not None
    assert out["type"] == "none"
    assert "NULL" in out["warning"]


# ── Acceptance case 5 ────────────────────────────────────────────────────────
# Q has trend keyword, SQL has date col, but row x values are plain "2026" (not ISO) → none/warning

def test_case5_trend_non_iso_date_blocked():
    svc = make_svc()
    rows = [{"reportdate": "2026", "cnt": 5}] * 3
    result = {
        "columns": ["reportdate", "cnt"],
        "rows": rows,
        "row_count": 3,
    }
    # Has ORDER BY and date col → Rule 2 path
    sql = "SELECT reportdate, COUNT(*) AS cnt FROM mxwo GROUP BY reportdate ORDER BY reportdate"
    out = svc._suggest_chart("月份趨勢", sql, result)
    # Should be degraded to bar (row_count <=30) or none — not line
    assert out is not None
    assert out["type"] != "line", f"Expected not line, got {out}"


# ── Extra: pie happy path ────────────────────────────────────────────────────

def test_pie_happy_path_5_rows():
    svc = make_svc()
    rows = [{"status": f"S{i}", "cnt": i + 1} for i in range(5)]
    result = {
        "columns": ["status", "cnt"],
        "rows": rows,
        "row_count": 5,
    }
    sql = "SELECT status, COUNT(*) AS cnt FROM mxwo GROUP BY status"
    out = svc._suggest_chart("狀態分布", sql, result)
    assert out is not None
    assert out["type"] == "pie"
    assert out["name_key"] == "status"
    assert out["value_key"] == "cnt"


# ── Extra: line happy path ───────────────────────────────────────────────────

def test_line_happy_path_iso_dates():
    svc = make_svc()
    # Rule 2: date col + numeric + ORDER BY (no GROUP BY / COUNT → Rule 1 skipped)
    rows = [{"reportdate": f"2026-0{i+1}-01", "total_cost": float(i * 100)} for i in range(3)]
    result = {
        "columns": ["reportdate", "total_cost"],
        "rows": rows,
        "row_count": 3,
    }
    sql = "SELECT reportdate, total_cost FROM mxwo ORDER BY reportdate"
    out = svc._suggest_chart("月份趨勢", sql, result)
    assert out is not None
    assert out["type"] == "line"
    assert out["x_key"] == "reportdate"


# ── Extra: bar too-many-rows blocked ─────────────────────────────────────────

def test_bar_blocked_when_over_30_rows():
    svc = make_svc()
    rows = [{"status": f"S{i}", "cnt": i + 1} for i in range(31)]
    result = {
        "columns": ["status", "cnt"],
        "rows": rows,
        "row_count": 31,
    }
    sql = "SELECT status, COUNT(*) AS cnt FROM mxwo GROUP BY status"
    out = svc._suggest_chart("狀態統計", sql, result)
    assert out is not None
    assert out["type"] == "none"
    assert "30" in out["warning"]
