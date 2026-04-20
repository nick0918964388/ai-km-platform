"""
Feature flag for Maximo tool-based query routing.

Set env var MAXIMO_TOOL_ROUTER_ENABLED=false to bypass router entirely
(all queries go to fallback/nl2sql). Default: true.

This is the production rollback channel for 012-maximo-query-tools.
"""
import os
import logging

logger = logging.getLogger(__name__)

_FLAG_NAME = "MAXIMO_TOOL_ROUTER_ENABLED"
_TRUE_VALUES = frozenset({"true", "1", "yes", "on"})
_FALSE_VALUES = frozenset({"false", "0", "no", "off"})


def is_tool_router_enabled() -> bool:
    """
    Read MAXIMO_TOOL_ROUTER_ENABLED env var.

    - Default (env var unset): True
    - "true"/"1"/"yes"/"on" (case insensitive): True
    - "false"/"0"/"no"/"off" (case insensitive): False
    - Any other value: log warning + treat as True (safe default — router runs)
    """
    raw = os.getenv(_FLAG_NAME)
    if raw is None:
        return True

    normalized = raw.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False

    logger.warning(
        "Invalid %s value %r; treating as enabled. Use 'true'/'false'.",
        _FLAG_NAME, raw,
    )
    return True
