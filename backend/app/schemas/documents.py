"""WS5a — Unified document schema: Document, Section, Chunk.

Every parser (PDF, DOCX, PPTX, email, Excel, text) normalizes into these models,
so chunking / PII scrubbing / embedding / extraction are format-agnostic.
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    EMAIL = "email"
    EXCEL = "excel"
    MARKDOWN = "markdown"
    TEXT = "text"


class DocumentCategory(str, Enum):
    """Coarse business category — refined later by the taxonomy classifier."""
    RESEARCH_NOTE = "research_note"
    SCHEME_SID = "scheme_sid"
    REGULATORY_CIRCULAR = "regulatory_circular"
    COMPLIANCE_MEMO = "compliance_memo"
    EMAIL_THREAD = "email_thread"
    SECTOR_DECK = "sector_deck"
    CALL_TRANSCRIPT = "call_transcript"
    TRACKER = "tracker"
    OTHER = "other"


class Section(BaseModel):
    """A logical section of a document (heading-scoped, slide, sheet, or email in a thread)."""
    section_id: str = Field(default_factory=lambda: str(uuid4()))
    title: Optional[str] = None
    level: int = 1  # heading depth; 1 = top level
    text: str
    order: int = 0
    metadata: dict = Field(default_factory=dict)  # page numbers, slide index, sheet name...


class Chunk(BaseModel):
    """Retrieval unit stored in Qdrant. Carries taxonomy tags + entity refs as payload."""
    chunk_id: str = Field(default_factory=lambda: str(uuid4()))
    document_id: str
    section_id: Optional[str] = None
    text: str
    token_count: int = 0
    order: int = 0
    # populated by ingestion pipeline:
    taxonomy_paths: list[str] = Field(default_factory=list)  # e.g. "Risk/Concentration Exposure/Issuer Group"
    entity_ids: list[str] = Field(default_factory=list)      # canonical entity ids mentioned in this chunk
    pii_scrubbed: bool = False
    metadata: dict = Field(default_factory=dict)


class Document(BaseModel):
    """Unified representation of any ingested source file."""
    document_id: str = Field(default_factory=lambda: str(uuid4()))
    filename: str
    doc_type: DocumentType
    category: DocumentCategory = DocumentCategory.OTHER
    title: Optional[str] = None
    author: Optional[str] = None
    created_at: Optional[datetime] = None
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    source_path: Optional[str] = None
    sections: list[Section] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)  # email headers, page count, etc.

    @property
    def full_text(self) -> str:
        return "\n\n".join(s.text for s in self.sections)
