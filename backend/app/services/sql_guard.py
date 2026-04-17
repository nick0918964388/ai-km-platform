"""SQL injection guard for user-submitted SQL examples."""
import re
import logging

log = logging.getLogger(__name__)

DANGEROUS_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bDROP\s+(TABLE|DATABASE|INDEX|VIEW)\b",
        r"\bDELETE\s+FROM\b",
        r"\bTRUNCATE\b",
        r"\bALTER\s+TABLE\b",
        r"\bCREATE\s+(TABLE|DATABASE|INDEX|VIEW)\b",
        r"\bINSERT\s+INTO\b",
        r"\bUPDATE\s+\w+\s+SET\b",
        r"\bGRANT\b",
        r"\bREVOKE\b",
        r"\bEXEC(UTE)?\b",
        r";\s*(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|TRUNCATE)",
        r"--\s*$",
        r"/\*.*\*/",
        r"\bUNION\s+(ALL\s+)?SELECT\b",
        r"\bINTO\s+OUTFILE\b",
        r"\bLOAD_FILE\b",
    ]
]


def scan_sql(sql: str) -> tuple[bool, str | None]:
    """Check if SQL is safe (SELECT-only). Returns (is_safe, reason)."""
    stripped = sql.strip().rstrip(';').strip()
    if not stripped.upper().startswith('SELECT'):
        return False, f"Only SELECT queries allowed, got: {stripped[:20]}..."

    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(sql):
            return False, f"Dangerous SQL pattern: {pattern.pattern}"

    return True, None
