"""Admin API endpoints for RAG metrics and monitoring."""
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.auth import require_admin
from app.db.session import get_db_context

router = APIRouter(tags=["admin"])


@router.get("/admin/rag-metrics")
async def get_rag_metrics():
    """Return last 7 days of RAG search quality stats grouped by date."""
    async with get_db_context() as session:
        result = await session.execute(
            text("""
                SELECT
                    created_at::date AS date,
                    COUNT(*) AS total_searches,
                    ROUND(AVG(avg_score)::numeric, 4) AS avg_score,
                    ROUND(AVG(duration_ms)::numeric, 0) AS avg_duration,
                    COUNT(*) FILTER (WHERE quality = 'good') AS good_count,
                    COUNT(*) FILTER (WHERE quality = 'low') AS low_count,
                    COUNT(*) FILTER (WHERE quality = 'none') AS none_count
                FROM rag_search_log
                WHERE created_at >= NOW() - INTERVAL '7 days'
                GROUP BY created_at::date
                ORDER BY date DESC
            """)
        )
        rows = result.fetchall()

    return [
        {
            "date": str(row.date),
            "total_searches": row.total_searches,
            "avg_score": float(row.avg_score) if row.avg_score else 0,
            "avg_duration": int(row.avg_duration) if row.avg_duration else 0,
            "quality_distribution": {
                "good": row.good_count,
                "low": row.low_count,
                "none": row.none_count,
            },
        }
        for row in rows
    ]


@router.get("/admin/audit-logs")
async def get_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type_filter: Optional[str] = Query(None),
):
    """Return paginated audit logs from both SQL and RAG queries."""
    offset = (page - 1) * page_size

    sql_select = """
        SELECT id, 'sql' as type, user_email, question as query,
               sql_generated as detail, tables_accessed,
               row_count, execution_ms as duration_ms, mode,
               cached, created_at, request_id
        FROM query_audit_log
    """
    rag_select = """
        SELECT id, 'rag' as type, NULL as user_email, query,
               search_query as detail, NULL as tables_accessed,
               source_count as row_count, duration_ms,
               quality as mode, rewrite_used as cached, created_at, request_id
        FROM rag_search_log
    """

    if type_filter == "sql":
        data_query = f"{sql_select} ORDER BY created_at DESC LIMIT :page_size OFFSET :offset"
        count_query = "SELECT COUNT(*) FROM query_audit_log"
    elif type_filter == "rag":
        data_query = f"{rag_select} ORDER BY created_at DESC LIMIT :page_size OFFSET :offset"
        count_query = "SELECT COUNT(*) FROM rag_search_log"
    else:
        data_query = f"""
            SELECT * FROM (
                {sql_select}
                UNION ALL
                {rag_select}
            ) combined
            ORDER BY created_at DESC
            LIMIT :page_size OFFSET :offset
        """
        count_query = """
            SELECT (SELECT COUNT(*) FROM query_audit_log)
                 + (SELECT COUNT(*) FROM rag_search_log)
        """

    try:
        async with get_db_context() as session:
            count_result = await session.execute(text(count_query))
            total = count_result.scalar() or 0

            result = await session.execute(
                text(data_query), {"page_size": page_size, "offset": offset}
            )
            rows = result.fetchall()
            columns = result.keys()

        logs = []
        for row in rows:
            row_dict = dict(zip(columns, row))
            row_dict["created_at"] = str(row_dict["created_at"]) if row_dict["created_at"] else None
            if row_dict.get("tables_accessed") and isinstance(row_dict["tables_accessed"], list):
                row_dict["tables_accessed"] = row_dict["tables_accessed"]
            logs.append(row_dict)

        return JSONResponse(content={
            "logs": logs,
            "total": total,
            "page": page,
            "page_size": page_size,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/call-traces/{request_id}")
async def get_call_traces(request_id: str):
    """Return all LLM call traces for a given request_id."""
    try:
        async with get_db_context() as session:
            result = await session.execute(
                text("SELECT * FROM call_traces WHERE request_id = :rid ORDER BY id"),
                {"rid": request_id},
            )
            traces = [dict(r._mapping) for r in result.fetchall()]
            for t in traces:
                if t.get("created_at"):
                    t["created_at"] = str(t["created_at"])
        return traces
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/audit-logs/{log_id}")
async def get_audit_log_detail(
    log_id: int,
    type: str = Query(..., regex="^(sql|rag)$"),
):
    """Return detailed info for a single audit log entry."""
    try:
        async with get_db_context() as session:
            if type == "sql":
                result = await session.execute(
                    text("SELECT * FROM query_audit_log WHERE id = :id"),
                    {"id": log_id},
                )
            else:
                result = await session.execute(
                    text("SELECT * FROM rag_search_log WHERE id = :id"),
                    {"id": log_id},
                )

            row = result.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Log not found")

            columns = result.keys()
            detail = dict(zip(columns, row))
            detail["type"] = type
            detail["created_at"] = str(detail["created_at"]) if detail.get("created_at") else None

        return JSONResponse(content=detail)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Column Label Management ──────────────────────────────────────────

@router.get("/admin/column-labels")
async def get_column_labels():
    """Get all custom column labels."""
    async with get_db_context() as session:
        result = await session.execute(
            text("SELECT column_name, label FROM custom_column_labels ORDER BY column_name")
        )
        return [{"column_name": r[0], "label": r[1]} for r in result.fetchall()]


@router.post("/admin/column-labels")
async def upsert_column_label(data: dict):
    """Create or update a column label."""
    async with get_db_context() as session:
        await session.execute(
            text("""INSERT INTO custom_column_labels (column_name, label, updated_at)
                    VALUES (:name, :label, NOW())
                    ON CONFLICT (column_name) DO UPDATE SET label = :label, updated_at = NOW()"""),
            {"name": data["column_name"], "label": data["label"]},
        )
    return {"status": "ok"}


@router.delete("/admin/column-labels/{column_name}")
async def delete_column_label(column_name: str):
    """Delete a column label."""
    async with get_db_context() as session:
        await session.execute(
            text("DELETE FROM custom_column_labels WHERE column_name = :name"),
            {"name": column_name},
        )
    return {"status": "ok"}


# ── Table Column Config ───────────────────────────────────────────────

@router.get("/admin/table-columns")
async def get_table_column_configs():
    """Get all table column configurations grouped by table."""
    async with get_db_context() as session:
        result = await session.execute(text(
            "SELECT table_name, column_name, display_order FROM table_column_config ORDER BY table_name, display_order"
        ))
        configs = {}
        for r in result.fetchall():
            table = r[0]
            if table not in configs:
                configs[table] = []
            configs[table].append({"column_name": r[1], "display_order": r[2]})
        return configs


@router.post("/admin/table-columns")
async def save_table_column_config(data: dict):
    """Save column config for a table. data = {table_name: str, columns: [{column_name, display_order}]}"""
    table_name = data.get("table_name")
    columns = data.get("columns", [])
    async with get_db_context() as session:
        await session.execute(text("DELETE FROM table_column_config WHERE table_name = :t"), {"t": table_name})
        for col in columns:
            await session.execute(text(
                "INSERT INTO table_column_config (table_name, column_name, display_order) VALUES (:t, :c, :o)"
            ), {"t": table_name, "c": col["column_name"], "o": col.get("display_order", 0)})
    return {"status": "ok"}


@router.get("/admin/table-columns/{table_name}/available")
async def get_available_columns(table_name: str):
    """Get all available columns for a table from information_schema."""
    async with get_db_context() as session:
        result = await session.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = :t ORDER BY ordinal_position"
        ), {"t": table_name})
        return [{"column_name": r[0], "data_type": r[1]} for r in result.fetchall()]


# ── System Settings ──────────────────────────────────────────────────

@router.get("/admin/settings")
async def get_system_settings():
    """Get all system settings."""
    from app.services import settings_service
    return await settings_service.get_all_settings()


@router.post("/admin/settings")
async def update_system_settings(data: dict):
    """Update system settings. Accepts {key: value, ...}."""
    from app.services import settings_service
    from app.config import invalidate_settings

    for key, value in data.items():
        await settings_service.set_setting(key, str(value))

    invalidate_settings()

    return {"status": "ok"}


# ── Pending SQL Examples ─────────────────────────────────────────────

class ReviewRequest(BaseModel):
    notes: Optional[str] = None


@router.get("/admin/pending-examples")
async def list_pending_examples(
    status: str = Query("pending"),
    admin: dict = Depends(require_admin),
):
    async with get_db_context() as session:
        result = await session.execute(
            text("SELECT * FROM pending_sql_examples WHERE status = :s ORDER BY submitted_at DESC"),
            {"s": status},
        )
        rows = result.fetchall()
        columns = result.keys()
    return [
        {k: str(v) if k.endswith("_at") and v else v for k, v in zip(columns, row)}
        for row in rows
    ]


@router.put("/admin/pending-examples/{example_id}/approve")
async def approve_pending_example(
    example_id: int,
    body: ReviewRequest = ReviewRequest(),
    admin: dict = Depends(require_admin),
):
    async with get_db_context() as session:
        row = await session.execute(
            text("SELECT question, sql_query, status FROM pending_sql_examples WHERE id = :id"),
            {"id": example_id},
        )
        pending = row.fetchone()
        if not pending:
            raise HTTPException(404, "Example not found")
        if pending[2] != "pending":
            raise HTTPException(400, f"Already {pending[2]}")

        await session.execute(
            text("""
                INSERT INTO nl_sql_examples (question, sql_query, verified, tag)
                VALUES (:q, :sql, true, 'user_feedback')
            """),
            {"q": pending[0], "sql": pending[1]},
        )
        await session.execute(
            text("""
                UPDATE pending_sql_examples
                SET status = 'approved', reviewed_by = :by, reviewed_at = NOW(), notes = :notes
                WHERE id = :id
            """),
            {"id": example_id, "by": admin.get("email", "admin"), "notes": body.notes},
        )
    return {"status": "approved", "id": example_id}


@router.put("/admin/pending-examples/{example_id}/reject")
async def reject_pending_example(
    example_id: int,
    body: ReviewRequest = ReviewRequest(),
    admin: dict = Depends(require_admin),
):
    async with get_db_context() as session:
        row = await session.execute(
            text("SELECT status FROM pending_sql_examples WHERE id = :id"),
            {"id": example_id},
        )
        pending = row.fetchone()
        if not pending:
            raise HTTPException(404, "Example not found")
        if pending[0] != "pending":
            raise HTTPException(400, f"Already {pending[0]}")

        await session.execute(
            text("""
                UPDATE pending_sql_examples
                SET status = 'rejected', reviewed_by = :by, reviewed_at = NOW(), notes = :notes
                WHERE id = :id
            """),
            {"id": example_id, "by": admin.get("email", "admin"), "notes": body.notes},
        )
    return {"status": "rejected", "id": example_id}
