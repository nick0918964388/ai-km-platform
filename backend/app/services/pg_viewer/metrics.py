"""Observability metrics for pg_viewer endpoints (T-045).

Emits two metrics when ``prometheus_client`` is installed:
  - Histogram ``pg_viewer_request_duration_seconds{endpoint, status}``
  - Counter   ``pg_viewer_requests_total{endpoint, status}``

Label hygiene (post-critic R2 M4 security):
  - ``endpoint`` = static route pattern name (e.g. ``"tables_list"``) — NOT the
    resolved table name (table names can be PII / high cardinality).
  - ``status``   = HTTP status code as string (``"200"``, ``"400"``, etc.).
  - No ``user_id`` label (PII + high cardinality).
  - No ``table`` label (potential PII disclosure, high cardinality).

Maximum cardinality: 6 endpoints × ~7 status codes = 42 series — safe.

Fallback mode
-------------
When ``prometheus_client`` is not importable (e.g. not installed), every call
to ``record_request`` emits an INFO log instead::

    pg_viewer endpoint=tables_list status=200 ms=12

Public API
----------
``record_request(endpoint: str, status: int, elapsed_s: float) -> None``
    Thread-safe, sync, never raises.

``_REQUEST_DURATION`` / ``_REQUEST_TOTAL``
    Module-level metric objects (only present when prometheus_client is
    installed).  Exposed so tests can read sample values.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics — stub when library absent
# ---------------------------------------------------------------------------

try:
    from prometheus_client import (  # type: ignore[import]
        CollectorRegistry,
        Counter,
        Histogram,
        REGISTRY as _DEFAULT_REGISTRY,
    )

    # Use the default registry in production.  Tests that need isolation
    # should reload this module with a patched registry (see test_observability.py).
    _REQUEST_DURATION = Histogram(
        "pg_viewer_request_duration_seconds",
        "Duration of pg_viewer endpoint requests in seconds",
        labelnames=["endpoint", "status"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )

    _REQUEST_TOTAL = Counter(
        "pg_viewer_requests_total",
        "Total number of pg_viewer endpoint requests",
        labelnames=["endpoint", "status"],
    )

    def record_request(endpoint: str, status: int, elapsed_s: float) -> None:
        """Observe histogram + increment counter for one completed request."""
        status_str = str(status)
        _REQUEST_DURATION.labels(endpoint=endpoint, status=status_str).observe(elapsed_s)
        _REQUEST_TOTAL.labels(endpoint=endpoint, status=status_str).inc()

except ImportError:
    def record_request(  # type: ignore[misc]
        endpoint: str, status: int, elapsed_s: float
    ) -> None:
        """Fallback: emit INFO log when prometheus_client is unavailable."""
        elapsed_ms = int(elapsed_s * 1000)
        logger.info("pg_viewer endpoint=%s status=%s ms=%s", endpoint, status, elapsed_ms)
