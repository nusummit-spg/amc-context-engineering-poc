#!/usr/bin/env python
"""Test Neo4j graph enrichment."""

import os
import sys
from dotenv import load_dotenv
from neo4j import GraphDatabase

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()
load_dotenv("backend/.env")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "contextgraph")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

with driver.session(database=NEO4J_DATABASE) as session:
    # Test 1: Count NAV nodes
    result = session.run("MATCH (nav:DataPoint {type: 'NAV'}) RETURN count(nav) as cnt")
    nav_count = result.single()["cnt"]
    print(f"Test 1: NAV nodes created: {nav_count}")
    
    # Test 2: Find specific NAV
    result = session.run("""
        MATCH (s:Entity {label: 'Scheme'})-[r:HAS_NAV]->(nav:DataPoint)
        WHERE s.text CONTAINS 'Aditya Birla Sun Life Large & Mid Cap Fund'
        RETURN s.text as scheme, nav.value as nav, r.as_of_date as date
        LIMIT 1
    """)
    record = result.single()
    if record:
        print(f"Test 2: Found NAV = {record['nav']} for {record['scheme'][:50]}...")
        if abs(record['nav'] - 922.67) < 0.01:
            print("  [OK] NAV value matches expected 922.67")
        else:
            print(f"  [FAIL] Expected 922.67, got {record['nav']}")
    else:
        print("Test 2: [FAIL] NAV not found")

driver.close()
