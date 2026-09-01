# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Generate canonical mapping manifest from legacy amc_master FAISS store.

Extracts all 18 baseline source documents and parent/child chunk records from
backend/app/engine/faiss_indexes/amc_master/index.pkl, computes deterministic
canonical SHA-256 IDs, and writes:
  - backend/data/migrations/legacy_id_map.csv
  - backend/data/migrations/legacy_manifest.json
"""
from __future__ import annotations

import csv
import json
import os
import pickle
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from app.contracts.identity import (
    compute_content_sha256,
    generate_chunk_id,
    generate_document_id,
    generate_document_version_id,
    generate_source_id,
)


def main():
    root = Path(__file__).resolve().parent.parent
    pkl_path = root / "app" / "engine" / "faiss_indexes" / "amc_master" / "index.pkl"
    if not pkl_path.exists():
        raise FileNotFoundError(f"Legacy FAISS pickle not found: {pkl_path}")

    with open(pkl_path, "rb") as f:
        data = pickle.load(f)

    parents = data.get("parents", {})
    children = data.get("children", {})
    source_files = data.get("source_files", [])

    print(f"Loaded legacy FAISS data: {len(parents)} parents, {len(children)} children, {len(source_files)} source files")

    migrations_dir = root / "data" / "migrations"
    migrations_dir.mkdir(parents=True, exist_ok=True)

    csv_path = migrations_dir / "legacy_id_map.csv"
    json_path = migrations_dir / "legacy_manifest.json"

    # Map sources
    doc_map = {}
    distinct_sources = sorted(list({p.get("source") for p in parents.values() if p.get("source")}))
    if not distinct_sources and source_files:
        distinct_sources = sorted(source_files)

    for src_name in distinct_sources:
        src_id = generate_source_id(src_name, namespace="amc_master_legacy")
        doc_id = generate_document_id(src_id)
        # Content hash from concatenated parent texts for this document in legacy store
        src_parent_texts = "".join(
            p.get("text", "") for p in sorted(
                [p for p in parents.values() if p.get("source") == src_name],
                key=lambda x: x.get("parent_id", "")
            )
        )
        content_sha = compute_content_sha256(src_parent_texts.encode("utf-8"))
        doc_ver_id = generate_document_version_id(doc_id, content_sha)

        doc_map[src_name] = {
            "source_filename": src_name,
            "source_id": src_id,
            "document_id": doc_id,
            "content_sha256": content_sha,
            "document_version_id": doc_ver_id,
        }

    # Map parent chunks
    chunk_records = []
    for pid, p in sorted(parents.items()):
        src_name = p.get("source", "unknown")
        doc_info = doc_map.get(src_name, {})
        doc_id = doc_info.get("document_id", "")
        doc_ver_id = doc_info.get("document_version_id", "")
        source_id = doc_info.get("source_id", "")
        page = p.get("page", 1)
        text = p.get("text", "")
        chunk_id = generate_chunk_id(doc_ver_id, f"page_{page}", text) if doc_ver_id else ""

        chunk_records.append({
            "legacy_parent_id": pid,
            "source_filename": src_name,
            "source_id": source_id,
            "document_id": doc_id,
            "document_version_id": doc_ver_id,
            "canonical_chunk_id": chunk_id,
            "page": page,
            "text_length": len(text),
            "text_fingerprint": compute_content_sha256(text.encode("utf-8"))[:16],
        })

    # Write CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "legacy_parent_id", "source_filename", "source_id", "document_id",
            "document_version_id", "canonical_chunk_id", "page", "text_length", "text_fingerprint"
        ])
        writer.writeheader()
        writer.writerows(chunk_records)

    # Write JSON manifest
    manifest_data = {
        "schema_version": "1.0",
        "legacy_corpus": "amc_master_legacy",
        "total_sources": len(doc_map),
        "total_parent_chunks": len(chunk_records),
        "sources": doc_map,
        "parent_chunks_sample": chunk_records[:10],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    print(f"Generated legacy mapping manifest: {csv_path} ({len(chunk_records)} rows), {json_path}")


if __name__ == "__main__":
    main()
