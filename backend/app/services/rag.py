"""RAG service for chat and search with optimizations."""
import logging
import os
import re
from collections import defaultdict
from typing import Optional
from openai import OpenAI

from app.config import get_settings
from app.services import embedding as embed_service
from app.services import vector_store
from app.services import reranker as reranker_service
from app.services import cache as cache_service
from app.services import file_storage
from app.services.terminology import expand_query, RAIL_TERMINOLOGY
from app.models.schemas import SearchResult, ChunkType

logger = logging.getLogger(__name__)


# 優化後的 System Prompt
SYSTEM_PROMPT = """你是台鐵 EMU800 電聯車維修知識助手。你的任務是根據知識庫內容準確回答維修相關問題。

## 回答規則

1. **嚴格依據知識庫**：只根據提供的知識庫內容回答，不要編造或猜測資訊
2. **精確引用**：涉及工具規格（如扭力值、尺寸）時，必須精確引用原文數值
3. **保持步驟順序**：步驟型回答要按原文順序呈現，不要重新排列或省略步驟
4. **標註來源**：使用 [來源 N] 的格式標註引用來源
5. **承認不足**：如果知識庫資訊不完整或沒有相關內容，明確告知用戶

## 專業術語對照

請注意以下術語可能有不同的說法：
- 軔缸 = 煞車缸 = 制動缸 (brake cylinder)
- 空簧 = 空氣彈簧 = 皮囊 (air spring)
- 密封膜 = 皮囊
- 轉向架 = 台車 = 走行部 (bogie)
- 牽引馬達 = 驅動馬達 = 電動機 (traction motor)
- 套筒 = 套筒扳手 (socket)
- 梅開板手 = 開口扳手 (open-end wrench)
- MR = 主風缸 (main reservoir)
- BP = 制動管 (brake pipe)

## 回答格式

- 對於「如何」問題：按步驟列出，保持原始順序
- 對於「什麼規格」問題：精確引用數值和單位
- 對於「檢查項目」問題：列出所有檢查點
"""


def bm25_score(query: str, document: str) -> float:
    """
    簡化版 BM25 評分
    
    Args:
        query: 查詢字串
        document: 文檔內容
        
    Returns:
        BM25 分數
    """
    # 簡化的關鍵字匹配評分
    query_terms = set(query.lower().split())
    doc_lower = document.lower()
    
    score = 0.0
    for term in query_terms:
        # 計算詞頻
        count = doc_lower.count(term)
        if count > 0:
            # 使用對數縮放避免長文檔優勢過大
            score += (count / (count + 1.0)) * len(term)
    
    return score


def reciprocal_rank_fusion(
    vector_results: list[dict],
    keyword_results: list[dict],
    top_k: int = 5,
    k: int = 60,
) -> list[dict]:
    """
    RRF (Reciprocal Rank Fusion) 融合排序
    
    Args:
        vector_results: 向量搜尋結果
        keyword_results: 關鍵字搜尋結果
        top_k: 返回結果數量
        k: RRF 常數（通常為 60）
        
    Returns:
        融合後的結果列表
    """
    scores = defaultdict(float)
    results_map = {}
    
    # 處理向量搜尋結果
    for rank, result in enumerate(vector_results):
        doc_id = result.get("id", "")
        scores[doc_id] += 1.0 / (k + rank + 1)
        results_map[doc_id] = result
    
    # 處理關鍵字搜尋結果
    for rank, result in enumerate(keyword_results):
        doc_id = result.get("id", "")
        scores[doc_id] += 1.0 / (k + rank + 1)
        if doc_id not in results_map:
            results_map[doc_id] = result
    
    # 按融合分數排序
    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    
    return [results_map[doc_id] for doc_id in sorted_ids[:top_k]]


def hybrid_search(
    query: str,
    top_k: int = 5,
    use_expansion: bool = True,
    use_rerank: bool = True,
) -> list[dict]:
    """
    混合搜尋：結合向量搜尋和關鍵字搜尋，可選 Reranker

    Args:
        query: 查詢字串
        top_k: 返回結果數量
        use_expansion: 是否使用查詢擴展
        use_rerank: 是否使用 Cohere Reranker

    Returns:
        搜尋結果列表
    """
    settings = get_settings()

    # Query Expansion
    expanded_query = expand_query(query) if use_expansion else query

    # 1. 向量搜尋
    text_embedding = embed_service.embed_text(expanded_query)
    # Fetch more candidates if reranking is enabled
    fetch_k = top_k * 4 if use_rerank else top_k * 2
    vector_results = vector_store.search_text(text_embedding, top_k=fetch_k)

    # 2. 關鍵字搜尋（基於 BM25）
    all_chunks = vector_store.search_text(text_embedding, top_k=100)  # 獲取更多候選

    # 計算 BM25 分數
    for chunk in all_chunks:
        chunk["bm25_score"] = bm25_score(expanded_query, chunk.get("content", ""))

    # 按 BM25 排序
    keyword_results = sorted(all_chunks, key=lambda x: x["bm25_score"], reverse=True)[:fetch_k]

    # 3. RRF 融合
    # Get more candidates for reranking
    fusion_top_k = settings.rerank_top_n * 2 if use_rerank else top_k
    fused_results = reciprocal_rank_fusion(vector_results, keyword_results, fusion_top_k)

    # 4. Rerank (if enabled and available)
    if use_rerank and reranker_service.is_reranker_available():
        logger.debug(f"Reranking {len(fused_results)} results for query: {query[:50]}...")
        reranked = reranker_service.rerank(
            query=query,  # Use original query for reranking
            documents=fused_results,
            top_n=top_k,
            content_key="content",
        )
        return reranked

    return fused_results[:top_k]


def search(
    query: str,
    image_base64: Optional[str] = None,
    top_k: int = 5,
    use_hybrid: bool = True,
    use_rerank: bool = True,
    use_cache: bool = True,
) -> list[SearchResult]:
    """
    Search knowledge base with text and/or image query.

    Returns combined and ranked results from both text and image collections.
    """
    results = []

    # Check cache first (only for text-only queries)
    cache_hit = False
    if query and use_cache and not image_base64:
        cached = cache_service.get_cached_results(query, top_k)
        if cached:
            cache_hit = True
            logger.debug(f"Cache hit for query: {query[:50]}...")
            # Convert cached dicts back to SearchResult
            for r in cached:
                results.append(SearchResult(**r))
            return results

    # Text search
    if query:
        if use_hybrid:
            text_results = hybrid_search(query, top_k=top_k, use_rerank=use_rerank)
        else:
            # 原始向量搜尋
            text_embedding = embed_service.embed_text(query)
            text_results = vector_store.search_text(text_embedding, top_k=top_k)

        for r in text_results:
            # Check if original file exists for preview
            doc_id = r["document_id"]
            file_url = f"/api/kb/documents/{doc_id}/file" if file_storage.file_exists(doc_id) else None

            results.append(
                SearchResult(
                    id=r["id"],
                    content=r["content"],
                    doc_type=ChunkType.TEXT,
                    document_id=doc_id,
                    document_name=r["document_name"],
                    score=r.get("score", 0.0),
                    file_url=file_url,
                )
            )

    # Image search using Jina CLIP
    if query:
        try:
            # 擴展查詢用於圖片搜尋
            expanded_query = expand_query(query)
            clip_text_embedding = embed_service.embed_text_jina(expanded_query)
            image_results = vector_store.search_images(clip_text_embedding, top_k=top_k)

            for r in image_results:
                # Check if original file exists for preview
                doc_id = r["document_id"]
                file_url = f"/api/kb/documents/{doc_id}/file" if file_storage.file_exists(doc_id) else None

                results.append(
                    SearchResult(
                        id=r["id"],
                        content=r.get("description", "Image"),
                        doc_type=ChunkType.IMAGE,
                        document_id=doc_id,
                        document_name=r["document_name"],
                        score=r["score"],
                        image_base64=r.get("image_base64"),
                        file_url=file_url,
                    )
                )
        except Exception:
            pass

    # Image-to-image search
    if image_base64:
        try:
            image_embedding = embed_service.embed_image_from_base64(image_base64)
            image_results = vector_store.search_images(image_embedding, top_k=top_k)

            for r in image_results:
                if not any(res.id == r["id"] for res in results):
                    # Check if original file exists for preview
                    doc_id = r["document_id"]
                    file_url = f"/api/kb/documents/{doc_id}/file" if file_storage.file_exists(doc_id) else None

                    results.append(
                        SearchResult(
                            id=r["id"],
                            content=r.get("description", "Image"),
                            doc_type=ChunkType.IMAGE,
                            document_id=doc_id,
                            document_name=r["document_name"],
                            score=r["score"],
                            image_base64=r.get("image_base64"),
                            file_url=file_url,
                        )
                    )
        except Exception:
            pass

    # Sort by score and limit
    results.sort(key=lambda x: x.score, reverse=True)
    final_results = results[:top_k]

    # Cache results (only for text-only queries)
    if query and use_cache and not image_base64 and not cache_hit:
        # Convert to dicts for caching
        results_to_cache = [r.model_dump() for r in final_results]
        cache_service.set_cached_results(query, top_k, results_to_cache)

    return final_results


def chat(
    query: str,
    image_base64: Optional[str] = None,
    top_k: int = 5,
) -> tuple[str, list[SearchResult]]:
    """
    RAG chat: retrieve relevant documents and generate answer using GPT-4o.

    Returns: (answer, sources)
    """
    # Search for relevant documents
    sources = search(query, image_base64, top_k)

    if not sources:
        return "找不到相關的知識庫內容。請上傳相關文件後再試。", []

    # Build context from sources
    context_parts = []
    for i, source in enumerate(sources, 1):
        if source.doc_type == ChunkType.TEXT:
            context_parts.append(f"[來源 {i}] {source.document_name}:\n{source.content}")
        else:
            context_parts.append(f"[來源 {i}] {source.document_name}: [圖片]")

    context = "\n\n".join(context_parts)

    user_content = [
        {"type": "text", "text": f"知識庫內容:\n{context}\n\n用戶問題: {query}"}
    ]

    # Add user's image if provided
    if image_base64:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
        })

    # Add relevant images from sources
    for source in sources[:3]:
        if source.doc_type == ChunkType.IMAGE and source.image_base64:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{source.image_base64}"}
            })

    # Call GPT-4o
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return "錯誤：未設定 OpenAI API Key。請在環境變數中設定 OPENAI_API_KEY。", sources

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=1500,
            temperature=0.5,  # 降低溫度提高準確性
        )
        answer = response.choices[0].message.content
    except Exception as e:
        answer = f"生成回答時發生錯誤: {str(e)}"

    return answer, sources


def chat_stream(
    query: str,
    sources: list[SearchResult],
    image_base64: Optional[str] = None,
):
    """
    Streaming RAG chat: generate answer using GPT-4o with streaming.

    Yields: text chunks as they are generated
    """
    if not sources:
        yield "找不到相關的知識庫內容。請上傳相關文件後再試。"
        return

    # Build context from sources
    context_parts = []
    for i, source in enumerate(sources, 1):
        if source.doc_type == ChunkType.TEXT:
            context_parts.append(f"[來源 {i}] {source.document_name}:\n{source.content}")
        else:
            context_parts.append(f"[來源 {i}] {source.document_name}: [圖片]")

    context = "\n\n".join(context_parts)

    user_content = [
        {"type": "text", "text": f"知識庫內容:\n{context}\n\n用戶問題: {query}"}
    ]

    # Add user's image if provided
    if image_base64:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
        })

    # Add relevant images from sources
    for source in sources[:3]:
        if source.doc_type == ChunkType.IMAGE and source.image_base64:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{source.image_base64}"}
            })

    # Call GPT-4o with streaming
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        yield "錯誤：未設定 OpenAI API Key。請在環境變數中設定 OPENAI_API_KEY。"
        return

    try:
        client = OpenAI(api_key=api_key)
        stream = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=1500,
            temperature=0.5,
            stream=True,
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    except Exception as e:
        yield f"生成回答時發生錯誤: {str(e)}"


def chat_stream_with_metadata(
    query: str,
    sources: list[SearchResult],
    image_base64: Optional[str] = None,
):
    """
    Streaming RAG chat with metadata: generate answer using GPT-4o with streaming.

    Yields: dict with 'type' and 'data' keys
    - type='content': text chunk
    - type='usage': token usage info (at the end)
    """
    if not sources:
        yield {"type": "content", "data": "找不到相關的知識庫內容。請上傳相關文件後再試。"}
        return

    # Build context from sources
    context_parts = []
    for i, source in enumerate(sources, 1):
        if source.doc_type == ChunkType.TEXT:
            context_parts.append(f"[來源 {i}] {source.document_name}:\n{source.content}")
        else:
            context_parts.append(f"[來源 {i}] {source.document_name}: [圖片]")

    context = "\n\n".join(context_parts)

    user_content = [
        {"type": "text", "text": f"知識庫內容:\n{context}\n\n用戶問題: {query}"}
    ]

    # Add user's image if provided
    if image_base64:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
        })

    # Add relevant images from sources
    for source in sources[:3]:
        if source.doc_type == ChunkType.IMAGE and source.image_base64:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{source.image_base64}"}
            })

    # Call GPT-4o with streaming
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        yield {"type": "content", "data": "錯誤：未設定 OpenAI API Key。請在環境變數中設定 OPENAI_API_KEY。"}
        return

    try:
        client = OpenAI(api_key=api_key)
        stream = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=1500,
            temperature=0.5,
            stream=True,
            stream_options={"include_usage": True},
        )

        usage_info = None
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield {"type": "content", "data": chunk.choices[0].delta.content}
            # Capture usage from the final chunk
            if chunk.usage:
                usage_info = {
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                    "total_tokens": chunk.usage.total_tokens,
                }

        # Yield usage info at the end
        if usage_info:
            yield {"type": "usage", "data": usage_info}

    except Exception as e:
        yield {"type": "content", "data": f"生成回答時發生錯誤: {str(e)}"}
