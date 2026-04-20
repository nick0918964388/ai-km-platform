"""Cypher static security validator — safe-by-default for Text2Cypher output."""
import re
import logging
import unicodedata
from enum import Enum

log = logging.getLogger(__name__)

# 零寬/不可見字元：插在關鍵字中間可繞過 \b word boundary
_ZERO_WIDTH_TRANS = dict.fromkeys(
    [0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD], None
)


def _normalize(cypher: str) -> str:
    """NFKC 正規化 + 移除零寬/隱藏字元，防止 keyword 繞過。"""
    return unicodedata.normalize("NFKC", cypher).translate(_ZERO_WIDTH_TRANS)


def _strip_trailing_comments(cypher: str) -> str:
    """剝除尾端行註解與區塊註解，避免 append LIMIT 被吞掉。"""
    out = cypher.rstrip()
    changed = True
    while changed:
        changed = False
        # 尾端行註解 //...（到字串結尾）
        m = re.search(r"//[^\n]*\Z", out)
        if m:
            out = out[: m.start()].rstrip()
            changed = True
            continue
        # 尾端區塊註解 /* ... */
        if out.endswith("*/"):
            idx = out.rfind("/*")
            if idx != -1:
                out = out[:idx].rstrip()
                changed = True
    return out


class ValidationResult(Enum):
    OK = "ok"
    REJECTED = "rejected"


# ── 黑名單：寫入/管理類關鍵字（word boundary，case-insensitive） ──────────
_FORBIDDEN_KEYWORDS = [
    r"\bCREATE\b",
    r"\bMERGE\b",
    r"\bDELETE\b",
    r"\bDETACH\s+DELETE\b",
    r"\bREMOVE\b",
    r"\bSET\b",
    r"\bDROP\b",
    r"\bLOAD\s+CSV\b",
    r"\bFOREACH\b",
    r"\bUSING\s+PERIODIC\s+COMMIT\b",
]
_FORBIDDEN_RE = [re.compile(p, re.IGNORECASE) for p in _FORBIDDEN_KEYWORDS]

# ── 允許的 APOC 命名空間（唯讀） ─────────────────────────────────────────
_ALLOWED_APOC_PREFIXES = (
    "apoc.coll.",
    "apoc.text.",
    "apoc.convert.",
)

# ── 禁止的 procedure 命名空間 ────────────────────────────────────────────
_FORBIDDEN_PROC_PREFIXES = (
    "db.",
    "dbms.",
    "gds.write.",
    "gds.alpha.create.",
    "gds.graph.drop",
    "gds.graph.create",
    "apoc.periodic.",
    "apoc.export.",
    "apoc.import.",
    "apoc.create.",
    "apoc.merge.",
    "apoc.refactor.",
    "apoc.schema.",
    "apoc.trigger.",
    "apoc.cypher.run",
    "apoc.cypher.doit",
)

# CALL <procedure-name>( 取出 procedure 名稱
_CALL_PROC_RE = re.compile(
    r"\bCALL\s+([a-zA-Z_][\w\.]*)\s*\(",
    re.IGNORECASE,
)

# 路徑長度 *a..b 或 *..b 或 *a 或 *a..
_PATH_DEPTH_RE = re.compile(r"\*\s*(\d*)\s*(?:\.\.\s*(\d*))?")


def _strip_strings_and_comments(cypher: str) -> str:
    """移除 string literals、backtick identifiers 與註解，避免誤判關鍵字。"""
    # 先移除區塊註解 /* ... */
    out = re.sub(r"/\*.*?\*/", " ", cypher, flags=re.DOTALL)
    # 再移除行註解 //...
    out = re.sub(r"//[^\n]*", " ", out)

    # 逐字掃描移除字串（考慮轉義字元）
    result = []
    i = 0
    n = len(out)
    while i < n:
        ch = out[i]
        if ch in ('"', "'", "`"):
            quote = ch
            i += 1
            while i < n:
                if out[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if out[i] == quote:
                    i += 1
                    break
                i += 1
            result.append(" ")
        else:
            result.append(ch)
            i += 1
    return "".join(result)


class CypherValidator:
    """對 Cypher 做靜態安全驗證；唯讀查詢白名單，寧殺錯不放過。"""

    def __init__(self, max_limit: int = 50, max_path_depth: int = 5,
                 max_length: int = 5000, max_subquery_depth: int = 3):
        self.max_limit = max_limit
        self.max_path_depth = max_path_depth
        self.max_length = max_length
        self.max_subquery_depth = max_subquery_depth

    def validate(self, cypher: str) -> tuple[bool, list[str], str]:
        """回傳 (is_valid, reasons, rewritten_cypher)。rewritten 自動補 LIMIT。"""
        reasons: list[str] = []

        if cypher is None or not cypher.strip():
            reasons.append("empty query")
            log.warning(f"Cypher rejected: {reasons} | query: ")
            return False, reasons, ""

        if len(cypher) > self.max_length:
            reasons.append(f"query too long ({len(cypher)} > {self.max_length})")
            log.warning(f"Cypher rejected: {reasons} | query: {cypher[:200]}")
            return False, reasons, ""

        # 先做 unicode 正規化（防止 zero-width / soft-hyphen 繞過）
        cypher = _normalize(cypher)

        # 剝掉 string / comment 再做關鍵字偵測
        sanitized = _strip_strings_and_comments(cypher)

        # 黑名單關鍵字
        for pat in _FORBIDDEN_RE:
            m = pat.search(sanitized)
            if m:
                reasons.append(f"forbidden keyword: {m.group(0).strip()}")

        # Procedure 白名單檢查
        for m in _CALL_PROC_RE.finditer(sanitized):
            proc = m.group(1).lower()
            if proc.startswith("apoc."):
                if not proc.startswith(_ALLOWED_APOC_PREFIXES):
                    reasons.append(f"forbidden procedure: {proc}")
                continue
            if proc.startswith(_FORBIDDEN_PROC_PREFIXES):
                reasons.append(f"forbidden procedure: {proc}")
                continue
            # 非 apoc、非明確白名單的 procedure 一律拒絕
            reasons.append(f"non-whitelisted procedure: {proc}")

        # 獨立的 apoc.xxx 函式呼叫（不是 CALL，而是 RETURN apoc.xxx(...)）
        for m in re.finditer(r"\bapoc\.[\w\.]+\s*\(", sanitized, re.IGNORECASE):
            token = m.group(0).rstrip("(").strip().lower()
            if not token.startswith(_ALLOWED_APOC_PREFIXES):
                reasons.append(f"forbidden apoc function: {token}")

        # 路徑長度 *1..N 上限檢查
        for m in _PATH_DEPTH_RE.finditer(sanitized):
            lo, hi = m.group(1), m.group(2)
            upper = hi if hi else lo
            if upper and upper.isdigit():
                if int(upper) > self.max_path_depth:
                    reasons.append(
                        f"path depth {upper} exceeds max {self.max_path_depth}"
                    )

        # 子查詢深度：只計 CALL { / EXISTS { / COUNT { / COLLECT { 的巢狀，
        # 忽略 property map `{...}`
        max_depth_seen = self._max_subquery_depth(sanitized)
        if max_depth_seen > self.max_subquery_depth:
            reasons.append(
                f"subquery depth {max_depth_seen} exceeds max {self.max_subquery_depth}"
            )

        if reasons:
            # 去重
            seen = set()
            uniq = [r for r in reasons if not (r in seen or seen.add(r))]
            log.warning(f"Cypher rejected: {uniq} | query: {cypher[:200]}")
            return False, uniq, ""

        # 通過檢查；若缺 LIMIT 自動補上
        rewritten = self._ensure_limit(cypher, sanitized)
        return True, [], rewritten

    def _max_subquery_depth(self, sanitized: str) -> int:
        """只計 CALL/EXISTS/COUNT/COLLECT 子查詢的巢狀深度，跳過 property map。"""
        subquery_open = re.compile(
            r"\b(?:CALL|EXISTS|COUNT|COLLECT)\s*\{", re.IGNORECASE
        )
        # 蒐集每個 subquery-open 的 `{` 實際位置
        opens: set[int] = set()
        for m in subquery_open.finditer(sanitized):
            opens.add(m.end() - 1)

        depth = 0
        max_seen = 0
        stack: list[bool] = []  # True 代表該 `{` 是 subquery
        for i, ch in enumerate(sanitized):
            if ch == "{":
                is_sub = i in opens
                stack.append(is_sub)
                if is_sub:
                    depth += 1
                    max_seen = max(max_seen, depth)
            elif ch == "}":
                if stack:
                    is_sub = stack.pop()
                    if is_sub:
                        depth -= 1
        return max_seen

    def _ensure_limit(self, original: str, sanitized: str) -> str:
        """若查詢（主句層）沒有 LIMIT，附加 LIMIT；UNION 則每段都補。"""
        # 先剝尾端註解，避免 append 被吞掉
        trimmed = _strip_trailing_comments(original).rstrip(";").rstrip()

        # UNION：對每段都需確保有 LIMIT
        if re.search(r"\bUNION\b", sanitized, re.IGNORECASE):
            return self._ensure_limit_per_union(trimmed)

        # 主層 LIMIT 偵測
        if re.search(r"\bLIMIT\s+\d+\b", sanitized, re.IGNORECASE):
            return trimmed
        # 用換行分隔，避免若 trimmed 因任何原因仍以註解結尾
        return f"{trimmed}\nLIMIT {self.max_limit}"

    def _ensure_limit_per_union(self, trimmed: str) -> str:
        """對 UNION 每個 segment 分別檢查是否有 LIMIT，沒就補。"""
        # 以 `UNION [ALL]` 切段（保留分隔符）
        parts = re.split(r"(\bUNION\s+ALL\b|\bUNION\b)", trimmed, flags=re.IGNORECASE)
        # parts 樣式：[seg0, UNION, seg1, UNION, seg2 ...]
        rebuilt: list[str] = []
        for idx, chunk in enumerate(parts):
            if idx % 2 == 1:
                # 分隔符原樣保留
                rebuilt.append(chunk)
                continue
            seg = _strip_trailing_comments(chunk).rstrip()
            seg_sanitized = _strip_strings_and_comments(seg)
            if not re.search(r"\bLIMIT\s+\d+\b", seg_sanitized, re.IGNORECASE):
                seg = f"{seg}\nLIMIT {self.max_limit}"
            rebuilt.append(seg)
        # 使用空白串接（UNION 前後需 whitespace）
        out = ""
        for idx, piece in enumerate(rebuilt):
            if idx == 0:
                out = piece
            elif idx % 2 == 1:
                out = f"{out}\n{piece.strip()}\n"
            else:
                out = f"{out}{piece.lstrip()}"
        return out


# 預設單例（方便呼叫端直接用）
default_validator = CypherValidator()


def validate_cypher(cypher: str) -> tuple[bool, list[str], str]:
    """便利函式：用預設 validator 檢查 cypher。"""
    return default_validator.validate(cypher)
