"""Tests for CypherValidator — static safety checks for Text2Cypher output."""
import re
import time
import pytest

from app.services.cypher_validator import CypherValidator, validate_cypher


@pytest.fixture
def v():
    return CypherValidator()


# ── 合法查詢：應通過（含 LIMIT 或被自動補上） ──────────────────────────────
LEGAL_QUERIES = [
    # 1. 簡單 MATCH...RETURN
    "MATCH (n:Asset) RETURN n LIMIT 10",
    # 2. 多跳 variable length
    "MATCH (a)-[:RELATES*1..3]->(b) RETURN a, b LIMIT 20",
    # 3. WITH 聚合
    "MATCH (n:WorkOrder) WITH n.status AS s, count(*) AS c RETURN s, c LIMIT 25",
    # 4. CASE WHEN
    "MATCH (n) RETURN CASE WHEN n.priority > 5 THEN 'high' ELSE 'low' END AS pri LIMIT 10",
    # 5. UNION
    "MATCH (n:A) RETURN n.id AS id UNION MATCH (m:B) RETURN m.id AS id LIMIT 50",
    # 6. OPTIONAL MATCH
    "MATCH (a:Asset) OPTIONAL MATCH (a)-[:HAS]->(w:WorkOrder) RETURN a, w LIMIT 10",
    # 7. WHERE EXISTS
    "MATCH (n:Asset) WHERE EXISTS { MATCH (n)-[:BROKE]->() } RETURN n LIMIT 5",
    # 8. APOC 唯讀函式 coll
    "MATCH (n) WITH collect(n.name) AS names RETURN apoc.coll.contains(names, 'x') LIMIT 1",
    # 9. APOC text.replace
    "MATCH (n) RETURN apoc.text.replace(n.name, 'foo', 'bar') LIMIT 10",
    # 10. CALL subquery
    "MATCH (a:Asset) CALL { WITH a MATCH (a)-[:HAS]->(w) RETURN w } RETURN a, w LIMIT 20",
    # 11. DISTINCT + ORDER BY + SKIP
    "MATCH (n:WorkOrder) RETURN DISTINCT n.status ORDER BY n.status SKIP 0 LIMIT 5",
    # 12. WITH ... WHERE
    "MATCH (n) WITH n, n.cost AS c WHERE c > 100 RETURN n LIMIT 10",
]


@pytest.mark.parametrize("q", LEGAL_QUERIES)
def test_legal_queries_pass(v, q):
    ok, reasons, rewritten = v.validate(q)
    assert ok, f"Expected legal, got reasons={reasons} for: {q}"
    assert rewritten, "rewritten cypher should be non-empty when OK"
    assert re.search(r"\bLIMIT\b", rewritten, re.IGNORECASE)


# ── 惡意查詢：全部必須被 block ────────────────────────────────────────────
MALICIOUS_QUERIES = [
    # 1. DETACH DELETE
    "MATCH (n) DETACH DELETE n",
    # 2. SET
    "MATCH (n) SET n.hacked = true RETURN n",
    # 3. CREATE
    "CREATE (n:Attacker) RETURN n",
    # 4. MERGE
    "MERGE (n:X {id: 1}) RETURN n",
    # 5. DROP
    "DROP CONSTRAINT x IF EXISTS",
    # 6. CALL db.*
    "CALL db.labels() YIELD label RETURN label",
    # 7. LOAD CSV
    "LOAD CSV FROM 'file:///etc/passwd' AS row RETURN row",
    # 8. apoc.export
    "CALL apoc.export.csv.all('/tmp/leak.csv', {}) YIELD file RETURN file",
    # 9. apoc.periodic
    "CALL apoc.periodic.iterate('MATCH (n) RETURN n', 'SET n.pwned=1', {})",
    # 10. path depth too large
    "MATCH (n)-[*1..100]->(m) RETURN m LIMIT 10",
    # 11. too long
    "MATCH (n) WHERE " + " OR ".join([f"n.p{i}=1" for i in range(1000)]) + " RETURN n LIMIT 10",
    # 14. 混合大小寫
    "MaTcH (n) DeLeTe n",
    # 15. UNION + DELETE 後段
    "MATCH (n:A) RETURN n UNION MATCH (m:B) DELETE m",
    # 16. 子查詢內 DELETE
    "MATCH (n) CALL { WITH n DELETE n } RETURN n",
    # 17. gds.graph.drop
    "CALL gds.graph.drop('mygraph') YIELD graphName RETURN graphName",
    # 18. dbms.security
    "CALL dbms.security.changePassword('new_pass')",
    # 額外：REMOVE
    "MATCH (n) REMOVE n.prop RETURN n",
    # 額外：不明 procedure
    "CALL custom.malicious.proc() YIELD x RETURN x",
    # 額外：apoc.create（非白名單）
    "MATCH (n) CALL apoc.create.node(['X'], {}) YIELD node RETURN node",
    # 額外：FOREACH (寫入語意)
    "MATCH (n) FOREACH (x IN [1,2,3] | SET n.v = x) RETURN n",
    # 額外：子查詢中 CREATE
    "MATCH (a) CALL { WITH a CREATE (b:Evil) RETURN b } RETURN a, b",
]


@pytest.mark.parametrize("q", MALICIOUS_QUERIES)
def test_malicious_queries_blocked(v, q):
    ok, reasons, rewritten = v.validate(q)
    assert not ok, f"Expected block, passed: {q}"
    assert reasons, "reasons must be populated when rejected"
    assert rewritten == ""


# ── 空字串 / 空白 ────────────────────────────────────────────────────────
def test_empty_query_rejected(v):
    ok, reasons, _ = v.validate("")
    assert not ok and "empty" in reasons[0]

    ok, reasons, _ = v.validate("    \n\t  ")
    assert not ok and "empty" in reasons[0]

    ok, reasons, _ = v.validate(None)  # type: ignore[arg-type]
    assert not ok and "empty" in reasons[0]


# ── 字串與註解不應觸發黑名單 ─────────────────────────────────────────────
def test_delete_inside_string_literal_ok(v):
    q = "MATCH (n) WHERE n.note = 'please DELETE old stuff later' RETURN n LIMIT 5"
    ok, reasons, _ = v.validate(q)
    assert ok, f"String-literal DELETE should pass, reasons={reasons}"


def test_delete_inside_double_quoted_string_ok(v):
    q = 'MATCH (n) WHERE n.msg = "DROP TABLE users; --" RETURN n LIMIT 5'
    ok, reasons, _ = v.validate(q)
    assert ok, f"DQ-string DELETE should pass, reasons={reasons}"


def test_delete_inside_block_comment_ok(v):
    q = "MATCH (n) /* DELETE ignore me */ RETURN n LIMIT 5"
    ok, reasons, _ = v.validate(q)
    assert ok, f"Block-comment DELETE should pass, reasons={reasons}"


def test_delete_inside_line_comment_ok(v):
    q = "MATCH (n) // DELETE n\nRETURN n LIMIT 5"
    ok, reasons, _ = v.validate(q)
    assert ok, f"Line-comment DELETE should pass, reasons={reasons}"


# ── 自動補 LIMIT ─────────────────────────────────────────────────────────
def test_missing_limit_auto_added(v):
    q = "MATCH (n:Asset) RETURN n"
    ok, reasons, rewritten = v.validate(q)
    assert ok, f"Should pass after limit injection, reasons={reasons}"
    assert re.search(r"LIMIT\s+50\b", rewritten, re.IGNORECASE)


def test_missing_limit_with_trailing_semicolon(v):
    q = "MATCH (n:Asset) RETURN n;"
    ok, _, rewritten = v.validate(q)
    assert ok
    assert rewritten.strip().upper().endswith("LIMIT 50")


def test_existing_limit_preserved(v):
    q = "MATCH (n) RETURN n LIMIT 7"
    ok, _, rewritten = v.validate(q)
    assert ok
    # rewritten 應等於 original（不再 append）
    assert rewritten.count("LIMIT") == 1
    assert "LIMIT 7" in rewritten


# ── 邊界測試 ─────────────────────────────────────────────────────────────
def test_length_exactly_5000_ok(v):
    filler_n = 5000 - len("MATCH (n) RETURN n LIMIT 5 //")
    q = "MATCH (n) RETURN n LIMIT 5 //" + "x" * filler_n
    assert len(q) == 5000
    ok, reasons, _ = v.validate(q)
    assert ok, f"5000 chars should pass, reasons={reasons}"


def test_length_5001_rejected(v):
    q = "MATCH (n) RETURN n LIMIT 5 //" + "x" * (5001 - len("MATCH (n) RETURN n LIMIT 5 //"))
    assert len(q) == 5001
    ok, reasons, _ = v.validate(q)
    assert not ok
    assert any("too long" in r for r in reasons)


def test_path_depth_5_ok(v):
    q = "MATCH (a)-[*1..5]->(b) RETURN a, b LIMIT 10"
    ok, reasons, _ = v.validate(q)
    assert ok, f"depth 5 should pass, reasons={reasons}"


def test_path_depth_6_rejected(v):
    q = "MATCH (a)-[*1..6]->(b) RETURN a, b LIMIT 10"
    ok, reasons, _ = v.validate(q)
    assert not ok
    assert any("path depth" in r for r in reasons)


# ── 子查詢深度 ────────────────────────────────────────────────────────────
def test_subquery_depth_3_ok(v):
    q = (
        "MATCH (a) CALL { WITH a CALL { WITH a CALL { WITH a "
        "MATCH (a)-[:R]->(b) RETURN b } RETURN b } RETURN b } RETURN a, b LIMIT 10"
    )
    ok, reasons, _ = v.validate(q)
    assert ok, f"3-level subquery ok, reasons={reasons}"


def test_subquery_depth_4_rejected(v):
    q = (
        "MATCH (a) CALL { WITH a CALL { WITH a CALL { WITH a CALL { WITH a "
        "MATCH (a)-[:R]->(b) RETURN b } RETURN b } RETURN b } RETURN b } RETURN a, b LIMIT 10"
    )
    ok, reasons, _ = v.validate(q)
    assert not ok
    assert any("subquery depth" in r for r in reasons)


# ── Performance：validator 本身應 < 10ms per query ───────────────────────
def test_performance_under_10ms(v):
    q = "MATCH (a)-[:R*1..3]->(b) WHERE a.name = 'x' RETURN a, b ORDER BY a.name LIMIT 50"
    # 暖機一次
    v.validate(q)
    start = time.perf_counter()
    for _ in range(100):
        v.validate(q)
    elapsed_ms = (time.perf_counter() - start) * 1000 / 100
    assert elapsed_ms < 10, f"Validator too slow: {elapsed_ms:.2f}ms avg"


# ── 便利函式 ─────────────────────────────────────────────────────────────
def test_module_level_helper():
    ok, _, rewritten = validate_cypher("MATCH (n) RETURN n")
    assert ok
    assert "LIMIT 50" in rewritten

    ok2, reasons, _ = validate_cypher("MATCH (n) DELETE n")
    assert not ok2 and reasons


# ── Regression：Review Agent W2-T3 發現的問題 ─────────────────────────────

@pytest.mark.parametrize("payload", [
    "DE\u200bLETE",   # ZWSP
    "DE\u200cLETE",   # ZWNJ
    "DE\u200dLETE",   # ZWJ
    "DE\u00adLETE",   # soft hyphen
    "DE\ufeffLETE",   # BOM
])
def test_unicode_invisible_chars_do_not_bypass_blacklist(v, payload):
    ok, reasons, _ = v.validate(f"MATCH (n) {payload} n")
    assert not ok, f"bypass via {payload!r} not blocked: {reasons}"


def test_deep_property_map_is_legal(v):
    # 5 層 property map，含 LIMIT — 應通過，不該誤判為 subquery 深度超標
    q = "MATCH (n) RETURN {a:{b:{c:{d:{e:1}}}}} AS x LIMIT 5"
    ok, reasons, _ = v.validate(q)
    assert ok, f"deep property map wrongly rejected: {reasons}"


def test_call_subquery_depth_still_enforced_with_maps(v):
    # 真的 4 層 CALL 子查詢（即使夾雜 property map）仍應被擋
    q = (
        "MATCH (a) CALL { WITH a CALL { WITH a CALL { WITH a CALL { WITH a "
        "RETURN {x:1} AS m } RETURN m } RETURN m } RETURN m } RETURN a LIMIT 5"
    )
    ok, reasons, _ = v.validate(q)
    assert not ok
    assert any("subquery depth" in r for r in reasons)


def test_union_auto_limit_applies_to_every_segment():
    ok, _, rewritten = validate_cypher(
        "MATCH (n:A) RETURN n UNION MATCH (m:B) RETURN m"
    )
    assert ok
    # 兩段都要有 LIMIT（至少出現 2 次）
    assert rewritten.upper().count("LIMIT 50") >= 2, rewritten


def test_union_preserves_explicit_limit_per_segment():
    # 第一段已有 LIMIT，第二段沒有 → 只補第二段
    ok, _, rewritten = validate_cypher(
        "MATCH (n:A) RETURN n LIMIT 10 UNION MATCH (m:B) RETURN m"
    )
    assert ok
    assert "LIMIT 10" in rewritten
    assert "LIMIT 50" in rewritten


def test_trailing_line_comment_does_not_swallow_limit():
    ok, _, rewritten = validate_cypher("MATCH (n) RETURN n //")
    assert ok
    # LIMIT 絕不能落在 // 之後同一行
    for line in rewritten.splitlines():
        if "LIMIT" in line.upper():
            before = line.upper().split("LIMIT")[0]
            assert "//" not in before, f"LIMIT in comment: {rewritten!r}"


def test_trailing_block_comment_does_not_swallow_limit():
    ok, _, rewritten = validate_cypher("MATCH (n) RETURN n /* tail */")
    assert ok
    assert re.search(r"\bLIMIT\s+50\b", rewritten), rewritten
