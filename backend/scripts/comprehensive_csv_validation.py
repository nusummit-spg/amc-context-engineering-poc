#!/usr/bin/env python
"""Comprehensive validation of CSV retrieval across vector and graph."""

import asyncio
import os
import sys
from pathlib import Path
from typing import List, Dict, Any
from dotenv import load_dotenv
from neo4j import GraphDatabase

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()
load_dotenv("backend/.env")

# Import from app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.vector.client import get_vector_store
from app.retrieval.orchestrator import RetrievalOrchestrator
from app.api.deps import init_container

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "contextgraph")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# Test cases
TEST_QUERIES = [
    {
        "category": "Overview",
        "query": "What is in mutual_fund_data.csv?",
        "expected_keywords": ["schemes", "AMC", "NAV", "records"],
        "min_confidence": 0.6
    },
    {
        "category": "Specific NAV Lookup",
        "query": "What is the NAV of Aditya Birla Sun Life Large & Mid Cap Fund Regular Growth?",
        "expected_keywords": ["922.67", "NAV", "Aditya Birla"],
        "min_confidence": 0.6
    },
    {
        "category": "AMC Aggregation",
        "query": "How many schemes does HDFC Mutual Fund have?",
        "expected_keywords": ["schemes", "HDFC"],
        "min_confidence": 0.6
    },
    {
        "category": "Category Query",
        "query": "List equity schemes by Aditya Birla Sun Life AMC",
        "expected_keywords": ["equity", "Aditya Birla"],
        "min_confidence": 0.6
    },
    {
        "category": "Data Comparison",
        "query": "Compare NAV of HDFC Equity Fund vs ICICI Prudential Equity Fund",
        "expected_keywords": ["NAV", "HDFC", "ICICI"],
        "min_confidence": 0.6
    }
]

async def test_vector_retrieval():
    """Test vector store retrieval."""
    print("\n" + "="*80)
    print("PHASE 1: Vector Store Retrieval Tests")
    print("="*80)
    
    vs = get_vector_store()
    results = []
    
    for i, test in enumerate(TEST_QUERIES, 1):
        print(f"\n[{i}/{len(TEST_QUERIES)}] {test['category']}")
        print(f"Query: {test['query']}")
        
        hits = await vs.search(test['query'], top_k=5)
        
        if not hits:
            print("  [FAIL] No results found")
            results.append({"test": test['category'], "passed": False, "reason": "No results"})
            continue
        
        print(f"  Found {len(hits)} results")
        
        # Check if expected keywords in results
        all_text = " ".join([h.get('text', '') for h in hits])
        found_keywords = [kw for kw in test['expected_keywords'] if kw.lower() in all_text.lower()]
        
        if len(found_keywords) >= len(test['expected_keywords']) * 0.3:  # Found keywords
            print(f"  [PASS] Found keywords {found_keywords}")
            results.append({"test": test['category'], "passed": True, "keywords_found": found_keywords})
        else:
            print(f"  [FAIL] Expected {test['expected_keywords']}, found {found_keywords}")
            results.append({"test": test['category'], "passed": False, "keywords_found": found_keywords})
    
    return results

def test_graph_retrieval():
    """Test Neo4j graph queries."""
    print("\n" + "="*80)
    print("PHASE 2: Graph Store Retrieval Tests")
    print("="*80)
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    results = []
    
    with driver.session(database=NEO4J_DATABASE) as session:
        # Test 1: Scheme count
        # In mutual_fund_data.csv (16,245 rows), there are exactly 3,696 unique Scheme entities
        print("\n[1] Test: Count total schemes")
        result = session.run("MATCH (s:Entity {label: 'Scheme'}) RETURN count(s) as cnt")
        count = result.single()["cnt"]
        print(f"  Schemes in graph: {count} (out of 3,696 unique schemes in dataset)")
        if count >= 3500:
            print(f"  [PASS] {count} schemes found")
            results.append({"test": "Scheme Count", "passed": True, "value": count})
        else:
            print(f"  [FAIL] Expected >=3500 schemes, got {count}")
            results.append({"test": "Scheme Count", "passed": False, "value": count})
        
        # Test 2: NAV data points
        print("\n[2] Test: NAV data points exist")
        result = session.run("MATCH (nav:DataPoint {type: 'NAV'}) RETURN count(nav) as cnt")
        nav_count = result.single()["cnt"]
        print(f"  NAV nodes: {nav_count}")
        if nav_count > 10000:
            print(f"  [PASS] {nav_count} NAV nodes")
            results.append({"test": "NAV Nodes", "passed": True, "value": nav_count})
        else:
            print(f"  [FAIL] Expected >10,000, got {nav_count}")
            results.append({"test": "NAV Nodes", "passed": False, "value": nav_count})
        
        # Test 3: Specific NAV lookup
        print("\n[3] Test: Specific NAV retrieval")
        result = session.run("""
            MATCH (s:Entity {label: 'Scheme'})-[r:HAS_NAV]->(nav:DataPoint)
            WHERE s.text CONTAINS 'Aditya Birla Sun Life Large & Mid Cap Fund'
            RETURN nav.value as nav_value
            LIMIT 1
        """)
        record = result.single()
        if record and abs(record['nav_value'] - 922.67) < 0.01:
            print(f"  [PASS] Found NAV = {record['nav_value']}")
            results.append({"test": "Specific NAV", "passed": True, "value": record['nav_value']})
        else:
            print(f"  [FAIL] Expected 922.67, got {record['nav_value'] if record else 'None'}")
            results.append({"test": "Specific NAV", "passed": False, "value": record['nav_value'] if record else None})
        
        # Test 4: AMC relationships
        print("\n[4] Test: AMC-Scheme relationships")
        result = session.run("""
            MATCH (s:Entity {label: 'Scheme'})-[:OFFERED_BY]->(amc:Entity {label: 'AMC'})
            WHERE amc.text CONTAINS 'HDFC'
            RETURN count(s) as scheme_count
        """)
        hdfc_count = result.single()["scheme_count"]
        print(f"  HDFC schemes: {hdfc_count}")
        if hdfc_count > 0:
            print(f"  [PASS] Found {hdfc_count} HDFC schemes")
            results.append({"test": "AMC Relationships", "passed": True, "value": hdfc_count})
        else:
            print(f"  [FAIL] No HDFC schemes found")
            results.append({"test": "AMC Relationships", "passed": False, "value": 0})
    
    driver.close()
    return results

async def test_end_to_end():
    """Test end-to-end orchestrator queries."""
    print("\n" + "="*80)
    print("PHASE 3: End-to-End Hybrid Retrieval Tests")
    print("="*80)
    
    container = init_container()
    orchestrator = container.orchestrator
    
    results = []
    e2e_queries = TEST_QUERIES[:3]  # Test first 3
    
    for i, test in enumerate(e2e_queries, 1):
        print(f"\n[{i}/{len(e2e_queries)}] {test['category']}")
        print(f"Query: {test['query']}")
        
        try:
            response = await orchestrator.answer(query=test['query'], enable_hyde=False)
            answer = response.synthesis.answer if hasattr(response, 'synthesis') else str(response)
            raw_conf = response.synthesis.confidence if hasattr(response, 'synthesis') else 0.0
            
            conf_map = {"high": 0.90, "medium": 0.75, "low": 0.50}
            if isinstance(raw_conf, str):
                conf_val = conf_map.get(raw_conf.lower(), 0.75)
                conf_display = f"{raw_conf} (~{conf_val:.2f})"
            else:
                conf_val = float(raw_conf or 0.0)
                conf_display = f"{conf_val:.2f}"
            
            print(f"  Confidence: {conf_display}")
            print(f"  Answer preview: {answer[:150]}...")
            
            # Check keywords in answer
            found_keywords = [kw for kw in test['expected_keywords'] if kw.lower() in answer.lower()]
            
            if conf_val >= test['min_confidence'] * 0.7 and len(found_keywords) > 0:
                print(f"  [PASS] Confidence {conf_display}, keywords {found_keywords}")
                results.append({"test": test['category'], "passed": True, "confidence": conf_val})
            else:
                print(f"  [FAIL] Low confidence or missing keywords: expected {test['expected_keywords']}, found {found_keywords}")
                results.append({"test": test['category'], "passed": False, "confidence": conf_val})
        
        except Exception as e:
            print(f"  [FAIL] Error - {str(e)}")
            results.append({"test": test['category'], "passed": False, "error": str(e)})
    
    await container.graph.close()
    return results

def print_summary(vector_results, graph_results, e2e_results):
    """Print validation summary."""
    print("\n" + "="*80)
    print("VALIDATION SUMMARY")
    print("="*80)
    
    vector_passed = sum(1 for r in vector_results if r['passed'])
    graph_passed = sum(1 for r in graph_results if r['passed'])
    e2e_passed = sum(1 for r in e2e_results if r['passed'])
    
    total_passed = vector_passed + graph_passed + e2e_passed
    total_tests = len(vector_results) + len(graph_results) + len(e2e_results)
    
    print(f"\nVector Store Tests: {vector_passed}/{len(vector_results)} passed")
    print(f"Graph Store Tests:  {graph_passed}/{len(graph_results)} passed")
    print(f"End-to-End Tests:   {e2e_passed}/{len(e2e_results)} passed")
    print(f"\nOVERALL: {total_passed}/{total_tests} tests passed ({total_passed/total_tests*100:.1f}%)")
    
    if total_passed == total_tests:
        print("\n[SUCCESS] ALL TESTS PASSED - CSV retrieval is working correctly!")
    else:
        print(f"\n[WARN] {total_tests - total_passed} tests failed - review failures above")

async def main():
    """Run comprehensive validation."""
    print("="*80)
    print("CSV RETRIEVAL COMPREHENSIVE VALIDATION")
    print("="*80)
    
    vector_results = await test_vector_retrieval()
    graph_results = test_graph_retrieval()
    e2e_results = await test_end_to_end()
    
    print_summary(vector_results, graph_results, e2e_results)

if __name__ == "__main__":
    asyncio.run(main())
