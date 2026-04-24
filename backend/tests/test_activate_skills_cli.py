"""Tests for activate_skills_from_examples.py

Covers:
- slug generation (ASCII, CJK, collision)
- trigger building (LLM success, LLM fallback)
- idempotency (skip existing, --force bump)
- dry-run (no DB writes)
"""
from __future__ import annotations

import asyncio
import json
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure backend/ is on path
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from scripts.activate_skills_from_examples import (
    _make_slug,
    _deduplicate_slug,
    _generate_variants_llm,
    _build_triggers,
)


# ─── Slug generation ──────────────────────────────────────────────────────────


class TestMakeSlug:
    def test_ascii_words_extracted(self):
        slug = _make_slug("EMU900 目前有幾組車組？")
        assert slug == "emu900"

    def test_pure_ascii_question(self):
        slug = _make_slug("How many vehicles are active?")
        assert slug == "how-many-vehicles-are-active"

    def test_length_capped_at_50(self):
        long_q = "abcde " * 20  # 120 chars
        slug = _make_slug(long_q)
        assert len(slug) <= 50

    def test_no_trailing_hyphen(self):
        # Input that would produce trailing hyphen after truncation
        q = "A" * 25 + " " + "B" * 25 + " extra"
        slug = _make_slug(q)
        assert not slug.endswith("-")

    def test_pure_cjk_returns_skill_prefix(self):
        slug = _make_slug("目前有幾組車組")
        assert slug.startswith("skill-")
        assert len(slug) <= 50

    def test_mixed_multiple_words(self):
        slug = _make_slug("EMU900 車組數 COUNT query")
        # Only ASCII tokens preserved
        assert "emu900" in slug
        assert "count" in slug
        assert "query" in slug

    def test_numeric_only(self):
        slug = _make_slug("2024 統計")
        assert slug == "2024"


class TestDeduplicateSlug:
    def test_no_collision(self):
        result = _deduplicate_slug("emu900", set())
        assert result == "emu900"

    def test_collision_appends_2(self):
        result = _deduplicate_slug("emu900", {"emu900"})
        assert result == "emu900-2"

    def test_collision_chain(self):
        existing = {"emu900", "emu900-2", "emu900-3"}
        result = _deduplicate_slug("emu900", existing)
        assert result == "emu900-4"

    def test_long_base_truncated_before_suffix(self):
        base = "a" * 50
        existing = {base}
        result = _deduplicate_slug(base, existing)
        assert len(result) <= 50
        assert result != base


# ─── Variant / trigger generation ────────────────────────────────────────────


class TestGenerateVariantsLlm:
    def _make_anthropic_response(self, variants: list[str]):
        """Build a minimal mock Anthropic response."""
        content_block = MagicMock()
        content_block.text = json.dumps(variants, ensure_ascii=False)
        msg = MagicMock()
        msg.content = [content_block]
        return msg

    def test_returns_variants_on_success(self):
        variants = ["EMU900 現在共幾列?", "EMU900 有多少組?", "EMU900 組數是多少?"]
        mock_msg = self._make_anthropic_response(variants)

        with patch("anthropic.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_msg
            MockAnthropic.return_value = mock_client

            result = _generate_variants_llm("EMU900 目前有幾組車組？", "fake-key")

        assert result == variants

    def test_returns_empty_on_api_error(self):
        with patch("anthropic.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = Exception("API error")
            MockAnthropic.return_value = mock_client

            result = _generate_variants_llm("EMU900 目前有幾組車組？", "fake-key")

        assert result == []

    def test_returns_empty_on_invalid_json(self):
        content_block = MagicMock()
        content_block.text = "not valid json at all"
        msg = MagicMock()
        msg.content = [content_block]

        with patch("anthropic.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = msg
            MockAnthropic.return_value = mock_client

            result = _generate_variants_llm("test question", "fake-key")

        assert result == []

    def test_strips_markdown_fences(self):
        variants = ["變體1", "變體2", "變體3"]
        fenced = f"```json\n{json.dumps(variants, ensure_ascii=False)}\n```"
        content_block = MagicMock()
        content_block.text = fenced
        msg = MagicMock()
        msg.content = [content_block]

        with patch("anthropic.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = msg
            MockAnthropic.return_value = mock_client

            result = _generate_variants_llm("test question", "fake-key")

        assert result == variants


class TestBuildTriggers:
    def test_no_api_key_returns_only_original(self):
        result = _build_triggers("EMU900 目前有幾組車組？", api_key=None)
        assert result == ["EMU900 目前有幾組車組？"]

    def test_with_api_key_includes_original_as_first(self):
        variants = ["變體1", "變體2", "變體3"]
        with patch(
            "scripts.activate_skills_from_examples._generate_variants_llm",
            return_value=variants,
        ):
            result = _build_triggers("EMU900 目前有幾組車組？", api_key="fake")

        assert result[0] == "EMU900 目前有幾組車組？"
        assert "變體1" in result
        assert len(result) == 4  # original + 3 variants

    def test_duplicates_removed(self):
        # Simulate LLM returning the original question as a variant
        with patch(
            "scripts.activate_skills_from_examples._generate_variants_llm",
            return_value=["EMU900 目前有幾組車組？", "重複", "重複"],
        ):
            result = _build_triggers("EMU900 目前有幾組車組？", api_key="fake")

        # Should deduplicate
        assert result.count("EMU900 目前有幾組車組？") == 1
        assert result.count("重複") == 1

    def test_llm_failure_falls_back_to_original_only(self):
        with patch(
            "scripts.activate_skills_from_examples._generate_variants_llm",
            return_value=[],
        ):
            result = _build_triggers("some question", api_key="fake")

        assert result == ["some question"]


# ─── Idempotency (skip / force) ───────────────────────────────────────────────


class TestIdempotency:
    """
    Test that _run() correctly skips existing skills (no --force)
    and dry-run produces no DB writes.

    Because _run() uses deferred imports (to allow pure-function tests to
    run without sqlalchemy), we patch the modules at their canonical paths
    and then re-import inside each test so the patches take effect.
    """

    def _make_example_row(self, id_=1, question="EMU900 目前有幾組車組？", sql="SELECT 1"):
        row = MagicMock()
        row.id = id_
        row.question = question
        row.sql_query = sql
        return row

    def _make_existing_skill(self, name="emu900"):
        return {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": name,
            "version": 1,
            "is_current": True,
            "description": name,
            "triggers": [name],
            "sql_template": "SELECT 1",
            "params_schema": {},
            "security": {},
            "stats": {},
            "active": True,
        }

    def _make_db_cm(self, examples, existing_names, skill_row=None):
        """Build a reusable async context-manager mock that returns a DB mock."""
        db_mock = AsyncMock()
        ex_result = MagicMock()
        ex_result.fetchall.return_value = examples

        existing_names_result = MagicMock()
        existing_names_result.fetchall.return_value = existing_names

        skill_result = MagicMock()
        if skill_row:
            skill_result.fetchone.return_value = MagicMock(
                _mapping=skill_row, **skill_row
            )
        else:
            skill_result.fetchone.return_value = None

        call_count = [0]

        async def fake_execute(sql_obj, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return ex_result          # SELECT from nl_sql_examples
            if call_count[0] == 2:
                return existing_names_result   # SELECT name FROM skills
            return skill_result           # get_current_skill_by_name

        db_mock.execute = fake_execute
        db_mock.commit = AsyncMock()

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=db_mock)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    @pytest.mark.asyncio
    async def test_skip_when_skill_exists_no_force(self):
        """When skill exists and --force is False, create_skill is never called."""
        example = self._make_example_row()
        existing = self._make_existing_skill("emu900")
        cm = self._make_db_cm(
            examples=[example],
            existing_names=[MagicMock(name="emu900")],
            skill_row=existing,
        )

        # Modules that _run() imports lazily
        fake_settings = MagicMock(anthropic_api_key="", qdrant_url="", qdrant_api_key="")
        fake_repo = MagicMock()
        fake_repo.get_current_skill_by_name = AsyncMock(return_value=existing)
        fake_repo.create_skill = AsyncMock()

        import types
        fake_sqlalchemy = types.ModuleType("sqlalchemy")
        fake_sqlalchemy.text = lambda s: s  # type: ignore

        fake_app_config = types.ModuleType("app.config")
        fake_app_config.get_settings = lambda: fake_settings  # type: ignore

        fake_db_session = types.ModuleType("app.db.session")
        fake_db_session.get_db_context = MagicMock(return_value=cm)  # type: ignore

        fake_skills_repo = types.ModuleType("app.services.skills.repository")
        fake_skills_repo.get_current_skill_by_name = AsyncMock(return_value=existing)  # type: ignore
        fake_skills_repo.create_skill = AsyncMock()  # type: ignore

        fake_qdrant_col = types.ModuleType("app.services.skills.qdrant_collection")
        fake_qdrant_col.ensure_collection = MagicMock()  # type: ignore
        fake_qdrant_col.upsert_skill_point = MagicMock()  # type: ignore

        fake_embedding = types.ModuleType("app.services.embedding")
        fake_embedding.embed_text = MagicMock(return_value=[0.1] * 16)  # type: ignore

        with (
            patch.dict(
                sys.modules,
                {
                    "sqlalchemy": fake_sqlalchemy,
                    "app.config": fake_app_config,
                    "app.db.session": fake_db_session,
                    "app.services.skills": types.ModuleType("app.services.skills"),
                    "app.services.skills.repository": fake_skills_repo,
                    "app.services.skills.qdrant_collection": fake_qdrant_col,
                    "app.services.embedding": fake_embedding,
                },
            ),
            patch("scripts.activate_skills_from_examples._get_qdrant",
                  return_value=MagicMock()),
        ):
            from scripts.activate_skills_from_examples import _run
            await _run(dry_run=False, force=False)

        fake_skills_repo.create_skill.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_no_db_writes(self, capsys):
        """--dry-run prints proposals without writing to DB or Qdrant."""
        example = self._make_example_row()
        cm = self._make_db_cm(examples=[example], existing_names=[])

        fake_settings = MagicMock(anthropic_api_key="")
        fake_repo_create = AsyncMock()

        import types
        fake_sqlalchemy = types.ModuleType("sqlalchemy")
        fake_sqlalchemy.text = lambda s: s  # type: ignore

        fake_app_config = types.ModuleType("app.config")
        fake_app_config.get_settings = lambda: fake_settings  # type: ignore

        fake_db_session = types.ModuleType("app.db.session")
        fake_db_session.get_db_context = MagicMock(return_value=cm)  # type: ignore

        fake_skills_repo = types.ModuleType("app.services.skills.repository")
        fake_skills_repo.create_skill = fake_repo_create  # type: ignore

        fake_qdrant_col = types.ModuleType("app.services.skills.qdrant_collection")
        fake_qdrant_col.ensure_collection = MagicMock()  # type: ignore
        fake_qdrant_col.upsert_skill_point = MagicMock()  # type: ignore

        fake_embedding = types.ModuleType("app.services.embedding")
        fake_embedding.embed_text = MagicMock(return_value=[0.1] * 16)  # type: ignore

        with patch.dict(
            sys.modules,
            {
                "sqlalchemy": fake_sqlalchemy,
                "app.config": fake_app_config,
                "app.db.session": fake_db_session,
                "app.services.skills": types.ModuleType("app.services.skills"),
                "app.services.skills.repository": fake_skills_repo,
                "app.services.skills.qdrant_collection": fake_qdrant_col,
                "app.services.embedding": fake_embedding,
            },
        ):
            from scripts.activate_skills_from_examples import _run
            await _run(dry_run=True, force=False)

        fake_repo_create.assert_not_called()
        captured = capsys.readouterr()
        assert "DRY-RUN" in captured.out
        assert "emu900" in captured.out
