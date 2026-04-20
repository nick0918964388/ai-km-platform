"""Unit tests for pg_viewer redaction module (T-013).

All tests are pure-unit: no DB connection required.

Acceptance criteria:
  1. `users_public` result rows never contain `password_hash` (layer-2 check).
  2. `system_settings` row with `key='openai_api_key'` → `value='***'`; other rows untouched.
  3. Input list is not mutated — caller's original list is unchanged after apply_redaction().
  4. Import-time scan is skipped when PG_VIEWER_DATABASE_URL is empty (env not set).

Import strategy:
  We load redaction.py directly via importlib.util.spec_from_file_location so
  that app/services/pg_viewer/__init__.py (which contains the JWT startup guard)
  is NOT executed.  This mirrors how other T-013-scope unit tests work and is
  the correct approach for a module designed to be importable independently.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixture: load redaction module directly (no __init__ side effects)
# ---------------------------------------------------------------------------

_REDACTION_PATH = (
    Path(__file__).parent.parent.parent  # backend/
    / "app" / "services" / "pg_viewer" / "redaction.py"
)


def _load_redaction_module(monkeypatch):
    """Load redaction.py directly, bypassing pg_viewer/__init__.py.

    Also ensures PG_VIEWER_DATABASE_URL is absent so the import-time schema
    scan is skipped.
    """
    monkeypatch.delenv("PG_VIEWER_DATABASE_URL", raising=False)

    mod_name = "app.services.pg_viewer.redaction_isolated"
    # Always reload so env patches take effect.
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    spec = importlib.util.spec_from_file_location(mod_name, str(_REDACTION_PATH))
    assert spec is not None, f"Cannot find {_REDACTION_PATH}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Test 1: users_public rows never contain password_hash
# ---------------------------------------------------------------------------

class TestUsersPublicNoPasswordHash:
    """users_public exposes only safe columns (id, email, display_name, ...).
    apply_redaction on 'users_public' must not return password_hash because the
    users_public VIEW definition excludes that column — this test documents and
    confirms the layer-2 invariant.
    """

    def test_users_public_clean_row_has_no_password_hash(self, monkeypatch):
        """A normal users_public row does not contain password_hash.

        apply_redaction passes through only the keys that are present in the
        input; since the view never projects password_hash, it cannot appear.
        """
        m = _load_redaction_module(monkeypatch)

        # Simulate a row as returned by `SELECT * FROM users_public`
        # (view columns: id, email, display_name, account_level, created_at, last_login_at)
        rows_in = [
            {
                "id": "user-uuid-001",
                "email": "alice@example.com",
                "display_name": "Alice",
                "account_level": "admin",
                "created_at": "2026-01-01T00:00:00Z",
                "last_login_at": "2026-04-20T08:00:00Z",
            }
        ]
        out_rows, col_meta = m.apply_redaction(rows_in, "users_public")

        assert len(out_rows) == 1
        row = out_rows[0]
        assert "password_hash" not in row, (
            "password_hash must not appear in users_public result — "
            "view definition excludes it; layer-2 confirms the key is absent."
        )
        assert row["email"] == "alice@example.com"

    def test_users_public_password_hash_not_in_hidden_columns(self, monkeypatch):
        """('users_public', 'password_hash') is not in HIDDEN_COLUMNS because
        the primary defense is the L5 REVOKE + view definition."""
        m = _load_redaction_module(monkeypatch)

        assert ("users_public", "password_hash") not in m.HIDDEN_COLUMNS, (
            "users_public.password_hash should not be in HIDDEN_COLUMNS — "
            "it is defended by L5 REVOKE on the raw `users` table and the "
            "view definition that excludes the column."
        )


# ---------------------------------------------------------------------------
# Test 2: system_settings masking
# ---------------------------------------------------------------------------

class TestSystemSettingsRedaction:
    """system_settings rows with sensitive keys must have value='***'."""

    def test_openai_api_key_masked(self, monkeypatch):
        """Row with key='openai_api_key' → value becomes '***'."""
        m = _load_redaction_module(monkeypatch)

        rows_in = [
            {"key": "openai_api_key", "value": "sk-super-secret-key-12345"},
        ]
        out_rows, col_meta = m.apply_redaction(rows_in, "system_settings")

        assert len(out_rows) == 1
        assert out_rows[0]["value"] == "***", (
            f"Expected value='***', got {out_rows[0]['value']!r}"
        )

    def test_jwt_secret_masked(self, monkeypatch):
        """Row with key='jwt_secret' → value becomes '***'."""
        m = _load_redaction_module(monkeypatch)

        rows_in = [{"key": "jwt_secret", "value": "very-secret-jwt-value"}]
        out_rows, _ = m.apply_redaction(rows_in, "system_settings")
        assert out_rows[0]["value"] == "***"

    def test_other_rows_untouched(self, monkeypatch):
        """Rows with non-sensitive keys must pass through unchanged."""
        m = _load_redaction_module(monkeypatch)

        rows_in = [
            {"key": "app_name", "value": "AIKM Platform"},
            {"key": "max_upload_size_mb", "value": "100"},
        ]
        out_rows, _ = m.apply_redaction(rows_in, "system_settings")

        assert out_rows[0]["value"] == "AIKM Platform"
        assert out_rows[1]["value"] == "100"

    def test_mixed_rows(self, monkeypatch):
        """Mixed sensitive + safe rows: only sensitive ones are masked."""
        m = _load_redaction_module(monkeypatch)

        rows_in = [
            {"key": "app_name", "value": "AIKM"},
            {"key": "openai_api_key", "value": "sk-secret"},
            {"key": "db_host", "value": "postgres"},
            {"key": "jwt_secret", "value": "mysecret"},
        ]
        out_rows, col_meta = m.apply_redaction(rows_in, "system_settings")

        assert len(out_rows) == 4
        assert out_rows[0]["value"] == "AIKM"
        assert out_rows[1]["value"] == "***"
        assert out_rows[2]["value"] == "postgres"
        assert out_rows[3]["value"] == "***"

    def test_substring_match_in_key(self, monkeypatch):
        """Key containing 'password' as a substring triggers masking."""
        m = _load_redaction_module(monkeypatch)

        rows_in = [{"key": "smtp_password", "value": "p@$$w0rd"}]
        out_rows, _ = m.apply_redaction(rows_in, "system_settings")
        assert out_rows[0]["value"] == "***"

    def test_column_meta_partially_redacted_flag(self, monkeypatch):
        """ColumnMeta for 'value' must have partially_redacted=True when at
        least one row was masked."""
        m = _load_redaction_module(monkeypatch)

        rows_in = [
            {"key": "app_name", "value": "AIKM"},
            {"key": "openai_api_key", "value": "sk-secret"},
        ]
        _, col_meta = m.apply_redaction(rows_in, "system_settings")

        value_meta = next((c for c in col_meta if c.name == "value"), None)
        assert value_meta is not None
        assert value_meta.partially_redacted is True
        assert value_meta.hidden is False

    def test_column_meta_not_redacted_when_all_safe(self, monkeypatch):
        """ColumnMeta for 'value' must have partially_redacted=False when no
        rows were masked."""
        m = _load_redaction_module(monkeypatch)

        rows_in = [
            {"key": "app_name", "value": "AIKM"},
            {"key": "theme", "value": "dark"},
        ]
        _, col_meta = m.apply_redaction(rows_in, "system_settings")

        value_meta = next((c for c in col_meta if c.name == "value"), None)
        assert value_meta is not None
        assert value_meta.partially_redacted is False


# ---------------------------------------------------------------------------
# Test 3: Input immutability
# ---------------------------------------------------------------------------

class TestInputImmutability:
    """apply_redaction must not mutate the caller's input list or row dicts."""

    def test_original_list_unchanged_after_redaction(self, monkeypatch):
        """Caller's list object must be unchanged (same length, same dicts)."""
        m = _load_redaction_module(monkeypatch)

        original_row = {"key": "openai_api_key", "value": "sk-real-secret"}
        rows_in = [original_row]

        original_value_before = rows_in[0]["value"]
        original_len_before = len(rows_in)

        out_rows, _ = m.apply_redaction(rows_in, "system_settings")

        # Output is redacted
        assert out_rows[0]["value"] == "***"

        # Input is NOT mutated
        assert len(rows_in) == original_len_before, "Input list length changed"
        assert rows_in[0]["value"] == original_value_before, (
            f"Input dict was mutated: rows_in[0]['value']={rows_in[0]['value']!r} "
            f"but expected {original_value_before!r}"
        )

    def test_output_rows_are_new_dicts(self, monkeypatch):
        """Output row dicts must be distinct objects from input row dicts."""
        m = _load_redaction_module(monkeypatch)

        rows_in = [{"key": "app_name", "value": "AIKM"}]
        out_rows, _ = m.apply_redaction(rows_in, "system_settings")

        assert out_rows[0] is not rows_in[0], (
            "Output row dict is the same object as input — apply_redaction must "
            "return new dicts, not references to the originals."
        )

    def test_empty_input_returns_empty(self, monkeypatch):
        """Empty input list → ([], [])."""
        m = _load_redaction_module(monkeypatch)

        out_rows, col_meta = m.apply_redaction([], "system_settings")
        assert out_rows == []
        assert col_meta == []

    def test_unrelated_table_rows_passed_through(self, monkeypatch):
        """Rows from a table with no redaction rules are returned unchanged."""
        m = _load_redaction_module(monkeypatch)

        rows_in = [
            {"id": 1, "name": "Asset A", "status": "OPERATING"},
            {"id": 2, "name": "Asset B", "status": "INACTIVE"},
        ]
        original_copy = [dict(r) for r in rows_in]
        out_rows, col_meta = m.apply_redaction(rows_in, "maximo_zz_asset")

        assert out_rows == original_copy
        # Input untouched
        assert rows_in == original_copy


# ---------------------------------------------------------------------------
# Test 4: Import-time scan skipped when PG_VIEWER_DATABASE_URL is empty
# ---------------------------------------------------------------------------

class TestImportTimeScanSkip:
    """The scan must not error when PG_VIEWER_DATABASE_URL is not set."""

    def test_scan_skipped_without_db_url(self, monkeypatch):
        """Calling _run_schema_scan() with no PG_VIEWER_DATABASE_URL must not raise."""
        m = _load_redaction_module(monkeypatch)
        # Direct call with URL absent — must be a no-op
        m._run_schema_scan()  # must not raise

    def test_module_importable_without_db_url(self, monkeypatch):
        """Module loads successfully when DB URL is absent."""
        m = _load_redaction_module(monkeypatch)
        assert hasattr(m, "apply_redaction")
        assert hasattr(m, "HIDDEN_COLUMNS")
        assert hasattr(m, "REDACTED_BY_ROW_RULE")


# ---------------------------------------------------------------------------
# Test 5: HIDDEN_COLUMNS structure
# ---------------------------------------------------------------------------

class TestHiddenColumnsConfig:
    """HIDDEN_COLUMNS must contain the expected entries from spec §3."""

    def test_system_settings_value_is_hidden(self, monkeypatch):
        m = _load_redaction_module(monkeypatch)
        assert ("system_settings", "value") in m.HIDDEN_COLUMNS

    def test_hidden_columns_is_set_of_tuples(self, monkeypatch):
        m = _load_redaction_module(monkeypatch)
        assert isinstance(m.HIDDEN_COLUMNS, set)
        for item in m.HIDDEN_COLUMNS:
            assert isinstance(item, tuple) and len(item) == 2


# ---------------------------------------------------------------------------
# Test 6: mask_email_ui helper
# ---------------------------------------------------------------------------

class TestMaskEmailUi:
    """mask_email_ui must mask the local part of the email address."""

    def test_normal_email(self, monkeypatch):
        m = _load_redaction_module(monkeypatch)
        assert m.mask_email_ui("alice@example.com") == "a***@example.com"

    def test_single_char_local(self, monkeypatch):
        m = _load_redaction_module(monkeypatch)
        assert m.mask_email_ui("a@example.com") == "*@example.com"

    def test_none_returns_none(self, monkeypatch):
        m = _load_redaction_module(monkeypatch)
        assert m.mask_email_ui(None) is None

    def test_no_at_sign_returned_as_is(self, monkeypatch):
        m = _load_redaction_module(monkeypatch)
        assert m.mask_email_ui("not-an-email") == "not-an-email"
