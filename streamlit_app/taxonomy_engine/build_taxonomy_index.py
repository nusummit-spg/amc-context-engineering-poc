"""
build_taxonomy_index.py
=========================
Builds the `taxonomy_showcase` FAISS index directly from the raw regulatory
source PDFs (config.TAXONOMY_SOURCE_DOCS_DIR).

Deliberately reuses faiss_store.py's existing sentence-boundary-aware
parent/child chunker (extract_pdf_text_full + build_parent_child_chunks) and
writes the exact same index.faiss/index.pkl/meta.json shape every other
FAISS index in this repo uses (see build_user_upload_index for the closest
existing pattern this mirrors) — NOT the flat fixed-size-chunk format the
original showcase script used, which BrochureFAISSStore can't load.

Run from streamlit_app/:
    python -m taxonomy_engine.build_taxonomy_index
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Dict, List

import faiss

import config
import faiss_store


def build_index() -> str:
    slug = config.TAXONOMY_FAISS_SLUG
    index_dir = config.FAISS_DIR / slug
    index_dir.mkdir(parents=True, exist_ok=True)

    pdf_paths = sorted(config.TAXONOMY_SOURCE_DOCS_DIR.glob("*.pdf"))
    print(f"Found {len(pdf_paths)} PDFs in {config.TAXONOMY_SOURCE_DOCS_DIR}", flush=True)

    all_parents: Dict[str, dict] = {}
    all_children: List[dict] = []
    parent_offset = 0
    child_offset = 0

    for pdf_path in pdf_paths:
        product_name = pdf_path.stem
        print(f"  Extracting: {product_name}", flush=True)
        pages_data = faiss_store.extract_pdf_text_full(str(pdf_path), verbose=False, use_vision=True)
        parents, children = faiss_store.build_parent_child_chunks(pages_data, product_name)

        id_map: Dict[str, str] = {}
        for p in parents:
            new_pid = f"P{parent_offset:05d}"
            id_map[p["parent_id"]] = new_pid
            p["parent_id"] = new_pid
            all_parents[new_pid] = p
            parent_offset += 1
        for c in children:
            c["child_id"] = f"C{child_offset:05d}"
            c["parent_id"] = id_map[c["parent_id"]]
            all_children.append(c)
            child_offset += 1

        print(f"    {len(parents)} parents, {len(children)} children", flush=True)

    if not all_children:
        raise RuntimeError("No chunks produced — check TAXONOMY_SOURCE_DOCS_DIR has PDFs in it.")

    print(f"Embedding {len(all_children)} total child chunks...", flush=True)
    vectors = faiss_store._embed_texts([c["text"] for c in all_children])
    dim = vectors.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(vectors)

    faiss.write_index(index, str(index_dir / "index.faiss"))
    with open(index_dir / "index.pkl", "wb") as f:
        pickle.dump({"children": all_children, "parents": all_parents}, f)

    meta = {
        "slug": slug,
        "product_name": "MF Taxonomy Sources",
        "source_file": ", ".join(p.name for p in pdf_paths),
        "num_pdfs": len(pdf_paths),
        "num_parents": len(all_parents),
        "num_children": len(all_children),
        "embed_dim": dim,
        "model": "all-MiniLM-L6-v2",
    }
    (index_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    faiss_store._store_cache.pop(slug, None)
    print(f"  [OK] Saved -> {index_dir}", flush=True)
    print(f"  {len(all_parents)} parents, {len(all_children)} children from {len(pdf_paths)} PDFs", flush=True)
    return slug


if __name__ == "__main__":
    build_index()
