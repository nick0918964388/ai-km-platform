"""S4 PreFilter unit tests.

驗收（7 項）：
  1. "你好"  → chitchat
  2. "?"     → clarify
  3. "查"    → clarify
  4. "EMU800 故障"  → allow
  5. "列出核簽中的工單"  → allow
  6. "hi  " (strip → "hi" len=2)  → clarify
  7. P95 benchmark: 100 次 check() < 20ms
"""

import statistics
import time

import pytest

from app.services.pre_filter import PreFilter, Verdict


@pytest.fixture(scope="module")
def pf() -> PreFilter:
    """One PreFilter instance shared across all tests in this module."""
    return PreFilter()


# ---------------------------------------------------------------------------
# 驗收 1-6
# ---------------------------------------------------------------------------

def test_chitchat_nihao(pf: PreFilter):
    """驗收 1: '你好' → chitchat（embedding 命中）"""
    v = pf.check("你好")
    assert v.action == "chitchat", f"expected chitchat, got {v.action!r} ({v.reason})"


def test_clarify_question_mark(pf: PreFilter):
    """驗收 2: '?' → clarify（len=1 < 5）"""
    v = pf.check("?")
    assert v.action == "clarify", f"expected clarify, got {v.action!r}"


def test_clarify_single_char(pf: PreFilter):
    """驗收 3: '查' → clarify（len=1 < 5）"""
    v = pf.check("查")
    assert v.action == "clarify", f"expected clarify, got {v.action!r}"


def test_allow_emu800(pf: PreFilter):
    """驗收 4: 'EMU800 故障' → allow"""
    v = pf.check("EMU800 故障")
    assert v.action == "allow", f"expected allow, got {v.action!r} ({v.reason})"


def test_allow_workorder_query(pf: PreFilter):
    """驗收 5: '列出核簽中的工單' → allow"""
    v = pf.check("列出核簽中的工單")
    assert v.action == "allow", f"expected allow, got {v.action!r} ({v.reason})"


def test_clarify_hi_with_spaces(pf: PreFilter):
    """驗收 6: 'hi  ' strip → 'hi' len=2 → clarify"""
    v = pf.check("hi  ")
    assert v.action == "clarify", f"expected clarify, got {v.action!r}"


# ---------------------------------------------------------------------------
# 驗收 7: P95 benchmark
# ---------------------------------------------------------------------------

def test_p95_latency(pf: PreFilter):
    """驗收 7: 100 次 check() 的 P95 < 20ms（seed 已預載）"""
    query = "EMU800 故障紀錄"
    times_ms: list[float] = []
    for _ in range(100):
        t0 = time.perf_counter()
        pf.check(query)
        times_ms.append((time.perf_counter() - t0) * 1000)

    p95 = statistics.quantiles(times_ms, n=100)[94]  # index 94 = P95
    print(f"\n[benchmark] P95={p95:.2f}ms  P50={statistics.median(times_ms):.2f}ms  max={max(times_ms):.2f}ms")
    assert p95 < 20.0, f"P95={p95:.2f}ms exceeds 20ms target"


# ---------------------------------------------------------------------------
# Extra edge cases
# ---------------------------------------------------------------------------

def test_clarify_returns_options(pf: PreFilter):
    """clarify verdict must carry clarification_options list."""
    v = pf.check("?")
    assert v.clarification_options is not None
    assert len(v.clarification_options) >= 1


def test_verdict_fields(pf: PreFilter):
    """Verdict dataclass has action + reason."""
    v = pf.check("你好")
    assert hasattr(v, "action")
    assert hasattr(v, "reason")
    assert isinstance(v.reason, str)


def test_cost_block_select_star(pf: PreFilter):
    """cost_block regex fires on SELECT * FROM workorders (no WHERE)."""
    v = pf.check("SELECT * FROM workorders")
    assert v.action == "cost_block"


def test_allow_select_star_with_where(pf: PreFilter):
    """SELECT * with WHERE should NOT be cost_blocked."""
    v = pf.check("SELECT * FROM workorders WHERE status='WAPPR'")
    assert v.action == "allow"
