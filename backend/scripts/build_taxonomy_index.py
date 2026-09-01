# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
build_taxonomy_index.py
========================
Builds a separate FAISS vector index (taxonomy_showcase) from the
mutual_fund_taxonomy_v0_3.json file. Unlike the main build_index.py which
extracts chunks from PDFs via NER, this script is fully deterministic:
it generates one rich text chunk per scheme class from the structured JSON.

Run from: backend/
    python scripts/build_taxonomy_index.py [--rebuild]
"""
from __future__ import annotations
import argparse
import json
import pickle
import sys
from pathlib import Path

import faiss
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.engine import faiss_store

TAXONOMY_PATH = Path(__file__).resolve().parent.parent / "data" / "taxonomy" / "mutual_fund_taxonomy_v0_3.json"
INDEX_DIR = Path(__file__).resolve().parent.parent / "faiss_indexes" / "taxonomy_showcase"

# ──────────────────────────────────────────────────────────────────────────────
# Chunk generators
# ──────────────────────────────────────────────────────────────────────────────

def _scheme_chunk(scheme: dict, section_label: str, circular: str, circular_title: str) -> str:
    """Convert one scheme class dict into a rich natural-language chunk."""
    parts = [
        f"[SCHEME CLASS] {scheme['canonical_label']} (Code: {scheme['code']})",
        f"Section: {section_label}",
        f"SEBI Category Identifier: {scheme.get('csv_category', scheme['canonical_label'])}",
        f"Investment Mandate: {scheme['investment_mandate']}",
    ]
    if scheme.get("duration_band"):
        parts.append(f"Macaulay Duration Band: {scheme['duration_band']}")
    if scheme.get("credit_quality_mandate"):
        parts.append(f"Credit Quality Mandate: {scheme['credit_quality_mandate']}")
    if scheme.get("market_cap_tier"):
        parts.append(f"Market Cap Tier: {scheme['market_cap_tier']}")
    if scheme.get("hybrid_equity_band"):
        parts.append(f"Equity Allocation Band: {scheme['hybrid_equity_band']}")
    if scheme.get("lock_in") and scheme["lock_in"] != "None":
        parts.append(f"Lock-in Requirement: {scheme['lock_in']}")
    if scheme.get("tax_benefit"):
        parts.append(f"Tax Benefit: {scheme['tax_benefit']}")
    if scheme.get("mutually_exclusive_with"):
        parts.append(f"SEBI Rule: An AMC CANNOT simultaneously offer this scheme and {scheme['mutually_exclusive_with']}.")
    if scheme.get("multiple_per_amc"):
        parts.append("Multiple Schemes Per AMC: Yes (exception to the general one-scheme-per-category rule).")
    if scheme.get("introduced_by_circular"):
        parts.append(f"Introduced By: SEBI Circular {scheme['introduced_by_circular']}")
    if scheme.get("data_status") == "ACTIVE":
        parts.append(f"Regulatory Basis: {circular} — {circular_title}")
    return "\n".join(parts)


def _legacy_chunk(scheme: dict) -> str:
    parts = [
        f"[LEGACY SCHEME CLASS] {scheme['canonical_label']} (Code: {scheme['code']})",
        f"CSV Category Label: {scheme['csv_category']}",
        f"Description: {scheme['description']}",
        f"Status: LEGACY — Pre-2017 SEBI Categorization and Rationalization Circular",
        f"Active Schemes in Data: {scheme.get('active_schemes_in_csv', 'Unknown')}",
    ]
    if scheme.get("maps_to"):
        parts.append(f"Post-Rationalization Equivalent: {scheme['maps_to']}")
    return "\n".join(parts)


def _circular_chunk(tax: dict) -> str:
    rb = tax["regulatory_basis"]
    lines = [
        f"[REGULATORY CIRCULAR] {rb['primary_circular']}",
        f"Title: {rb['primary_circular_title']}",
        f"Date: {rb['primary_circular_date']}",
        f"General Rule: {rb['general_rule']}",
        "Key Amendments:",
    ]
    for a in rb["key_amendments"]:
        lines.append(f"  - [{a['date']}] Circular {a['circular']}: {a['change']}")
    return "\n".join(lines)


def _mutual_exclusion_chunk(rules: list) -> str:
    lines = ["[MUTUAL EXCLUSION RULES — SEBI Scheme Restrictions]"]
    for r in rules:
        lines.append(f"  - {r['scheme_a']} and {r['scheme_b']}: {r['rule']} (Circular: {r['source_circular']})")
    return "\n".join(lines)


def _section_summary_chunk(section: dict, scheme_classes: list) -> str:
    labels = [s["canonical_label"] for s in scheme_classes]
    return (
        f"[SECTION SUMMARY] Section {section['section']}: {section['label']}\n"
        f"Contains {len(labels)} scheme categories: {', '.join(labels)}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Main builder
# ──────────────────────────────────────────────────────────────────────────────

def build(rebuild: bool = False):
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    faiss_path = INDEX_DIR / "index.faiss"
    pkl_path   = INDEX_DIR / "index.pkl"

    if not rebuild and faiss_path.exists() and pkl_path.exists():
        print("  ↩ Index already exists. Use --rebuild to regenerate.", flush=True)
        return

    tax = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    circular = tax["regulatory_basis"]["primary_circular"]
    circular_title = tax["regulatory_basis"]["primary_circular_title"]

    # --- Section definitions ---
    section_map = {s["section"]: s for s in tax["section_map"]}
    all_active_sections = {
        "I":   tax["scheme_classes_section_I_equity"],
        "II":  tax["scheme_classes_section_II_debt"],
        "III": tax["scheme_classes_section_III_hybrid"],
        "IV":  tax["scheme_classes_section_IV_solution_oriented"],
        "V":   tax["scheme_classes_section_V_other_schemes"],
    }

    chunks = []  # list of dicts: {text, source, code, section}

    # 1. One chunk for the main regulatory circular
    chunks.append({"text": _circular_chunk(tax), "source": "taxonomy_v0_3", "code": "CIRCULAR_PRIMARY", "section": "META"})

    # 2. One chunk for mutual exclusion rules
    chunks.append({"text": _mutual_exclusion_chunk(tax["mutual_exclusion_rules"]), "source": "taxonomy_v0_3", "code": "MUTUAL_EXCLUSIONS", "section": "META"})

    # 3. Section summary chunks
    for sec_id, schemes in all_active_sections.items():
        chunks.append({
            "text": _section_summary_chunk(section_map[sec_id], schemes),
            "source": "taxonomy_v0_3",
            "code": f"SECTION_{sec_id}_SUMMARY",
            "section": sec_id
        })

    # 4. Individual scheme class chunks
    for sec_id, schemes in all_active_sections.items():
        for scheme in schemes:
            chunks.append({
                "text": _scheme_chunk(scheme, section_map[sec_id]["label"], circular, circular_title),
                "source": "taxonomy_v0_3",
                "code": scheme["code"],
                "section": sec_id
            })

    # 5. Legacy scheme chunks
    for scheme in tax["legacy_scheme_classes"]:
        chunks.append({
            "text": _legacy_chunk(scheme),
            "source": "taxonomy_v0_3",
            "code": scheme["code"],
            "section": "LEGACY"
        })

    print(f"  Generated {len(chunks)} total chunks. Embedding...", flush=True)

    # Embed all chunks
    texts = [c["text"] for c in chunks]
    vecs  = faiss_store._embed_texts(texts)
    print(f"  Embedded. Vector shape: {vecs.shape}", flush=True)

    # Build FAISS flat IP index
    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)

    # Save
    faiss.write_index(index, str(faiss_path))
    with open(pkl_path, "wb") as f:
        pickle.dump({"children": chunks}, f)
    (INDEX_DIR / "meta.json").write_text(json.dumps({
        "slug": "taxonomy_showcase",
        "num_chunks": len(chunks),
        "taxonomy_version": tax["taxonomy_id"]
    }, indent=2))

    print(f"\n  [OK] Done. {len(chunks)} chunks indexed -> {INDEX_DIR}", flush=True)
    for sec_id, schemes in all_active_sections.items():
        print(f"    Section {sec_id}: {len(schemes)} scheme classes")
    print(f"    Legacy: {len(tax['legacy_scheme_classes'])} categories")
    print(f"    Meta chunks (circular + exclusions + summaries): {2 + len(all_active_sections)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()
    build(rebuild=args.rebuild)
