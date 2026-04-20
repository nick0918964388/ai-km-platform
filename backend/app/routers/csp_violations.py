"""FastAPI router for CSP violation reports (T-046).

Endpoint
--------
POST /api/csp-violations  — public, no auth required (browsers send anonymously)

Accepts both formats:
  - Legacy: Content-Type: application/csp-report, body {"csp-report": {...}}
  - Modern: Content-Type: application/reports+json, body [{...}, ...]

Security notes
--------------
- Body capped at 16 KB (413 if exceeded).
- Only the enumerated CSP fields are stored — no cookies, referrers, or request
  bodies beyond the defined schema.
- IP resolved via XFF trust logic (reuses audit._resolve_ip pattern) using
  pg_viewer_trusted_proxy_ips allowlist.
- Malformed JSON → 400 with generic message (no stack trace).
- Rate limit: TODO — wire to require_rate_budget(60, "csp_violations", ip) once
  T-014.6 (rate-budget dependency) is merged.

Retention
---------
30-day purge cron is T-043. See quickstart.md §"CSP violation log retention".
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response, JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["csp-violations"])

# Body size cap: 16 KB
_MAX_BODY_BYTES = 16 * 1024


# ---------------------------------------------------------------------------
# IP resolution helper (mirrors audit._resolve_ip)
# ---------------------------------------------------------------------------

def _resolve_client_ip(request: Request) -> str | None:
    """Return the best-available client IP, trusting XFF only from known proxies."""
    xff = request.headers.get("x-forwarded-for")
    peer = getattr(request.client, "host", None) if request.client else None

    if xff and peer:
        try:
            from app.config import get_settings  # noqa: PLC0415
            trusted: list[str] = get_settings().pg_viewer_trusted_proxy_ips
        except Exception:
            trusted = []

        if peer in trusted:
            return xff.split(",")[0].strip()

    return peer


# ---------------------------------------------------------------------------
# CSP field extractor helpers
# ---------------------------------------------------------------------------

_CSP_FIELDS = {
    "blocked-uri",
    "effective-directive",
    "original-policy",
    "document-uri",
    "violated-directive",
    "source-file",
    "line-number",
    "status-code",
}

# Modern Report-To object field mapping (draft-ietf-httpbis-reporting-04)
_MODERN_BODY_FIELDS = {
    "blockedURL": "blocked-uri",
    "effectiveDirective": "effective-directive",
    "originalPolicy": "original-policy",
    "documentURL": "document-uri",
    "violatedDirective": "violated-directive",
    "sourceFile": "source-file",
    "lineNumber": "line-number",
    "statusCode": "status-code",
}


def _extract_legacy(report: dict[str, Any]) -> dict[str, Any]:
    """Extract canonical fields from a legacy csp-report object."""
    return {
        "blocked_uri": report.get("blocked-uri"),
        "effective_directive": report.get("effective-directive"),
        "original_policy": report.get("original-policy"),
        "document_uri": report.get("document-uri"),
        "violated_directive": report.get("violated-directive"),
        "source_file": report.get("source-file"),
        "line_number": _safe_int(report.get("line-number")),
        "status_code": _safe_int(report.get("status-code")),
    }


def _extract_modern(body: dict[str, Any]) -> dict[str, Any]:
    """Extract canonical fields from a modern Report-To body object."""
    return {
        "blocked_uri": body.get("blockedURL") or body.get("blocked-uri"),
        "effective_directive": body.get("effectiveDirective") or body.get("effective-directive"),
        "original_policy": body.get("originalPolicy") or body.get("original-policy"),
        "document_uri": body.get("documentURL") or body.get("document-uri"),
        "violated_directive": body.get("violatedDirective") or body.get("violated-directive"),
        "source_file": body.get("sourceFile") or body.get("source-file"),
        "line_number": _safe_int(body.get("lineNumber") or body.get("line-number")),
        "status_code": _safe_int(body.get("statusCode") or body.get("status-code")),
    }


def _safe_int(value: Any) -> int | None:
    """Coerce to int or return None."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Database insert helper
# ---------------------------------------------------------------------------

async def _insert_row(fields: dict[str, Any], ip: str | None, ua: str | None) -> None:
    """Insert one CSP violation row into csp_violation_log."""
    try:
        from sqlalchemy import text  # noqa: PLC0415
        from app.db.session import get_db_context  # noqa: PLC0415

        async with get_db_context() as db:
            await db.execute(
                text("""
                    INSERT INTO csp_violation_log (
                        blocked_uri, effective_directive, original_policy,
                        document_uri, violated_directive, source_file,
                        line_number, status_code, user_agent, ip_address
                    ) VALUES (
                        :blocked_uri, :effective_directive, :original_policy,
                        :document_uri, :violated_directive, :source_file,
                        :line_number, :status_code, :user_agent, :ip_address
                    )
                """),
                {**fields, "user_agent": ua, "ip_address": ip},
            )
    except Exception as exc:
        # Audit failures must never disrupt the 204 response.
        logger.warning("csp_violation_log insert failed: %s", type(exc).__name__)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/csp-violations", status_code=204)
async def receive_csp_violation(request: Request) -> Response:
    """Accept browser CSP violation reports (public — no auth).

    Returns 204 No Content on success.
    Returns 400 for malformed JSON.
    Returns 413 if body exceeds 16 KB.
    Returns 503 if Redis is down (fail-closed to prevent DB saturation).
    """
    # --- Rate limit (H-3 fix): 60 requests/min per IP, fail-closed on Redis down ---
    ip_for_rate = _resolve_client_ip(request) or "anon"
    try:
        from app.services.pg_viewer.rate_limiter import _check_rate  # noqa: PLC0415
        await _check_rate("csp", ip_for_rate, 60)
    except Exception as rl_exc:
        from fastapi import HTTPException  # noqa: PLC0415
        if isinstance(rl_exc, HTTPException):
            return JSONResponse(
                status_code=rl_exc.status_code,
                content={"detail": rl_exc.detail},
            )
        # Redis down or other error — fail-closed (503 beats DB saturation).
        return JSONResponse(
            status_code=503,
            content={"detail": "rate limiter unavailable"},
        )

    # --- Body size cap ---
    body_bytes = await request.body()
    if len(body_bytes) > _MAX_BODY_BYTES:
        return JSONResponse(
            status_code=413,
            content={"detail": "CSP report body exceeds size limit"},
        )

    # --- Parse JSON ---
    try:
        payload = json.loads(body_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(
            status_code=400,
            content={"detail": "Invalid JSON in CSP report"},
        )

    # --- Resolve client metadata ---
    ip = _resolve_client_ip(request)
    ua = request.headers.get("user-agent")

    # --- Determine format and extract rows ---
    content_type = request.headers.get("content-type", "")

    rows: list[dict[str, Any]] = []

    if isinstance(payload, list):
        # Modern application/reports+json — array of Report objects.
        for item in payload:
            if not isinstance(item, dict):
                continue
            body = item.get("body") or {}
            if not isinstance(body, dict):
                body = {}
            rows.append(_extract_modern(body))

    elif isinstance(payload, dict):
        legacy_report = payload.get("csp-report")
        if isinstance(legacy_report, dict):
            # Legacy application/csp-report format.
            rows.append(_extract_legacy(legacy_report))
        else:
            # Fallback: treat top-level dict as a modern body.
            rows.append(_extract_modern(payload))
    else:
        return JSONResponse(
            status_code=400,
            content={"detail": "Unexpected CSP report structure"},
        )

    # --- Persist rows ---
    for row_fields in rows:
        await _insert_row(row_fields, ip=ip, ua=ua)

    return Response(status_code=204)
