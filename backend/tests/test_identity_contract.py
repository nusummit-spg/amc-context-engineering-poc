# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Tests for canonical identity contract and deterministic hashing."""
from app.contracts.identity import (
    compute_content_sha256,
    generate_chunk_id,
    generate_document_id,
    generate_document_version_id,
    generate_source_id,
    normalize_text,
)


def test_source_id_determinism():
    path_1 = "Docs\\selected_source_documents\\AEL_Annual_Return_FY_2024.pdf"
    path_2 = "docs/selected_source_documents/ael_annual_return_fy_2024.pdf"
    
    src_id_1 = generate_source_id(path_1)
    src_id_2 = generate_source_id(path_2)
    
    assert src_id_1 == src_id_2
    assert len(src_id_1) == 64


def test_document_and_version_id_chain():
    source_id = generate_source_id("test/doc.pdf")
    doc_id = generate_document_id(source_id)
    
    bytes_v1 = b"Hello world version 1"
    bytes_v2 = b"Hello world version 2"
    
    sha_v1 = compute_content_sha256(bytes_v1)
    sha_v2 = compute_content_sha256(bytes_v2)
    
    ver_1 = generate_document_version_id(doc_id, sha_v1)
    ver_2 = generate_document_version_id(doc_id, sha_v2)
    
    assert ver_1 != ver_2
    assert len(ver_1) == 64
    assert len(ver_2) == 64


def test_chunk_id_determinism():
    doc_ver_id = "a" * 64
    text_1 = "Section 1: Mutual   fund regulations and guidelines.  "
    text_2 = "Section 1: Mutual fund regulations and guidelines."
    
    chunk_1 = generate_chunk_id(doc_ver_id, "page_1", text_1)
    chunk_2 = generate_chunk_id(doc_ver_id, "page_1", text_2)
    
    assert chunk_1 == chunk_2
    assert len(chunk_1) == 64
