"""Verified pointer-bound FAISS retrieval adapter; opt-in replacement for unsafe readers.

Requires faiss-cpu/numpy at runtime. `search` is intentionally coupled to
VerifiedGenerationResolver (published receipt plus exact effect and byte proof).
Do not simply create this adapter and assume existing app traffic uses it:
application retrieval wiring must be separately reviewed and tested.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import math
import hashlib
import json

from .faiss_artifacts import FaissGenerationStore
from .serving27 import VerifiedGenerationResolver, ServingDenied


class VerifiedFaissRetriever:
    def __init__(self, sessions, root: str | Path):
        # No embedding model is required for read-only index load.
        self.store = FaissGenerationStore(root, embedder=None)
        self.sessions = sessions
        self._loaded: dict[str, tuple[str, str, object, list[dict]]] = {}
        self.resolver = VerifiedGenerationResolver(sessions, self.store, serving_loader=self._load)

    def _load(self, tenant: str, generation_id: str, digest: str) -> bool:
        if generation_id != digest:
            raise ServingDenied('non-content-addressed generation refused')
        docs = self.store.verify_by_digest(digest, tenant)  # full binary SHA + every ID
        faiss, _ = self.store._imports()
        directory = self.store._path(digest)
        path = directory / 'index.faiss'
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        expected_hash = manifest.get('index_hash')
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            raise ServingDenied('missing exact binary artifact hash')
        before_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if before_hash != expected_hash:
            raise ServingDenied('FAISS bytes changed before serving load')
        index = faiss.read_index(str(path))
        # The loaded index itself must match the manifest (not merely another
        # validated file that existed a moment earlier).
        if index.ntotal != len(docs) or index.d != manifest.get('dimension'):
            raise ServingDenied('loaded FAISS count/dimension differs from verified corpus')
        ids = faiss.vector_to_array(index.id_map).tolist()
        if ids != list(range(1, len(docs)+1)):
            raise ServingDenied('loaded FAISS ID map mismatch')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            raise ServingDenied('FAISS bytes changed during serving load')
        self._loaded[tenant] = (generation_id, digest, index, docs)
        return True

    def probe_activation(self, tenant: str, generation_id: str, digest: str) -> bool:
        """Used by worker before receipt; NEVER authorizes answer serving."""
        return self.resolver.probe_activation(tenant, generation_id, digest)

    def search(self, tenant: str, embedding: list[float], *, limit: int = 10,
               work_id: str | None = None, receipt_id: str | None = None) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('bounded result limit 1..100 required')
        try:
            values = [float(x) for x in embedding]
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError('valid numeric embedding required') from exc
        if not values or any(not math.isfinite(x) for x in values):
            raise ValueError('embedding must contain finite numeric dimensions')
        generation = self.resolver.resolve_for_serving(tenant, work_id=work_id, receipt_id=receipt_id)
        cur = self._loaded.get(tenant)
        if not cur or cur[:2] != (generation.generation_id, generation.digest):
            raise ServingDenied('active loaded index does not match current generation')
        _, _, index, docs = cur
        if len(values) != index.d:
            raise ServingDenied('embedding/index dimension mismatch')
        _, np = self.store._imports()
        matrix = np.asarray(values, dtype='float32').reshape(1, -1)
        if not np.all(np.isfinite(matrix)):
            raise ValueError('embedding overflowed float32')
        faiss, _ = self.store._imports()
        faiss.normalize_L2(matrix)
        scores, ids = index.search(matrix, min(limit, len(docs)))
        hits=[]
        seen=set()
        for score, id_ in zip(scores[0].tolist(), ids[0].tolist()):
            if int(id_) == -1:
                continue
            idx=int(id_)
            if idx < 1 or idx > len(docs) or idx in seen or not math.isfinite(float(score)):
                raise ServingDenied('FAISS returned out-of-range/duplicate/nonfinite hit')
            seen.add(idx)
            hits.append({'chunk_id':docs[idx-1]['chunk_id'], 'score':float(score),
                         'document':docs[idx-1]})
        # Reader state may have changed while query executed. Recheck pointer and
        # receipt eligibility before the caller can emit grounded citations.
        if self.resolver._pointer(tenant) != (generation.generation_id,generation.digest,generation.epoch):
            raise ServingDenied('pointer changed while querying')
        self.resolver._receipt(tenant,generation.generation_id,generation.digest,
                               generation.work_id,generation.receipt_id)
        # W30: The pointer/receipt can remain unchanged while a new graph
        # publication or rollback SUSPENDS serving authority. Recheck the
        # authoritative sidecar after the physical search, not only the pointer.
        authority = getattr(self.resolver, '_authority', None)
        if callable(authority):
            observed = authority(tenant)
            expected = (generation.generation_id, generation.digest, generation.epoch,
                        generation.work_id, generation.receipt_id)
            if observed != expected:
                raise ServingDenied('active receipt authority changed during FAISS search')
        else:
            # Historical Wave 2.7 contract tests may use an older resolver in
            # offline mode. Production enforcement must NOT accept that resolver.
            import os
            if os.environ.get('AMC_VERIFIED_SERVING_MODE', 'off') == 'enforce':
                raise ServingDenied('active receipt authority resolver missing')
        return hits
