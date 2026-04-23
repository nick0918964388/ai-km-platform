"""
S1.5 Terminology Normalizer — 驗收測試 × 4

AC1: normalize("核簽工單有幾張") → "核簽中工單有幾張", applied 含 ("核簽工單","核簽中工單")
AC2: normalize("列出故障") → ("列出故障", [])
AC3: 50-term dict P95 normalize() < 2 ms
AC4: YAML 缺失 → load 不 crash，返空 dict → normalize() passthrough
"""

from __future__ import annotations

import importlib
import os
import statistics
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# ── 確保 backend 在 import path ──────────────────────────────────────────────
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.terminology_normalizer import loader as _loader_mod
from app.services.terminology_normalizer import normalizer as _norm_mod


# ── Helpers ──────────────────────────────────────────────────────────────────

def _reload_with_dict(terms: dict[str, str]) -> None:
    """Force normalizer to use a specific dict (bypasses YAML)."""
    _norm_mod._loaded = False
    _norm_mod._sorted_terms = sorted(terms.items(), key=lambda kv: len(kv[0]), reverse=True)
    _norm_mod._terms_dict = terms
    _norm_mod._loaded = True


def _reset_normalizer() -> None:
    _norm_mod._loaded = False
    _norm_mod._sorted_terms = []
    _norm_mod._terms_dict = {}


# ── AC1: 正常替換（最長片段優先） ────────────────────────────────────────────

def test_ac1_longest_match_wins():
    """核簽工單 > 核簽，確保長片段優先且 canonical 不被二次命中。"""
    _reload_with_dict(
        {
            "核簽": "核簽中",
            "核簽工單": "核簽中工單",
            "等待核簽": "核簽中",
            "派工": "派工中",
            "未結案": "未完工",
        }
    )
    result, applied = _norm_mod.normalize("核簽工單有幾張")

    assert result == "核簽中工單有幾張", f"Got: {result!r}"
    assert ("核簽工單", "核簽中工單") in applied, f"applied: {applied}"
    # 確認較短的 "核簽" 沒有被套用（因為 "核簽工單" 先匹配並保護了該段）
    applied_sources = [a[0] for a in applied]
    assert "核簽" not in applied_sources, f"'核簽' should NOT appear in applied: {applied}"


# ── AC2: 無匹配 passthrough ───────────────────────────────────────────────────

def test_ac2_no_match():
    _reload_with_dict(
        {
            "核簽": "核簽中",
            "核簽工單": "核簽中工單",
        }
    )
    result, applied = _norm_mod.normalize("列出故障")
    assert result == "列出故障"
    assert applied == []


# ── AC3: 50-term dict P95 < 2ms ─────────────────────────────────────────────

def test_ac3_performance_p95():
    # 構建 50 個 term
    terms = {f"術語{i:02d}": f"標準術語{i:02d}" for i in range(50)}
    terms.update({"核簽工單": "核簽中工單", "核簽": "核簽中"})
    _reload_with_dict(terms)

    samples = 200
    query = "請列出核簽工單有幾張，以及術語01和術語25的統計"

    timings: list[float] = []
    for _ in range(samples):
        t0 = time.perf_counter()
        _norm_mod.normalize(query)
        timings.append((time.perf_counter() - t0) * 1000)  # ms

    p95 = statistics.quantiles(timings, n=100)[94]  # index 94 = 95th percentile
    assert p95 < 2.0, f"P95 latency = {p95:.3f} ms, expected < 2 ms"


# ── AC4: YAML 缺失不 crash ───────────────────────────────────────────────────

def test_ac4_missing_yaml_no_crash():
    # loader: 缺檔返空 dict
    result = _loader_mod.load_terminology("/nonexistent/path/terminology.yml")
    assert result == {}, f"Expected empty dict, got: {result}"

    # normalizer: 空字典下 normalize() 直接 passthrough
    _reload_with_dict({})
    out, applied = _norm_mod.normalize("核簽工單")
    assert out == "核簽工單"
    assert applied == []


# ── 額外：驗證多處替換不互相污染 ─────────────────────────────────────────────

def test_no_cross_contamination():
    """「核簽」在 canonical「核簽中工單」裡不會被再次替換。"""
    _reload_with_dict({"核簽工單": "核簽中工單", "核簽": "核簽中"})
    result, applied = _norm_mod.normalize("核簽工單核簽")
    # "核簽工單" → "核簽中工單"（protected），"核簽" → "核簽中"
    assert result == "核簽中工單核簽中", f"Got: {result!r}"
    applied_sources = {a[0] for a in applied}
    assert applied_sources == {"核簽工單", "核簽"}, f"applied: {applied}"
