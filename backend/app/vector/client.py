"""Qdrant vector store wrapper — collection setup, embedding, upsert, scoped search.

Embeddings run locally via fastembed (no API key needed for the POC). The chunk
payload carries taxonomy paths + entity ids, enabling taxonomy-scoped hybrid
retrieval (WS5d taxonomy-path -> Qdrant filter mapper).
"""
import asyncio
import logging
from typing import Optional

from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchText,
    PointStruct,
    VectorParams,
)

from app.config import get_settings
from app.schemas.documents import Chunk

logger = logging.getLogger("vector")


class VectorStore:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )
        self._collection = settings.qdrant_collection
        self._dim = settings.embedding_dim
        self._embedder = TextEmbedding(model_name=settings.embedding_model)

    # ---------- setup ----------

    def ensure_collection(self) -> None:
        if not self._client.collection_exists(self._collection):
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=self._dim, distance=Distance.COSINE),
            )
            logger.info("Created Qdrant collection %s", self._collection)

    def ping(self) -> bool:
        try:
            self._client.get_collections()
            return True
        except Exception:
            return False

    def count(self) -> int:
        try:
            return self._client.count(self._collection).count
        except Exception:
            return 0

    # ---------- embedding ----------

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._embedder.embed(texts)]

    async def embed_async(self, texts: list[str]) -> list[list[float]]:
        # fastembed is CPU-bound / sync; run off the event loop.
        return await asyncio.to_thread(self.embed, texts)

    # ---------- indexing (WS2 batch embedding pipeline) ----------

    async def index_chunks(self, chunks: list[Chunk], document_meta: dict) -> int:
        if not chunks:
            return 0
        vectors = await self.embed_async([c.text for c in chunks])
        points = [
            PointStruct(
                id=chunk.chunk_id,
                vector=vector,
                payload={
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "document_title": document_meta.get("title") or document_meta.get("filename"),
                    "doc_type": document_meta.get("doc_type"),
                    "category": document_meta.get("category"),
                    "text": chunk.text,
                    "order": chunk.order,
                    "taxonomy_paths": chunk.taxonomy_paths,
                    "entity_ids": chunk.entity_ids,
                },
            )
            for chunk, vector in zip(chunks, vectors)
        ]
        await asyncio.to_thread(
            self._client.upsert, collection_name=self._collection, points=points
        )
        return len(points)

    # ---------- search ----------

    async def search(
        self,
        query: str,
        top_k: int = 8,
        taxonomy_paths: Optional[list[str]] = None,
        entity_names: Optional[list[str]] = None,
    ) -> list[dict]:
        """Semantic search, optionally scoped by taxonomy branch (prefix match via
        payload list) and/or entity mentions."""
        vector = (await self.embed_async([query]))[0]

        must: list[FieldCondition] = []
        if taxonomy_paths:
            # Chunks store full paths; scope = any stored path that starts with an
            # activated branch. Qdrant keyword match is exact, so we match on the
            # branch values themselves and their descendants indexed at tag time.
            must.append(
                FieldCondition(key="taxonomy_paths", match=MatchAny(any=taxonomy_paths))
            )
        query_filter = Filter(must=must) if must else None

        def _run(flt):
            return self._client.query_points(
                collection_name=self._collection,
                query=vector,
                limit=top_k,
                query_filter=flt,
                with_payload=True,
            ).points

        hits = await asyncio.to_thread(_run, query_filter)
        # If the taxonomy scope was too narrow, degrade gracefully to unscoped search.
        if not hits and query_filter is not None:
            hits = await asyncio.to_thread(_run, None)

        return [
            {
                "chunk_id": str(h.id),
                "score": h.score,
                **(h.payload or {}),
            }
            for h in hits
        ]

    async def list_documents(self) -> list[dict]:
        """Distinct documents present in the collection (for /docs and /status)."""
        docs: dict[str, dict] = {}
        offset = None
        while True:
            points, offset = await asyncio.to_thread(
                self._client.scroll,
                collection_name=self._collection,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for p in points:
                payload = p.payload or {}
                doc_id = payload.get("document_id")
                if not doc_id:
                    continue
                entry = docs.setdefault(
                    doc_id,
                    {
                        "document_id": doc_id,
                        "title": payload.get("document_title"),
                        "doc_type": payload.get("doc_type"),
                        "category": payload.get("category"),
                        "chunk_count": 0,
                        "taxonomy_paths": set(),
                    },
                )
                entry["chunk_count"] += 1
                entry["taxonomy_paths"].update(payload.get("taxonomy_paths") or [])
            if offset is None:
                break
        for entry in docs.values():
            entry["taxonomy_paths"] = sorted(entry["taxonomy_paths"])
        return list(docs.values())

    async def get_document_chunks(self, document_id: str) -> list[dict]:
        points, _ = await asyncio.to_thread(
            self._client.scroll,
            collection_name=self._collection,
            limit=1000,
            scroll_filter=Filter(
                must=[FieldCondition(key="document_id", match=MatchText(text=document_id))]
            ),
            with_payload=True,
            with_vectors=False,
        )
        chunks = [
            {
                "chunk_id": str(p.id),
                "text": (p.payload or {}).get("text", ""),
                "order": (p.payload or {}).get("order", 0),
            }
            for p in points
        ]
        return sorted(chunks, key=lambda c: c["order"])


_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
