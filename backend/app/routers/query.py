"""
Unified Query API - Handles natural language queries.
Routes to appropriate backend (RAG or Structured Data).
"""

from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.session import get_db
from app.services.nl2sql_service import get_nl2sql_service
from app.services.structured_query import get_structured_query_service


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


class QueryResponse(BaseModel):
    """Unified query response"""
    success: bool
    query: str
    query_type: str  # "structured", "knowledge", "hybrid", "clarification"
    structured_result: Optional[StructuredDataResult] = None
    knowledge_result: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    error: Optional[str] = None
    timestamp: str


@router.post("", response_model=QueryResponse)
async def unified_query(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Process a natural language query.
    
    Automatically determines if the query should be routed to:
    - Structured data (SQL queries on vehicle/maintenance data)
    - Knowledge base (RAG on documents)
    - Hybrid (both)
    
    Examples:
    - "查詢 EMU801 故障歷程" → Structured
    - "轉向架維修標準流程" → Knowledge base
    - "EMU801 煞車系統故障原因分析" → Hybrid
    """
    timestamp = datetime.now().isoformat()
    
    try:
        # Get services
        nl2sql = get_nl2sql_service()
        structured = get_structured_query_service(db)
        
        # Try to convert to SQL
        sql_query = await nl2sql.convert_to_sql(request.query, request.context)
        
        if sql_query.is_valid and sql_query.sql:
            # Execute structured query
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
        
        # If SQL conversion failed, it might be a knowledge query
        # For now, return clarification request
        # TODO: Integrate with RAG service
        
        if sql_query.error:
            return QueryResponse(
                success=False,
                query=request.query,
                query_type="clarification",
                message=f"無法理解您的查詢。{sql_query.error}",
                error=sql_query.error,
                timestamp=timestamp
            )
        
        # Fallback to knowledge base (placeholder)
        return QueryResponse(
            success=True,
            query=request.query,
            query_type="knowledge",
            message="此查詢將路由至知識庫（功能開發中）",
            knowledge_result=None,
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


@router.post("/sql", response_model=QueryResponse)
async def direct_sql_query(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Convert natural language to SQL and execute.
    
    This endpoint focuses only on structured data queries.
    """
    timestamp = datetime.now().isoformat()
    
    try:
        nl2sql = get_nl2sql_service()
        structured = get_structured_query_service(db)
        
        # Convert to SQL
        sql_query = await nl2sql.convert_to_sql(request.query, request.context)
        
        if not sql_query.is_valid:
            return QueryResponse(
                success=False,
                query=request.query,
                query_type="structured",
                error=sql_query.error or "無法轉換為 SQL",
                timestamp=timestamp
            )
        
        # Execute
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
