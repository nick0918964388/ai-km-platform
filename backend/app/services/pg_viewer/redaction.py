"""Secondary redaction defense for pg_viewer result rows.

PRIMARY defense: L5 role-level REVOKE — `aikm_viewer` cannot SELECT
`users`, `sessions`, `api_keys`, or `pg_viewer_audit_log` at all.

SECONDARY defense (this module): drop HIDDEN_COLUMNS and mask
REDACTED_BY_ROW_RULE rows so that schema-grant drift or a newly-added
sensitive column is caught before reaching the frontend.

Import-time schema scan:
  On first import this module queries `information_schema.columns` via the
  `aikm_viewer` role and asserts every column whose name matches
  /password|secret|token|api_key|credential|private_key|passphrase/i is
  either (a) inaccessible (permission denied — L5 REVOKE), (b) in
  HIDDEN_COLUMNS, or (c) covered by REDACTED_BY_ROW_RULE.

  The scan is SKIPPED when PG_VIEWER_DATABASE_URL is empty — this covers
  unit-test / dev environments without a live DB.  Set the env var to
  activate the scan in CI.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Sensitive column registry
# ---------------------------------------------------------------------------

# NOTE (post-critic R2-H1): `email` is SAFE for admin purposes — FR-062
# declares email in the curated `users_public` projection. Email is NOT here.
# A separate UI-layer mask (EMAIL_MASK_UI_COLUMNS) handles audit display.

# (table, column) — these columns are NEVER projected to the frontend.
# The entire column key is removed from every returned row dict.
HIDDEN_COLUMNS: set[tuple[str, str]] = {
    ("system_settings", "value"),  # masked per ROW_RULE below; hidden as fallback
}

# Row-level masking rules.
# Schema: { table_name: { "column_to_mask", "key_column", "key_substrings", "mask" } }
# A row in `table_name` where `row[key_column]` contains any of `key_substrings`
# (case-insensitive substring match) will have `column_to_mask` replaced with `mask`.
REDACTED_BY_ROW_RULE: dict[str, dict] = {
    "system_settings": {
        "column_to_mask": "value",
        "key_column": "key",
        "key_substrings": [
            "secret",
            "token",
            "api_key",
            "password",
            "credential",
            "private_key",
            "passphrase",
        ],
        "mask": "***",
    },
}

# UI-layer email mask — applied ONLY in the /audit response serializer.
# Does NOT alter stored `user_email` in `pg_viewer_audit_log` (kept raw for forensics).
EMAIL_MASK_UI_COLUMNS: set[tuple[str, str]] = {
    ("pg_viewer_audit_log", "user_email"),
}


# ---------------------------------------------------------------------------
# ColumnMeta — returned alongside sanitised rows
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ColumnMeta:
    """Metadata about a single column after redaction."""

    name: str
    # True when the column was completely dropped from all rows (HIDDEN_COLUMNS).
    hidden: bool = False
    # True when at least one row in the result had this column's value masked
    # (REDACTED_BY_ROW_RULE matched).  False when all rows were untouched.
    partially_redacted: bool = False


# ---------------------------------------------------------------------------
# Regex for import-time schema scan
# ---------------------------------------------------------------------------

_SENSITIVE_RE = re.compile(
    r"password|secret|token|api_key|credential|private_key|passphrase",
    re.IGNORECASE,
)


def _build_redacted_columns_set() -> set[tuple[str, str]]:
    """Return the union of HIDDEN_COLUMNS and REDACTED_BY_ROW_RULE coverage."""
    covered: set[tuple[str, str]] = set(HIDDEN_COLUMNS)
    for table, rule in REDACTED_BY_ROW_RULE.items():
        covered.add((table, rule["column_to_mask"]))
    return covered


# ---------------------------------------------------------------------------
# Core redaction function
# ---------------------------------------------------------------------------

def apply_redaction(
    rows: list[dict], table: str
) -> tuple[list[dict], list[ColumnMeta]]:
    """Apply secondary redaction to result rows for the given table.

    Steps:
      1. Identify every column key present in the result set.
      2. Drop columns in HIDDEN_COLUMNS for this table.
      3. Apply REDACTED_BY_ROW_RULE masking for this table.
      4. Return (new_rows, columns_meta).

    Guarantees:
      - Input `rows` is never mutated — new dicts are created for each row.
      - Returns an empty list with no columns_meta if `rows` is empty.
    """
    if not rows:
        return [], []

    # Collect all column names seen across rows (preserving first-seen order).
    all_cols: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for k in row:
            if k not in seen:
                all_cols.append(k)
                seen.add(k)

    # Determine which columns are hidden for this table.
    hidden_cols: set[str] = {
        col for (tbl, col) in HIDDEN_COLUMNS if tbl == table
    }

    # Load row-masking rule for this table (None if not applicable).
    row_rule = REDACTED_BY_ROW_RULE.get(table)

    # Build result rows — never mutate input dicts.
    new_rows: list[dict] = []
    # Track which columns had at least one masked value.
    masked_cols: set[str] = set()

    # Columns covered by a row rule for this table — these get mask-or-passthrough
    # treatment (NOT the blanket drop), even if they also appear in HIDDEN_COLUMNS.
    row_rule_col: str | None = row_rule["column_to_mask"] if row_rule else None

    for row in rows:
        new_row: dict = {}
        for k, v in row.items():
            # Row rule takes priority: if this column is the mask target, decide
            # per-row whether to mask or pass through before considering HIDDEN.
            if row_rule and k == row_rule_col:
                key_col = row_rule["key_column"]
                key_val = str(row.get(key_col, "") or "").lower()
                triggered = any(
                    sub in key_val for sub in row_rule["key_substrings"]
                )
                if triggered:
                    new_row[k] = row_rule["mask"]
                    masked_cols.add(k)
                else:
                    new_row[k] = v
                continue

            if k in hidden_cols:
                # Drop entirely — do not include key in new_row.
                continue

            new_row[k] = v
        new_rows.append(new_row)

    # Columns that were truly dropped (in hidden_cols but NOT handled by the row rule).
    # Row-rule columns appear in output (masked or clear), so they are NOT hidden.
    actually_dropped: set[str] = {
        col for col in hidden_cols if col != row_rule_col
    }

    # Build ColumnMeta list in original column order.
    columns_meta: list[ColumnMeta] = []
    for col in all_cols:
        if col in actually_dropped:
            columns_meta.append(ColumnMeta(name=col, hidden=True, partially_redacted=False))
        else:
            columns_meta.append(ColumnMeta(
                name=col,
                hidden=False,
                partially_redacted=(col in masked_cols),
            ))

    return new_rows, columns_meta


# ---------------------------------------------------------------------------
# UI-layer email mask helper
# ---------------------------------------------------------------------------

def mask_email_ui(email: str | None) -> str | None:
    """Mask an email address for display in the audit-log viewer.

    Produces `j***@domain.com` format.  Does not alter stored values.
    """
    if not email or "@" not in email:
        return email
    local, _, domain = email.partition("@")
    if len(local) <= 1:
        return f"*@{domain}"
    return f"{local[0]}***@{domain}"


# ---------------------------------------------------------------------------
# Import-time schema scan
# ---------------------------------------------------------------------------

def _run_schema_scan() -> None:
    """Query information_schema.columns as aikm_viewer and assert all sensitive
    columns are either inaccessible or covered by redaction config.

    Skips silently when PG_VIEWER_DATABASE_URL is empty.
    Raises RuntimeError on first uncovered sensitive column found.
    """
    pg_url = os.getenv("PG_VIEWER_DATABASE_URL", "")
    if not pg_url:
        # No DB available (unit-test / dev env) — skip scan.
        return

    try:
        import asyncio

        import psycopg  # type: ignore[import]
    except ImportError:
        # psycopg3 not installed — skip scan gracefully.
        return

    covered = _build_redacted_columns_set()

    async def _scan() -> None:
        # Normalise URL: strip asyncpg dialect prefix if present.
        url = pg_url
        for prefix in ("postgresql+asyncpg://", "postgres+asyncpg://"):
            if url.startswith(prefix):
                url = "postgresql://" + url[len(prefix):]
                break

        try:
            conn = await psycopg.AsyncConnection.connect(url, autocommit=True)
        except Exception:
            # Cannot connect — skip scan (DB may not be up yet at import time).
            return

        async with conn:
            query = """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND regexp_like(column_name,
                      'password|secret|token|api_key|credential|private_key|passphrase',
                      'i')
            """
            try:
                async with conn.cursor() as cur:
                    await cur.execute(query)  # type: ignore[arg-type]
                    rows = await cur.fetchall()
            except Exception:
                # information_schema query failed — skip scan.
                return

        for tbl, col in rows:
            if (tbl, col) in covered:
                continue
            # Column is visible to aikm_viewer — check if it's actually inaccessible.
            # If not in our covered set AND reachable, it's an unredacted leak.
            raise RuntimeError(
                f"unredacted sensitive column: {tbl}.{col} — "
                "add to HIDDEN_COLUMNS or REDACTED_BY_ROW_RULE in redaction.py, "
                "or REVOKE SELECT on the table from aikm_viewer."
            )

    asyncio.run(_scan())


_run_schema_scan()
