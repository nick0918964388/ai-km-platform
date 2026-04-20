"""Pydantic models for the pg_viewer feature (013-postgres-viewer).

Field names match the OpenAPI spec contracts/pg-viewer-api.yaml exactly.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class TableSummary(BaseModel):
    """Summary row returned by list_tables() — mirrors TableSummary in the spec."""

    schema_name: str = ""  # stored as `schema` in JSON; alias below
    name: str
    kind: str  # "table" | "view"
    approx_row_count: int = 0
    group: Optional[str] = None
    grant_missing: bool = False

    model_config = {"populate_by_name": True}

    def model_dump_api(self) -> dict:
        """Return dict with `schema` key (not `schema_name`) for the API response."""
        d = self.model_dump()
        d["schema"] = d.pop("schema_name")
        return d


class ColumnSummary(BaseModel):
    """Per-column metadata — mirrors Column in the spec."""

    name: str
    data_type: str
    nullable: bool
    default: Optional[str] = None
    comment: Optional[str] = None
    is_pk: bool = False
    is_indexed: bool = False


class IndexSummary(BaseModel):
    """Index metadata — mirrors Index in the spec."""

    name: str
    definition: str
    unique: bool = False


class ForeignKeySummary(BaseModel):
    """Foreign-key metadata — mirrors ForeignKey in the spec."""

    column: str
    foreign_table: str
    foreign_column: str


class TableSchema(BaseModel):
    """Full schema for one table — mirrors TableSchema in the spec."""

    schema_name: str = ""
    name: str
    columns: List[ColumnSummary] = []
    primary_key: List[str] = []
    indexes: List[IndexSummary] = []
    foreign_keys: List[ForeignKeySummary] = []
    approx_row_count: int = 0

    model_config = {"populate_by_name": True}

    def model_dump_api(self) -> dict:
        """Return dict with `schema` key (not `schema_name`) for the API response."""
        d = self.model_dump()
        d["schema"] = d.pop("schema_name")
        return d
