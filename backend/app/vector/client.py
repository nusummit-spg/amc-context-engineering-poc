# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

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
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import faiss
import numpy as np
from fastembed import TextEmbedding

from app.config import get_settings
from app.models.documents import Chunk

logger = logging.getLogger("vector")

_VECTOR_STOP_WORDS = {
    "what", "is", "the", "for", "and", "in", "to", "of", "a", "an", "under", "did", "does",
    "are", "by", "its", "it", "on", "as", "with", "from", "according", "how", "much", "many",
    "was", "were", "been", "that", "this", "these", "those", "have", "has", "had", "which"
}



class VectorStore:
    def __init__(self, faiss_dir: Optional[str] = None, corpus_version: Optional[str] = None) -> None:
        """Initialize a new instance of VectorStore.

        Args:
            faiss_dir (Optional[str]): The faiss dir.
            corpus_version (Optional[str]): Version of the active document corpus.
        """
        settings = get_settings()
        self._dim = settings.embedding_dim
        self._embedder = TextEmbedding(model_name=settings.embedding_model)
        self._corpus_version = corpus_version or getattr(settings, "active_corpus_version", "v2_baseline_20260814")
        
        if faiss_dir:
            self._dir = faiss_dir
        else:
            candidates = [
                os.path.join("./data/vector_store", self._corpus_version),
                os.path.join(str(Path(__file__).resolve().parent.parent.parent / "data" / "vector_store"), self._corpus_version),
                os.path.join(str(Path(__file__).resolve().parent.parent.parent.parent / "data" / "vector_store"), self._corpus_version),
                settings.faiss_dir,
            ]
            self._dir = candidates[0]
            for cand in candidates:
                if os.path.exists(cand) and os.path.exists(os.path.join(cand, "index.faiss")):
                    self._dir = cand
                    break

        self._index_path = os.path.join(self._dir, "index.faiss")
        self._payload_path = os.path.join(self._dir, "payloads.json")
        self._index: Optional[faiss.Index] = None
        self._payloads: dict[int, dict] = {}   # faiss id -> chunk payload
        self._next_id = 0
        self._lock = asyncio.Lock()
        self.ensure_collection()

    # ---------- setup / persistence ----------

    def _new_index(self) -> faiss.Index:
        """New index.

        Returns:
            faiss.Index: Resulting faiss.Index instance.
        """
        return faiss.IndexIDMap2(faiss.IndexFlatIP(self._dim))

    def ensure_collection(self) -> None:
        """Ensure collection.
        """
        try:
            os.makedirs(self._dir, exist_ok=True)
        except Exception as exc:
            logger.warning("Could not create vector store dir %s: %s", self._dir, exc)

        if os.path.exists(self._index_path) and os.path.exists(self._payload_path):
            try:
                raw_idx = faiss.read_index(self._index_path)
                if raw_idx.d != self._dim:
                    raise ValueError(
                        f"FAISS index dimension mismatch: index at {self._index_path} has dimension {raw_idx.d}, "
                        f"expected {self._dim} ({self._model_name}). Falling back to baseline hydration."
                    )
                if not isinstance(raw_idx, (faiss.IndexIDMap, faiss.IndexIDMap2)):
                    n = raw_idx.ntotal
                    d = raw_idx.d
                    vecs = np.zeros((n, d), dtype="float32")
                    raw_idx.reconstruct_n(0, n, vecs)
                    self._index = faiss.IndexIDMap2(faiss.IndexFlatIP(d))
                    ids = np.arange(n, dtype="int64")
                    self._index.add_with_ids(vecs, ids)
                else:
                    self._index = raw_idx
                with open(self._payload_path, "r", encoding="utf-8") as f:
                    self._payloads = {int(k): v for k, v in json.load(f).items()}
                self._next_id = (max(self._payloads) + 1) if self._payloads else 0
                logger.info("Loaded FAISS index (%d vectors) from %s", self._index.ntotal, self._dir)
            except Exception as exc:
                logger.warning("Failed to load FAISS index or payloads from %s: %s. Re-initializing empty.", self._dir, exc)
                self._index = None
                self._payloads = {}
                self._next_id = 0

        # Auto-hydrate from amc_master baseline if index is empty or unpopulated
        if self._index is None or self._index.ntotal == 0 or len(self._payloads) == 0:
            from pathlib import Path
            import pickle
            base_engine_dir = Path(__file__).resolve().parent.parent / "engine" / "faiss_indexes" / "amc_master"
            master_faiss = base_engine_dir / "index.faiss"
            master_pkl = base_engine_dir / "index.pkl"
            if master_faiss.exists() and master_pkl.exists():
                try:
                    logger.info("Auto-hydrating VectorStore from amc_master baseline (%s)", base_engine_dir)
                    raw_idx = faiss.read_index(str(master_faiss))
                    if not isinstance(raw_idx, (faiss.IndexIDMap, faiss.IndexIDMap2)):
                        n = raw_idx.ntotal
                        d = raw_idx.d
                        vecs = np.zeros((n, d), dtype="float32")
                        raw_idx.reconstruct_n(0, n, vecs)
                        self._index = faiss.IndexIDMap2(faiss.IndexFlatIP(d))
                        ids = np.arange(n, dtype="int64")
                        self._index.add_with_ids(vecs, ids)
                    else:
                        self._index = raw_idx
                    with open(master_pkl, "rb") as f:
                        master_data = pickle.load(f)
                    children = master_data.get("children", [])
                    parents = master_data.get("parents", {})
                    self._payloads = {}
                    for idx, child in enumerate(children):
                        if isinstance(child, dict):
                            parent_id = child.get("parent_id", f"p_{idx}")
                            parent = parents.get(parent_id, {})
                            parent_text = parent.get("text", child.get("text", ""))
                            src_name = child.get("source") or child.get("product_name") or f"doc_{idx}"
                            page_num = child.get("page_num", 1)
                            self._payloads[idx] = {
                                "chunk_id": child.get("child_id", f"c_{idx}"),
                                "document_id": src_name,
                                "document_title": src_name,
                                "source_filename": src_name,
                                "page_start": page_num,
                                "page_end": page_num,
                                "section_locator": f"p.{page_num}:{parent_id}",
                                "corpus_version": self._corpus_version,
                                "legacy_parent_id": parent_id,
                                "text": parent_text or child.get("text", ""),
                                "order": idx,
                                "taxonomy_paths": [],
                                "entity_ids": [],
                            }
                    self._next_id = len(self._payloads)
                    self._persist()
                    logger.info("Successfully hydrated VectorStore with %d vectors from amc_master", self._index.ntotal)
                except Exception as exc:
                    logger.warning("Failed to auto-hydrate VectorStore from amc_master: %s", exc)
                    self._index = self._new_index()
                    self._payloads = {}
                    self._next_id = 0
            else:
                self._index = self._new_index()
                self._payloads = {}
                self._next_id = 0
                logger.info("Initialized empty in-memory FAISS index at %s", self._dir)

    def _persist(self) -> None:
        """Persist.
        """
        if self._index is None:
            return
        try:
            os.makedirs(self._dir, exist_ok=True)
            faiss.write_index(self._index, self._index_path)
            with open(self._payload_path, "w", encoding="utf-8") as f:
                json.dump({str(k): v for k, v in self._payloads.items()}, f)
        except Exception as exc:
            logger.warning("Could not persist FAISS index to %s: %s", self._dir, exc)

    def ping(self) -> bool:
        """Check connectivity and availability of the service.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        return self._index is not None

    def count(self) -> int:
        """Count.

        Returns:
            int: Resulting int instance.
        """
        return self._index.ntotal if self._index is not None else 0

    # ---------- embedding ----------

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed.

        Args:
            texts (list[str]): Collection or list of texts.

        Returns:
            list[list[float]]: List of resulting items or records.
        """
        return [v.tolist() for v in self._embedder.embed(texts)]

    async def embed_async(self, texts: list[str]) -> list[list[float]]:
        """Embed async.

        Args:
            texts (list[str]): Collection or list of texts.

        Returns:
            list[list[float]]: List of resulting items or records.
        """
        # fastembed is CPU-bound / sync; run off the event loop.
        return await asyncio.to_thread(self.embed, texts)

    def _matrix(self, vectors: list[list[float]]) -> np.ndarray:
        """Matrix.

        Args:
            vectors (list[list[float]]): Collection or list of vectors.

        Returns:
            np.ndarray: Resulting np.ndarray instance.
        """
        m = np.asarray(vectors, dtype="float32")
        faiss.normalize_L2(m)   # cosine via inner product
        return m

    # ---------- indexing (WS2 batch embedding pipeline) ----------

    async def index_chunks(self, chunks: list[Chunk], document_meta: dict) -> int:
        """Index chunks.

        Args:
            chunks (list[Chunk]): List of retrieved text chunks.
            document_meta (dict): The document meta.

        Returns:
            int: Resulting int instance.
        """
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
                    "document_version_id": getattr(chunk, "document_version_id", None),
                    "source_id": getattr(chunk, "source_id", None),
                    "content_sha256": getattr(chunk, "content_sha256", None),
                    "source_filename": getattr(chunk, "source_filename", None) or document_meta.get("filename"),
                    "page_start": getattr(chunk, "page_start", None),
                    "page_end": getattr(chunk, "page_end", None),
                    "section_locator": getattr(chunk, "section_locator", None),
                    "corpus_version": getattr(chunk, "corpus_version", None) or self._corpus_version,
                    "legacy_parent_id": getattr(chunk, "legacy_parent_id", None),
                    "document_title": document_meta.get("title") or document_meta.get("filename"),
                    "doc_type": document_meta.get("doc_type"),
                    "category": document_meta.get("category"),
                    "user_id": getattr(chunk, "user_id", None) or document_meta.get("user_id"),
                    "tenant_id": getattr(chunk, "tenant_id", None) or document_meta.get("tenant_id"),
                    "text": chunk.text,
                    "order": chunk.order,
                    "taxonomy_paths": chunk.taxonomy_paths,
                    "entity_ids": chunk.entity_ids,
                }
            self._next_id += len(chunks)
            await asyncio.to_thread(self._persist)
        return len(chunks)

    async def add(self, documents: list[dict]) -> list[str]:
        """Add arbitrary document dicts into the FAISS index.

        Args:
            documents (list[dict]): Collection or list of documents.

        Returns:
            list[str]: List of resulting items or records.
        """
        if not documents:
            return []
        if self._index is None:
            self.ensure_collection()
        texts = [doc.get("text", "") for doc in documents]
        vectors = await self.embed_async(texts)
        matrix = self._matrix(vectors)
        ids = np.arange(self._next_id, self._next_id + len(documents), dtype="int64")

        chunk_ids: list[str] = []
        async with self._lock:
            await asyncio.to_thread(self._index.add_with_ids, matrix, ids)
            for fid, doc in zip(ids.tolist(), documents):
                cid = doc.get("chunk_id") or doc.get("id") or f"doc_{fid}"
                chunk_ids.append(cid)
                meta = doc.get("metadata") or {}
                self._payloads[fid] = {
                    "chunk_id": cid,
                    "document_id": doc.get("document_id") or meta.get("document_id") or cid,
                    "document_title": doc.get("document_title") or meta.get("title") or doc.get("title"),
                    "text": doc.get("text", ""),
                    "user_id": doc.get("user_id") or meta.get("user_id"),
                    "tenant_id": doc.get("tenant_id") or meta.get("tenant_id"),
                    "indexed_at": meta.get("indexed_at"),
                    "metadata": meta,
                    "order": doc.get("order", fid),
                    "taxonomy_paths": doc.get("taxonomy_paths") or meta.get("taxonomy_paths") or [],
                    "entity_ids": doc.get("entity_ids") or meta.get("entity_ids") or [],
                }
            self._next_id += len(documents)
            await asyncio.to_thread(self._persist)
        return chunk_ids

    async def add_documents(
        self,
        documents: list[dict],
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> list[str]:
        """Add documents with injected ownership metadata.

        Args:
            documents (list[dict]): Collection or list of documents.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            list[str]: List of resulting items or records.
        """
        for doc in documents:
            if "metadata" not in doc:
                doc["metadata"] = {}
            if user_id:
                doc["metadata"]["user_id"] = user_id
                doc["user_id"] = user_id
            if tenant_id:
                doc["metadata"]["tenant_id"] = tenant_id
                doc["tenant_id"] = tenant_id
            doc["metadata"]["indexed_at"] = datetime.now(timezone.utc).isoformat()
        return await self.add(documents)

    # ---------- search ----------

    async def search(
        self,
        query: Union[str, list[float]],
        top_k: int = 8,
        taxonomy_paths: Optional[list[str]] = None,
        entity_names: Optional[list[str]] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        metadata_filter: Optional[dict] = None,
    ) -> list[dict]:
        """Semantic search, optionally scoped by taxonomy branch and filtered by user/tenant.

        Args:
            query (Union[str, list[float]]): Search query or input text.
            top_k (int): Number of top results to return.
            taxonomy_paths (Optional[list[str]]): Collection or list of taxonomy paths.
            entity_names (Optional[list[str]]): Collection or list of entity names.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.
            metadata_filter (Optional[dict]): The metadata filter.

        Returns:
            list[dict]: List of resulting items or records.
        """
        if self._index is None or self._index.ntotal == 0:
            return []
        if isinstance(query, (list, np.ndarray)):
            vec = self._matrix([query])
        else:
            vec = self._matrix(await self.embed_async([query]))

        fetch = min(self._index.ntotal, max(top_k * 30, 300))
        scores, ids = await asyncio.to_thread(self._index.search, vec, fetch)

        # Extract search query tokens for hybrid lexical scoring (strip HyDE text if present)
        q_tokens = []
        if isinstance(query, str):
            actual_q = query.split("\n\nHYPOTHETICAL DOCUMENT:")[0]
            clean_q = re.sub(r"[^a-zA-Z0-9_\-\.]", " ", actual_q.lower())
            q_tokens = [w for w in clean_q.split() if len(w) >= 3 and w not in _VECTOR_STOP_WORDS]

        # Build candidate pairs from dense FAISS search + top lexical matches
        dense_candidates = [(float(score), fid) for score, fid in zip(scores[0].tolist(), ids[0].tolist()) if fid != -1]
        dense_fid_set = {fid for _, fid in dense_candidates}
        lex_supplement: list[tuple[float, int]] = []

        if len(q_tokens) >= 2 and self._payloads:
            lex_hits: list[tuple[int, int]] = []
            seen_lex_prefixes = set()
            for fid, p in self._payloads.items():
                if fid in dense_fid_set:
                    continue
                raw_t = p.get("text", "")
                t_low = raw_t.lower()
                mc = sum(1 for kw in q_tokens if kw in t_low)
                if mc >= 2:
                    norm = re.sub(r"\s+", " ", raw_t[:140].strip().lower())
                    if norm not in seen_lex_prefixes:
                        seen_lex_prefixes.add(norm)
                        lex_hits.append((fid, mc))
            lex_hits.sort(key=lambda x: x[1], reverse=True)
            for fid, mc in lex_hits[:40]:
                base_sc = 0.75 + (0.10 * (mc / len(q_tokens)))
                lex_supplement.append((base_sc, fid))

        candidate_pool = dense_candidates + lex_supplement

        def _collect(apply_scope: bool) -> list[dict]:
            candidates: list[dict] = []
            seen_prefixes = set()

            for score, fid in candidate_pool:
                payload = self._payloads.get(fid)
                if payload is None:
                    continue

                # User isolation
                doc_user = payload.get("user_id")
                if user_id:
                    if doc_user is not None and doc_user != user_id:
                        continue
                elif doc_user is not None:
                    continue

                # Tenant isolation
                doc_tenant = payload.get("tenant_id")
                if tenant_id:
                    if doc_tenant is not None and doc_tenant != tenant_id:
                        continue
                elif doc_tenant is not None:
                    continue

                # Metadata filter
                if metadata_filter:
                    match = True
                    meta = payload.get("metadata") or {}
                    for mk, mv in metadata_filter.items():
                        if payload.get(mk) != mv and meta.get(mk) != mv:
                            match = False
                            break
                    if not match:
                        continue

                if apply_scope and taxonomy_paths:
                    if not set(payload.get("taxonomy_paths") or []) & set(taxonomy_paths):
                        continue

                # Text-level deduplication: avoid duplicate copies of the same section
                raw_text = payload.get("text", "")
                norm_snip = re.sub(r"\s+", " ", raw_text[:140].strip().lower())
                if norm_snip in seen_prefixes:
                    continue
                seen_prefixes.add(norm_snip)

                # Lexical keyword boost
                final_score = float(score)
                if q_tokens:
                    t_low = raw_text.lower()
                    kw_matches = sum(1 for kw in q_tokens if kw in t_low)
                    kw_ratio = kw_matches / len(q_tokens)
                    final_score += 0.20 * kw_ratio

                # Clamp strictly between 0.0 and 1.0 to satisfy Pydantic RetrievedChunk model constraints
                clamped_score = min(1.0, max(0.0, round(final_score, 4)))
                candidates.append({"chunk_id": payload["chunk_id"], "score": clamped_score, **payload})

            # Sort by hybrid final_score
            candidates.sort(key=lambda x: x["score"], reverse=True)
            return candidates[:top_k]

        hits = _collect(apply_scope=True)
        if len(hits) < top_k and taxonomy_paths:
            seen_ids = {h["chunk_id"] for h in hits}
            seen_texts = {re.sub(r"\s+", " ", h.get("text", "")[:140].strip().lower()) for h in hits}
            fallback_hits = _collect(apply_scope=False)
            for h in fallback_hits:
                snip = re.sub(r"\s+", " ", h.get("text", "")[:140].strip().lower())
                if h["chunk_id"] not in seen_ids and snip not in seen_texts:
                    hits.append(h)
                    seen_ids.add(h["chunk_id"])
                    seen_texts.add(snip)
                    if len(hits) >= top_k:
                        break
        return hits

    async def similarity_search(
        self,
        embedding: Optional[list[float]] = None,
        query: Optional[str] = None,
        limit: int = 10,
        metadata_filter: Optional[dict] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> list[dict]:
        """Similarity search by embedding or query text with metadata filtering.

        Args:
            embedding (Optional[list[float]]): The embedding.
            query (Optional[str]): Search query or input text.
            limit (int): Maximum number of records to return.
            metadata_filter (Optional[dict]): The metadata filter.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            list[dict]: List of resulting items or records.
        """
        if self._index is None or self._index.ntotal == 0:
            return []
        if embedding is not None:
            vec = self._matrix([embedding])
        elif query is not None:
            vec = self._matrix(await self.embed_async([query]))
        else:
            return []

        fetch = min(self._index.ntotal, max(limit * 5, limit))
        scores, ids = await asyncio.to_thread(self._index.search, vec, fetch)

        out: list[dict] = []
        for score, fid in zip(scores[0].tolist(), ids[0].tolist()):
            if fid == -1:
                continue
            payload = self._payloads.get(fid)
            if payload is None:
                continue

            doc_user = payload.get("user_id")
            if user_id:
                if doc_user is not None and doc_user != user_id:
                    continue
            elif doc_user is not None:
                continue

            doc_tenant = payload.get("tenant_id")
            if tenant_id:
                if doc_tenant is not None and doc_tenant != tenant_id:
                    continue
            elif doc_tenant is not None:
                continue

            if metadata_filter:
                match = True
                meta = payload.get("metadata") or {}
                for mk, mv in metadata_filter.items():
                    if payload.get(mk) != mv and meta.get(mk) != mv:
                        match = False
                        break
                if not match:
                    continue

            out.append({"chunk_id": payload["chunk_id"], "score": float(score), **payload})
            if len(out) >= limit:
                break
        return out

    async def list_documents(
        self,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> list[dict]:
        """Distinct documents present in the index, scoped by user and tenant.

        Args:
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            list[dict]: List of resulting items or records.
        """
        docs: dict[str, dict] = {}
        for payload in self._payloads.values():
            doc_id = payload.get("document_id")
            if not doc_id:
                continue
            doc_user = payload.get("user_id")
            if user_id:
                if doc_user is not None and doc_user != user_id:
                    continue
            elif doc_user is not None:
                continue
            doc_tenant = payload.get("tenant_id")
            if tenant_id:
                if doc_tenant is not None and doc_tenant != tenant_id:
                    continue
            elif doc_tenant is not None:
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

    async def get_document_chunks(
        self,
        document_id: str,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> list[dict]:
        """Retrieve document chunks.

        Args:
            document_id (str): Unique identifier of the document.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            list[dict]: List of resulting items or records.
        """
        chunks = []
        for p in self._payloads.values():
            if p.get("document_id") != document_id:
                continue
            doc_user = p.get("user_id")
            if user_id:
                if doc_user is not None and doc_user != user_id:
                    continue
            elif doc_user is not None:
                continue
            doc_tenant = p.get("tenant_id")
            if tenant_id:
                if doc_tenant is not None and doc_tenant != tenant_id:
                    continue
            elif doc_tenant is not None:
                continue
            chunks.append({"chunk_id": p["chunk_id"], "text": p.get("text", ""), "order": p.get("order", 0)})
        return sorted(chunks, key=lambda c: c["order"])

    async def ingest_synthetic_patch_chunk(
        self,
        patch_id: str,
        entity_id: str,
        attribute: str,
        value: Any,
        source: str = "Regulatory Erratum",
        context_snippet: Optional[str] = None,
    ) -> str:
        """Option 3: Ingest an authoritative synthetic patch chunk into the FAISS vector index.

        Args:
            patch_id (str): Unique identifier of the patch.
            entity_id (str): Unique identifier of the entity.
            attribute (str): The attribute.
            value (Any): The value.
            source (str): The source.
            context_snippet (Optional[str]): The context snippet.

        Returns:
            str: Resulting str instance.
        """
        clean_attr = str(attribute).replace("_", " ").title()
        doc_text = (
            f"Official Regulatory Erratum and Verified Master Data: "
            f"The {clean_attr} for {entity_id} is officially {value}. "
            f"This verified filing supersedes all prior documents and prospectus excerpts."
        )
        doc = {
            "chunk_id": f"synthetic_patch_{patch_id}",
            "document_id": f"patch_{patch_id}",
            "document_title": f"Verified Erratum: {entity_id} ({clean_attr})",
            "source_filename": f"erratum_{entity_id.lower().replace(' ', '_')}.pdf",
            "text": doc_text,
            "page_start": 1,
            "page_end": 1,
            "metadata": {
                "is_synthetic_patch": True,
                "patch_id": patch_id,
                "entity_id": entity_id,
                "attribute": attribute,
                "value": str(value),
                "indexed_at": datetime.now(timezone.utc).isoformat(),
            },
            "taxonomy_paths": [],
            "entity_ids": [entity_id],
        }
        res = await self.add_documents([doc])
        logger.info("Ingested synthetic vector chunk for patch %s: %s.%s = %s", patch_id, entity_id, attribute, value)
        return res[0] if res else f"synthetic_patch_{patch_id}"

    async def evict_synthetic_patch_chunk(self, patch_id: str) -> bool:
        """Option 3: Evict synthetic patch chunk from vector store index.

        Args:
            patch_id (str): Unique identifier of the patch.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        target_chunk_id = f"synthetic_patch_{patch_id}"
        async with self._lock:
            found_key = None
            for fid, payload in list(self._payloads.items()):
                if payload.get("chunk_id") == target_chunk_id or (payload.get("metadata") or {}).get("patch_id") == patch_id:
                    found_key = fid
                    break
            if found_key is not None:
                del self._payloads[found_key]
                await asyncio.to_thread(self._persist)
                logger.info("Evicted synthetic vector chunk for patch %s", patch_id)
                return True
        return False


class UserScopedVectorStore:
    """Vector store wrapper with user/tenant metadata filtering."""

    def __init__(
        self,
        base_client: VectorStore,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Initialize a new instance of UserScopedVectorStore.

        Args:
            base_client (VectorStore): The base client.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.
        """
        self.client = base_client
        self.user_id = user_id
        self.tenant_id = tenant_id

    async def search(
        self,
        query: Union[str, list[float]],
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        top_k: int = 8,
        limit: Optional[int] = None,
        taxonomy_paths: Optional[list[str]] = None,
        entity_names: Optional[list[str]] = None,
        metadata_filter: Optional[dict] = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Search vector store with user/tenant filtering.

        Args:
            query (Union[str, list[float]]): Search query or input text.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.
            top_k (int): Number of top results to return.
            limit (Optional[int]): Maximum number of records to return.
            taxonomy_paths (Optional[list[str]]): Collection or list of taxonomy paths.
            entity_names (Optional[list[str]]): Collection or list of entity names.
            metadata_filter (Optional[dict]): The metadata filter.

        Returns:
            list[dict[str, Any]]: List of resulting items or records.
        """
        eff_user = user_id if user_id is not None else self.user_id
        eff_tenant = tenant_id if tenant_id is not None else self.tenant_id
        eff_k = limit if limit is not None else top_k

        if isinstance(query, (list, np.ndarray)):
            return await self.client.similarity_search(
                embedding=query,
                limit=eff_k,
                metadata_filter=metadata_filter,
                user_id=eff_user,
                tenant_id=eff_tenant,
            )

        return await self.client.search(
            query=query,
            top_k=eff_k,
            taxonomy_paths=taxonomy_paths,
            entity_names=entity_names,
            user_id=eff_user,
            tenant_id=eff_tenant,
            metadata_filter=metadata_filter,
            **kwargs,
        )

    async def similarity_search(
        self,
        embedding: Optional[list[float]] = None,
        query: Optional[str] = None,
        limit: int = 10,
        metadata_filter: Optional[dict] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Search with user/tenant metadata filter.

        Args:
            embedding (Optional[list[float]]): The embedding.
            query (Optional[str]): Search query or input text.
            limit (int): Maximum number of records to return.
            metadata_filter (Optional[dict]): The metadata filter.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            list[dict[str, Any]]: List of resulting items or records.
        """
        eff_user = user_id if user_id is not None else self.user_id
        eff_tenant = tenant_id if tenant_id is not None else self.tenant_id
        return await self.client.similarity_search(
            embedding=embedding,
            query=query,
            limit=limit,
            metadata_filter=metadata_filter,
            user_id=eff_user,
            tenant_id=eff_tenant,
        )

    async def add_documents(
        self,
        documents: list[dict[str, Any]],
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> list[str]:
        """Add documents to vector store with ownership metadata.

        Args:
            documents (list[dict[str, Any]]): Collection or list of documents.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            list[str]: List of resulting items or records.
        """
        eff_user = user_id if user_id is not None else self.user_id
        eff_tenant = tenant_id if tenant_id is not None else self.tenant_id
        return await self.client.add_documents(documents, user_id=eff_user, tenant_id=eff_tenant)

    async def add(
        self,
        documents: list[dict[str, Any]],
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> list[str]:
        """Add documents with ownership metadata.

        Args:
            documents (list[dict[str, Any]]): Collection or list of documents.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            list[str]: List of resulting items or records.
        """
        eff_user = user_id if user_id is not None else self.user_id
        eff_tenant = tenant_id if tenant_id is not None else self.tenant_id
        return await self.client.add_documents(documents, user_id=eff_user, tenant_id=eff_tenant)

    async def index_chunks(
        self,
        chunks: list[Chunk],
        document_meta: dict,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> int:
        """Index chunks with user and tenant metadata.

        Args:
            chunks (list[Chunk]): List of retrieved text chunks.
            document_meta (dict): The document meta.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            int: Resulting int instance.
        """
        eff_user = user_id if user_id is not None else self.user_id
        eff_tenant = tenant_id if tenant_id is not None else self.tenant_id
        meta = dict(document_meta)
        if eff_user and "user_id" not in meta:
            meta["user_id"] = eff_user
        if eff_tenant and "tenant_id" not in meta:
            meta["tenant_id"] = eff_tenant
        return await self.client.index_chunks(chunks, meta)

    async def list_documents(
        self,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> list[dict]:
        """List documents.

        Args:
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            list[dict]: List of resulting items or records.
        """
        eff_user = user_id if user_id is not None else self.user_id
        eff_tenant = tenant_id if tenant_id is not None else self.tenant_id
        return await self.client.list_documents(user_id=eff_user, tenant_id=eff_tenant)

    async def get_document_chunks(
        self,
        document_id: str,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> list[dict]:
        """Retrieve document chunks.

        Args:
            document_id (str): Unique identifier of the document.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            list[dict]: List of resulting items or records.
        """
        eff_user = user_id if user_id is not None else self.user_id
        eff_tenant = tenant_id if tenant_id is not None else self.tenant_id
        return await self.client.get_document_chunks(document_id, user_id=eff_user, tenant_id=eff_tenant)

    def __getattr__(self, name: str) -> Any:
        """Special dunder method for getattr.

        Args:
            name (str): Name of the entity or component.

        Returns:
            Any: Resulting Any instance.
        """
        return getattr(self.client, name)


_vector_store: Optional[VectorStore] = None


def get_base_vector_store() -> VectorStore:
    """Retrieve base vector store.

    Returns:
        VectorStore: Resulting VectorStore instance.
    """
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store


def get_vector_store(
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> UserScopedVectorStore:
    """Retrieve vector store.

    Args:
        user_id (Optional[str]): Unique identifier of the user.
        tenant_id (Optional[str]): Unique identifier of the tenant.

    Returns:
        UserScopedVectorStore: Resulting UserScopedVectorStore instance.
    """
    base = get_base_vector_store()
    return UserScopedVectorStore(base, user_id=user_id, tenant_id=tenant_id)

