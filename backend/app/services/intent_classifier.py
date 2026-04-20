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
from app.services.circuit_breaker import LLM_BREAKER
# Note: DOMAIN_CONSTRAINT_PREFIX intentionally NOT applied here. Intent classifier
# outputs structured JSON only (no freeform text leak risk). Input-layer guardrail
# already catches off-topic before this runs. Keeping system prompt lean (~600 tokens).

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


# Compact few-shots: cover each intent + follow-up edge case
FEW_SHOT_EXAMPLES = """範例:
Q: 查詢 EMU801 故障歷程
A: {"intent":"structured","confidence":0.95,"entities":{"vehicle_code":"EMU801","query_type":"faults"},"reasoning":"指定車號與查詢類型"}

Q: 如何更換集電弓碳條？
A: {"intent":"knowledge","confidence":0.95,"entities":{"topic":"集電弓碳條更換"},"reasoning":"操作程序文件"}

Q: EMU900 的維修紀錄與對應的 SOP 處理程序
A: {"intent":"hybrid","confidence":0.92,"entities":{"vehicle_code":"EMU900"},"reasoning":"需結構化工單資料 + 文件庫 SOP 程序，才能完整回答"}

前一輪: structured (EMU3000 工單類型分布)
Q: 那同樣的 EMU900 呢？
A: {"intent":"structured","confidence":0.93,"entities":{"vehicle_code":"EMU900","query_type":"worktype_distribution"},"reasoning":"追問延續前題 structured 模式，僅換車號"}

Q: 工單
A: {"intent":"clarification","confidence":0.6,"entities":{},"reasoning":"查詢過於簡短","clarification_options":[{"label":"所有工單列表","query":"列出所有工單"},{"label":"核簽中的工單","query":"核簽中的工單有哪些"}]}"""

SYSTEM_PROMPT = f"""你是車輛維修系統的意圖分類器。請輸出純 JSON。

意圖類別：
- structured: 結構化資料（車輛/故障/檢修/成本/庫存/工單統計）
- knowledge: 文件知識（手冊/程序/規範/SOP）
- hybrid: **同時**需要結構化資料 + 文件知識（例：工單紀錄 + 對應 SOP 處理）。僅「多車號比較」或「多車型對比」仍屬 structured，不是 hybrid。
- clarification: 不明確，需反問

規則：
- **追問繼承**：使用者用「那/同樣地/再/也」等接續詞，intent 應繼承前一輪，除非明確轉向其他類別。
- **結構化比較**：「EMU3000 vs EMU900」「A 和 B 哪個多」這類比較屬 structured（同一 SQL 加 GROUP BY 或兩次查詢合併），不是 hybrid。
- hybrid 的判準是「**資料來源**不同」（SQL + 文件），不是「面向多」。
- 若對話脈絡已足夠，即使當前查詢短，也分類為 structured/knowledge/hybrid，而非 clarification。
- clarification_options 格式：[{{"label": "顯示文字", "query": "完整查詢"}}]。

實體：vehicle_code, vehicle_type, depot, fault_type, date_range, query_type。

{FEW_SHOT_EXAMPLES}

輸出 JSON 欄位：intent, confidence, entities, reasoning, clarification_options(僅 clarification 時)。"""


class IntentClassifierService:
    def __init__(self):
        settings = get_settings()
        self.provider = settings.intent_provider  # "ollama", "anthropic", "openai"
        self.model = settings.intent_llm_model

        if self.provider == "anthropic" and settings.anthropic_api_key:
            self.anthropic_key = settings.anthropic_api_key
            self.model = settings.intent_anthropic_model or "claude-haiku-4-5-20251001"
            self.client = None  # Use anthropic SDK directly
        elif self.provider == "openai" and settings.openai_api_key:
            self.client = AsyncOpenAI(api_key=settings.openai_api_key)
            self.model = settings.openai_model or "gpt-4o-mini"
            self.anthropic_key = None
        else:
            # Default: ollama
            self.client = AsyncOpenAI(api_key="ollama", base_url=settings.intent_llm_url)
            self.anthropic_key = None

    async def _call_anthropic(self, system: str, user_msg: str) -> str:
        """Call Anthropic API directly using httpx."""
        import httpx
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": 500,
                    "system": system,
                    "messages": [{"role": "user", "content": user_msg}],
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]

    async def classify(self, query: str, context: list = None) -> IntentResult:
        user_prompt = f"使用者查詢: {query}"
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
            # Pattern 5: Circuit Breaker — LLM 斷路保護
            if not LLM_BREAKER.is_available:
                log.warning("LLM circuit breaker OPEN — skipping to keyword fallback")
                raise RuntimeError("LLM circuit breaker is open")

            if self.anthropic_key:
                content = await self._call_anthropic(SYSTEM_PROMPT, user_prompt)
            else:
                # Add /no_think for ollama models
                ollama_prompt = f"/no_think\n{user_prompt}" if not self.anthropic_key else user_prompt
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": ollama_prompt}
                    ],
                    temperature=0,
                    max_tokens=500,
                    extra_body={"keep_alive": -1},
                )
                content = response.choices[0].message.content

            # Strip <think>...</think> tags from qwen/ollama models
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

            LLM_BREAKER.record_success()
            return IntentResult(
                intent=QueryIntent(result.get("intent", "clarification")),
                confidence=result.get("confidence", 0.5),
                entities=result.get("entities", {}),
                reasoning=result.get("reasoning", ""),
                clarification_options=result.get("clarification_options"),
            )

        except Exception as e:
            LLM_BREAKER.record_failure()
            log.warning("Intent classification error: %s", e)
            return IntentResult(
                intent=QueryIntent.CLARIFICATION,
                confidence=0.0,
                entities={},
                reasoning=f"分類錯誤: {str(e)}",
                clarification_options=[{"label": "請重新描述您的問題", "query": query}],
            )

    async def classify_with_fallback(self, query: str, context: list = None, timeout: float = 10.0) -> IntentResult:
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
_intent_classifier_config_hash = None


def _get_config_hash() -> str:
    """Get a hash of intent-related settings to detect changes."""
    settings = get_settings()
    return f"{settings.intent_provider}|{settings.intent_llm_url}|{settings.intent_llm_model}|{settings.anthropic_api_key[:8] if settings.anthropic_api_key else ''}|{settings.intent_anthropic_model}"


def get_intent_classifier() -> IntentClassifierService:
    global _intent_classifier, _intent_classifier_config_hash
    current_hash = _get_config_hash()
    if _intent_classifier is None or _intent_classifier_config_hash != current_hash:
        _intent_classifier = IntentClassifierService()
        _intent_classifier_config_hash = current_hash
        log.info("Intent classifier (re)initialized: %s", current_hash)
    return _intent_classifier
