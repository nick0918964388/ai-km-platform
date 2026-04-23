-- Migration 013: Skills System (S1)
-- Creates skills, skill_changelog, and skill_feedback tables.

-- ─── skills ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS skills (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(120) NOT NULL,
    version         INTEGER     NOT NULL DEFAULT 1,
    is_current      BOOLEAN     NOT NULL DEFAULT TRUE,
    description     TEXT,
    triggers        TEXT[]      NOT NULL DEFAULT '{}',
    sql_template    TEXT,
    params_schema   JSONB       NOT NULL DEFAULT '{}',
    security        JSONB       NOT NULL DEFAULT '{}',
    stats           JSONB       NOT NULL DEFAULT '{}',
    active          BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (name, version)
);

-- Partial index: fast lookup for current active skills
CREATE INDEX IF NOT EXISTS idx_skills_current
    ON skills (name)
    WHERE is_current = TRUE;

CREATE INDEX IF NOT EXISTS idx_skills_active_current
    ON skills (active, is_current);

-- ─── skill_changelog ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS skill_changelog (
    id          SERIAL      PRIMARY KEY,
    skill_id    UUID        NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    version     INTEGER     NOT NULL,
    changed_by  TEXT,
    reason      TEXT,
    diff        JSONB       NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_skill_changelog_skill_id
    ON skill_changelog (skill_id);

-- ─── skill_feedback ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS skill_feedback (
    id            SERIAL      PRIMARY KEY,
    skill_id      UUID        NOT NULL,
    skill_version INTEGER     NOT NULL,
    message_id    TEXT,
    rating        TEXT        NOT NULL CHECK (rating IN ('up', 'down')),
    comment       TEXT,
    user_id       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_skill_feedback_skill
    ON skill_feedback (skill_id, skill_version);
