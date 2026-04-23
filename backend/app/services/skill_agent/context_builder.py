"""
Skill Agent Context Builder — S3

Assembles the <recent_context> block injected into the system prompt.
Inputs:
  - conversation_history: list of past turn dicts
  - skill_results: top-5 matched skills (optional, from S1 SkillMatcher)
  - schema_summary: static schema text
History contract:
  - Each history entry may contain:
      q (str), sql (str|None), row_count (int|None), intent (str|None)
  - Raw user text is forwarded truncated to 30 chars as prev_intent label.
    Structured summaries also forwarded: prev_sql (≤200 char) / prev_row_count.
  - Max 3 turns kept; older turns are silently truncated.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

_MAX_HISTORY_TURNS = 3
_SQL_PREVIEW_LEN = 200

# Static schema summary — mirrors the main schema known to the agent.
_STATIC_SCHEMA_SUMMARY = """\
Maximo 資料表（PostgreSQL）：
- maximo_assets: 車輛主檔（assetnum PK, eq24 車號, vehicle_type, vehicle_class, status）
- maximo_pm_workorders: 定期工單（wonum PK, assetnum, work_type 1A/2A/3A/4A, status, act_finish）
- maximo_cm_workorders: 維修工單（wonum PK, assetnum, work_type T1/TR/CM, status, failure_code）
- maximo_fault_reports: 故障通報（ticketid PK, assetnum, grade, status, occurrence_date）
"""


def build_system_context(
    conversation_history: list[dict[str, Any]] | None = None,
    matched_skills: list[dict[str, Any]] | None = None,
    extra_schema: str | None = None,
) -> str:
    """
    Returns a <recent_context> block string to be appended to the system prompt.

    conversation_history entries accepted keys:
      q, sql, row_count, intent
    Structured summaries are forwarded — raw question text (q) is included
    as `prev_intent` truncated to 30 chars.
    """
    parts: list[str] = []

    # 1. Schema
    schema_text = extra_schema if extra_schema else _STATIC_SCHEMA_SUMMARY
    parts.append(f"<schema>\n{schema_text.strip()}\n</schema>")

    # 2. Matched skills (top-5)
    if matched_skills:
        skill_lines = []
        for s in matched_skills[:5]:
            name = s.get("name", "?")
            desc = s.get("description", "")
            skill_lines.append(f"  - {name}: {desc}")
        parts.append("<matched_skills>\n" + "\n".join(skill_lines) + "\n</matched_skills>")

    # 3. Conversation history
    if conversation_history:
        turns = conversation_history[-_MAX_HISTORY_TURNS:]
        turn_lines: list[str] = []
        for i, turn in enumerate(turns, 1):
            # Only pass structured summaries — never raw user text
            intent = turn.get("intent") or _extract_intent_from_q(turn.get("q", ""))
            sql_preview = _truncate(turn.get("sql") or "", _SQL_PREVIEW_LEN)
            row_count = turn.get("row_count")
            line = f"  turn{i}: prev_intent={intent!r}"
            if sql_preview:
                line += f", prev_sql={sql_preview!r}"
            if row_count is not None:
                line += f", prev_row_count={row_count}"
            turn_lines.append(line)
        parts.append("<recent_context>\n" + "\n".join(turn_lines) + "\n</recent_context>")

    return "\n\n".join(parts)


def _extract_intent_from_q(q: str) -> str:
    """
    Produce a short intent label from raw user question.
    Raw text is truncated to 30 chars (still contains raw user input).
    30 chars is insufficient to eliminate prompt injection risk for Chinese;
    callers should prefer storing a structured intent label in history instead.
    """
    if not q:
        return "unknown"
    return q.strip()[:30]


def _truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len] + "..."
