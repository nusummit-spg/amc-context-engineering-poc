"""Optional real immutable FAISS generation builder.

Requires ``pip install faiss-cpu numpy`` and an embedder with synchronous
``embed(list[str]) -> list[list[float]]`` (AMC VectorStore supports this).

The generated files are never edited after atomic directory rename. This class
is a drop-in artifact backend for PublicationWorker and verifies the actual
FAISS IDs/index and snapshot hash prior to switching the active DB pointer.

IMPORTANT: Legacy serving readers must be updated to resolve the current
``publication_pointer_v2``. Building these files alone does not activate them
in a running VectorStore instance.
"""
import json
import os
import shutil
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

from .artifacts import ImmutableSnapshotStore
from .types import Generation, VerificationFailed, canonical_bytes, sha256_json


class FaissGenerationStore(ImmutableSnapshotStore):
    def __init__(self, root: str | Path, embedder: Any):
        super().__init__(root)
        self.embedder = embedder

    @staticmethod
    def _imports():
        try:
            import faiss
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("faiss-cpu and numpy must be installed to build verified FAISS generations") from exc
        return faiss, np

    def stage(self, tenant: str, docs: list[dict]) -> Generation:
        faiss, np = self._imports()
        ordered = self._canonical_documents(tenant, docs)
        identity = {"tenant": tenant, "documents": ordered}
        digest = sha256_json(identity)
        gen = Generation(digest, digest, len(ordered))
        dest = self._path(digest)
        if dest.exists():
            self.verify(gen, tenant)
            return gen
        dest.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(mkdtemp(prefix="faiss-stage-", dir=dest.parent))
        try:
            # No silent partial builds: embeddings for every input row required.
            vectors = self.embedder.embed([doc["text"] for doc in ordered]) if ordered else []
            if len(vectors) != len(ordered):
                raise VerificationFailed("embedder returned incorrect vector count")
            dimension = len(vectors[0]) if vectors else int(getattr(self.embedder, "_dim", 0))
            if dimension <= 0:
                raise VerificationFailed("embedding dimension unavailable")
            if any(len(v) != dimension for v in vectors):
                raise VerificationFailed("mixed embedding dimensions")
            idx = faiss.IndexIDMap2(faiss.IndexFlatIP(dimension))
            if ordered:
                matrix = np.asarray(vectors, dtype="float32")
                if not np.all(np.isfinite(matrix)):
                    raise VerificationFailed("non-finite vector in generated index")
                faiss.normalize_L2(matrix)
                ids = np.arange(1, len(ordered) + 1, dtype="int64")
                idx.add_with_ids(matrix, ids)
            index_path = stage / "index.faiss"
            faiss.write_index(idx, str(index_path))
            payloads = {str(i): doc for i, doc in enumerate(ordered, start=1)}
            (stage / "payloads.json").write_bytes(canonical_bytes(payloads))
            (stage / "snapshot.json").write_bytes(canonical_bytes(identity))
            # Index checksum validates physical binary, not merely JSON metadata.
            import hashlib
            binary_hash = hashlib.sha256(index_path.read_bytes()).hexdigest()
            manifest = {"generation_id": digest, "digest": digest, "count": len(ordered),
                        "tenant": tenant, "dimension": dimension, "index_hash": binary_hash,
                        "payload_hash": sha256_json(payloads), "format": "faiss-idmap2-ip-v1"}
            (stage / "manifest.json").write_bytes(canonical_bytes(manifest))
            for f in stage.iterdir():
                with f.open("rb") as fh:
                    os.fsync(fh.fileno())
            try:
                os.rename(stage, dest)
            except FileExistsError:
                # Another worker has already published content-addressed bytes.
                self.verify(gen, tenant)
                return gen
            fd = os.open(dest.parent, os.O_RDONLY)
            try: os.fsync(fd)
            finally: os.close(fd)
            self.verify(gen, tenant)
            return gen
        finally:
            if stage.exists(): shutil.rmtree(stage)

    def verify(self, generation: Generation, tenant: str) -> list[dict]:
        faiss, np = self._imports()
        import hashlib
        path = self._path(generation.digest)
        try:
            manifest = json.loads((path / "manifest.json").read_bytes())
            snapshot = json.loads((path / "snapshot.json").read_bytes())
            payloads = json.loads((path / "payloads.json").read_bytes())
            binary = (path / "index.faiss").read_bytes()
            index = faiss.read_index(str(path / "index.faiss"))
        except (OSError, ValueError, RuntimeError) as exc:
            raise VerificationFailed("FAISS generation files are not readable") from exc
        if (manifest.get("format") != "faiss-idmap2-ip-v1" or
            manifest.get("generation_id") != generation.generation_id or
            manifest.get("digest") != generation.digest or
            manifest.get("tenant") != tenant or
            manifest.get("count") != generation.count or
            snapshot.get("tenant") != tenant or
            sha256_json(snapshot) != generation.digest or
            sha256_json(payloads) != manifest.get("payload_hash") or
            hashlib.sha256(binary).hexdigest() != manifest.get("index_hash") or
            index.ntotal != generation.count or index.d != manifest.get("dimension") or
            len(payloads) != generation.count):
            raise VerificationFailed("FAISS generation exact checksum/count/dimension failed")
        for i, doc in enumerate(snapshot["documents"], start=1):
            if payloads.get(str(i)) != doc:
                raise VerificationFailed("FAISS payload ID map mismatch")
        # Check every physical FAISS ID, not similarity search candidates.
        ids = faiss.vector_to_array(index.id_map).tolist()
        if ids != list(range(1, generation.count + 1)):
            raise VerificationFailed("FAISS binary contains unexpected IDs")
        return snapshot["documents"]
