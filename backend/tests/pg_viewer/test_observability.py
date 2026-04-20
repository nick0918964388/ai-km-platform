"""Unit tests for pg_viewer observability metrics (T-045).

Test matrix
-----------
1. Endpoint call → histogram observes duration (bucket sample > 0).
2. Counter increments on each call.
3. Label names across all registered pg_viewer metrics contain NO
   ``user_id`` and NO ``table`` (static route name only; no PII leakage).
4. Fallback log-mode: when prometheus_client is not importable (mocked
   ImportError), ``logger.info`` fires with ``"pg_viewer endpoint=..."``
   prefix on each record_request call.

All tests are pure unit tests — no live DB, no Redis, no FastAPI app required.

Run with::

    pytest backend/tests/pg_viewer/test_observability.py -v
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import sys
import types
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_BACKEND_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def _load_metrics_fresh(module_key: str = "app.services.pg_viewer.metrics") -> types.ModuleType:
    """Load metrics.py with a fresh CollectorRegistry so each test is isolated.

    prometheus_client raises ValueError if you register the same metric name
    twice in the same registry.  We work around this by injecting a brand-new
    CollectorRegistry into prometheus_client before executing the module, so
    the Histogram/Counter constructors attach to a throwaway registry rather
    than the global default one.

    The returned module exposes ``_REQUEST_DURATION`` and ``_REQUEST_TOTAL``
    bound to that isolated registry.
    """
    try:
        from prometheus_client import CollectorRegistry  # type: ignore[import]
    except ImportError:
        pytest.skip("prometheus_client not installed")

    # Remove any previously loaded version.
    for key in list(sys.modules.keys()):
        if "pg_viewer.metrics" in key or key == module_key:
            del sys.modules[key]

    abs_path = os.path.join(
        _BACKEND_DIR,
        "app", "services", "pg_viewer", "metrics.py",
    )
    spec = importlib.util.spec_from_file_location(module_key, abs_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[module_key] = mod

    # Patch prometheus_client so Histogram/Counter use an isolated registry.
    fresh_registry = CollectorRegistry()
    import prometheus_client as _prom_client  # type: ignore[import]

    original_histogram = _prom_client.Histogram
    original_counter = _prom_client.Counter

    def _patched_histogram(*args, **kwargs):
        kwargs.setdefault("registry", fresh_registry)
        return original_histogram(*args, **kwargs)

    def _patched_counter(*args, **kwargs):
        kwargs.setdefault("registry", fresh_registry)
        return original_counter(*args, **kwargs)

    with (
        patch.object(_prom_client, "Histogram", side_effect=_patched_histogram),
        patch.object(_prom_client, "Counter", side_effect=_patched_counter),
    ):
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

    return mod


# ---------------------------------------------------------------------------
# Test 1 — Histogram observes duration
# ---------------------------------------------------------------------------


class TestHistogramObservesDuration:
    """record_request → histogram bucket count increases."""

    def test_histogram_sample_recorded(self):
        """After one call, _sum on the histogram label set must be > 0."""
        try:
            import prometheus_client  # noqa: F401
        except ImportError:
            pytest.skip("prometheus_client not installed — histogram test skipped")

        metrics = _load_metrics_fresh()
        metrics.record_request("tables_list", 200, 0.042)

        # Collect all samples from the histogram
        samples = list(metrics._REQUEST_DURATION.collect())
        assert samples, "Histogram returned no metric families"

        found_sum = False
        for family in samples:
            for sample in family.samples:
                if (
                    sample.name.endswith("_sum")
                    and sample.labels.get("endpoint") == "tables_list"
                    and sample.labels.get("status") == "200"
                ):
                    assert sample.value == pytest.approx(0.042, abs=1e-6)
                    found_sum = True

        assert found_sum, "No _sum sample found for endpoint=tables_list status=200"

    def test_histogram_bucket_populated(self):
        """After a ~50ms call, at least one bucket should be populated."""
        try:
            import prometheus_client  # noqa: F401
        except ImportError:
            pytest.skip("prometheus_client not installed — histogram test skipped")

        metrics = _load_metrics_fresh()
        metrics.record_request("sql_editor", 200, 0.050)

        found_bucket = False
        for family in metrics._REQUEST_DURATION.collect():
            for sample in family.samples:
                if (
                    sample.name.endswith("_bucket")
                    and sample.labels.get("endpoint") == "sql_editor"
                    and sample.labels.get("status") == "200"
                    and sample.value > 0
                ):
                    found_bucket = True
                    break

        assert found_bucket, "No populated bucket found for sql_editor 200 after 50ms call"


# ---------------------------------------------------------------------------
# Test 2 — Counter increments
# ---------------------------------------------------------------------------


class TestCounterIncrements:
    """record_request → counter value increases by 1 per call."""

    def test_counter_single_call(self):
        """One call → counter for that label set == 1."""
        try:
            import prometheus_client  # noqa: F401
        except ImportError:
            pytest.skip("prometheus_client not installed — counter test skipped")

        metrics = _load_metrics_fresh()
        metrics.record_request("audit_list", 200, 0.010)

        total = None
        for family in metrics._REQUEST_TOTAL.collect():
            for sample in family.samples:
                if (
                    sample.name == "pg_viewer_requests_total"
                    and sample.labels.get("endpoint") == "audit_list"
                    and sample.labels.get("status") == "200"
                ):
                    total = sample.value
                    break

        assert total == 1.0, f"Expected counter == 1, got {total}"

    def test_counter_multiple_calls(self):
        """Three calls → counter == 3."""
        try:
            import prometheus_client  # noqa: F401
        except ImportError:
            pytest.skip("prometheus_client not installed — counter test skipped")

        metrics = _load_metrics_fresh()
        for _ in range(3):
            metrics.record_request("table_rows", 400, 0.005)

        total = None
        for family in metrics._REQUEST_TOTAL.collect():
            for sample in family.samples:
                if (
                    sample.name == "pg_viewer_requests_total"
                    and sample.labels.get("endpoint") == "table_rows"
                    and sample.labels.get("status") == "400"
                ):
                    total = sample.value
                    break

        assert total == 3.0, f"Expected counter == 3, got {total}"

    def test_counter_increments_across_statuses(self):
        """Counters for different status codes are independent."""
        try:
            import prometheus_client  # noqa: F401
        except ImportError:
            pytest.skip("prometheus_client not installed — counter test skipped")

        metrics = _load_metrics_fresh()
        metrics.record_request("table_schema", 200, 0.020)
        metrics.record_request("table_schema", 404, 0.001)
        metrics.record_request("table_schema", 404, 0.001)

        counts: dict[str, float] = {}
        for family in metrics._REQUEST_TOTAL.collect():
            for sample in family.samples:
                # Filter to the _total sample only; skip _created (timestamp) samples.
                if (
                    sample.name == "pg_viewer_requests_total"
                    and sample.labels.get("endpoint") == "table_schema"
                ):
                    counts[sample.labels.get("status", "")] = sample.value

        assert counts.get("200") == 1.0
        assert counts.get("404") == 2.0


# ---------------------------------------------------------------------------
# Test 3 — Label hygiene: no user_id, no table name in label names
# ---------------------------------------------------------------------------


class TestLabelHygiene:
    """Registered metric label names must NOT include 'user_id' or 'table'."""

    def test_no_user_id_label(self):
        """No label called 'user_id' on any pg_viewer metric."""
        try:
            import prometheus_client  # noqa: F401
        except ImportError:
            pytest.skip("prometheus_client not installed — label hygiene test skipped")

        metrics = _load_metrics_fresh()
        # Trigger at least one observation so the metrics exist in the registry
        metrics.record_request("tables_list", 200, 0.001)

        for family in metrics._REQUEST_DURATION.collect():
            for sample in family.samples:
                label_names = list(sample.labels.keys())
                assert "user_id" not in label_names, (
                    f"PII label 'user_id' found in histogram sample labels: {label_names}"
                )

        for family in metrics._REQUEST_TOTAL.collect():
            for sample in family.samples:
                label_names = list(sample.labels.keys())
                assert "user_id" not in label_names, (
                    f"PII label 'user_id' found in counter sample labels: {label_names}"
                )

    def test_no_table_label(self):
        """No label called 'table' on any pg_viewer metric."""
        try:
            import prometheus_client  # noqa: F401
        except ImportError:
            pytest.skip("prometheus_client not installed — label hygiene test skipped")

        metrics = _load_metrics_fresh()
        metrics.record_request("table_rows", 200, 0.015)

        for family in metrics._REQUEST_DURATION.collect():
            for sample in family.samples:
                label_names = list(sample.labels.keys())
                assert "table" not in label_names, (
                    f"High-cardinality/PII label 'table' found in histogram sample labels: {label_names}"
                )

        for family in metrics._REQUEST_TOTAL.collect():
            for sample in family.samples:
                label_names = list(sample.labels.keys())
                assert "table" not in label_names, (
                    f"High-cardinality/PII label 'table' found in counter sample labels: {label_names}"
                )

    def test_only_endpoint_and_status_labels(self):
        """The only label names present are 'endpoint' and 'status'."""
        try:
            import prometheus_client  # noqa: F401
        except ImportError:
            pytest.skip("prometheus_client not installed — label hygiene test skipped")

        metrics = _load_metrics_fresh()
        metrics.record_request("sql_editor", 200, 0.030)

        allowed = {"endpoint", "status", "le"}  # 'le' is the histogram upper bound label

        for family in metrics._REQUEST_DURATION.collect():
            for sample in family.samples:
                extra = set(sample.labels.keys()) - allowed
                assert not extra, (
                    f"Unexpected label names in histogram: {extra}. "
                    "Only 'endpoint', 'status', 'le' are allowed."
                )

        for family in metrics._REQUEST_TOTAL.collect():
            for sample in family.samples:
                extra = set(sample.labels.keys()) - {"endpoint", "status"}
                assert not extra, (
                    f"Unexpected label names in counter: {extra}. "
                    "Only 'endpoint' and 'status' are allowed."
                )


# ---------------------------------------------------------------------------
# Test 4 — Fallback log mode when prometheus_client is not importable
# ---------------------------------------------------------------------------


class TestFallbackLogMode:
    """When prometheus_client raises ImportError, record_request logs via logger.info."""

    def _load_metrics_without_prometheus(self) -> types.ModuleType:
        """Load metrics.py with prometheus_client blocked from import."""
        module_key = "app.services.pg_viewer.metrics_fallback_test"
        for key in list(sys.modules.keys()):
            if "metrics_fallback_test" in key or key == module_key:
                del sys.modules[key]

        abs_path = os.path.join(
            _BACKEND_DIR,
            "app", "services", "pg_viewer", "metrics.py",
        )
        spec = importlib.util.spec_from_file_location(module_key, abs_path)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]

        # Patch prometheus_client as unimportable before exec
        original_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

        def _blocking_import(name, *args, **kwargs):
            if name == "prometheus_client":
                raise ImportError("prometheus_client not available (mocked)")
            return original_import(name, *args, **kwargs)

        sys.modules[module_key] = mod
        with patch("builtins.__import__", side_effect=_blocking_import):
            spec.loader.exec_module(mod)  # type: ignore[union-attr]

        return mod

    def test_fallback_logger_info_fires(self, caplog):
        """record_request in fallback mode emits INFO log with correct prefix."""
        mod = self._load_metrics_without_prometheus()

        with caplog.at_level(logging.INFO, logger="app.services.pg_viewer.metrics_fallback_test"):
            mod.record_request("tables_list", 200, 0.025)

        assert any(
            "pg_viewer endpoint=tables_list" in rec.message
            for rec in caplog.records
        ), f"Expected 'pg_viewer endpoint=tables_list' in log; got: {[r.message for r in caplog.records]}"

    def test_fallback_log_contains_status(self, caplog):
        """Fallback log includes the status code."""
        mod = self._load_metrics_without_prometheus()

        with caplog.at_level(logging.INFO, logger="app.services.pg_viewer.metrics_fallback_test"):
            mod.record_request("sql_editor", 400, 0.003)

        assert any(
            "status=400" in rec.message
            for rec in caplog.records
        ), f"Expected 'status=400' in log; got: {[r.message for r in caplog.records]}"

    def test_fallback_log_contains_ms(self, caplog):
        """Fallback log includes elapsed time in ms."""
        mod = self._load_metrics_without_prometheus()

        with caplog.at_level(logging.INFO, logger="app.services.pg_viewer.metrics_fallback_test"):
            mod.record_request("audit_list", 200, 0.050)

        assert any(
            "ms=50" in rec.message
            for rec in caplog.records
        ), f"Expected 'ms=50' in log; got: {[r.message for r in caplog.records]}"

    def test_fallback_fires_for_each_endpoint(self, caplog):
        """Fallback emits one log line per record_request call."""
        mod = self._load_metrics_without_prometheus()

        endpoints = ["tables_list", "table_schema", "table_rows", "table_export",
                     "audit_list", "sql_editor"]

        with caplog.at_level(logging.INFO, logger="app.services.pg_viewer.metrics_fallback_test"):
            for ep in endpoints:
                mod.record_request(ep, 200, 0.010)

        logged_endpoints = [
            rec.message.split("endpoint=")[1].split(" ")[0]
            for rec in caplog.records
            if "pg_viewer endpoint=" in rec.message
        ]
        assert logged_endpoints == endpoints, (
            f"Expected one log per endpoint in order; got: {logged_endpoints}"
        )
