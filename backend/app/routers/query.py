"""
Unified Query API - Handles natural language queries.
Routes to appropriate backend (RAG or Structured Data) based on intent.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.session import get_db
from app.services.nl2sql_service import get_nl2sql_service
from app.services.structured_query import get_structured_query_service
from app.services.intent_classifier import get_intent_classifier, QueryIntent


router = APIRouter(prefix="/query", tags=["Query"])


class QueryRequest(BaseModel):
    """Unified query request"""
    query: str
    context: Optional[str] = None
    include_sources: bool = True


class StructuredDataResult(BaseModel):
    """Structured data query result"""
    type: str = "structured"
    sql: str
    data: List[Dict[str, Any]]
    row_count: int
    columns: List[str]
    execution_time_ms: float


class IntentInfo(BaseModel):
    """Intent classification info"""
    intent: str
    confidence: float
    entities: Dict[str, Any]
    reasoning: str


class QueryResponse(BaseModel):
    """Unified query response"""
    success: bool
    query: str
    query_type: str  # "structured", "knowledge", "hybrid", "clarification"
    intent_info: Optional[IntentInfo] = None
    structured_result: Optional[StructuredDataResult] = None
    knowledge_result: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    suggested_queries: Optional[List[str]] = None
    error: Optional[str] = None
    timestamp: str


@router.post("", response_model=QueryResponse)
async def unified_query(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Process a natural language query with intelligent routing.
    
    Uses AI intent classification to determine the best processing path:
    - **structured**: Query structured data (vehicles, faults, maintenance, costs)
    - **knowledge**: Query knowledge base documents (manuals, procedures)
    - **hybrid**: Combine both structured data and knowledge
    - **clarification**: Request more information from user
    
    Examples:
    - "查詢 EMU801 故障歷程" → Structured (SQL query)
    - "轉向架維修標準流程" → Knowledge (RAG search)
    - "EMU801 煞車系統故障原因分析" → Hybrid (both)
    """
    timestamp = datetime.now().isoformat()
    
    try:
        # Step 1: Classify intent
        classifier = get_intent_classifier()
        intent_result = await classifier.classify(request.query, request.context)
        
        intent_info = IntentInfo(
            intent=intent_result.intent.value,
            confidence=intent_result.confidence,
            entities=intent_result.entities,
            reasoning=intent_result.reasoning
        )
        
        # Step 2: Route based on intent
        if intent_result.intent == QueryIntent.CLARIFICATION:
            return QueryResponse(
                success=True,
                query=request.query,
                query_type="clarification",
                intent_info=intent_info,
                message="請提供更多資訊以便我更準確地回答您的問題。",
                suggested_queries=intent_result.suggested_queries,
                timestamp=timestamp
            )
        
        if intent_result.intent == QueryIntent.KNOWLEDGE:
            # TODO: Integrate with existing RAG service
            return QueryResponse(
                success=True,
                query=request.query,
                query_type="knowledge",
                intent_info=intent_info,
                message="正在知識庫中搜尋相關資料...",
                knowledge_result={"status": "pending", "note": "RAG integration coming"},
                timestamp=timestamp
            )
        
        # Structured or Hybrid - execute SQL query
        nl2sql = get_nl2sql_service()
        structured = get_structured_query_service(db)
        
        sql_query = await nl2sql.convert_to_sql(request.query, request.context)
        
        if sql_query.is_valid and sql_query.sql:
            result = await structured.execute_sql(sql_query.sql)
            
            if result.success:
                response = QueryResponse(
                    success=True,
                    query=request.query,
                    query_type=intent_result.intent.value,
                    intent_info=intent_info,
                    structured_result=StructuredDataResult(
                        sql=sql_query.sql,
                        data=result.data,
                        row_count=result.row_count,
                        columns=result.columns,
                        execution_time_ms=result.execution_time_ms
                    ),
                    timestamp=timestamp
                )
                
                # For hybrid, add note about knowledge search
                if intent_result.intent == QueryIntent.HYBRID:
                    response.message = "已查詢結構化資料。知識庫搜尋功能開發中。"
                
                return response
            else:
                return QueryResponse(
                    success=False,
                    query=request.query,
                    query_type=intent_result.intent.value,
                    intent_info=intent_info,
                    error=result.error,
                    timestamp=timestamp
                )
        
        # SQL conversion failed
        return QueryResponse(
            success=False,
            query=request.query,
            query_type="clarification",
            intent_info=intent_info,
            message="無法將您的查詢轉換為資料庫查詢。",
            error=sql_query.error,
            suggested_queries=["請嘗試更具體的描述，例如：查詢 EMU801 故障歷程"],
            timestamp=timestamp
        )
        
    except Exception as e:
        return QueryResponse(
            success=False,
            query=request.query,
            query_type="error",
            error=str(e),
            timestamp=timestamp
        )


@router.post("/classify", response_model=IntentInfo)
async def classify_intent(request: QueryRequest):
    """
    Classify query intent without executing.
    
    Useful for preview/debugging intent classification.
    """
    classifier = get_intent_classifier()
    result = await classifier.classify(request.query, request.context)
    
    return IntentInfo(
        intent=result.intent.value,
        confidence=result.confidence,
        entities=result.entities,
        reasoning=result.reasoning
    )


@router.post("/sql", response_model=QueryResponse)
async def direct_sql_query(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Convert natural language to SQL and execute (bypass intent classification).
    
    Use this endpoint when you know the query is for structured data.
    """
    timestamp = datetime.now().isoformat()
    
    try:
        nl2sql = get_nl2sql_service()
        structured = get_structured_query_service(db)
        
        sql_query = await nl2sql.convert_to_sql(request.query, request.context)
        
        if not sql_query.is_valid:
            return QueryResponse(
                success=False,
                query=request.query,
                query_type="structured",
                error=sql_query.error or "無法轉換為 SQL",
                timestamp=timestamp
            )
        
        result = await structured.execute_sql(sql_query.sql)
        
        if result.success:
            return QueryResponse(
                success=True,
                query=request.query,
                query_type="structured",
                structured_result=StructuredDataResult(
                    sql=sql_query.sql,
                    data=result.data,
                    row_count=result.row_count,
                    columns=result.columns,
                    execution_time_ms=result.execution_time_ms
                ),
                timestamp=timestamp
            )
        else:
            return QueryResponse(
                success=False,
                query=request.query,
                query_type="structured",
                error=result.error,
                timestamp=timestamp
            )
            
    except Exception as e:
        return QueryResponse(
            success=False,
            query=request.query,
            query_type="error",
            error=str(e),
            timestamp=timestamp
        )
