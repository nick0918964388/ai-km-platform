"""Multi-Agent Orchestrator for Phase 2.5 Agentic RAG.
Decomposes complex queries into parallel sub-tasks, executes concurrently, synthesizes results.
"""

import asyncio
import json
import re
import time
import logging
from dataclasses import dataclass, field
from typing import Optional, AsyncGenerator

from openai import AsyncOpenAI

from app.config import get_settings

log = logging.getLogger(__name__)


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


async def decompose_query(query: str, context: list = None) -> DecompositionResult:
    settings = get_settings()
    client = AsyncOpenAI(api_key="ollama", base_url=settings.ollama_chat_url)

    user_prompt = f"/no_think\n使用者查詢: {query}"
    if context:
        conv_parts = [f"{m.get('role', 'user')}: {m.get('content', '')[:100]}" for m in context[-3:]]
        if conv_parts:
            user_prompt = f"對話脈絡:\n" + "\n".join(conv_parts) + f"\n\n{user_prompt}"

    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=settings.ollama_light_model,
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


async def _run_sql_task(task: SubTask, sql_history: list = None) -> dict:
    t0 = time.time()
    try:
        from app.services.maximo_nl2sql import MaximoNL2SQL
        from app.db.session import get_db_context

        async with get_db_context() as db:
            service = MaximoNL2SQL(db)
            result = await service.query(
                question=task.sub_query,
                mode="fast",
                conversation_history=sql_history,
            )
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


async def _run_rag_task(task: SubTask, top_k: int = 5) -> dict:
    t0 = time.time()
    try:
        from app.services import rag

        sources = await asyncio.to_thread(rag.search, query=task.sub_query, top_k=top_k)
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
) -> AsyncGenerator[dict, None]:
    queue: asyncio.Queue[dict] = asyncio.Queue()

    async def _worker(task: SubTask):
        if task.type == "sql":
            result = await _run_sql_task(task, sql_history)
        else:
            result = await _run_rag_task(task, request_top_k)
        await queue.put(result)

    tasks = [asyncio.create_task(_worker(t)) for t in sub_tasks]

    for _ in range(len(tasks)):
        result = await queue.get()
        yield result

    await asyncio.gather(*tasks, return_exceptions=True)


def _build_synthesis_context(results: list[dict]) -> str:
    parts = []
    for r in results:
        if r.get("error"):
            parts.append(f"【{r['task_id']}】查詢失敗: {r['error']}")
            continue

        if r["type"] == "sql" and r.get("result"):
            res = r["result"]
            row_count = res.get("row_count", 0)
            data = res.get("data", [])
            sql = res.get("sql", "")
            summary = f"【{r['task_id']}】SQL 查詢結果（{row_count} 筆）\nSQL: {sql}\n"
            if data:
                for row in data[:5]:
                    summary += str(row) + "\n"
                if row_count > 5:
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
    settings = get_settings()
    client = AsyncOpenAI(api_key="ollama", base_url=settings.ollama_chat_url)

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
            model=settings.ollama_chat_model,
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
