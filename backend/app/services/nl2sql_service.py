"""
NL2SQL Service - Natural Language to SQL conversion.
Uses LLM to convert user queries to safe SQL statements.
"""

import os
import re
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from openai import AsyncOpenAI


@dataclass
class SQLQuery:
    """Parsed SQL query with metadata"""
    sql: str
    query_type: str  # select, aggregate, etc.
    tables: List[str]
    parameters: Dict[str, Any]
    is_valid: bool
    error: Optional[str] = None


# Table schema for context
TABLE_SCHEMA = """
## Database Schema (PostgreSQL)

### vehicles (車輛基本資料)
- id: UUID (PK)
- vehicle_code: VARCHAR(20) - 車輛編號 (如 EMU801, EMU802)
- vehicle_type: VARCHAR(50) - 車型 (如 EMU800系列, TEMU2000型)
- manufacturer: VARCHAR(100) - 製造商 (如 日立, 川崎重工)
- manufacture_year: INTEGER - 製造年份
- status: VARCHAR(20) - 狀態 (active/maintenance/retired)
- depot: VARCHAR(50) - 所屬機務段 (如 新竹機務段, 台中機務段)
- last_maintenance_date: DATE - 最後保養日期

### fault_records (故障歷程)
- id: UUID (PK)
- vehicle_id: UUID (FK → vehicles.id)
- fault_code: VARCHAR(30) - 故障編號
- fault_date: TIMESTAMP - 故障發生時間
- fault_type: VARCHAR(50) - 故障類型 (轉向架/煞車系統/電氣系統/空調系統/門機系統/推進系統/集電弓)
- severity: VARCHAR(20) - 嚴重程度 (critical/major/minor)
- status: VARCHAR(20) - 處理狀態 (open/in_progress/resolved)
- description: TEXT - 故障描述
- resolution: TEXT - 處理方式
- resolved_at: TIMESTAMP - 解決時間
- reported_by: VARCHAR(100) - 回報人員

### maintenance_records (檢修歷程)
- id: UUID (PK)
- vehicle_id: UUID (FK → vehicles.id)
- maintenance_code: VARCHAR(30) - 檢修編號
- maintenance_type: VARCHAR(50) - 檢修類型 (scheduled/unscheduled/emergency)
- maintenance_date: TIMESTAMP - 檢修日期
- completed_date: TIMESTAMP - 完成日期
- status: VARCHAR(20) - 狀態 (pending/in_progress/completed)
- description: TEXT - 檢修描述
- labor_hours: NUMERIC(10,2) - 工時
- labor_cost: NUMERIC(12,2) - 人工費用
- technician: VARCHAR(100) - 維修技師
- supervisor: VARCHAR(100) - 督導

### usage_records (使用歷程)
- id: UUID (PK)
- vehicle_id: UUID (FK → vehicles.id)
- record_date: DATE - 記錄日期
- mileage: INTEGER - 里程數 (公里)
- operating_hours: NUMERIC(10,2) - 運轉時數
- trips_count: INTEGER - 班次數
- route: VARCHAR(100) - 運行路線

### parts_inventory (零件庫存)
- id: UUID (PK)
- part_number: VARCHAR(50) - 零件編號
- part_name: VARCHAR(200) - 零件名稱
- category: VARCHAR(50) - 零件類別
- quantity_on_hand: INTEGER - 庫存數量
- minimum_quantity: INTEGER - 最低庫存量
- unit_price: NUMERIC(12,2) - 單價
- supplier: VARCHAR(200) - 供應商

### parts_used (用料歷程)
- id: UUID (PK)
- maintenance_id: UUID (FK → maintenance_records.id)
- part_id: UUID (FK → parts_inventory.id)
- part_number: VARCHAR(50) - 零件編號
- part_name: VARCHAR(200) - 零件名稱
- quantity: INTEGER - 使用數量
- unit_cost: NUMERIC(12,2) - 單價
- total_cost: NUMERIC(12,2) - 總價

### cost_records (維修成本)
- id: UUID (PK)
- vehicle_id: UUID (FK → vehicles.id)
- record_date: DATE - 記錄日期
- cost_type: VARCHAR(50) - 成本類型 (labor/parts/external/other)
- category: VARCHAR(50) - 成本分類
- description: VARCHAR(500) - 費用說明
- amount: NUMERIC(14,2) - 金額
- currency: VARCHAR(10) - 幣別 (TWD)
"""

# SQL whitelist for validation
ALLOWED_KEYWORDS = {
    "select", "from", "where", "join", "left", "right", "inner", "outer",
    "on", "and", "or", "not", "in", "like", "between", "is", "null",
    "order", "by", "asc", "desc", "limit", "offset", "group", "having",
    "count", "sum", "avg", "min", "max", "distinct", "as", "case", "when",
    "then", "else", "end", "cast", "coalesce", "nullif", "extract", "date_trunc",
    "true", "false"
}

FORBIDDEN_KEYWORDS = {
    "insert", "update", "delete", "drop", "truncate", "alter", "create",
    "grant", "revoke", "execute", "exec", "call", "shutdown", "copy",
    "pg_", "information_schema"
}

ALLOWED_TABLES = {
    "vehicles", "fault_records", "maintenance_records", "usage_records",
    "parts_inventory", "parts_used", "cost_records"
}


class NL2SQLService:
    """Service for converting natural language to SQL"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o")
    
    async def convert_to_sql(self, query: str, context: Optional[str] = None) -> SQLQuery:
        """
        Convert natural language query to SQL.
        
        Args:
            query: Natural language query from user
            context: Optional additional context
            
        Returns:
            SQLQuery object with SQL and metadata
        """
        system_prompt = f"""You are a SQL expert for a vehicle maintenance database.
Convert the user's natural language query to a PostgreSQL SELECT statement.

{TABLE_SCHEMA}

Rules:
1. ONLY generate SELECT queries (no INSERT, UPDATE, DELETE)
2. Always include relevant JOINs when referencing multiple tables
3. Use table aliases for clarity (e.g., v for vehicles, f for fault_records)
4. Return at most 100 rows unless user specifies otherwise
5. For date ranges, use appropriate date functions
6. Always order by relevant date/time columns descending by default

Output format (JSON only):
{{
    "sql": "SELECT ...",
    "query_type": "select|aggregate",
    "tables": ["table1", "table2"],
    "explanation": "Brief explanation of the query"
}}

If the query cannot be converted to SQL, respond with:
{{
    "error": "Explanation of why",
    "sql": null
}}
"""

        user_prompt = f"Query: {query}"
        if context:
            user_prompt += f"\nContext: {context}"

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            if result.get("error") or not result.get("sql"):
                return SQLQuery(
                    sql="",
                    query_type="error",
                    tables=[],
                    parameters={},
                    is_valid=False,
                    error=result.get("error", "Failed to generate SQL")
                )
            
            # Validate the generated SQL
            validation = self.validate_sql(result["sql"])
            if not validation["is_valid"]:
                return SQLQuery(
                    sql=result["sql"],
                    query_type=result.get("query_type", "unknown"),
                    tables=result.get("tables", []),
                    parameters={},
                    is_valid=False,
                    error=validation["error"]
                )
            
            return SQLQuery(
                sql=result["sql"],
                query_type=result.get("query_type", "select"),
                tables=result.get("tables", []),
                parameters={},
                is_valid=True
            )
            
        except Exception as e:
            return SQLQuery(
                sql="",
                query_type="error",
                tables=[],
                parameters={},
                is_valid=False,
                error=str(e)
            )
    
    def validate_sql(self, sql: str) -> Dict[str, Any]:
        """
        Validate SQL query for safety.
        
        Args:
            sql: SQL query string
            
        Returns:
            Dict with is_valid and optional error
        """
        if not sql:
            return {"is_valid": False, "error": "Empty SQL query"}
        
        sql_lower = sql.lower()
        
        # Check for forbidden keywords
        for keyword in FORBIDDEN_KEYWORDS:
            if re.search(rf'\b{keyword}\b', sql_lower):
                return {"is_valid": False, "error": f"Forbidden keyword: {keyword}"}
        
        # Must start with SELECT
        if not sql_lower.strip().startswith("select"):
            return {"is_valid": False, "error": "Query must be a SELECT statement"}
        
        # Check for comments (potential injection)
        if "--" in sql or "/*" in sql:
            return {"is_valid": False, "error": "SQL comments not allowed"}
        
        # Check for multiple statements
        if ";" in sql[:-1]:  # Allow trailing semicolon
            return {"is_valid": False, "error": "Multiple statements not allowed"}
        
        # Extract and validate table names
        tables_in_query = self._extract_tables(sql_lower)
        for table in tables_in_query:
            if table not in ALLOWED_TABLES:
                return {"is_valid": False, "error": f"Unknown table: {table}"}
        
        return {"is_valid": True}
    
    def _extract_tables(self, sql: str) -> List[str]:
        """Extract table names from SQL query"""
        tables = []
        # Pattern for FROM and JOIN clauses
        patterns = [
            r'\bfrom\s+(\w+)',
            r'\bjoin\s+(\w+)',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, sql)
            tables.extend(matches)
        return list(set(tables))


# Singleton instance
_nl2sql_service = None


def get_nl2sql_service() -> NL2SQLService:
    """Get or create NL2SQL service instance"""
    global _nl2sql_service
    if _nl2sql_service is None:
        _nl2sql_service = NL2SQLService()
    return _nl2sql_service
