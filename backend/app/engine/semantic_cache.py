# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import faiss
import numpy as np
import time
from typing import Dict, Optional, Tuple

class SemanticCache:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2", threshold: float = 0.95):
        print("  [cache] Initializing Semantic Cache...")
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)
        
        # We use a simple inner product index (cosine similarity if normalized)
        # embedding dimension is 384 for all-MiniLM-L6-v2, or 768 for paraphrase-multilingual-MiniLM-L12-v2
        # Let's dynamically get it from the model
        dummy = self.model.encode(["test"])
        self.dim = dummy.shape[1]
        
        self.index = faiss.IndexFlatIP(self.dim)
        self.threshold = threshold
        self.storage: Dict[int, dict] = {} # maps faiss id -> payload (answer, telemetry)
        self.next_id = 0

    def _normalize(self, vec: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vec, axis=1, keepdims=True)
        return vec / (norm + 1e-9)

    def check(self, query: str) -> Tuple[Optional[dict], float]:
        """Returns (cached_payload, latency_ms) if a semantic hit is found, else (None, latency_ms)"""
        t0 = time.perf_counter()
        if self.next_id == 0:
            return None, (time.perf_counter() - t0) * 1000.0

        query_emb = self.model.encode([query])
        query_emb = self._normalize(query_emb)
        
        distances, indices = self.index.search(query_emb, 1)
        best_idx = int(indices[0][0])
        best_score = float(distances[0][0])

        latency = (time.perf_counter() - t0) * 1000.0

        if best_idx != -1 and best_score >= self.threshold:
            print(f"  [cache] HIT! Score={best_score:.3f} >= {self.threshold}")
            return self.storage[best_idx], latency
            
        print(f"  [cache] MISS. Best score={best_score:.3f} < {self.threshold}")
        return None, latency

    def clear(self):
        """Clears the semantic cache index and storage."""
        self.index = faiss.IndexFlatIP(self.dim)
        self.storage.clear()
        self.next_id = 0
        print("  [cache] Cleared semantic cache.")

    def warm_cache_patterns(self, precomputed_items: list[tuple[str, dict]]):
        """Pre-populates semantic cache with precomputed archetypes/answers."""
        for query, payload in precomputed_items:
            self.store(query, payload)
        print(f"  [cache] Pre-warmed semantic cache with {len(precomputed_items)} items.")

    def store(self, query: str, payload: dict):
        """Stores the response in the cache"""
        query_emb = self.model.encode([query])
        query_emb = self._normalize(query_emb)
        
        self.index.add(query_emb)
        self.storage[self.next_id] = payload
        self.next_id += 1
        print(f"  [cache] Stored query in cache (ID={self.next_id - 1}).")

# Global singleton so it persists across stream/api calls in the same process
_global_cache = None

def get_cache() -> SemanticCache:
    global _global_cache
    if _global_cache is None:
        _global_cache = SemanticCache(model_name="paraphrase-multilingual-MiniLM-L12-v2", threshold=0.88)
    return _global_cache
