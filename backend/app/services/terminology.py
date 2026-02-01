"""
台鐵 EMU800 電聯車維修專業術語同義詞表
用於 Query Expansion 提升搜尋準確度
"""

# 專業術語同義詞對照表
RAIL_TERMINOLOGY = {
    # 轉向架相關
    "轉向架": ["bogie", "台車", "走行部", "轉向架總成"],
    "牽引馬達": ["traction motor", "驅動馬達", "電動機", "牽引電機"],
    "空氣彈簧": ["air spring", "空簧", "皮囊", "氣墊"],
    "軔缸": ["brake cylinder", "煞車缸", "制動缸"],
    "碟煞": ["disc brake", "碟式煞車", "碟煞盤"],
    "軸箱": ["axle box", "軸承箱"],
    "車輪": ["wheel", "輪對", "車輪組"],
    "齒輪箱": ["gear box", "減速箱", "齒輪傳動箱"],
    
    # 連結器相關
    "連結器": ["coupler", "車鉤", "聯結器"],
    "密著式連結器": ["tight-lock coupler", "密連", "密著連結器"],
    "緩衝器": ["buffer", "緩衝橡皮", "緩衝裝置"],
    
    # 煞車系統
    "煞車": ["brake", "制動", "軔機"],
    "閘瓦": ["brake shoe", "煞車片", "制動塊"],
    "踏面清潔裝置": ["tread cleaner", "踏面清潔器"],
    
    # 空氣系統
    "空壓機": ["compressor", "壓縮機", "空氣壓縮機"],
    "司軔閥": ["driver's brake valve", "司機制動閥"],
    "MR": ["main reservoir", "主風缸", "總風缸"],
    "BP": ["brake pipe", "制動管", "列車管"],
    
    # 電氣系統
    "集電弓": ["pantograph", "受電弓"],
    "主變壓器": ["main transformer", "主變"],
    "輔助電源": ["auxiliary power supply", "SIV", "靜態變流器"],
    
    # 車體結構
    "車身": ["car body", "車體", "車殼"],
    "中心銷": ["center pin", "中心盤", "回轉盤"],
    "牽引桿": ["traction link", "牽引裝置"],
    
    # 維修動作
    "拆卸": ["disassemble", "拆除", "分解", "卸下"],
    "組裝": ["assemble", "安裝", "裝配", "鎖固"],
    "檢修": ["inspection", "維修", "檢查", "保養"],
    "量測": ["measure", "測量", "量測"],
    "更新": ["replace", "更換", "換新"],
    "敲診": ["tap test", "敲擊測試", "敲打檢查"],
    
    # 工具
    "套筒": ["socket", "套筒扳手"],
    "梅開板手": ["open-end wrench", "開口扳手"],
    "空氣槍": ["air gun", "氣動扳手", "風動扳手"],
    "扭力值": ["torque", "扭矩", "鎖緊力矩"],
}

# 反向索引：從同義詞找主詞
_REVERSE_INDEX = {}
for main_term, synonyms in RAIL_TERMINOLOGY.items():
    _REVERSE_INDEX[main_term.lower()] = main_term
    for syn in synonyms:
        _REVERSE_INDEX[syn.lower()] = main_term


def expand_query(query: str) -> str:
    """
    擴展查詢詞，加入同義詞以提升搜尋召回率
    
    Args:
        query: 原始查詢字串
        
    Returns:
        擴展後的查詢字串（包含同義詞）
    """
    expanded_terms = set()
    expanded_terms.add(query)
    
    # 檢查查詢中是否包含術語
    for term, synonyms in RAIL_TERMINOLOGY.items():
        if term in query:
            # 加入所有同義詞
            expanded_terms.update(synonyms)
        # 也檢查同義詞
        for syn in synonyms:
            if syn.lower() in query.lower():
                expanded_terms.add(term)
                expanded_terms.update(synonyms)
                break
    
    return " ".join(expanded_terms)


def normalize_term(term: str) -> str:
    """
    將術語標準化為主要術語
    
    Args:
        term: 輸入術語（可能是同義詞）
        
    Returns:
        標準化後的主要術語
    """
    return _REVERSE_INDEX.get(term.lower(), term)


def get_all_synonyms(term: str) -> list[str]:
    """
    獲取某術語的所有同義詞
    
    Args:
        term: 術語
        
    Returns:
        同義詞列表（包含主詞）
    """
    main_term = normalize_term(term)
    if main_term in RAIL_TERMINOLOGY:
        return [main_term] + RAIL_TERMINOLOGY[main_term]
    return [term]


def extract_components(text: str) -> list[str]:
    """
    從文本中提取零件名稱
    
    Args:
        text: 輸入文本
        
    Returns:
        識別到的零件名稱列表
    """
    components = []
    for term in RAIL_TERMINOLOGY.keys():
        if term in text:
            components.append(term)
    return components


def extract_actions(text: str) -> list[str]:
    """
    從文本中提取維修動作類型
    
    Args:
        text: 輸入文本
        
    Returns:
        識別到的動作類型列表
    """
    action_terms = ["拆卸", "組裝", "檢修", "量測", "更新", "敲診"]
    actions = []
    for action in action_terms:
        if action in text:
            actions.append(action)
    return actions
