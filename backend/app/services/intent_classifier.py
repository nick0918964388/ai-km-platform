"""Intent Classifier Service — LLM-based query intent classification with Ollama."""

import asyncio
import json
import re
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from openai import AsyncOpenAI

from app.config import get_settings

log = logging.getLogger(__name__)


class QueryIntent(str, Enum):
    STRUCTURED = "structured"
    KNOWLEDGE = "knowledge"
    HYBRID = "hybrid"
    CLARIFICATION = "clarification"


@dataclass
class IntentResult:
    intent: QueryIntent
    confidence: float
    entities: Dict[str, Any]
    reasoning: str
    clarification_options: List[Dict[str, str]] = None


FEW_SHOT_EXAMPLES = """
範例 1:
使用者: 查詢 EMU801 故障歷程
分析: 使用者要查詢特定車輛的故障記錄，這是結構化資料查詢
結果: {"intent": "structured", "confidence": 0.95, "entities": {"vehicle_code": "EMU801", "query_type": "faults"}, "reasoning": "明確指定車輛編號和查詢類型"}

範例 2:
使用者: 轉向架維修標準流程是什麼？
分析: 使用者要查詢維修流程文件，這是知識庫查詢
結果: {"intent": "knowledge", "confidence": 0.9, "entities": {"topic": "轉向架維修", "doc_type": "標準流程"}, "reasoning": "查詢維修流程屬於文件知識"}

範例 3:
使用者: EMU801 煞車系統為什麼常故障？有什麼維修建議？
分析: 使用者既要查詢故障數據，也需要維修建議文件
結果: {"intent": "hybrid", "confidence": 0.85, "entities": {"vehicle_code": "EMU801", "system": "煞車系統"}, "reasoning": "需要結合故障數據和維修文件"}

範例 4:
使用者: 最近的故障情況
分析: 使用者沒有指定車輛或時間範圍，需要澄清
結果: {"intent": "clarification", "confidence": 0.7, "entities": {}, "reasoning": "缺少具體查詢條件，需要知道車輛和時間範圍", "clarification_options": [{"label": "最近一週全車隊故障", "query": "最近一週全部車輛的故障通報"}, {"label": "指定車輛故障歷程", "query": "EMU801 的故障歷程"}]}

範例 5:
使用者: 新竹機務段所有車輛的維修成本統計
分析: 使用者要查詢特定機務段的成本數據，這是結構化資料查詢
結果: {"intent": "structured", "confidence": 0.9, "entities": {"depot": "新竹機務段", "query_type": "costs", "aggregation": "sum"}, "reasoning": "明確指定機務段和統計類型"}

範例 6:
使用者: 如何更換集電弓碳條？
分析: 使用者要查詢操作程序文件
結果: {"intent": "knowledge", "confidence": 0.95, "entities": {"topic": "集電弓碳條更換", "doc_type": "操作程序"}, "reasoning": "查詢操作步驟屬於文件知識"}

範例 7:
使用者: 工單
分析: 使用者只說了「工單」，不確定要查哪種工單或什麼操作
結果: {"intent": "clarification", "confidence": 0.6, "entities": {}, "reasoning": "查詢過於簡短，需要更多資訊", "clarification_options": [{"label": "所有工單列表", "query": "列出所有工單"}, {"label": "核簽中的工單", "query": "核簽中的工單有哪些"}, {"label": "最近的臨修工單", "query": "最近一週的臨修工單"}]}

範例 8:
使用者: 車輛狀況
分析: 使用者想了解車輛狀況但沒有指定車號或查詢類型
結果: {"intent": "clarification", "confidence": 0.65, "entities": {}, "reasoning": "未指定車輛編號或具體要查詢的面向", "clarification_options": [{"label": "全車隊資產總覽", "query": "全部車輛資產統計"}, {"label": "特定車號故障紀錄", "query": "EMU900 的故障紀錄"}, {"label": "車輛維修成本排名", "query": "各車輛維修成本排名"}]}
"""

SYSTEM_PROMPT = f"""你是一個車輛維修知識管理系統的意圖分類器。

你的任務是分析使用者的查詢，判斷其意圖類型：
1. **structured**: 查詢結構化資料（車輛資訊、故障記錄、檢修歷程、成本、零件庫存）
2. **knowledge**: 查詢知識庫文件（維修手冊、操作程序、技術規範）
3. **hybrid**: 同時需要結構化資料和知識文件
4. **clarification**: 查詢不明確，需要使用者提供更多資訊

重要規則：
- 如果對話脈絡已提供足夠資訊（例如使用者在追問上一個問題的細節），即使當前查詢較短或模糊，也應該判斷為 structured/knowledge/hybrid，而非 clarification。
- clarification_options 必須是 {{"label": "顯示文字", "query": "完整查詢"}} 格式的陣列。

可識別的實體：
- vehicle_code: 車輛編號 (如 EMU801, TEMU2001)
- vehicle_type: 車型 (如 EMU800系列)
- depot: 機務段 (如 新竹機務段、台中機務段)
- fault_type: 故障類型 (轉向架、煞車系統、電氣系統、空調系統、門機系統、推進系統、集電弓)
- date_range: 時間範圍
- query_type: 查詢類型 (faults, maintenance, costs, usage, inventory)

{FEW_SHOT_EXAMPLES}

請以 JSON 格式回覆，包含：
- intent: 意圖類型
- confidence: 信心度 (0-1)
- entities: 識別的實體
- reasoning: 判斷理由
- clarification_options: (僅 clarification 時) 建議選項，格式為 [{{"label": "顯示文字", "query": "完整查詢"}}]
"""


class IntentClassifierService:
    def __init__(self):
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.ollama_chat_api_key, base_url=settings.ollama_chat_url)
        self.model = settings.ollama_light_model

    async def classify(self, query: str, context: list = None) -> IntentResult:
        user_prompt = f"/no_think\n使用者查詢: {query}"
        if context:
            conv_parts = []
            for m in context[-3:]:
                role = m.get("role", "user")
                content = m.get("content", "")[:100]
                part = f"{role}: {content}"
                if m.get("intent") == "sql" and m.get("sql"):
                    part += f" [SQL查詢: {m['sql'][:80]}]"
                conv_parts.append(part)
            if conv_parts:
                user_prompt = f"對話脈絡:\n" + "\n".join(conv_parts) + f"\n\n{user_prompt}"

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0,
                max_tokens=500,
            )

            content = response.choices[0].message.content

            # Strip <think>...</think> tags from qwen models
            content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()

            # Strip markdown code fences if present
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]

            # Extract outermost JSON object by bracket matching
            start = content.find('{')
            if start == -1:
                raise ValueError(f"No JSON found in response: {content[:200]}")
            depth, end = 0, start
            for i in range(start, len(content)):
                if content[i] == '{':
                    depth += 1
                elif content[i] == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            result = json.loads(content[start:end])

            return IntentResult(
                intent=QueryIntent(result.get("intent", "clarification")),
                confidence=result.get("confidence", 0.5),
                entities=result.get("entities", {}),
                reasoning=result.get("reasoning", ""),
                clarification_options=result.get("clarification_options"),
            )

        except Exception as e:
            log.warning("Intent classification error: %s", e)
            return IntentResult(
                intent=QueryIntent.CLARIFICATION,
                confidence=0.0,
                entities={},
                reasoning=f"分類錯誤: {str(e)}",
                clarification_options=[{"label": "請重新描述您的問題", "query": query}],
            )

    async def classify_with_fallback(self, query: str, context: list = None, timeout: float = 8.0) -> IntentResult:
        try:
            return await asyncio.wait_for(self.classify(query, context), timeout=timeout)
        except (asyncio.TimeoutError, Exception) as e:
            log.warning("LLM intent classification failed (%s: %s), falling back to keywords", type(e).__name__, e)
            from app.services.intent_router import detect_intent
            kw = detect_intent(query, context=context)
            intent_map = {"sql": QueryIntent.STRUCTURED, "rag": QueryIntent.KNOWLEDGE, "hybrid": QueryIntent.HYBRID}
            return IntentResult(
                intent=intent_map.get(kw["intent"], QueryIntent.KNOWLEDGE),
                confidence=kw["confidence"],
                entities={},
                reasoning=f"[fallback] {kw['reason']}",
            )


_intent_classifier = None


def get_intent_classifier() -> IntentClassifierService:
    global _intent_classifier
    if _intent_classifier is None:
        _intent_classifier = IntentClassifierService()
    return _intent_classifier
