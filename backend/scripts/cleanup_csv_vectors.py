#!/usr/bin/env python
"""Remove old CSV chunk vectors from FAISS index."""

import json
import faiss
import numpy as np
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

VECTOR_STORE_DIR = Path("data/vector_store/v2_baseline_20260814")
if not VECTOR_STORE_DIR.exists() and Path("backend/data/vector_store/v2_baseline_20260814").exists():
    VECTOR_STORE_DIR = Path("backend/data/vector_store/v2_baseline_20260814")

INDEX_PATH = VECTOR_STORE_DIR / "index.faiss"
PAYLOAD_PATH = VECTOR_STORE_DIR / "payloads.json"

def cleanup_csv_vectors():
    """Remove all CSV chunk vectors from index."""
    
    # Load existing data
    print("Loading vector store...", flush=True)
    index = faiss.read_index(str(INDEX_PATH))
    
    with open(PAYLOAD_PATH, "r", encoding="utf-8") as f:
        payloads = {int(k): v for k, v in json.load(f).items()}
    
    print(f"Current state: {index.ntotal} vectors, {len(payloads)} payloads", flush=True)
    
    # Identify CSV chunk entries to remove
    csv_vector_ids = set()
    for vector_id, payload in payloads.items():
        doc_id = payload.get("document_id", "")
        chunk_id = payload.get("chunk_id", "")
        src = payload.get("source_filename", "")
        if (
            "mutual_fund_data_chunk" in doc_id
            or "mutual_fund_data.csv" in doc_id
            or "mutual_fund_data_chunk" in chunk_id
            or "mutual_fund_data" in chunk_id
            or "mutual_fund_data" in src
        ):
            csv_vector_ids.add(vector_id)
    
    print(f"\nFound {len(csv_vector_ids)} CSV chunk vectors to remove", flush=True)
    
    if len(csv_vector_ids) == 0:
        print("No CSV vectors found. Nothing to clean.", flush=True)
        return
    
    # Create new index with non-CSV vectors
    dimension = index.d
    new_index = faiss.IndexIDMap2(faiss.IndexFlatIP(dimension))
    new_payloads = {}
    
    # Get all actual existing vector IDs from the index
    raw_ids = faiss.vector_to_array(index.id_map)
    all_unique_ids = list(dict.fromkeys(raw_ids))
    
    # Remove CSV IDs
    keep_ids = [int(vid) for vid in all_unique_ids if int(vid) not in csv_vector_ids]
    
    print(f"Keeping {len(keep_ids)} non-CSV vectors", flush=True)
    
    # Reconstruct vectors for kept IDs
    if len(keep_ids) > 0:
        vectors = np.zeros((len(keep_ids), dimension), dtype='float32')
        for i, vid in enumerate(keep_ids):
            vectors[i] = index.reconstruct(int(vid))
        
        # Add to new index
        keep_ids_array = np.array(keep_ids, dtype='int64')
        new_index.add_with_ids(vectors, keep_ids_array)
        
        # Copy payloads
        for vid in keep_ids:
            if int(vid) in payloads:
                new_payloads[int(vid)] = payloads[int(vid)]
    
    # Save cleaned index
    print(f"\nSaving cleaned vector store...", flush=True)
    faiss.write_index(new_index, str(INDEX_PATH))
    
    with open(PAYLOAD_PATH, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in new_payloads.items()}, f, indent=2)
    
    print(f"[OK] Cleanup complete!", flush=True)
    print(f"  Removed: {len(csv_vector_ids)} CSV vectors", flush=True)
    print(f"  Remaining: {new_index.ntotal} vectors", flush=True)
    print(f"  New payload count: {len(new_payloads)}", flush=True)

if __name__ == "__main__":
    cleanup_csv_vectors()
