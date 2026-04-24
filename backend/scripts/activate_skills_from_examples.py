"""CLI: Activate skills from nl_sql_examples (verified=true).

Usage:
    python backend/scripts/activate_skills_from_examples.py [--dry-run] [--force]

--dry-run  Print what would be created, do not write to DB or Qdrant.
--force    If skill name already exists, bump version instead of skipping.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import os

# Allow running from repo root or inside container (WORKDIR /app → backend/)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_SCRIPT_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Heavy imports are deferred to _run() so that unit tests can import
# the pure helper functions (_make_slug, _deduplicate_slug, etc.) without
# needing sqlalchemy / qdrant_client installed in the test environment.

log = logging.getLogger("activate_skills")
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(message)s",
)

# ─── Security default for every activated skill ───────────────────────────────
_DEFAULT_SECURITY = {
    "allowed_roles": [
        "viewer",
        "maint_tech",
        "maint_manager",
        "analyst",
        "admin",
    ],
    "row_filter": True,
}

_HAIKU_MODEL = "claude-haiku-4-5-20251001"


# ─── Slug helpers ─────────────────────────────────────────────────────────────

def _make_slug(question: str) -> str:
    """Convert a Chinese/English question to a safe ASCII slug ≤ 50 chars.

    Algorithm:
    1. Extract ASCII words (letters + digits).
    2. If result is empty (pure Chinese), use pinyin-like prefix from char codes → fall back
       to a positional tag built from the first 4 hex chars of hash.
    3. Truncate to 50 chars, strip trailing hyphens.
    """
    # Try to harvest English words first
    words = re.findall(r"[A-Za-z0-9]+", question)
    slug = "-".join(w.lower() for w in words if w)
    if not slug:
        # Pure Chinese: derive from hash to guarantee uniqueness yet be stable
        h = abs(hash(question)) % (16 ** 8)
        slug = f"skill-{h:08x}"
    slug = slug[:50].rstrip("-")
    return slug


def _deduplicate_slug(base: str, existing_names: set[str]) -> str:
    """Append numeric suffix if base collides with an already-seen name."""
    if base not in existing_names:
        return base
    # try up to 99 suffixes
    for i in range(2, 100):
        candidate = f"{base[:47]}-{i}" if len(base) >= 48 else f"{base}-{i}"
        if candidate not in existing_names:
            return candidate
    # last resort: append hash fragment
    h = abs(hash(base)) % 9999
    return f"{base[:44]}-{h}"


# ─── LLM variant generation ───────────────────────────────────────────────────

def _generate_variants_llm(question: str, api_key: str) -> list[str]:
    """Call Anthropic Haiku to generate 3 trigger variants.

    Returns a list of variant strings.  On any error returns [].
    """
    import anthropic  # type: ignore

    prompt = (
        f"原始問題：「{question}」\n"
        "請產生 3 個語義相同但講法不同的變體（口語化、省略、同義詞替換）。\n"
        "輸出純 JSON 陣列，不要加其他文字：[\"變體1\", \"變體2\", \"變體3\"]"
    )
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```[^\n]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw).strip()
        variants = json.loads(raw)
        if isinstance(variants, list):
            return [str(v).strip() for v in variants if str(v).strip()]
    except Exception as exc:
        log.warning("LLM variant generation failed for %r: %s", question, exc)
    return []


def _build_triggers(question: str, api_key: str | None) -> list[str]:
    """Return [question] + LLM variants.  Always includes original as first trigger."""
    triggers: list[str] = [question]
    if api_key:
        variants = _generate_variants_llm(question, api_key)
        # De-duplicate while preserving order
        seen = {question}
        for v in variants:
            if v not in seen:
                triggers.append(v)
                seen.add(v)
    return triggers


# ─── Qdrant helper ────────────────────────────────────────────────────────────

def _get_qdrant():
    from qdrant_client import QdrantClient
    from app.config import get_settings
    s = get_settings()
    kwargs: dict = {"url": s.qdrant_url}
    if s.qdrant_api_key:
        kwargs["api_key"] = s.qdrant_api_key
    return QdrantClient(**kwargs)


# ─── Main logic ───────────────────────────────────────────────────────────────

async def _run(dry_run: bool, force: bool) -> None:
    from sqlalchemy import text
    from app.config import get_settings
    from app.db.session import get_db_context
    from app.services.skills import repository as repo
    from app.services.skills.qdrant_collection import ensure_collection, upsert_skill_point
    from app.services.embedding import embed_text

    settings = get_settings()
    api_key = settings.anthropic_api_key or None

    if not api_key:
        log.warning("anthropic_api_key not set — LLM variants disabled, using original question only")

    qdrant = None  # QdrantClient | None
    if not dry_run:
        try:
            qdrant = _get_qdrant()
            ensure_collection(qdrant)
        except Exception as exc:
            log.warning("Qdrant unavailable (%s) — Qdrant sync will be skipped", exc)
            qdrant = None

    async with get_db_context() as db:
        # Fetch all verified examples
        result = await db.execute(
            text("""
                SELECT id, question, sql_query
                FROM nl_sql_examples
                WHERE verified = TRUE
                ORDER BY id
            """)
        )
        examples = result.fetchall()

    if not examples:
        log.warning("No verified nl_sql_examples found. Nothing to do.")
        return

    log.info("Found %d verified nl_sql_examples", len(examples))

    ok_count = 0
    skip_count = 0
    err_count = 0
    seen_slugs: set[str] = set()

    # Pre-load existing slugs to handle deduplication within this batch
    async with get_db_context() as db:
        existing_result = await db.execute(
            text("SELECT name FROM skills WHERE is_current = TRUE")
        )
        for row in existing_result.fetchall():
            seen_slugs.add(row.name)

    for ex in examples:
        question: str = ex.question
        sql: str = ex.sql_query

        base_slug = _make_slug(question)
        name = _deduplicate_slug(base_slug, seen_slugs)

        triggers = _build_triggers(question, api_key)

        skill_data = {
            "name": name,
            "description": question,
            "triggers": triggers,
            "sql_template": sql,
            "params_schema": {},
            "security": _DEFAULT_SECURITY,
            "stats": {"seed_origin": "nl_sql_examples", "source_id": ex.id},
            "active": True,
        }

        if dry_run:
            print(
                f"[DRY-RUN] name={name!r:52s} "
                f"triggers={len(triggers)} "
                f"sql_len={len(sql)}"
            )
            for t in triggers:
                print(f"          trigger: {t}")
            seen_slugs.add(name)
            ok_count += 1
            continue

        try:
            async with get_db_context() as db:
                existing = await repo.get_current_skill_by_name(db, name)

            if existing and not force:
                log.info("[SKIP] %r already exists (use --force to overwrite)", name)
                seen_slugs.add(name)
                skip_count += 1
                continue

            if existing and force:
                # bump version
                from app.services.skills.versioning import bump_version

                async with get_db_context() as db:
                    skill = await bump_version(
                        db=db,
                        qdrant=qdrant,
                        embedder=embed_text,
                        name=name,
                        update_data=skill_data,
                        changed_by="activate_skills_cli",
                        reason="force re-activate from nl_sql_examples",
                    )
                log.info("[BUMP] %r → v%d  triggers=%d", name, skill["version"], len(triggers))
            else:
                # create v1
                async with get_db_context() as db:
                    skill = await repo.create_skill(db, skill_data)

                # Qdrant upsert (best-effort)
                if qdrant is not None:
                    try:
                        vector = embed_text(triggers[0])
                        upsert_skill_point(
                            qdrant,
                            skill_id=skill["id"],
                            version=skill["version"],
                            name=skill["name"],
                            is_current=True,
                            vector=vector,
                            active=True,
                        )
                    except Exception as exc:
                        log.warning("Qdrant upsert failed for %r: %s", name, exc)

                log.info("[OK] %r  triggers=%d", name, len(triggers))

            seen_slugs.add(name)
            ok_count += 1

        except Exception as exc:
            log.warning("[ERR] %r failed: %s — continuing", name, exc)
            err_count += 1

    print()
    print("=" * 60)
    if dry_run:
        print(f"DRY-RUN complete: {ok_count} skills would be created")
    else:
        print(
            f"Done: {ok_count} created/bumped, {skip_count} skipped, {err_count} errors"
        )
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Activate skills from nl_sql_examples (verified=true)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print proposals without writing to DB or Qdrant",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="If skill name already exists, bump version instead of skipping",
    )
    args = parser.parse_args()
    asyncio.run(_run(dry_run=args.dry_run, force=args.force))


if __name__ == "__main__":
    main()
