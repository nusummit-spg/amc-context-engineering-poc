# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
files.py
========
Static & protected file route for serving original PDF source documents.
Supports clickable PDF citations with inline viewer and page anchoring.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.config import get_settings
from app.engine import config as engine_config

logger = logging.getLogger("app.api.files")

router = APIRouter(prefix="/files", tags=["files"])

# Candidate directories where PDFs are stored
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
    engine_config.DATA_DIR,
]


def _normalize_name(name: str) -> str:
    """Normalize string for fuzzy filename matching (lowercase alphanumeric only)."""
    return "".join(c.lower() for c in name if c.isalnum())


def resolve_pdf_path(document_id: str) -> Optional[Path]:
    """
    Safely resolve a document ID or filename to an existing on-disk PDF file.
    Prevents path traversal and checks allowed candidate directories.
    """
    if not document_id:
        return None

    # Unquote URL encoding
    decoded_name = urllib.parse.unquote(document_id).strip()

    # If full path was passed, get basename
    if "/" in decoded_name or "\\" in decoded_name:
        clean_name = Path(decoded_name).name
        if clean_name and ".." not in clean_name:
            decoded_name = clean_name
        else:
            return None

    # Clean double dots or trailing dots
    clean_stem = decoded_name[:-4] if decoded_name.lower().endswith(".pdf") else decoded_name
    clean_stem = clean_stem.rstrip(".")

    candidates = [
        decoded_name,
        f"{decoded_name}.pdf",
        f"{clean_stem}.pdf",
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
        try:
            for item in search_dir.iterdir():
                if item.is_file() and item.suffix.lower() == ".pdf":
                    if _normalize_name(item.stem) == norm_target:
                        return item.resolve()
        except Exception:
            continue

    return None


def get_pdf_url(document_id: str, page: Optional[int] = None) -> Optional[str]:
    """
    Returns public API URL for accessing the PDF if it exists, otherwise None.
    Appends #page=N fragment if page is specified.
    """
    path = resolve_pdf_path(document_id)
    if not path:
        return None

    encoded_name = urllib.parse.quote(path.name)
    url = f"/api/files/{encoded_name}"
    if page and int(page) > 0:
        url += f"#page={int(page)}"
    return url


@router.get("/{document_id:path}")
async def get_pdf_file(document_id: str):
    """
    Stream the requested PDF document for browser viewing.
    """
    pdf_path = resolve_pdf_path(document_id)
    if not pdf_path or not pdf_path.is_file():
        logger.warning("PDF document not found: %s", document_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' unavailable or not found.",
        )

    # Return PDF with inline disposition for in-browser PDF viewing
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=pdf_path.name,
        headers={
            "Content-Disposition": f'inline; filename="{pdf_path.name}"',
            "Cache-Control": "public, max-age=3600",
        },
    )
