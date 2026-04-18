"""Hybrid decompose parallel execution tests (Batch 2-A).

Validates:
  1. Sub-tasks run in parallel (elapsed ≈ max individual latency, not sum)
  2. Partial failure — one sub-task fails, others still return results
  3. Hybrid path disables self-reflection retry (is_hybrid=True → max_iter=1)

These tests are pure-async with mocks, no DB/LLM/network required.
Follows repo convention: wrap async bodies in asyncio.run() since the project
does not use pytest-asyncio.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch


# --------------------------------------------------------------------------- #
# 1. Parallel execution — two sub-tasks complete concurrently
# --------------------------------------------------------------------------- #

def test_hybrid_parallel_execution_concurrent():
    """Two sub-SQL tasks of 0.3s each should complete in ~0.3s (parallel),
    not ~0.6s (serial)."""
    from app.services.orchestrator import run_parallel_agents, SubTask

    sub_tasks = [
        SubTask(id="sql_a", type="sql", sub_query="q1", label="A"),
        SubTask(id="sql_b", type="sql", sub_query="q2", label="B"),
    ]

    async def slow_sql(task, sql_history=None, prebuilt_schema=None):
        await asyncio.sleep(0.3)
        return {
            "task_id": task.id,
            "type": "sql",
            "result": {"success": True, "row_count": 1, "data": [{"x": 1}]},
            "sources": None,
            "error": None,
            "duration_ms": 300,
        }

    async def run():
        with patch("app.services.orchestrator._run_sql_task", side_effect=slow_sql):
            t0 = time.time()
            results = []
            async for r in run_parallel_agents(sub_tasks, query="hybrid test"):
                results.append(r)
            return time.time() - t0, results

    elapsed, results = asyncio.run(run())

    assert len(results) == 2
    # Parallel: elapsed should be close to max (~0.3s), NOT sum (~0.6s).
    # Allow 50% slack for scheduling overhead.
    assert elapsed < 0.5, f"Sub-tasks appear to be serial (elapsed={elapsed:.2f}s, expected ~0.3s)"
    assert all(r.get("result", {}).get("success") for r in results)


def test_hybrid_parallel_uses_concurrent_scheduling():
    """Verify that tasks are scheduled via asyncio.create_task (真正併發),
    not sequential await — checked by recording start timestamps."""
    from app.services.orchestrator import run_parallel_agents, SubTask

    start_times: list[float] = []
    lock = asyncio.Lock()

    async def record_start(task, sql_history=None, prebuilt_schema=None):
        async with lock:
            start_times.append(time.time())
        await asyncio.sleep(0.2)
        return {
            "task_id": task.id,
            "type": "sql",
            "result": {"success": True, "row_count": 0, "data": []},
            "sources": None,
            "error": None,
            "duration_ms": 200,
        }

    sub_tasks = [
        SubTask(id="sql_a", type="sql", sub_query="q1", label="A"),
        SubTask(id="sql_b", type="sql", sub_query="q2", label="B"),
        SubTask(id="sql_c", type="sql", sub_query="q3", label="C"),
    ]

    async def run():
        with patch("app.services.orchestrator._run_sql_task", side_effect=record_start):
            async for _ in run_parallel_agents(sub_tasks, query="t"):
                pass

    asyncio.run(run())

    assert len(start_times) == 3
    # All three should start within ~100ms of each other (truly concurrent).
    spread = max(start_times) - min(start_times)
    assert spread < 0.1, f"Tasks did not start concurrently (spread={spread:.3f}s)"


# --------------------------------------------------------------------------- #
# 2. Partial failure — one fails, others succeed
# --------------------------------------------------------------------------- #

def test_hybrid_partial_failure_returns_surviving_results():
    """When sub_a raises but sub_b succeeds, we still get sub_b's result."""
    from app.services.orchestrator import run_parallel_agents, SubTask

    async def flaky_sql(task, sql_history=None, prebuilt_schema=None):
        if task.id == "sql_fail":
            raise RuntimeError("DB connection lost")
        return {
            "task_id": task.id,
            "type": "sql",
            "result": {"success": True, "row_count": 5, "data": [{"y": 1}]},
            "sources": None,
            "error": None,
            "duration_ms": 50,
        }

    sub_tasks = [
        SubTask(id="sql_fail", type="sql", sub_query="q1", label="fails"),
        SubTask(id="sql_ok", type="sql", sub_query="q2", label="ok"),
    ]

    async def run():
        with patch("app.services.orchestrator._run_sql_task", side_effect=flaky_sql):
            results = []
            async for r in run_parallel_agents(sub_tasks, query="partial fail"):
                results.append(r)
            return results

    results = asyncio.run(run())

    assert len(results) == 2
    by_id = {r["task_id"]: r for r in results}
    assert by_id["sql_fail"].get("error")
    assert by_id["sql_ok"].get("result", {}).get("success") is True
    # failure should be suppressed (not bubbled as exception)
    assert by_id["sql_fail"].get("_suppressed") is True


def test_hybrid_all_failed_no_suppression():
    """If ALL sub-tasks fail, no _suppressed flag (so error is visible)."""
    from app.services.orchestrator import run_parallel_agents, SubTask

    async def always_fail(task, sql_history=None, prebuilt_schema=None):
        raise RuntimeError("kaboom")

    sub_tasks = [
        SubTask(id="a", type="sql", sub_query="q1", label="A"),
        SubTask(id="b", type="sql", sub_query="q2", label="B"),
    ]

    async def run():
        with patch("app.services.orchestrator._run_sql_task", side_effect=always_fail):
            results = []
            async for r in run_parallel_agents(sub_tasks, query="all fail"):
                results.append(r)
            return results

    results = asyncio.run(run())

    assert len(results) == 2
    assert all(r.get("error") for r in results)
    # When ALL fail, don't suppress — user needs to see the error.
    assert not any(r.get("_suppressed") for r in results)


# --------------------------------------------------------------------------- #
# 3. Hybrid disables self-reflection retry (max_iter=1)
# --------------------------------------------------------------------------- #

def test_maximo_nl2sql_hybrid_caps_iterations_to_one():
    """is_hybrid=True must force max_iter=1 (no self-reflection retry).

    Mocked generate_sql returns bad SQL → normally retries up to max_iter.
    With is_hybrid=True, must stop after 1 attempt.
    """
    from app.services.maximo_nl2sql import MaximoNL2SQL

    call_count = {"n": 0}

    async def fake_generate(question, feedback=None, history=None, prebuilt_schema=None):
        call_count["n"] += 1
        return {"sql": None, "error": "generation failed", "_model": "test", "_llm_ms": 10}

    async def run():
        svc = MaximoNL2SQL(db=MagicMock())
        svc.generate_sql = fake_generate
        svc._load_user_permissions = AsyncMock(return_value={"allow_freeform": True})

        # Fake redis so cache lookup fails fast and we fall into generation loop.
        class _FakeRedis:
            async def get(self, key):
                return None

            async def aclose(self):
                pass

        with patch("redis.asyncio.from_url", return_value=_FakeRedis()):
            return await svc.query("test question", mode="fast", is_hybrid=True)

    result = asyncio.run(run())

    assert call_count["n"] == 1, f"Expected 1 attempt under is_hybrid, got {call_count['n']}"
    assert result.get("success") is False


def test_maximo_nl2sql_accurate_mode_retries_normally():
    """Sanity check: accurate mode (no hybrid) does 1+cfg_max_retries attempts.

    Ensures our is_hybrid cap is strictly additive (i.e. we didn't accidentally
    truncate non-hybrid paths). Default config has 1 retry → 2 attempts total.
    """
    from app.services.maximo_nl2sql import MaximoNL2SQL

    call_count = {"n": 0}

    async def fake_generate(question, feedback=None, history=None, prebuilt_schema=None):
        call_count["n"] += 1
        return {"sql": None, "error": "generation failed", "_model": "test", "_llm_ms": 10}

    async def run():
        svc = MaximoNL2SQL(db=MagicMock())
        svc.generate_sql = fake_generate
        svc._load_user_permissions = AsyncMock(return_value={"allow_freeform": True})

        class _FakeRedis:
            async def get(self, key):
                return None

            async def aclose(self):
                pass

        with patch("redis.asyncio.from_url", return_value=_FakeRedis()):
            await svc.query("test question", mode="accurate", is_hybrid=False)

    asyncio.run(run())

    # accurate mode without is_hybrid: max_iter = 1 + cfg_max_retries (default 1) = 2 attempts.
    # Must be >= 2 to prove that is_hybrid cap specifically applies to hybrid only.
    assert call_count["n"] >= 2, (
        f"Expected >=2 attempts in accurate mode (retries enabled), got {call_count['n']}"
    )


# --------------------------------------------------------------------------- #
# 4. _run_sql_task passes is_hybrid=True to MaximoNL2SQL.query
# --------------------------------------------------------------------------- #

def test_run_sql_task_passes_is_hybrid_flag():
    """Ensure the orchestrator's SQL worker propagates is_hybrid=True."""
    from app.services.orchestrator import _run_sql_task, SubTask

    task = SubTask(id="x", type="sql", sub_query="q", label="L")
    captured = {}

    class FakeService:
        def __init__(self, db):
            self.db = db

        async def query(self, **kwargs):
            captured.update(kwargs)
            return {"success": True, "row_count": 0, "data": [], "columns": []}

    class FakeCtx:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, *a):
            return False

    def fake_ctx():
        return FakeCtx()

    async def run():
        with patch("app.services.maximo_nl2sql.MaximoNL2SQL", FakeService), \
             patch("app.db.session.get_db_context", fake_ctx):
            return await _run_sql_task(task)

    out = asyncio.run(run())

    assert captured.get("is_hybrid") is True
    assert captured.get("mode") == "fast"
    assert out.get("task_id") == "x"
