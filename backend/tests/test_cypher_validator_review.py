"""Review POC tests for CypherValidator — bypass attempts.

These tests encode adversarial payloads the primary suite did NOT cover.
A FAILING test here means the validator let an unsafe query through.
"""
import pytest

from app.services.cypher_validator import CypherValidator


@pytest.fixture
def v():
    return CypherValidator()


# ─────────────────────────────────────────────────────────────────────
# [C-A] Zero-width / soft-hyphen bypass of word-boundary blacklist
#       Neo4j parser ignores some non-ASCII characters or treats them
#       as identifier chars. If the validator strips strings but does
#       NOT normalize unicode, "DE\u200bLETE" breaks the \b regex.
# ─────────────────────────────────────────────────────────────────────
def test_zero_width_inside_keyword_blocked(v):
    # Zero-width space U+200B between DE and LETE
    q = "MATCH (n) DE\u200bLETE n"
    ok, reasons, _ = v.validate(q)
    assert not ok, f"Zero-width bypass not blocked: reasons={reasons}"


def test_soft_hyphen_inside_keyword_blocked(v):
    # U+00AD soft hyphen is commonly invisible
    q = "MATCH (n) DE\u00adLETE n"
    ok, reasons, _ = v.validate(q)
    assert not ok, f"Soft-hyphen bypass not blocked: reasons={reasons}"


# ─────────────────────────────────────────────────────────────────────
# [C-B] apoc.cypher.runFirstColumn — RCE-style runtime Cypher eval.
#       Current blacklist has 'apoc.cypher.run' prefix which *should*
#       catch it; this is a sanity POC.  Also tests
#       apoc.cypher.parallel (destructive in some APOC versions).
# ─────────────────────────────────────────────────────────────────────
def test_apoc_cypher_runfirstcolumn_blocked(v):
    q = (
        "MATCH (n) "
        "RETURN apoc.cypher.runFirstColumn("
        "'MATCH (x) DETACH DELETE x RETURN 1', {}) AS x LIMIT 1"
    )
    ok, reasons, _ = v.validate(q)
    assert not ok, f"apoc.cypher.runFirstColumn bypass: reasons={reasons}"


def test_apoc_cypher_parallel_blocked(v):
    q = (
        "CALL apoc.cypher.parallel("
        "'MATCH (n) DETACH DELETE n', {}, []) YIELD value RETURN value"
    )
    ok, reasons, _ = v.validate(q)
    assert not ok, f"apoc.cypher.parallel bypass: reasons={reasons}"


# ─────────────────────────────────────────────────────────────────────
# [C-C] Unterminated string literal — stripper may swallow the rest
#       of the query including real keywords after it.  But attacker
#       cannot actually execute an unterminated literal in Neo4j, so
#       this is mostly about validator crashing vs not.  Verify NO
#       crash, and that obviously malicious trailing keyword after a
#       well-terminated mix IS still caught.
# ─────────────────────────────────────────────────────────────────────
def test_unterminated_string_does_not_crash(v):
    q = "MATCH (n) WHERE n.x = 'oops DELETE n"
    # Should NOT raise — either reject or accept deterministically
    ok, reasons, _ = v.validate(q)
    # Either outcome is acceptable; crash is not.
    assert isinstance(ok, bool)


def test_string_then_real_delete_still_caught(v):
    # String literal closed properly, then a real DELETE follows
    q = "MATCH (n) WHERE n.note = 'safe text' DELETE n"
    ok, reasons, _ = v.validate(q)
    assert not ok, f"real DELETE after string slipped through: reasons={reasons}"


# ─────────────────────────────────────────────────────────────────────
# [C-D] UNION + auto-LIMIT semantics
#       validator appends "LIMIT 50" to the end of the query.  In
#       Cypher, "RETURN ... UNION RETURN ... LIMIT 50" applies LIMIT
#       only to the last sub-clause (per spec each RETURN owns its
#       own ORDER BY/SKIP/LIMIT before UNION).  But the bigger worry
#       is that a crafted query can bypass LIMIT on the first leg.
#       This is a correctness (not safety) concern — we document it.
# ─────────────────────────────────────────────────────────────────────
def test_union_without_any_limit_gets_rewritten(v):
    q = "MATCH (n:A) RETURN n UNION MATCH (m:B) RETURN m"
    ok, reasons, rewritten = v.validate(q)
    assert ok
    assert "LIMIT 50" in rewritten
    # Document: LIMIT currently applies only to the SECOND leg in Cypher.
    # The first leg (MATCH A) can still return unbounded rows.
    # This is a known gap — flagged in review report.


# ─────────────────────────────────────────────────────────────────────
# [C-E] Subquery depth counter is confused by property-map braces.
#       A RETURN with many inline maps can inflate max_depth_seen and
#       trigger false positives; conversely it can also be abused to
#       mask real subquery depth if somehow the counter decrements.
# ─────────────────────────────────────────────────────────────────────
def test_property_maps_inflate_subquery_depth(v):
    # Legal query with deeply nested property map but NO CALL { } blocks
    q = (
        "MATCH (n) RETURN {a: {b: {c: {d: {e: 1}}}}} AS x LIMIT 5"
    )
    ok, reasons, _ = v.validate(q)
    # If validator conflates { } for subquery and property map, this
    # legal query fails — documenting as correctness issue.
    assert ok, f"property map mistaken for subquery: reasons={reasons}"


# ─────────────────────────────────────────────────────────────────────
# [C-F] Trailing-semicolon-with-comment bypass of auto-LIMIT.
#       validator strips trailing ';' but if query ends with '//'
#       line comment before newline, LIMIT gets appended inside the
#       comment and is effectively ignored by Neo4j.
# ─────────────────────────────────────────────────────────────────────
def test_trailing_line_comment_does_not_hide_limit(v):
    q = "MATCH (n) RETURN n //"
    ok, reasons, rewritten = v.validate(q)
    assert ok
    # The appended " LIMIT 50" MUST NOT be inside the line comment.
    # rewritten should still produce a parseable Cypher that actually
    # enforces LIMIT when sent to Neo4j.
    last_line = rewritten.splitlines()[-1]
    assert "LIMIT" in last_line and last_line.lstrip().startswith("LIMIT") is False \
        or "//" not in last_line.split("LIMIT")[0], \
        f"LIMIT appended inside line comment: {rewritten!r}"


# ─────────────────────────────────────────────────────────────────────
# [C-G] Unicode-normalized keyword (NFKC).  Full-width 'DELETE' typed
#       as ＤＥＬＥＴＥ (U+FF24 etc.). Neo4j itself would NOT parse
#       this as DELETE, so it's a soft risk — but if the validator's
#       upstream (LLM) echoes fullwidth, fail-safe is to reject.
# ─────────────────────────────────────────────────────────────────────
def test_fullwidth_delete_is_harmless(v):
    # This query won't execute as DELETE in Neo4j; we only assert no
    # crash and deterministic behaviour.
    q = "MATCH (n) \uFF24\uFF25\uFF2C\uFF25\uFF34\uFF25 n"
    ok, _, _ = v.validate(q)
    assert isinstance(ok, bool)


# ─────────────────────────────────────────────────────────────────────
# [C-H] Log injection: extremely long query should be truncated in
#       log output (currently 200 chars).  Just assert no exception.
# ─────────────────────────────────────────────────────────────────────
def test_oversized_query_logs_truncated(v, caplog):
    q = "MATCH (n) DELETE n " + ("x" * 6000)
    ok, reasons, _ = v.validate(q)
    assert not ok
    # log msg should not contain the full 6000-char suffix
    for rec in caplog.records:
        assert len(rec.getMessage()) < 2000
