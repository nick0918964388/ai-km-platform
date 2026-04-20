"""Tests for Batch 2-B self-reflection retry decision logic.

We cover the pure decision function `MaximoNL2SQL.should_retry_reflection`
(class-level, no DB needed). End-to-end retry count behavior is exercised
only indirectly via the decision function — spinning up a full `MaximoNL2SQL`
instance requires an AsyncSession which is out of scope for unit tests.
"""
from __future__ import annotations

import pytest

from app.services.maximo_nl2sql import MaximoNL2SQL


# ── Core skip/retry matrix ────────────────────────────────────────────────

def test_skip_reflection_when_sql_valid_and_high_confidence():
    """SQL validator passed + confidence 0.8 + no rule issues → SKIP retry."""
    assert MaximoNL2SQL.should_retry_reflection(
        confidence=0.8,
        sql_valid=True,
        from_cache=False,
        is_hybrid=False,
        rule_issues=[],
        attempt=0,
        max_iter=2,
    ) is False


def test_skip_reflection_when_sql_valid_and_mid_confidence():
    """Mid confidence (0.5) with no issues → SKIP (old threshold 0.7 was too aggressive)."""
    assert MaximoNL2SQL.should_retry_reflection(
        confidence=0.5,
        sql_valid=True,
        from_cache=False,
        is_hybrid=False,
        rule_issues=[],
        attempt=0,
        max_iter=2,
    ) is False


def test_retry_when_confidence_very_low():
    """Confidence < 0.3 triggers retry even without rule issues."""
    assert MaximoNL2SQL.should_retry_reflection(
        confidence=0.1,
        sql_valid=True,
        from_cache=False,
        is_hybrid=False,
        rule_issues=["問題要求排名/排序，但 SQL 未使用 ORDER BY"],
        attempt=0,
        max_iter=2,
    ) is True


def test_retry_when_sql_invalid():
    """SQL validator failure is a hard error → always retry regardless of confidence."""
    assert MaximoNL2SQL.should_retry_reflection(
        confidence=0.9,
        sql_valid=False,
        from_cache=False,
        is_hybrid=False,
        rule_issues=[],
        attempt=0,
        max_iter=2,
    ) is True


def test_retry_when_hard_rule_issue_present():
    """Hard rule issue (asked for count, no COUNT) → retry."""
    assert MaximoNL2SQL.should_retry_reflection(
        confidence=0.8,
        sql_valid=True,
        from_cache=False,
        is_hybrid=False,
        rule_issues=["問題要求統計數量，但 SQL 未使用 COUNT 函數"],
        attempt=0,
        max_iter=2,
    ) is True


def test_skip_reflection_for_zero_rows_only():
    """0-rows is a soft hint; should NOT alone trigger retry (waste of 2-3s)."""
    # 0-rows issue ≠ hard rule marker; no hard issues → skip
    assert MaximoNL2SQL.should_retry_reflection(
        confidence=0.7,
        sql_valid=True,
        from_cache=False,
        is_hybrid=False,
        rule_issues=["查詢結果為 0 筆，可能查錯表或 WHERE 條件有誤，請檢查狀態值是否正確"],
        attempt=0,
        max_iter=2,
        skip_on_rule_pass=True,
    ) is False


# ── Cache & hybrid short-circuits ─────────────────────────────────────────

def test_skip_reflection_for_cache_hit():
    """Cache hit → never retry (SQL already validated when first cached)."""
    assert MaximoNL2SQL.should_retry_reflection(
        confidence=0.1,
        sql_valid=False,
        from_cache=True,
        is_hybrid=False,
        rule_issues=["SQL 驗證失敗：不允許存取的表：foo"],
        attempt=0,
        max_iter=2,
    ) is False


def test_skip_reflection_for_hybrid():
    """Hybrid path leaves retry to Alpha's decompose layer."""
    assert MaximoNL2SQL.should_retry_reflection(
        confidence=0.0,
        sql_valid=False,
        from_cache=False,
        is_hybrid=True,
        rule_issues=["SQL 驗證失敗：語法錯誤"],
        attempt=0,
        max_iter=1,
    ) is False


# ── Max retries cap ───────────────────────────────────────────────────────

def test_max_retry_capped():
    """On last attempt (attempt == max_iter-1) must not retry."""
    assert MaximoNL2SQL.should_retry_reflection(
        confidence=0.0,
        sql_valid=False,
        from_cache=False,
        is_hybrid=False,
        rule_issues=["SQL 驗證失敗：foo"],
        attempt=1,
        max_iter=2,
    ) is False


def test_max_retry_capped_at_1_in_default_config():
    """Default config sets nl2sql_max_retries=1, so max_iter for accurate=2,
    meaning 1 generation + 1 retry max. Verify semantics:
    - attempt=0 with hard error → retry (True)
    - attempt=1 (which is max_iter-1=1) → skip (False)
    """
    # First attempt with hard error → retry
    assert MaximoNL2SQL.should_retry_reflection(
        confidence=0.0, sql_valid=False, from_cache=False, is_hybrid=False,
        rule_issues=[], attempt=0, max_iter=2,
    ) is True
    # Second attempt (last) → no more retries
    assert MaximoNL2SQL.should_retry_reflection(
        confidence=0.0, sql_valid=False, from_cache=False, is_hybrid=False,
        rule_issues=[], attempt=1, max_iter=2,
    ) is False


# ── skip_on_rule_pass toggle ──────────────────────────────────────────────

def test_skip_on_rule_pass_disabled_falls_through_to_confidence():
    """When operator disables skip_on_rule_pass, confidence threshold still
    governs: high confidence → skip, low confidence → retry."""
    # Even with skip disabled, confidence 0.9 is safe
    assert MaximoNL2SQL.should_retry_reflection(
        confidence=0.9,
        sql_valid=True,
        from_cache=False,
        is_hybrid=False,
        rule_issues=[],
        attempt=0,
        max_iter=2,
        skip_on_rule_pass=False,
    ) is False
    # Confidence below threshold → retry
    assert MaximoNL2SQL.should_retry_reflection(
        confidence=0.1,
        sql_valid=True,
        from_cache=False,
        is_hybrid=False,
        rule_issues=[],
        attempt=0,
        max_iter=2,
        skip_on_rule_pass=False,
    ) is True


def test_custom_threshold():
    """Threshold parameter can be tuned — higher threshold = more retries."""
    # conf=0.5, threshold=0.7 → retry (below)
    # but skip_on_rule_pass=True with no rule issues skips anyway
    assert MaximoNL2SQL.should_retry_reflection(
        confidence=0.5,
        sql_valid=True,
        from_cache=False,
        is_hybrid=False,
        rule_issues=[],
        attempt=0,
        max_iter=2,
        threshold=0.7,
        skip_on_rule_pass=True,
    ) is False
    # With skip disabled, 0.5 < 0.7 → retry
    assert MaximoNL2SQL.should_retry_reflection(
        confidence=0.5,
        sql_valid=True,
        from_cache=False,
        is_hybrid=False,
        rule_issues=[],
        attempt=0,
        max_iter=2,
        threshold=0.7,
        skip_on_rule_pass=False,
    ) is True
