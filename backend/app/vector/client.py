"""FAISS vector store — in-process index persisted to disk (EBS on EC2).

Replaces the Qdrant server. Embeddings run locally via fastembed (no API key).
Cosine similarity = inner product over L2-normalized vectors (IndexFlatIP wrapped
in IndexIDMap2). Taxonomy/entity scoping is a Python post-filter over payloads.

Persistence: index -> {faiss_dir}/index.faiss, payloads -> {faiss_dir}/payloads.json.
Loaded at startup (ensure_collection) and rewritten on each index_chunks() call.
Because FAISS is in-process, ingestion must run where the index lives — for the
demo that's inside the API (via the ingest queue), so the live index updates
directly and is persisted for the next start.
"""
import asyncio
import json
import logging
import os
from typing import Optional

import faiss
import numpy as np
from fastembed import TextEmbedding

from app.config import get_settings
from app.schemas.documents import Chunk

logger = logging.getLogger("vector")


class VectorStore:
    def __init__(self) -> None:
        settings = get_settings()
        self._dim = settings.embedding_dim
        self._embedder = TextEmbedding(model_name=settings.embedding_model)
        self._dir = settings.faiss_dir
        self._index_path = os.path.join(self._dir, "index.faiss")
        self._payload_path = os.path.join(self._dir, "payloads.json")
        self._index: Optional[faiss.Index] = None
        self._payloads: dict[int, dict] = {}   # faiss id -> chunk payload
        self._next_id = 0
        self._lock = asyncio.Lock()

    # ---------- setup / persistence ----------

    def _new_index(self) -> faiss.Index:
        return faiss.IndexIDMap2(faiss.IndexFlatIP(self._dim))

    def ensure_collection(self) -> None:
        os.makedirs(self._dir, exist_ok=True)
        if os.path.exists(self._index_path) and os.path.exists(self._payload_path):
            self._index = faiss.read_index(self._index_path)
            with open(self._payload_path, "r", encoding="utf-8") as f:
                self._payloads = {int(k): v for k, v in json.load(f).items()}
            self._next_id = (max(self._payloads) + 1) if self._payloads else 0
            logger.info("Loaded FAISS index (%d vectors) from %s", self._index.ntotal, self._dir)
        else:
            self._index = self._new_index()
            self._payloads = {}
            self._next_id = 0
            logger.info("Initialized empty FAISS index at %s", self._dir)

    def _persist(self) -> None:
        os.makedirs(self._dir, exist_ok=True)
        faiss.write_index(self._index, self._index_path)
        with open(self._payload_path, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in self._payloads.items()}, f)

    def ping(self) -> bool:
        return self._index is not None

    def count(self) -> int:
        return self._index.ntotal if self._index is not None else 0

    # ---------- embedding ----------

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._embedder.embed(texts)]

    async def embed_async(self, texts: list[str]) -> list[list[float]]:
        # fastembed is CPU-bound / sync; run off the event loop.
        return await asyncio.to_thread(self.embed, texts)

    def _matrix(self, vectors: list[list[float]]) -> np.ndarray:
        m = np.asarray(vectors, dtype="float32")
        faiss.normalize_L2(m)   # cosine via inner product
        return m

    # ---------- indexing (WS2 batch embedding pipeline) ----------

    async def index_chunks(self, chunks: list[Chunk], document_meta: dict) -> int:
        if not chunks:
            return 0
        if self._index is None:
            self.ensure_collection()
        vectors = await self.embed_async([c.text for c in chunks])
        matrix = self._matrix(vectors)
        ids = np.arange(self._next_id, self._next_id + len(chunks), dtype="int64")

        async with self._lock:
            await asyncio.to_thread(self._index.add_with_ids, matrix, ids)
            for fid, chunk in zip(ids.tolist(), chunks):
                self._payloads[fid] = {
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "document_title": document_meta.get("title") or document_meta.get("filename"),
                    "doc_type": document_meta.get("doc_type"),
                    "category": document_meta.get("category"),
                    "text": chunk.text,
                    "order": chunk.order,
                    "taxonomy_paths": chunk.taxonomy_paths,
                    "entity_ids": chunk.entity_ids,
                }
            self._next_id += len(chunks)
            await asyncio.to_thread(self._persist)
        return len(chunks)

    # ---------- search ----------

    async def search(
        self,
        query: str,
        top_k: int = 8,
        taxonomy_paths: Optional[list[str]] = None,
        entity_names: Optional[list[str]] = None,
    ) -> list[dict]:
        """Semantic search, optionally scoped by taxonomy branch (Python post-filter).
        Degrades to unscoped search when the taxonomy scope yields nothing."""
        if self._index is None or self._index.ntotal == 0:
            return []
        vec = self._matrix(await self.embed_async([query]))
        # Over-fetch so the taxonomy post-filter still has candidates to return.
        fetch = min(self._index.ntotal, max(top_k * 5, top_k))
        scores, ids = await asyncio.to_thread(self._index.search, vec, fetch)

        def _collect(apply_scope: bool) -> list[dict]:
            out: list[dict] = []
            for score, fid in zip(scores[0].tolist(), ids[0].tolist()):
                if fid == -1:
                    continue
                payload = self._payloads.get(fid)
                if payload is None:
                    continue
                if apply_scope and taxonomy_paths:
                    if not set(payload.get("taxonomy_paths") or []) & set(taxonomy_paths):
                        continue
                out.append({"chunk_id": payload["chunk_id"], "score": float(score), **payload})
                if len(out) >= top_k:
                    break
            return out

        hits = _collect(apply_scope=True)
        if not hits and taxonomy_paths:
            hits = _collect(apply_scope=False)
        return hits

    async def list_documents(self) -> list[dict]:
        """Distinct documents present in the index (for /docs and /status)."""
        docs: dict[str, dict] = {}
        for payload in self._payloads.values():
            doc_id = payload.get("document_id")
            if not doc_id:
                continue
            entry = docs.setdefault(doc_id, {
                "document_id": doc_id,
                "title": payload.get("document_title"),
                "doc_type": payload.get("doc_type"),
                "category": payload.get("category"),
                "chunk_count": 0,
                "taxonomy_paths": set(),
            })
            entry["chunk_count"] += 1
            entry["taxonomy_paths"].update(payload.get("taxonomy_paths") or [])
        for entry in docs.values():
            entry["taxonomy_paths"] = sorted(entry["taxonomy_paths"])
        return list(docs.values())

    async def get_document_chunks(self, document_id: str) -> list[dict]:
        chunks = [
            {"chunk_id": p["chunk_id"], "text": p.get("text", ""), "order": p.get("order", 0)}
            for p in self._payloads.values()
            if p.get("document_id") == document_id
        ]
        return sorted(chunks, key=lambda c: c["order"])


_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
