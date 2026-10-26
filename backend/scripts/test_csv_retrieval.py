"""Verification script for CSV context retrieval."""

import asyncio
from app.graph.client import GraphClient
from app.vector.client import get_vector_store
from app.api.deps import Container


async def test():
    print("=== TEST 1: Neo4j Knowledge Graph Verification ===")
    gc = GraphClient()
    try:
        r1 = await gc.run("MATCH (s:Entity {label: 'Scheme'}) RETURN count(s) AS cnt;")
        print("Scheme count in Neo4j:", r1[0]["cnt"])
        r2 = await gc.run("MATCH (a:Entity {label: 'AMC'}) RETURN count(a) AS cnt;")
        print("AMC count in Neo4j:", r2[0]["cnt"])
        r3 = await gc.run("MATCH (s:Entity)-[:OFFERED_BY]->(a:Entity) RETURN count(*) AS cnt;")
        print("OFFERED_BY links in Neo4j:", r3[0]["cnt"])

        # Check sample scheme node
        sample = await gc.run("MATCH (s:Entity {label: 'Scheme'}) WHERE s.text CONTAINS 'Aditya Birla Sun Life Large & Mid Cap Fund' RETURN s.text AS name, s.nav AS nav, s.aum_cr AS aum LIMIT 1;")
        if sample:
            print(f"Sample Scheme found in Neo4j: {sample[0]['name']}, NAV={sample[0]['nav']}, AUM={sample[0]['aum']}")
    except Exception as e:
        print("Neo4j test error:", e)

    print("\n=== TEST 2: Vector Search Verification ===")
    vs = get_vector_store()
    test_queries = [
        "What is in the csv file?",
        "mutual_fund_data.csv",
        "What is the NAV of Aditya Birla Sun Life Large & Mid Cap Fund from the csv file?",
    ]
    for q in test_queries:
        hits = await vs.search(q, top_k=3)
        print(f"\nQuery: '{q}' -> Hits: {len(hits)}")
        for h in hits:
            print(f"  [{h.get('chunk_id')}] doc={h.get('document_id')} score={round(h.get('score', 0), 3)}")
            print(f"    text: {h.get('text', '')[:110]}...")

    print("\n=== TEST 3: End-to-End Orchestrator.answer() ===")
    container = Container()
    orchestrator = container.orchestrator

    eval_queries = [
        "What is in the csv file?",
        "What is the NAV of Aditya Birla Sun Life Large & Mid Cap Fund from the csv file?",
    ]
    for eq in eval_queries:
        print(f"\n---> Running Orchestrator for: '{eq}'")
        try:
            resp = await orchestrator.answer(query=eq, enable_hyde=False)
            print("Confidence:", resp.synthesis.confidence)
            print("Quality Gate Passed:", resp.context.passed_quality_gate if resp.context else None)
            print("Quality Score:", resp.context.quality_score if resp.context else None)
            print("Sources Count:", len(resp.context.sources) if resp.context else 0)
            print("Answer Preview:\n", resp.synthesis.answer)
        except Exception as err:
            print("Orchestrator error:", err)


if __name__ == "__main__":
    asyncio.run(test())
