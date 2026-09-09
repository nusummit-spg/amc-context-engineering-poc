# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
build_50doc_faiss_index.py
==========================
Phase 2 Ingestion: Build 50-Document FAISS Index with BAAI/bge-small-en-v1.5
and Hybrid Structural / Clause-Aware Chunking.

Aggregates documents across all 4 strategic tiers:
  - Tier 1: SEBI Master Circulars (8 docs)
  - Tier 2: High-Value SEBI Circulars (10 docs)
  - Tier 3: Adani Corporate Intelligence (10 docs)
  - Tier 4: AMC Fund House SIDs (8 docs)
  - Existing Core: Selected Source Documents (14 docs)
"""
from __future__ import annotations
import sys
import os
import json
import pickle
import time
from pathlib import Path
try:
    import pymupdf as fitz  # PyMuPDF
except ImportError:
    import fitz


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.engine import faiss_store as fs
from app.ingestion.chunker import _split_long_text, approx_tokens

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_INDEX_DIR = Path(__file__).resolve().parent.parent / "faiss_indexes" / "taxonomy_showcase"

# 50 Document Target Matrix
TARGET_DOCUMENTS = [
    # --- Tier 1: SEBI Master Circulars ---
    {"path": "Docs/AMC Docs/AMC/SEBI Master Circulars/Master Circular for Mutual Funds.pdf", "tier": "Tier 1", "category": "sebi_master_circular"},
    {"path": "Docs/AMC Docs/AMC/SEBI Master Circulars/Master Circular for Investment Advisers.pdf", "tier": "Tier 1", "category": "sebi_master_circular"},
    {"path": "Docs/AMC Docs/AMC/SEBI Master Circulars/Master Circular for Portfolio Managers.pdf", "tier": "Tier 1", "category": "sebi_master_circular"},
    {"path": "Docs/AMC Docs/AMC/SEBI Master Circulars/Master Circular for Alternative Investment Funds (AIFs).pdf", "tier": "Tier 1", "category": "sebi_master_circular"},
    {"path": "Docs/AMC Docs/AMC/SEBI Master Circulars/Master Circular for ESG Rating Providers (ERPs).pdf", "tier": "Tier 1", "category": "sebi_master_circular"},
    {"path": "Docs/AMC Docs/AMC/SEBI Master Circulars/Master Circular for Stock Brokers.pdf", "tier": "Tier 1", "category": "sebi_master_circular"},
    {"path": "Docs/AMC Docs/AMC/SEBI Master Circulars/Guidelines on Anti-Money Laundering (AML) Standards and Combating the Financing of Terrorism (CFT).pdf", "tier": "Tier 1", "category": "sebi_master_circular"},
    {"path": "Docs/AMC Docs/AMC/SEBI Master Circulars/Master Circular for Research Analysts.pdf", "tier": "Tier 1", "category": "sebi_master_circular"},

    # --- Tier 2: High-Value SEBI Circulars ---
    {"path": "Docs/AMC Docs/AMC/SEBI Circulars/Categorization and Rationalization of Mutual Fund Schemes.pdf", "tier": "Tier 2", "category": "sebi_circular"},
    {"path": "Docs/AMC Docs/AMC/SEBI Circulars/Regulatory framework for Specialized Investment Funds.pdf", "tier": "Tier 2", "category": "sebi_circular"},
    {"path": "Docs/AMC Docs/AMC/SEBI Circulars/Framework for Environment, Social and Governance (ESG) Debt Securities (other than green debt securities).pdf", "tier": "Tier 2", "category": "sebi_circular"},
    {"path": "Docs/AMC Docs/AMC/SEBI Circulars/Reclassification of Real Estate Investment Trusts (REITs) as equity related instruments for facilitating enhanced participation by Mutual Funds and Specialized Investment Funds (SIFs).pdf", "tier": "Tier 2", "category": "sebi_circular"},
    {"path": "Docs/AMC Docs/AMC/SEBI Circulars/Timelines for rebalancing of portfolios of mutual fund schemes in cases of all passive breaches.pdf", "tier": "Tier 2", "category": "sebi_circular"},
    {"path": "Docs/AMC Docs/AMC/SEBI Circulars/Valuation of physical Gold and Silver held by mutual fund schemes.pdf", "tier": "Tier 2", "category": "sebi_circular"},
    {"path": "Docs/AMC Docs/AMC/SEBI Circulars/Timelines for deployment of funds collected by Asset Management Companies (AMCs) in New Fund Offer (NFO) as per asset allocation of the scheme.pdf", "tier": "Tier 2", "category": "sebi_circular"},
    {"path": "Docs/AMC Docs/AMC/SEBI Circulars/Introduction of Voluntary Lock-in - Debit freeze facility to Mutual Fund folios.pdf", "tier": "Tier 2", "category": "sebi_circular"},
    {"path": "Docs/AMC Docs/AMC/SEBI Circulars/Clarification on Regulatory framework for Specialized Investment Funds.pdf", "tier": "Tier 2", "category": "sebi_circular"},
    {"path": "Docs/AMC Docs/AMC/SEBI Circulars/Transaction charges paid to Mutual Fund Distributors.pdf", "tier": "Tier 2", "category": "sebi_circular"},

    # --- Tier 3: Adani Corporate Intelligence ---
    {"path": "Docs/selected_source_documents/Adani_Portfolio_H1FY25_ESG.pdf", "tier": "Tier 3", "category": "adani_corporate"},
    {"path": "Docs/Adani_Enterprises_Ltd_Investors_Docs/Adani_Enterprises_Ltd_Investors/Adani_Portfolio_H1FY25_Credit_Summary.pdf", "tier": "Tier 3", "category": "adani_corporate"},
    {"path": "Docs/Adani_Enterprises_Ltd_Investors_Docs/Adani_Enterprises_Ltd_Investors/Adani_Portfolio_H1FY25_Results_Compendium.pdf", "tier": "Tier 3", "category": "adani_corporate"},
    {"path": "Docs/Adani_Enterprises_Ltd_Investors_Docs/Adani_Enterprises_Ltd_Investors/Adani_Portfolio_Equity_Note_H1_FY25.pdf", "tier": "Tier 3", "category": "adani_corporate"},
    {"path": "Docs/Adani_Enterprises_Ltd_Investors_Docs/Adani_Enterprises_Ltd_Investors/AEL_AR_FY25.pdf", "tier": "Tier 3", "category": "adani_corporate"},
    {"path": "Docs/selected_source_documents/AEL_AR_FY24.pdf", "tier": "Tier 3", "category": "adani_corporate"},
    {"path": "Docs/Adani_Enterprises_Ltd_Investors_Docs/Adani_Enterprises_Ltd_Investors/AEL_AR_FY23.pdf", "tier": "Tier 3", "category": "adani_corporate"},
    {"path": "Docs/Adani_Enterprises_Ltd_Investors_Docs/Adani_Enterprises_Ltd_Investors/AEL_Earnings_Call_Q4_FY25.pdf", "tier": "Tier 3", "category": "adani_corporate"},
    {"path": "Docs/Adani_Enterprises_Ltd_Investors_Docs/Adani_Enterprises_Ltd_Investors/AEL_Earnings_Call_Q1_FY26.pdf", "tier": "Tier 3", "category": "adani_corporate"},
    {"path": "Docs/Adani_Enterprises_Ltd_Investors_Docs/Adani_Enterprises_Ltd_Investors/ESG_Deck_June_25.pdf", "tier": "Tier 3", "category": "adani_corporate"},

    # --- Tier 4: AMC Fund House SIDs ---
    {"path": "Docs/AMC Docs/AMC/MF/HDFC Mutual Fund/HDFC Banking & Financial Services Fund Info Doc.pdf", "tier": "Tier 4", "category": "amc_sid"},
    {"path": "Docs/AMC Docs/AMC/MF/SBI Mutual Fund/SBI EQUITY HYBRID FUND Info Doc.pdf", "tier": "Tier 4", "category": "amc_sid"},
    {"path": "Docs/AMC Docs/AMC/MF/Axis Mutual Fund/Axis Aggressive Hybrid Fund Info Doc.pdf", "tier": "Tier 4", "category": "amc_sid"},
    {"path": "Docs/AMC Docs/AMC/MF/Tata Mutual Fund/Tata Banking & Financial Services Fund Info Doc.pdf", "tier": "Tier 4", "category": "amc_sid"},
    {"path": "Docs/AMC Docs/AMC/MF/Groww Mutual Fund/Groww Aggressive Hybrid Fund Info Doc.pdf", "tier": "Tier 4", "category": "amc_sid"},
    {"path": "Docs/AMC Docs/AMC/MF/360 ONE MF/360 ONE Flexicap Fund Info Doc.pdf", "tier": "Tier 4", "category": "amc_sid"},
    {"path": "Docs/AMC Docs/AMC/MF/Bajaj Finserv Mutual Fund/Bajaj Finserv Flexi Cap Fund Info Doc.pdf", "tier": "Tier 4", "category": "amc_sid"},
    {"path": "Docs/AMC Docs/AMC/MF/Zerodha Mutual Fund/Zerodha Nifty 50 ETF Info Doc.pdf", "tier": "Tier 4", "category": "amc_sid"},

    # --- Baseline Corpus ---
    {"path": "Docs/selected_source_documents/AEL_Annual_Return_FY_2024.pdf", "tier": "Baseline", "category": "adani_corporate"},
    {"path": "Docs/selected_source_documents/AEL_Earnings_Call_Q1_FY19.pdf", "tier": "Baseline", "category": "adani_corporate"},
    {"path": "Docs/selected_source_documents/AEL_Earnings_Call_Q4_FY24.pdf", "tier": "Baseline", "category": "adani_corporate"},
    {"path": "Docs/selected_source_documents/April 2024.pdf", "tier": "Baseline", "category": "fund_performance"},
    {"path": "Docs/selected_source_documents/April 2025.pdf", "tier": "Baseline", "category": "fund_performance"},
    {"path": "Docs/selected_source_documents/May 2024.pdf", "tier": "Baseline", "category": "fund_performance"},
    {"path": "Docs/selected_source_documents/Borrowing by Mutual Funds.pdf", "tier": "Baseline", "category": "sebi_circular"},
    {"path": "Docs/selected_source_documents/Disclosure of Risk adjusted Return - Information Ratio (IR) for Mutual Fund Schemes..pdf", "tier": "Baseline", "category": "sebi_circular"},
    {"path": "Docs/selected_source_documents/Guidelines for Investment Advisers.pdf", "tier": "Baseline", "category": "sebi_circular"},
    {"path": "Docs/selected_source_documents/Safer participation of retail investors in Algorithmic trading.pdf", "tier": "Baseline", "category": "sebi_circular"},
]


def build_50doc_index():
    print("=" * 80)
    print("  PHASE 2: 50-DOCUMENT FAISS INDEX BUILD (BAAI/bge-small-en-v1.5)")
    print("=" * 80)
    OUTPUT_INDEX_DIR.mkdir(parents=True, exist_ok=True)

    all_chunks = []
    metadata_list = []
    docs_processed = 0

    for item in TARGET_DOCUMENTS:
        rel_path = item["path"]
        full_path = PROJECT_ROOT / rel_path
        if not full_path.exists():
            print(f"[WARNING] File not found: {rel_path}")
            continue

        doc_name = full_path.name
        tier = item["tier"]
        category = item["category"]
        print(f"[{docs_processed+1}/{len(TARGET_DOCUMENTS)}] Ingesting ({tier}) {doc_name}...")

        try:
            doc = fitz.open(full_path)
            doc_chunks = 0
            for page_num, page in enumerate(doc, start=1):
                page_text = page.get_text().strip()
                if not page_text:
                    continue

                # Apply Clause-Aware / Structural Chunking
                pieces = _split_long_text(page_text, max_tokens=350)
                for order, piece in enumerate(pieces):
                    chunk_text = f"[DOC: {doc_name} | PAGE: {page_num} | CATEGORY: {category}]\n{piece.strip()}"
                    all_chunks.append(chunk_text)
                    metadata_list.append({
                        "doc_name": doc_name,
                        "page_num": page_num,
                        "category": category,
                        "tier": tier,
                        "token_count": approx_tokens(piece),
                        "order": order,
                    })
                    doc_chunks += 1
            doc.close()
            docs_processed += 1
            print(f"    -> {doc_chunks} chunks extracted.")
        except Exception as exc:
            print(f"❌ Failed to extract {doc_name}: {exc}")

    print("-" * 80)
    print(f"Total Documents Processed: {docs_processed}")
    print(f"Total Chunks Created: {len(all_chunks)}")

    if not all_chunks:
        print("Error: No chunks created.")
        return

    # Compute BAAI/bge-small-en-v1.5 embeddings
    print("\nComputing embeddings with BAAI/bge-small-en-v1.5...")
    dim = 384
    index = faiss.IndexFlatIP(dim)
    batch_size = 128

    t0 = time.time()
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i : i + batch_size]
        vecs = fs._embed_texts(batch)
        faiss.normalize_L2(vecs)
        index.add(vecs)
        print(f"  Processed {min(i + batch_size, len(all_chunks))}/{len(all_chunks)} chunks...")

    latency = time.time() - t0
    print(f"Embeddings finished in {latency:.2f}s.")

    # Save FAISS Index and Payload Pkl
    index_path = OUTPUT_INDEX_DIR / "index.faiss"
    pkl_path = OUTPUT_INDEX_DIR / "index.pkl"

    faiss.write_index(index, str(index_path))
    with open(pkl_path, "wb") as f:
        pickle.dump({
            "children": [{"text": text, **meta} for text, meta in zip(all_chunks, metadata_list)],
            "total_docs": docs_processed,
            "embedding_model": "BAAI/bge-small-en-v1.5",
        }, f)

    print(f"[SUCCESS] Saved 50-Doc Index to {OUTPUT_INDEX_DIR}")
    print("=" * 80)


if __name__ == "__main__":
    build_50doc_index()
