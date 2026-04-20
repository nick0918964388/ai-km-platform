"""
輸入層 Guardrail — Phase Security #1

功能：
1. Topic Classifier — 判斷 query 是否屬於領域範圍
2. Jailbreak Detector — 偵測 prompt injection 典型模式
3. Refusal template — 產生統一的婉拒回應

整合點：chat 主流程最前面，在 intent_classifier 之前跑。
Off-topic / jailbreak 直接返回婉拒，不進入 LLM pipeline。
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re
import logging

logger = logging.getLogger(__name__)


class GuardrailAction(Enum):
    ALLOW = "allow"
    REFUSE_OFF_TOPIC = "refuse_off_topic"
    REFUSE_JAILBREAK = "refuse_jailbreak"
    GREETING = "greeting"  # 短問候直接回應，不走 LLM


@dataclass
class GuardrailResult:
    action: GuardrailAction
    reason: str
    matched_patterns: list[str]  # for audit
    refusal_message: str | None = None


class InputGuardrail:
    """Lightweight input filter. Sync, <10ms per call."""

    # 領域關鍵字（中英混合，大小寫不敏感）
    DOMAIN_KEYWORDS = {
        "work_order", "workorder", "工單", "wo", "mxwo",
        "fault", "故障", "異常", "failure",
        "asset", "資產", "車輛", "車", "emu", "dr", "列車",
        "sop", "程序", "手冊", "文件", "操作規範",
        "maintenance", "維修", "檢修", "保養", "pm", "cm",
        "depot", "車廠", "車輛段", "機廠", "機務段",
        "parts", "零件", "材料",
        "technician", "技師", "人員",
        "schedule", "排程", "計畫",
    }

    # Jailbreak / prompt injection patterns（中英）
    JAILBREAK_PATTERNS = [
        # 經典指令覆寫（允許多個 qualifier，如 "ignore all previous instructions"）
        re.compile(r"ignore\s+(?:(?:all|previous|above|your|the|those|these)\s+)*(?:instruction|prompt|rule|system|directive)s?", re.IGNORECASE),
        re.compile(r"忽略\s*(?:之前|先前|上述|原本|系統)?\s*(?:的)?\s*(?:指令|指示|提示|規則|設定)"),
        re.compile(r"disregard\s+(?:(?:all|previous|above|your|the|those|these)\s+)*(?:instruction|prompt|rule|directive)s?", re.IGNORECASE),

        # 角色扮演劫持
        re.compile(r"you\s+are\s+now\s+(?:a\s+|an\s+)?", re.IGNORECASE),
        re.compile(r"act\s+as\s+(?:a\s+|an\s+)?(?:dan|jailbroken|unrestricted|developer|admin|root)", re.IGNORECASE),
        re.compile(r"pretend\s+(?:to\s+be|you\s+are)", re.IGNORECASE),
        re.compile(r"你\s*現在\s*(?:是|扮演)"),
        re.compile(r"假裝\s*(?:你是|成為|你)"),

        # DAN / 越獄模板
        re.compile(r"\bDAN\b"),
        re.compile(r"do\s+anything\s+now", re.IGNORECASE),
        re.compile(r"developer\s+mode", re.IGNORECASE),
        re.compile(r"沒有限制的\s*AI", re.IGNORECASE),
        re.compile(r"不受限制的\s*AI", re.IGNORECASE),

        # 系統資訊探測
        re.compile(r"(?:show|reveal|print|output|tell\s+me)\s+(?:your|the)\s+(?:system\s+prompt|instruction|rule)", re.IGNORECASE),
        re.compile(r"(?:顯示|列出|告訴我|輸出)\s*(?:(?:你的|系統|原本)\s*)*(?:指令|提示|prompt|規則)", re.IGNORECASE),
        re.compile(r"revealing\s+system\s+prompt", re.IGNORECASE),

        # Code execution 嘗試
        re.compile(r"(?:eval|exec|system|shell|bash|import\s+os|subprocess)\s*\(", re.IGNORECASE),
        re.compile(r"os\.system\s*\(", re.IGNORECASE),
        re.compile(r"執行\s*(?:程式碼|代碼|命令|指令)"),

        # SQL injection 模板（非 SQL 白名單內的）
        re.compile(r";\s*(?:drop|truncate|delete)\s+(?:table|database)", re.IGNORECASE),
        re.compile(r"--\s*(?:end|terminate|cancel)", re.IGNORECASE),
    ]

    # Off-topic 常見關鍵字（可能要擋）— 用於加強偵測
    OFF_TOPIC_STRONG_HINTS = [
        re.compile(r"天氣|氣溫|下雨|颱風|weather|forecast", re.IGNORECASE),
        re.compile(r"股票|股價|匯率|stock\s+price|crypto|bitcoin", re.IGNORECASE),
        re.compile(r"新聞|娛樂|電影|明星|偶像|celebrity", re.IGNORECASE),
        re.compile(r"烹飪|食譜|料理|recipe|cooking", re.IGNORECASE),
        re.compile(r"翻譯\s*(?:這|此|一|以下|成|到|為)|translate\s+(?:to|into|this)", re.IGNORECASE),
    ]

    # 短問候 / 寒暄 — 直接禮貌回應，不浪費 LLM
    # Rule: 必須「整句僅為問候」才觸發（有 domain keyword 就放行讓 intent classifier 處理）
    GREETING_PATTERNS = [
        re.compile(r"^(?:hi|hello|hey|yo|hola|howdy)[\s!?.,]*$", re.IGNORECASE),
        re.compile(r"^(?:你好|您好|嗨|哈囉|哈喽)[\s!?。，.,]*$"),
        re.compile(r"^(?:good\s+(?:morning|afternoon|evening|night))[\s!?.,]*$", re.IGNORECASE),
        re.compile(r"^(?:早|早安|午安|晚安|晚上好|早上好|中午好)[\s!?。，.,]*$"),
        re.compile(r"^(?:thanks?|thank\s+you|thx|ty)[\s!?.,]*$", re.IGNORECASE),
        re.compile(r"^(?:謝謝|感謝|感恩|多謝|thanks啦)(?:你|您|妳|大家|啦|囉|喔)?[\s!?。，.,]*$"),
        re.compile(r"^(?:bye|goodbye|see\s+ya|cya)[\s!?.,]*$", re.IGNORECASE),
        re.compile(r"^(?:再見|掰|掰掰|拜拜|下次見)[\s!?。，.,]*$"),
        re.compile(r"^(?:how\s+are\s+you|what'?s\s+up|how'?s\s+it\s+going)[\s!?.,]*$", re.IGNORECASE),
        re.compile(r"^(?:在嗎|在\s*?嗎|有人嗎|hello\?+)[\s!?。，.,]*$", re.IGNORECASE),
    ]

    GREETING_RESPONSE = (
        "你好！我是車輛維修知識助理 🚆\n"
        "可以協助您查詢：\n"
        "- 工單與維修紀錄\n"
        "- 故障代碼與排除\n"
        "- 資產與車輛資訊（如 EMU800、DR3100）\n"
        "- 維修程序（SOP）與手冊\n\n"
        "請問有什麼需要協助的？"
    )

    THANKS_RESPONSE = "不客氣！如果還有其他維修相關問題，隨時告訴我。"

    FAREWELL_RESPONSE = "再見！有維修相關問題歡迎隨時回來問我。"

    OFF_TOPIC_REFUSAL_MSG = (
        "抱歉，我是車輛維修知識助理，目前只能協助回答**工單、故障、資產、維修程序（SOP）、零件、人員**相關的問題。"
        "您的提問似乎不在我的專業領域內，建議您改問例如：\n"
        "- 「EMU800 最近的維修工單」\n"
        "- 「煞車系統異常的故障代碼」\n"
        "- 「B1234 故障對應的 SOP」"
    )

    JAILBREAK_REFUSAL_MSG = (
        "抱歉，我偵測到您的提問中包含試圖修改我設定的內容。"
        "我是專注於車輛維修知識的 AI 助理，無法執行超出這個範圍的指令。"
        "如果您有維修相關問題，我很樂意協助。"
    )

    def check(self, query: str) -> GuardrailResult:
        """唯一公開介面。回傳 GuardrailResult，呼叫端依 action 決定後續。"""
        query_stripped = (query or "").strip()

        if not query_stripped:
            return GuardrailResult(
                action=GuardrailAction.REFUSE_OFF_TOPIC,
                reason="empty_query",
                matched_patterns=[],
                refusal_message="請輸入您的問題。",
            )

        # 1. Jailbreak 偵測（優先級最高）
        jb_matches = []
        for pat in self.JAILBREAK_PATTERNS:
            m = pat.search(query_stripped)
            if m:
                jb_matches.append(m.group(0)[:50])

        if jb_matches:
            logger.warning(
                "[guardrail] jailbreak blocked: query=%r matches=%s",
                query_stripped[:100], jb_matches
            )
            return GuardrailResult(
                action=GuardrailAction.REFUSE_JAILBREAK,
                reason="jailbreak_pattern_matched",
                matched_patterns=jb_matches,
                refusal_message=self.JAILBREAK_REFUSAL_MSG,
            )

        # 2. Topic 判斷
        q_lower = query_stripped.lower()
        domain_hits = [kw for kw in self.DOMAIN_KEYWORDS if kw in q_lower]

        # 2a. 短問候偵測（整句僅為 greeting / thanks / farewell，且無 domain kw）
        # 優先於 off-topic 偵測，讓使用者打招呼時有禮貌回應不走 LLM。
        if not domain_hits:
            for pat in self.GREETING_PATTERNS:
                if pat.match(query_stripped):
                    matched = pat.pattern
                    # 依 pattern 類型選回應
                    if any(kw in matched.lower() for kw in ("thank", "謝", "感恩", "多謝")):
                        msg = self.THANKS_RESPONSE
                    elif any(kw in matched.lower() for kw in ("bye", "再見", "掰", "拜拜", "see ya", "cya")):
                        msg = self.FAREWELL_RESPONSE
                    else:
                        msg = self.GREETING_RESPONSE
                    logger.info("[guardrail] greeting handled: query=%r", query_stripped[:50])
                    return GuardrailResult(
                        action=GuardrailAction.GREETING,
                        reason="greeting_pattern_matched",
                        matched_patterns=[query_stripped[:30]],
                        refusal_message=msg,
                    )

        # 2b. 明顯 off-topic hints
        off_hints = []
        for pat in self.OFF_TOPIC_STRONG_HINTS:
            m = pat.search(query_stripped)
            if m:
                off_hints.append(m.group(0)[:30])

        # 決策邏輯：
        # - 有 off-topic strong hint 且沒有 domain keyword → refuse
        # - 其他情況 → allow（intent classifier 會進一步細判）
        if off_hints and not domain_hits:
            logger.info(
                "[guardrail] off-topic blocked: query=%r hints=%s",
                query_stripped[:100], off_hints
            )
            return GuardrailResult(
                action=GuardrailAction.REFUSE_OFF_TOPIC,
                reason="strong_off_topic_hint_no_domain_kw",
                matched_patterns=off_hints,
                refusal_message=self.OFF_TOPIC_REFUSAL_MSG,
            )

        return GuardrailResult(
            action=GuardrailAction.ALLOW,
            reason="passed",
            matched_patterns=domain_hits[:5],  # 前 5 個領域命中詞
        )


# 單例
_guardrail: InputGuardrail | None = None


def get_input_guardrail() -> InputGuardrail:
    global _guardrail
    if _guardrail is None:
        _guardrail = InputGuardrail()
    return _guardrail
