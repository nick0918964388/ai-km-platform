from typing import Final

# 中文大分類 → eq11 代碼列表（貨車雙碼）
VEHICLE_CATEGORY_CODES: Final[dict[str, list[str]]] = {
    "動力車": ["RSTL"],
    "客車":   ["RSTA"],
    "貨車":   ["RSTF", "RSTP"],
}

# eq11 代碼 → 中文大分類（反向，RSTF 和 RSTP 都映射到貨車）
CODE_TO_CATEGORY: Final[dict[str, str]] = {
    code: category
    for category, codes in VEHICLE_CATEGORY_CODES.items()
    for code in codes
}

# 車輛階層欄位對照（用於 Tool 5/6 的 group_by）
CATEGORY_LEVEL_FIELD: Final[dict[str, str]] = {
    "大分類": "eq11",
    "車種":   "eq3",
    "車型":   "eq4",
}


def to_codes(chinese: str) -> list[str]:
    """中文大分類轉 eq11 代碼列表。未知值回 [chinese] 原值（作 unknown fallback）。"""
    return VEHICLE_CATEGORY_CODES.get(chinese, [chinese])


def from_code(code: str) -> str:
    """eq11 代碼轉中文大分類。未知代碼回原值。"""
    return CODE_TO_CATEGORY.get(code, code)


def level_to_field(level: str) -> str:
    """階層中文 → 對應 mxasset 欄位名。未知階層 raise KeyError。"""
    return CATEGORY_LEVEL_FIELD[level]
