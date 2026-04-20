"""Anthropic tool_use wrapper — isolates SDK for mocking in tests."""
from __future__ import annotations

import logging
from typing import Any

from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

# claude-sonnet-4-6 (research.md R1 決策)
_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 1024


class AnthropicToolUseCaller:
    """Thin wrapper around anthropic.messages.create for tool_use."""

    def __init__(self, api_key: str | None = None):
        self._client = AsyncAnthropic(api_key=api_key) if api_key else AsyncAnthropic()

    async def __call__(self, system: str, user_query: str, tools: list[dict]) -> Any:
        """
        Call Claude with tools. Returns raw anthropic response object.
        Router extracts stop_reason / content[].type / content[].name|input.

        IMPORTANT (critic HIGH-1): user_query 放在 messages[].content，
        **不**串到 system。防止 prompt injection。
        """
        response = await self._client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user_query}],
            tools=tools,
        )
        return response
