# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""WS2 — Semantic chunking engine: heading-aware, clause-aware, max ~400 tokens.

Strategy:
  1. Chunk within section boundaries (never merge across headings).
  2. Split oversized sections on sentence/clause boundaries.
  3. Keep [TABLE] blocks intact where possible.
Token counts use a chars/4 approximation — good enough for budget control;
exact counting isn't needed at chunk granularity.
"""
import re
from typing import TYPE_CHECKING

from app.contracts.identity import generate_chunk_id
from app.schemas.documents import Chunk, Document

if TYPE_CHECKING:
    from app.schemas.documents import ParentChunk

# Sentence boundary regex — Unicode-aware, covers:
#   Latin scripts (English)
#   Devanagari (\u0900-\u097F) — Hindi, Marathi, Sanskrit
#   Bengali (\u0980-\u09FF)
#   Gujarati (\u0A80-\u0AFF)
#   Tamil (\u0B80-\u0BFF)
#   Telugu (\u0C00-\u0C7F)
#   Table row boundaries (markdown | chars)
_SENTENCE_RE = re.compile(
    r'(?<=[.!?])\s+(?=[A-Z\u0900-\u097F\u0980-\u09FF\u0A80-\u0AFF\u0B80-\u0BFF\u0C00-\u0C7F\'"(\[])'
    r'|\n(?=\n)'        # paragraph break
    r'|\n(?=\|)'        # line before a markdown table row
    r'|(?<=\|)\n',      # line after a markdown table row
    re.UNICODE,
)
_CLAUSE_RE = re.compile(r"(?=\n(?:\d+\.\d+(?:\.\d+)*|[A-Z]\.|\(\d+\)|\([a-z]\))\s+)")


def approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _split_long_text(text: str, max_tokens: int) -> list[str]:
    if approx_tokens(text) <= max_tokens:
        return [text]
    
    # Try splitting on clause boundaries first if present
    clause_splits = [s for s in _CLAUSE_RE.split(text) if s.strip()]
    if len(clause_splits) > 1:
        pieces: list[str] = []
        current: list[str] = []
        current_tokens = 0
        for clause in clause_splits:
            ct = approx_tokens(clause)
            if current and current_tokens + ct > max_tokens:
                pieces.append("\n".join(current))
                current, current_tokens = [], 0
            if ct > max_tokens:
                # Sub-split long clause by sentences
                pieces.extend(_split_by_sentence(clause, max_tokens))
            else:
                current.append(clause)
                current_tokens += ct
        if current:
            pieces.append("\n".join(current))
        return pieces

    return _split_by_sentence(text, max_tokens)


def _split_by_sentence(text: str, max_tokens: int) -> list[str]:
    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for sentence in _SENTENCE_RE.split(text):
        st = approx_tokens(sentence)
        if current and current_tokens + st > max_tokens:
            pieces.append(" ".join(current))
            current, current_tokens = [], 0
        current.append(sentence)
        current_tokens += st
    if current:
        pieces.append(" ".join(current))
    return pieces


def chunk_document(document: Document, max_tokens: int = 400) -> list[Chunk]:
    """Chunk a document into smaller pieces, with multilingual sentence boundaries and canonical SHA-256 IDs."""
    chunks: list[Chunk] = []
    order = 0
    doc_ver_id = document.document_version_id or document.document_id
    for section in document.sections:
        if not section.text.strip():
            continue
        header = f"[{document.title or document.filename}"
        if section.title:
            header += f" — {section.title}"
        header += "]\n"

        locator = section.heading_path_str or section.title or f"sec_{section.order}"

        # Keep table blocks as standalone chunks; chunk prose separately.
        blocks = re.split(r"(\[TABLE\]\n(?:.*\n?)*?)(?=\n\n|\Z)", section.text)
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            budget = max_tokens - approx_tokens(header)
            for piece in _split_long_text(block, max(budget, 50)):
                text = header + piece
                chunk_id = generate_chunk_id(doc_ver_id, f"{locator}:order_{order}", text)
                chunks.append(Chunk(
                    chunk_id=chunk_id,
                    document_id=document.document_id,
                    document_version_id=document.document_version_id,
                    source_id=document.source_id,
                    content_sha256=document.content_sha256,
                    source_filename=document.filename,
                    section_id=section.section_id,
                    section_locator=locator,
                    page_start=section.page_start,
                    page_end=section.page_end,
                    corpus_version=document.corpus_version,
                    text=text,
                    token_count=approx_tokens(text),
                    order=order,
                    metadata={"section_title": section.title, **section.metadata},
                ))
                order += 1
    return chunks


PARENT_CHUNK_SIZE    = 1200   # chars — what LLM reads as context
PARENT_CHUNK_OVERLAP = 150
CHILD_CHUNK_SIZE     = 250    # chars — what gets embedded and searched
CHILD_CHUNK_OVERLAP  = 50


def _split_at_sentence_boundary(
    text: str,
    target_size: int,
    overlap: int,
    multilingual: bool = True,
) -> list[str]:
    """Split text into chunks of approximately `target_size` characters.
    Splits ONLY at sentence boundaries. Never cuts mid-sentence.
    Overlap is applied by repeating the last `overlap` chars at the start of the next chunk.
    Table rows (lines starting with |) are treated as atomic units.
    
    Unicode ranges covered when multilingual=True:
      \u0900-\u097F  Devanagari (Hindi, Sanskrit, Marathi)
      \u0980-\u09FF  Bengali
      \u0A00-\u0A7F  Gujarati  
      \u0B80-\u0BFF  Tamil
    """
    if len(text) <= target_size:
        return [text]

    if multilingual:
        # Unicode-aware sentence splitter covering Latin + major Indian scripts
        sentence_pattern = re.compile(
            r'(?<=[.!?])\s+(?=[A-Z\u0900-\u097F\u0980-\u09FF\u0A00-\u0A7F\u0B80-\u0BFF\'"(\[])'
            r'|\n(?=\n)'       # paragraph break
            r'|\n(?=\|)'       # line before a table row
            r'|(?<=\|)\n',     # line after a table row
            re.UNICODE,
        )
    else:
        sentence_pattern = _SENTENCE_RE

    units = sentence_pattern.split(text)
    units = [u.strip() for u in units if u.strip()]

    chunks: list[str] = []
    current: list[str] = []
    cur_len = 0

    for unit in units:
        unit_len = len(unit)
        if cur_len + unit_len + 1 > target_size and current:
            chunk_text = " ".join(current)
            chunks.append(chunk_text)
            if overlap > 0:
                tail = chunk_text[-overlap:]
                m = re.search(r'(?<=[.!?\n])\s+', tail)
                overlap_text = tail[m.start():] if m else tail
                current = [overlap_text.strip(), unit]
                cur_len = len(overlap_text) + unit_len + 1
            else:
                current = [unit]
                cur_len = unit_len
        else:
            current.append(unit)
            cur_len += unit_len + 1

    if current:
        chunks.append(" ".join(current))

    # Safety: hard-split on newlines for oversized chunks (e.g. massive tables)
    final: list[str] = []
    for chunk in chunks:
        if len(chunk) <= target_size * 1.5:
            final.append(chunk)
        else:
            lines = chunk.split("\n")
            partial: list[str] = []
            p_len = 0
            for line in lines:
                if p_len + len(line) > target_size and partial:
                    final.append("\n".join(partial))
                    partial = [line]
                    p_len = len(line)
                else:
                    partial.append(line)
                    p_len += len(line) + 1
            if partial:
                final.append("\n".join(partial))

    return [c for c in final if c.strip()]


def chunk_document_hierarchical(
    document: "Document",
    parent_size: int = PARENT_CHUNK_SIZE,
    parent_overlap: int = PARENT_CHUNK_OVERLAP,
    child_size: int = CHILD_CHUNK_SIZE,
    child_overlap: int = CHILD_CHUNK_OVERLAP,
    multilingual: bool = True,
) -> tuple[list["ParentChunk"], list["Chunk"]]:
    """Build parent-child chunk hierarchy for a document.
    
    Returns (parents, children). Each child carries its parent_chunk_id.
    
    Usage:
        parents, children = chunk_document_hierarchical(document)
        # Index children in vector store (embed child.text)
        # Store parents keyed by parent_chunk_id for retrieval expansion
        # At query time: retrieve child -> fetch parent -> send parent.text to LLM
    """
    from app.schemas.documents import ParentChunk

    parents: list[ParentChunk] = []
    children: list[Chunk] = []
    parent_order = child_order = 0

    for section in document.sections:
        if not section.text.strip():
            continue

        header = f"[{document.title or document.filename}"
        if section.title:
            header += f" — {section.title}"
        header += "]\n"

        # Split section into TABLE and prose blocks
        blocks = re.split(r"(\[TABLE\]\n(?:.*\n?)*?)(?=\n\n|\Z)", section.text)

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            # Build parent chunks from block
            parent_texts = _split_at_sentence_boundary(
                block, parent_size, parent_overlap, multilingual
            )

            for pc_text in parent_texts:
                if not pc_text.strip():
                    continue

                parent_text_full = header + pc_text
                parent = ParentChunk(
                    document_id=document.document_id,
                    section_id=section.section_id,
                    text=parent_text_full,
                    token_count=approx_tokens(parent_text_full),
                    order=parent_order,
                    metadata={
                        "section_title": section.title,
                        "is_table": block.startswith("|") or "[TABLE]" in block,
                        **section.metadata,
                    },
                )
                parent_order += 1

                # Build child chunks from the same block (smaller slices)
                child_texts = _split_at_sentence_boundary(
                    pc_text, child_size, child_overlap, multilingual
                )

                for ct in child_texts:
                    if not ct.strip():
                        continue
                    child_text_full = header + ct
                    child = Chunk(
                        document_id=document.document_id,
                        section_id=section.section_id,
                        text=child_text_full,
                        token_count=approx_tokens(child_text_full),
                        order=child_order,
                        is_table=block.startswith("|") or "[TABLE]" in block,
                        parent_chunk_id=parent.parent_chunk_id,
                        metadata={
                            "section_title": section.title,
                            "parent_chunk_id": parent.parent_chunk_id,
                            **section.metadata,
                        },
                    )
                    child_order += 1
                    parent.child_ids.append(child.chunk_id)
                    children.append(child)

                parents.append(parent)

    return parents, children
