"""CSV exporter for pg_viewer (T-015 — 013-postgres-viewer).

Public API
----------
export_csv(table, columns, filters, order_by, order_dir, *, row_limit) -> StreamingResponse
    Stream rows from the named table through the query builder → viewer engine →
    redaction → per-cell truncation → CSV encode, under a 10 MB total payload cap.

Streaming design
----------------
- Rows are fetched from the DB in one query (LIMIT row_limit) and materialised
  into a Python list before streaming begins.  This is necessary because
  StreamingResponse headers (X-Row-Count, X-Truncated) must be set before the
  first byte is yielded, so we need the final row count up front.
- The list holds at most 1000 dict rows (~200 KB raw data), not the full CSV
  text.  CSV encoding is done lazily inside the async generator.
- Each row is encoded individually into a fresh io.StringIO buffer; the generator
  yields one CSV line at a time (plus CRLF as emitted by csv.writer).
- If the cumulative output exceeds _MAX_PAYLOAD_BYTES the generator stops
  immediately (no fake rows appended to the CSV body).

Per-cell truncation (spec §T-015)
----------------------------------
- str  > 1000 chars  → clip to 1000 + append "…" (UTF-8 ellipsis).
- bytes / memoryview → base64-encode the raw bytes THEN clip to 200 chars.
- None              → empty CSV field (empty string).
- Other scalars     → str(value).

No BOM is written.  Content-Type is text/csv; charset=utf-8.
"""
from __future__ import annotations

import base64
import csv
import io
import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Literal

from fastapi.responses import StreamingResponse

if TYPE_CHECKING:
    from app.services.pg_viewer.query_builder import FilterClause


# ---------------------------------------------------------------------------
# Patchable dependency factories (mirrors introspect.py pattern)
# Tests replace these module attributes directly to inject fakes.
# ---------------------------------------------------------------------------


def get_viewer_db():
    """Return the get_viewer_db async-generator factory (deferred import).

    Exposed at module level so tests can monkeypatch
    ``exporter.get_viewer_db = my_fake_gen`` without needing sqlalchemy.
    """
    from app.services.pg_viewer.engine import get_viewer_db as _gvdb  # noqa: PLC0415
    return _gvdb()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_PAYLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
_TEXT_CLIP_CHARS = 1000
_BYTES_CLIP_CHARS = 200
_ELLIPSIS = "\u2026"  # …

# Whitelist for filename characters — everything else is replaced with "_".
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9_\-]")


# ---------------------------------------------------------------------------
# Per-cell value encoder
# ---------------------------------------------------------------------------

def _encode_cell(value: Any) -> str:
    """Encode a single DB cell value to a CSV-safe string.

    Rules (spec §T-015):
    - None         → ""
    - bytes/memoryview → base64-encode, then clip to 200 chars (no ellipsis added)
    - str > 1000   → clip to 1000 chars + "…"
    - other        → str(value), no clipping
    """
    if value is None:
        return ""

    if isinstance(value, (bytes, memoryview)):
        raw = bytes(value) if isinstance(value, memoryview) else value
        encoded = base64.b64encode(raw).decode("ascii")
        return encoded[:_BYTES_CLIP_CHARS]

    if isinstance(value, str):
        if len(value) > _TEXT_CLIP_CHARS:
            return value[:_TEXT_CLIP_CHARS] + _ELLIPSIS
        return value

    return str(value)


# ---------------------------------------------------------------------------
# Filename sanitiser
# ---------------------------------------------------------------------------

def _safe_filename(table: str) -> str:
    """Produce a safe filename stem from a table name.

    All non-whitelisted characters are replaced with '_'.  The result is
    always non-empty (falls back to "export" if the entire stem is stripped).
    """
    stem = _SAFE_FILENAME_RE.sub("_", table)
    return stem if stem else "export"


# ---------------------------------------------------------------------------
# Public export function
# ---------------------------------------------------------------------------

async def export_csv(
    table: str,
    columns: list[str],
    filters: "list[FilterClause]",
    order_by: list[str] | None,
    order_dir: Literal["asc", "desc"],
    *,
    row_limit: int = 1000,
) -> StreamingResponse:
    """Stream table rows as a CSV file.

    Steps:
    1. Build SELECT SQL via build_table_select (T-012).
    2. Execute via get_viewer_db (T-010) — returns list of Row objects.
    3. Convert each Row to a plain dict.
    4. Apply redaction via apply_redaction (T-013).
    5. Determine headers (column names from redacted rows).
    6. Set StreamingResponse headers: Content-Type, Content-Disposition,
       X-Row-Count, X-Truncated.
    7. Yield CSV header line, then data lines one-by-one with a 10 MB cap.

    Parameters
    ----------
    table     : target table name (validated by build_table_select via T-011)
    columns   : columns to project; empty list → SELECT *
    filters   : WHERE predicates
    order_by  : explicit ORDER BY columns (None → PK fallback inside builder)
    order_dir : "asc" or "desc"
    row_limit : max rows to export (default 1000, must not exceed builder limit)
    """
    from app.services.pg_viewer.query_builder import build_table_select  # noqa: PLC0415
    from app.services.pg_viewer.redaction import apply_redaction  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415 — deferred for unit-test compat

    # ------------------------------------------------------------------
    # 1. Build SQL
    # ------------------------------------------------------------------
    sql_str, params = build_table_select(
        None,
        table=table,
        columns=columns,
        filters=filters,
        order_by=order_by,
        order_dir=order_dir,
        limit=row_limit,
        offset=0,
        pk_columns=None,
    )

    # H-2 fix: build_table_select emits asyncpg $N placeholders + list.
    # SQLAlchemy text() requires :name placeholders + dict.
    import re as _re  # noqa: PLC0415

    def _adapt_params(sql: str, p_list: list) -> tuple[str, dict]:
        adapted = _re.sub(r"\$(\d+)", lambda m: f":p{m.group(1)}", sql)
        return adapted, {f"p{i + 1}": v for i, v in enumerate(p_list)}

    adapted_sql, adapted_params = _adapt_params(sql_str, params)

    # ------------------------------------------------------------------
    # 2. Execute query — fetch all rows into memory (max row_limit rows)
    # ------------------------------------------------------------------
    raw_rows: list[dict] = []
    gen = get_viewer_db()
    conn = await gen.__anext__()
    try:
        result = await conn.execute(text(adapted_sql), adapted_params)
        sa_rows = result.fetchall()
        col_names: list[str] = list(result.keys())
        for row in sa_rows:
            raw_rows.append(dict(zip(col_names, row)))
    finally:
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass

    # ------------------------------------------------------------------
    # 3. Apply redaction (T-013)
    # ------------------------------------------------------------------
    redacted_rows, columns_meta = apply_redaction(raw_rows, table)

    # ------------------------------------------------------------------
    # 4. Derive output column names (visible, non-hidden columns)
    # ------------------------------------------------------------------
    if redacted_rows:
        output_columns = list(redacted_rows[0].keys())
    elif columns_meta:
        output_columns = [m.name for m in columns_meta if not m.hidden]
    elif raw_rows:
        # Fallback: all columns from the raw result (no redaction removed anything)
        output_columns = col_names
    else:
        output_columns = col_names

    # ------------------------------------------------------------------
    # 5. Determine X-Truncated and X-Row-Count
    #    (needs to be known before starting the stream)
    # ------------------------------------------------------------------
    actual_row_count = len(redacted_rows)
    # If the DB returned exactly row_limit rows it may have been truncated —
    # we report X-Truncated: true so callers know there might be more data.
    hit_limit = len(raw_rows) >= row_limit

    # ------------------------------------------------------------------
    # 6. Build response headers
    # ------------------------------------------------------------------
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    safe_stem = _safe_filename(table)
    filename = f"{safe_stem}_{ts}.csv"

    headers: dict[str, str] = {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Row-Count": str(actual_row_count),
    }
    if hit_limit:
        headers["X-Truncated"] = "true"

    # ------------------------------------------------------------------
    # 7. Build async generator — yields CSV lines (no BOM)
    # ------------------------------------------------------------------
    async def _generator():
        total_bytes = 0

        buf = io.StringIO()
        writer = csv.writer(buf)

        # --- header row ---
        writer.writerow(output_columns)
        line_bytes = buf.getvalue().encode("utf-8")
        total_bytes += len(line_bytes)
        yield line_bytes
        buf.seek(0)
        buf.truncate()

        # --- data rows ---
        for row in redacted_rows:
            if total_bytes >= _MAX_PAYLOAD_BYTES:
                logger.warning(
                    "pg_viewer CSV export for table %r reached 10 MB cap "
                    "after %d rows; stream closed early.",
                    table,
                    actual_row_count,
                )
                return

            encoded_cells = [_encode_cell(row.get(c)) for c in output_columns]
            writer.writerow(encoded_cells)
            line_bytes = buf.getvalue().encode("utf-8")
            total_bytes += len(line_bytes)
            yield line_bytes
            buf.seek(0)
            buf.truncate()

    return StreamingResponse(
        _generator(),
        headers=headers,
        media_type="text/csv",
    )
