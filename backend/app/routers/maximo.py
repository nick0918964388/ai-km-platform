"""
Maximo API Routes — NL→SQL structured query for Maximo data.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, List, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.maximo_nl2sql import MaximoNL2SQL

router = APIRouter(prefix="/maximo", tags=["Maximo"])


class NL2SQLRequest(BaseModel):
    question: str


class NL2SQLResponse(BaseModel):
    success: bool
    sql: Optional[str] = None
    explanation: Optional[str] = None
    data: List[Any] = []
    columns: List[str] = []
    row_count: int = 0
    execution_ms: Optional[float] = None
    error: Optional[str] = None


@router.post("/nl2sql", response_model=NL2SQLResponse)
async def nl2sql(req: NL2SQLRequest, db: AsyncSession = Depends(get_db)):
    """Convert natural language question to SQL and execute against Maximo tables."""
    service = MaximoNL2SQL(db)
    result = await service.query(req.question)
    return NL2SQLResponse(**result)
