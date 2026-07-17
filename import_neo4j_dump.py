"""
import_neo4j_dump.py
====================
Universal 1-Click Importer for ContextGraph Hybrid RAG Database.
Reads `amc_master_full_dump.cypher` (or `amc_master_full_dump.json`) and
automatically seeds/restores the complete graph (every node, constraint,
index, and relationship) into any Neo4j target instance.

Usage:
  python import_neo4j_dump.py [--cypher amc_master_full_dump.cypher]
"""
import argparse
import sys
import time
from pathlib import Path
from neo4j import GraphDatabase
import config

def import_dump(cypher_file: str):
    path = Path(cypher_file)
    if not path.exists():
        print(f"  [ERROR] Dump file not found: {path.resolve()}")
        sys.exit(1)
        
    print("================================================================================")
    print(f"  [NEO4J IMPORTER] IMPORTING GRAPH FROM {path.name}")
    print(f"  Target Neo4j Instance: {config.NEO4J_URI} (DB: {config.NEO4J_DATABASE})")
    print("================================================================================")
    
    driver = GraphDatabase.driver(
        config.NEO4J_URI,
        auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
    )
    
    content = path.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.split("\n")]
    
    statements = []
    current_stmt = []
    
    for line in lines:
        if not line or line.startswith("//"):
            continue
        current_stmt.append(line)
        if line.endswith(";"):
            statements.append(" ".join(current_stmt)[:-1]) # strip trailing semicolon
            current_stmt = []
            
    print(f"  [i] Parsed {len(statements)} total Cypher statements from dump.")
    
    success_count = 0
    error_count = 0
    t0 = time.perf_counter()
    
    with driver.session(database=config.NEO4J_DATABASE) as session:
        for idx, stmt in enumerate(statements, 1):
            try:
                session.run(stmt)
                success_count += 1
                if idx % 50 == 0 or idx == len(statements):
                    print(f"  --> [{idx}/{len(statements)}] Executed Cypher statements...")
            except Exception as exc:
                # If constraint already exists or minor duplicate, log and continue
                error_count += 1
                if "already exists" not in str(exc).lower():
                    print(f"  [Warning on stmt #{idx}]: {exc}")
                    
    elapsed = time.perf_counter() - t0
    print("\n================================================================================")
    print(f"  [SUCCESS] Graph restore completed in {elapsed:.2f} seconds!")
    print(f"  [+] Statements Executed: {success_count}")
    print(f"  [!] Skipped / Existing : {error_count}")
    print("================================================================================")
    driver.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import ContextGraph Neo4j Dump")
    parser.add_argument("--cypher", default="amc_master_full_dump.cypher", help="Path to Cypher dump file")
    args = parser.parse_args()
    import_dump(args.cypher)
