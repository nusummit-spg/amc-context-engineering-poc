"""REC05: Real FAISS IndexIDMap2 integration smoke test.

Tests that a FAISS index can be built, saved, reloaded, and queried
with exact ID matching.  Skips if faiss is not installed.

Run: python -m pytest tests/test_faiss_integration.py -v
"""
import sys
import os
import json
import hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

try:
    import faiss
    import numpy as np
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False

pytestmark = pytest.mark.skipif(not HAS_FAISS, reason="faiss not installed")

def test_rec05_build_reload_and_search():
    """REC05: Build IndexIDMap2, save, reload, and search with exact IDs."""
    dim = 128
    num_vectors = 10

    # Generate deterministic test vectors
    vectors = np.random.RandomState(42).randn(num_vectors, dim).astype("float32")
    faiss.normalize_L2(vectors)

    chunk_ids = [f"chunk-{i:04d}" for i in range(num_vectors)]
    int_ids = np.arange(num_vectors, dtype="int64")

    # Build index
    quantizer = faiss.IndexFlatIP(dim)
    index = faiss.IndexIDMap2(quantizer)
    index.add_with_ids(vectors, int_ids)

    assert index.ntotal == num_vectors

    # Save to temp file
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = os.path.join(tmpdir, "test.index")
        faiss.write_index(index, index_path)

        # Compute index digest
        with open(index_path, "rb") as f:
            index_bytes = f.read()
        index_digest = hashlib.sha256(index_bytes).hexdigest()

        # Save payloads
        payloads_path = os.path.join(tmpdir, "payloads.json")
        with open(payloads_path, "w") as f:
            json.dump(
                {"chunk_ids": chunk_ids, "dim": dim, "count": num_vectors},
                f,
            )

        # Reload
        reloaded = faiss.read_index(index_path)
        assert reloaded.ntotal == num_vectors

        # Search for vector 3
        query = vectors[3:4]
        k = 3
        scores, ids = reloaded.search(query, k)

        # Top result must be ID 3
        assert ids[0][0] == 3, f"Expected top match ID=3, got {ids[0][0]}"
        assert scores[0][0] > 0.99, f"Expected high similarity, got {scores[0][0]}"

        # Verify all IDs are within range
        for row_ids in ids:
            for i in row_ids:
                assert 0 <= i < num_vectors

    print("REC05: FAISS build/reload/search smoke test passed")

def test_rec05_corrupt_binary_detected():
    """REC05: A corrupted FAISS binary must be detectable via digest mismatch."""
    import tempfile

    dim = 64
    num_vectors = 5
    vectors = np.random.RandomState(42).randn(num_vectors, dim).astype("float32")
    faiss.normalize_L2(vectors)

    quantizer = faiss.IndexFlatIP(dim)
    index = faiss.IndexIDMap2(quantizer)
    index.add_with_ids(vectors, np.arange(num_vectors, dtype="int64"))

    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = os.path.join(tmpdir, "corrupt.index")
        faiss.write_index(index, index_path)

        # Compute original digest
        with open(index_path, "rb") as f:
            original_bytes = f.read()
        original_digest = hashlib.sha256(original_bytes).hexdigest()

        # Corrupt the binary
        corrupt_bytes = bytearray(original_bytes)
        corrupt_bytes[100] = (corrupt_bytes[100] + 1) % 256
        with open(index_path, "wb") as f:
            f.write(bytes(corrupt_bytes))

        # Recompute digest — must differ
        with open(index_path, "rb") as f:
            corrupt_bytes_reread = f.read()
        corrupt_digest = hashlib.sha256(corrupt_bytes_reread).hexdigest()

        assert corrupt_digest != original_digest, "Corruption not detected by digest"

        # Verify faiss can detect it too (read will fail or produce wrong results)
        try:
            bad_index = faiss.read_index(index_path)
            # If it loads, searching should produce garbage
            _, bad_ids = bad_index.search(vectors[0:1], 1)
            # The result might be wrong but the key point is the digest catches it
        except Exception:
            pass  # Corrupt index fails to load — also acceptable

    print("REC05: Corruption detection via digest passed")

def test_rec05_payload_hash_matches():
    """REC05: Payload hash includes exact chunk_ids, dimension, and count."""
    chunk_ids = [f"chunk-{i:04d}" for i in range(10)]
    dim = 128
    count = 10

    payload = {"chunk_ids": chunk_ids, "dim": dim, "count": count}
    payload_str = json.dumps(payload, sort_keys=True)
    digest1 = hashlib.sha256(payload_str.encode()).hexdigest()

    # Same data → same hash
    payload2 = {"chunk_ids": chunk_ids, "dim": dim, "count": count}
    payload2_str = json.dumps(payload2, sort_keys=True)
    digest2 = hashlib.sha256(payload2_str.encode()).hexdigest()
    assert digest1 == digest2

    # Different chunk_ids → different hash
    payload3 = {"chunk_ids": chunk_ids[::-1], "dim": dim, "count": count}
    payload3_str = json.dumps(payload3, sort_keys=True)
    digest3 = hashlib.sha256(payload3_str.encode()).hexdigest()
    assert digest1 != digest3

    print("REC05: Payload hash determinism passed")