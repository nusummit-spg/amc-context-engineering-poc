"""Operational and maintenance script for ingest csv."""

import csv
import json
import os
from pathlib import Path
import faiss
from fastembed import TextEmbedding
import numpy as np

# 1. Paths and Configuration
CSV_PATH = "data/source_docs/mutual_fund_data.csv"
VECTOR_STORE_DIR = "data/vector_store/v2_baseline_20260814"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DIMENSION = 384

index_path = os.path.join(VECTOR_STORE_DIR, "index.faiss")
payload_path = os.path.join(VECTOR_STORE_DIR, "payloads.json")

# 2. Read and serialize the CSV into semantic text chunks
print(f"Reading CSV: {CSV_PATH}")
chunks = []
with open(CSV_PATH, mode="r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row_idx, row in enumerate(reader, start=1):
        # Build key-value semantic text
        pairs = [f"{k.strip()}: {v.strip()}" for k, v in row.items() if v]
        row_text = " | ".join(pairs)
        
        chunks.append({
            "text": row_text,
            "row_idx": row_idx,
            "metadata": dict(row)
        })

print(f"Generated {len(chunks)} chunks from CSV.")

# 3. Load existing FAISS index and payloads
if os.path.exists(index_path) and os.path.exists(payload_path):
    index = faiss.read_index(index_path)
    with open(payload_path, "r", encoding="utf-8") as f:
        payloads = {int(k): v for k, v in json.load(f).items()}
    next_id = (max(payloads.keys()) + 1) if payloads else 0
    print(f"Loaded existing index with {index.ntotal} vectors.")
else:
    # Create new flat inner-product index with ID map
    index = faiss.IndexIDMap2(faiss.IndexFlatIP(DIMENSION))
    payloads = {}
    next_id = 0
    print("Initialized empty FAISS index.")

# 4. Generate Embeddings using fastembed
print(f"Generating embeddings using {EMBEDDING_MODEL}...")
embedder = TextEmbedding(model_name=EMBEDDING_MODEL)
texts = [c["text"] for c in chunks]
embeddings = list(embedder.embed(texts))

# Convert to float32 and L2-normalize for Cosine Similarity
matrix = np.asarray(embeddings, dtype="float32")
faiss.normalize_L2(matrix)

# 5. Add vectors and payloads to FAISS
new_ids = np.arange(next_id, next_id + len(chunks), dtype="int64")
index.add_with_ids(matrix, new_ids)

source_file = Path(CSV_PATH).name
for i, chunk in enumerate(chunks):
    assigned_id = int(new_ids[i])
    payloads[assigned_id] = {
        "chunk_id": f"csv_{source_file}_{chunk['row_idx']}",
        "document_id": source_file,
        "document_title": source_file,
        "source_filename": source_file,
        "page_start": chunk["row_idx"],
        "page_end": chunk["row_idx"],
        "section_locator": f"row.{chunk['row_idx']}",
        "corpus_version": "v2_baseline_20260814",
        "legacy_parent_id": f"p_csv_{chunk['row_idx']}",
        "text": chunk["text"],
        "order": assigned_id,
        "taxonomy_paths": [],
        "entity_ids": []
    }

# 6. Save back to disk
print(f"Saving updated FAISS index ({index.ntotal} total vectors)...")
os.makedirs(VECTOR_STORE_DIR, exist_ok=True)
faiss.write_index(index, index_path)

with open(payload_path, "w", encoding="utf-8") as f:
    json.dump({str(k): v for k, v in payloads.items()}, f, indent=2)

print("✅ Ingestion complete!")