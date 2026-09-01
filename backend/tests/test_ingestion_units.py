# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""WS2 unit tests: chunker, PII scrubber, entity resolver (non-LLM paths)."""
from pathlib import Path

from app.api.deps import ALIAS_SEED_PATH
from app.ingestion.chunker import approx_tokens, chunk_document
from app.ingestion.pii import PiiScrubber
from app.schemas.documents import Document, DocumentType, Section


def _make_doc(texts: list[str]) -> Document:
    return Document(
        filename="test.txt",
        doc_type=DocumentType.TEXT,
        title="Test Doc",
        sections=[Section(title=f"S{i}", text=t, order=i) for i, t in enumerate(texts)],
    )


def test_chunker_respects_section_boundaries():
    doc = _make_doc(["First section prose.", "Second section prose."])
    chunks = chunk_document(doc, max_tokens=400)
    assert len(chunks) == 2
    assert all(c.document_id == doc.document_id for c in chunks)
    # Header carries document + section title for retrieval context
    assert "Test Doc" in chunks[0].text


def test_chunker_splits_long_sections():
    long_text = " ".join(f"Sentence number {i} about scheme holdings." for i in range(300))
    doc = _make_doc([long_text])
    chunks = chunk_document(doc, max_tokens=100)
    assert len(chunks) > 1
    assert all(c.token_count <= 160 for c in chunks)  # header + budget slack


def test_approx_tokens():
    assert approx_tokens("abcd" * 100) == 100


def test_pii_scrubber_redacts():
    scrubber = PiiScrubber()
    text = ("Investor PAN ABCDE1234F, phone +91 98765 43210, "
            "email someone@personalmail.com contacted the desk.")
    scrubbed, modified = scrubber.scrub(text)
    assert modified
    assert "ABCDE1234F" not in scrubbed
    assert "98765" not in scrubbed
    assert "someone@" not in scrubbed
    assert "[PAN-REDACTED]" in scrubbed


def test_pii_scrubber_leaves_clean_text():
    scrubber = PiiScrubber()
    text = "Infra Fund holds Adani Green at 5.8% of NAV."
    scrubbed, modified = scrubber.scrub(text)
    assert not modified
    assert scrubbed == text


def test_resolver_alias_lookup_without_llm():
    # Only the seed-based (non-LLM) path is exercised: llm=None is safe here.
    from app.extraction.resolver import EntityResolver
    resolver = EntityResolver(llm=None, alias_seed_path=ALIAS_SEED_PATH)

    entity = resolver.resolve_surface_form("Adani")
    assert entity is not None and entity.name == "Adani Group"

    entity = resolver.resolve_surface_form("Infra Fund")
    assert entity is not None and entity.name == "NuSummit Infra Fund"

    entity = resolver.resolve_surface_form("chola")
    assert entity is not None and "Cholamandalam" in entity.name

    res_unknown = resolver.resolve_surface_form("Unknown Corp XYZ")
    assert not res_unknown and res_unknown.entity is None and res_unknown.confidence == 0.0
