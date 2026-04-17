"""Explore Mode — Agent with LLM function calling for multi-step reasoning."""
import asyncio
import json
import time
import logging
from typing import AsyncGenerator

from openai import AsyncOpenAI
from app.config import get_settings, get_active_llm_info
from app.db.session import get_db_context

log = logging.getLogger(__name__)

MAX_ITERATIONS = 8
AGENT_TIMEOUT = 120

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "sql_query",
            "description": "查詢 Maximo 結構化資料。可查詢：工單(maximo_cm_workorders/pm_workorders)、故障通報(maximo_fault_reports/maximo_mxsr)、資產(maximo_assets/maximo_mxasset)。用自然語言描述查詢需求。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "用自然語言描述要查詢的資料，例如「EMU3000 本週故障通報按狀態統計」",
                    }
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kb_search",
            "description": "搜尋知識庫文件（SOP、維修手冊、作業程序等）。用關鍵字或問題描述搜尋。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜尋關鍵字或問題，例如「EMU900 轉向架檢修程序」",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "回傳結果數量，預設 5",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
]

AGENT_SYSTEM_PROMPT = """你是台鐵車輛維修知識管理系統的深度探索助手。

你可以使用以下工具來回答使用者的問題：
- sql_query: 查詢結構化資料（工單、故障、資產統計）
- kb_search: 搜尋知識庫文件（SOP、維修手冊）

## 工作方式
1. 分析使用者問題，決定需要哪些資訊
2. 呼叫適當的工具取得資料
3. 分析結果，如果需要更多資訊，繼續呼叫工具
4. 用取得的資料綜合回答使用者

## 注意事項
- 每次只呼叫 1 個工具
- 看到結果後再決定下一步
- 不要猜測資料，一定要查詢確認
- 最多呼叫 8 次工具
- 回答時引用資料來源"""


def _get_client() -> tuple[AsyncOpenAI, str]:
    settings = get_settings()
    llm_url, llm_model = get_active_llm_info()
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        client = AsyncOpenAI(base_url=llm_url, api_key=settings.anthropic_api_key)
    elif settings.llm_provider == "openai" and settings.openai_api_key:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
    else:
        client = AsyncOpenAI(base_url=llm_url, api_key=settings.ollama_chat_api_key)
    return client, llm_model


async def execute_tool(name: str, args: dict) -> dict:
    try:
        if name == "sql_query":
            from app.services.maximo_nl2sql import MaximoNL2SQL
            async with get_db_context() as db:
                service = MaximoNL2SQL(db)
                result = await asyncio.wait_for(
                    service.query(args["question"], mode="accurate"),
                    timeout=30.0,
                )
            if result.get("success"):
                data = result.get("data", [])
                return {
                    "success": True,
                    "row_count": len(data),
                    "columns": result.get("columns", []),
                    "data": data[:20],
                    "sql": result.get("sql", ""),
                    "explanation": result.get("explanation", ""),
                }
            else:
                return {"success": False, "error": result.get("error", "查詢失敗")}

        elif name == "kb_search":
            from app.services import rag
            sources = rag.search(query=args["query"], top_k=args.get("top_k", 5))
            return {
                "results": [
                    {
                        "title": s.document_name,
                        "content": s.content[:500],
                        "score": round(s.score, 3) if s.score else 0,
                    }
                    for s in sources[:5]
                ],
                "count": len(sources),
            }

        else:
            return {"error": f"Unknown tool: {name}"}

    except asyncio.TimeoutError:
        return {"error": f"Tool {name} timed out"}
    except Exception as e:
        return {"error": f"Tool {name} failed: {str(e)[:200]}"}


async def run_agent_loop(
    query: str,
    context: list = None,
    memory_context: str = None,
) -> AsyncGenerator[dict, None]:
    """Run the agent loop, yielding SSE events."""
    client, llm_model = _get_client()

    system_prompt = AGENT_SYSTEM_PROMPT
    if memory_context:
        system_prompt = f"{system_prompt}\n\n{memory_context}"

    messages = [{"role": "system", "content": system_prompt}]

    if context:
        for m in context[-6:]:
            messages.append({"role": m.get("role", "user"), "content": m.get("content", "")[:300]})

    messages.append({"role": "user", "content": query})

    tools_used = []
    start_time = time.time()
    iteration = 0

    for iteration in range(MAX_ITERATIONS):
        if time.time() - start_time > AGENT_TIMEOUT:
            yield {"type": "agent_thinking", "data": {"text": f"已達到時間限制（{AGENT_TIMEOUT}s），開始總結。"}}
            break

        try:
            call_kwargs = {
                "model": llm_model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 2000,
            }

            if iteration < MAX_ITERATIONS - 1:
                call_kwargs["tools"] = TOOLS
                call_kwargs["tool_choice"] = "auto"

            response = await asyncio.wait_for(
                client.chat.completions.create(**call_kwargs),
                timeout=30.0,
            )

            choice = response.choices[0]

            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    tool_name = tc.function.name
                    try:
                        tool_args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        tool_args = {"query": tc.function.arguments}

                    yield {"type": "agent_tool_call", "data": {"tool": tool_name, "args": tool_args, "iteration": iteration + 1}}

                    tool_result = await execute_tool(tool_name, tool_args)
                    tools_used.append(tool_name)

                    result_str = json.dumps(tool_result, ensure_ascii=False, default=str)
                    if len(result_str) > 2000:
                        result_str = result_str[:2000] + "...(truncated)"

                    yield {"type": "agent_tool_result", "data": {"tool": tool_name, "result": tool_result, "iteration": iteration + 1}}

                    messages.append(choice.message.model_dump())
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_str,
                    })

                continue

            if choice.message.content:
                yield {"type": "content", "data": choice.message.content}

            break

        except asyncio.TimeoutError:
            yield {"type": "agent_thinking", "data": {"text": f"第 {iteration + 1} 步逾時，繼續嘗試。"}}
            continue
        except Exception as e:
            log.error("Agent loop error at iteration %d: %s", iteration + 1, e)
            yield {"type": "agent_thinking", "data": {"text": f"發生錯誤：{str(e)[:100]}"}}
            break

    yield {"type": "agent_done", "data": {
        "iterations": iteration + 1,
        "tools_used": tools_used,
        "duration_ms": int((time.time() - start_time) * 1000),
    }}
