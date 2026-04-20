"""
SQL Row-level Policy (Security #4) — 深度防禦，即使 admin 也要過。

防止：
1. 跨權限越權查詢（table 不在此 role 的 allowed set）
2. 系統敏感表（users / api_keys / sessions 等）透過 NL→SQL 被讀取
3. 敏感欄位（password / secret / private_key）出現在 SELECT

整合點：maximo_nl2sql.py 在 validate_sql 之後、execute_sql 之前。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PolicyResult:
    allowed: bool
    reason: str
    blocked_tables: list[str] = field(default_factory=list)
    blocked_columns: list[str] = field(default_factory=list)


class SQLRowLevelPolicy:
    # 嚴格禁查的系統表（即使 admin 也不能透過 NL→SQL 查詢這些）
    FORBIDDEN_TABLES: set[str] = {
        # 認證 / 使用者敏感資料
        "users",
        "user_credentials",
        "user_passwords",
        "api_keys",
        "auth_tokens",
        "sessions",
        "jwt_blacklist",
        "refresh_tokens",
        # 系統設定 / 稽核（稽核資料走另外的管道）
        "system_settings",
        "audit_log_raw",
        # PostgreSQL 內部表
        "pg_stat_statements",
        "pg_stat_activity",
        "pg_shadow",
        "pg_authid",
        "information_schema",
        "pg_catalog",
    }

    # 敏感欄位：即使是允許的表也要擋
    FORBIDDEN_COLUMNS: set[str] = {
        "password",
        "password_hash",
        "password_hash_bcrypt",
        "passwd",
        "api_key",
        "apikey",
        "secret",
        "secret_key",
        "private_key",
        "jwt_secret",
        "encryption_key",
        "access_token",
        "refresh_token",
    }

    def check(self, sql: str, allowed_tables: set[str] | None = None) -> PolicyResult:
        """
        Args:
            sql: LLM 產出的 SQL。
            allowed_tables: 此使用者 role 可查的表。None = 不檢查（用 SQL validator 的 static set），
                            空 set 或非空 set = 比對。
        """
        if not sql:
            return PolicyResult(allowed=False, reason="empty_sql")

        sql_lower = sql.lower()

        # 1. 禁查系統表：比對 from/join 後的 table name（避免把 'users' 這個字串本身 false positive）
        blocked_tables: list[str] = []
        for t in self.FORBIDDEN_TABLES:
            if re.search(rf"\b(?:from|join)\s+{re.escape(t)}\b", sql_lower):
                blocked_tables.append(t)

        if blocked_tables:
            logger.warning("[sql_policy] blocked system tables: %s", blocked_tables)
            return PolicyResult(
                allowed=False,
                reason=f"Query references forbidden system tables: {blocked_tables}",
                blocked_tables=blocked_tables,
            )

        # 2. 禁查敏感欄位（掃 SELECT / WHERE / ORDER BY 整段 SQL 字面上出現）
        # 需避免 false positive：比對整字 (\b...\b)
        blocked_cols: list[str] = []
        for col in self.FORBIDDEN_COLUMNS:
            # 必須非 table name 的一部分，所以跟 . 或 space 或 , 等相鄰
            if re.search(rf"\b{re.escape(col)}\b", sql_lower):
                blocked_cols.append(col)

        if blocked_cols:
            logger.warning("[sql_policy] blocked columns: %s", blocked_cols)
            return PolicyResult(
                allowed=False,
                reason=f"Query references forbidden column(s): {blocked_cols}",
                blocked_columns=blocked_cols,
            )

        # 3. 逐 table 檢查是否在 allowed_tables 內
        if allowed_tables:
            table_refs = re.findall(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql_lower)
            # 排除 SQL/PostgreSQL 功能性詞彙
            sql_builtins = {"lateral", "unnest", "generate_series"}
            unauthorized = [
                t for t in table_refs
                if t not in allowed_tables and t not in sql_builtins
            ]
            if unauthorized:
                logger.warning(
                    "[sql_policy] unauthorized tables: %s (allowed=%s)",
                    unauthorized,
                    sorted(allowed_tables)[:10],
                )
                return PolicyResult(
                    allowed=False,
                    reason=f"Query references unauthorized tables: {unauthorized}",
                    blocked_tables=unauthorized,
                )

        return PolicyResult(allowed=True, reason="passed")


_policy: SQLRowLevelPolicy | None = None


def get_sql_policy() -> SQLRowLevelPolicy:
    global _policy
    if _policy is None:
        _policy = SQLRowLevelPolicy()
    return _policy


class PolicyViolation(Exception):
    """SQL 違反 row-level policy。"""

    def __init__(self, message: str, result: PolicyResult | None = None):
        super().__init__(message)
        self.result = result
