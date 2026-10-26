"""Operational script to enrich mutual_fund_data.csv into VectorStore and Neo4j Knowledge Graph."""

import csv
import json
import os
import re
from pathlib import Path
import faiss
from fastembed import TextEmbedding
import numpy as np

# Neo4j
from neo4j import GraphDatabase

CSV_PATH = "backend/data/source_docs/mutual_fund_data.csv"
if not os.path.exists(CSV_PATH):
    CSV_PATH = "data/source_docs/mutual_fund_data.csv"

VECTOR_STORE_DIR = "backend/data/vector_store/v2_baseline_20260814"
if not os.path.exists(VECTOR_STORE_DIR):
    VECTOR_STORE_DIR = "data/vector_store/v2_baseline_20260814"

INDEX_PATH = os.path.join(VECTOR_STORE_DIR, "index.faiss")
PAYLOAD_PATH = os.path.join(VECTOR_STORE_DIR, "payloads.json")
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "contextgraph")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


def dedup_key(label: str, text: str) -> str:
    norm = re.sub(r"\s+", " ", text.strip().lower())
    return f"{label}::{norm}"


def main():
    print(f"--- 1. Loading CSV from {CSV_PATH} ---")
    with open(CSV_PATH, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Loaded {len(rows)} rows from CSV.")

    # ── Part 1: Update FAISS & Payloads ──────────────────────────────────────────
    print(f"--- 2. Updating Vector Store payloads at {VECTOR_STORE_DIR} ---")
    with open(PAYLOAD_PATH, "r", encoding="utf-8") as f:
        payloads = {int(k): v for k, v in json.load(f).items()}

    index = faiss.read_index(INDEX_PATH)
    next_id = (max(payloads.keys()) + 1) if payloads else 0

    csv_chunk_count = 0
    # Map row index to row data for fast entity enrichment
    row_by_idx = {i: r for i, r in enumerate(rows, start=1)}

    for pid, p in payloads.items():
        doc_id = p.get("document_id", "")
        chunk_id = p.get("chunk_id", "")
        if "mutual_fund_data.csv" in doc_id or "mutual_fund_data.csv" in chunk_id:
            csv_chunk_count += 1
            # Update taxonomy
            p["taxonomy_paths"] = ["Product/Mutual Funds", "Operations/NAV"]
            # Extract row index from chunk_id (e.g. csv_mutual_fund_data.csv_123)
            match = re.search(r"_(\d+)$", chunk_id)
            if match:
                ridx = int(match.group(1))
                r = row_by_idx.get(ridx)
                if r:
                    scheme = r.get("Scheme_Name", "").strip()
                    amc = r.get("AMC", "").strip()
                    cat = r.get("Scheme_Category", "").strip()
                    isin = r.get("ISIN_Div_Payout/Growth", "").strip()
                    code = r.get("Scheme_Code", "").strip()
                    ents = [e for e in [scheme, amc, cat, isin, code] if e and e != "-"]
                    p["entity_ids"] = ents

    print(f"Enriched {csv_chunk_count} existing CSV chunks with taxonomy_paths & entity_ids.")

    # Check if dataset overview chunks already exist
    has_overview = any(p.get("chunk_id", "").startswith("csv_mutual_fund_data_overview") for p in payloads.values())
    if not has_overview:
        print("Generating dataset overview chunks...")
        overview_chunks = [
            {
                "id": "csv_mutual_fund_data_overview_1",
                "text": (
                    "Dataset Overview: mutual_fund_data.csv is the comprehensive master dataset of Indian mutual fund "
                    "schemes, containing 16,245 records across 54 Asset Management Companies (AMCs) and 50 scheme categories. "
                    "This CSV file provides verified regulatory and operational master data including scheme codes, scheme names, "
                    "fund houses (AMCs), scheme types (open-ended/closed-ended), scheme categories (Equity, Debt, Hybrid, Solution Oriented, "
                    "Index Funds, Liquid Funds), Net Asset Values (NAV), NAV dates, Average Assets Under Management (AUM in Crores), "
                    "AAUM quarters, and ISIN identifiers for both Growth and IDCW options."
                ),
                "title": "Dataset Overview: mutual_fund_data.csv (Master Fund Data)",
            },
            {
                "id": "csv_mutual_fund_data_overview_2",
                "text": (
                    "CSV File Structure and Column Definitions for mutual_fund_data.csv:\n"
                    "- Scheme_Code: Unique AMFI numeric scheme identifier (e.g., 100033).\n"
                    "- Scheme_Name: Full legal name of the mutual fund scheme (e.g., Aditya Birla Sun Life Large & Mid Cap Fund).\n"
                    "- AMC: The Asset Management Company or Fund House managing the scheme (e.g., Aditya Birla Sun Life AMC Limited).\n"
                    "- Scheme_Type: Open Ended or Closed Ended structure.\n"
                    "- Scheme_Category: SEBI categorization (e.g., Equity Scheme - Large & Mid Cap Fund, Debt Scheme - Liquid Fund).\n"
                    "- Scheme_NAV_Name: Specific option plan (Regular Growth, Direct Growth, IDCW).\n"
                    "- Scheme_Min_Amt: Minimum lump-sum investment amount (e.g., 5000).\n"
                    "- NAV: Latest Net Asset Value per unit in Indian Rupees (INR).\n"
                    "- Latest_NAV_Date: Effective valuation date of the reported NAV.\n"
                    "- Average_AUM_Cr: Quarterly Average Assets Under Management in INR Crores.\n"
                    "- AAUM_Quarter: Reporting quarter for AUM (e.g., January - March 2026).\n"
                    "- ISIN_Div_Payout/Growth: International Securities Identification Number.\n"
                    "- Launch_Date / Closure_Date: Inception date and closure date of the fund."
                ),
                "title": "CSV Column Definitions: mutual_fund_data.csv",
            },
            {
                "id": "csv_mutual_fund_data_overview_3",
                "text": (
                    "Covered AMCs and Fund Houses in mutual_fund_data.csv: Includes 54 major Indian asset managers such as "
                    "Aditya Birla Sun Life AMC, Axis Mutual Fund, DSP Asset Managers, HDFC Mutual Fund, ICICI Prudential Mutual Fund, "
                    "SBI Mutual Fund, Nippon India Mutual Fund, Kotak Mahindra Mutual Fund, UTI Mutual Fund, Bandhan Mutual Fund, "
                    "Tata Mutual Fund, Mirae Asset Mutual Fund, Motilal Oswal Mutual Fund, Edelweiss Mutual Fund, and others. "
                    "The dataset spans all major categories: Large Cap, Large & Mid Cap, Mid Cap, Small Cap, Flexi Cap, Multi Cap, "
                    "Liquid, Ultra Short Duration, Low Duration, Money Market, Short Duration, Medium Duration, Banking and PSU, "
                    "Corporate Bond, Gilt, Arbitrage, Balanced Advantage, and Index Funds."
                ),
                "title": "AMCs and Categories Catalog: mutual_fund_data.csv",
            },
        ]

        embedder = TextEmbedding(model_name=EMBEDDING_MODEL)
        ov_texts = [c["text"] for c in overview_chunks]
        ov_embeddings = list(embedder.embed(ov_texts))
        ov_matrix = np.asarray(ov_embeddings, dtype="float32")
        faiss.normalize_L2(ov_matrix)

        new_ids = np.arange(next_id, next_id + len(overview_chunks), dtype="int64")
        index.add_with_ids(ov_matrix, new_ids)

        for i, c in enumerate(overview_chunks):
            assigned = int(new_ids[i])
            payloads[assigned] = {
                "chunk_id": c["id"],
                "document_id": "mutual_fund_data.csv",
                "document_title": c["title"],
                "source_filename": "mutual_fund_data.csv",
                "page_start": 1,
                "page_end": 1,
                "section_locator": "dataset.overview",
                "corpus_version": "v2_baseline_20260814",
                "text": c["text"],
                "order": assigned,
                "taxonomy_paths": ["Product/Mutual Funds", "Operations/NAV"],
                "entity_ids": ["mutual_fund_data.csv", "Mutual Funds", "CSV", "AMC", "NAV", "AUM"],
            }
        print(f"Added {len(overview_chunks)} dataset overview chunks to FAISS index.")

    # Save FAISS index and payloads
    print(f"Saving updated FAISS index ({index.ntotal} vectors)...")
    faiss.write_index(index, INDEX_PATH)
    with open(PAYLOAD_PATH, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in payloads.items()}, f, indent=2)
    print("Vector store update complete!")

    # ── Part 2: Neo4j Ingestion ──────────────────────────────────────────────────
    print(f"--- 3. Ingesting Schemes & AMCs into Neo4j at {NEO4J_URI} ---")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    # Aggregate distinct AMCs, Categories, and Schemes
    amc_set = set()
    category_set = set()
    schemes_dict = {}

    for r in rows:
        scheme_name = r.get("Scheme_Name", "").strip()
        amc = r.get("AMC", "").strip()
        cat = r.get("Scheme_Category", "").strip()
        nav_val = r.get("NAV", "").strip()
        aum_val = r.get("Average_AUM_Cr", "").strip()
        code = r.get("Scheme_Code", "").strip()
        isin = r.get("ISIN_Div_Payout/Growth", "").strip()

        if amc:
            amc_set.add(amc)
        if cat:
            category_set.add(cat)
        if scheme_name:
            # Keep representative row with valid NAV/AUM
            if scheme_name not in schemes_dict or (nav_val and not schemes_dict[scheme_name].get("nav")):
                schemes_dict[scheme_name] = {
                    "name": scheme_name,
                    "amc": amc,
                    "category": cat,
                    "nav": nav_val,
                    "aum_cr": aum_val,
                    "code": code,
                    "isin": isin,
                }

    print(f"Distinct AMCs: {len(amc_set)}, Categories: {len(category_set)}, Schemes: {len(schemes_dict)}")

    with driver.session(database=NEO4J_DATABASE) as session:
        # Schema index
        try:
            session.run("CREATE INDEX entity_dedup_idx IF NOT EXISTS FOR (e:Entity) ON (e.dedup_key)")
            session.run("CREATE INDEX entity_text_idx IF NOT EXISTS FOR (e:Entity) ON (e.text)")
        except Exception as exc:
            print("Index creation notice:", exc)

        # 1. Insert AMCs
        amc_rows = [{"key": dedup_key("AMC", a), "text": a, "label": "AMC"} for a in amc_set]
        session.run(
            """
            UNWIND $rows AS r
            MERGE (e:Entity {dedup_key: r.key})
            ON CREATE SET e.text = r.text, e.label = r.label, e.source = 'mutual_fund_data.csv'
            ON MATCH SET e.label = r.label
            """,
            rows=amc_rows,
        )
        print(f"Inserted {len(amc_rows)} AMC entities into Neo4j.")

        # 2. Insert Categories
        cat_rows = [{"key": dedup_key("Category", c), "text": c, "label": "Category"} for c in category_set]
        session.run(
            """
            UNWIND $rows AS r
            MERGE (e:Entity {dedup_key: r.key})
            ON CREATE SET e.text = r.text, e.label = r.label, e.source = 'mutual_fund_data.csv'
            ON MATCH SET e.label = r.label
            """,
            rows=cat_rows,
        )
        print(f"Inserted {len(cat_rows)} Category entities into Neo4j.")

        # 3. Batch insert Schemes & Relationships
        scheme_list = list(schemes_dict.values())
        batch_size = 500
        for i in range(0, len(scheme_list), batch_size):
            batch = scheme_list[i:i + batch_size]
            scheme_rows = []
            for s in batch:
                s_key = dedup_key("Scheme", s["name"])
                amc_key = dedup_key("AMC", s["amc"]) if s["amc"] else None
                cat_key = dedup_key("Category", s["category"]) if s["category"] else None
                scheme_rows.append({
                    "s_key": s_key,
                    "name": s["name"],
                    "nav": s["nav"],
                    "aum_cr": s["aum_cr"],
                    "code": s["code"],
                    "isin": s["isin"],
                    "amc_key": amc_key,
                    "cat_key": cat_key,
                })

            session.run(
                """
                UNWIND $rows AS r
                MERGE (s:Entity {dedup_key: r.s_key})
                ON CREATE SET s.text = r.name, s.label = 'Scheme', s.product_name = r.name,
                              s.nav = r.nav, s.aum_cr = r.aum_cr, s.code = r.code, s.isin = r.isin,
                              s.source = 'mutual_fund_data.csv'
                ON MATCH SET s.nav = coalesce(r.nav, s.nav), s.aum_cr = coalesce(r.aum_cr, s.aum_cr),
                             s.code = coalesce(r.code, s.code), s.isin = coalesce(r.isin, s.isin)

                FOREACH (_ IN CASE WHEN r.amc_key IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (a:Entity {dedup_key: r.amc_key})
                    MERGE (s)-[:OFFERED_BY {confidence: 1.0, source: 'mutual_fund_data.csv'}]->(a)
                )

                FOREACH (_ IN CASE WHEN r.cat_key IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (c:Entity {dedup_key: r.cat_key})
                    MERGE (s)-[:IN_CATEGORY {confidence: 1.0, source: 'mutual_fund_data.csv'}]->(c)
                )
                """,
                rows=scheme_rows,
            )
            print(f"  Processed schemes batch {i + 1} - {min(i + batch_size, len(scheme_list))}...")

    driver.close()
    print("[SUCCESS] Successfully enriched mutual_fund_data.csv across FAISS and Neo4j!")


if __name__ == "__main__":
    main()
