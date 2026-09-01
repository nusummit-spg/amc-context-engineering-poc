# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Canonical identity and provenance contract (SHA-256 deterministic IDs).

Implements the identifier model defined in Docs/convergence_implementation_plan.md:
  - source_id:           SHA-256 of canonical source URI/path + namespace
  - document_id:         Stable logical document ID, derived from source_id
  - content_sha256:      SHA-256 of exact acquired raw file bytes
  - document_version_id: SHA-256 of document_id + content_sha256
  - chunk_id:            SHA-256 of document_version_id + locator + normalized text
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional


def _sha256(text_or_bytes: str | bytes) -> str:
    """Compute standard hexadecimal SHA-256 digest."""
    if isinstance(text_or_bytes, str):
        text_or_bytes = text_or_bytes.encode("utf-8")
    return hashlib.sha256(text_or_bytes).hexdigest()


def normalize_text(text: str) -> str:
    """Normalize text whitespace and casing for deterministic hashing."""
    return re.sub(r"\s+", " ", text).strip()


def generate_source_id(source_uri_or_path: str, namespace: str = "default") -> str:
    """Generate stable source_id from canonical URI or normalized file path."""
    # Normalize Windows backslashes and strip trailing slashes
    norm_path = source_uri_or_path.replace("\\", "/").strip().lower()
    return _sha256(f"{namespace}:{norm_path}")


def generate_document_id(source_id: str) -> str:
    """Generate stable logical document_id from source_id."""
    return _sha256(f"doc:{source_id}")


def compute_content_sha256(raw_bytes: bytes) -> str:
    """Compute SHA-256 of exact acquired raw file bytes."""
    return _sha256(raw_bytes)


def generate_document_version_id(document_id: str, content_sha256: str) -> str:
    """Generate immutable document_version_id from document_id + content_sha256."""
    return _sha256(f"{document_id}:{content_sha256}")


def generate_chunk_id(
    document_version_id: str,
    section_or_page: str,
    chunk_text: str,
) -> str:
    """Generate deterministic chunk_id from version + locator + normalized text."""
    norm_text = normalize_text(chunk_text)
    norm_loc = section_or_page.strip().lower()
    return _sha256(f"{document_version_id}:{norm_loc}:{norm_text}")
