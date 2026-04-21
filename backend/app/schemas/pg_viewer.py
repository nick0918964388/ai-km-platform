"""Pydantic API schemas for pg_viewer endpoints (013-postgres-viewer).

Field names match the OpenAPI spec contracts/pg-viewer-api.yaml exactly.
These are the wire-format models for request/response serialization.
Internal service models live in app/models/pg_viewer_schemas.py.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Component schemas (mirroring pg-viewer-api.yaml components/schemas)
# ---------------------------------------------------------------------------


class TableSummarySchema(BaseModel):
    """TableSummary wire model — one entry in GET /tables response."""

    model_config = ConfigDict(populate_by_name=True)

    # The OpenAPI spec uses "schema" as the field name. To avoid shadowing
    # BaseModel.schema (a classmethod), we store as schema_name and alias to
    # "schema" in JSON output.
    schema_name: str = Field("public", alias="schema", description="Schema name")
    name: str
    kind: str  # "table" | "view"
    approx_row_count: int = 0
    group: Optional[str] = None
    grant_missing: Optional[bool] = None


class ColumnSchema(BaseModel):
    """Column descriptor within TableSchema."""

    name: str
    data_type: str
    nullable: bool
    default: Optional[str] = None
    comment: Optional[str] = None
    is_pk: Optional[bool] = None
    is_indexed: Optional[bool] = None


class IndexSchema(BaseModel):
    """Index descriptor within TableSchema."""

    name: str
    definition: str
    unique: Optional[bool] = None


class ForeignKeySchema(BaseModel):
    """Foreign key descriptor within TableSchema."""

    column: str
    foreign_table: str
    foreign_column: str


class TableSchemaResponse(BaseModel):
    """Full table schema — GET /tables/{table}/schema response."""

    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field("public", alias="schema")
    name: str
    columns: List[ColumnSchema] = []
    primary_key: List[str] = []
    indexes: List[IndexSchema] = []
    foreign_keys: List[ForeignKeySchema] = []
    approx_row_count: int = 0


class RowColumnMeta(BaseModel):
    """Column metadata within RowPage."""

    name: str
    data_type: str
    redacted: Optional[bool] = None


class RowPage(BaseModel):
    """Paginated row result — GET /tables/{table}/rows response."""

    columns: List[RowColumnMeta]
    rows: List[Dict[str, Any]]
    limit: int
    offset: int
    approx_total: int
    execution_ms: float
    truncated: bool
    notice: Optional[str] = None


class SqlColumnMeta(BaseModel):
    """Column metadata within SqlResult."""

    name: str
    data_type: str
    redacted: Optional[bool] = None


class SqlResult(BaseModel):
    """SQL editor result — POST /sql response."""

    columns: List[SqlColumnMeta]
    rows: List[Dict[str, Any]]
    row_count: int
    elapsed_ms: float
    truncated: bool
    notice: Optional[str] = None


class AuditEntry(BaseModel):
    """Single audit log entry — GET /audit response item."""

    id: Optional[int] = None
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    action: Optional[str] = None
    table_name: Optional[str] = None
    filters_json: Optional[Dict[str, Any]] = None
    order_by: Optional[str] = None
    order_dir: Optional[str] = None
    limit_val: Optional[int] = None
    offset_val: Optional[int] = None
    row_count: Optional[int] = None
    execution_ms: Optional[float] = None
    error_message: Optional[str] = None
    query_type: Optional[str] = None
    raw_sql: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None


class ErrorSchema(BaseModel):
    """Error response body."""

    detail: str


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class SqlEditorRequest(BaseModel):
    """Request body for POST /sql."""

    sql: str = Field(..., min_length=1, max_length=8000)


# ---------------------------------------------------------------------------
# Response wrappers
# ---------------------------------------------------------------------------


class TableListResponse(BaseModel):
    """Response wrapper for GET /tables."""

    tables: List[TableSummarySchema]


class AuditListResponse(BaseModel):
    """Response wrapper for GET /audit."""

    entries: List[AuditEntry]
    total: int = 0
