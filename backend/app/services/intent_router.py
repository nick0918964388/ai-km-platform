"""Intent Router — Detect whether a query is about documents (RAG) or data (SQL) or both."""

import re
import logging

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
    "狀態", "status",
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

    sql_score = sum(1 for kw in SQL_KEYWORDS if kw.lower() in q)
    rag_score = sum(1 for kw in RAG_KEYWORDS if kw.lower() in q)
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
