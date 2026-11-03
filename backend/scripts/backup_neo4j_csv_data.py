#!/usr/bin/env python
"""Export Neo4j CSV-related entities and relationships to JSON."""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
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

BACKUP_ROOT = Path("data/backups/neo4j")
if not BACKUP_ROOT.parent.exists() and Path("backend/data").exists():
    BACKUP_ROOT = Path("backend/data/backups/neo4j")

def backup_neo4j_csv_data():
    """Backup all CSV-related entities and relationships."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_ROOT / f"backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session(database=NEO4J_DATABASE) as session:
        # Backup Scheme entities
        schemes = session.run("""
            MATCH (s:Entity {label: 'Scheme'})
            WHERE s.source = 'mutual_fund_data.csv'
            RETURN s
        """).data()
        
        with open(backup_dir / "schemes.json", "w", encoding="utf-8") as f:
            json.dump(schemes, f, indent=2, default=str)
        print(f"[OK] Backed up {len(schemes)} scheme entities")
        
        # Backup AMC entities
        amcs = session.run("""
            MATCH (a:Entity {label: 'AMC'})
            WHERE a.source = 'mutual_fund_data.csv'
            RETURN a
        """).data()
        
        with open(backup_dir / "amcs.json", "w", encoding="utf-8") as f:
            json.dump(amcs, f, indent=2, default=str)
        print(f"[OK] Backed up {len(amcs)} AMC entities")
        
        # Backup Category entities
        categories = session.run("""
            MATCH (c:Entity {label: 'Category'})
            WHERE c.source = 'mutual_fund_data.csv'
            RETURN c
        """).data()
        
        with open(backup_dir / "categories.json", "w", encoding="utf-8") as f:
            json.dump(categories, f, indent=2, default=str)
        print(f"[OK] Backed up {len(categories)} category entities")
        
        # Backup relationships
        relationships = session.run("""
            MATCH (s:Entity {label: 'Scheme'})-[r]->(target)
            WHERE s.source = 'mutual_fund_data.csv'
            RETURN type(r) as rel_type, properties(r) as props, 
                   s.text as source_name, target.text as target_name,
                   labels(target) as target_labels
        """).data()
        
        with open(backup_dir / "relationships.json", "w", encoding="utf-8") as f:
            json.dump(relationships, f, indent=2, default=str)
        print(f"[OK] Backed up {len(relationships)} relationships")
    
    driver.close()
    
    # Create metadata
    metadata = {
        "timestamp": timestamp,
        "neo4j_uri": NEO4J_URI,
        "backup_path": str(backup_dir),
        "counts": {
            "schemes": len(schemes),
            "amcs": len(amcs),
            "categories": len(categories),
            "relationships": len(relationships)
        }
    }
    
    with open(backup_dir / "backup_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\n[OK] Neo4j backup created: {backup_dir}")
    return backup_dir

if __name__ == "__main__":
    backup_neo4j_csv_data()
