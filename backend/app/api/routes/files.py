# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
files.py
========
Static & protected file route for serving and downloading source documents.
Supports:
- Clickable PDF citations with inline viewer and page anchoring.
- Direct CSV file downloads to the user's local system with attachment headers.
- Safe path resolution and directory traversal prevention.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import urllib.parse
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.config import get_settings
from app.engine import config as engine_config

logger = logging.getLogger("app.api.files")

router = APIRouter(prefix="/files", tags=["files"])

# Candidate directories where documents are stored
_THIS_FILE = Path(__file__).resolve()
# Go up from backend/app/api/routes/files.py to context-engineering root
_REPO_ROOT = _THIS_FILE.parent.parent.parent.parent.parent
_BACKEND_ROOT = _THIS_FILE.parent.parent.parent.parent

SEARCH_DIRS: List[Path] = [
    _REPO_ROOT / "Docs" / "selected_source_documents",
    _REPO_ROOT / "Docs",
    _REPO_ROOT / "data" / "AMC",
    _REPO_ROOT / "data" / "corpus",
    _REPO_ROOT / "data" / "uploads",
    _REPO_ROOT / "data",
    _BACKEND_ROOT / "app" / "engine" / "data",
    _BACKEND_ROOT / "data",
    _BACKEND_ROOT / "data" / "source_docs",
    _REPO_ROOT / "backend" / "data" / "source_docs",
    engine_config.DATA_DIR,
]

MIME_TYPES = {
    ".pdf": "application/pdf",
    ".csv": "text/csv; charset=utf-8",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".json": "application/json",
}


def _normalize_name(name: str) -> str:
    """Normalize string for fuzzy filename matching (lowercase alphanumeric only).

    Args:
        name (str): Name of the entity or component.

    Returns:
        str: Resulting str instance.
    """
    return "".join(c.lower() for c in name if c.isalnum())


def resolve_file_path(document_id: str) -> Optional[Path]:
    """Safely resolve a document ID or filename to an existing on-disk file.
    Supports CSV, PDF, and other configured document formats.
    Prevents path traversal and checks allowed candidate directories.

    Args:
        document_id (str): Unique identifier or filename of the document.

    Returns:
        Optional[Path]: Matching Path if found, None otherwise.
    """
    if not document_id:
        return None

    # Unquote URL encoding
    decoded_name = urllib.parse.unquote(document_id).strip()

    # If full path was passed, isolate filename to prevent traversal
    if "/" in decoded_name or "\\" in decoded_name:
        clean_name = Path(decoded_name).name
        if clean_name and ".." not in clean_name:
            decoded_name = clean_name
        else:
            return None

    # Clean double dots or trailing dots
    clean_stem = decoded_name
    for ext in (".pdf", ".csv", ".xlsx", ".docx", ".txt", ".md"):
        if decoded_name.lower().endswith(ext):
            clean_stem = decoded_name[:-len(ext)]
            break
    clean_stem = clean_stem.rstrip(".")

    candidates = [
        decoded_name,
        f"{decoded_name}.csv",
        f"{decoded_name}.pdf",
        f"{clean_stem}.csv",
        f"{clean_stem}.pdf",
        f"{clean_stem}.xlsx",
        f"{clean_stem}..pdf",
    ]

    for search_dir in SEARCH_DIRS:
        if not search_dir.exists():
            continue
        # Direct check
        for cand in candidates:
            target = search_dir / cand
            if target.is_file():
                return target.resolve()

        # Normalized / fuzzy match in directory
        norm_target = _normalize_name(clean_stem)
        norm_full = _normalize_name(decoded_name)
        try:
            for item in search_dir.iterdir():
                if not item.is_file():
                    continue
                item_norm_stem = _normalize_name(item.stem)
                item_norm_full = _normalize_name(item.name)
                if item_norm_full == norm_full or item_norm_stem == norm_target:
                    return item.resolve()
        except Exception:
            continue

    return None


def resolve_pdf_path(document_id: str) -> Optional[Path]:
    """Backwards-compatible alias for resolve_file_path."""
    return resolve_file_path(document_id)


def get_pdf_url(document_id: str, page: Optional[int] = None) -> Optional[str]:
    """Returns public API URL for accessing or downloading the file if it exists.
    For PDFs, appends #page=N fragment if page is specified.
    For CSVs, returns download link.
    """
    path = resolve_file_path(document_id)
    if not path:
        return None

    encoded_name = urllib.parse.quote(path.name)
    if path.suffix.lower() == ".csv":
        return f"/api/files/{encoded_name}?download=true"

    url = f"/api/files/{encoded_name}"
    if page and int(page) > 0:
        url += f"#page={int(page)}"
    return url


@router.get("/download/{document_id:path}")
async def download_file(document_id: str):
    """Force download of the requested document (CSV, PDF, etc.) to user's local disk."""
    return await _serve_file_response(document_id=document_id, force_download=True)


@router.get("/{document_id:path}")
async def get_file(
    document_id: str,
    download: bool = Query(default=False, description="Whether to force attachment download"),
):
    """Serve or download requested document.
    - CSV files default to attachment download into user's local system.
    - PDF files default to inline viewing with page anchoring.
    """
    return await _serve_file_response(document_id=document_id, force_download=download)


async def _serve_file_response(document_id: str, force_download: bool = False):
    """Internal helper to build FileResponse with appropriate headers and disposition."""
    file_path = resolve_file_path(document_id)
    if not file_path or not file_path.is_file():
        logger.warning("Document not found: %s", document_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' unavailable or not found.",
        )

    ext = file_path.suffix.lower()
    media_type = MIME_TYPES.get(ext) or mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"

    # CSV files are always downloaded as attachment, or any file where force_download is True
    if ext == ".csv" or force_download:
        disposition = f'attachment; filename="{file_path.name}"'
    else:
        disposition = f'inline; filename="{file_path.name}"'

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=file_path.name,
        headers={
            "Content-Disposition": disposition,
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
