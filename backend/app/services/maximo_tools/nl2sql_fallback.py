"""Adapt existing MaximoNL2SQL service to router's FallbackFn interface."""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.maximo_tools.base import UserContext

logger = logging.getLogger(__name__)


class NL2SQLFallback:
    """
    Wraps MaximoNL2SQL.query() into the FallbackFn signature expected by MaximoQueryRouter.

    The AsyncSession is captured from the request context (per-request dependency).

    After __call__ returns, the full NL2SQL result is accessible via .last_result
    so the endpoint can merge backward-compat fields (data, columns, sql, etc.).

    Note: spec FR-009 — passes original user query unmodified.
    """

    def __init__(self, db: AsyncSession, user_context: dict):
        self._db = db
        self._user_context = user_context  # raw auth dict for MaximoNL2SQL compat
        self.last_result: dict = {}        # side-channel for backward-compat merge

    async def __call__(self, query: str, user_ctx: UserContext, query_id: UUID) -> dict:
        """
        Call existing NL2SQL pipeline.

        Returns dict with keys the router expects:
          rows      — list[dict]
          row_count — int
          chart_hint — dict | None
          debug     — dict

        Full NL2SQL result is also stored on self.last_result for backward-compat use.
        """
        from app.services.maximo_nl2sql import MaximoNL2SQL

        service = MaximoNL2SQL(self._db)

        # FR-009: pass original query, no rewrite
        result = await service.query(
            question=query,
            mode="accurate",
            user_context=self._user_context,
            conversation_history=[],
        )

        # Side-channel: endpoint reads this after route() returns
        self.last_result = result

        data = result.get("data") or []

        return {
            "rows": data,
            "row_count": result.get("row_count", 0),
            "chart_hint": result.get("chart_suggestion"),
            "debug": {
                "sql": result.get("sql"),
                "llm_stop_reason": None,
                "fallback_reason": None,  # router overwrites this
            },
        }
