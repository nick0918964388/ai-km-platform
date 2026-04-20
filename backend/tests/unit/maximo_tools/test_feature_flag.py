"""
Unit tests for backend/app/services/maximo_tools/feature_flag.py

Tests use monkeypatch to set/unset MAXIMO_TOOL_ROUTER_ENABLED without
touching any external state. No real env vars are modified permanently.
"""

import logging

import pytest

from app.services.maximo_tools.feature_flag import (
    _FLAG_NAME,
    is_tool_router_enabled,
)


# ---------------------------------------------------------------------------
# TC-01: env var unset → True (safe default)
# ---------------------------------------------------------------------------

def test_unset_returns_true(monkeypatch):
    monkeypatch.delenv(_FLAG_NAME, raising=False)
    assert is_tool_router_enabled() is True


# ---------------------------------------------------------------------------
# TC-02: "true" → True
# ---------------------------------------------------------------------------

def test_true_string_returns_true(monkeypatch):
    monkeypatch.setenv(_FLAG_NAME, "true")
    assert is_tool_router_enabled() is True


# ---------------------------------------------------------------------------
# TC-03: "false" → False
# ---------------------------------------------------------------------------

def test_false_string_returns_false(monkeypatch):
    monkeypatch.setenv(_FLAG_NAME, "false")
    assert is_tool_router_enabled() is False


# ---------------------------------------------------------------------------
# TC-04: "FALSE" → False (case insensitive)
# ---------------------------------------------------------------------------

def test_false_uppercase_returns_false(monkeypatch):
    monkeypatch.setenv(_FLAG_NAME, "FALSE")
    assert is_tool_router_enabled() is False


# ---------------------------------------------------------------------------
# TC-05: "1" → True
# ---------------------------------------------------------------------------

def test_one_returns_true(monkeypatch):
    monkeypatch.setenv(_FLAG_NAME, "1")
    assert is_tool_router_enabled() is True


# ---------------------------------------------------------------------------
# TC-06: "0" → False
# ---------------------------------------------------------------------------

def test_zero_returns_false(monkeypatch):
    monkeypatch.setenv(_FLAG_NAME, "0")
    assert is_tool_router_enabled() is False


# ---------------------------------------------------------------------------
# TC-07: "yes" → True
# ---------------------------------------------------------------------------

def test_yes_returns_true(monkeypatch):
    monkeypatch.setenv(_FLAG_NAME, "yes")
    assert is_tool_router_enabled() is True


# ---------------------------------------------------------------------------
# TC-08: "no" → False
# ---------------------------------------------------------------------------

def test_no_returns_false(monkeypatch):
    monkeypatch.setenv(_FLAG_NAME, "no")
    assert is_tool_router_enabled() is False


# ---------------------------------------------------------------------------
# TC-09: unknown value → True + log warning
# ---------------------------------------------------------------------------

def test_gibberish_returns_true_with_warning(monkeypatch, caplog):
    monkeypatch.setenv(_FLAG_NAME, "gibberish")
    with caplog.at_level(logging.WARNING, logger="app.services.maximo_tools.feature_flag"):
        result = is_tool_router_enabled()
    assert result is True
    assert any("Invalid" in r.message for r in caplog.records)
    assert any("gibberish" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# TC-10a: empty string → unknown value → True + log warning
# ---------------------------------------------------------------------------

def test_empty_string_returns_true_with_warning(monkeypatch, caplog):
    monkeypatch.setenv(_FLAG_NAME, "")
    with caplog.at_level(logging.WARNING, logger="app.services.maximo_tools.feature_flag"):
        result = is_tool_router_enabled()
    assert result is True
    assert any("Invalid" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# TC-10b: value with surrounding whitespace is normalised correctly
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("  true  ", True),
    ("  false  ", False),
    ("  TRUE  ", True),
    ("  FALSE  ", False),
    ("  1  ", True),
    ("  0  ", False),
    ("  yes  ", True),
    ("  no  ", False),
    ("  on  ", True),
    ("  off  ", False),
])
def test_whitespace_trimmed(monkeypatch, value, expected):
    monkeypatch.setenv(_FLAG_NAME, value)
    assert is_tool_router_enabled() is expected


# ---------------------------------------------------------------------------
# TC-10c: "on" / "off" are also recognised
# ---------------------------------------------------------------------------

def test_on_returns_true(monkeypatch):
    monkeypatch.setenv(_FLAG_NAME, "on")
    assert is_tool_router_enabled() is True


def test_off_returns_false(monkeypatch):
    monkeypatch.setenv(_FLAG_NAME, "off")
    assert is_tool_router_enabled() is False


# ---------------------------------------------------------------------------
# TC-10d: TRUE (all caps) → True (case insensitive)
# ---------------------------------------------------------------------------

def test_true_uppercase_returns_true(monkeypatch):
    monkeypatch.setenv(_FLAG_NAME, "TRUE")
    assert is_tool_router_enabled() is True
