# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
build_pdf_faiss_index.py
========================
Builds a FAISS index directly from the raw PDF source documents.
Replaces the lossy JSON-based taxonomy FAISS index.
"""
from __future__ import annotations
import sys
from pathlib import Path
import faiss
try:
    import pymupdf as fitz  # PyMuPDF
except ImportError:
    import fitz


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.engine import faiss_store as fs

PDF_DIR = Path(__file__).resolve().parent.parent.parent / "Docs" / "selected_source_documents"
if not PDF_DIR.exists():
    PDF_DIR = Path(__file__).resolve().parent.parent.parent / "selected_source_documents"
INDEX_DIR = Path(__file__).resolve().parent.parent / "faiss_indexes" / "taxonomy_showcase"

def chunk_text(text: str, chunk_size: int = 1500, overlap: int = 300) -> list[str]:
    chunks = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks

def build_index():
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    
    all_chunks = []
    pdf_files = list(PDF_DIR.glob("*.pdf"))
    print(f"Found {len(pdf_files)} PDFs in {PDF_DIR}")
    
    for pdf_path in pdf_files:
        print(f"Parsing {pdf_path.name}...")
        try:
            doc = fitz.open(pdf_path)
            full_text = ""
            for page in doc:
                full_text += page.get_text() + "\n"
            
            # Create chunks
            chunks = chunk_text(full_text)
            for c in chunks:
                if c.strip():
                    all_chunks.append(f"[SOURCE: {pdf_path.name}]\n{c.strip()}")
        except Exception as e:
            print(f"Failed to parse {pdf_path.name}: {e}")
            
    print(f"Total chunks created: {len(all_chunks)}")
    
    # Embed and add to FAISS
    dim = 384
    index = faiss.IndexFlatIP(dim)
    
    print("Computing embeddings...")
    batch_size = 128
    
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i+batch_size]
        vecs = fs._embed_texts(batch)
        # Normalize for IP -> Cosine similarity
        faiss.normalize_L2(vecs)
        index.add(vecs)
        print(f"  Embedded {min(i+batch_size, len(all_chunks))}/{len(all_chunks)}")
        
    # Save
    faiss.write_index(index, str(INDEX_DIR / "index.faiss"))
    with open(INDEX_DIR / "index.pkl", "wb") as f:
        pickle.dump({"children": all_chunks}, f)
        
    print(f"  [OK] Saved to {INDEX_DIR}")

if __name__ == "__main__":
    build_index()
