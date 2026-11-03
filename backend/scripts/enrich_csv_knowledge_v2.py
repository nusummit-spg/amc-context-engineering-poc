#!/usr/bin/env python
"""Enhanced CSV enrichment with data value nodes for Neo4j."""

import csv
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()
load_dotenv("backend/.env")

# Paths
CHUNKS_DIR = Path("data/source_docs/chunks")
if not CHUNKS_DIR.exists() and Path("backend/data/source_docs/chunks").exists():
    CHUNKS_DIR = Path("backend/data/source_docs/chunks")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "contextgraph")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

def dedup_key(label: str, text: str) -> str:
    """Create deduplication key."""
    norm = re.sub(r"\s+", " ", text.strip().lower())
    return f"{label}::{norm}"

def enrich_csv_with_data_values():
    """Enrich CSV data with NAV and AUM value nodes."""
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    # Ensure indexes exist
    with driver.session(database=NEO4J_DATABASE) as session:
        try:
            session.run("CREATE INDEX entity_dedup_idx IF NOT EXISTS FOR (e:Entity) ON (e.dedup_key)")
            session.run("CREATE INDEX entity_text_idx IF NOT EXISTS FOR (e:Entity) ON (e.text)")
            session.run("CREATE INDEX datapoint_type_idx IF NOT EXISTS FOR (d:DataPoint) ON (d.type)")
            session.run("CREATE INDEX metric_type_idx IF NOT EXISTS FOR (m:MetricValue) ON (m.type)")
        except Exception as exc:
            print("Index creation notice:", exc)
    
    # Get all chunk files
    chunk_files = sorted(CHUNKS_DIR.glob("mutual_fund_data_chunk_*.csv"))
    print(f"Found {len(chunk_files)} chunk files", flush=True)
    
    total_nav_nodes = 0
    total_schemes_processed = 0
    
    for chunk_file in chunk_files:
        print(f"\nProcessing {chunk_file.name}...", flush=True)
        
        with open(chunk_file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        batch_data = []
        
        for row in rows:
            scheme_name = row.get("Scheme_Name", "").strip()
            nav_value = row.get("NAV", "").strip()
            nav_date = row.get("Latest_NAV_Date", "").strip()
            aum_value = row.get("Average_AUM_Cr", "").strip()
            aum_quarter = row.get("AAUM_Quarter", "").strip()
            amc_name = row.get("AMC", "").strip()
            category_name = row.get("Scheme_Category", "").strip()
            
            if not scheme_name:
                continue
            
            scheme_key = dedup_key("Scheme", scheme_name)
            amc_key = dedup_key("AMC", amc_name) if amc_name else None
            cat_key = dedup_key("Category", category_name) if category_name else None
            
            nav_float = None
            if nav_value and nav_value != "-":
                try:
                    nav_float = float(nav_value)
                except (ValueError, TypeError):
                    nav_float = None
            
            aum_float = None
            if aum_value and aum_value != "-":
                try:
                    aum_float = float(aum_value)
                except (ValueError, TypeError):
                    aum_float = None
            
            batch_data.append({
                "scheme_key": scheme_key,
                "scheme_name": scheme_name,
                "amc_key": amc_key,
                "amc_name": amc_name,
                "category_key": cat_key,
                "category_name": category_name,
                "nav_value": nav_float,
                "nav_date": nav_date or "unknown",
                "aum_value": aum_float,
                "aum_quarter": aum_quarter or "unknown",
                "source": chunk_file.name
            })
        
        # Batch insert into Neo4j in sub-batches of 250 for optimal performance
        sub_batch_size = 250
        chunk_nav_count = 0
        for i in range(0, len(batch_data), sub_batch_size):
            sub_batch = batch_data[i:i + sub_batch_size]
            with driver.session(database=NEO4J_DATABASE) as session:
                result = session.run("""
                    UNWIND $batch AS row
                    
                    // Match or create the scheme entity
                    MERGE (s:Entity {dedup_key: row.scheme_key})
                    ON CREATE SET s.text = row.scheme_name, s.label = 'Scheme', s.source = 'mutual_fund_data.csv'
                    ON MATCH SET s.text = coalesce(s.text, row.scheme_name), s.label = 'Scheme'
                    
                    // Link to AMC entity if AMC present
                    FOREACH (_ IN CASE WHEN row.amc_key IS NOT NULL THEN [1] ELSE [] END |
                        MERGE (a:Entity {dedup_key: row.amc_key})
                        ON CREATE SET a.text = row.amc_name, a.label = 'AMC', a.source = 'mutual_fund_data.csv'
                        ON MATCH SET a.label = 'AMC'
                        MERGE (s)-[:OFFERED_BY {confidence: 1.0, source: 'mutual_fund_data.csv'}]->(a)
                    )
                    
                    // Link to Category entity if Category present
                    FOREACH (_ IN CASE WHEN row.category_key IS NOT NULL THEN [1] ELSE [] END |
                        MERGE (c:Entity {dedup_key: row.category_key})
                        ON CREATE SET c.text = row.category_name, c.label = 'Category', c.source = 'mutual_fund_data.csv'
                        ON MATCH SET c.label = 'Category'
                        MERGE (s)-[:IN_CATEGORY {confidence: 1.0, source: 'mutual_fund_data.csv'}]->(c)
                    )
                    
                    // Create or update NAV data point if available
                    FOREACH (_ IN CASE WHEN row.nav_value IS NOT NULL THEN [1] ELSE [] END |
                        MERGE (nav:DataPoint {
                            type: 'NAV',
                            value: row.nav_value,
                            as_of_date: row.nav_date
                        })
                        ON CREATE SET nav.currency = 'INR',
                                      nav.created_from = row.source
                        
                        MERGE (s)-[r_nav:HAS_NAV {as_of_date: row.nav_date}]->(nav)
                        ON CREATE SET r_nav.source = row.source,
                                      r_nav.confidence = 1.0
                    )
                    
                    // Create AUM data point if available
                    FOREACH (_ IN CASE WHEN row.aum_value IS NOT NULL THEN [1] ELSE [] END |
                        MERGE (aum:MetricValue {
                            type: 'AUM',
                            value: row.aum_value,
                            quarter: row.aum_quarter
                        })
                        ON CREATE SET aum.unit = 'Crores',
                                      aum.created_from = row.source
                        
                        MERGE (s)-[r_aum:HAS_AUM {quarter: row.aum_quarter}]->(aum)
                        ON CREATE SET r_aum.source = row.source,
                                      r_aum.confidence = 1.0
                    )
                    
                    RETURN count(s) as scnt
                """, batch=sub_batch)
                res = result.single()
                chunk_nav_count += sum(1 for r in sub_batch if r["nav_value"] is not None)
        
        total_nav_nodes += chunk_nav_count
        total_schemes_processed += len(batch_data)
        print(f"  [OK] Processed {len(batch_data)} schemes, added NAV points ({chunk_nav_count})", flush=True)
    
    driver.close()
    
    print(f"\n[SUCCESS] Enrichment complete!", flush=True)
    print(f"  Total NAV entries recorded: {total_nav_nodes}", flush=True)
    print(f"  Total schemes processed: {total_schemes_processed}", flush=True)

if __name__ == "__main__":
    enrich_csv_with_data_values()
