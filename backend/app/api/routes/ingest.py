"""WS3 — /ingest endpoints: upload, batch, status polling."""
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile

from app.api.deps import Container, get_container
from app.core.errors import NotFoundError, ValidationFailedError
from app.schemas.api import IngestJobResponse, IngestStatusResponse
from app.tasks.queue import ingest_queue

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/file", response_model=IngestJobResponse)
async def ingest_file(
    file: UploadFile,
    container: Container = Depends(get_container),
) -> IngestJobResponse:
    upload_dir = Path(container.settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload").name
    dest = upload_dir / safe_name

    supported = container.pipeline._registry.supported_extensions()
    if dest.suffix.lower() not in supported:
        raise ValidationFailedError(
            f"Unsupported file type {dest.suffix!r}", {"supported": supported}
        )

    dest.write_bytes(await file.read())
    job = ingest_queue.enqueue([dest])
    return IngestJobResponse(job_id=job.job_id, status=job.status, filename=safe_name)


@router.post("/batch", response_model=IngestJobResponse)
async def ingest_batch(container: Container = Depends(get_container)) -> IngestJobResponse:
    """Ingest every supported file in the configured corpus directory."""
    corpus_dir = Path(container.settings.corpus_dir)
    if not corpus_dir.exists():
        raise NotFoundError(f"Corpus directory not found: {corpus_dir}")
    supported = set(container.pipeline._registry.supported_extensions())
    paths = sorted(
        p for p in corpus_dir.rglob("*") if p.is_file() and p.suffix.lower() in supported
    )
    if not paths:
        raise NotFoundError(f"No supported documents found in {corpus_dir}")
    job = ingest_queue.enqueue(paths)
    return IngestJobResponse(
        job_id=job.job_id, status=job.status,
        detail=f"{len(paths)} document(s) queued",
    )


@router.get("/status/{job_id}", response_model=IngestStatusResponse)
async def ingest_status(job_id: str) -> IngestStatusResponse:
    job = ingest_queue.get_job(job_id)
    if job is None:
        raise NotFoundError(f"Unknown ingest job: {job_id}")
    return IngestStatusResponse(
        job_id=job.job_id,
        status=job.status,
        progress={
            "stage": job.stage,
            "docs_done": job.docs_done,
            "docs_total": job.docs_total,
            "errors": job.errors,
        },
    )
