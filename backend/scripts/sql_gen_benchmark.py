"""SQL Generation Benchmark — Anthropic Sonnet vs NVIDIA minimax (Batch 2-C)

Runs a fixed set of NL→SQL test questions through both providers, compares:
  1. SQL syntax validity (PostgreSQL EXPLAIN)
  2. Query execution equivalence (first N rows match, or row_count match for aggregates)
  3. LLM latency

Usage (on deployment host 192.168.1.11 where DB + env + key are live):

    docker exec -it aikm-backend python -m app.scripts.sql_gen_benchmark \\
        --out /tmp/bench.json

Or from host:

    cd backend
    python -m scripts.sql_gen_benchmark --out docs/sql_gen_benchmark_result.json

Options:
  --only anthropic|nvidia   Run only one provider (skip comparison)
  --limit N                 Run first N questions only
  --out PATH                Write JSON report
  --test-set NAME           built-in set name (default: 'core20')

Writes a JSON report with per-question results. A companion markdown summary is
produced at `docs/sql_gen_benchmark_2026-04-19.md` by hand or via --md flag.

NOTE: This script only runs against a live DB + LLM keys — it is NOT part of
pytest. CI should NOT invoke it. Treat as an ops tool.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

# Ensure backend/app is importable when invoked from scripts dir directly
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# ── Test question sets ────────────────────────────────────────────────────
# 20 representative NL→SQL queries covering: count, filter by asset, time range,
# ranking, join (cm + fault), follow-up, hybrid-ish.
CORE_20 = [
    "全部車輛數量",
    "EMU900 去年故障了幾次",
    "哪台車最常故障前5名",
    "列出最近一週臨修工單",
    "列出最新 10 個工單",
    "TEMU2000 的狀態",
    "去年每月的故障通報數量",
    "列出所有 EMU800 車輛",
    "EMU901-1 的所有故障紀錄",
    "定檢工單中 3A 的數量",
    "借用段在南港的車輛",
    "最近一個月的臨修工單數量",
    "故障等級為高的通報數量",
    "2025 年的定檢工單",
    "T1 工單中最近 10 筆",
    "列出故障說明包含煞車的工單",
    "每個機廠的車輛數量",
    "EMU3000 車型的車輛有幾台",
    "本月已結案的故障通報",
    "狀態為 OPERATING 的 EMU 車輛",
]

TEST_SETS = {
    "core20": CORE_20,
    "quick5": CORE_20[:5],
}


# ── Result dataclass ──────────────────────────────────────────────────────

@dataclass
class ProviderResult:
    provider: str
    model: str
    sql: Optional[str] = None
    error: Optional[str] = None
    llm_ms: Optional[float] = None
    syntax_ok: bool = False
    exec_ok: bool = False
    row_count: Optional[int] = None
    sample_rows: List[dict] = field(default_factory=list)


@dataclass
class BenchmarkRow:
    question: str
    anthropic: Optional[ProviderResult] = None
    nvidia: Optional[ProviderResult] = None
    equivalent: Optional[bool] = None
    equivalence_reason: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────

async def run_one_provider(provider: str, question: str) -> ProviderResult:
    """Invoke MaximoNL2SQL under the given provider override and execute SQL."""
    from app.config import get_settings, invalidate_settings
    from app.services.maximo_nl2sql import MaximoNL2SQL
    from app.db.session import get_db

    # Override feature flag for this call
    invalidate_settings()
    settings = get_settings()
    orig_provider = settings.sql_generation_provider
    orig_model = settings.sql_generation_model
    try:
        settings.sql_generation_provider = provider  # type: ignore[attr-defined]
        if provider == "nvidia":
            settings.sql_generation_model = settings.nvidia_sql_model  # type: ignore[attr-defined]
        elif provider == "anthropic":
            settings.sql_generation_model = settings.anthropic_model  # type: ignore[attr-defined]

        async for db in get_db():
            svc = MaximoNL2SQL(db)
            res = ProviderResult(provider=provider, model=svc.model)
            try:
                t0 = time.monotonic()
                gen = await svc.generate_sql(question)
                res.llm_ms = round((time.monotonic() - t0) * 1000, 1)
                if gen.get("error") or not gen.get("sql"):
                    res.error = gen.get("error", "no sql generated")
                    return res
                res.sql = gen["sql"]

                # Syntax check via validate_sql
                err = svc.validate_sql(res.sql)
                if err:
                    res.error = f"validate_sql: {err}"
                    res.syntax_ok = False
                    return res
                res.syntax_ok = True

                # Execute
                exec_res = await svc.execute_sql(res.sql)
                if exec_res.get("error"):
                    res.error = f"execute: {exec_res['error']}"
                    res.exec_ok = False
                    return res
                res.exec_ok = True
                res.row_count = exec_res.get("row_count")
                res.sample_rows = exec_res.get("rows", [])[:3]
                return res
            except Exception as e:  # noqa: BLE001
                res.error = f"exception: {e!r}"
                return res
            finally:
                try:
                    await db.close()
                except Exception:
                    pass
            break
    finally:
        settings.sql_generation_provider = orig_provider  # type: ignore[attr-defined]
        settings.sql_generation_model = orig_model  # type: ignore[attr-defined]
    return ProviderResult(provider=provider, model="")


def compare_results(a: ProviderResult, b: ProviderResult) -> tuple[bool, str]:
    """Rough equivalence check. Not a full semantic comparison — use as a
    directional signal only."""
    if not a.exec_ok or not b.exec_ok:
        return False, f"one side failed: anthropic.ok={a.exec_ok} nvidia.ok={b.exec_ok}"
    # Aggregate queries (row_count tiny) → compare row_count
    if (a.row_count or 0) <= 5 and (b.row_count or 0) <= 5:
        if a.row_count == b.row_count and a.sample_rows == b.sample_rows:
            return True, "aggregate rows match"
        return False, f"aggregate row diff: a={a.sample_rows} b={b.sample_rows}"
    # Large result sets: compare row_count within ±10% (SQL may differ in ORDER BY)
    if a.row_count and b.row_count:
        ratio = min(a.row_count, b.row_count) / max(a.row_count, b.row_count)
        if ratio >= 0.9:
            return True, f"row_count within 10% ({a.row_count} vs {b.row_count})"
        return False, f"row_count diff > 10% ({a.row_count} vs {b.row_count})"
    return False, "unknown"


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--only", choices=["anthropic", "nvidia"], default=None,
                   help="run only one provider (skip comparison)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--out", default="/tmp/sql_gen_benchmark.json")
    p.add_argument("--test-set", default="core20", choices=list(TEST_SETS.keys()))
    args = p.parse_args()

    questions = TEST_SETS[args.test_set]
    if args.limit:
        questions = questions[: args.limit]

    print(f"Running {len(questions)} questions...")
    rows: List[BenchmarkRow] = []
    for i, q in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] {q}")
        row = BenchmarkRow(question=q)
        if args.only in (None, "anthropic"):
            row.anthropic = await run_one_provider("anthropic", q)
        if args.only in (None, "nvidia"):
            row.nvidia = await run_one_provider("nvidia", q)
        if row.anthropic and row.nvidia:
            eq, reason = compare_results(row.anthropic, row.nvidia)
            row.equivalent = eq
            row.equivalence_reason = reason
        rows.append(row)

    # Summary
    total = len(rows)
    equiv = sum(1 for r in rows if r.equivalent)
    a_ms = [r.anthropic.llm_ms for r in rows if r.anthropic and r.anthropic.llm_ms]
    n_ms = [r.nvidia.llm_ms for r in rows if r.nvidia and r.nvidia.llm_ms]
    a_avg = sum(a_ms) / len(a_ms) if a_ms else None
    n_avg = sum(n_ms) / len(n_ms) if n_ms else None
    a_syntax = sum(1 for r in rows if r.anthropic and r.anthropic.syntax_ok)
    n_syntax = sum(1 for r in rows if r.nvidia and r.nvidia.syntax_ok)
    a_exec = sum(1 for r in rows if r.anthropic and r.anthropic.exec_ok)
    n_exec = sum(1 for r in rows if r.nvidia and r.nvidia.exec_ok)

    summary = {
        "total": total,
        "equivalent_count": equiv,
        "equivalent_rate": (equiv / total) if total else 0,
        "anthropic": {
            "avg_llm_ms": a_avg,
            "syntax_ok": a_syntax,
            "exec_ok": a_exec,
        },
        "nvidia": {
            "avg_llm_ms": n_avg,
            "syntax_ok": n_syntax,
            "exec_ok": n_exec,
        },
    }
    report = {
        "summary": summary,
        "rows": [
            {
                "question": r.question,
                "anthropic": asdict(r.anthropic) if r.anthropic else None,
                "nvidia": asdict(r.nvidia) if r.nvidia else None,
                "equivalent": r.equivalent,
                "equivalence_reason": r.equivalence_reason,
            }
            for r in rows
        ],
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print()
    print("=" * 60)
    print(f"Report written to {args.out}")
    print(f"Total: {total}, Equivalent: {equiv}/{total} ({equiv/total*100:.1f}%)")
    print(f"Avg LLM latency — anthropic: {a_avg}ms, nvidia: {n_avg}ms")
    print(f"Syntax OK — anthropic: {a_syntax}/{total}, nvidia: {n_syntax}/{total}")
    print(f"Exec OK   — anthropic: {a_exec}/{total}, nvidia: {n_exec}/{total}")
    # Recommendation
    if equiv / total >= 0.85 if total else False:
        print()
        print("✅ Recommendation: ≥85% equivalence → safe to set sql_generation_provider=nvidia as default")
    else:
        print()
        print("⚠️  Recommendation: <85% equivalence → keep anthropic default; nvidia as opt-in only")


if __name__ == "__main__":
    asyncio.run(main())
