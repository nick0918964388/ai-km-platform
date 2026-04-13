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
from app.services.reranker_factory import get_reranker_factory
from app.services import cache as cache_service
from app.services import file_storage
from app.services.terminology import expand_query, RAIL_TERMINOLOGY
from app.models.schemas import SearchResult, RerankerMetadata, ChunkType

logger = logging.getLogger(__name__)


def _get_llm_client(light: bool = False):
    """Return (client, model) based on configured LLM provider."""
    settings = get_settings()
    if settings.llm_provider == "ollama":
        client = OpenAI(base_url=settings.ollama_chat_url, api_key="ollama")
        model = settings.ollama_light_model if light else settings.ollama_chat_model
    else:
        api_key = os.environ.get("OPENAI_API_KEY", settings.openai_api_key)
        if not api_key:
            return None, None
        client = OpenAI(api_key=api_key)
        model = "gpt-4o-mini" if light else settings.openai_model
    return client, model


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
) -> tuple[list[dict], Optional[dict]]:
    """
    混合搜尋：結合向量搜尋和關鍵字搜尋，可選 Reranker

    Args:
        query: 查詢字串
        top_k: 返回結果數量
        use_expansion: 是否使用查詢擴展
        use_rerank: 是否使用 Reranker (via RerankerFactory)

    Returns:
        Tuple of (搜尋結果列表, reranker_info dict or None)
    """
    settings = get_settings()
    reranker_info = None

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

    # 4. Rerank using RerankerFactory (if enabled)
    if use_rerank:
        factory = get_reranker_factory()
        if factory.is_available():
            logger.debug(f"Reranking {len(fused_results)} results for query: {query[:50]}...")
            result = factory.rerank(
                query=query,  # Use original query for reranking
                documents=fused_results,
                top_n=top_k,
                content_key="content",
            )
            reranker_info = {
                "provider": result.provider,
                "latency_ms": result.latency_ms,
                "fallback_used": result.fallback_used,
                "original_ranks": result.original_ranks,
            }
            return result.documents, reranker_info

    return fused_results[:top_k], None


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
    reranker_info = None
    if query:
        if use_hybrid:
            text_results, reranker_info = hybrid_search(query, top_k=top_k, use_rerank=use_rerank)
        else:
            # 原始向量搜尋
            text_embedding = embed_service.embed_text(query)
            text_results = vector_store.search_text(text_embedding, top_k=top_k)

        for idx, r in enumerate(text_results):
            # Check if original file exists for preview
            doc_id = r["document_id"]
            file_url = f"/api/kb/documents/{doc_id}/file" if file_storage.file_exists(doc_id) else None

            # Build reranker metadata if available
            reranker_metadata = None
            if reranker_info:
                original_rank = reranker_info["original_ranks"][idx] if idx < len(reranker_info.get("original_ranks", [])) else None
                reranker_metadata = RerankerMetadata(
                    provider=reranker_info["provider"],
                    latency_ms=reranker_info["latency_ms"],
                    fallback_used=reranker_info["fallback_used"],
                    original_rank=original_rank,
                )

            results.append(
                SearchResult(
                    id=r["id"],
                    content=r["content"],
                    doc_type=ChunkType.TEXT,
                    document_id=doc_id,
                    document_name=r["document_name"],
                    score=r.get("score", 0.0),
                    file_url=file_url,
                    relevance_score=r.get("relevance_score"),
                    reranker_metadata=reranker_metadata,
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

    # Call LLM
    client, model = _get_llm_client()
    if client is None:
        return "錯誤：未設定 OpenAI API Key。請在環境變數中設定 OPENAI_API_KEY。", sources

    try:
        response = client.chat.completions.create(
            model=model,
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

    # Call LLM with streaming
    client, model = _get_llm_client()
    if client is None:
        yield "錯誤：未設定 OpenAI API Key。請在環境變數中設定 OPENAI_API_KEY。"
        return

    try:
        stream = client.chat.completions.create(
            model=model,
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
    # Filter sources by relevance score (>= 0.5 threshold)
    MIN_RELEVANCE_SCORE = 0.5
    relevant_sources = [s for s in sources if (s.score or 0) >= MIN_RELEVANCE_SCORE]
    
    if not relevant_sources:
        yield {"type": "content", "data": "找不到相關的知識庫內容。請上傳相關文件後再試。"}
        return

    # Build context from relevant sources only
    context_parts = []
    for i, source in enumerate(relevant_sources, 1):
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

    # Call LLM with streaming
    client, model = _get_llm_client()
    if client is None:
        yield {"type": "content", "data": "錯誤：未設定 OpenAI API Key。請在環境變數中設定 OPENAI_API_KEY。"}
        return

    settings = get_settings()
    is_openai = settings.llm_provider != "ollama"

    try:
        create_kwargs = dict(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=1500,
            temperature=0.5,
            stream=True,
        )
        # stream_options is OpenAI-only; Ollama doesn't support it
        if is_openai:
            create_kwargs["stream_options"] = {"include_usage": True}

        stream = client.chat.completions.create(**create_kwargs)

        usage_info = None
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield {"type": "content", "data": chunk.choices[0].delta.content}
            # Capture usage from the final chunk (OpenAI only)
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


def rewrite_query(query: str, attempt: int = 1) -> str | None:
    """Use LLM to rewrite a query for better retrieval. Returns rewritten query or None on failure."""
    client, model = _get_llm_client(light=True)
    if client is None:
        return None

    strategies = [
        "擴展同義詞和相關術語（例如：煞車→制動、軔缸；保養→定期檢修、PM）",
        "換個角度描述，使用更具體的技術術語或更廣泛的概念",
    ]
    strategy = strategies[min(attempt - 1, len(strategies) - 1)]

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": f"""請改寫以下查詢以提高文件檢索效果。策略：{strategy}

原始查詢：{query}

要求：
- 只輸出改寫後的查詢，不要其他內容
- 使用繁體中文
- 保持原意但加入同義詞或相關術語
- 不超過 50 字"""}],
            max_tokens=100,
            temperature=0.3,
        )
        content = response.choices[0].message.content or ""
        # Strip think tags from qwen
        import re as _re
        content = _re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        rewritten = content.strip().strip('"').strip("'")
        if rewritten and rewritten != query:
            return rewritten
    except Exception as e:
        logger.warning("Query rewrite failed: %s", e)
    return None


def evaluate_retrieval_quality(sources: list[SearchResult], threshold: float = 0.5) -> dict:
    """Evaluate retrieval quality based on source scores.
    Returns: {quality: 'good'|'low'|'none', avg_score, top_score, count}
    """
    if not sources:
        return {"quality": "none", "avg_score": 0, "top_score": 0, "count": 0}

    scores = [s.score or 0 for s in sources]
    avg_score = sum(scores) / len(scores)
    top_score = max(scores)

    # Also check relevance_score from reranker if available
    rel_scores = [s.relevance_score for s in sources if s.relevance_score is not None]
    avg_rel = sum(rel_scores) / len(rel_scores) if rel_scores else None

    quality = "good"
    if len(sources) < 2 or top_score < threshold:
        quality = "low"
    elif avg_rel is not None and avg_rel < 0.3:
        quality = "low"

    return {"quality": quality, "avg_score": round(avg_score, 3), "top_score": round(top_score, 3), "count": len(sources), "avg_relevance": round(avg_rel, 3) if avg_rel is not None else None}


def generate_follow_up_questions(query: str, answer: str, max_questions: int = 3) -> list[str]:
    """
    Generate follow-up questions based on the user's query and the AI's answer.
    
    Args:
        query: Original user query
        answer: AI's response
        max_questions: Maximum number of questions to generate
        
    Returns:
        List of follow-up question strings
    """
    client, model = _get_llm_client(light=True)

    if client is None:
        return []

    try:
        prompt = f"""根據以下問答內容，生成 {max_questions} 個使用者可能想進一步了解的後續問題。

使用者問題：{query}

AI 回答：{answer[:1000]}...

要求：
1. 問題要與原始問題相關，但探索不同面向
2. 問題要具體且實用
3. 每個問題獨立一行，不要編號
4. 使用繁體中文
5. 問題要簡潔，不超過 30 字

只輸出問題，不要其他內容。"""

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.7,
        )
        
        content = response.choices[0].message.content or ""
        questions = [q.strip() for q in content.strip().split('\n') if q.strip()]
        return questions[:max_questions]
        
    except Exception as e:
        logger.error(f"Error generating follow-up questions: {e}")
        return []
