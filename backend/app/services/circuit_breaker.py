"""
Pattern 5: Circuit Breaker — 避免級聯故障
為 LLM/Qdrant/Redis 等外部服務提供斷路保護。

狀態：CLOSED（正常）→ OPEN（斷路）→ HALF_OPEN（試探）
"""

import time
import logging
from enum import Enum
from typing import Optional

log = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """輕量級 Circuit Breaker，不依賴外部套件。"""

    def __init__(self, name: str, failure_threshold: int = 3,
                 recovery_timeout: float = 30.0, half_open_max: int = 1):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                log.info("Circuit breaker [%s]: OPEN → HALF_OPEN", self.name)
        return self._state

    @property
    def is_available(self) -> bool:
        """是否允許通過（CLOSED 或 HALF_OPEN 且未超過試探次數）。"""
        s = self.state
        if s == CircuitState.CLOSED:
            return True
        if s == CircuitState.HALF_OPEN:
            return self._half_open_calls < self.half_open_max
        return False

    def record_success(self):
        """記錄成功呼叫。"""
        if self._state == CircuitState.HALF_OPEN:
            log.info("Circuit breaker [%s]: HALF_OPEN → CLOSED (success)", self.name)
        self._state = CircuitState.CLOSED
        self._failure_count = 0

    def record_failure(self):
        """記錄失敗呼叫。"""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            log.warning("Circuit breaker [%s]: HALF_OPEN → OPEN (failure)", self.name)
        elif self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            log.warning("Circuit breaker [%s]: CLOSED → OPEN (failures=%d)",
                        self.name, self._failure_count)

        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1

    def reset(self):
        """手動重置。"""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_calls = 0

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
        }


# ── 全域斷路器實例 ──────────────────────────────────────────────────────
_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(name: str, failure_threshold: int = 3,
                recovery_timeout: float = 30.0) -> CircuitBreaker:
    """取得或建立指定名稱的 CircuitBreaker。"""
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name, failure_threshold, recovery_timeout)
    return _breakers[name]


def get_all_breakers() -> dict[str, dict]:
    """取得所有斷路器狀態（供健康檢查用）。"""
    return {name: cb.get_status() for name, cb in _breakers.items()}


# 預定義常用斷路器
LLM_BREAKER = get_breaker("llm", failure_threshold=3, recovery_timeout=60.0)
QDRANT_BREAKER = get_breaker("qdrant", failure_threshold=3, recovery_timeout=30.0)
REDIS_BREAKER = get_breaker("redis", failure_threshold=5, recovery_timeout=15.0)
