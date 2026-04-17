"""Domain code to Chinese mapping for Maximo fields."""
import logging
from app.db.session import get_db_context
from sqlalchemy import text

log = logging.getLogger(__name__)

DEPOT_CODES = {
    "MGY00": "高雄機務段",
    "MYY00": "嘉義機務段",
    "MPY00": "彰化機務段",
    "MHY00": "新竹機務段",
    "MHY10": "新竹機務段富岡機廠",
    "MMY00": "臺北機務段",
    "MMY20": "臺北機務段樹林調車場",
    "MAY00": "花蓮機務段",
    "MIY00": "臺東機務段",
    "TKY00": "高雄運務段",
    "TRY00": "嘉義運務段",
    "TNY00": "臺中運務段",
    "TSY00": "臺北運務段",
}

TRANSLATABLE_FIELDS = {
    "eq2": DEPOT_CODES,
    "配屬段": DEPOT_CODES,
    "location": None,
    "siteid": None,
}

_cache: dict[str, dict[str, str]] = {}


async def load_domain_cache():
    global _cache
    try:
        async with get_db_context() as db:
            result = await db.execute(text("""
                SELECT d.domainid, a.value, a.description
                FROM maximo_zz_domain d
                JOIN maximo_zz_domain_alndomain a ON a._parent_key = d.maxdomainid::text
                WHERE a.description IS NOT NULL AND a.description != ''
            """))
            for row in result.fetchall():
                domain_key = row.domainid.lower()
                if domain_key not in _cache:
                    _cache[domain_key] = {}
                _cache[domain_key][row.value] = row.description

            try:
                result = await db.execute(text(
                    "SELECT deptid, description FROM maximo_zz_dept WHERE description IS NOT NULL"
                ))
                dept_map = {}
                for row in result.fetchall():
                    dept_map[row.deptid] = row.description
                if dept_map:
                    _cache["department"] = dept_map
            except Exception:
                pass

        log.info("Domain cache loaded: %d domains", len(_cache))
    except Exception as e:
        log.warning("Failed to load domain cache: %s", e)


def translate_value(field: str, value) -> str:
    if value is None:
        return None
    str_val = str(value)

    field_lower = field.lower()
    if field_lower in TRANSLATABLE_FIELDS and TRANSLATABLE_FIELDS[field_lower]:
        mapped = TRANSLATABLE_FIELDS[field_lower].get(str_val)
        if mapped:
            return mapped

    for domain_key, mapping in _cache.items():
        if str_val in mapping:
            return mapping[str_val]

    return str_val


def translate_row(row: dict) -> dict:
    translated = {}
    for key, value in row.items():
        translated_val = translate_value(key, value)
        if translated_val != (str(value) if value is not None else None):
            translated[key] = translated_val
        else:
            translated[key] = value
    return translated


def translate_rows(rows: list[dict]) -> list[dict]:
    return [translate_row(r) for r in rows]
