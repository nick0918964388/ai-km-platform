"""Rate Limit + Guardrail Alert 單元測試 — Security #5"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.middleware import rate_limit as rl


class FakePipeline:
    def __init__(self, counter_ref: dict, key: str):
        self.counter_ref = counter_ref
        self.key = key
        self._ops: list = []

    def incr(self, key):
        self._ops.append(("incr", key))
        return self

    def expire(self, key, ttl):
        self._ops.append(("expire", key, ttl))
        return self

    def execute(self):
        self.counter_ref[self.key] = self.counter_ref.get(self.key, 0) + 1
        return [self.counter_ref[self.key], True]


class FakeRedis:
    def __init__(self):
        self.counters: dict[str, int] = {}
        self._fail = False

    def pipeline(self):
        if self._fail:
            raise RuntimeError("fake redis failure")
        # 每次 pipeline 呼叫時，一旦 execute 時 increment 對應 key
        # 實際上 key 是在 pipeline.incr 後記住，但為簡化 — pipeline 取 last incr key
        return FakePipelineWrapper(self.counters)


class FakePipelineWrapper:
    def __init__(self, counters: dict):
        self.counters = counters
        self._key: str | None = None
        self._ttl: int | None = None

    def incr(self, key):
        self._key = key
        return self

    def expire(self, key, ttl):
        self._ttl = ttl
        return self

    def execute(self):
        assert self._key is not None
        self.counters[self._key] = self.counters.get(self._key, 0) + 1
        return [self.counters[self._key], True]


@pytest.fixture
def fake_redis():
    return FakeRedis()


# ── Rate limit pass ────────────────────────────────────────────────
def test_rate_limit_under_quota_passes(fake_redis):
    with patch.object(rl.cache_service, "get_redis_client", return_value=fake_redis):
        for _ in range(5):
            rl.check_rate_limit("user1", endpoint="chat", limit_per_min=30)
    # should not raise
    assert True


def test_rate_limit_over_quota_raises_429(fake_redis):
    with patch.object(rl.cache_service, "get_redis_client", return_value=fake_redis):
        # 超過 limit → 429
        with pytest.raises(HTTPException) as exc:
            for _ in range(35):
                rl.check_rate_limit("user2", endpoint="chat", limit_per_min=30)
        assert exc.value.status_code == 429


def test_rate_limit_fail_open_when_cache_unavailable():
    """Cache 不可用時 fail-open（不 raise）。"""
    with patch.object(rl.cache_service, "get_redis_client", return_value=None):
        for _ in range(100):
            rl.check_rate_limit("user3", endpoint="chat", limit_per_min=30)
    # 不 raise 就是通過


def test_rate_limit_separate_users(fake_redis):
    """不同 user 用不同 bucket。"""
    with patch.object(rl.cache_service, "get_redis_client", return_value=fake_redis):
        for _ in range(20):
            rl.check_rate_limit("userA", endpoint="chat", limit_per_min=30)
            rl.check_rate_limit("userB", endpoint="chat", limit_per_min=30)
    # 兩人各 20 次都應通過


# ── Guardrail block counter ─────────────────────────────────────────
def test_guardrail_block_counter_accumulates(fake_redis):
    with patch.object(rl.cache_service, "get_redis_client", return_value=fake_redis):
        c1 = rl.record_guardrail_block("spammer")
        c2 = rl.record_guardrail_block("spammer")
        c3 = rl.record_guardrail_block("spammer")
    assert c1 == 1
    assert c2 == 2
    assert c3 == 3


def test_abuse_threshold_triggers_alert_log(fake_redis, caplog):
    import logging
    caplog.set_level(logging.ERROR, logger=rl.__name__)
    with patch.object(rl.cache_service, "get_redis_client", return_value=fake_redis):
        # 預設 threshold = 3
        for _ in range(rl.ABUSE_THRESHOLD):
            rl.record_guardrail_block("bad_actor")

    # 至少有一筆 SECURITY_ALERT level=ERROR log
    alerts = [r for r in caplog.records if "SECURITY_ALERT" in r.getMessage()]
    assert len(alerts) >= 1, f"Expected alert log, got: {[r.getMessage() for r in caplog.records]}"


def test_guardrail_block_fail_open_no_cache():
    with patch.object(rl.cache_service, "get_redis_client", return_value=None):
        result = rl.record_guardrail_block("x")
    assert result == 0  # fail-open return 0


# ── 空字串 user_id 被處理 ──────────────────────────────────────────
def test_empty_user_id_uses_anonymous(fake_redis):
    with patch.object(rl.cache_service, "get_redis_client", return_value=fake_redis):
        rl.check_rate_limit("", endpoint="chat", limit_per_min=30)
    # 不 raise 就是成功
