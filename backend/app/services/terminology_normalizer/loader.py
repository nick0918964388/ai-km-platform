"""
載入 terminology.yml 至 in-memory dict。
缺檔或解析失敗時返回空 dict，不 crash。
"""

import logging
import os
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

# 預設 YAML 路徑（相對於 backend package root）
# __file__ layout:
#   Docker : /app/app/services/terminology_normalizer/loader.py
#   parents[0] = terminology_normalizer, [1] = services, [2] = app, [3] = /app  (backend root)
#   Mac    : .../backend/app/services/terminology_normalizer/loader.py
#   parents[3] = backend/
# Either way: parents[3] / "data" / "terminology.yml" resolves correctly.
_DEFAULT_YAML = Path(__file__).resolve().parents[3] / "data" / "terminology.yml"


def load_terminology(path: str | Path | None = None) -> Dict[str, str]:
    """
    Load terminology mapping from YAML file.

    Returns:
        dict mapping source term -> canonical term.
        Returns empty dict if file is missing or malformed.
    """
    target = Path(path) if path else _DEFAULT_YAML

    if not target.exists():
        logger.warning("terminology.yml not found at %s — using empty dict", target)
        return {}

    try:
        import yaml  # PyYAML；FastAPI 環境已有此依賴
    except ImportError:
        logger.error("PyYAML not installed — terminology normalizer disabled")
        return {}

    try:
        with open(target, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as exc:
        logger.error("Failed to parse %s: %s — using empty dict", target, exc)
        return {}

    if not isinstance(data, dict):
        logger.warning("terminology.yml root is not a mapping — using empty dict")
        return {}

    terms = data.get("terms", {})
    if not isinstance(terms, dict):
        logger.warning("terminology.yml 'terms' key is not a mapping — using empty dict")
        return {}

    # 確保所有 key/value 都是字串
    result: Dict[str, str] = {}
    for k, v in terms.items():
        if isinstance(k, str) and isinstance(v, str):
            result[k] = v
        else:
            logger.warning("Skipping non-string term entry: %r -> %r", k, v)

    logger.debug("Loaded %d terminology entries from %s", len(result), target)
    return result
