# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Rich entity extractor — deterministic domain-specific patterns.

Adapted from Agentic Testing Platform's rich_entity_extractor.py.
Extracts:
  - Regulatory citations (SEBI/RBI/IRDAI circular reference numbers)
  - Contact points (emails, phone numbers, URLs)
  - Financial table facts (structured table rows -> entity properties)

All extractors are regex-only (no LLM). They supplement the LLM NER pipeline
with pattern-matched entities that LLMs commonly miss or hallucinate.
"""
from __future__ import annotations

import re
from typing import Optional

from app.schemas.documents import Document, Section
from app.schemas.entities import (
    BaseEntity, EntityType, RegulatoryCircular, DocumentNode
)


# ─────────────────────────────────────────────────────────────────────────────
# Regulatory citation patterns
# ─────────────────────────────────────────────────────────────────────────────

_REG_PATTERNS = [
    # SEBI circular: SEBI/HO/IMD/May2026/0142
    re.compile(
        r"(SEBI/[A-Z]{2}/[A-Z]+/\w+/\d+|SEBI\.HO\.[A-Z]+\.[A-Z]+\.\d{4}/\d+)",
        re.I,
    ),
    # RBI circular: RBI/2024-25/123
    re.compile(r"(RBI/\d{4}-\d{2,4}/\d+)", re.I),
    # IRDAI circular: IRDAI/LIFE/CIR/2024/012
    re.compile(r"(IRDAI/[A-Z]+/[A-Z]+/\d{4}/\d+)", re.I),
    # Generic regulator circular reference: Circular No. 12/2025
    re.compile(r"(?:Circular\s+No\.?\s+)(\d+/\d{4})", re.I),
]

# ─────────────────────────────────────────────────────────────────────────────
# Contact point patterns
# ─────────────────────────────────────────────────────────────────────────────

_EMAIL_RE    = re.compile(r"([\w.+%-]+@[\w-]+\.[a-zA-Z]{2,})", re.I)
_PHONE_RE    = re.compile(r"((?:\+91[\s-]?)?\d{2,4}[\s-]?\d{3,4}[\s-]?\d{4})", re.I)
_URL_RE      = re.compile(r"((?:https?://|www\.)[\w./%-]+)", re.I)

# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def extract_regulatory_citations(document: Document) -> list[RegulatoryCircular]:
    """Extract regulatory circular reference numbers from document text.
    
    Returns RegulatoryCircular entities with the reference number populated.
    These supplement LLM-extracted entities with precise pattern-matched references.
    """
    seen: dict[str, RegulatoryCircular] = {}

    for section in document.sections:
        for pattern in _REG_PATTERNS:
            for match in pattern.finditer(section.text):
                ref = match.group(1).strip()
                if ref in seen:
                    if document.document_id not in seen[ref].source_document_ids:
                        seen[ref].source_document_ids.append(document.document_id)
                    continue

                # Infer issuing body from reference prefix
                issuing_body = "SEBI"
                if ref.upper().startswith("RBI"):
                    issuing_body = "RBI"
                elif ref.upper().startswith("IRDAI"):
                    issuing_body = "IRDAI"

                entity = RegulatoryCircular(
                    name=ref,
                    aliases=[],
                    reference=ref,
                    issuing_body=issuing_body,
                    source_document_ids=[document.document_id],
                    confidence=0.97,  # regex match is high confidence
                )
                seen[ref] = entity

    return list(seen.values())


def extract_contact_points(document: Document) -> list[dict]:
    """Extract contact points (email, phone, URL) from document text.
    
    Returns a list of dicts: {type, value, section_title}.
    These are stored as Document node properties rather than separate entity nodes.
    """
    contacts: list[dict] = []
    seen: set[str] = set()

    pattern_map = [
        ("email", _EMAIL_RE),
        ("phone", _PHONE_RE),
        ("url",   _URL_RE),
    ]

    for section in document.sections:
        for contact_type, pattern in pattern_map:
            for match in pattern.finditer(section.text):
                value = match.group(1).strip()
                if value in seen:
                    continue
                seen.add(value)
                contacts.append({
                    "type": contact_type,
                    "value": value,
                    "section_title": section.title or "",
                })

    return contacts


def extract_rich_entities(
    document: Document,
    existing_entities: Optional[list[BaseEntity]] = None,
) -> tuple[list[RegulatoryCircular], list[dict]]:
    """Run all rich entity extractors on a document.
    
    Returns:
        (regulatory_citations, contact_points)
        
    The caller is responsible for merging regulatory_citations with the
    existing resolved entities (dedup by reference number).
    """
    citations  = extract_regulatory_citations(document)
    contacts   = extract_contact_points(document)
    return citations, contacts
