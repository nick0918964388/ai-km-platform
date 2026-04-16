"""
Pattern 8: Result Budgeting — 結果行數管理
控制 per-query 和 per-conversation 的結果行數，避免 prompt 爆炸和前端效能問題。
"""

import logging

log = logging.getLogger(__name__)

# 預設限制
DEFAULT_PER_QUERY = 50
DEFAULT_PER_CONVERSATION = 200
OVERFLOW_NOTICE = "（結果已截斷，共 {total} 筆，顯示前 {shown} 筆）"


class ResultBudget:
    """追蹤單次對話中的累計結果行數。"""

    def __init__(self, per_query: int = DEFAULT_PER_QUERY,
                 per_conversation: int = DEFAULT_PER_CONVERSATION):
        self.per_query = per_query
        self.per_conversation = per_conversation
        self._used = 0

    @property
    def remaining(self) -> int:
        return max(0, self.per_conversation - self._used)

    def allocate(self, rows: list, total_count: int = None) -> dict:
        """分配行數預算，回傳截斷後的結果和 metadata。

        Returns:
            {
                "data": list,       # 截斷後的資料
                "shown": int,       # 實際顯示筆數
                "total": int,       # 原始總筆數
                "truncated": bool,  # 是否被截斷
                "notice": str|None, # 截斷提示（如有）
            }
        """
        if total_count is None:
            total_count = len(rows)

        # 取 per_query 和 remaining conversation budget 的較小值
        limit = min(self.per_query, self.remaining)
        truncated = len(rows) > limit
        result_rows = rows[:limit]
        self._used += len(result_rows)

        notice = None
        if truncated:
            notice = OVERFLOW_NOTICE.format(total=total_count, shown=len(result_rows))
            log.info("Result budget: truncated %d → %d rows (conversation used: %d/%d)",
                     len(rows), len(result_rows), self._used, self.per_conversation)

        return {
            "data": result_rows,
            "shown": len(result_rows),
            "total": total_count,
            "truncated": truncated,
            "notice": notice,
        }

    def get_status(self) -> dict:
        return {
            "used": self._used,
            "per_query": self.per_query,
            "per_conversation": self.per_conversation,
            "remaining": self.remaining,
        }
