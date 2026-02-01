"""
Intent Classifier Service - Determine query type and route accordingly.
Uses LLM to classify user intent into: structured, knowledge, hybrid, or clarification.
"""

import os
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from openai import AsyncOpenAI


class QueryIntent(str, Enum):
    """Query intent types"""
    STRUCTURED = "structured"  # Query structured data (vehicles, faults, etc.)
    KNOWLEDGE = "knowledge"    # Query knowledge base (documents, manuals)
    HYBRID = "hybrid"          # Both structured and knowledge
    CLARIFICATION = "clarification"  # Need more info from user


@dataclass
class IntentResult:
    """Intent classification result"""
    intent: QueryIntent
    confidence: float
    entities: Dict[str, Any]  # Extracted entities (vehicle_code, date_range, etc.)
    reasoning: str
    suggested_queries: List[str] = None  # For clarification


# Few-shot examples for intent classification
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
結果: {"intent": "clarification", "confidence": 0.7, "entities": {}, "reasoning": "缺少具體查詢條件", "suggested_queries": ["請問您要查詢哪台車輛？", "請問要查詢多長時間內的故障？"]}

範例 5:
使用者: 新竹機務段所有車輛的維修成本統計
分析: 使用者要查詢特定機務段的成本數據，這是結構化資料查詢
結果: {"intent": "structured", "confidence": 0.9, "entities": {"depot": "新竹機務段", "query_type": "costs", "aggregation": "sum"}, "reasoning": "明確指定機務段和統計類型"}

範例 6:
使用者: 如何更換集電弓碳條？
分析: 使用者要查詢操作程序文件
結果: {"intent": "knowledge", "confidence": 0.95, "entities": {"topic": "集電弓碳條更換", "doc_type": "操作程序"}, "reasoning": "查詢操作步驟屬於文件知識"}
"""

SYSTEM_PROMPT = f"""你是一個車輛維修知識管理系統的意圖分類器。

你的任務是分析使用者的查詢，判斷其意圖類型：
1. **structured**: 查詢結構化資料（車輛資訊、故障記錄、檢修歷程、成本、零件庫存）
2. **knowledge**: 查詢知識庫文件（維修手冊、操作程序、技術規範）
3. **hybrid**: 同時需要結構化資料和知識文件
4. **clarification**: 查詢不明確，需要使用者提供更多資訊

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
- suggested_queries: (僅 clarification 時) 建議的澄清問題
"""


class IntentClassifierService:
    """Service for classifying user query intent"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o")
    
    async def classify(self, query: str, context: Optional[str] = None) -> IntentResult:
        """
        Classify user query intent.
        
        Args:
            query: User's natural language query
            context: Optional conversation context
            
        Returns:
            IntentResult with classification details
        """
        user_prompt = f"使用者查詢: {query}"
        if context:
            user_prompt = f"對話脈絡: {context}\n\n{user_prompt}"
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            return IntentResult(
                intent=QueryIntent(result.get("intent", "clarification")),
                confidence=result.get("confidence", 0.5),
                entities=result.get("entities", {}),
                reasoning=result.get("reasoning", ""),
                suggested_queries=result.get("suggested_queries")
            )
            
        except Exception as e:
            # Fallback to clarification on error
            return IntentResult(
                intent=QueryIntent.CLARIFICATION,
                confidence=0.0,
                entities={},
                reasoning=f"分類錯誤: {str(e)}",
                suggested_queries=["請重新描述您的問題"]
            )
    
    async def classify_batch(self, queries: List[str]) -> List[IntentResult]:
        """Classify multiple queries"""
        results = []
        for query in queries:
            result = await self.classify(query)
            results.append(result)
        return results


# Singleton instance
_intent_classifier = None


def get_intent_classifier() -> IntentClassifierService:
    """Get or create intent classifier instance"""
    global _intent_classifier
    if _intent_classifier is None:
        _intent_classifier = IntentClassifierService()
    return _intent_classifier
