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
from app.db.session import get_db_context
from sqlalchemy import text

logger = logging.getLogger(__name__)


async def log_search_metrics(
    query: str,
    search_query: Optional[str],
    sources: list,
    quality: str,
    rewrite_used: bool = False,
    rewrite_query: Optional[str] = None,
    duration_ms: int = 0,
    intent: Optional[str] = None,
    request_id: Optional[str] = None,
):
    """Insert RAG search metrics into rag_search_log."""
    try:
        scores = [s.score if hasattr(s, 'score') else s.get('score', 0) for s in sources]
        top_score = max(scores) if scores else 0.0
        avg_score = sum(scores) / len(scores) if scores else 0.0

        async with get_db_context() as session:
            await session.execute(
                text("""
                    INSERT INTO rag_search_log
                        (query, search_query, top_score, avg_score, source_count,
                         rewrite_used, rewrite_query, quality, duration_ms, intent, request_id)
                    VALUES
                        (:query, :search_query, :top_score, :avg_score, :source_count,
                         :rewrite_used, :rewrite_query, :quality, :duration_ms, :intent, :request_id)
                """),
                {
                    "query": query,
                    "search_query": search_query,
                    "top_score": top_score,
                    "avg_score": avg_score,
                    "source_count": len(sources),
                    "rewrite_used": rewrite_used,
                    "rewrite_query": rewrite_query,
                    "quality": quality,
                    "duration_ms": duration_ms,
                    "intent": intent,
                    "request_id": request_id,
                },
            )
    except Exception as e:
        logger.error(f"Failed to log search metrics: {e}")


def _get_llm_client(light: bool = False, model_override: str = None):
    """Return (client, model) based on configured LLM provider. model_override takes precedence.

    For anthropic provider, returns (None, model) — callers should check settings.llm_provider
    and use _call_anthropic_stream() instead.
    """
    settings = get_settings()
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        model = model_override or settings.anthropic_model or "claude-haiku-4-5-20251001"
        return "anthropic", model
    elif settings.llm_provider == "ollama":
        client = OpenAI(base_url=settings.ollama_chat_url, api_key=settings.ollama_chat_api_key)
        if model_override:
            model = model_override
        else:
            model = settings.ollama_light_model if light else settings.ollama_chat_model
    else:
        api_key = os.environ.get("OPENAI_API_KEY", settings.openai_api_key)
        if not api_key:
            return None, None
        client = OpenAI(api_key=api_key)
        if model_override:
            model = model_override
        else:
            model = "gpt-4o-mini" if light else settings.openai_model
    return client, model


def _try_llm_with_fallback(messages: list, system: str, max_tokens: int = 4000, model_override: str = None):
    """Pattern 4: Withholding — silently fall back through providers.
    Tries configured primary → Anthropic → OpenAI → Ollama.
    Only surfaces error if ALL fail. Yields content chunks (streaming).
    """
    settings = get_settings()
    providers = []

    # Build ordered provider list: configured primary first, then fallbacks
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        providers.append(("anthropic", model_override or settings.anthropic_model or "claude-haiku-4-5-20251001"))
    if settings.llm_provider == "openai" and settings.openai_api_key:
        providers.append(("openai", model_override or settings.openai_model or "gpt-4o"))
    elif settings.openai_api_key:
        providers.append(("openai", settings.openai_model or "gpt-4o"))
    if settings.llm_provider == "ollama":
        providers.append(("ollama", model_override or settings.ollama_chat_model))
    elif settings.ollama_chat_url:
        providers.append(("ollama", settings.ollama_chat_model))
    # Add remaining fallbacks not already in list
    if settings.anthropic_api_key and not any(p[0] == "anthropic" for p in providers):
        providers.append(("anthropic", settings.anthropic_model or "claude-haiku-4-5-20251001"))

    last_error = None
    for provider_name, model in providers:
        try:
            if provider_name == "anthropic":
                user_text = messages[0]["content"] if messages else ""
                if isinstance(user_text, list):
                    user_text = user_text[0].get("text", "") if user_text else ""
                for chunk in _call_anthropic_stream(
                    messages=[{"role": "user", "content": user_text}],
                    model=model, system=system, max_tokens=max_tokens,
                ):
                    yield {"type": "content", "data": chunk}
                logger.info("LLM fallback: using %s/%s", provider_name, model)
                return
            elif provider_name == "openai":
                client = OpenAI(api_key=settings.openai_api_key)
            else:
                client = OpenAI(base_url=settings.ollama_chat_url, api_key=settings.ollama_chat_api_key)

            stream = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}] + messages,
                max_tokens=max_tokens, temperature=0.5, stream=True,
            )
            emitted = False
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    emitted = True
                    yield {"type": "content", "data": chunk.choices[0].delta.content}
                if chunk.usage:
                    yield {"type": "usage", "data": {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens": chunk.usage.total_tokens,
                    }}
            if emitted:
                if provider_name != settings.llm_provider:
                    logger.info("LLM silent fallback: %s → %s/%s", settings.llm_provider, provider_name, model)
                return
        except Exception as e:
            last_error = e
            logger.warning("LLM provider %s/%s failed: %s, trying next...", provider_name, model, e)
            continue

    yield {"type": "content", "data": f"生成回答時發生錯誤: {last_error}"}


def _call_anthropic(messages: list, model: str, system: str = "", max_tokens: int = 2000) -> str:
    """Call Anthropic API (non-streaming) for simple completions."""
    import httpx
    settings = get_settings()
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def _call_anthropic_stream(messages: list, model: str, system: str = "", max_tokens: int = 4000):
    """Call Anthropic API with streaming. Yields text chunks."""
    import httpx
    settings = get_settings()
    with httpx.stream(
        "POST",
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": max_tokens,
            "stream": True,
            "system": system,
            "messages": messages,
        },
        timeout=120.0,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line.startswith("data: "):
                import json as _json
                try:
                    data = _json.loads(line[6:])
                    if data.get("type") == "content_block_delta":
                        text = data.get("delta", {}).get("text", "")
                        if text:
                            yield text
                except Exception:
                    pass


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


# === Source feedback boost cache (in-memory, refreshed every 60s) ===
# `search()` is sync so we avoid per-call async DB queries; instead cache the
# `source_boost_scores` view in-process and refresh on a TTL.
import time as _time
import threading as _threading

_BOOST_CACHE: dict[str, int] = {}
_BOOST_CACHE_TS: float = 0.0
_BOOST_CACHE_TTL_SEC: float = 60.0
_BOOST_CACHE_LOCK = _threading.Lock()


def _load_boost_scores() -> dict[str, int]:
    """Load chunk_id → net_score from the source_boost_scores view using a sync
    psycopg2 connection (since `search()` is a sync function)."""
    try:
        import psycopg2
        db_url = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://aikm:aikm@localhost:5432/aikm",
        )
        # Strip SQLAlchemy async driver prefix for psycopg2
        dsn = db_url.replace("postgresql+asyncpg://", "postgresql://")
        conn = psycopg2.connect(dsn, connect_timeout=3)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT chunk_id, net_score FROM source_boost_scores WHERE net_score <> 0"
                )
                return {row[0]: int(row[1]) for row in cur.fetchall()}
        finally:
            conn.close()
    except Exception as e:
        # Table/view may not exist yet (migration not applied) — treat as empty
        logger.debug(f"Boost score load skipped: {e}")
        return {}


def _get_boost_scores() -> dict[str, int]:
    """Return cached chunk_id → net_score map, refreshing if TTL expired."""
    global _BOOST_CACHE, _BOOST_CACHE_TS
    now = _time.time()
    if now - _BOOST_CACHE_TS < _BOOST_CACHE_TTL_SEC and _BOOST_CACHE_TS > 0:
        return _BOOST_CACHE
    with _BOOST_CACHE_LOCK:
        # Double-check after acquiring lock
        if now - _BOOST_CACHE_TS < _BOOST_CACHE_TTL_SEC and _BOOST_CACHE_TS > 0:
            return _BOOST_CACHE
        _BOOST_CACHE = _load_boost_scores()
        _BOOST_CACHE_TS = _time.time()
    return _BOOST_CACHE


def invalidate_boost_cache() -> None:
    """Force the boost cache to refresh on next read. Called after new votes."""
    global _BOOST_CACHE_TS
    with _BOOST_CACHE_LOCK:
        _BOOST_CACHE_TS = 0.0


def _apply_feedback_boost(results: list[SearchResult]) -> list[SearchResult]:
    """Apply net-score based boost to search results' score.
    Each net_score point = +5% relative score, capped at +50% (i.e. 10 net upvotes)."""
    if not results:
        return results
    boosts = _get_boost_scores()
    if not boosts:
        return results
    for r in results:
        boost = boosts.get(r.id, 0)
        if boost > 0:
            current = r.score or 0
            r.score = current * (1 + 0.05 * min(boost, 10))
    results.sort(key=lambda x: x.score or 0, reverse=True)
    return results


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
            # Apply feedback boost (may reorder if new votes came in since cache)
            results = _apply_feedback_boost(results)
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

    # Apply feedback boost before final sort/truncation so upvoted chunks can rise in ranking
    results = _apply_feedback_boost(results)

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
    model: Optional[str] = None,
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
        {"type": "text", "text": f"/no_think\n知識庫內容:\n{context}\n\n用戶問題: {query}"}
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

    # Call LLM with streaming (use model override from frontend if provided)
    client, resolved_model = _get_llm_client(model_override=model)
    if client is None:
        yield {"type": "content", "data": "錯誤：未設定 API Key。請在系統設定中配置。"}
        return

    settings = get_settings()
    model = resolved_model

    # Pattern 3: Output Token Reservation — 根據 context 長度動態調整 max_tokens
    # 短 context（<2000 chars）用 1024，長 context 或多來源用 2048
    context_len = len(context)
    source_count = len(relevant_sources)
    if context_len > 4000 or source_count > 5:
        output_tokens = 4096
    elif context_len > 2000 or source_count > 3:
        output_tokens = 2048
    else:
        output_tokens = 1024

    try:
        # Pattern 4: Withholding — use fallback pipeline for resilient LLM calls
        messages = [{"role": "user", "content": user_content}]
        for result in _try_llm_with_fallback(
            messages=messages,
            system=SYSTEM_PROMPT,
            max_tokens=output_tokens,
            model_override=model,
        ):
            yield result

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

    prompt = f"""請改寫以下查詢以提高文件檢索效果。策略：{strategy}

原始查詢：{query}

要求：
- 只輸出改寫後的查詢，不要其他內容
- 使用繁體中文
- 保持原意但加入同義詞或相關術語
- 不超過 50 字"""

    try:
        if client == "anthropic":
            content = _call_anthropic([{"role": "user", "content": prompt}], model, max_tokens=100)
        else:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": f"/no_think\n{prompt}"}],
                max_tokens=100,
                temperature=0.3,
            )
            content = response.choices[0].message.content or ""
        # Strip think tags from qwen
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        rewritten = content.strip().strip('"').strip("'")
        if rewritten and rewritten != query:
            return rewritten
    except Exception as e:
        logger.warning("Query rewrite failed: %s", e)
    return None


def evaluate_retrieval_quality(sources: list[SearchResult], threshold: float = 0.5) -> dict:
    """Evaluate retrieval quality based on source scores (pass unfiltered results).
    Returns: {quality: 'good'|'low'|'none', avg_score, top_score, count}
    """
    if not sources:
        return {"quality": "none", "avg_score": 0, "top_score": 0, "count": 0}

    scores = [s.score or 0 for s in sources]
    avg_score = sum(scores) / len(scores)
    top_score = max(scores)
    above_threshold = sum(1 for s in scores if s >= threshold)

    # Also check relevance_score from reranker if available
    rel_scores = [s.relevance_score for s in sources if s.relevance_score is not None]
    avg_rel = sum(rel_scores) / len(rel_scores) if rel_scores else None

    quality = "good"
    if above_threshold < 2 or top_score < threshold:
        quality = "low"
    elif avg_rel is not None and avg_rel < 0.3:
        quality = "low"

    return {"quality": quality, "avg_score": round(avg_score, 3), "top_score": round(top_score, 3), "count": above_threshold, "avg_relevance": round(avg_rel, 3) if avg_rel is not None else None}


def generate_follow_up_questions(query: str, answer: str, max_questions: int = 3, model: str = None) -> list[str]:
    """
    Generate follow-up questions based on the user's query and the AI's answer.
    
    Args:
        query: Original user query
        answer: AI's response
        max_questions: Maximum number of questions to generate
        
    Returns:
        List of follow-up question strings
    """
    client, resolved_model = _get_llm_client(light=True, model_override=model)

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
            model=resolved_model,
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
