"""SQL Row-level Policy 單元測試 — Security #4"""
from __future__ import annotations

import pytest

from app.services.sql_policy import (
    SQLRowLevelPolicy,
    PolicyViolation,
    get_sql_policy,
)


@pytest.fixture
def policy() -> SQLRowLevelPolicy:
    return SQLRowLevelPolicy()


# ── 正常查詢 ──────────────────────────────────────────────────────
def test_allow_normal_query(policy):
    sql = "SELECT * FROM maximo_mxwo WHERE status = 'OPEN' LIMIT 10"
    result = policy.check(sql, allowed_tables={"maximo_mxwo"})
    assert result.allowed, f"reason={result.reason}"


def test_allow_join_within_allowed(policy):
    sql = "SELECT a.wonum, b.description FROM maximo_mxwo a JOIN maximo_asset b ON a.assetnum = b.assetnum"
    result = policy.check(sql, allowed_tables={"maximo_mxwo", "maximo_asset"})
    assert result.allowed


def test_allow_without_allowed_tables_check(policy):
    """allowed_tables=None 時不檢查跨表，但 forbidden 表仍擋。"""
    sql = "SELECT * FROM maximo_mxwo LIMIT 10"
    result = policy.check(sql, allowed_tables=None)
    assert result.allowed


# ── 系統表擋下 ────────────────────────────────────────────────────
@pytest.mark.parametrize("table", [
    "users",
    "api_keys",
    "sessions",
    "auth_tokens",
    "jwt_blacklist",
    "system_settings",
    "pg_stat_activity",
    "refresh_tokens",
])
def test_block_forbidden_system_tables(policy, table):
    sql = f"SELECT * FROM {table}"
    result = policy.check(sql, allowed_tables={table, "maximo_mxwo"})
    assert not result.allowed
    assert table in result.blocked_tables


def test_block_forbidden_via_join(policy):
    sql = "SELECT a.id, u.email FROM maximo_mxwo a JOIN users u ON a.user_id = u.id"
    result = policy.check(sql, allowed_tables={"maximo_mxwo", "users"})
    assert not result.allowed
    assert "users" in result.blocked_tables


# ── 敏感欄位擋下 ──────────────────────────────────────────────────
@pytest.mark.parametrize("col", [
    "password",
    "password_hash",
    "api_key",
    "secret",
    "private_key",
    "jwt_secret",
    "access_token",
    "refresh_token",
])
def test_block_forbidden_columns(policy, col):
    sql = f"SELECT {col} FROM maximo_mxwo"
    result = policy.check(sql, allowed_tables={"maximo_mxwo"})
    assert not result.allowed
    assert col in result.blocked_columns


def test_block_forbidden_column_in_where(policy):
    sql = "SELECT id FROM maximo_mxwo WHERE password = 'abc'"
    result = policy.check(sql, allowed_tables={"maximo_mxwo"})
    assert not result.allowed


# ── 跨表越權 ──────────────────────────────────────────────────────
def test_block_cross_table_unauthorized(policy):
    sql = "SELECT * FROM unauthorized_table"
    result = policy.check(sql, allowed_tables={"maximo_mxwo"})
    assert not result.allowed
    assert "unauthorized_table" in result.blocked_tables


def test_block_join_unauthorized_table(policy):
    sql = "SELECT a.id FROM maximo_mxwo a JOIN other_table b ON a.id = b.id"
    result = policy.check(sql, allowed_tables={"maximo_mxwo"})
    assert not result.allowed
    assert "other_table" in result.blocked_tables


# ── SQL builtins 不算越權 ────────────────────────────────────────
def test_lateral_unnest_allowed(policy):
    sql = "SELECT * FROM maximo_mxwo, LATERAL unnest(ARRAY[1,2,3]) AS x"
    result = policy.check(sql, allowed_tables={"maximo_mxwo"})
    assert result.allowed


# ── Empty sql ─────────────────────────────────────────────────────
def test_empty_sql_blocked(policy):
    result = policy.check("", allowed_tables={"maximo_mxwo"})
    assert not result.allowed


# ── Singleton ─────────────────────────────────────────────────────
def test_singleton():
    assert get_sql_policy() is get_sql_policy()


# ── PolicyViolation exception ─────────────────────────────────────
def test_policy_violation_exception():
    result = SQLRowLevelPolicy().check("SELECT * FROM users", allowed_tables={"users"})
    with pytest.raises(PolicyViolation):
        if not result.allowed:
            raise PolicyViolation(result.reason, result=result)
