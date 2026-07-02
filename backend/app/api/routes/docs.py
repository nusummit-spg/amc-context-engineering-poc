"""WS3 — /docs endpoints: document metadata + chunk content for the UI modals."""
from fastapi import APIRouter, Depends

from backend.app.api.deps import Container, get_container
from backend.app.core.errors import NotFoundError
from backend.app.schemas.api import DocumentDetailOut, DocumentSummaryOut

router = APIRouter(prefix="/docs", tags=["docs"])


@router.get("", response_model=list[DocumentSummaryOut])
async def list_documents(container: Container = Depends(get_container)):
    docs = await container.vector.list_documents()
    return [
        DocumentSummaryOut(
            document_id=d["document_id"],
            filename=d.get("title") or d["document_id"],
            title=d.get("title"),
            doc_type=d.get("doc_type") or "unknown",
            category=d.get("category") or "other",
            chunk_count=d.get("chunk_count", 0),
            taxonomy_paths=d.get("taxonomy_paths", []),
        )
        for d in docs
    ]


@router.get("/{document_id}", response_model=DocumentDetailOut)
async def get_document(document_id: str, container: Container = Depends(get_container)):
    docs = await container.vector.list_documents()
    match = next((d for d in docs if d["document_id"] == document_id), None)
    if match is None:
        raise NotFoundError(f"Document not found: {document_id}")
    chunks = await container.vector.get_document_chunks(document_id)
    return DocumentDetailOut(
        document_id=document_id,
        filename=match.get("title") or document_id,
        title=match.get("title"),
        doc_type=match.get("doc_type") or "unknown",
        category=match.get("category") or "other",
        chunk_count=len(chunks),
        taxonomy_paths=match.get("taxonomy_paths", []),
        chunks=chunks,
    )
