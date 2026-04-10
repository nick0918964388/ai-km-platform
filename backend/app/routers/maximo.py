"""
Maximo API Routes — NL→SQL structured query + knowledge base management.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import get_db
from app.services.maximo_nl2sql import MaximoNL2SQL

router = APIRouter(prefix="/maximo", tags=["Maximo"])


# ── NL→SQL ───────────────────────────────────────────────────────────────────

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


# ── Knowledge Base Management ─────────────────────────────────────────────────

class RuleItem(BaseModel):
    id: int
    content: str

class ExampleItem(BaseModel):
    id: int
    question: str
    sql_query: str
    verified: bool

class KnowledgeResponse(BaseModel):
    rules: List[RuleItem]
    examples: List[ExampleItem]

class AddRuleRequest(BaseModel):
    content: str

class AddExampleRequest(BaseModel):
    question: str
    sql_query: str


@router.get("/knowledge", response_model=KnowledgeResponse)
async def get_knowledge(db: AsyncSession = Depends(get_db)):
    """Get all domain rules and SQL examples."""
    rules_result = await db.execute(text(
        "SELECT id, description FROM maximo_field_metadata "
        "WHERE table_name = '_rules' ORDER BY id"
    ))
    rules = [RuleItem(id=r.id, content=r.description) for r in rules_result.fetchall()]

    examples_result = await db.execute(text(
        "SELECT id, question, sql_query, verified FROM nl_sql_examples ORDER BY id"
    ))
    examples = [
        ExampleItem(id=r.id, question=r.question, sql_query=r.sql_query, verified=r.verified)
        for r in examples_result.fetchall()
    ]

    return KnowledgeResponse(rules=rules, examples=examples)


@router.post("/knowledge/rule", response_model=RuleItem)
async def add_rule(req: AddRuleRequest, db: AsyncSession = Depends(get_db)):
    """Add a domain knowledge rule."""
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    # Auto-generate column name
    count_result = await db.execute(text(
        "SELECT COUNT(*) FROM maximo_field_metadata WHERE table_name = '_rules'"
    ))
    count = count_result.scalar()
    col_name = f"rule_{count + 1}"

    result = await db.execute(text(
        "INSERT INTO maximo_field_metadata (table_name, column_name, display_name, description) "
        "VALUES ('_rules', :col, '查詢規則', :desc) RETURNING id"
    ), {"col": col_name, "desc": req.content.strip()})
    await db.commit()
    new_id = result.scalar()
    return RuleItem(id=new_id, content=req.content.strip())


@router.delete("/knowledge/rule/{rule_id}")
async def delete_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a domain rule."""
    result = await db.execute(text(
        "DELETE FROM maximo_field_metadata WHERE id = :id AND table_name = '_rules'"
    ), {"id": rule_id})
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"success": True}


@router.post("/knowledge/example", response_model=ExampleItem)
async def add_example(req: AddExampleRequest, db: AsyncSession = Depends(get_db)):
    """Add a NL→SQL example."""
    if not req.question.strip() or not req.sql_query.strip():
        raise HTTPException(status_code=400, detail="Question and SQL cannot be empty")
    if not req.sql_query.strip().lower().startswith("select"):
        raise HTTPException(status_code=400, detail="Only SELECT queries allowed")

    result = await db.execute(text(
        "INSERT INTO nl_sql_examples (question, sql_query, verified) "
        "VALUES (:q, :sql, true) RETURNING id"
    ), {"q": req.question.strip(), "sql": req.sql_query.strip()})
    await db.commit()
    new_id = result.scalar()
    return ExampleItem(id=new_id, question=req.question.strip(), sql_query=req.sql_query.strip(), verified=True)


@router.delete("/knowledge/example/{example_id}")
async def delete_example(example_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a SQL example."""
    result = await db.execute(text(
        "DELETE FROM nl_sql_examples WHERE id = :id"
    ), {"id": example_id})
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Example not found")
    return {"success": True}
