# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
ingest_selected_documents.py
=============================
Batch ingestion script for all documents in `Docs/selected_source_documents`.
Extracts PDFs and CSVs, builds parent-child chunks, extracts entities and
relational graph triplets, updates the Graph store, and builds FAISS indexes.
"""
import os
import sys
import json
import pickle
import time
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple

import faiss
import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure backend root is in sys.path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

# Load .env
_env_path = BACKEND_ROOT / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

from app.engine import config
from app.engine import document_extractors
from app.engine import faiss_store
from app.engine import graph_store
from app.engine import ner_pipeline
from app.engine import pii_scrub

DOCS_DIR = PROJECT_ROOT / "Docs" / "selected_source_documents"

FAISS_TARGET_DIRS = [
    BACKEND_ROOT / "app" / "engine" / "faiss_indexes" / "amc_master",
    BACKEND_ROOT / "faiss_indexes" / "taxonomy_showcase",
    PROJECT_ROOT / "streamlit_app" / "faiss_indexes" / "amc_master",
]

GRAPH_DUMP_PATHS = [
    PROJECT_ROOT / "amc_master_full_dump.json",
    BACKEND_ROOT / "graph_dump.json",
]


def ingest_all_documents():
    print(f"================================================================")
    print(f" Starting Ingestion of Selected Source Documents")
    print(f" Source Directory: {DOCS_DIR}")
    print(f"================================================================")

    if not DOCS_DIR.exists():
        raise FileNotFoundError(f"Source documents directory not found: {DOCS_DIR}")

    files = sorted([f for f in DOCS_DIR.iterdir() if f.is_file() and f.suffix.lower() in (".pdf", ".csv", ".xlsx", ".docx", ".txt")])
    print(f"Found {len(files)} files to ingest:")
    for i, f in enumerate(files, 1):
        print(f"  {i}. {f.name} ({f.stat().st_size / 1024:.1f} KB)")

    all_parents: Dict[str, dict] = {}
    all_children: List[dict] = []
    parent_offset = 0
    child_offset = 0

    all_entities: List[dict] = []
    all_relations: List[dict] = []

    for file_path in files:
        print(f"\nProcessing [{file_path.name}]...")
        t0 = time.perf_counter()
        product_name = file_path.stem

        try:
            pages_data = document_extractors.extract_any(str(file_path), use_gemini=False)
        except Exception as exc:
            print(f"  [ERROR] Extraction failed for {file_path.name}: {exc}")
            continue

        if getattr(config, "PII_SCRUB_ENABLED", False):
            pages_data = pii_scrub.scrub_pages(pages_data)

        # Build parent-child chunks
        parents, children = faiss_store.build_parent_child_chunks(pages_data, product_name)
        print(f"  Extracted {len(pages_data)} pages -> {len(parents)} parents, {len(children)} children in {time.perf_counter() - t0:.2f}s")

        # Map IDs into sequential master ID space
        id_map = {}
        for p in parents:
            new_pid = f"P{parent_offset:05d}"
            id_map[p["parent_id"]] = new_pid
            p["parent_id"] = new_pid
            all_parents[new_pid] = p
            parent_offset += 1

        for c in children:
            c["child_id"] = f"C{child_offset:05d}"
            c["parent_id"] = id_map.get(c["parent_id"], c["parent_id"])
            all_children.append(c)
            child_offset += 1

        # Run NER & Relational Extraction on representative chunks
        parents_map = {p["parent_id"]: p for p in parents}
        parents_sample = dict(list(parents_map.items())[:2])
        try:
            ner_out = ner_pipeline.run_full_ner_for_chunk_set(children[:8], parents_sample)
            ents = ner_out.get("entities", [])
            rels = ner_out.get("relations", [])
            print(f"  [NER] Found {len(ents)} entities, {len(rels)} relations")
            all_entities.extend(ents)
            all_relations.extend(rels)

            # Upsert into graph store
            graph_store.upsert_entities(ents, product_name, file_path.name)
            graph_store.upsert_relations(rels, product_name, file_path.name)
        except Exception as exc:
            print(f"  [NER NOTICE] NER pipeline notice for {file_path.name}: {exc}")

    print(f"\n================================================================")
    print(f" Total Ingested Corpus Statistics:")
    print(f" Total Documents : {len(files)}")
    print(f" Total Parents   : {len(all_parents)}")
    print(f" Total Children  : {len(all_children)}")
    print(f" Total Entities  : {len(all_entities)}")
    print(f" Total Relations : {len(all_relations)}")
    print(f"================================================================")

    # ── Update and export In-Memory Graph Dumps ───────────────────────────────
    print("\nUpdating In-Memory Graph Knowledge Bases...")
    existing_dump = graph_store._load_in_memory_dump()
    existing_nodes = {n.get("name", n.get("properties", {}).get("name", "")): n for n in existing_dump.get("nodes", [])}
    existing_edges = {(e["s"], e["rel"], e["o"]): e for e in existing_dump.get("edges", [])}

    for ent in all_entities:
        name = ent.get("name", ent.get("text", ""))
        label = ent.get("label", "Entity")
        if name and name not in existing_nodes:
            existing_nodes[name] = {
                "name": name,
                "label": label,
                "properties": {"name": name, "label": label, "source": ent.get("source", "")}
            }

    for rel in all_relations:
        s = rel.get("s", rel.get("source", ""))
        r = rel.get("rel", rel.get("type", "RELATED_TO"))
        o = rel.get("o", rel.get("target", ""))
        conf = float(rel.get("conf", 1.0))
        s_prod = rel.get("s_product", "")
        if s and r and o:
            key = (s, r, o)
            existing_edges[key] = {
                "s": s, "rel": r, "o": o, "conf": conf, "s_product": s_prod
            }

    merged_graph_dump = {
        "nodes": list(existing_nodes.values()),
        "edges": list(existing_edges.values())
    }

    for dump_path in GRAPH_DUMP_PATHS:
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        dump_path.write_text(json.dumps(merged_graph_dump, indent=2), encoding="utf-8")
        print(f"  [OK] Saved Graph Dump ({len(merged_graph_dump['nodes'])} nodes, {len(merged_graph_dump['edges'])} edges) -> {dump_path}")

    # ── Compute Embeddings & Build FAISS Index ────────────────────────────────
    print("\nComputing embeddings with BAAI/bge-small-en-v1.5...")
    texts = [c["text"] for c in all_children]
    batch_size = 128
    all_vecs = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        vecs = faiss_store._embed_texts(batch)
        all_vecs.append(vecs)
        if (i + batch_size) % 256 == 0 or (i + batch_size) >= len(texts):
            print(f"  Embedded {min(i + batch_size, len(texts))}/{len(texts)} chunks")

    embeddings_matrix = np.vstack(all_vecs)
    dim = embeddings_matrix.shape[1]

    index = faiss.IndexFlatIP(dim)
    index.add(embeddings_matrix)
    print(f"Created FAISS IndexFlatIP with {index.ntotal} vectors @ dim={dim}")

    # ── Write to all target index directories ─────────────────────────────────
    payload = {
        "children": all_children,
        "parents": all_parents,
    }
    meta = {
        "slug": "amc_master",
        "num_parents": len(all_parents),
        "num_children": len(all_children),
        "embedding_dim": dim,
        "model": "BAAI/bge-small-en-v1.5",
        "documents": [f.name for f in files],
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    for target_dir in FAISS_TARGET_DIRS:
        target_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(target_dir / "index.faiss"))
        with open(target_dir / "index.pkl", "wb") as f:
            pickle.dump(payload, f)
        (target_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(f"  [OK] Successfully synchronized index -> {target_dir}")

    print("\n================================================================")
    print(" Ingestion Completed Successfully!")
    print("================================================================")


if __name__ == "__main__":
    ingest_all_documents()
