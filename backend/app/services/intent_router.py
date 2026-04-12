"""Intent Router — Detect whether a query is about documents (RAG) or data (SQL) or both."""

import re
import logging
from typing import Optional

log = logging.getLogger(__name__)

# Keywords that suggest Maximo data queries (SQL)
SQL_KEYWORDS = [
    # 工單相關
    "工單", "維修單", "定檢", "臨修", "核簽", "派工", "完工",
    "1A", "2A", "3A", "4A",
    # 故障相關
    "故障", "通報", "立案", "結案", "故障碼", "TCMS",
    # 資產相關
    "車輛", "車號", "資產", "EMU", "TEMU", "車組", "車型",
    # 統計相關
    "幾筆", "幾台", "幾張", "多少", "數量", "統計", "趨勢", "佔比", "排名",
    # 狀態查詢
    "狀態",
    # 表名直接引用
    "maximo", "mxwo", "mxsr", "mxasset",
]

# Keywords that suggest document/SOP queries (RAG)
RAG_KEYWORDS = [
    "SOP", "手冊", "規範", "文件", "步驟", "怎麼修", "如何", "維修程序",
    "操作手冊", "技術文件", "規格", "標準", "說明書",
    "什麼是", "解釋", "定義",
]

# Keywords that suggest both
HYBRID_KEYWORDS = [
    "相關文件", "參考", "SOP.*工單", "工單.*SOP",
    "故障.*處理方法", "維修.*步驟",
]


def detect_intent(query: str) -> dict:
    """
    Detect query intent: 'rag' (document search), 'sql' (data query), or 'hybrid' (both).
    Returns: {"intent": "rag"|"sql"|"hybrid", "confidence": float, "reason": str}
    """
    q = query.lower()

    def _match(kw: str, text: str) -> bool:
        k = kw.lower()
        # Short English keywords (like 1A, 2A) need word boundary to avoid false matches
        if len(k) <= 3 and k.isascii():
            return bool(re.search(r'\b' + re.escape(k) + r'\b', text, re.IGNORECASE))
        return k in text

    sql_score = sum(1 for kw in SQL_KEYWORDS if _match(kw, q))
    rag_score = sum(1 for kw in RAG_KEYWORDS if _match(kw, q))
    hybrid_match = any(re.search(pat, q, re.IGNORECASE) for pat in HYBRID_KEYWORDS)

    if hybrid_match:
        return {"intent": "hybrid", "confidence": 0.8, "reason": "問題同時涉及資料查詢與文件搜尋"}

    if sql_score > 0 and rag_score > 0:
        if sql_score > rag_score:
            return {"intent": "sql", "confidence": 0.7, "reason": f"資料查詢關鍵字較多（{sql_score} vs {rag_score}）"}
        elif rag_score > sql_score:
            return {"intent": "rag", "confidence": 0.7, "reason": f"文件搜尋關鍵字較多（{rag_score} vs {sql_score}）"}
        else:
            return {"intent": "hybrid", "confidence": 0.6, "reason": "資料與文件關鍵字相當"}

    if sql_score > 0:
        conf = min(0.95, 0.6 + sql_score * 0.1)
        return {"intent": "sql", "confidence": conf, "reason": "偵測到資料查詢關鍵字"}

    if rag_score > 0:
        conf = min(0.95, 0.6 + rag_score * 0.1)
        return {"intent": "rag", "confidence": conf, "reason": "偵測到文件搜尋關鍵字"}

    # Default to RAG (knowledge base search)
    return {"intent": "rag", "confidence": 0.5, "reason": "預設使用知識庫搜尋"}


def detect_ambiguity(query: str, history: list = None) -> Optional[dict]:
    """Detect if query is too ambiguous and needs clarification.
    Returns None if query is clear enough, or a dict with clarification options.

    Only triggers when:
    - No multi-turn history (context would disambiguate)
    - Query matches ambiguity rules
    """
    # Skip if multi-turn context available
    if history and len(history) > 0:
        return None

    q = query.strip()
    q_lower = q.lower()

    # Rule 1: Very short/vague query (< 4 chars)
    if len(q) < 4:
        return {
            "message": "請提供更具體的查詢條件：",
            "options": [
                {"label": "核簽中的工單有哪些？", "query": "核簽中的工單有哪些？"},
                {"label": "EMU900 的故障通報", "query": "EMU900 的故障通報"},
                {"label": "各車型資產數量統計", "query": "各車型的資產數量統計"},
            ]
        }

    # Rule 2: "工單" without specifying which type/table — BUT only if no status/type keywords
    if "工單" in q and not any(kw in q_lower for kw in [
        "maximo_mxwo", "pm_workorder", "cm_workorder", "mxwo",
        "核簽", "執行中", "完工", "初始", "退回",  # status keywords = clear intent
        "1a", "2a", "3a", "4a",  # PM work types
        "t1", "tr", "cm",  # CM work types
        "定檢", "臨修", "定期", "全部",
    ]):
        return {
            "message": "「工單」在系統中有多種來源，您要查詢哪一種？",
            "options": [
                {"label": "所有工單 (maximo_mxwo)", "query": f"maximo_mxwo {q}"},
                {"label": "定期檢修工單 (1A/2A/3A/4A)", "query": f"定期檢修工單 {q}"},
                {"label": "臨修工單 (T1/TR/CM)", "query": f"臨修工單 {q}"},
            ]
        }

    # Rule 3: Ambiguous "狀態" without subject
    if "狀態" in q and not any(kw in q for kw in ["工單", "故障", "車輛", "資產", "通報", "mxwo", "mxsr", "mxasset"]):
        return {
            "message": "您想查詢哪種資料的狀態？",
            "options": [
                {"label": "工單狀態", "query": f"工單{q}"},
                {"label": "故障通報狀態", "query": f"故障通報{q}"},
                {"label": "車輛資產狀態", "query": f"車輛資產{q}"},
            ]
        }

    # Rule 4: "最近" without time range and without specific count
    if "最近" in q and not any(kw in q for kw in [
        "天", "週", "月", "年", "筆", "個", "台",
        "10", "20", "30", "50", "100",
    ]):
        return {
            "message": "「最近」是指多長的時間範圍？",
            "options": [
                {"label": "最近一週", "query": q.replace("最近", "最近一週")},
                {"label": "最近一個月", "query": q.replace("最近", "最近一個月")},
                {"label": "最近 10 筆", "query": f"{q}，列出 10 筆"},
            ]
        }

    # Rule 5: Just a vehicle number without action
    if re.match(r'^(EMU|TEMU|ED|E)\d+$', q.strip(), re.IGNORECASE):
        vehicle = q.strip()
        return {
            "message": f"您想查詢 {vehicle} 的哪些資訊？",
            "options": [
                {"label": f"{vehicle} 的基本資料", "query": f"{vehicle} 車輛資產資料"},
                {"label": f"{vehicle} 的工單", "query": f"{vehicle} 的工單有哪些"},
                {"label": f"{vehicle} 的故障通報", "query": f"{vehicle} 的故障通報"},
            ]
        }

    return None  # Query is clear enough
