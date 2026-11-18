"""Test launcher: run the REAL AMC app (uvicorn) for the live HTTP suite.

Only the query-embedding model is swapped: the legacy VectorStore (which loads a downloadable
embedding model) is replaced by an object that only provides embed_async(), backed by the same
deterministic embedder that built the published FAISS index. Authentication, the ASGI perimeter,
the verified retriever, PostgreSQL, Neo4j and the v2 orchestrator are all the real code.

    python -m tests.live31.serve_app31 PORT
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND.parent))

import app.vector.client as vector_client  # noqa: E402
from tests.live31.support import HashEmbedder  # noqa: E402


class _QueryEmbedderOnly:
    """Stands in for the legacy VectorStore as the query embedder and nothing else."""
    _embedder = HashEmbedder()

    def embed(self, texts):
        return self._embedder.embed(texts)

    async def embed_async(self, texts):
        return self._embedder.embed(texts)


vector_client._vector_store = _QueryEmbedderOnly()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
