"""WS5a — Document schemas: Document, Section, Chunk, IngestionJob.

Every parser (PDF, DOCX, PPTX, email, Excel, text) normalizes into these models
so chunking / PII scrubbing / embedding / extraction are format-agnostic.

Unified with WS5a extended design:
  - Section gains page_end >= page_start validator
  - Chunk gains minimum text length validation (20 chars) and deduplication of taxonomy_paths
  - Document gains chunk_count computed property
  - IngestionJob added for structured async job tracking
    (replaces the bare string-status dicts in the ingestion queue)
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class DocumentType(str, Enum):
    PDF      = "pdf"
    DOCX     = "docx"
    PPTX     = "pptx"
    EMAIL    = "email"
    EXCEL    = "excel"
    MARKDOWN = "markdown"
    TEXT     = "text"


class DocumentCategory(str, Enum):
    """Coarse business category — refined later by the taxonomy classifier.
    Set during ingestion (parser heuristic or filename pattern match).
    """
    RESEARCH_NOTE       = "research_note"
    SCHEME_SID          = "scheme_sid"
    REGULATORY_CIRCULAR = "regulatory_circular"
    COMPLIANCE_MEMO     = "compliance_memo"
    EMAIL_THREAD        = "email_thread"
    SECTOR_DECK         = "sector_deck"
    CALL_TRANSCRIPT     = "call_transcript"
    TRACKER             = "tracker"
    OTHER               = "other"


class IngestionStatus(str, Enum):
    QUEUED     = "queued"
    RUNNING    = "running"
    COMPLETED  = "completed"
    FAILED     = "failed"


class Section(BaseModel):
    """A logical section of a document (heading-scoped block, slide, sheet, or email)."""
    section_id: str           = Field(default_factory=lambda: str(uuid4()))
    title:      Optional[str] = None
    level:      int           = Field(default=1, ge=1, le=6, description="Heading depth; 1 = top level")
    text:       str
    order:      int           = Field(default=0, ge=0)
    page_start: Optional[int] = Field(default=None, ge=1)
    page_end:   Optional[int] = Field(default=None, ge=1)
    metadata:   dict          = Field(default_factory=dict)  # slide index, sheet name, email metadata…

    @model_validator(mode="after")
    def page_end_not_before_start(self) -> "Section":
        """page_end must not be before page_start if both are provided."""
        if self.page_start is not None and self.page_end is not None:
            if self.page_end < self.page_start:
                raise ValueError(
                    f"page_end ({self.page_end}) must be >= page_start ({self.page_start})"
                )
        return self


class Chunk(BaseModel):
    """Retrieval unit stored in Qdrant. Carries taxonomy tags + entity refs as payload."""
    chunk_id:      str           = Field(default_factory=lambda: str(uuid4()))
    document_id:   str
    section_id:    Optional[str] = None
    text:          str           = Field(min_length=20, description="Minimum 20 chars to ensure meaningful retrieval")
    token_count:   int           = Field(default=0, ge=0)
    order:         int           = Field(default=0, ge=0)
    # Populated by ingestion pipeline:
    taxonomy_paths: list[str]   = Field(
        default_factory=list,
        description="Slash-joined taxonomy paths, e.g. 'Risk/Concentration Exposure/Issuer Group'",
    )
    entity_ids:    list[str]    = Field(default_factory=list)
    pii_scrubbed:  bool         = False
    is_table:      bool         = False     # True when chunk originated from a table
    metadata:      dict         = Field(default_factory=dict)

    @field_validator("taxonomy_paths", mode="before")
    @classmethod
    def deduplicate_taxonomy_paths(cls, v: list[str]) -> list[str]:
        """Remove duplicate taxonomy paths preserving order."""
        seen: set[str] = set()
        return [p for p in v if p not in seen and not seen.add(p)]  # type: ignore[func-returns-value]


class Document(BaseModel):
    """Unified representation of any ingested source file."""
    document_id: str                     = Field(default_factory=lambda: str(uuid4()))
    filename:    str
    doc_type:    DocumentType
    category:    DocumentCategory        = DocumentCategory.OTHER
    title:       Optional[str]           = None
    author:      Optional[str]           = None
    created_at:  Optional[datetime]      = None
    ingested_at: datetime                = Field(default_factory=datetime.utcnow)
    source_path: Optional[str]           = None
    sections:    list[Section]           = Field(default_factory=list)
    chunk_ids:   list[str]               = Field(default_factory=list)
    metadata:    dict                    = Field(default_factory=dict)

    @property
    def full_text(self) -> str:
        """Concatenated text of all sections."""
        return "\n\n".join(s.text for s in self.sections)

    @property
    def chunk_count(self) -> int:
        """Number of chunks produced from this document."""
        return len(self.chunk_ids)


class IngestionJob(BaseModel):
    """Tracks an async ingestion job through its lifecycle.

    Lifecycle:  QUEUED → RUNNING → COMPLETED | FAILED

    progress_pct = (docs_done / total_files) * 100
    """
    job_id:      str             = Field(default_factory=lambda: str(uuid4()))
    status:      IngestionStatus = IngestionStatus.QUEUED
    total_files: int             = Field(default=0, ge=0)
    docs_done:   int             = Field(default=0, ge=0)
    docs_failed: int             = Field(default=0, ge=0)
    stage:       str             = Field(default="queued", description="Current pipeline stage label")
    errors:      list[str]       = Field(default_factory=list)
    created_at:  datetime        = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    @model_validator(mode="after")
    def processed_not_exceeds_total(self) -> "IngestionJob":
        if self.docs_done + self.docs_failed > self.total_files:
            raise ValueError(
                f"docs_done ({self.docs_done}) + docs_failed ({self.docs_failed}) "
                f"= {self.docs_done + self.docs_failed} exceeds total_files ({self.total_files})"
            )
        return self

    @property
    def progress_pct(self) -> float:
        """Completion percentage (docs processed out of total, including failures)."""
        if self.total_files == 0:
            return 0.0
        return round(((self.docs_done + self.docs_failed) / self.total_files) * 100, 1)
