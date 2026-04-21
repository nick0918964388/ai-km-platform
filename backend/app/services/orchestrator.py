"""Multi-Agent Orchestrator for Phase 2.5 Agentic RAG.
Decomposes complex queries into parallel sub-tasks, executes concurrently, synthesizes results.
"""

import asyncio
import json
import re
import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import Optional, AsyncGenerator

from openai import AsyncOpenAI

from app.config import get_settings

log = logging.getLogger(__name__)

MAX_DELEGATION_DEPTH = 2
WORKER_TIMEOUT_SECONDS = 60
WORKER_HEARTBEAT_SECONDS = 30

BLOCKED_OPERATIONS = frozenset({
    "delegate",
    "clarification",
    "maximo_write",
})


@dataclass
class SubTask:
    id: str
    type: str  # "sql" or "rag"
    sub_query: str
    label: str  # Chinese display label


@dataclass
class DecompositionResult:
    sub_tasks: list[SubTask]
    synthesis_instruction: str


DECOMPOSE_SYSTEM_PROMPT = """你是車輛維修知識管理系統的查詢分解器。

你的任務是將複雜查詢拆解為可平行執行的子任務。

## 可用資料來源

### 結構化資料（SQL 查詢）
- maximo_mxasset: 車輛主檔（車號、車型、機廠、狀態）
- maximo_mxwo: 工單（定檢/臨修工單、工時、費用）
- maximo_mxsr: 服務請求/故障通報
- maximo_fault_reports: 故障報告
- maximo_cm_workorders: 臨修工單
- maximo_pm_workorders: 定期檢修工單

### 知識庫（RAG 文件檢索）
- 維修手冊、操作程序、技術規範
- SOP 文件、訓練教材

## 輸出格式（JSON）
{
  "sub_tasks": [
    {"id": "sql_faults", "type": "sql", "sub_query": "子問題", "label": "查詢故障紀錄"},
    {"id": "rag_docs", "type": "rag", "sub_query": "子問題", "label": "搜尋知識庫"}
  ],
  "synthesis_instruction": "如何綜合這些結果的指引"
}

## 規則
- type 只能是 "sql" 或 "rag"
- id 必須唯一
- 每個子任務的 sub_query 應該是獨立可執行的完整問句
- 如果查詢只需要單一來源，仍然回傳一個子任務

## 範例

使用者: EMU801 煞車系統故障次數以及維修 SOP
回覆:
{
  "sub_tasks": [
    {"id": "sql_faults", "type": "sql", "sub_query": "EMU801 煞車系統故障次數統計", "label": "查詢故障統計"},
    {"id": "rag_sop", "type": "rag", "sub_query": "煞車系統維修 SOP 標準作業程序", "label": "搜尋維修 SOP"}
  ],
  "synthesis_instruction": "結合故障統計數據與 SOP 文件，分析故障頻率是否與維修規範有關"
}

使用者: 最近一個月各車型工單數量比較
回覆:
{
  "sub_tasks": [
    {"id": "sql_workorders", "type": "sql", "sub_query": "最近一個月各車型工單數量統計", "label": "查詢工單統計"}
  ],
  "synthesis_instruction": "呈現各車型工單數量比較分析"
}

使用者: 轉向架檢修流程和注意事項
回覆:
{
  "sub_tasks": [
    {"id": "rag_procedure", "type": "rag", "sub_query": "轉向架檢修流程和注意事項", "label": "搜尋檢修文件"}
  ],
  "synthesis_instruction": "整理轉向架檢修流程重點"
}
"""

SYNTHESIS_SYSTEM_PROMPT = """你是車輛維修分析師，根據以下多來源資料進行綜合分析。

規則：
- 使用繁體中文回答
- 引用資料時標註來源（SQL 查詢結果 / 知識庫文件）
- 如果某個來源查無結果或失敗，說明並基於可用資料回答
- 回答要有結構，使用 markdown 格式
"""


def _strip_think_tags(text: str) -> str:
    return re.sub(r'<think>[\s\S]*?</think>', '', text).strip()


def _extract_json(text: str) -> dict:
    text = _strip_think_tags(text)
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    start = text.find('{')
    if start == -1:
        raise ValueError(f"No JSON found: {text[:200]}")
    depth, end = 0, start
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    return json.loads(text[start:end])


def _heuristic_decompose(query: str) -> DecompositionResult:
    tasks = []
    q_lower = query.lower()

    if any(kw in q_lower for kw in ["故障", "通報"]):
        tasks.append(SubTask(id="sql_faults", type="sql", sub_query=query, label="查詢故障紀錄"))
    if any(kw in q_lower for kw in ["工單", "維修", "檢修"]):
        tasks.append(SubTask(id="sql_workorders", type="sql", sub_query=query, label="查詢工單紀錄"))
    if any(kw in q_lower for kw in ["車輛", "資產"]):
        tasks.append(SubTask(id="sql_assets", type="sql", sub_query=query, label="查詢車輛資產"))

    tasks.append(SubTask(id="rag_docs", type="rag", sub_query=query, label="搜尋知識庫"))

    if len(tasks) == 1:
        # Only RAG, no SQL keywords matched
        return DecompositionResult(sub_tasks=tasks, synthesis_instruction="根據知識庫文件回答")

    return DecompositionResult(
        sub_tasks=tasks,
        synthesis_instruction="綜合結構化資料與知識庫文件進行分析"
    )


def _get_llm_client():
    """依 llm_provider 回傳 (AsyncOpenAI client, light_model_name)。"""
    settings = get_settings()
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        # Anthropic 不支援 OpenAI-compatible，decompose/synthesis 用 ollama light model
        return AsyncOpenAI(api_key=settings.ollama_chat_api_key, base_url=settings.ollama_chat_url), settings.ollama_light_model
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return AsyncOpenAI(api_key=settings.openai_api_key), settings.openai_model or "gpt-4o"
    return AsyncOpenAI(api_key=settings.ollama_chat_api_key, base_url=settings.ollama_chat_url), settings.ollama_light_model


def _get_chat_client():
    """依 llm_provider 回傳 (AsyncOpenAI client, chat_model_name)。"""
    settings = get_settings()
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        return AsyncOpenAI(api_key=settings.ollama_chat_api_key, base_url=settings.ollama_chat_url), settings.ollama_chat_model
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return AsyncOpenAI(api_key=settings.openai_api_key), settings.openai_model or "gpt-4o"
    return AsyncOpenAI(api_key=settings.ollama_chat_api_key, base_url=settings.ollama_chat_url), settings.ollama_chat_model


async def decompose_query(query: str, context: list = None) -> DecompositionResult:
    client, model = _get_llm_client()

    user_prompt = f"/no_think\n使用者查詢: {query}"
    if context:
        conv_parts = [f"{m.get('role', 'user')}: {m.get('content', '')[:100]}" for m in context[-3:]]
        if conv_parts:
            user_prompt = f"對話脈絡:\n" + "\n".join(conv_parts) + f"\n\n{user_prompt}"

    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": DECOMPOSE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
            ),
            timeout=5.0,
        )
        content = response.choices[0].message.content
        result = _extract_json(content)

        sub_tasks = [
            SubTask(
                id=t["id"],
                type=t["type"],
                sub_query=t["sub_query"],
                label=t["label"],
            )
            for t in result.get("sub_tasks", [])
        ]
        if not sub_tasks:
            raise ValueError("LLM 回傳空子任務列表")

        return DecompositionResult(
            sub_tasks=sub_tasks,
            synthesis_instruction=result.get("synthesis_instruction", "綜合分析"),
        )

    except Exception as e:
        log.warning("Query decomposition failed, using heuristic: %s", e)
        return _heuristic_decompose(query)


def _adapt_tool_result_to_nl2sql_shape(router_result: dict) -> dict:
    """Convert MaximoQueryRouter response dict to the shape MaximoNL2SQL.query() returns.

    Router result keys: query_id, route_path, tool_name, tool_input, rows, row_count,
                        chart_hint, elapsed_ms, debug
    NL2SQL result keys: success, sql, explanation, data, columns, row_count,
                        execution_ms, model, route_path, ...
    """
    rows = router_result.get("rows") or []
    row_count = router_result.get("row_count", 0)
    tool_name = router_result.get("tool_name") or "tool"
    tool_input = router_result.get("tool_input") or {}
    elapsed_ms = router_result.get("elapsed_ms", 0)

    # Infer columns from first row keys; empty list when no rows
    columns = list(rows[0].keys()) if rows else []

    explanation = f"已使用 {tool_name} 工具（參數: {tool_input}）"

    return {
        "success": True,
        "sql": None,
        "explanation": explanation,
        "data": rows,
        "columns": columns,
        "row_count": row_count,
        "execution_ms": elapsed_ms,
        "model": "tool",
        "llm_ms": None,
        "verify_ms": None,
        "iterations": 0,
        "confidence": 0.9,
        "verification_history": [],
        "mode": "tool",
        "cached": False,
        "query_plan": None,
        "chart_suggestion": router_result.get("chart_hint"),
        "summary": None,
        "column_labels": {},
        "suggestions": [],
        "route_path": "tool",
        "tool_name": tool_name,
    }


async def _run_sql_task(task: SubTask, sql_history: list = None,
                        prebuilt_schema: tuple = None) -> dict:
    """Pattern 7: SQL Worker 只拿 schema + SQL history，不帶 RAG/KB context.

    Batch 2-A：傳 is_hybrid=True 禁用每個 sub-SQL 的 self-reflection 重試，
    因為 hybrid 路徑已有 LLM synthesis 可以補救失敗 sub-task，避免重試複合延遲。
    每個 sub-task 使用獨立的 DB session（來自 pool），可與其他 sub-task 平行執行。

    Fix A: Try the 012 tool router first. If it succeeds (route_path=tool), adapt the
    result to the NL2SQL shape and return. Otherwise fall through to MaximoNL2SQL.
    """
    t0 = time.time()
    try:
        # Fix A: Tool router first — covers the 6 specific Maximo tools.
        # build_router() uses module-level singletons (lazy-init, idempotent).
        from app.services.maximo_tools.router_factory import build_router
        from app.services.maximo_tools.base import UserContext

        async def _nl2sql_fallback(query: str, user_ctx: UserContext, query_id) -> dict:
            """Fallback fn signature required by MaximoQueryRouter."""
            from app.db.session import get_db_context
            async with get_db_context() as db:
                from app.services.maximo_nl2sql import MaximoNL2SQL
                service = MaximoNL2SQL(db)
                nl2sql_result = await service.query(
                    question=query,
                    mode="fast",
                    conversation_history=sql_history,
                    prebuilt_schema=prebuilt_schema,
                    is_hybrid=True,
                )
            rows = nl2sql_result.get("data", [])
            return {
                "rows": rows,
                "row_count": nl2sql_result.get("row_count", 0),
                "chart_hint": nl2sql_result.get("chart_suggestion"),
                "debug": {
                    "sql": nl2sql_result.get("sql"),
                    "explanation": nl2sql_result.get("explanation"),
                    "nl2sql_result": nl2sql_result,
                },
            }

        # Anonymous user context for orchestrator path — tool router uses it for
        # row-level filtering; admin gives broadest access.
        user_ctx = UserContext(user_id="orchestrator", role="admin")
        router = build_router(fallback_fn=_nl2sql_fallback)
        router_result = await router.route(task.sub_query, user_ctx)

        route_path = router_result.get("route_path")

        if route_path == "tool":
            # Tool hit — adapt to NL2SQL shape
            result = _adapt_tool_result_to_nl2sql_shape(router_result)
        elif route_path == "fallback":
            # NL2SQL fallback ran inside _nl2sql_fallback; unpack the nl2sql_result
            nl2sql_result = router_result.get("debug", {}).get("nl2sql_result")
            if nl2sql_result:
                result = nl2sql_result
            else:
                # Reconstruct from router fallback shape
                rows = router_result.get("rows", [])
                result = {
                    "success": bool(rows is not None),
                    "sql": router_result.get("debug", {}).get("sql"),
                    "explanation": router_result.get("debug", {}).get("explanation"),
                    "data": rows,
                    "columns": list(rows[0].keys()) if rows else [],
                    "row_count": router_result.get("row_count", 0),
                    "execution_ms": router_result.get("elapsed_ms", 0),
                    "route_path": "fallback",
                }
        else:
            # error path — return empty result with error flag
            result = {
                "success": False,
                "error": router_result.get("debug", {}).get("error", {}).get("message", "查詢失敗"),
                "sql": None,
                "data": [],
                "columns": [],
                "row_count": 0,
                "route_path": route_path,
            }

        return {
            "task_id": task.id,
            "type": "sql",
            "result": result,
            "sources": None,
            "error": None,
            "duration_ms": int((time.time() - t0) * 1000),
        }
    except Exception as e:
        log.error("SQL sub-task %s failed: %s", task.id, e)
        return {
            "task_id": task.id,
            "type": "sql",
            "result": None,
            "sources": None,
            "error": str(e),
            "duration_ms": int((time.time() - t0) * 1000),
        }


async def _run_rag_task(task: SubTask, top_k: int = 5,
                        rag_context: list = None) -> dict:
    """Pattern 7: RAG Worker 只拿最近 2 輪對話 context，不帶 SQL schema/history。"""
    t0 = time.time()
    try:
        from app.services import rag

        # 如果有對話 context，把它加入搜尋查詢以改善向量搜尋品質
        search_query = task.sub_query
        if rag_context:
            recent = [f"{m.get('role','user')}: {m.get('content','')[:80]}" for m in rag_context[-2:]]
            search_query = f"對話背景：{'；'.join(recent)}。\n問題：{task.sub_query}"

        sources = await asyncio.to_thread(rag.search, query=search_query, top_k=top_k)
        return {
            "task_id": task.id,
            "type": "rag",
            "result": None,
            "sources": sources,  # list[SearchResult]
            "error": None,
            "duration_ms": int((time.time() - t0) * 1000),
        }
    except Exception as e:
        log.error("RAG sub-task %s failed: %s", task.id, e)
        return {
            "task_id": task.id,
            "type": "rag",
            "result": None,
            "sources": None,
            "error": str(e),
            "duration_ms": int((time.time() - t0) * 1000),
        }


async def run_parallel_agents(
    sub_tasks: list[SubTask],
    query: str,
    request_top_k: int = 5,
    sql_history: list = None,
    conversation_context: list = None,
    depth: int = 0,
) -> AsyncGenerator[dict, None]:
    """Run sub-tasks in parallel.

    Batch 2-A：平行化實作 — 所有 sub-task 透過 asyncio.create_task 同時啟動，
    然後用 asyncio.as_completed 以「完成順序」收集結果並即時 yield（支援 SSE
    streaming UX）。一個 sub-task 失敗不影響其他（每個 worker 內部 try/except
    捕獲，最終結果格式統一）。

    Pattern 4: Withholding — suppress individual task failures silently.
    Pattern 7: Context Stripping — SQL 只拿 sql_history，RAG 只拿最近對話。
    """
    if depth >= MAX_DELEGATION_DEPTH:
        raise ValueError(f"Maximum delegation depth ({MAX_DELEGATION_DEPTH}) exceeded")

    rag_context = None
    if conversation_context:
        rag_context = [
            {"role": m.get("role", "user"), "content": m.get("content", "")[:150]}
            for m in conversation_context[-2:]
            if m.get("intent") != "sql"
        ]

    async def _worker(task: SubTask, trace_id: str) -> dict:
        """單一 sub-task executor，所有錯誤都轉成統一 dict 回傳（不 raise）。"""
        t0 = time.time()
        try:
            if task.type == "sql":
                result = await asyncio.wait_for(
                    _run_sql_task(task, sql_history),
                    timeout=WORKER_TIMEOUT_SECONDS,
                )
            else:
                result = await asyncio.wait_for(
                    _run_rag_task(task, request_top_k, rag_context=rag_context),
                    timeout=WORKER_TIMEOUT_SECONDS,
                )
            result["task_trace_id"] = trace_id
            log.info(
                "Worker %s (%s) completed in %dms",
                trace_id, task.id, int((time.time() - t0) * 1000),
            )
            return result
        except asyncio.TimeoutError:
            log.error("Worker %s (%s) timed out after %ds", trace_id, task.id, WORKER_TIMEOUT_SECONDS)
            return {
                "task_id": task.id,
                "type": task.type,
                "task_trace_id": trace_id,
                "status": "timeout",
                "result": None,
                "sources": None,
                "error": f"Worker timed out after {WORKER_TIMEOUT_SECONDS}s",
                "duration_ms": int((time.time() - t0) * 1000),
            }
        except Exception as e:
            log.error("Worker %s (%s) failed: %s", trace_id, task.id, e)
            return {
                "task_id": task.id,
                "type": task.type,
                "task_trace_id": trace_id,
                "result": None,
                "sources": None,
                "error": str(e),
                "duration_ms": int((time.time() - t0) * 1000),
            }

    # Launch all sub-tasks in parallel (真正並行啟動).
    tasks = [
        asyncio.create_task(_worker(t, uuid.uuid4().hex[:12]))
        for t in sub_tasks
    ]

    # Collect results as they complete (for SSE streaming UX).
    # asyncio.as_completed yields futures in completion order.
    all_results: list[dict] = []
    for fut in asyncio.as_completed(tasks):
        try:
            result = await fut
        except Exception as e:
            # _worker 保證不 raise，這裡是防禦性 fallback。
            log.error("Worker future raised unexpectedly: %s", e)
            result = {
                "task_id": "_unknown",
                "type": "error",
                "result": None,
                "sources": None,
                "error": str(e),
                "duration_ms": 0,
            }
        all_results.append(result)

    all_failed = all(r.get("error") for r in all_results)
    all_timeout = all(r.get("status") == "timeout" for r in all_results)

    if all_timeout:
        yield {
            "task_id": "_orchestrator",
            "type": "error",
            "result": None,
            "sources": None,
            "error": f"All {len(all_results)} workers timed out after {WORKER_TIMEOUT_SECONDS}s",
        }
        return

    for result in all_results:
        if result.get("error") and not all_failed:
            log.warning("Sub-task %s [%s] failed (suppressed): %s", result["task_id"], result.get("task_trace_id", "?"), result["error"])
            result["_suppressed"] = True
        yield result


def _build_synthesis_context(results: list[dict]) -> str:
    parts = []
    for r in results:
        if r.get("error"):
            if r.get("_suppressed"):
                continue
            parts.append(f"【{r['task_id']}】查詢失敗: {r['error']}")
            continue

        if r["type"] == "sql" and r.get("result"):
            res = r["result"]
            row_count = res.get("row_count", 0)
            data = res.get("data", [])
            sql = res.get("sql", "")
            # Pattern 7: 精簡 synthesis context — 只帶 3 筆樣本 + 摘要
            summary = f"【{r['task_id']}】SQL 查詢結果（{row_count} 筆）\nSQL: {sql}\n"
            if res.get("summary"):
                summary += f"摘要：{res['summary']}\n"
            if data:
                for row in data[:3]:
                    summary += str(row) + "\n"
                if row_count > 3:
                    summary += f"...（共 {row_count} 筆）\n"
            parts.append(summary)

        elif r["type"] == "rag" and r.get("sources"):
            snippets = []
            for s in r["sources"][:5]:
                name = s.document_name if hasattr(s, 'document_name') else s.get("document_name", "未知")
                content = s.content[:300] if hasattr(s, 'content') else s.get("content", "")[:300]
                snippets.append(f"- {name}: {content}")
            parts.append(f"【{r['task_id']}】知識庫文件:\n" + "\n".join(snippets))

    return "\n\n".join(parts) if parts else "所有子任務均無結果"


async def synthesize_results(
    query: str,
    results: list[dict],
    instruction: str,
) -> AsyncGenerator[dict, None]:
    client, model = _get_chat_client()

    context_text = _build_synthesis_context(results)
    user_prompt = f"""/no_think
## 使用者問題
{query}

## 綜合指引
{instruction}

## 多來源資料
{context_text}

請根據以上資料進行綜合分析回答。"""

    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                content = _strip_think_tags(content)
                if content:
                    yield {"type": "content", "data": content}
    except Exception as e:
        log.error("Synthesis streaming failed: %s", e)
        yield {"type": "content", "data": f"綜合分析失敗: {e}"}
