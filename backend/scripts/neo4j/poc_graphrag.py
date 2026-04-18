"""
neo4j-graphrag-python POC — Phase 3 W2-T1

目的：驗證三個主要 retriever 能否用於 AI-KM 平台
- Text2CypherRetriever
- VectorCypherRetriever
- HybridRetriever

流程：
1. 連 Neo4j
2. MERGE 少量測試節點（用 PocTest_* label 前綴）
3. 分別跑三個 retriever × 3 個問題 = 9 個 case
4. 清掉測試節點（保險起見 try/finally）
5. 輸出評估結果到 stdout 與 docs/graphrag_poc_notes.md

執行：
    cd /Volumes/kingston/Projects/ai-km-platform
    backend/venv/bin/python backend/scripts/neo4j/poc_graphrag.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from typing import Any

# ---------------------------------------------------------------------------
# 環境設定
# ---------------------------------------------------------------------------
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://192.168.1.11:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "8bdYv##P&bE+-r^3uVrp7v8b")

# 測試 label 前綴 — 清除時依此 match
POC_LABELS = [
    "PocTest_WorkOrder",
    "PocTest_Asset",
    "PocTest_ClassStructure",
]

POC_VECTOR_INDEX = "poc_wo_desc_vec"
POC_FULLTEXT_INDEX = "poc_wo_desc_fts"

# ---------------------------------------------------------------------------
# 匯入依賴（失敗時直接報錯終止）
# ---------------------------------------------------------------------------
from neo4j import GraphDatabase
from neo4j_graphrag.retrievers import (
    Text2CypherRetriever,
    VectorCypherRetriever,
    HybridRetriever,
)
from neo4j_graphrag.llm import OllamaLLM
from neo4j_graphrag.embeddings import SentenceTransformerEmbeddings

# ---------------------------------------------------------------------------
# LLM 設定
# ---------------------------------------------------------------------------
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://ollama.webtw.xyz:11434")
# 用輕量 model 減少 POC 延遲；失敗時可換成任何 ollama 可用 model
OLLAMA_MODEL = os.environ.get("OLLAMA_CHAT_MODEL", "gemma4:31b-cloud")

# Embedding：用本地 sentence-transformer 避免依賴外部 API
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


# ---------------------------------------------------------------------------
# 資料結構
# ---------------------------------------------------------------------------
@dataclass
class CaseResult:
    question: str
    ok: bool
    latency_ms: float
    rows: int
    snippet: str = ""
    generated_cypher: str | None = None
    error: str | None = None


@dataclass
class RetrieverReport:
    name: str
    installed: bool = True
    works: bool = False
    avg_latency_ms: float = 0.0
    cases: list[CaseResult] = field(default_factory=list)
    setup_error: str | None = None


# ---------------------------------------------------------------------------
# 測試資料 seeding / cleanup
# ---------------------------------------------------------------------------
SEED_CYPHER = """
// 車型 ClassStructure
MERGE (emu:PocTest_ClassStructure {classstructureid: 'POC_CS_EMU'})
  ON CREATE SET emu.description = 'EMU 電聯車分類'
MERGE (emu_a:PocTest_ClassStructure {classstructureid: 'POC_CS_EMU_BRAKE'})
  ON CREATE SET emu_a.description = 'EMU 制動系統'

// 車號 Asset
MERGE (emu01:PocTest_Asset {assetnum: 'POC_EMU01', description: 'EMU01 電聯車', assettype: 'EMU', location: 'TPE-DEPOT'})
MERGE (emu02:PocTest_Asset {assetnum: 'POC_EMU02', description: 'EMU02 電聯車', assettype: 'EMU', location: 'TPE-DEPOT'})
MERGE (tra01:PocTest_Asset {assetnum: 'POC_TRA01', description: 'TRA01 區間車', assettype: 'TRA', location: 'KHH-DEPOT'})

// 工單（模擬 reportdate，含中文描述）
MERGE (wo1:PocTest_WorkOrder {wonum: 'POC_WO001', description: 'EMU01 煞車異常更換制動片', worktype: 'CM', status: 'COMP', reportdate: '2026-04-15'})
MERGE (wo2:PocTest_WorkOrder {wonum: 'POC_WO002', description: 'EMU01 例行保養檢查', worktype: 'PM', status: 'WAPPR', reportdate: '2026-04-12'})
MERGE (wo3:PocTest_WorkOrder {wonum: 'POC_WO003', description: 'EMU02 空調冷媒洩漏維修', worktype: 'CM', status: 'INPRG', reportdate: '2026-04-16'})
MERGE (wo4:PocTest_WorkOrder {wonum: 'POC_WO004', description: 'TRA01 門控故障排除', worktype: 'CM', status: 'COMP', reportdate: '2026-04-10'})
MERGE (wo5:PocTest_WorkOrder {wonum: 'POC_WO005', description: 'EMU01 受電弓磨耗檢查', worktype: 'PM', status: 'WAPPR', reportdate: '2026-04-17'})

// 關係
MERGE (wo1)-[:PocTest_PERFORMED_ON]->(emu01)
MERGE (wo2)-[:PocTest_PERFORMED_ON]->(emu01)
MERGE (wo5)-[:PocTest_PERFORMED_ON]->(emu01)
MERGE (wo3)-[:PocTest_PERFORMED_ON]->(emu02)
MERGE (wo4)-[:PocTest_PERFORMED_ON]->(tra01)
MERGE (emu01)-[:PocTest_CLASSIFIED_AS]->(emu)
MERGE (emu02)-[:PocTest_CLASSIFIED_AS]->(emu)
MERGE (emu_a)-[:PocTest_PARENT_OF]->(emu)
RETURN count(*) AS touched
"""

CLEANUP_CYPHER = """
MATCH (n)
WHERE any(l IN labels(n) WHERE l STARTS WITH 'PocTest_')
DETACH DELETE n
"""

DROP_INDEX_VEC = f"DROP INDEX {POC_VECTOR_INDEX} IF EXISTS"
DROP_INDEX_FTS = f"DROP INDEX {POC_FULLTEXT_INDEX} IF EXISTS"


def seed(driver) -> int:
    with driver.session() as s:
        res = s.run(SEED_CYPHER).single()
        return res["touched"] if res else 0


def cleanup(driver) -> None:
    with driver.session() as s:
        s.run(DROP_INDEX_VEC)
        s.run(DROP_INDEX_FTS)
        s.run(CLEANUP_CYPHER)


def create_vector_index(driver, embedder: SentenceTransformerEmbeddings) -> None:
    """建 vector index + 把 description 塞 embedding 到 WorkOrder"""
    with driver.session() as s:
        s.run(
            f"""
            CREATE VECTOR INDEX {POC_VECTOR_INDEX} IF NOT EXISTS
            FOR (w:PocTest_WorkOrder) ON (w.desc_embedding)
            OPTIONS {{indexConfig: {{
                `vector.dimensions`: {EMBEDDING_DIM},
                `vector.similarity_function`: 'cosine'
            }}}}
            """
        )
        s.run(
            f"""
            CREATE FULLTEXT INDEX {POC_FULLTEXT_INDEX} IF NOT EXISTS
            FOR (w:PocTest_WorkOrder) ON EACH [w.description]
            """
        )
        # 把 embedding 寫入每個 WorkOrder
        wos = s.run(
            "MATCH (w:PocTest_WorkOrder) RETURN w.wonum AS wonum, w.description AS desc"
        ).data()
        for row in wos:
            vec = embedder.embed_query(row["desc"])
            s.run(
                "MATCH (w:PocTest_WorkOrder {wonum:$n}) SET w.desc_embedding=$v",
                n=row["wonum"],
                v=vec,
            )
    # 等 index populate
    time.sleep(2)


# ---------------------------------------------------------------------------
# Retriever 測試
# ---------------------------------------------------------------------------
QUESTIONS = [
    "找車號 POC_EMU01 的所有工單",
    "EMU 車型相關的分類結構有哪些？",
    "顯示最近一週的工單狀態（reportdate >= '2026-04-11'）",
]


def _snippet(items: list[Any], limit: int = 160) -> str:
    if not items:
        return ""
    try:
        txt = json.dumps([str(it)[:120] for it in items[:3]], ensure_ascii=False)
    except Exception:
        txt = str(items[:2])
    return txt[:limit]


def run_retriever(name: str, retriever, questions: list[str]) -> RetrieverReport:
    rep = RetrieverReport(name=name, works=True)
    latencies: list[float] = []
    for q in questions:
        t0 = time.time()
        try:
            result = retriever.search(query_text=q)
            ms = (time.time() - t0) * 1000
            items = getattr(result, "items", []) or []
            cypher = getattr(result, "metadata", {}).get("cypher") if hasattr(result, "metadata") else None
            rep.cases.append(
                CaseResult(
                    question=q,
                    ok=True,
                    latency_ms=ms,
                    rows=len(items),
                    snippet=_snippet(items),
                    generated_cypher=cypher,
                )
            )
            latencies.append(ms)
        except Exception as e:
            ms = (time.time() - t0) * 1000
            rep.cases.append(
                CaseResult(
                    question=q,
                    ok=False,
                    latency_ms=ms,
                    rows=0,
                    error=f"{type(e).__name__}: {e}",
                )
            )
    if latencies:
        rep.avg_latency_ms = sum(latencies) / len(latencies)
    rep.works = any(c.ok for c in rep.cases)
    return rep


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    print(f"[POC] Neo4j URI: {NEO4J_URI}")
    print(f"[POC] LLM (Ollama): {OLLAMA_HOST} / {OLLAMA_MODEL}")
    print(f"[POC] Embedding (local): {EMBEDDING_MODEL} dim={EMBEDDING_DIM}")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print("[POC] Neo4j connected")

    # 準備 LLM + Embedder
    llm_setup_error: str | None = None
    llm = None
    try:
        llm = OllamaLLM(
            model_name=OLLAMA_MODEL,
            host=OLLAMA_HOST,
            model_params={"temperature": 0.0},
        )
        # smoke test
        _ = llm.invoke("回 'pong'")
        print("[POC] Ollama LLM ready")
    except Exception as e:
        llm_setup_error = f"{type(e).__name__}: {e}"
        print(f"[POC][WARN] Ollama LLM 不可用：{llm_setup_error}")

    embed_setup_error: str | None = None
    embedder = None
    try:
        embedder = SentenceTransformerEmbeddings(model=EMBEDDING_MODEL)
        _ = embedder.embed_query("smoke test")
        print("[POC] SentenceTransformer embedder ready")
    except Exception as e:
        embed_setup_error = f"{type(e).__name__}: {e}"
        print(f"[POC][WARN] embedder 不可用：{embed_setup_error}")

    # Seed
    try:
        cleanup(driver)  # 防髒
        touched = seed(driver)
        print(f"[POC] Seeded graph (touched={touched})")
        if embedder is not None:
            create_vector_index(driver, embedder)
            print("[POC] Vector + Fulltext indexes ready")
    except Exception as e:
        print(f"[POC][FATAL] seed failed: {e}")
        traceback.print_exc()
        driver.close()
        return 2

    reports: list[RetrieverReport] = []

    # -----------------------------------------------------------------------
    # Retriever 1 — Text2CypherRetriever
    # -----------------------------------------------------------------------
    r1 = RetrieverReport(name="Text2CypherRetriever")
    if llm is None:
        r1.installed = True
        r1.works = False
        r1.setup_error = llm_setup_error or "LLM not available"
        reports.append(r1)
    else:
        try:
            neo4j_schema = """
Node properties:
- PocTest_WorkOrder {wonum: STRING, description: STRING, worktype: STRING, status: STRING, reportdate: STRING}
- PocTest_Asset {assetnum: STRING, description: STRING, assettype: STRING, location: STRING}
- PocTest_ClassStructure {classstructureid: STRING, description: STRING, classification_parent: STRING}
Relationships:
- (:PocTest_WorkOrder)-[:PocTest_PERFORMED_ON]->(:PocTest_Asset)
- (:PocTest_Asset)-[:PocTest_CLASSIFIED_AS]->(:PocTest_ClassStructure)
- (:PocTest_ClassStructure)-[:PocTest_PARENT_OF]->(:PocTest_ClassStructure)
"""
            examples = [
                "USER INPUT: '找車號 POC_EMU02 的工單' QUERY: MATCH (w:PocTest_WorkOrder)-[:PocTest_PERFORMED_ON]->(a:PocTest_Asset {assetnum:'POC_EMU02'}) RETURN w.wonum, w.description, w.status",
            ]
            retriever = Text2CypherRetriever(
                driver=driver,
                llm=llm,
                neo4j_schema=neo4j_schema,
                examples=examples,
            )
            r1 = run_retriever("Text2CypherRetriever", retriever, QUESTIONS)
        except Exception as e:
            r1.setup_error = f"{type(e).__name__}: {e}"
            r1.works = False
            traceback.print_exc()
        reports.append(r1)

    # -----------------------------------------------------------------------
    # Retriever 2 — VectorCypherRetriever
    # -----------------------------------------------------------------------
    r2 = RetrieverReport(name="VectorCypherRetriever")
    if embedder is None:
        r2.installed = True
        r2.works = False
        r2.setup_error = embed_setup_error or "Embedder not available"
        reports.append(r2)
    else:
        try:
            retrieval_query = """
RETURN node.wonum AS wonum, node.description AS description,
       node.status AS status, node.reportdate AS reportdate,
       [(node)-[:PocTest_PERFORMED_ON]->(a) | a.assetnum] AS assets,
       score
"""
            retriever = VectorCypherRetriever(
                driver=driver,
                index_name=POC_VECTOR_INDEX,
                retrieval_query=retrieval_query,
                embedder=embedder,
            )
            r2 = run_retriever("VectorCypherRetriever", retriever, QUESTIONS)
        except Exception as e:
            r2.setup_error = f"{type(e).__name__}: {e}"
            r2.works = False
            traceback.print_exc()
        reports.append(r2)

    # -----------------------------------------------------------------------
    # Retriever 3 — HybridRetriever
    # -----------------------------------------------------------------------
    r3 = RetrieverReport(name="HybridRetriever")
    if embedder is None:
        r3.installed = True
        r3.works = False
        r3.setup_error = embed_setup_error or "Embedder not available"
        reports.append(r3)
    else:
        try:
            retriever = HybridRetriever(
                driver=driver,
                vector_index_name=POC_VECTOR_INDEX,
                fulltext_index_name=POC_FULLTEXT_INDEX,
                embedder=embedder,
                return_properties=["wonum", "description", "status", "reportdate"],
            )
            r3 = run_retriever("HybridRetriever", retriever, QUESTIONS)
        except Exception as e:
            r3.setup_error = f"{type(e).__name__}: {e}"
            r3.works = False
            traceback.print_exc()
        reports.append(r3)

    # -----------------------------------------------------------------------
    # 輸出
    # -----------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("POC SUMMARY")
    print("=" * 70)
    for rep in reports:
        print(f"\n[{rep.name}] works={rep.works} avg_latency={rep.avg_latency_ms:.1f} ms")
        if rep.setup_error:
            print(f"  setup_error: {rep.setup_error}")
        for c in rep.cases:
            mark = "OK" if c.ok else "FAIL"
            print(f"  - [{mark}] {c.question} ({c.latency_ms:.0f}ms) rows={c.rows}")
            if c.generated_cypher:
                print(f"    cypher: {c.generated_cypher[:160]}")
            if c.error:
                print(f"    error: {c.error[:240]}")
            if c.snippet:
                print(f"    snippet: {c.snippet}")

    # 清理 & 關閉
    try:
        cleanup(driver)
        # 驗證 0 殘留
        with driver.session() as s:
            r = s.run(
                "MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'PocTest_') RETURN count(n) AS remain"
            ).single()
            print(f"\n[POC] cleanup remain={r['remain'] if r else '?'} (should be 0)")
    finally:
        driver.close()

    # JSON summary for programmatic use / CI
    summary = {
        "reports": [asdict(r) for r in reports],
        "llm": {"host": OLLAMA_HOST, "model": OLLAMA_MODEL, "setup_error": llm_setup_error},
        "embedder": {"model": EMBEDDING_MODEL, "setup_error": embed_setup_error},
    }
    out_path = os.path.join(os.path.dirname(__file__), "poc_graphrag_result.json")
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(summary, fp, ensure_ascii=False, indent=2, default=str)
    print(f"\n[POC] JSON report -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
