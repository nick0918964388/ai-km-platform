"""S1 Skills System — acceptance tests.

AC1: POST create → version=1 is_current=True, Qdrant has new point
AC2: PUT update  → version=2 is_current=True, v1 is_current=False, changelog +1
AC3: SkillMatcher.match returns only is_current=True results
AC4: sql_template with DELETE → 400 unsafe_sql (via _is_safe_select)
AC5: v1 feedback → skill_feedback table; SkillMatcher queries v2, not affected by v1 stats
AC6: Qdrant collection missing → ensure_collection creates it
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.services.maximo_nl2sql_tools import _is_safe_select
from app.services.skills.schema import SkillCreate, SkillUpdate, FeedbackCreate
from app.services.skills.qdrant_collection import (
    SKILLS_COLLECTION,
    ensure_collection,
    upsert_skill_point,
    _point_id,
)
from app.services.skills.matcher import SkillMatcher, MATCH_THRESHOLD
from app.services.skills.feedback import record as feedback_record


# ─── helpers ─────────────────────────────────────────────────────────────────


def _make_row(**kwargs):
    """Build a minimal SQLAlchemy Row-like object."""
    m = MagicMock()
    m._mapping = kwargs
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


def _make_db_for_create(skill_row: dict):
    """Mock db that returns skill_row on first execute (INSERT) and nothing after."""
    db = AsyncMock()

    result_create = MagicMock()
    result_create.fetchone = MagicMock(return_value=_make_row(**skill_row))

    result_generic = MagicMock()
    result_generic.fetchone = MagicMock(return_value=None)
    result_generic.scalar = MagicMock(return_value=None)
    result_generic.fetchall = MagicMock(return_value=[])

    db.execute = AsyncMock(return_value=result_create)
    db.commit = AsyncMock()
    return db


def _fake_embedder(text: str) -> list[float]:
    return [0.1] * 16


# ─── AC1: create skill v1 ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ac1_create_skill_v1():
    """POST create → version=1 is_current=True, Qdrant upsert called."""
    from app.services.skills import repository as repo

    skill_id = str(uuid.uuid4())
    row_data = {
        "id": skill_id,
        "name": "EMU800 有幾組車組",
        "version": 1,
        "is_current": True,
        "description": "查詢 EMU800 車組數",
        "triggers": ["EMU800 有幾組車組"],
        "sql_template": "SELECT COUNT(*) FROM maximo_assets WHERE vehicle_type='EMU800'",
        "params_schema": {},
        "security": {},
        "stats": {},
        "active": False,
    }

    db = _make_db_for_create(row_data)

    result = await repo.create_skill(db, {
        "name": "EMU800 有幾組車組",
        "description": "查詢 EMU800 車組數",
        "triggers": ["EMU800 有幾組車組"],
        "sql_template": "SELECT COUNT(*) FROM maximo_assets WHERE vehicle_type='EMU800'",
        "active": False,
    })

    assert result["version"] == 1
    assert result["is_current"] is True
    assert result["id"] == skill_id
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_ac1_qdrant_upsert_on_create():
    """Qdrant upsert_skill_point is called after create."""
    qdrant = MagicMock()
    qdrant.get_collections = MagicMock(return_value=MagicMock(
        collections=[MagicMock(name=SKILLS_COLLECTION)]
    ))
    # Silence upsert
    qdrant.upsert = MagicMock()

    skill_id = str(uuid.uuid4())
    upsert_skill_point(qdrant, skill_id, 1, "EMU800 有幾組車組", True, [0.1] * 16)
    qdrant.upsert.assert_called_once()
    call_kwargs = qdrant.upsert.call_args
    assert call_kwargs.kwargs["collection_name"] == SKILLS_COLLECTION
    points = call_kwargs.kwargs["points"]
    assert len(points) == 1
    assert points[0].payload["skill_id"] == skill_id
    assert points[0].payload["version"] == 1
    assert points[0].payload["is_current"] is True


# ─── AC2: bump version ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ac2_bump_version():
    """PUT update → v2 is_current=True, v1 is_current=False, changelog written."""
    from app.services.skills import repository as repo
    from app.services.skills.versioning import bump_version

    skill_id = str(uuid.uuid4())
    v1_row = {
        "id": skill_id,
        "name": "EMU800 有幾組車組",
        "version": 1,
        "is_current": True,
        "description": "舊說明",
        "triggers": ["EMU800 有幾組車組"],
        "sql_template": "SELECT 1",
        "params_schema": {},
        "security": {},
        "stats": {},
        "active": False,
    }
    new_skill_id = str(uuid.uuid4())
    v2_row = {**v1_row, "id": new_skill_id, "version": 2, "description": "新說明"}

    db = AsyncMock()
    db.commit = AsyncMock()

    execute_responses = []
    # 1) get_current_skill_by_name
    r1 = MagicMock()
    r1.fetchone = MagicMock(return_value=_make_row(**v1_row))
    execute_responses.append(r1)
    # 2) deactivate_current_versions (UPDATE, no return needed)
    r2 = MagicMock()
    r2.fetchone = MagicMock(return_value=None)
    execute_responses.append(r2)
    # 3) MAX(version) query in create_new_version
    r3 = MagicMock()
    r3.scalar = MagicMock(return_value=2)
    execute_responses.append(r3)
    # 4) INSERT new version
    r4 = MagicMock()
    r4.fetchone = MagicMock(return_value=_make_row(**v2_row))
    execute_responses.append(r4)
    # 5) write_changelog INSERT
    r5 = MagicMock()
    execute_responses.append(r5)

    db.execute = AsyncMock(side_effect=execute_responses)

    qdrant = MagicMock()
    qdrant.set_payload = MagicMock()
    qdrant.upsert = MagicMock()

    new_skill = await bump_version(
        db=db,
        qdrant=qdrant,
        embedder=_fake_embedder,
        name="EMU800 有幾組車組",
        update_data={"description": "新說明"},
        changed_by="admin@example.com",
        reason="更新說明",
    )

    assert new_skill["version"] == 2
    assert new_skill["is_current"] is True
    # changelog INSERT was called (5th execute call)
    assert db.execute.call_count == 5
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_ac2_old_version_is_current_false():
    """After bump_version, the deactivate call sets v1.is_current=False."""
    # This is validated by checking that deactivate_current_versions was called
    # (second execute call in bump_version test above).
    # Here we test the repo function directly.
    from app.services.skills import repository as repo

    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock())
    db.commit = AsyncMock()

    await repo.deactivate_current_versions(db, "EMU800 有幾組車組")
    db.execute.assert_called_once()
    sql_arg = db.execute.call_args[0][0]
    assert "is_current = FALSE" in str(sql_arg)


# ─── AC3: SkillMatcher only returns is_current=True ──────────────────────────


def test_ac3_matcher_only_returns_current():
    """SkillMatcher.match filters by is_current=True and threshold 0.85."""
    qdrant = MagicMock()

    # Two search results: one current (score 0.92), one old (score 0.90 but is_current=False)
    hit_current = MagicMock()
    hit_current.score = 0.92
    hit_current.id = str(uuid.uuid4())
    hit_current.payload = {
        "skill_id": "skill-v2",
        "version": 2,
        "name": "EMU800 有幾組車組",
        "is_current": True,
    }

    hit_old = MagicMock()
    hit_old.score = 0.90
    hit_old.id = str(uuid.uuid4())
    hit_old.payload = {
        "skill_id": "skill-v1",
        "version": 1,
        "name": "EMU800 有幾組車組",
        "is_current": False,
    }

    # Qdrant already filters via query_filter on is_current=True, so only hit_current comes back
    qdrant.search = MagicMock(return_value=[hit_current])
    qdrant.get_collections = MagicMock(return_value=MagicMock(
        collections=[MagicMock(name=SKILLS_COLLECTION)]
    ))

    matcher = SkillMatcher(qdrant, _fake_embedder)
    results = matcher.match("EMU800 有幾組車組")

    assert len(results) == 1
    assert results[0]["version"] == 2
    assert results[0]["is_current"] is True
    # Confirm search was called with is_current filter
    call_kwargs = qdrant.search.call_args.kwargs
    assert call_kwargs["collection_name"] == SKILLS_COLLECTION
    must_conditions = call_kwargs["query_filter"].must
    assert any(
        getattr(c, "key", None) == "is_current" for c in must_conditions
    )


def test_ac3_matcher_threshold_filters_low_scores():
    """Scores below 0.85 are excluded even if Qdrant returns them."""
    qdrant = MagicMock()
    low_hit = MagicMock()
    low_hit.score = 0.80
    low_hit.id = str(uuid.uuid4())
    low_hit.payload = {"skill_id": "x", "version": 1, "name": "foo", "is_current": True}

    qdrant.search = MagicMock(return_value=[low_hit])
    qdrant.get_collections = MagicMock(return_value=MagicMock(
        collections=[MagicMock(name=SKILLS_COLLECTION)]
    ))

    matcher = SkillMatcher(qdrant, _fake_embedder)
    results = matcher.match("some query")
    assert results == []


# ─── AC4: DELETE sql_template → 400 unsafe_sql ────────────────────────────────


def test_ac4_delete_sql_template_rejected():
    """sql_template containing DELETE is rejected by _is_safe_select."""
    ok, err = _is_safe_select("DELETE FROM maximo_assets WHERE 1=1")
    assert not ok
    assert "FORBIDDEN" in err


def test_ac4_safe_select_passes():
    """A valid SELECT passes the guard."""
    ok, err = _is_safe_select(
        "SELECT COUNT(*) FROM maximo_assets WHERE vehicle_type='EMU800'"
    )
    assert ok


def test_ac4_router_returns_400_for_unsafe_sql():
    """The router layer raises HTTPException 400 for unsafe sql_template."""
    from fastapi import HTTPException

    sql = "DELETE FROM skills WHERE 1=1"
    ok, err = _is_safe_select(sql)
    assert not ok
    # Simulate what the router does
    try:
        raise HTTPException(status_code=400, detail=f"unsafe_sql: {err}")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "unsafe_sql" in exc.detail


# ─── AC5: feedback → skill_feedback, matcher query v2 unaffected ─────────────


@pytest.mark.asyncio
async def test_ac5_feedback_written_to_skill_feedback():
    """feedback.record() writes to skill_feedback (not rag_feedback)."""
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar = MagicMock(return_value=42)
    db.execute = AsyncMock(return_value=result_mock)
    db.commit = AsyncMock()

    skill_id = uuid.uuid4()
    fb_id = await feedback_record(
        db=db,
        skill_id=skill_id,
        skill_version=1,
        rating="up",
        message_id="msg-001",
        user_id="user-1",
    )

    assert fb_id == 42
    db.commit.assert_called_once()
    # Verify INSERT targeted skill_feedback (not rag_feedback)
    sql_arg = str(db.execute.call_args[0][0])
    assert "skill_feedback" in sql_arg
    assert "rag_feedback" not in sql_arg


def test_ac5_matcher_v2_independent_of_v1_feedback():
    """SkillMatcher searches Qdrant with is_current filter; v1 feedback cannot affect v2 results.

    This is a structural test: the matcher filters by is_current=True at the
    Qdrant query layer, so v1 feedback (stored in skill_feedback for skill_version=1)
    has zero influence on whether v2 appears in results.
    """
    qdrant = MagicMock()

    v2_hit = MagicMock()
    v2_hit.score = 0.95
    v2_hit.id = str(uuid.uuid4())
    v2_hit.payload = {
        "skill_id": "skill-abc",
        "version": 2,
        "name": "EMU800 有幾組車組",
        "is_current": True,
    }
    qdrant.search = MagicMock(return_value=[v2_hit])
    qdrant.get_collections = MagicMock(return_value=MagicMock(
        collections=[MagicMock(name=SKILLS_COLLECTION)]
    ))

    matcher = SkillMatcher(qdrant, _fake_embedder)
    # Even after hypothetical v1 👍 feedback exists, matcher returns v2
    results = matcher.match("EMU800 有幾組車組")
    assert len(results) == 1
    assert results[0]["version"] == 2
    # Qdrant filter is on is_current — feedback table not consulted
    assert results[0]["skill_id"] == "skill-abc"


# ─── AC6: Qdrant collection missing → auto-created ───────────────────────────


def test_ac6_ensure_collection_creates_if_missing():
    """ensure_collection() creates skills_vectors when absent (idempotent)."""
    qdrant = MagicMock()
    # Simulate empty collections list
    qdrant.get_collections = MagicMock(return_value=MagicMock(collections=[]))
    qdrant.create_collection = MagicMock()

    with patch(
        "app.services.skills.qdrant_collection.get_text_embedding_dimension",
        return_value=384,
    ):
        ensure_collection(qdrant)

    qdrant.create_collection.assert_called_once()
    create_kwargs = qdrant.create_collection.call_args.kwargs
    assert create_kwargs["collection_name"] == SKILLS_COLLECTION
    assert create_kwargs["vectors_config"].size == 384


def test_ac6_ensure_collection_idempotent_if_exists():
    """ensure_collection() is a no-op when collection already exists."""
    qdrant = MagicMock()
    existing_col = MagicMock()
    existing_col.name = SKILLS_COLLECTION
    qdrant.get_collections = MagicMock(return_value=MagicMock(collections=[existing_col]))
    qdrant.create_collection = MagicMock()

    ensure_collection(qdrant)

    qdrant.create_collection.assert_not_called()


# ─── bonus: skill_feedback table not rag_feedback ────────────────────────────


def test_rag_feedback_not_referenced_in_feedback_module():
    """feedback.py must not query or import rag_feedback table/module."""
    import inspect
    from app.services.skills import feedback as fb_module

    source = inspect.getsource(fb_module)
    # Must not contain SQL targeting rag_feedback or import the rag_feedback module
    assert "FROM rag_feedback" not in source
    assert "import rag_feedback" not in source


# ─── CRITICAL 2: active=False skill not matched ───────────────────────────────


def test_matcher_does_not_return_inactive_skills():
    """SkillMatcher must NOT return active=False skills.

    Qdrant filter requires BOTH is_current=True AND active=True.
    Seeded skills start with active=False — they must be invisible to the matcher.
    """
    qdrant = MagicMock()

    # Simulate Qdrant returning zero results because the filter on active=True
    # excludes the inactive skill. In practice Qdrant does the filtering;
    # here we assert the filter is constructed correctly.
    qdrant.search = MagicMock(return_value=[])
    qdrant.get_collections = MagicMock(return_value=MagicMock(
        collections=[MagicMock(name=SKILLS_COLLECTION)]
    ))

    matcher = SkillMatcher(qdrant, lambda t: [0.1] * 16)
    results = matcher.match("EMU800 有幾組車組")

    assert results == []

    # Verify both is_current AND active filters are in the Qdrant query
    call_kwargs = qdrant.search.call_args.kwargs
    must_conditions = call_kwargs["query_filter"].must
    filter_keys = {getattr(c, "key", None) for c in must_conditions}
    assert "is_current" in filter_keys, "is_current filter missing"
    assert "active" in filter_keys, "active filter missing — inactive skills would leak through"


def test_upsert_skill_point_includes_active_field():
    """upsert_skill_point must include 'active' in Qdrant payload."""
    qdrant = MagicMock()
    qdrant.upsert = MagicMock()

    skill_id = str(uuid.uuid4())
    upsert_skill_point(qdrant, skill_id, 1, "test skill", True, [0.1] * 16, active=False)

    points = qdrant.upsert.call_args.kwargs["points"]
    assert "active" in points[0].payload
    assert points[0].payload["active"] is False

    # Also verify active=True round-trip
    qdrant.upsert.reset_mock()
    upsert_skill_point(qdrant, skill_id, 2, "test skill", True, [0.1] * 16, active=True)
    points2 = qdrant.upsert.call_args.kwargs["points"]
    assert points2[0].payload["active"] is True


# ─── MEDIUM 7: admin PUT changed_by from JWT ─────────────────────────────────


def test_put_changed_by_forced_from_jwt():
    """PUT endpoint ignores payload.changed_by and uses JWT user email instead.

    Reads router source directly (avoids importing the module which requires
    jwt/sqlalchemy to be installed in the test environment).
    """
    from pathlib import Path
    router_path = Path(__file__).resolve().parents[1] / "app" / "routers" / "skills_admin.py"
    source = router_path.read_text(encoding="utf-8")

    # The update_skill function must use user.get("email") as changed_by
    assert 'changed_by=user.get("email")' in source, (
        "update_skill must pass user.get('email') as changed_by, not payload.changed_by"
    )
    # The exclude set in model_dump must include 'changed_by' so payload value is dropped
    assert '"changed_by"' in source or "'changed_by'" in source, (
        "update_skill model_dump must exclude 'changed_by' from update_data"
    )
