"""
智慧文本分段策略
針對技術文件優化，保持完整的操作步驟
"""
import re
from typing import Optional

from app.services.terminology import extract_components, extract_actions


# 步驟邊界識別模式
STEP_PATTERNS = [
    r'^(\d+)[\.\)、]',           # 1. 或 1) 或 1、
    r'^[一二三四五六七八九十]+[、\.]',  # 一、二、
    r'^第[一二三四五六七八九十\d]+[章節步]',  # 第一章、第二節
    r'^[（\(][一二三四五六七八九十\d]+[）\)]',  # (一) 或 （1）
    r'^[A-Z][\.\)]',              # A. 或 A)
]

# 動作開頭模式
ACTION_PATTERNS = [
    r'^拆卸',
    r'^組裝',
    r'^檢查',
    r'^量測',
    r'^更新',
    r'^安裝',
    r'^取下',
    r'^吊',
    r'^鎖固',
    r'^以.*板手',
    r'^以.*套筒',
    r'^以.*起重機',
    r'^使用',
]


def is_step_boundary(line: str) -> bool:
    """
    判斷該行是否為步驟邊界
    
    Args:
        line: 文本行
        
    Returns:
        是否為步驟邊界
    """
    line = line.strip()
    if not line:
        return False
    
    # 檢查數字/字母編號
    for pattern in STEP_PATTERNS:
        if re.match(pattern, line):
            return True
    
    # 檢查動作開頭
    for pattern in ACTION_PATTERNS:
        if re.match(pattern, line):
            return True
    
    return False


def smart_chunk(
    text: str,
    chunk_size: int = 500,
    overlap: int = 100,
    min_chunk_size: int = 50,
) -> list[dict]:
    """
    智慧分段：保持完整的操作步驟
    
    Args:
        text: 輸入文本
        chunk_size: 目標區塊大小（字元數）
        overlap: 區塊間重疊字元數
        min_chunk_size: 最小區塊大小
        
    Returns:
        區塊列表，每個區塊包含 content 和 metadata
    """
    lines = text.split('\n')
    chunks = []
    current_chunk = []
    current_len = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 如果是新步驟邊界，且當前 chunk 夠大
        if is_step_boundary(line) and current_len > chunk_size:
            # 儲存當前 chunk
            chunk_text = '\n'.join(current_chunk)
            if len(chunk_text) >= min_chunk_size:
                chunks.append({
                    'content': chunk_text,
                    'metadata': _extract_chunk_metadata(chunk_text),
                })
            
            # 保留 overlap（最後幾行）
            overlap_lines = []
            overlap_len = 0
            for prev_line in reversed(current_chunk):
                if overlap_len + len(prev_line) > overlap:
                    break
                overlap_lines.insert(0, prev_line)
                overlap_len += len(prev_line)
            
            current_chunk = overlap_lines
            current_len = overlap_len
        
        current_chunk.append(line)
        current_len += len(line)
    
    # 處理最後一個 chunk
    if current_chunk:
        chunk_text = '\n'.join(current_chunk)
        if len(chunk_text) >= min_chunk_size:
            chunks.append({
                'content': chunk_text,
                'metadata': _extract_chunk_metadata(chunk_text),
            })
    
    return chunks


def _extract_chunk_metadata(text: str) -> dict:
    """
    從文本中提取 metadata
    
    Args:
        text: 區塊文本
        
    Returns:
        metadata 字典
    """
    components = extract_components(text)
    actions = extract_actions(text)
    
    # 判斷文檔類型
    doc_type = "general"
    if any(action in text for action in ["拆卸", "組裝", "安裝"]):
        doc_type = "procedure"
    elif any(word in text for word in ["檢查", "量測", "確認"]):
        doc_type = "checklist"
    elif any(word in text for word in ["規格", "尺寸", "標準", "mm", "Nm"]):
        doc_type = "specification"
    
    return {
        "doc_type": doc_type,
        "components": components,
        "actions": actions,
        "has_measurements": bool(re.search(r'\d+(\.\d+)?\s*(mm|cm|kg|Nm|bar)', text)),
    }


def chunk_document(
    text: str,
    filename: str,
    chunk_strategy: str = "smart",
    **kwargs,
) -> list[dict]:
    """
    根據策略分段文檔
    
    Args:
        text: 文檔文本
        filename: 檔案名稱
        chunk_strategy: 分段策略 ("smart", "paragraph", "fixed")
        **kwargs: 其他參數
        
    Returns:
        區塊列表
    """
    if chunk_strategy == "smart":
        return smart_chunk(text, **kwargs)
    elif chunk_strategy == "paragraph":
        return _paragraph_chunk(text, **kwargs)
    else:
        return _fixed_chunk(text, **kwargs)


def _paragraph_chunk(text: str, min_length: int = 30) -> list[dict]:
    """段落分段（原始方式）"""
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    return [
        {'content': p, 'metadata': _extract_chunk_metadata(p)}
        for p in paragraphs
        if len(p) >= min_length
    ]


def _fixed_chunk(text: str, chunk_size: int = 500, overlap: int = 100) -> list[dict]:
    """固定大小分段"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk_text = text[start:end]
        if chunk_text.strip():
            chunks.append({
                'content': chunk_text,
                'metadata': _extract_chunk_metadata(chunk_text),
            })
        start = end - overlap
    return chunks
